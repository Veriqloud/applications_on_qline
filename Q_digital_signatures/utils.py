import hashlib
import random
import json
from typing import Union
from ldpc import BpDecoder
from typing import List, Tuple, Union
from collections import defaultdict
import numpy as np
import os
import logging
import asyncio
import pandas as pd
from pathlib import Path
from scipy.io import mmread
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import reverse_cuthill_mckee
import time
from datetime import timedelta, datetime
import queue
from threading import Lock
import csv
import galois
from pylfsr import LFSR
import math

# security (trusted intervalle) for sampling error on the qber
# EPS_SEC1=2**(-35)
EPS_SEC1 = 2**(-23) # original
# security (trusted intervalle) for sampling error on the 2 basis-subsets
# EPS_SEC2=2**(-35)
EPS_SEC2 = 2**(-23) # original
EPS_COR=2**(-24)

BATCH_SIZE = 3000
CONFIDENCE = 0.997


def text_to_bits(text: str) -> np.ndarray:
    raw_bytes = np.frombuffer(text.encode('utf-8'), dtype=np.uint8)
    return np.unpackbits(raw_bytes)  # one uint8 (0 or 1) per bit

def calculate_batches(num_qubits):
    num_batches = num_qubits // BATCH_SIZE
    if num_qubits % BATCH_SIZE > 0:
        num_batches += 1

    return num_batches, BATCH_SIZE 


