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
timelog_path = "sequence_based_QDS/log/timelog_Charlie.csv"
timelog = {}


class QDSHandlerCharlie:
    def __init__(self, args):
        self.bH = None
        self.key = None
        self.Bob_key = ""
        #self.Bob_indices = []
        self.Alice_message = ""
        self.Alice_signature = ""
        self.mode = args.mode
        self.path_config = args.path_config
        self.network_config = args.network_config
        self.result = None

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
                fieldnames = ["timestamp", "id", "bM", "bH", "t_total", "t_QKD", "t_key_transfer", "t_verifications_total", "t_single_verification", "mode"]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                #writer.writeheader()
                writer.writerow(timelog)
                print(timelog)


    async def handle_QKD(self, reader, writer, request):
        t = time.perf_counter()
        QKD_Charlie = QKDHandlerBob(reader, writer, path_config=self.path_config, mode=self.mode, num_qubits=request["num_qubits"], num_batches=request["num_batches"], batch_size=request["batch_size"])
        logging.info("[Charlie][QKD] Created Charlie's QKD handler object.")
        self.bH = request["bH"]
        timelog["bH"] = self.bH
        timelog["id"] = request["id"]
        timelog["mode"] = self.mode
        self.key = await QKD_Charlie.run_protocol()
        logging.info(f"[Charlie] Alice-Charlie key: {self.key[:10]}, length: {len(self.key)}")

        writer.close()
        await writer.wait_closed()
        timelog["t_QKD"] = time.perf_counter() - t

    async def handle_key_transfer(self, reader, writer, request):
        t = time.perf_counter()
        self.Bob_key = request["Bob_key"]
        self.Alice_message = request["message"]
        self.Alice_message_bits = text_to_bits(self.Alice_message)
        self.Alice_signature = request["signature"]
        await assend(writer, self.key)
        writer.close()
        await writer.wait_closed()
        timelog["t_key_transfer"] = time.perf_counter() - t


    def handle_verification(self):
        t = time.perf_counter()

        key = self.key[:3 * self.bH] ^ self.Bob_key[:3 * self.bH]

        errors = 0
        t_indiv = time.perf_counter()
        if verify(key, self.bH, self.Alice_message_bits, self.Alice_signature) is False:
            errors += 1
        t_single_verification = time.perf_counter() - t_indiv
        timelog["t_single_verification"] = t_single_verification

        timelog["t_verifications_total"] = time.perf_counter() - t
        timelog["bM"] = len(self.Alice_message_bits)
        
        logging.info(f"[Charlie] Number of errors detected during verification: {errors}")
        return errors


    async def dispatcher(self, reader, writer):
        request = await asrecv(reader)

        if request["type"] == "QKD":
            logging.info("=============== [Charlie] QKD with Alice ===============")
            await self.handle_QKD(reader, writer, request)

        elif request["type"] == "FORWARDING":

            logging.info("=============== [Charlie] Signatures received from Bob.  ===============")
            logging.info("--- Sending Charlie's key sent to Bob. ---")
            await self.handle_key_transfer(reader, writer, request)

            logging.info("--- Charlie's key sent to Bob. Beginning verification. ---")
            errors = self.handle_verification()
            if errors > 0:
                self.result = 0
                logging.info("*************** [Charlie] Verification Failed. ***************")
                #print("failed")
            else:
                self.result = 1
                logging.info("*************** [Charlie] Verification Successful. ***************")

            writer.close()
            await writer.wait_closed()

            
            
        elif request["type"] == "RESULT":
            logging.info("--- [Charlie] Result received from Bob. Sending Charlie's response. ---")
            response = request["response"]
            await assend(writer, self.result)
            if response == 1:
                logging.info("*************** [Charlie] Bob's Verification Passed. ***************")
            elif response == 0:
                logging.info("*************** [Charlie] Bob's Verification Failed. ***************")

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
    timelog["timestamp"] = timestamp

    log_filename = f"sequence_based_QDS/log/sim_charlie_{timestamp}.log"
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