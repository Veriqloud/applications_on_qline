import asyncio
import logging
from async_communication import asrecv, assend
from qkd import QKDHandlerAlice
from start_stop import send_start_command
import argparse
from utils import Toeplitz, irreducible_polynomial, sign, verify, calculate_num_qubits
import numpy as np

from datetime import datetime

num_qubits = 300 * 2
path_config = "config_test/sim/alice/ot.json"


class QDSHandlerAlice():

    def __init__(self, args):
        
        self.n = args.num_blocks
        self.bH = args.bH
        self.num_qubits, self.num_batches, self.batch_size = calculate_num_qubits(self.n, self.bH)
        self.message = [int(i) for i in "1010110110"]
        self.mode = args.mode
        self.Charlie_key = None
        self.Bob_key = None
        
    async def run_QKD(self, name, host, port):
        socket_reader, socket_writer = await send_start_command("hwsim", path_config)
        reader, writer = await asyncio.open_connection(host, port)
        logging.info(f"[C] Connected to {host}:{port}")

        #await assend(writer, {"type": "QKD", "num_qubits": self.num_qubits, "n": self.n, "bH": self.bH, "mode": self.mode})
        await assend(writer, {"type": "QKD", "num_qubits": self.num_qubits, "num_batches": self.num_batches, "batch_size": self.batch_size, "n": self.n, "bH": self.bH, "mode": self.mode})
        #print(num_qubits)
        QKD_Alice = QKDHandlerAlice(reader, writer, path_config=path_config, mode=self.mode, num_qubits=self.num_qubits, num_batches=self.num_batches, batch_size=self.batch_size, socket_reader=socket_reader, socket_writer=socket_writer)
        
        if name == "Charlie":
            self.Charlie_key = await QKD_Alice.run_protocol()
        elif name == "Bob":
            self.Bob_key = await QKD_Alice.run_protocol()

        writer.close()
        await writer.wait_closed()
        

    
    
    async def sign(self, host, port):
        # sign doc and send to Bob
        reader, writer = await asyncio.open_connection(host, port)
        logging.info(f"[C] Connected to {host}:{port}")

        
        logging.info("Processing Alice's keys")
        self.n = 5
        self.bH = 17
        Alice_key = [self.Bob_key[i * (3 * self.bH): (i+1) * (3 * self.bH)] for i in range(self.n)] + [self.Charlie_key[i * (3 * self.bH): (i+1) * (3 * self.bH)] for i in range(self.n)]
        print(len(self.Bob_key), len(self.Charlie_key), 3 * self.bH * self.n)
        print("test, test")
        print(Alice_key, self.Bob_key)
        signatures = []

        logging.info("Beginning signatures of message")
        for key in Alice_key:
            signature = sign(key, self.bH,self.message)
            #print(verify(key, self.bH,self.message, signature))
            signatures.append(signature)
        logging.info("Signatures completed")
        
        logging.info("Sending Signatures to Bob")
        await assend(writer, {"type": "SIGNATURES", "message": self.message, "signatures": signatures})
        logging.info("Signatures sent. Awaiting response")
        response = await asrecv(reader)
        writer.close()
        await writer.wait_closed()
        print(response)
        logging.info(f"Response: {response}")
        

        #writer.close()
       # await writer.wait_closed()


    async def run(self):
        # TODO: edit
        Charlie_host = "localhost"
        Charlie_port = "7100"
        Bob_host = "localhost"
        Bob_port = "1700"


        logging.info(f"Charlie's ip adress: {Charlie_host}")
        logging.info(f"Charlie's port: {Charlie_port}")
        logging.info(f"Bob's ip adress: {Bob_host}")
        logging.info(f"Bob's port: {Bob_port}")

        ### QKD with Charlie ###
        logging.info("--- QKD with Charlie ---")
        await self.run_QKD("Charlie", Charlie_host, Charlie_port)
        if self.Charlie_key is None:
            logging.info("Protocol Aborted.")
            return
        
        ### QKD with Bob ###
        logging.info("--- QKD with Bob ---")
        await self.run_QKD("Bob", Bob_host, Bob_port)
        if self.Bob_key is None:
            logging.info("Protocol Aborted.")
            return
        print("test")
        print(self.Charlie_key)
        print(self.Bob_key)

        ### Sign message and send to Bob ###
        logging.info("--- Signing message and sending to Bob ---")
        await self.sign(Bob_host, Bob_port)
    
    

    ### 






