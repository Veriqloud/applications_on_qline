import asyncio
import struct
import pickle
import logging

async def assend(writer, data):
    datap = pickle.dumps(data)
    length = struct.pack('>I', len(datap))
    logging.debug(f"[async_communication][TCP] Sending {len(datap)} bytes")
    writer.write(length+datap)
    await writer.drain()
    logging.debug(f"[async_communication][TCP] Data sent, writer.closed? %s", writer.is_closing())

async def asrecv(reader):
    length_bytes = await reader.readexactly(4)
    length = struct.unpack('>I', length_bytes)[0]
    logging.debug(f"[async_communication][TCP] Receiving {length} bytes")
    received = await reader.readexactly(length)
    data = pickle.loads(received)
    logging.debug(f"[async_communication][TCP] Received {length} bytes")
    return data
