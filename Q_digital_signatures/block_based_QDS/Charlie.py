import asyncio
from helpers.async_communication import asrecv, assend
from helpers.qkd import QKDHandlerBob
import random
from datetime import datetime
import logging
import numpy as np
from helpers.utils import verify, text_to_bits
import json
import argparse
import time
import csv

all_connections_done = asyncio.Event()

path_config = "config_test/sim/bob/qds.json"
network_config = "config/network.json"
timelog_path = "block_based_QDS/log/timelog_Charlie.csv"
timelog = {}


class QDSHandlerCharlie:
    def __init__(self, args):
        self.n = None
        self.bH = None
        self.key = None
        self.Bob_half = []
        self.Bob_indices = []
        self.Alice_message = ""
        self.Alice_signatures = ""
        self.eMax = None
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
        t_total = time.perf_counter()

        logging.info(f"Charlie's ip adress: {self.Charlie_host}")
        logging.info(f"Charlie's port: {self.Charlie_port}")
        logging.info(f"Bob's ip adress: {self.Bob_host}")
        logging.info(f"Bob's port: {self.Bob_port}")

        timestamp

        server = await asyncio.start_server(
            charlie.dispatcher,
            charlie.Charlie_host, charlie.Charlie_port
        )

        async with server: 
            await all_connections_done.wait()
            server.close()
            await server.wait_closed()
            logging.info("[Charlie] Server Closed.")
            timelog["t_total"] = time.perf_counter() - t_total
            with open(timelog_path, "a", newline='') as csvfile:
                fieldnames = ["timestamp", "id", "bM", "n", "bH", "e_max", "t_total", "t_QKD", "t_key_transfer", "t_verifications_total", "t_single_verification", "mode"]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                #writer.writeheader()
                writer.writerow(timelog)
                print(timelog)


    async def handle_QKD(self, reader, writer, request):
        t = time.perf_counter()
        QKD_Charlie = QKDHandlerBob(reader, writer, path_config=self.path_config, mode=self.mode, num_qubits=request["num_qubits"], num_batches=request["num_batches"], batch_size=request["batch_size"])
        logging.info("[Charlie][QKD] Created Charlie's QKD handler object.")
        self.n = request["n"]
        self.bH = request["bH"]
        self.eMax = request["eMax"]
        timelog["n"] = self.n
        timelog["bH"] = self.bH
        timelog["e_max"] = self.eMax
        timelog["id"] = request["id"]
        timelog["mode"] = self.mode
        self.key = await QKD_Charlie.run_protocol()
        logging.info(f"[Charlie] Alice-Charlie key: {self.key[:10]}, length: {len(self.key)}")
        print(f"Alice-Charlie key: {self.key[:10]}, length: {len(self.key)}")

        writer.close()
        await writer.wait_closed()
        timelog["t_QKD"] = time.perf_counter() - t

    async def handle_key_transfer(self, reader, writer, request):
        t = time.perf_counter()
        self.Bob_half = request["Bob_half"]
        self.Bob_indices = request["Bob_indices"]
        logging.info(f"[Charlie] Number of Bob's bits received: {sum([len(block) for block in self.Bob_half])}")
        print(f"[Charlie] Number of Bob's bits received: {sum([len(block) for block in self.Bob_half])}")

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
        timelog["t_key_transfer"] = time.perf_counter() - t


    def handle_verification(self, request):
        t = time.perf_counter()
        self.Alice_message = request["message"]
        self.Alice_message_bits = text_to_bits(self.Alice_message)
        self.Alice_signatures = request["signatures"]
        logging.info("--------------- [Charlie] Processing relevant keys and signatures. ---------------")
        logging.info(f"[Charlie] Sifting for signatures corresponding to the received Alice-Bob key blocks or Alice-Charlie key.")
        relevant_signatures = np.concatenate(([self.Alice_signatures[i] for i in np.array(self.Bob_indices)], self.Alice_signatures[self.n:]))
        key = np.concatenate((self.Bob_half, [self.key[i * (3 * self.bH): (i+1) * (3 * self.bH)] for i in range(self.n)]))
        logging.info(f"[Charlie] Combined received Alice-Bob key blocks and Alice-Charlie key to form {len(key)} blocks, totalling {sum([len(block) for block in key])} bits")
        
        errors = 0
        timings = []
        for i in range(3 * self.n // 2):
            t_indiv = time.perf_counter()
            if verify(key[i], self.bH, self.Alice_message_bits, relevant_signatures[i]) is False:
                errors += 1
            timings.append(time.perf_counter() - t_indiv)
        timelog["t_single_verification"] = sum(timings)/(3 * self.n // 2)

        timelog["t_verifications_total"] = time.perf_counter() - t
        timelog["bM"] = len(self.Alice_message_bits)
        
        logging.info(f"[Charlie] Number of errors detected during verification: {errors}")
        print(f"Number of errors detected during verification: {errors}")
        return errors


    async def dispatcher(self, reader, writer):
        request = await asrecv(reader)

        if request["type"] == "QKD":
            logging.info("=============== [Charlie] QKD with Alice ===============")
            print("Starting QKD with Alice.")
            await self.handle_QKD(reader, writer, request)

        elif request["type"] == "KEY_TRANSFER":
            logging.info("=============== [Charlie] Key Exchange with Bob ===============")
            print("Starting Key Exchange with Bob.")
            await self.handle_key_transfer(reader, writer, request) 

            
            
        elif request["type"] == "SIGNATURES":
            logging.info("--- Signatures received from Bob. Beginning verification. ---")
            print("Signatures received from Bob. Beginning verification.")
            errors = self.handle_verification(request)
            logging.info(f"[Charlie] Error tolerance: {self.eMax}")
            print(f"Error tolerance: {self.eMax}")
            if errors > self.eMax:
                await assend(writer, "Verification Failed.")
                logging.info("*************** [Charlie] Verification Failed. Response sent to Bob. ***************")
                print("Verification Failed. Response sent to Bob.")
                #print("failed")
            else:
                await assend(writer, "Verification Successful.")
                logging.info("*************** Verification Successful. Response sent to Bob. ***************")
                print("Verification Successful. Response sent to Bob.")

            writer.close()
            await writer.wait_closed()

            logging.info("[Charlie] All connections completed, closing server.")
            print("All connections completed, closing server.")
            all_connections_done.set()

        elif request["type"] == "END":
            logging.info("[Charlie] Received command to close server, cause unknown. Closing server.")
            print("[Charlie] eceived command to close server, cause unknown. Closing server.")
            all_connections_done.set()

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Charlie Protocol Runner")
    parser.add_argument("-m", "--mode", type=str, default="hwsim",
                        help="Operation mode: 'hwsim', or 'real'")
    parser.add_argument("-p", "--path_config", type=str, default="config_test/sim/bob/qds.json",
                        help="Path to FIFO config file (default: config_test/sim/bob/qds.json)")
    parser.add_argument("-c", "--network_config", type=str, default="config/network.json",
                        help="Path to network config file")
    #parser.add_argument("-e", "--eMax", type=str, default=21,
    #                    help="Charlie's error tolerance")
    #parser.add_argument("-q", "--qber", type=float, default=0.055,
    #                    help="Quantum bit error rate (default: 0.055)")
    parser.add_argument("-l", "--loglive", action="store_true",
                        help="show log in live")
    
    args = parser.parse_args()


    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    timelog["timestamp"] = timestamp

    log_filename = f"block_based_QDS/log/sim_charlie_{timestamp}.log"
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