import hashlib
import os
import logging
import asyncio
import struct
import numpy as np

#logging.basicConfig(level=logging.DEBUG)


def H(value: bytes) -> bytes:
    """Random oracle H simulated using SHA-256."""
    return hashlib.sha256(value).digest()[:17]  # λ+1 bits = 17 bytes (~136 bits)


async def _send_data(writer: asyncio.StreamWriter, data: bytes) -> None:
    """Efficiently send data with length prefix."""
    length = struct.pack('>I', len(data))
    writer.write(length + data)
    await writer.drain()


async def _receive_data(reader: asyncio.StreamReader) -> bytes:
    """Efficiently receive length-prefixed data."""
    length_bytes = await reader.readexactly(4)
    length = struct.unpack('>I', length_bytes)[0]
    return await reader.readexactly(length)



# --- Compact Com / Open functions ---

def ComH_compact(security_level: int, b_array: np.ndarray):
    """
    Produce compact contiguous randomness buffer and commitments buffer.
    Returns: (rand_all: np.uint8 (n, rand_size), coms: np.uint8 (n, com_size))
    """
    b_array = np.asarray(b_array, dtype=np.uint8).flatten()
    n = len(b_array)
    rand_size = security_level // 8
    com_size = 17  # as in your H

    if not np.all((b_array == 0) | (b_array == 1)):
        raise ValueError("All elements must be 0 or 1")

    # Allocate contiguous randomness buffer: n * rand_size bytes
    # Use os.urandom to fill the whole block and copy once.
    rand_bytes = os.urandom(n * rand_size)
    rand_all = np.frombuffer(rand_bytes, dtype=np.uint8).copy().reshape((n, rand_size))

    # Allocate commitment buffer
    coms = np.empty((n, com_size), dtype=np.uint8)

    # Prepare a reusable bytearray to avoid creating many small bytes objects
    # We'll create a bytearray of size 1 + rand_size and fill it per-row
    buf = bytearray(1 + rand_size)
    m = hashlib.sha256

    for i in range(n):
        buf[0] = int(b_array[i])
        # assign the row bytes into the buffer
        buf[1:] = memoryview(rand_all[i])  # does a single copy into buf
        h = m(buf).digest()[:com_size]
        coms[i, :] = np.frombuffer(h, dtype=np.uint8)

    return rand_all, coms


def OpenH_compact(rand_all: np.ndarray, b_array: np.ndarray, T: np.ndarray):
    """
    Build compact openings buffer for indices in T.
    Format for each selected index i:
      - 1 byte: bit (0/1)
      - rand_size bytes: randomness
    Returns: openings_bytes (bytes) and count (len(T_valid))
    """
    b_array = np.asarray(b_array, dtype=np.uint8).flatten()
    T = np.asarray(T, dtype=np.int64)
    valid_mask = (T >= 0) & (T < len(b_array))
    T_valid = T[valid_mask]
    rand_size = rand_all.shape[1]

    # Preallocate bytearray for all openings
    openings = bytearray(len(T_valid) * (1 + rand_size))
    off = 0
    for idx in T_valid:
        openings[off] = int(b_array[idx])
        off += 1
        # copy randomness row
        row = rand_all[idx]
        openings[off:off + rand_size] = memoryview(row)
        off += rand_size

    return bytes(openings), T_valid.tolist()


# --- Compact server/client coroutines (dual arrays) ---

async def server_eec_dual_compact(security_level: int,
                                 b_array_x: np.ndarray,
                                 b_array_theta: np.ndarray,
                                 reader: 'asyncio.StreamReader',
                                 writer: 'asyncio.StreamWriter'):
    """
    Memory-optimized server handling two bit-arrays (x and theta).
    Wire format (length-prefixed frames via _send_data/_receive_data):
      1) Commitments metadata + bytes for coms_x:
         payload = struct.pack(">QII", n, com_size, rand_size) + coms_x.tobytes()
      2) Commitments metadata + bytes for coms_theta (same struct)
         (or you could send both in one frame; here we send two sequential frames)
      3) Receive indices frame (compact).
      4) For openings, send two frames:
         - openings_x frame payload: struct.pack(">QII", count, com_size, rand_size) + openings_bytes_x
           where openings_bytes_x = concatenation of (bit + randomness) per opened index
         - openings_theta frame similarly
    """
    logging.info(f"[S compact] commit x (n={len(b_array_x)}) and theta (n={len(b_array_theta)})")

    # 1) Build compact commitments for x
    st_x_rand, coms_x = ComH_compact(security_level, b_array_x)
    # 2) Build compact commitments for theta
    st_theta_rand, coms_theta = ComH_compact(security_level, b_array_theta)

    # Send coms_x: header + bytes
    n_x = coms_x.shape[0]
    com_size = coms_x.shape[1]
    rand_size = st_x_rand.shape[1]
    header_x = struct.pack(">QII", n_x, com_size, rand_size)
    payload_x = header_x + coms_x.tobytes()
    await _send_data(writer, payload_x)

    # Send coms_theta
    n_th = coms_theta.shape[0]
    com_size_th = coms_theta.shape[1]
    rand_size_th = st_theta_rand.shape[1]
    header_th = struct.pack(">QII", n_th, com_size_th, rand_size_th)
    payload_th = header_th + coms_theta.tobytes()
    await _send_data(writer, payload_th)

    # Receive indices
    data = await _receive_data(reader)
    if len(data) < 8:
        raise ValueError("Index frame too small")

    count = struct.unpack(">Q", data[:8])[0]
    expected = 8 + count * 8

    if len(data) != expected:
        raise ValueError("Bad index frame size")

    T = struct.unpack(f">{count}Q", data[8:])

    # convert into numpy array
    T_array = np.frombuffer(
        np.array(T, dtype=np.int64),
        dtype=np.int64
    )

    # Build openings as compact binary buffers
    openings_x_bytes, T_valid_x = OpenH_compact(st_x_rand, b_array_x, T_array)
    openings_th_bytes, T_valid_th = OpenH_compact(st_theta_rand, b_array_theta, T_array)

    # Send openings_x: header contains count and rand_size; com_size not needed here but keep for consistency
    count_x = len(T_valid_x)
    logging.info(f"[S eec] count_x = {count_x}")
    header_open_x = struct.pack(">QII", count_x, com_size, rand_size)
    await _send_data(writer, header_open_x + openings_x_bytes)

    # Send openings_theta
    count_th = len(T_valid_th)
    header_open_th = struct.pack(">QII", count_th, com_size_th, rand_size_th)
    await _send_data(writer, header_open_th + openings_th_bytes)

    return T


