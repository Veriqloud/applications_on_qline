import asyncio
import logging
from helpers.async_communication import asrecv, assend
from helpers.qkd import QKDHandlerAlice
from helpers.start_stop import send_start_command
import argparse
from helpers.utils import sign, calculate_num_qubits, text_to_bits, forgery_prob, repudiation_prob
import numpy as np
from datetime import datetime
import json
from helpers.configuration import E_MAX, BH_PRIME
import random
import time
import csv

path_config = "config_test/sim/alice/qds.json"
timelog_path = "log/timelog_Alice.csv"
timelog = {}



class QDSHandlerAlice():

    def __init__(self, args):

        self.id = random.randrange(0, 1_000_000_000)
        timelog["id"] = self.id
        
        self.n = args.num_blocks
        self.bH = args.bH
        self.num_qubits, self.num_batches, self.batch_size = calculate_num_qubits(self.n, self.bH, 0.08)
        self.message = "1" * 1_0  #"hello world!"
        self.message_bits = text_to_bits(self.message)
        self.mode = args.mode
        self.Charlie_key = None
        self.Bob_key = None
        self.Charlie_eMax = args.eMax

        print(self.num_qubits, self.num_batches, self.batch_size)
        print(len(self.message_bits))

        forg_prob = forgery_prob(self.n, len(self.message_bits), self.bH, e_max=self.Charlie_eMax)
        rep_prob = repudiation_prob(self.n, len(self.message_bits), self.bH, bH_prime=args.bH_prime, e_max=self.Charlie_eMax)
        print(forg_prob, rep_prob)
        logging.info(f"[Alice] ɛ-forgery: {forg_prob}, ɛ-repudiation: {rep_prob}")

        timelog["n"] = self.n
        timelog["bM"] = len(self.message_bits)
        timelog["bH"] = self.bH
        timelog["b_prime_H"] = args.bH_prime
        timelog["e_max"] = self.Charlie_eMax
        timelog["forg_prob"] = forg_prob
        timelog["rep_prob"] = rep_prob
        timelog["mode"] = self.mode

        with open(args.config_network, 'r') as f:
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
        
        
    async def run_QKD(self, name, host, port):
        t = time.perf_counter()
        socket_reader, socket_writer = await send_start_command(self.mode, path_config)
        logging.info(f"[Alice][quantum channel] Sent start command for quantum channel.")
        
        reader, writer = await asyncio.open_connection(host, port)
        logging.info(f"[Alice][TCP] Connected to {host}:{port}")

        await assend(writer, {"type": "QKD", "num_qubits": self.num_qubits, "num_batches": self.num_batches, "batch_size": self.batch_size, "n": self.n, "bH": self.bH, "eMax": self.Charlie_eMax, "id": self.id})
        logging.info(f"[Alice][TCP] Sent QKD request to {name}'s handler. {self.num_qubits} qubits to be used.")

        QKD_Alice = QKDHandlerAlice(reader, writer, path_config=path_config, mode=self.mode, num_qubits=self.num_qubits, num_batches=self.num_batches, batch_size=self.batch_size, socket_reader=socket_reader, socket_writer=socket_writer)
        logging.info(f"[Alice][QKD] Created Alice's QKD handler object.")

        if name == "Charlie":
            self.Charlie_key = await QKD_Alice.run_protocol()
        elif name == "Bob":
            self.Bob_key = await QKD_Alice.run_protocol()

        writer.close()
        await writer.wait_closed()
        timelog[f"t_QKD_{name}"] = time.perf_counter() - t
        
        

    async def sign(self, host, port):
        # sign doc and send to Bob
        reader, writer = await asyncio.open_connection(host, port)
        logging.info(f"[Alice][TCP] Connected to {host}:{port}")

        t = time.perf_counter()
        logging.info("--------------- [Alice] Processing Alice's keys ---------------")
        #self.n = 5
        #self.bH = 17
        logging.info(f"[Alice] Combining Alice-Bob and Alice-Charlie keys to form {self.n * 2} blocks of {3 * self.bH} bits.")
        Alice_key = [self.Bob_key[i * (3 * self.bH): (i+1) * (3 * self.bH)] for i in range(self.n)] + [self.Charlie_key[i * (3 * self.bH): (i+1) * (3 * self.bH)] for i in range(self.n)]
        logging.debug(f"Number of blocks formed: {len(Alice_key)}")
        logging.debug(f"Alice-Bob key length: {len(self.Bob_key)}, Alice-Charlie key length: {len(self.Charlie_key)}, required total length: {2 * 3 * self.n * self.bH}")

        logging.info("--------------- [Alice] Beginning signatures of message ---------------")
        signatures = []
        timings = []
        for i, key in enumerate(Alice_key):
            #print(i)
            t_indiv = time.perf_counter()
            signatures.append(sign(key, self.bH,self.message_bits))
            timings.append(time.perf_counter() - t_indiv)
        timelog["t_single_signature"] = sum(timings)/len(Alice_key)
        logging.info("[Alice] Signatures completed.")

        timelog["t_signatures_total"] = time.perf_counter() - t
        
        logging.info("--------------- [Alice] Sending Signatures to Bob ---------------")
        await assend(writer, {"type": "SIGNATURES", "message": self.message, "signatures": signatures})
        logging.info("[Alice] Signatures sent. Awaiting response.")
        response = await asrecv(reader)
        
        writer.close()
        await writer.wait_closed()

        logging.info(f"*************** [Alice] Response from Bob: {response} ***************")


    async def run(self):
        t_total = time.perf_counter()

        logging.info(f"Charlie's ip adress: {self.Charlie_host}")
        logging.info(f"Charlie's port: {self.Charlie_port}")
        logging.info(f"Bob's ip adress: {self.Bob_host}")
        logging.info(f"Bob's port: {self.Bob_port}")

        ### QKD with Charlie ###
        logging.info("=============== [Alice] QKD with Charlie ===============")
        await self.run_QKD("Charlie", self.Charlie_host, self.Charlie_port)
        if self.Charlie_key is None:
            logging.info("[Alice][QKD] Alice-Charlie key not established. Protocol Aborted.")
            return
        logging.info(f"[Alice] Alice-Charlie key: {self.Charlie_key[:10]}, length: {len(self.Charlie_key)}")
        
        ### QKD with Bob ###
        logging.info("=============== [Alice] QKD with Bob ===============")
        await self.run_QKD("Bob", self.Bob_host, self.Bob_port)
        if self.Bob_key is None:
            logging.info("[Alice][QKD] Alice-Bob key not established. Protocol Aborted.")
            return
        logging.info(f"[Alice] Alice-Bob key: {self.Bob_key[:10]}, length: {len(self.Bob_key)}")

        ### Sign message and send to Bob ###
        logging.info("=============== [Alice] Message signature ===============")
        await self.sign(self.Bob_host, self.Bob_port)

        timelog["t_total"] = time.perf_counter() - t_total
        with open(timelog_path, "a", newline='') as csvfile:
            fieldnames = ["timestamp", "id", "bM", "n", "bH", "b_prime_H", "e_max", "forg_prob", "rep_prob", "t_total", "t_QKD_Bob", "t_QKD_Charlie", "t_signatures_total", "t_single_signature", "mode"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            #writer.writeheader()
            writer.writerow(timelog)
            print(timelog)

if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(description="Alice Protocol Runner")
    parser.add_argument("-m", "--mode", type=str, default="hwsim",
                        help="Operation mode: 'hwsim', or 'real'")
    parser.add_argument("-p", "--path_config", type=str, default="config_test/sim/alice/qds.json",
                        help="Path to FIFO config file (default: config_test/sim/alice/qds.json)")
    parser.add_argument("-n", "--num_blocks", type=int, default=52,
                        help="Number of blocks (default: 10)")
    parser.add_argument("-bH", "--bH", type=int, default=33,
                        help="bH as defined in the paper (default: 10)")
    parser.add_argument("-bH_p", "--bH_prime", type=int, default=21,
                            help="bH_prime as defined in the paper (default: 10)")
    parser.add_argument("-e", "--eMax", type=int, default=21,
                        help="Charlie's error tolerance")
    parser.add_argument("-c", "--config_network", type=str, default="config/network.json",
                        help="Path to network config file")
    #parser.add_argument("-q", "--qber", type=float, default=0.055,
    #                    help="Quantum bit error rate (default: 0.055)")
    parser.add_argument("-l", "--loglive", action="store_true",
                        help="show log in live")
    
    args = parser.parse_args()
    

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    timelog["timestamp"] = timestamp

    log_filename = f"log/sim_alice_{timestamp}.log"
    # Configure logging
    logging.basicConfig(
        filename=log_filename,
        format="%(asctime)s - %(levelname)s - %(message)s",
        #level=logging.INFO, 
        level=logging.DEBUG, 
        force=True
    )
    logging.getLogger('numba').setLevel(logging.WARNING)
    alice = QDSHandlerAlice(args)
    asyncio.run(alice.run())
    
    