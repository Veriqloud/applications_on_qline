import asyncio
from helpers.async_communication import asrecv, assend
from helpers.qkd import QKDHandlerBob
import logging
from datetime import datetime
import random
import numpy as np
from helpers.utils import verify, text_to_bits
import json
import argparse
import time
import csv


all_connections_done = asyncio.Event()

path_config = "config_test/sim/bob/qds.json"
network_config = "config/network.json"
timelog_path = "log/timelog_Bob.csv"
timelog = {}


class QDSHandlerBob():
    def __init__(self, args):
        self.bH = None
        self.key = None
        self.Charlie_key = ""
        self.Alice_signature = ""
        self.Alice_message = ""
        self.mode = args.mode
        self.network_config = args.network_config
        self.path_config = args.path_config

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

        
        server = await asyncio.start_server(
            self.dispatcher,
            self.Bob_host, self.Bob_port
        )
        logging.info("=============== [Bob] Server started. Waiting for Connections. ===============")

        
        async with server: 
            await all_connections_done.wait()
            server.close()
            await server.wait_closed()
            logging.info("[Bob] Server Closed.")
            timelog["t_total"] = time.perf_counter() - t_total
            with open(timelog_path, "a", newline='') as csvfile:
                fieldnames = ["timestamp", "id", "bM", "bH", "t_total", "t_QKD", "t_verifications_total", "t_single_verification", "mode"]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                #writer.writeheader()
                writer.writerow(timelog)
                print(timelog)
        

    async def handle_QKD(self, reader, writer, request):
        t = time.perf_counter()
        QKD_Bob = QKDHandlerBob(reader, writer, path_config = self.path_config, mode=self.mode, num_qubits=request["num_qubits"],  num_batches=request["num_batches"], batch_size=request["batch_size"])
        logging.info("[Bob][QKD] Created Bob's QKD handler object.")
        self.bH = request["bH"]
        timelog["bH"] = self.bH
        timelog["id"] = request["id"]
        timelog["mode"] = self.mode
        self.key = await QKD_Bob.run_protocol()
        logging.info(f"[Bob] Alice-Bob key: {self.key[:10]}, length: {len(self.key)}")

        
        writer.close()
        await writer.wait_closed()
        timelog["t_QKD"] = time.perf_counter() - t
    

    async def handle_verification(self, request):
        t = time.perf_counter()
        self.Alice_message = request["message"]
        self.Alice_message_bits = text_to_bits(self.Alice_message)
        self.Alice_signature = request["signature"]
        Charlie_request = {"type": "FORWARDING", "message": self.Alice_message, "signature": self.Alice_signature, "Bob_key": self.key}
        self.Charlie_key = await self.handle_forwarding(Charlie_request)
        key = self.key[:3 * self.bH] ^ self.Charlie_key[:3 * self.bH]
        

        logging.info(f"[Bob] Combined Alice-Bob key blocks and received Alice-Charlie key blocks to form {len(key)} blocks")
        
        logging.info("--------------- [Bob] Beginning Verification. ---------------")
        t_indiv = time.perf_counter()
        if verify(key, self.bH, self.Alice_message_bits, self.Alice_signature) is False:
            logging.info("[Bob] Error Detected during Verification. Protocol Aborted.")
            return False
        t_single_verification = time.perf_counter() - t_indiv

        timelog["t_single_verification"] = t_single_verification
        timelog["t_verifications_total"] = time.perf_counter() - t
        timelog["bM"] = len(self.Alice_message_bits)
        logging.info("[Bob] Verification completed without errors detected.")
        return True


    async def handle_forwarding(self, request):
        
        reader, writer = await asyncio.open_connection(self.Charlie_host, self.Charlie_port)
        logging.info(f"[Bob][TCP] Connected to {self.Charlie_host}:{self.Charlie_port}")

        logging.info("[Bob][TCP] Sending forwarding request.")
        await assend(writer, request)
        logging.info("[Bob][TCP] Waiting for response.")
        response = await asrecv(reader)

        writer.close()
        await writer.wait_closed()
        return response


    async def dispatcher(self, reader, writer):
        request = await asrecv(reader)
        logging.info("[Bob] New request received by dispatcher.")


        if request["type"] == "QKD":
            logging.info("=============== [Bob] QKD with Alice ===============")
            await self.handle_QKD(reader, writer, request)
        
        elif request["type"] == "SIGNATURES":
            logging.info("=============== [Bob] Signatures received from Alice. Beginning verification. ===============")
            verification = await self.handle_verification(request)
            if verification == False:
                logging.info("*************** [Bob] Verification Failed. Transmitting response to Alice. Signatures not forwarded to Charlie. ***************")
                await assend(writer, "Verification Failed.")
                # consider adding a forward to Charlie for Charlie to close server?
                writer.close()
                await writer.wait_closed()

                logging.info("---------- [Bob] Forwarding Result to Charlie. Awaiting Response. ----------")
                #response = await self.handle_forwarding({"type": "RESULT", "response": "Verification Failed."})
                response = await self.handle_forwarding({"type": "RESULT", "response": 0})
            else:
                logging.info("*************** [Bob] Verification Successful. Transmitting response to Alice. ***************")
                await assend(writer, "Verification Successful, forwarding message to Charlie")
                writer.close()
                await writer.wait_closed()
                logging.info("---------- [Bob] Forwarding Result to Charlie. Awaiting Response. ----------")
                response = await self.handle_forwarding({"type": "RESULT", "response": 1})

            if response == 0:
                response = "Verification Failed."
            elif response == 1:
                response = "Verification Successful."

            logging.info(f"*************** [Bob] Charlie's Response: {response} ***************")



            logging.info("[Bob] All connections completed, closing server.")
            all_connections_done.set()
    

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Bob Protocol Runner")
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

    log_filename = f"log/sim_bob_{timestamp}.log"
    # Configure logging
    logging.basicConfig(
        filename=log_filename,
        format="%(asctime)s - %(levelname)s - %(message)s",
        #level=logging.INFO, 
        level=logging.DEBUG, 
        force=True
    )
    bob = QDSHandlerBob(args)
    asyncio.run(bob.run())