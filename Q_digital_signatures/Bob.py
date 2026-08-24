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
        self.n = None
        self.bH = None
        self.key = None
        #self.Charlie_host = Charlie_host
        #self.Charlie_port = Charlie_port
        self.Charlie_half = []
        self.Charlie_indices = []
        self.Alice_signatures = []
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
                fieldnames = ["timestamp", "id", "bM", "n", "bH", "t_total", "t_QKD", "t_key_transfer", "t_verifications_total", "t_single_verification", "mode"]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                #writer.writeheader()
                writer.writerow(timelog)
                print(timelog)

        

    async def handle_QKD(self, reader, writer, request):
        t = time.perf_counter()
        QKD_Bob = QKDHandlerBob(reader, writer, path_config = self.path_config, mode=self.mode, num_qubits=request["num_qubits"],  num_batches=request["num_batches"], batch_size=request["batch_size"])
        logging.info("[Bob][QKD] Created Bob's QKD handler object.")
        self.n = request["n"]
        self.bH = request["bH"]
        timelog["n"] = self.n
        timelog["bH"] = self.bH
        timelog["id"] = request["id"]
        timelog["mode"] = self.mode
        self.key = await QKD_Bob.run_protocol()
        #print("Bob_key", self.key[:10])
        logging.info(f"[Bob] Alice-Bob key: {self.key[:10]}, length: {len(self.key)}")

        
        writer.close()
        await writer.wait_closed()
        timelog["t_QKD"] = time.perf_counter() - t
        #so Alice and Charlie QKD shld happen first, then Alice and Bob QKD will trigger the key exchange
        
    
    async def handle_key_transfer(self, request):
        #self.n = 5
        #self.bH = 17
        t = time.perf_counter()
        reader, writer = await asyncio.open_connection(self.Charlie_host, self.Charlie_port)
        logging.info(f"[Bob][TCP] Connected to {self.Charlie_host}:{self.Charlie_port}")

        logging.info("---------- [Bob] Randomly selecting half of blocks to send to Charlie. ----------")
        indices = list(range(self.n))
        random.shuffle(indices)
        Bob_half = [self.key[i * (3 * self.bH): (i+1) * (3 * self.bH)] for i in indices[:self.n//2]]
        logging.info(f"n: {self.n}, bH: {self.bH}")
        logging.info(f"Number of bits which should be sent: {3 * self.n * self.bH //2}")
        logging.info(f"Number of bits to be sent: {sum([len(block) for block in Bob_half])}")

        # would any of them want to lie about n, bH and num_qubits?
        # honestly kinda, hence best if both hear of n and bH from alice directly.
        logging.info(f"---------- [Bob][TCP] Sending request for key exchange, along with half of Bob's key and their positions. ----------")
        await assend(writer, {"type": "KEY_TRANSFER", "Bob_indices": indices[:self.n//2], "Bob_half": Bob_half})
        logging.info(f"[Bob][TCP] Waiting for response.")
        response = await asrecv(reader)
        logging.info(f"[Bob][TCP] Response received.")

        self.Charlie_half = response["Charlie_half"]
        self.Charlie_indices = response["Charlie_indices"]
        logging.info(f"[Bob] Number of Charlie's bits received: {sum([len(block) for block in self.Charlie_half])}")

        writer.close()
        await writer.wait_closed()
        timelog["t_key_transfer"] = time.perf_counter() - t
    

    async def handle_verification(self, request):
        t = time.perf_counter()
        self.Alice_message = request["message"]
        self.Alice_message_bits = text_to_bits(self.Alice_message)
        self.Alice_signatures = request["signatures"]
        logging.info("--------------- [Bob] Processing relevant keys and signatures. ---------------")
        logging.info(f"[Bob] Sifting for signatures corresponding to the Alice-Bob key or received Alice-Charlie key blocks")
        relevant_signatures = np.concatenate((self.Alice_signatures[:self.n], [self.Alice_signatures[i] for i in np.array(self.Charlie_indices) + self.n]))
        
        key = np.concatenate(([self.key[i * (3 * self.bH): (i+1) * (3 * self.bH)] for i in range(self.n)], self.Charlie_half))
        logging.info(f"[Bob] Combined Alice-Bob key blocks and received Alice-Charlie key blocks to form {len(key)} blocks, totalling {sum([len(block) for block in key])} bits")
        
        logging.info("--------------- [Bob] Beginning Verification. ---------------")
        timings = []
        for i in range(3 * self.n // 2):
            t_indiv = time.perf_counter()
            if verify(key[i], self.bH, self.Alice_message_bits, relevant_signatures[i]) is False:
                logging.info("[Bob] Error Detected during Verification. Protocol Aborted.")
                return False
            timings.append(time.perf_counter() - t_indiv)

        timelog["t_single_verification"] = sum(timings)/(3 * self.n // 2)
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
            logging.info("=============== [Bob] Key Exchange with Charlie ===============")
            await self.handle_key_transfer(request) 
        
        elif request["type"] == "SIGNATURES":
            logging.info("=============== [Bob] Signatures received from Alice. Beginning verification. ===============")
            verification = await self.handle_verification(request)
            if verification == False:
                logging.info("*************** [Bob] Verification Failed. Transmitting response to Alice. Signatures not forwarded to Charlie. ***************")
                await assend(writer, "Verification Failed.")
                # consider adding a forward to Charlie for Charlie to close server?
                writer.close()
                await writer.wait_closed()
            else:
                logging.info("*************** [Bob] Verification Successful. Transmitting response to Alice. ***************")
                await assend(writer, "Verification Successful, forwarding message to Charlie")
                writer.close()
                await writer.wait_closed()
                logging.info("---------- [Bob] Forwarding Signatures to Charlie. Awaiting Response. ----------")
                response = await self.handle_forwarding(request)
                logging.info(f"*************** Response: {response} ***************")
                # print(response)



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