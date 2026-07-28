import asyncio
from async_communication import asrecv, assend
from qkd import QKDHandlerBob
import random
from datetime import datetime
import logging
import numpy as np
from utils import verify

all_connections_done = asyncio.Event()

path_config = "config_test/sim/bob/ot.json"

class QDSHandlerCharlie:
    def __init__(self):
        self.n = None
        self.bH = None
        self.key = None
        self.Bob_half = []
        self.Bob_indices = []
        self.eMax = 0.0

    
    def handle_verification(self, request):
        self.Alice_message = request["message"]
        self.Alice_signatures = request["signatures"]
        relevant_signatures = np.concatenate(([self.Alice_signatures[i] for i in np.array(self.Bob_indices)], self.Alice_signatures[self.n:]))
        key = np.concatenate((self.Bob_half, [self.key[i * (3 * self.bH): (i+1) * (3 * self.bH)] for i in range(self.n)]))
        errors = 0
        for i in range(3 * self.n // 2):
            if verify(key[i], self.bH, self.Alice_message, relevant_signatures[i]) is False:
                errors += 1

        return errors


    async def dispatcher(self, reader, writer):
        request = await asrecv(reader)

        if request["type"] == "QKD":
            logging.info("--- QKD with Alice ---")
            QKD_Charlie = QKDHandlerBob(reader, writer, path_config=path_config, mode="hwsim", num_qubits=request["num_qubits"])
            self.n = request["n"]
            self.bH = request["bH"]
            self.key = await QKD_Charlie.run_protocol()
            print("Charlie_key", self.key[:10])

            writer.close()
            await writer.wait_closed()

        elif request["type"] == "KEY_TRANSFER":
            # await handle_key_transfer(reader, writer, request)

            logging.info("--- Key Exchange with Bob. ---")

            self.Bob_half = request["Bob_half"]
            self.Bob_indices = request["Bob_indices"]
            
            #self.n = request["n"]
            #self.bH = request["bH"]
            self.n = 5
            self.bH = 17

            indices = list(range(self.n))
            random.shuffle(indices)
            print(indices)
            print(self.bH)
            Charlie_half = [self.key[i * (3 * self.bH): (i+1) * (3 * self.bH)] for i in indices[:self.n//2]]
            # print("test", Charlie_half)
            await assend(writer, {"Charlie_indices": indices[:self.n//2], "Charlie_half": Charlie_half})

            writer.close()
            await writer.wait_closed()
            #print("Charlie_Bob", self.Bob_half)
            

        elif request["type"] == "SIGNATURES":
            logging.info("--- Signatures received from Bob. Beginning verification. ---")
            errors = self.handle_verification(request)
            if errors > self.eMax:
                await assend(writer, "Verification Failed.")
                logging.info("--- Verification Failed. Response sent to Bob. ---")
                #print("failed")
            else:
                await assend(writer, "Verification Successful.")
                logging.info("--- Verification Successful. Response sent to Bob. ---")

            writer.close()
            await writer.wait_closed()

 

async def main():

    # TODO: edit
    host = "localhost"
    port = "7100"
    charlie = QDSHandlerCharlie()

    server = await asyncio.start_server(
        charlie.dispatcher,
        host, port
    )

    async with server: 
        await all_connections_done.wait()
        server.close()
        await server.wait_closed()

if __name__ == "__main__":
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_filename = f"sim_charlie_{timestamp}.log"
    # Configure logging
    logging.basicConfig(
        filename=log_filename,
        format="%(asctime)s - %(levelname)s - %(message)s",
        #level=logging.INFO, 
        level=logging.DEBUG, 
        force=True
    )
    asyncio.run(main())