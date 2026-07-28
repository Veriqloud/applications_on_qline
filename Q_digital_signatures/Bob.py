import asyncio
from async_communication import asrecv, assend
from qkd import QKDHandlerBob
import logging
from datetime import datetime
import random
import numpy as np
from utils import verify


all_connections_done = asyncio.Event()

path_config = "config_test/sim/bob/ot.json"


class QDSHandlerBob():
    def __init__(self, Charlie_host, Charlie_port):
        self.n = None
        self.bH = None
        self.key = None
        self.Charlie_host = Charlie_host
        self.Charlie_port = Charlie_port
        self.Charlie_half = []
        self.Charlie_indices = []
        self.Alice_signatures = []
        

    async def handle_QKD(self, reader, writer, request):
        QKD_Bob = QKDHandlerBob(reader, writer, path_config, mode=request["mode"], num_qubits=request["num_qubits"])
        self.n = request["n"]
        self.bH = request["bH"]
        self.key = await QKD_Bob.run_protocol()
        print("Bob_key", self.key[:10])

        writer.close()
        await writer.wait_closed()

        #so Alice and Charlie QKD shld happen first, then Alice and Bob QKD will trigger the key exchange
        

        
    
    async def handle_key_transfer(self, request):
        self.n = 5
        self.bH = 17
        reader, writer = await asyncio.open_connection(self.Charlie_host, self.Charlie_port)
        logging.info(f"[C] Connected to {self.Charlie_host}:{self.Charlie_port}")

        indices = list(range(self.n))
        random.shuffle(indices)
        Bob_half = [self.key[i * (3 * self.bH): (i+1) * (3 * self.bH)] for i in indices[:self.n//2]]

        # would any of them want to lie about n, bH and num_qubits?
        # honestly kinda, hence best if both hear of n and bH from alice directly.
        await assend(writer, {"type": "KEY_TRANSFER", "Bob_indices": indices[:self.n//2], "Bob_half": Bob_half})
        response = await asrecv(reader)

        self.Charlie_half = response["Charlie_half"]
        self.Charlie_indices = response["Charlie_indices"]
        
        writer.close()
        await writer.wait_closed()

        print("Bob_Charlie", self.Charlie_half)
    

    def handle_verification(self, request):
        self.Alice_message = request["message"]
        self.Alice_signatures = request["signatures"]
        logging.info("Processing relevant keys and signatures.")
        relevant_signatures = np.concatenate((self.Alice_signatures[:self.n], [self.Alice_signatures[i] for i in np.array(self.Charlie_indices) + self.n]))
        key = np.concatenate(([self.key[i * (3 * self.bH): (i+1) * (3 * self.bH)] for i in range(self.n)], self.Charlie_half))
        # errors = 0
        logging.info("Beginning Verification.")
        for i in range(3 * self.n // 2):
            if verify(key[i], self.bH, self.Alice_message, relevant_signatures[i]) is False:
                #errors += 1
                logging.info("Error Detected during Verification. Protocol Aborted.")
                return False

        #return errors
        logging.info("Verification completed without errors detected.")
        return True

    async def handle_forwarding(self, request):
        
        reader, writer = await asyncio.open_connection(self.Charlie_host, self.Charlie_port)
        logging.info(f"[C] Connected to {self.Charlie_host}:{self.Charlie_port}")

        await assend(writer, request)
        response = await asrecv(reader)

        writer.close()
        await writer.wait_closed()
        return response



    async def dispatcher(self, reader, writer):
        request = await asrecv(reader)

        if request["type"] == "QKD":
            logging.info("--- QKD with Alice ---")
            await self.handle_QKD(reader, writer, request)
            logging.info("--- Key Exchange with Charlie. ---")
            await self.handle_key_transfer(request) 
        
        elif request["type"] == "SIGNATURES":
            logging.info("--- Signatures received from Alice. Beginning verification. ---")
            verification = self.handle_verification(request)
            if verification == False:
                logging.info("--- Verification Failed. Transmitting response to Alice. ---")
                await assend(writer, "Verification Failed.")
                # print("failed")
                writer.close()
                await writer.wait_closed()
            else:
                logging.info("--- Verification Successful. Transmitting response to Alice. ---")
                await assend(writer, "Verification Successful, forwarding message to Charlie")
                writer.close()
                await writer.wait_closed()
                logging.info("--- Forwarding Signatures to Charlie. Awaiting Response ---")
                response = await self.handle_forwarding(request)
                logging.info(f"Response: {response}")
                print(response)
            


            



async def main():

    # TODO: edit
    Charlie_host = "localhost"
    Charlie_port = "7100"
    host = "localhost"
    port = "1700"

    logging.info(f"Charlie's ip adress: {Charlie_host}")
    logging.info(f"Charlie's port: {Charlie_port}")
    logging.info(f"Bob's ip adress: {host}")
    logging.info(f"Bob's port: {port}")

    bob = QDSHandlerBob(Charlie_host, Charlie_port)

    server = await asyncio.start_server(
        bob.dispatcher,
        host, port
    )

    async with server: 
        await all_connections_done.wait()
        server.close()
        await server.wait_closed()

if __name__ == "__main__":

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_filename = f"sim_bob_{timestamp}.log"
    # Configure logging
    logging.basicConfig(
        filename=log_filename,
        format="%(asctime)s - %(levelname)s - %(message)s",
        #level=logging.INFO, 
        level=logging.DEBUG, 
        force=True
    )
    asyncio.run(main())