async def client_eec_dual_compact(open_indices: list[int],
                                  reader: 'asyncio.StreamReader',
                                  writer: 'asyncio.StreamWriter'):
    """
    Client receiving compact frames and verifying openings.
    Steps (matching server):
      - Receive coms_x frame:
          read header: (n, com_size, rand_size), then read n * com_size bytes and reshape to (n, com_size)
      - Receive coms_theta frame (same)
      - Send indices to open 
      - Receive openings_x frame: header (count, com_size, rand_size) + count * (1 + rand_size) bytes
      - Verify openings against coms_x and similarly for theta
    """

    # Receive coms_x
    payload_x = await _receive_data(reader)
    # parse header
    if len(payload_x) < struct.calcsize(">QII"):
        raise ValueError("Bad coms_x frame")
    header_n, com_size, rand_size = struct.unpack(">QII", payload_x[:16])  # Q=8, I=4, I=4 => 16 bytes
    body_x = payload_x[16:]
    expected_len_x = header_n * com_size
    if len(body_x) != expected_len_x:
        raise ValueError(f"Expected {expected_len_x} bytes for coms_x, got {len(body_x)}")
    coms_x = np.frombuffer(body_x, dtype=np.uint8).reshape((header_n, com_size))

    # Receive coms_theta
    payload_th = await _receive_data(reader)
    header_n_th, com_size_th, rand_size_th = struct.unpack(">QII", payload_th[:16])
    body_th = payload_th[16:]
    if len(body_th) != header_n_th * com_size_th:
        raise ValueError("Bad coms_theta length")
    coms_theta = np.frombuffer(body_th, dtype=np.uint8).reshape((header_n_th, com_size_th))

    # Send indices (small)
    # binary index list
    count = len(open_indices)
    buf = struct.pack(f">Q{count}Q", count, *map(int, open_indices))
    await _send_data(writer, buf)


    # Receive openings_x
    payload_open_x = await _receive_data(reader)
    count_x, com_size_rx, rand_size_rx = struct.unpack(">QII", payload_open_x[:16])
    body_open_x = payload_open_x[16:]
    expected_open_len_x = count_x * (1 + rand_size_rx)
    if len(body_open_x) != expected_open_len_x:
        raise ValueError("Bad openings_x length")

    # Parse openings_x into list of (idx, bit) and verify
    # Note: server used same T ordering; client still knows open_indices list ordering (open_indices)
    openings_x = []
    off = 0
    for _ in range(count_x):
        bit = body_open_x[off]
        off += 1
        rand = bytes(body_open_x[off:off + rand_size_rx])
        off += rand_size_rx
        openings_x.append((bit, rand))

    # Receive openings_theta
    payload_open_th = await _receive_data(reader)
    count_th, com_size_rth, rand_size_rth = struct.unpack(">QII", payload_open_th[:16])
    body_open_th = payload_open_th[16:]
    if len(body_open_th) != count_th * (1 + rand_size_rth):
        raise ValueError("Bad openings_theta length")

    openings_theta = []
    off = 0
    for _ in range(count_th):
        bit = body_open_th[off]
        off += 1
        rand = bytes(body_open_th[off:off + rand_size_rth])
        off += rand_size_rth
        openings_theta.append((bit, rand))

    # Verify commitments using RecH_list-style logic but adapted to compact coms
    # open_indices may contain indices that were invalid/truncated on server; we assume server returned the corresponding valid openings in same T order.
    def verify_from_compact(coms_array: np.ndarray, indices: list[int], openings: list[tuple[int, bytes]]) -> list[int] | None:
        # coms_array shape (n, com_size)
        result_bits = []
        coms_view = coms_array  # np.uint8 view
        for idx, (bit, rand) in zip(indices, openings):
            if idx >= coms_view.shape[0]:
                logging.error(f"[client compact] index {idx} out of bounds")
                return None
            # compute hash and compare
            computed = hashlib.sha256(bytes([int(bit)]) + rand).digest()[:coms_view.shape[1]]
            expected = bytes(coms_view[idx].tobytes())
            if computed != expected:
                logging.error(f"[client compact] verification failed at index {idx}")
                return None
            result_bits.append(int(bit))
        return result_bits

    res_x = verify_from_compact(coms_x, open_indices, openings_x)
    if res_x is None:
        logging.error("[C compact] x verification failed")
        return None, None
    res_th = verify_from_compact(coms_theta, open_indices, openings_theta)
    if res_th is None:
        logging.error("[C compact] theta verification failed")
        return None, None

    return res_x, res_th
