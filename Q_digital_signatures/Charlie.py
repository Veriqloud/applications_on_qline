import asyncio
from async_communication import asrecv, assend
from qkd import QKDHandlerBob
import random
from datetime import datetime
import logging
import numpy as np
from utils import verify
import json
import argparse

all_connections_done = asyncio.Event()

path_config = "config_test/sim/bob/qds.json"
network_config = "config/network.json"
mode = "hwsim"

class QDSHandlerCharlie:
    def __init__(self, args):
        self.n = None
        self.bH = None
        self.key = None
        self.Bob_half = []
        self.Bob_indices = []
        self.eMax = 0.0
        self.mode = args.mode
        self.path_config = args.path_config
        self.network_config = args.network_config

        with open(self.network_config, 'r') as f:
            network = json.load(f)
        if self.mode == "hwsim":
            self.Charlie_host = network['ip']['bob_hwsim']
            self.Charlie_port = int(network['port']['hwsim_charlie'])
            self.Bob_host = network['ip']['bob_hwsim']
            self.Bob_port = int(network['port']['hwsim_bob'])
        elif self.mode == "real":
            self.Charlie_host = network['ip']['bob']
            self.Charlie_port = int(network['port']['qds_charlie'])
            self.Bob_host = network['ip']['bob']
            self.Bob_port = int(network['port']['qds_bob'])


    async def run(self):
        logging.info(f"Charlie's ip adress: {self.Charlie_host}")
        logging.info(f"Charlie's port: {self.Charlie_port}")
        logging.info(f"Bob's ip adress: {self.Bob_host}")
        logging.info(f"Bob's port: {self.Bob_port}")

        server = await asyncio.start_server(
            charlie.dispatcher,
            charlie.Charlie_host, charlie.Charlie_port
        )

        async with server: 
            await all_connections_done.wait()
            server.close()
            await server.wait_closed()


    def handle_verification(self, request):
        self.Alice_message = request["message"]
        self.Alice_signatures = request["signatures"]
        logging.info("--------------- [Charlie] Processing relevant keys and signatures. ---------------")
        logging.info(f"[Charlie] Sifting for signatures corresponding to the received Alice-Bob key blocks or Alice-Charlie key.")
        relevant_signatures = np.concatenate(([self.Alice_signatures[i] for i in np.array(self.Bob_indices)], self.Alice_signatures[self.n:]))
        key = np.concatenate((self.Bob_half, [self.key[i * (3 * self.bH): (i+1) * (3 * self.bH)] for i in range(self.n)]))
        logging.info(f"[Charlie] Combined received Alice-Bob key blocks and Alice-Charlie key to form {len(key)} blocks, totalling {sum([len(block) for block in key])} bits")
        
        errors = 0
        for i in range(3 * self.n // 2):
            if verify(key[i], self.bH, self.Alice_message, relevant_signatures[i]) is False:
                errors += 1
        
        logging.info(f"[Charlie] Number of errors detected during verification: {errors}")
        return errors


    async def dispatcher(self, reader, writer):
        request = await asrecv(reader)

        if request["type"] == "QKD":
            logging.info("=============== [Charlie] QKD with Alice ===============")
            QKD_Charlie = QKDHandlerBob(reader, writer, path_config=self.path_config, mode=self.mode, num_qubits=request["num_qubits"], num_batches=request["num_batches"], batch_size=request["batch_size"])
            logging.info("[Charlie][QKD] Created Charlie's QKD handler object.")
            self.n = request["n"]
            self.bH = request["bH"]
            self.key = await QKD_Charlie.run_protocol()
            logging.info(f"[Charlie] Alice-Charlie key: {self.key[:10]}, length: {len(self.key)}")

            writer.close()
            await writer.wait_closed()

        elif request["type"] == "KEY_TRANSFER":
            # await handle_key_transfer(reader, writer, request)

            logging.info("=============== [Charlie] Key Exchange with Bob ===============")

            self.Bob_half = request["Bob_half"]
            self.Bob_indices = request["Bob_indices"]
            logging.info(f"[Charlie] Number of Bob's bits received: {sum([len(block) for block in self.Bob_half])}")
            
            #self.n = request["n"]
            #self.bH = request["bH"]
            self.n = 5
            self.bH = 17

            logging.info("---------- [Charlie] Randomly selecting half of blocks to send to Bob. ----------")
            indices = list(range(self.n))
            random.shuffle(indices)
            Charlie_half = [self.key[i * (3 * self.bH): (i+1) * (3 * self.bH)] for i in indices[:self.n//2]]
            logging.info(f"n: {self.n}, bH: {self.bH}")
            logging.info(f"Number of bits which should be sent: {3 * self.n * self.bH //2}")
            logging.info(f"Number of bits to be sent: {sum([len(block) for block in Charlie_half])}")
            logging.info(f"---------- [Charlie][TCP] Sending half of Charlie's key and their positions. ----------")
            await assend(writer, {"Charlie_indices": indices[:self.n//2], "Charlie_half": Charlie_half})

            writer.close()
            await writer.wait_closed()
            
        elif request["type"] == "SIGNATURES":
            logging.info("--- Signatures received from Bob. Beginning verification. ---")
            errors = self.handle_verification(request)
            logging.info(f"[Charlie] Error tolerance: {self.eMax}")
            if errors > self.eMax:
                await assend(writer, "Verification Failed.")
                logging.info("*************** [Charlie] Verification Failed. Response sent to Bob. ***************")
                #print("failed")
            else:
                await assend(writer, "Verification Successful.")
                logging.info("*************** Verification Successful. Response sent to Bob. ***************")

            writer.close()
            await writer.wait_closed()

            logging.info("[Charlie] All connections completed, closing server.")
            all_connections_done.set()


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Charlie Protocol Runner")
    parser.add_argument("-m", "--mode", type=str, default="hwsim",
                        help="Operation mode: 'hwsim', or 'real'")
    parser.add_argument("-p", "--path_config", type=str, default="config_test/sim/bob/qds.json",
                        help="Path to FIFO config file (default: config_test/sim/bob/qds.json)")
    parser.add_argument("-c", "--network_config", type=str, default="config/network.json",
                        help="Path to network config file")
    #parser.add_argument("-q", "--qber", type=float, default=0.055,
    #                    help="Quantum bit error rate (default: 0.055)")
    parser.add_argument("-l", "--loglive", action="store_true",
                        help="show log in live")
    
    args = parser.parse_args()


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
    charlie = QDSHandlerCharlie(args)
    asyncio.run(charlie.run())