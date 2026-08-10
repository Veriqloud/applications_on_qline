import asyncio
from utils import *
from readerA_sq_batched import reader_alice 
from readerB_sq_batched import reader_bob 
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

class QKDHandlerBob:
    def __init__(self, reader, writer, path_config, mode = "hwsim", num_qubits=100, num_batches=None, batch_size=None, qber = 0.08, csvpath=None):

        self.reader = reader
        self.writer = writer
        self.mode = mode
        self.num_qubits = num_qubits
        self.num_batches = num_batches
        self.batch_size = batch_size
        self.qber = qber
        self.path_config = path_config
        self.csvpath = csvpath

    async def run_protocol(self):

        logging.info(f"[QKD] Mode: {self.mode}")
        logging.info("[QKD] Running QKD protocol.")

        logging.info("--------------- [QKD] Data Reading ---------------")
        
        '''
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
        '''

        if self.mode == "hwsim" or self.mode == "real":
            logging.debug(f"[QKD] server start in {self.mode} mode")
            time0=start_time()
            #num_batches, batch_size = calculate_batches(self.num_qubits)
            logging.info(f"[QKD] Starting Reader B.")
            tmptheta, tmpRes = reader_bob(mode=self.mode, num_batches=self.num_batches, batch_size=self.batch_size,  path_config=self.path_config)
            time_to_receive = delta_time(time0)


            if len(tmptheta) == 0:
                return
            
            logging.info("[QKD] Received data from Reader B. Processing Qubit Information.")
            time1=start_time()
            interRes = array_flaten(tmpRes)
            theta2, xlist = parse_angle(tmptheta, 'B')
            time_to_parse = delta_time(time1)
            logging.info(f"time to parse: {time_to_parse} s")
            x2 = xflip(interRes, xlist)
            # print(x2)
            del tmptheta
            del tmpRes
         
        if self.mode not in ["hwsim", "real", "test"]:
            logging.error(f"[S] Unknown mode: {self.mode}")
            return
    
        logging.debug(f"[QKD] length of Bob/Charlie's bits (x2): {x2[:10]}, length: {len(x2)}")
        logging.debug(f"[QKD] length of Bob/Charlie's bases (theta2): {theta2[:10]}, B: {len(theta2)}")
        logging.info(f"[QKD] length of Bob/Charlie's bits: {len(x2)}, length of Bob/Charlie's bases: {len(theta2)}") 

        logging.info("--------------- [QKD] Basis Reconciliation ---------------")

        # Receive remained theta1 for calculating I0, I1
        logging.info(f"[QKD][TCP] Waiting for bases from Alice to continue.")
        theta1 = await asrecv(self.reader)
        logging.info(f"[QKD][TCP] Bases from Alice received.")

        '''
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
            logging.error(f"Error while waiting for theta from Alice: {e}. reader.at_eof={eof}, writer.is_closing={writer_closed}. Maybe the client aborted.")
            return
        '''
        
        #logging.debug(f"[S] self.num_qubits = {self.num_qubits}")
        #num_bits = self.num_batches * self.batch_size *2
        
        logging.debug(f"[QKD] number of qubits = {self.num_qubits}, length of Bob/Charlie's bits = {len(x2)}")
        logging.debug(f"[QKD] length of Alice's bases (theta1) = {len(theta1)}, length of Bob/Charlie's bases (theta2) = {len(theta2)}")

        logging.info(f"[QKD] Matching Alice's bases and Bob/Charlie's bases.")
        I = [i for i in range(self.num_qubits) if theta1[i] == theta2[i]]

        logging.debug(f"[QKD] Matched Indices (I) : {I[:10]}, length = {len(I)}")

        logging.info("[QKD][TCP] Sending basis to Alice.")
        # send I0, I1 to B
        await assend(self.writer, I)

        initial_key = np.array([x2[i] for i in I], dtype=np.uint8)
        length_initial_key = len(initial_key)
        logging.debug(f"[QKD] key after basis reconciliation: {initial_key[:10]}, length: {length_initial_key}")
        del x2

        logging.info("--------------- [QKD] QBER Measurement ---------------")
        logging.info("[QKD][TCP] Receiving subset of key from Alice to measure QBER.")
        response = await asrecv(self.reader)
        logging.info("[QKD] Computing QBER.")
        verification_key_Bob = [initial_key[i] for i in response['verify_indices']]
        verification_length = len(verification_key_Bob)
        error = 0
        for a, b in zip(verification_key_Bob, response['verification_key_Alice']):
            if a != b:
                error += 1
        measured_qber = error/verification_length
        logging.info(f"[QKD] Measured QBER: {measured_qber}")

        logging.info("[QKD][TCP] Sending measured QBER to Alice.")
        await assend(self.writer, measured_qber)
        # maybe send errors (int) instead of qber (float) ??
        # this loop seems unnecessary..
        # shld i send the states too for alice to verify?? 
        # (actually it's really not necessarily, Bob can always manipulate what he sends, only commitment coulddd potentially be useful)
        if measured_qber > self.qber:
            logging.info("[QKD] QBER abnormal, aborting protocol")
            return None
        
        remaining_key = [initial_key[i] for i in response['rest_indices']]
        remaining_key=np.array(remaining_key, dtype=np.uint8)
        if measured_qber == 0.0:
            return remaining_key
        
        logging.info(f"[QKD] Remaining key after QBER measurement: {remaining_key[:10]}, length: {len(remaining_key)}")


        logging.info("--------------- [QKD] Error Correction ---------------")
        # basically copy code from QOT to do the error correction
        time1=start_time()

        # read matrix
        logging.info("[QKD] load LDPC matrix")
        Hldpc, eccblock = read_matrix(len(remaining_key), measured_qber)
        logging.debug(f"[QKD] H shape : {Hldpc.shape}")
        logging.info("[QKD] Matrix loaded.")
        print_csr_size(Hldpc)

        if len(remaining_key) < eccblock: # Insecure case    
            # Xx = Xx + [0]*(eccblock - len(Xx))
            logging.error(f"[C] Not enough bits for error correction block size! len(Xx):{len(remaining_key)},eccblock:{eccblock}.")
            return None

        # receive Salice_x, Salice_y
        # Error correction phase
        logging.info("[QKD][TCP] Receiving EC syndrome and Toeplitz seed.")
        response = await asrecv(self.reader)
        Salice_key = response['syndromes']
        Toeplitz_seed = response['Toeplitz_seed']
        logging.info("[QKD][TCP] EC Syndrome and Toeplitz seed received")
        alice_key = await asrecv(self.reader) # only for debugging, remove when finalising

        # compute LDPC syndrome
        EC_key = np.zeros(0, dtype=np.uint8)
        logging.debug("[QKD] Truncating key based on size of error correction block.")
        remaining_key=remaining_key[:eccblock*(len(remaining_key)//eccblock)]
        logging.info(f"half_key of length {len(remaining_key)}")
        
        leak = 0 
        for i in range(0, len(remaining_key), eccblock):
            logging.debug(f"[S] decoding block {i}")
            block = remaining_key[i:i+eccblock]
            try:
                logging.debug("[QKD] Compute syndrome")
                Sbob = Hldpc @ block %2
                logging.debug(f"[QKD] Syndrome Bob/Charlie :{Sbob[:10]}, length:{len(Sbob)} ")
                logging.debug("[QKD] run belief propagation")
                Salice_block=np.array(Salice_key[0], dtype=np.uint8)
                Sbob=np.array(Sbob, dtype=np.uint8)
                tmp = EC_ldpc(Salice_block, Sbob, block, Hldpc, float(measured_qber), 70)
                logging.debug("[QKD] BP done")
                Salice_key.pop(0)  # remove the used syndrome
                #logging.debug(f"[S] Decoded tmp :{tmp[:10]}, length:{len(tmp)} ")
                EC_key = np.concatenate([EC_key, tmp])
                logging.debug(f"[QKD] Decoded Xx_Xy: {EC_key[:10]},length:{len(EC_key)} ")
                leak+=Hldpc.shape[0]

            except Exception as e:
                logging.error(f"[S] End LDPC decoding: {e}")

        logging.info("--------------- [QKD] Privacy Amplification ---------------")  
        final_key, s = apply_privacy_amplification(EC_key, measured_qber, length_initial_key, verification_length, leak, Toeplitz_seed)
        
        time_ecc = delta_time(time1)

        try:
            left_errors = (alice_key ^ final_key).sum()
            logging.debug(f"[S] left errors after decoding : {left_errors}/{len(alice_key)}")
        except Exception as e:
            logging.warning(f"[S] left errors after decoding not available : {e}")
        #logging.info(f"[S] Xx_Xy: {final_key}, length:{len(final_key)}")

        return final_key


class QKDHandlerAlice:
    def __init__(self, reader, writer, path_config, mode = "hwsim", num_qubits=100, num_batches=None, batch_size=None, qber = 0.08, socket_reader=None, socket_writer=None, csvpath=None):

        self.reader = reader
        self.writer = writer
        self.mode = mode
        self.num_qubits = num_qubits
        self.num_batches = num_batches
        self.batch_size = batch_size
        self.qber = qber
        self.path_config = path_config
        self.socket_reader = socket_reader
        self.socket_writer = socket_writer
        self.csvpath = csvpath

    async def run_protocol(self):

        logging.info(f"[QKD] Mode: {self.mode}")
        logging.info("[QKD] Running QKD protocol.")

        logging.info("--------------- [QKD] Data Reading ---------------")
        

        time0=start_time()
        time_to_receive = 0
        '''
        if self.mode == "test":
            logging.debug(f"[C] client starts in test mode")
            with open('alice_angles.json', 'r') as f:
                dataA = json.load(f)

            
            raw_ang = dataA['angles_A']
            logging.debug(f"[C] raw_ang: {raw_ang[:10]}")

            theta1, x1 = parse_angle(dataA['angles_A'], 'A')
        '''
        if self.mode == "hwsim" or self.mode == "real":

            logging.info(f"[QKD] Starting Reader A.")
            tmptheta = reader_alice(mode=self.mode,num_batches=self.num_batches, batch_size=self.batch_size, path_config=self.path_config)
            logging.debug(f"num_qubits: {self.num_qubits}")
            time_to_receive=delta_time(time0)

            await send_stop_command(self.mode, self.path_config, self.socket_reader, self.socket_writer)
            logging.info("[QKD][quantum channel] Sent stop command for quantum channel.")
            if len(tmptheta) == 0:
                return
            
            logging.info("[QKD] Received data from Reader A. Processing Qubit Information.")
            theta1, x1 = parse_angle(tmptheta, 'A')
            del tmptheta

        if self.mode not in ["hwsim", "real", "test"]:
            logging.error(f"[QKD] Unknown mode: {self.mode}")
            return

        logging.debug(f"[QKD] length of Alice's bits (x1): {x1[:10]}, length: {len(x1)}")
        logging.debug(f"[QKD] length of Alice's bases (theta1): {theta1[:10]}, length: {len(theta1)}")
        logging.info(f"[QKD] length of Alice's bits: {len(x1)}, length of Alice's bases: {len(theta1)}") 

        logging.info("--------------- [QKD] Basis Reconciliation ---------------")
        
        logging.info("[QKD][TCP] Sending Alice's chosen bases to Bob/Charlie")
        await assend(self.writer,theta1)
        
        del theta1
        #del data

        logging.info("[QKD][TCP] Receiving matched indices from Bob/Charlie")
        I = await asrecv(self.reader)
        logging.debug(f"[QKD] Matched Indices (I): {I[:10]}, length: {len(I)}")


        initial_key = np.array([x1[i] for i in I], dtype=np.uint8)
        logging.info(f"[QKD] Key after basis reconciliation: {initial_key[:10]}, length: {len(initial_key)}")
        del x1

        logging.info("--------------- [QKD] QBER Measurement ---------------")

        logging.info("[QKD] Selecting random subset of key to measure QBER")
        length_initial_key = len(I)
        verify_index = list(range(0, length_initial_key))  # Create a list of numbers from 0 to num_bits
        random.shuffle(verify_index)  # Shuffle the list
        mid = length_initial_key // 2
        rest_index, verify_index = verify_index[:mid], verify_index[mid:]  # Split the list into two halves

        # Sort the indices for better readability
        rest_index.sort()  
        verify_index.sort()

        verification_key = [initial_key[i] for i in verify_index]
        logging.info("[QKD][TCP] Sending random subset of key to measure QBER.")
        await assend(self.writer, {'verify_indices': verify_index, 'rest_indices': rest_index, 'verification_key_Alice': verification_key})
        # Note to self: both Alice and Bob don't want to lie here, whether they are honest or not
        # both want their shared key to be as accurate as possible (if not will not pass later QDS checks)
        logging.info("[QKD][TCP] Receiving measured QBER from Bob/Charlie.")
        measured_qber = await asrecv(self.reader)
        logging.info(f"[QKD] Measured QBER: {measured_qber}")

        # if qber is too high, if yes abort
        if measured_qber > self.qber:
            logging.info("[QKD] QBER is too high, aborting protocol.")
            return None
        
        remaining_key = [initial_key[i] for i in rest_index]
        remaining_key=np.array(remaining_key, dtype=np.uint8)
        if measured_qber == 0.0:
            return remaining_key
        
        logging.info("--------------- [QKD] Error Correction ---------------")
        time1=start_time()

        logging.debug("[QKD] Start syndrome computation.")
        Salice_key = [] # S=syndrome
        # read matrix
        logging.debug("[QKD] Load LDPC matrix.")
        Hldpc, eccblock = read_matrix(len(remaining_key), measured_qber)
        logging.debug("[QKD] Matrix loaded.")
        print_csr_size(Hldpc)

        if len(remaining_key) < eccblock: # Insecure case    
            # Xx = Xx + [0]*(eccblock - len(Xx))
            logging.error(f"[QKD] Not enough bits for error correction block size! len(Xx):{len(remaining_key)},eccblock:{eccblock}.")
            return None

        logging.debug("[QKD] Truncating key based on size of error correction block.")
        remaining_key=remaining_key[:eccblock*(len(remaining_key)//eccblock)]
        minlen = len(remaining_key)
        logging.debug(f"[QKD] Length of remaining key: {minlen}")

        logging.info("[QKD] Computing leak and syndromes.")
        leak=0
        for i in range(0, minlen, eccblock):
            block = remaining_key[i:i+eccblock]
            try:
                Salice_key.append((Hldpc @ block % 2).astype(np.uint8))  # length need to fit the n of matrix
                leak+=Hldpc.shape[0]

            except Exception as e:
                logging.debug(f"[C] left syndrome... {e}")


        #logging.debug(f"[C] syndrome alice Sx:{Salice_x[0][:10]} ,length:{len(Salice_x)}")
        #logging.debug(f"[C] syndrome alice Sy:{Salice_y[0][:10]} ,length:{len(Salice_y)}")


        logging.info("--------------- [QKD] Privacy Amplification ---------------")
        logging.info("[QKD] Computing final key and Toeplitz seed from Privacy amplification")
        # print(remaining_key[:10], measured_qber, mid, leak)
        final_key, s = apply_privacy_amplification(remaining_key, measured_qber, length_initial_key, mid, leak)

        logging.info("[QKD][TCP] send EC syndromes and Toeplitz seed to Bob/Charlie.")
        # send syndromes to the server
        await assend(self.writer, {'syndromes':Salice_key, 'Toeplitz_seed': s})
        await assend(self.writer, final_key) # only for debugging, pls remove when finalising

        
        
        time_ecc = delta_time(time1)

        return final_key

        