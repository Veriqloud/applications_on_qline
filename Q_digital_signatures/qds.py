import asyncio
from utils import *
from extractable_equivocal_commitment.eec import server_eec_dual_compact, client_eec_dual_compact
from readerA_sq import reader_alice # single thread from readerA
from readerB_sq import reader_bob # single thread from readerB
#from readerA import reader_alice
#from readerB import reader_bob
from start_stop import send_stop_command
import numpy as np
import pickle
import logging
import struct
import time 
from datetime import timedelta
from async_communication import assend, asrecv


'''
from applications_on_qline.Q_oblivious_transfer.utils import *
from applications_on_qline.Q_oblivious_transfer.extractable_equivocal_commitment.eec import server_eec_dual_compact, client_eec_dual_compact
from applications_on_qline.Q_oblivious_transfer.readerA_sq import reader_alice # single thread from readerA
from applications_on_qline.Q_oblivious_transfer.readerB_sq import reader_bob # single thread from readerB
from applications_on_qline.Q_oblivious_transfer.start_stop import send_stop_command
from applications_on_qline.Q_oblivious_transfer.async_communication import assend, asrecv
'''
# Configure logging
#logging.basicConfig(level=logging.DEBUG)



class QDSHandler:
    def __init__(self, key, hash, message, n, L):
        self.key = key
        self.hash = hash
        self.m = message
        self.n = n
        self.L = L

    def sign_message(self):
        h = self.hash(self.message)
        c = one_time_pad(self.key, ) # write these functions in utils.py
        blocks = split_string(c, self.n)

class QDSHandlerBob:
    def __init__(self):
        self.n = None
        self.bH = None
        self.key = None
        self.Charlie_half = []
        self.Charlie_indices = []

    def exchange_keys(self, n, bH, key):
        return
    def sign_message(self):
        return
    def verify(self):
        return
    





class QDSHandlerBob:
    def __init__(self, reader, writer, path_config, mode = "hwsim", num_qubits=10000, csvpath=None):

        self.reader = reader
        self.writer = writer
        self.mode = mode
        self.num_qubits = num_qubits
        #self.qber = qber
        self.path_config = path_config
        #self.socket_reader = socket_reader
        #self.socket_writer = socket_writer
        self.csvpath = csvpath

    async def run_protocol(self):
        #num_bits = self.num_batches * self.batch_size *2
        #lambda_ot = num_bits // 2

        logging.debug(f"[handler] mode: {self.mode}")

        logging.info("[S] Q-RECEIVE")
        
        if self.mode == "test":
            logging.debug(f"[S] server start in test mode")
            with open('bob_angles.json', 'r') as f:
                dataB = json.load(f)
            raw_res = dataB['results']
            raw_ang = dataB['angles_B']
            print(f"[S] raw_res: {raw_res[:10]}")
            print(f"[S] raw_ang: {raw_ang[:10]}")

            interRes = array_flaten(raw_res)
            theta2,xlist = parse_angle(raw_ang, 'B')
            x2 = xflip(interRes, xlist)
            time_to_receive = 0

        elif self.mode == "hwsim" or self.mode == "real":
            logging.debug(f"[S] server start in {self.mode} mode")
            time0=start_time()
            tmptheta, tmpRes = reader_bob(mode=self.mode, num_qubits=self.num_qubits,  path_config=self.path_config)
            time_to_receive = delta_time(time0)


            if len(tmptheta) == 0:
                return
            

            time1=start_time()
            interRes = array_flaten(tmpRes)
            theta2, xlist = parse_angle(tmptheta, 'B')
            time_to_parse = delta_time(time1)
            logging.info(f"time to parse: {time_to_parse} s")
            x2 = xflip(interRes, xlist)
            del tmptheta
            del tmpRes

        else:
            logging.error(f"[S] Unknown mode: {self.mode}")
            return



        logging.info("[S] BASIS RECONCILIATION")

        # Receive remained theta1 for calculating I0, I1
        logging.info(f"[S] waiting for theta from Alice to continue...if not aborted")

        try:
            length_bytes = await asyncio.wait_for(self.reader.readexactly(4), timeout=2000)
            length = struct.unpack('>I', length_bytes)[0]
            tmp_data = await asyncio.wait_for(self.reader.readexactly(length), timeout=2000)
            theta1 = pickle.loads(tmp_data) # theta1 = pickle.loads(tmp_data)
            #verify_index = tmp["verify_index"]
            #theta1_half = tmp["remain_theta"]
        
        except (asyncio.TimeoutError, asyncio.IncompleteReadError) as e:
            # If EOF/zero-bytes read happened, report more state
            eof = self.reader.at_eof()
            writer_closed = getattr(self.writer, "is_closing", lambda: False)()
            logging.error(f"[S] Error while waiting for theta from Bob: {e}. reader.at_eof={eof}, writer.is_closing={writer_closed}. Maybe the client aborted.")
            return


        #logging.debug(f"[S] self.num_qubits = {self.num_qubits}")
        #num_bits = self.num_batches * self.batch_size *2
        logging.debug(f"[S] N = {self.num_qubits}")
        logging.debug(f"[S] len(theta1) = {len(theta1)}")

        logging.debug(f"[S] len(theta2) = {len(theta2)}")
        logging.debug(f"[S] len(x2) = {len(x2)}")

        logging.debug(f"[S] reconcile basis")

        I = [i for i in range(self.num_qubits) if theta1[i] == theta2[i]]

        logging.debug(f"[S] Indices I : {I[:10]}")


        logging.debug("[S] send basis to Alice")
        # send I0, I1 to B
        await assend(self.writer,I)

        key = [x2[i] for i in I]
        logging.debug(f"[S] X: {key[:10]}, length:{len(key)}")
        del x2

        #logging.info("[S] ERROR CORRECTION")
        print(key)