def calculate_num_qubits(n, bH, estimated_qber, confidence=CONFIDENCE):
    '''
    #return 3 * n * bH * 2 * 2 
    tmp = int(3 * (n+1) * bH * 2 * 2 * 1.05)
    if tmp % 2 == 0: # always return even number of qubits
        return tmp
    else:
        return tmp + 1
    '''
    key_length = 3 * n * bH
    length_after_BR = invert_length(key_length, estimated_qber)
    num_qubits = int(basis_reconciliation_num_qubits(length_after_BR, confidence))
    batch_size = BATCH_SIZE #
    #num_qubits = 1200000
    num_batches = (num_qubits//batch_size)//2
    if num_batches * 2 * batch_size < num_qubits:
        num_batches += 1
        num_qubits = num_batches * 2 * batch_size
    #return 6000000, 1000, 3000
    #print(num_qubits, num_batches, batch_size)
    return num_qubits, num_batches,batch_size


def basis_reconciliation_num_qubits(resulting_num_qubits, confidence):
    #chernoff bound
    failure_prob = 1 - confidence
    a = 0.25
    b = np.log(1-confidence) - resulting_num_qubits
    c = math.pow(resulting_num_qubits, 2)
    num_qubits = (- b + np.sqrt(math.pow(b, 2) - 4 * a * c))/ (2 * a)
    #x2 = (- b - np.sqrt(math.pow(b, 2) - 4 * a * c))/ (2 * a)
    return num_qubits


def estimate_leak(initial_length, measured_qber):
        # initial_length is the length after basis reconciliation
        #verification_length = initial_length//2
        remaining_key_length = initial_length//2

        #print(initial_length)
        Hldpc, eccblock = read_matrix(remaining_key_length, measured_qber)
        

        if remaining_key_length < eccblock: # Insecure case    
            return None, None

        truncated_key_length=(remaining_key_length // eccblock) * eccblock

        leak = (remaining_key_length // eccblock) * Hldpc.shape[0]
        return leak, truncated_key_length


def estimate_final_key_length(initial_length, measured_qber):
    leak, truncated_key_length = estimate_leak(initial_length, measured_qber)
    if leak == None:
         return 0
    
    verification_length = initial_length // 2
    #print(truncated_key_length, verification_length)
    l = randomness_extraction_length_qkd(truncated_key_length, verification_length, leak, q=measured_qber, eps_sec=EPS_SEC1, eps_cor=EPS_COR)
    return l


def invert_length(target_final_length, qber,
                   lo=10000, hi=3_000_000, tol=0):
    """
    Finds the smallest initial_length such that l1 (or l2) >= target_final_length,
    for a given measured_qber. Assumes the function is non-decreasing in initial_length.
    """
    def f(x):
        l = estimate_final_key_length(x, qber)
        return l

    # Make sure the target is even achievable within [lo, hi]
    #print("test1")
    f_hi = f(hi)
    if f_hi < target_final_length:
        raise ValueError(f"Target {target_final_length} not reachable even at hi={hi} "
                          f"(got {f_hi}). Increase hi.")

    #print("test2")
    f_lo = f(lo)
    if f_lo >= target_final_length:
        return lo  # already satisfied at the lower bound

    #print("test3")
    while hi - lo > tol:
        mid = (lo + hi) // 2
        if f(mid) >= target_final_length:
            hi = mid
        else:
            lo = mid + 1

    return hi


def irreducible_polynomial(bH):
    GF = galois.GF(2)

    while True:
        coeffs = [1] + [random.randint(0, 1) for _ in range(bH)]
        p = galois.Poly(coeffs, field=GF)

        if p.is_irreducible():
            ''' Old code, depends on which represenatation is needed
            exps = [bH]
            for i, c in enumerate(coeffs[1:-1], start=1):   # x^(bH-1) down to x^1
                if c == 1:
                    exps.append(bH - i)
            '''
            return np.array(coeffs, dtype=np.uint8) 

def coeffs_to_exps(coeffs, bH):
    exps = []
    for i, c in enumerate(coeffs[:-1]):
        if c == 1:
            exps.append(bH - i)
    return exps

''' Old version
def coeffs_to_exps(coeffs, bH):
    exps = [bH]
    for i, c in enumerate(coeffs[1:-1], start=1):
        if c == 1:
            exps.append(bH - i)
    return exps

_POPCOUNT_LUT = np.array([bin(i).count("1") & 1 for i in range(256)], dtype=np.uint8)

def gf2_matvec_popcount(T, vec):
    T = np.ascontiguousarray(T, dtype=np.uint8)
    vec = np.ascontiguousarray(vec, dtype=np.uint8)

    Tp = np.packbits(T, axis=1)
    vp = np.packbits(vec)

    anded = Tp & vp
    parity_per_byte = _POPCOUNT_LUT[anded]
    return np.bitwise_xor.reduce(parity_per_byte, axis=1)


def toeplitz_prealloc(coeffs, state, bH, bM):
    exps = coeffs_to_exps(coeffs, bH)
    lfsr = LFSR(exps, state)
    T = np.empty((bH, bM), dtype=np.uint8)
    for j in range(bM):
        T[:, j] = lfsr.state
        lfsr.next()
    return T
'''
''' Oldest version
def Toeplitz(coeffs, state, bH, bM):

    # coeffs = [1, c_{bH-1}, ..., c_1, c_0], degree bH, monic, c_0 must be 1
    # pylfsr fpoly wants exponents with a 1-coefficient, EXCLUDING the
    # implicit constant term (x^0), and INCLUDING the top degree bH.
    exps = [bH]
    for i, c in enumerate(coeffs[1:-1], start=1):   # x^(bH-1) down to x^1
        if c == 1:
            exps.append(bH - i) # e.g. [10, 8, 3] instead of a raw bitmask
    lfsr = LFSR(exps, state)

    columns = []

    for _ in range(bM):
        columns.append(lfsr.state)
        lfsr.next()
    T = np.column_stack(columns)

    return T
'''

def toeplitz_raw_numpy(coeffs, state, bH, bM):
    """Same output as toeplitz_prealloc, but steps the LFSR manually
    in numpy instead of calling pylfsr.next() each iteration."""
    # Build the feedback-tap mask directly from coeffs, matching
    # coeffs_to_exps' convention (bH is always a tap; middle coeffs
    # optionally are).
    exps = coeffs_to_exps(coeffs, bH)  # e.g. [10, 8, 3]

    state = np.array(state, dtype=np.uint8)
    T = np.empty((bH, bM), dtype=np.uint8)

    # tap_indices: which positions of `state` (0-indexed from the
    # "s_{n-1}" end) contribute to the feedback bit. Verify against
    # pylfsr's actual state ordering before trusting this mapping.
    tap_indices = [e - 1 for e in exps]
    #print(tap_indices)
    #print(exps)

    for j in range(bM):
        T[:, j] = state
        #print(T[:, j], "v3")
        feedback = np.bitwise_xor.reduce(state[tap_indices])
        state = np.concatenate(([feedback], state[:-1]))

    return T

def matvec_naive(T, message):
    message = np.asarray(message, dtype=np.uint8)
    return (T @ message) % 2

def sign(key, bH, message):
    
    key1 = key[:bH]
    key2 = key[bH:]
    coeffs = irreducible_polynomial(bH)
    #T = Toeplitz(coeffs, key1, bH, len(message))
    #hashed = np.concatenate((T @ message % 2, coeffs[1:]))
    hashed = np.concatenate((matvec_naive(toeplitz_raw_numpy(coeffs, key1, bH, len(message)), message), coeffs[1:]))
    #print("test1")
    #T = toeplitz_prealloc(coeffs, key1, bH, len(message))
    #print("test2")
    #hashed = np.concatenate((gf2_matvec_popcount(T, message), coeffs[1:]))
    #print("test3")
    signed = hashed ^ key2
    return signed


def verify(key, bH, message, signature):
    key1 = key[:bH]
    key2 = key[bH:]
    hashed = signature ^ key2
    coeffs = np.append(np.array([1], dtype=np.uint8), hashed[bH:])
    hashed = hashed[:bH]
    #T = Toeplitz(coeffs, key1, bH, len(message))
    #test = T @ message % 2
    test = matvec_naive(toeplitz_raw_numpy(coeffs, key1, bH, len(message)), message)
    #T = toeplitz_prealloc(coeffs, key1, bH, len(message))
    #test = gf2_matvec_popcount(T, message)
    if all(test[i] == hashed[i] for i in range(bH)):
        return True
    else:
        return False


def apply_privacy_amplification(current_key, measured_qber, length, k, leak, s=None):
    n = len(current_key)
    #print(n, k, leak, q=measured_qber, eps_sec=EPS_SEC1, eps_cor=EPS_COR)
    #l = randomness_extraction_length_qkd(length, k, leak, q=measured_qber, eps_sec=EPS_SEC1, eps_cor=EPS_COR)
    l = randomness_extraction_length_qkd(n, k, leak, q=measured_qber, eps_sec=EPS_SEC1, eps_cor=EPS_COR)
    #l = min(l, 256)
    
    if s is None:
        s = toep_coeff(n, l)
    #print(current_key, n, l, s)
    key = two_universal_hash_pa_DS(current_key, n, l, s)
    #print(key, )
    return key, s # shld change this to a version where pack bits is simply not done..

    
def two_universal_hash_pa_DS(xkey, n, l, toep): 
    """
    compute the 2-universal hash using Toepliz matrix multiplication
    :xkey: bitstring input (string of byte 0 and byte 1)
    :n: length of xkey (in bit)
    :l: final length (in bit)
    :toep: random bit of length n+m 
    """

    #toep = secrets.token_bytes(nbytes+mytes)
    logging.debug(f"[utils][hash_PA] n={n},l={l}, n+l={n+l}, toep len:{len(toep)},xkey len:{len(xkey)}")
    res = np.empty(l, dtype=np.uint8)  # preallocate instead of np.append in a loop
    for i in range(l):
        a = toep[i:n+i] & xkey
        res[i] = np.bitwise_xor.reduce(a)
    return res



def start_time():
    return time.time()

def delta_time(time1):
    time2 = time.time()
    return time2 - time1

def initcsv(name):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
    path=f"log/log_{name}_{timestamp}.csv"
    # path=f"applications_on_qline/Q_oblivious_transfer/log/log_{name}_{timestamp}.csv"
    with open(path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        header = ["timestamp","N","time_to_receive","time_commitment","qber","left_errors","time_ecc","PA","time_total","mode"]
        writer.writerow(header)
        return path


def writecsv(path, row, add_timestamp):
    with open(path, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        if add_timestamp is True:
            writer.writerow([timestamp, *row])
        else:
            writer.writerow(row)



class DroppingQueue(queue.Queue):
    def __init__(self, maxsize):
        super().__init__(maxsize)
        self._lock = Lock()

    def put(self, item, block=True, timeout=None):
        with self._lock:
            if self.full():
                # remove the oldest item
                try:
                    self.get_nowait()
                except Exception:
                    pass
            # now actually put the new item into the underlying queue
            return super().put(item, block=block, timeout=timeout)

def read_exactly(f, n):
    """Blocking read: return exactly n bytes or return fewer if EOF."""
    chunks = []
    remaining = n

    while remaining > 0:
        chunk = f.read(remaining)
        if not chunk:  # EOF or FIFO closed
            break
        chunks.append(chunk)
        remaining -= len(chunk)

    return b"".join(chunks)



def EC_ldpc(syndrome_A, syndrome_B, vector_bob, parity_check_matrix, errrate, maxiter):


    bp = BpDecoder(
        parity_check_matrix, #the parity check matrix
        error_rate=errrate, # the error rate on each bit
        max_iter=maxiter, #the maximum iteration depth for BP
        bp_method="product_sum", #BP method. The other option is `minimum_sum'
    )
    
    syndrome = syndrome_A ^ syndrome_B 
    decoding=bp.decode(syndrome)
    vector_decoded_B = vector_bob ^ decoding

    return vector_decoded_B



def read_matrix_simple(Qth):
    logging.info(f"[Matrix] Estimated QBER {Qth}")
    # initialize LDPC parity check
    if Qth > 0 and Qth < 0.045: 
        logging.info(f"[Matrix] Using LDPC code for QBER < 0.045 ")
        path = "codes_ldpc/rate_0.33/block_6144_proto_2x6_313422410401.qccsc.mtx"
        eccblock = 6144
        if not Path(path).exists():
            logging.error(f"[Matrix] file {path} not found, please refer to code_ldpc/README.md to generate the required LDPC files.")
            exit(1)
    elif Qth >= 0.045 and Qth < 0.086 :
        logging.info(f"[Matrix] Using LDPC code for QBER in [0.045, 0.086) ")
        path = "codes_ldpc/rate_0.5/block_4096_proto_2x4_12131025.qccsc.mtx"
        eccblock = 4096
        if not Path(path).exists():
            logging.warning(f"[Matrix] file {path} not found, please refer to code_ldpc/README.md to generate the required LDPC files.")
            path = "codes_ldpc/rate_0.33/block_6144_proto_2x6_313422410401.qccsc.mtx"
    else : 
        logging.error(f"[Matrix] qber {Qth} > maximum tolerable. Or handle 0 separately")
        exit(1)

    H = mmread(path).tocsr()
    return H, eccblock


def print_csr_size(A):
    size_bytes = (
        A.data.nbytes +
        A.indices.nbytes +
        A.indptr.nbytes
    )
    logging.info(f"[utils][csr] Size of H.data: {A.data.nbytes}, H.indices: {A.indices.nbytes} H.indptr: {A.indptr.nbytes}")
    logging.info(f"[utils][csr] size_bytes:{size_bytes} bytes")
    logging.info(f"[utils][csr] total {size_bytes / (1024**2)} MB")


def read_matrix(N, Qth):
    logging.debug(f"[utils][Matrix] Estimated QBER {Qth}")
    # initialize LDPC parity check
    if Qth > 0 and Qth < 0.045: 
        logging.debug(f"[utils][Matrix] Using LDPC code for QBER < 0.045 ")
        if N < 1572864 :    
            path = "codes_ldpc/rate_0.33/block_6144_proto_2x6_313422410401.qccsc.mtx"
            pathpairs_csv = "codes_ldpc/rate_adaptation/rate_adaption_2x6_block_6144.csv"
            eccblock = 6144
            if not Path(path).exists():
                logging.error(f"[Matrix] file {path} not found.")
                exit(1)
            if not Path(pathpairs_csv).exists():
                logging.error(f"[Matrix] file {pathpairs_csv} not found.")
                exit(1)
        else :
            logging.warning(f"[Matrix] Using large block size LDPC for better performance at N={N}")
            path = "codes_ldpc/rate_0.33/block_1572864_proto_2x6_313422410401.qccsc.mtx"
            pathpairs_csv = "codes_ldpc/rate_adaptation/rate_adaption_2x6_block_1572864.csv"
            eccblock = 1572864
            if not Path(path).exists():
                logging.warning(f"[Matrix] file {path} not found, please refer to code_ldpc/README.md to generate the required LDPC files.")
                path = "codes_ldpc/rate_0.33/block_6144_proto_2x6_313422410401.qccsc.mtx"
                pathpairs_csv = "codes_ldpc/rate_adaptation/rate_adaption_2x6_block_6144.csv"
                eccblock = 6144

            if not Path(pathpairs_csv).exists() or not Path(path).exists():
                logging.warning(f"[Matrix] file {pathpairs_csv} or {path} not found.")
                exit(1)


    elif Qth >= 0.045 and Qth < 0.086 :
        logging.info(f"[Matrix] Using LDPC code for QBER in [0.045, 0.086) ")
        path = "codes_ldpc/rate_0.5/block_4096_proto_2x4_12131025.qccsc.mtx"
        pathpairs_csv = "codes_ldpc/rate_adaptation/rate_adaption_2x4_block_4096.csv"
        eccblock = 4096
        if not Path(path).exists():
            logging.error(f"[Matrix] file {path} not found.")
            exit(1)
        if not Path(pathpairs_csv).exists():
            logging.error(f"[Matrix] file {pathpairs_csv} not found.")
            exit(1)
    else : 
        logging.error(f"[Matrix] qber {Qth} > maximum tolerable. Or handle 0 separately")
        exit(1)

    H = mmread(path).tocsr()
    logging.debug(f"shape before rate adaptation: {H.shape}")

    ## optimize with rate adaptation. adjust nrows_to_delete to the desired efficiency. Here we 
    ## allow up to 80% of probability of failure after decoding to get a Nqubit required bellow 20_000_000 (memory limit)

    nrows_to_delete = 0
    if eccblock == 1572864:
        if round(Qth,3) <= 0.025:
            nrows_to_delete = 152000
        else:
            nrows_to_delete = 111500

    if nrows_to_delete != 0:
        logging.info("[S] rate adapting matrix")
        pairs = pd.read_csv(pathpairs_csv,header=None,names=['i','j'],nrows=int(nrows_to_delete))
        pairs = pairs.astype(int)

        rows_to_delete = set()
        row_map = {}

        # Precompute XOR rows (still sparse)
        for i, j in pairs.itertuples(index=False):
            row_map[i] = (H[i] != H[j]).astype(int)
            rows_to_delete.add(j)

        # ---------- Build CSR triplets ----------
        data = []
        indices = []
        indptr = [0]

        for r in range(H.shape[0]):
            if r in rows_to_delete:
                continue

            if r in row_map:
                row = row_map[r]
            else:
                row = H[r]

            # Append row’s sparse structure
            data.extend(row.data)
            indices.extend(row.indices)
            indptr.append(len(data))

        # Construct final matrix WITHOUT dense conversion
        H = csr_matrix((data, indices, indptr), shape=(len(indptr)-1, H.shape[1]))
        H.data = np.array(H.data, dtype=np.uint8, copy=True)
        H.indices = np.array(H.indices, dtype=np.int32, copy=True)
        H.indptr  = np.array(H.indptr,  dtype=np.int32, copy=True)
    
    return H, eccblock


'''
Filter and verify the received commitment against expected values at specified indices.
received_commitment: A dictionary containing {“x”: [...], “theta”: [...]}. length of x and theta is N.
x and theta: Are the raw data (length 2N).
verify_index: Is the list of indices to verify (length N)
'''
def RC_filter(received_commitment, x, theta, verify_index):

    debug_idx = 10
    # filter local x and theta with verify_index
    logging.debug(f"[RC_filter] local len x={len(x)}, len  theta={len(theta)}")
    logging.debug(f"[RC_filter] local x={x[:debug_idx]}, theta={theta[:debug_idx]}")
    expected_x  = [x[i] for i in verify_index]
    theta2verify  = [theta[i] for i in verify_index]
    logging.debug(f"[RC_filter] expected_x: {expected_x[:debug_idx]}")
    logging.debug(f"[RC_filter] theta to verify: {theta2verify[:debug_idx]}")

    # verify and compute error rate 
    x_bob = received_commitment["x"]
    theta_bob = received_commitment["theta"]
    logging.debug(f"[RC_filter] len x_bob={len(x_bob)}, len theta_bob={len(theta_bob)}")
    logging.debug(f"[RC_filter] x_bob={x_bob[:debug_idx]}, len theta_bob={theta_bob[:debug_idx]}")

    total = len(verify_index)
    logging.debug(f"[RC_filter] verify_index: {verify_index[:debug_idx]}, length:{total}")
    logging.debug(f"[RC_filter] len verify_index: {total}")

    wrong_x = [expected_x[i] ^ x_bob[i] for i in range(total) if theta2verify[i] == theta_bob[i]]
    matched_len = len(wrong_x)
    wrong_x = np.array(wrong_x)
    wrong_x = np.count_nonzero(wrong_x) # to avoid overflow on sum(uint8)

    all_idx = set(range(len(x)))
    # redondant ? Already computed in main function
    remain_idx = sorted(all_idx - set(verify_index))
    remain_x = [x[i] for i in remain_idx]
    remain_theta = [theta[i] for i in remain_idx]
    logging.debug(f"[RC_filter] remain_x: {remain_x[:debug_idx]}, length:{len(remain_x)}")
    logging.debug(f"[RC_filter] remain_theta: {remain_theta[:debug_idx]}, length:{len(remain_theta)}")

    x_error = wrong_x / matched_len if matched_len > 0 else 0.0
    logging.debug(f"[RC_filter] x_error={x_error}, wrong_x={wrong_x}, matched_len={matched_len}")

    return {
        "x_error": x_error,
        "remain_x": remain_x,               # after verify_index filtering
        "remain_theta": remain_theta,
    }

async def drain_fifo(path: str) -> None:
    """
    Drain (empty) a FIFO by reading and discarding all available data.

    Args:
        path (str): Path to the FIFO
    """
    # Open the FIFO in non-blocking mode
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    loop = asyncio.get_running_loop()

    try:
        while True:
            try:
                data = await loop.run_in_executor(None, os.read, fd, 4096)
            except BlockingIOError:
                break  # nothing left to read
            if not data:
                break  # EOF
    finally:
        os.close(fd)

def read_with_padding(filename, size: int) -> str:
    with open(filename, "r", encoding="utf-8") as f:
        data = f.read(int(size))
    
    # If file has fewer characters than requested, pad with random bytes
    if len(data) < size:
        padding_length = size - len(data)
        # generate random bytes and decode safely
        # padding = os.urandom(padding_length).decode('latin1')  
        padding="a"*padding_length
        data += padding

    return data

def xflip(mainlist, xlist):
    """
    Flip the bits in mainlist based on the corresponding bits in xlist.
    
    Parameters
    ----------
    mainlist : list[int]
        List of bits to be flipped.
    xlist : list[int]
        List of bits indicating whether to flip (1) or not (0).
        
    Returns
    -------
    list[int]
        The modified mainlist with bits flipped according to xlist.
    """
    return [bit ^ flip for bit, flip in zip(mainlist, xlist)]   


def array_flaten(two_d):
    #logging.debug(f"two_d:{two_d[:2]},len:{len(two_d)}")
    one_d = []
    for sublist in two_d:
        for item in sublist:
            one_d.append(item)
    #logging.debug(f"one_d:{one_d[:10]},len:{len(one_d)}")
    return one_d


# integrated function to parse angles from a 2D array
def parse_angle(two_d_array, party):

    # Hardcoded mappings for Alice and Bob
    Alice_mapping = {
        0: (0, 1),
        1: (1, 0),
        2: (0, 0),
        3: (1, 1)
    }

    Bob_mapping = {
        0: (0, 0),
        1: (1, 1),
        2: (0, 1),
        3: (1, 0)
    }

    # Select mapping based on parameter
    if party == 'A':
        mapping = Alice_mapping
    elif party == 'B':
        mapping = Bob_mapping
    else:
        raise ValueError("mapping_type must be 'A' or 'B'.")
    
    # Step 1: Flatten the 2D array
    one_d = [item for sublist in two_d_array for item in sublist]
    #logging.debug(f"Flattened array (first 10): {one_d[:10]}, Length: {len(one_d)}")

    # Step 2: Split each number into high and low nibbles
    nibbles = []
    for num in one_d:
        if not (0 <= num <= 255):
            raise ValueError("All elements must be in the range 0 to 255.")
        nibbles.append((num >> 4) & 0xF)  # High nibble
        nibbles.append(num & 0xF)        # Low nibble

    #logging.debug(f"Nibbles (first 10): {nibbles[:10]}, Length: {len(nibbles)}")

    # Step 3: Swap adjacent pairs
    for i in range(0, len(nibbles) - 1, 2):
        nibbles[i], nibbles[i + 1] = nibbles[i + 1], nibbles[i]
    
    #logging.debug(f"Swapped nibbles (first 10): {nibbles[:10]}")

    # Step 4: Apply mapping and split into two lists
    X_list = [] 
    H_list = [] 

    for val in nibbles:
        if val not in mapping:
            #raise ValueError(f"Value {val} not in mapping.")
            logging.warn(f"Value {val} not in mapping.")
            a,b = (0,0)
        else: 
            a, b = mapping[val]
        X_list.append(a)
        H_list.append(b)

    return H_list, X_list


def swap_pairs(lst):
    for i in range(0, len(lst) - 1, 2):
        lst[i], lst[i + 1] = lst[i + 1], lst[i]
    return lst


def xy_z_statistics(xs, ys, zs):
    if not (len(xs) == len(ys) == len(zs)):
        raise ValueError("All input lists must have the same length.")

    stats = defaultdict(lambda: [0, 0])  # maps (X,Y) -> [count of Z=0, count of Z=1]

    # Count Z values for each (X,Y)
    for x, y, z in zip(xs, ys, zs):
        stats[(x, y)][z] += 1

    # Display statistics
    #logging.debug("Statistics for each (X, Y) pair:\n")
    for (x, y), counts in sorted(stats.items()):
        total = sum(counts)
        pct_0 = (counts[0] / total) * 100
        pct_1 = (counts[1] / total) * 100
        #logging.debug(f"(X, Y) = ({x}, {y}): Z=0 → {pct_0:.1f}%, Z=1 → {pct_1:.1f}%")

# entropy function
def h(e): 
    if e == 0 or e == 1: 
        return 0
    elif e < 0 or e > 1.0:
        logging.debug(f"h(x) define over [0,1], e={e}")
        return 1
    return (-e * np.log(e) - (1 - e) * np.log(1-e)) / np.log(2)


# n should be >= 10^4 or 10^5
def randomness_extraction_length_qkd(n, k, leak, q, eps_sec, eps_cor):
    """
    computes the number of extractable secure bits, as per Tomamichel and Leverrier
    :param n: rawkey length
    :param k: length of check bits / decommitment string
    :param leak: legnth of the syndrome
    :param q: tolerable qber
    :eps_sec: security parameter
    :eps_cor: correctness parameter
    """
    q2 = q + np.sqrt((n+k)*(k+1)* np.log(2/eps_sec)/(n*k*k)) # ~sqrt(47/n)
    small = np.log(2/(eps_sec*eps_sec*eps_cor))/np.log(2) # ~100
    final_length_fs = int(n - leak - (h(q2) * n) - small)

    logging.debug(f"[utils][extraction] For n = {n}, k = {k}, q = {q}, leak = {leak},")
    logging.debug(f"[utils][extraction] finite size bound: l = {final_length_fs} bits.") #256

    return max(int(final_length_fs), 0)

# n should be >= 10^4 or 10^5
def randomness_extraction_length_ot_for_find_length_decoy(n, leak, q, eps_sec1, eps_cor, eps_sec2, p_single):
    """
    computes the number of extractable secure bits, as per DGI24-Algo5. 
    :param n: lambda_OT = length of the non open commitment = length of the open commitment
    :param leak: maximum over the two syndrome lengths
    :param q: tolerable qber
    :eps_sec1: security parameter (qber sampling error)
    :eps_cor: correctness parameter
    :eps_sec2: security paramter (basis sampling error)
    """

    # n_max is the total length of the key before randomness extraction. For OT it corresponds to the minimun length of unknow bit in x_{\bar{b}}
    xi = np.sqrt(2*(np.log(2/eps_sec2))/n)
    n_max = int(0.5*p_single*n*(0.5 - xi))
    # n_dishonnest is the max number of bits learn by dishonnest Bob during transmission
    delta = 10*np.sqrt(np.log(np.sqrt(6)/eps_sec1)/n)
    n_dishonest = int(0.5*n*h(q + delta))
    #securebits = securebitscorrectness − securebitssampling_qber − securebitssampling_I
    securebits = np.log(1/(4*(eps_sec1+eps_sec2)**2))/np.log(2) #~46
    final_length_fs = n_max - n_dishonest - leak - securebits

    logging.debug(f"[extraction] For lambda_ot = {n}, n_max: {n_max} n_dishonest: {n_dishonest} leak: {leak} securebits: {securebits}")

    #logging.debug(f"[extraction] finite size bound: l = {final_length_fs} bits.") #need to be above 256 for security feature
    if final_length_fs < 256:
        logging.warning(f"[extraction] finite size bound is below 256 bits: l = {final_length_fs} bits.")
    else:
        logging.info(f"[extraction] security bound passed!! : l = {final_length_fs} bits.")
    return max(int(final_length_fs), 0)

# n should be >= 10^4 or 10^5
def randomness_extraction_length_ot_for_find_length(n, leak, q, eps_sec1, eps_cor, eps_sec2):
    """
    computes the number of extractable secure bits, as per DGI24-Algo5. 
    :param n: lambda_OT = length of the non open commitment = length of the open commitment
    :param leak: maximum over the two syndrome lengths
    :param q: tolerable qber
    :eps_sec1: security parameter (qber sampling error)
    :eps_cor: correctness parameter
    :eps_sec2: security paramter (basis sampling error)
    """

    # n_max is the total length of the key before randomness extraction. For OT it corresponds to the minimun length of unknow bit in x_{\bar{b}}
    #xi = np.sqrt(2*(np.log(2/eps_sec2))/n) -> missing a factor of 2: i want eps_sec2 / 2 + eps_sec2 / 2
    xi = np.sqrt(2*(np.log(4/eps_sec2))/n)
    n_max = int(0.5*n*(0.5 - xi))
    # n_dishonnest is the max number of bits learn by dishonnest Bob during transmission
    #delta = 10*np.sqrt(np.log(np.sqrt(6)/eps_sec1)/n) -> missing a factor of 2: i want eps_sec1 / 2 + eps_sec1 / 2
    delta = 10*np.sqrt(np.log(2*np.sqrt(6)/eps_sec1)/n)  
    n_dishonest = int(0.5*n*h(q + delta))
    #securebits = securebitscorrectness − securebitssampling_qber − securebitssampling_I
    securebits = np.log(1/(4*(eps_sec1+eps_sec2)**2))/np.log(2) #~46
    final_length_fs = n_max - n_dishonest - leak - securebits

    logging.debug(f"[extraction] For lambda_ot = {n}, n_max: {n_max} n_dishonest: {n_dishonest} leak: {leak} securebits: {securebits}")

    #logging.debug(f"[extraction] finite size bound: l = {final_length_fs} bits.") #need to be above 256 for security feature
    if final_length_fs < 256:
        logging.warning(f"[extraction] finite size bound is below 256 bits: l = {final_length_fs} bits.")
    else:
        logging.info(f"[extraction] security bound passed!! : l = {final_length_fs} bits.")

    return max(int(final_length_fs), 0)

# n should be >= 10^4 or 10^5
def randomness_extraction_length_ot(n, leak, q, eps_sec1, eps_cor, eps_sec2):
    """
    computes the number of extractable secure bits, as per DGI24-Algo5. 
    :param n: lambda_OT = length of the non open commitment = length of the open commitment
    :param leak: maximum over the two syndrome lengths
    :param q: tolerable qber
    :eps_sec1: security parameter (qber sampling error)
    :eps_cor: correctness parameter
    :eps_sec2: security paramter (basis sampling error)
    """

    final_length_fs = randomness_extraction_length_ot_for_find_length(n, leak, q, eps_sec1, eps_cor, eps_sec2)
    
    return min(final_length_fs, 256)



def toep_coeff(n, l):
    toep = np.random.randint(0, 2, n + l - 1, dtype=np.uint8)
    return toep


# extract m bit of randmness from n bit length xkey
def two_universal_hash_pa(xkey, n, l, toep): 
    """
    compute the 2-universal hash using Toepliz matrix multiplication
    :xkey: bitstring input (string of byte 0 and byte 1)
    :n: length of xkey (in bit)
    :l: final length (in bit)
    :toep: random bit of length n+m 
    """

    #toep = secrets.token_bytes(nbytes+mytes)

    logging.debug(f"[utils][hash_PA] n={n},l={l}, n+l={n+l}, toep len:{len(toep)},xkey len:{len(xkey)}")
    res = np.array([], dtype=np.uint8)

    # remove for loop ?
    for i in range(l): 
        a = toep[i:n+i] & xkey
        a = np.bitwise_xor.reduce(a)
        res=np.append(res,a)

    # pad with 0 on the right
    resbyte = np.packbits(res)
    resbyte = np.array(resbyte, dtype= np.uint8)
    pad = 8*len(resbyte) - len(res)
    return resbyte, pad 


# add leak param when available
def prg_encrypt2(xbit: bytes, m: Union[bytes, bytearray],Qtol: float, lambda_ot, leak) -> bytes:
    """
    Compute PRG(h(s, x)) XOR m using SHA-256 and SHAKE-256.
    :param s: Seed value (bytes)
    :param x: Bitstring input (bytes)
    :param m: Message to encrypt (bytes)
    :return: Encrypted message (bytes)
    """
    # Ensure m is bytes
    if isinstance(m, str):
        m = m.encode("utf-8")   # or "latin1" depending on your use case
    #logging.debug(f"m: {m}")
    # Step 1: Hash s and x together (this is h(s, x))
    #hash_input = s + x
    # unpack x and s 
    logging.debug(f"[prg encrypt2] xbit: {xbit[:10]}")
    n = len(xbit)
    # use an approximation of leak for now
    # leak = 1.3*n*h(Qtol)
    l = randomness_extraction_length_ot(lambda_ot, leak, q=Qtol, eps_sec1=EPS_SEC1, eps_cor=EPS_COR, eps_sec2=EPS_SEC2)
    logging.info("[C] call toepliz sbytes")
    with open("cpu_usage.log", "a") as log:
        log.write("[C] calling teopliz\n")
    sbit = toep_coeff(n,l)

    logging.debug(f"[prg encrypt2] n:{n}, l:{l}, leak:{leak}, sbit len: {len(sbit)}")
    start = time.perf_counter()
    with open("cpu_usage.log", "a") as log:
        log.write("[C] start PA\n")
    logging.info("[C] start PA")
    h_sx, pad = two_universal_hash_pa(xbit,n,l,sbit) # You can swap with a 2-universal hash if needed
    end = time.perf_counter()
    logging.info(f"[C]: PA in {str(timedelta(seconds=end-start))}")
    with open("cpu_usage.log", "a") as log:
        log.write("[C] end PA\n")

    # Step 2: Use SHAKE-256 as the PRG to generate pseudorandom bytes
    prg_output = hashlib.shake_256(h_sx.tobytes()).digest(len(m))  # Match message length

    # Step 3: XOR PRG output with message
    encrypted = bytes(a ^ b for a, b in zip(prg_output, m))

    return encrypted,sbit

def prg_decrypt2(sbit: bytes, xbit: bytes, c:bytes, Qtol: float, lambda_ot, leak) -> bytes:

    # unpack x
    # xbit = np.unpackbits(x, bitorder='little')
    n = len(xbit)
    # use an approximation of leak for now
    # leak = 1.3*n*h(Qtol)
    # for this protocol, the size of the decommitment string is the same as the length of xkey = n
    l = randomness_extraction_length_ot(lambda_ot, leak, q=Qtol, eps_sec1=EPS_SEC1, eps_cor=EPS_COR, eps_sec2=EPS_SEC2)
    
    start = time.perf_counter()
    with open("cpu_usage.log", "a") as log:
        log.write("[S prg] start PA\n")
    logging.debug("[S prg] start PA")
    h_sx, pad = two_universal_hash_pa(xbit,n,l,sbit) # You can swap with a 2-universal hash if needed
    end = time.perf_counter()
    logging.info(f"[S prg]: PA in {str(timedelta(seconds=end-start))}")
    with open("cpu_usage.log", "a") as log:
        log.write("[S prg] end PA\n")

    key = hashlib.shake_256(h_sx.tobytes()).digest(len(c))
    mb = bytes(a ^ b for a, b in zip(key, c))
    return mb



def list_to_bytes(bit_list):
    # Ensure the list length is a multiple of 8
    if len(bit_list) % 8 != 0:
        padding = [0] * (8 - len(bit_list) % 8)
        bit_list += padding

    byte_array = bytearray()
    for i in range(0, len(bit_list), 8):
        byte = bit_list[i:i+8]
        byte_str = ''.join(str(b) for b in byte)
        byte_value = int(byte_str, 2)
        byte_array.append(byte_value)

    return bytes(byte_array)


def generate_random_bases(length):
    return [random.randint(0, 1) for _ in range(length)]

def apply_qubit_state(x, theta):
    if theta == 0:
        return '0' if x == 0 else '1'
    else:
        return '+' if x == 0 else '-'

def measure_qubit(qubit, theta):
    if theta == 0:
        return 0 if qubit in ['0', '+'] else 1
    else:
        return 0 if qubit in ['+', '0'] else 1


def commit(data):
    data_str = json.dumps(data)
    commitment = hashlib.sha256(data_str.encode()).hexdigest()
    return commitment, data_str

def verify_commit(commitment, data_str):
    return commitment == hashlib.sha256(data_str.encode()).hexdigest()

def check_ldpc_params(H, syndrome_A, syndrome_B, vector_bob):
    """
    Check LDPC related parameter sizes for consistency
    H: parity-check matrix (shape: m x n)
    syndrome_A, syndrome_B: syndrome vectors (length m)
    vector_bob: Bob's bit vector (length n)
    """

    # 1. Check H and get shape 
    if not isinstance(H, np.ndarray):
        raise TypeError("H must be numpy array")
    if H.ndim != 2:
        raise ValueError(f"H must be 2D matrix, but got {H.ndim}D")

    m, n = H.shape

    # 2. Check syndrome_A / syndrome_B
    if len(syndrome_A) != m:
        raise ValueError(f"syndrome_A length {len(syndrome_A)} != H rows {m}")
    if len(syndrome_B) != m:
        raise ValueError(f"syndrome_B length {len(syndrome_B)} != H rows {m}")

    # 3. Check vector_bob
    if len(vector_bob) != n:
        raise ValueError(f"vector_bob length {len(vector_bob)} != H cols {n}")

    logging.debug("Check_ldpc_params passed:")
    logging.debug(f"   H.shape = ({m}, {n})")
    logging.debug(f"   len(syndrome_A) = len(syndrome_B) = {m}")
    logging.debug(f"   len(vector_bob) = {n}")
    return True



def decode_angle(angle: Union[bytes, bytearray, List[int]]) -> Tuple[List[int], List[int]]:
    """
    Decode a stream of bytes into two parallel lists, theta and x.

    Each byte is treated as two independent 4‑bit messages (high nibble, low nibble).
    From each nibble we take its two least‑significant bits—and map them
    via the truth table:

        00 → (theta=0, x=0)
        01 → (theta=1, x=0)
        10 → (theta=1, x=1)
        11 → (theta=0, x=1)

    Parameters
    ----------
    angle : bytes | bytearray | list[int]
        Sequence of integers in the range 0‑255.

    Returns
    -------
    theta : list[int]
    x     : list[int]
        Lists have length 2 x len(angle) (one entry per nibble).
    """
    # Two‑bit → (theta, x) look‑up table
    lookup = (
        (0, 1),  # 00  +
        (0, 0),  # 01
        (1, 0),  # 10
        (1, 1),  # 11  -
    )

    theta, x = [], []

    for byte in angle:
        for shift in (4, 0):          # high nibble first, then low
            nibble      = (byte >> shift) & 0xF
            code        = nibble & 0b11   # use lowest two bits
            t, xi       = lookup[code]
            theta.append(t)
            x.append(xi)

    return theta, x

def raw_binary_input_to_bytes(raw_binary: str) -> bytes:
    """
    Converts a raw binary string (e.g., '00010000...') into a bytes object.

    Parameters
    ----------
    raw_binary : str
        A string containing only '0' and '1' characters. Length must be a multiple of 8.

    Returns
    -------
    bytes
        The resulting bytes object.
    """
    # Clean up any accidental whitespace
    raw_binary = raw_binary.replace(" ", "").replace("\n", "")

    if len(raw_binary) % 8 != 0:
        raise ValueError("Binary input length must be a multiple of 8.")

    if any(c not in '01' for c in raw_binary):
        raise ValueError("Input must contain only '0' and '1' characters.")

    return bytes(int(raw_binary[i:i+8], 2) for i in range(0, len(raw_binary), 8))


def decode_lsb_bits(data: Union[bytes, List[int]]) -> List[int]:
    """
    Extract the least significant bit (LSB) from each byte in the input.

    Parameters
    ----------
    data : bytes | list[int]
        A bytes object or list of integers (0–255).

    Returns
    -------
    List[int]
        A list of bits (0 or 1), one per byte.
    """
    return [byte & 1 for byte in data]