if __name__ == "__main__":

    

    parser = argparse.ArgumentParser(description="Client Protocol Runner")
    parser.add_argument("-m", "--mode", type=str, default="hwsim",
                        help="Operation mode: 'hwsim', or 'real'")
    parser.add_argument("-p", "--path_config", type=str, default="config_test/sim/alice/ot.json",
                        help="Path to FIFO config file (default: config_test/sim/alice/ot.json)")
    parser.add_argument("-n", "--num_blocks", type=int, default=38,
                        help="Number of blocks (default: 10)")
    parser.add_argument("-bH", "--bH", type=int, default=35,
                        help="bH as defined in the paper (default: 10)")
    parser.add_argument("-c", "--config_network", type=str, default="config/network.json",
                        help="Path to network config file")
    #parser.add_argument("-q", "--qber", type=float, default=0.055,
    #                    help="Quantum bit error rate (default: 0.055)")
    parser.add_argument("-l", "--loglive", action="store_true",
                        help="show log in live")
    
    args = parser.parse_args()
    '''
    alice = QDSHandlerAlice(args)
    alice.Bob_key = [0, 0, 0, 1, 0, 0, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 0, 0, 1, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 1, 1, 1, 0, 1, 0, 0, 0, 1, 1, 1, 1, 0, 1, 1, 0, 1, 1, 0, 1, 0, 1, 1, 1, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1, 0, 1, 1, 1, 1, 0, 1, 0, 1, 1, 0, 0, 0, 1, 1, 1, 1, 0, 1, 0, 1, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 1, 1, 1, 0, 1, 1, 0, 1, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 1, 0, 1, 1, 0, 0, 1, 1, 0, 1, 0, 1, 1, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 1, 1, 0, 1, 0, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 1, 1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 1, 1, 0, 1, 1, 1, 0, 1, 0, 1, 1, 0, 0, 0, 1, 0, 0, 1, 0, 1, 1, 1, 1, 1, 0, 1, 0, 0, 1, 0, 1, 0, 0, 1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 1, 0, 0, 0, 0, 1, 0, 1, 1, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 0, 0, 1, 0, 1, 1, 1, 1, 0, 1, 1, 0, 0, 0, 0, 0, 1, 0, 1, 0, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1]
    alice.Charlie_key = [0, 0, 0, 1, 0, 0, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 0, 0, 1, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 1, 1, 1, 0, 1, 0, 0, 0, 1, 1, 1, 1, 0, 1, 1, 0, 1, 1, 0, 1, 0, 1, 1, 1, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1, 0, 1, 1, 1, 1, 0, 1, 0, 1, 1, 0, 0, 0, 1, 1, 1, 1, 0, 1, 0, 1, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 1, 1, 1, 0, 1, 1, 0, 1, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 1, 0, 1, 1, 0, 0, 1, 1, 0, 1, 0, 1, 1, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 1, 1, 0, 1, 0, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 1, 1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 1, 1, 0, 1, 1, 1, 0, 1, 0, 1, 1, 0, 0, 0, 1, 0, 0, 1, 0, 1, 1, 1, 1, 1, 0, 1, 0, 0, 1, 0, 1, 0, 0, 1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 1, 0, 0, 0, 0, 1, 0, 1, 1, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 0, 0, 1, 0, 1, 1, 1, 1, 0, 1, 1, 0, 0, 0, 0, 0, 1, 0, 1, 0, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1]
    print(alice.sign())
    '''
    

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_filename = f"sim_alice_{timestamp}.log"
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
    
    