class ProtocolHandlerAlice:
    def __init__(self, reader, writer, path_config, mode = "hwsim", num_qubits=10000, socket_reader=None, socket_writer=None, csvpath=None):

        self.reader = reader
        self.writer = writer
        self.mode = mode
        self.num_qubits = num_qubits
        #self.qber = qber
        self.path_config = path_config
        self.socket_reader = socket_reader
        self.socket_writer = socket_writer
        self.csvpath = csvpath

    async def run_protocol(self):
        #num_bits = self.num_batches * self.batch_size *2
        #lambda_ot = num_bits // 2

        logging.debug(f"[handler] mode: {self.mode}")
        
        #logging.debug(f"[C] client starts")
        logging.info("[C] Q-RECEIVE")
        time0=start_time()
        time_to_receive = 0
        if self.mode == "test":
            logging.debug(f"[C] client starts in test mode")
            with open('alice_angles.json', 'r') as f:
                dataA = json.load(f)

            
            raw_ang = dataA['angles_A']
            logging.debug(f"[C] raw_ang: {raw_ang[:10]}")

            theta1, x1 = parse_angle(dataA['angles_A'], 'A')

        elif self.mode == "hwsim" or self.mode == "real":
            logging.debug(f"[C] client starts in {self.mode} mode")
            logging.debug(f"[C] reading angles:")

            tmptheta = reader_alice(mode=self.mode,num_qubits=self.num_qubits, path_config=self.path_config)
            time_to_receive=delta_time(time0)

            await send_stop_command(self.mode, self.path_config, self.socket_reader, self.socket_writer)
            if len(tmptheta) == 0:
                return
            theta1, x1 = parse_angle(tmptheta, 'A')
            del tmptheta
            
        else:
            logging.error(f"[C] Unknown mode: {self.mode}")
            return

        logging.debug(f"[C] x1: {x1[:10]}, length: {len(x1)}")
        logging.debug(f"[C] theta1: {theta1[:10]}, length: {len(theta1)}")
        logging.info(f"[S] len x_alice: {len(x1)}, theta_alice: {len(theta1)}") 

        
        #if num_bits//2 > num_bits + 1:
        #    raise ValueError("[C] L can't be larger than the total number of unique indices (n + 1).")
        
        # send remained theta1
        logging.info("[C] BASIS RECONCILIATION")
        
        logging.debug("[C] sending remaining theta1 and verify_index to Bob")
        await assend(self.writer,theta1)
        
        del theta1
        #del data

        # receive I0,I1
        logging.debug(f"[C] receiving I")
        I = await asrecv(self.reader)
        logging.debug(f"[C] Indices Ib : {I[:10]}")

        # At this point,client should not know which I is the matched one

        key = [x1[i] for i in I]
        logging.debug(f"[C] X: {key[:10]},length:{len(key)}")
        del x1

        print(key)

        