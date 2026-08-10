
from handler import ProtocolHandler
import asyncio
import logging

logging.basicConfig(level=logging.DEBUG)

async def run_client(inx):
    reader, writer = await asyncio.open_connection('localhost', 7100)

    #with socket.create_connection(('localhost', 7100)) as s:
    handler = ProtocolHandler(dict={}, inx=inx, reader=reader, writer=writer, role='client' )
    #asyncio.run(handler.run_protocol())
    await handler.run_protocol()

    print(f"[C eec] result: {handler.result}")

    writer.close()
    await writer.wait_closed()

if __name__ == "__main__":
    asyncio.run(run_client([1, 2, 3]))

