from handler import ProtocolHandler
import asyncio
import logging
logging.basicConfig(level=logging.DEBUG)

async def run_server_once(dict):
    done_event = asyncio.Event()

    async def handle_client(reader, writer):
        handler = ProtocolHandler(dict=dict, inx=None, reader=reader, writer=writer, role='server')
        await handler.run_protocol()
        writer.close()
        await writer.wait_closed()
        logging.debug("[S eec] Protocol done, setting done_event")
        done_event.set() 

    server = await asyncio.start_server(handle_client, 'localhost', 7100)

    async with server:
        logging.debug("[S eec] Waiting for one client...")
        await server.start_serving()
        await done_event.wait()
        logging.debug("[S eec] Done event received, closing server.")



if __name__ == "__main__":
    asyncio.run(run_server_once({"x": [1, 0, 0, 1, 1],"theta": [0, 1, 1, 0, 1]}))
