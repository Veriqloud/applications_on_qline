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

class QKDHandlerBob:
    def __init__(self, reader, writer, path_config, mode = "hwsim", num_qubits=100, qber = 0.08, csvpath=None):

        self.reader = reader
        self.writer = writer
        self.mode = mode
        self.num_qubits = num_qubits
        self.qber = qber
        self.path_config = path_config
        self.csvpath = csvpath

    async def run_protocol(self):

        logging.info(f"[QKD] mode: {self.mode}")

        logging.info("Reading Qubit Information.")
        
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
            logging.debug(f"[S] server start in {self.mode} mode")
            time0=start_time()
            tmptheta, tmpRes = reader_bob(mode=self.mode, num_qubits=self.num_qubits,  path_config=self.path_config)
            time_to_receive = delta_time(time0)


            if len(tmptheta) == 0:
                return
            
            logging.info("Processing Qubit Information.")
            time1=start_time()
            interRes = array_flaten(tmpRes)
            theta2, xlist = parse_angle(tmptheta, 'B')
            time_to_parse = delta_time(time1)
            logging.info(f"time to parse: {time_to_parse} s")
            x2 = xflip(interRes, xlist)
            # print(x2)
            del tmptheta
            del tmpRes
        
        logging.info(f"[S] len x_alice: {len(x2)}, theta_alice: {len(theta2)}") 
        
        '''
        if self.mode not in ["hwsim", "real", "test"]:
            logging.error(f"[S] Unknown mode: {self.mode}")
            return
        '''



        logging.info("Starting Basis Reconciliation.")

        # Receive remained theta1 for calculating I0, I1
        logging.info(f"Waiting for theta from Alice to continue.")

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

        logging.info(f"Theta from Alice received")
        #logging.debug(f"[S] self.num_qubits = {self.num_qubits}")
        #num_bits = self.num_batches * self.batch_size *2
        logging.debug(f"[S] N = {self.num_qubits}")
        logging.debug(f"[S] len(theta1) = {len(theta1)}")

        logging.debug(f"[S] len(theta2) = {len(theta2)}")
        logging.debug(f"[S] len(x2) = {len(x2)}")

        logging.info(f"Reconciling basis.")

        I = [i for i in range(self.num_qubits) if theta1[i] == theta2[i]]

        logging.debug(f"[S] Indices I : {I[:10]}")


        logging.info("Sending basis to Alice.")
        # send I0, I1 to B
        await assend(self.writer, I)

        key = [x2[i] for i in I]
        #logging.debug(f"[S] X: {key[:10]}, length:{len(key)}")
        logging.debug(f"[C] key after basis reconciliation: {key[:50]}, length: {len(key)}")
        del x2

        logging.info("Measuring QBER")
        response = await asrecv(self.reader)
        verification_ks_Bob = [key[i] for i in response['verify_indices']]
        length = len(verification_ks_Bob)
        error = 0
        for a, b in zip(verification_ks_Bob, response['verification_ks_Alice']):
            if a != b:
                error += 1
        measured_qber = error/length
        await assend(self.writer, measured_qber)
        # maybe send errors (int) instead of qber (float) ??
        # this loop seems unnecessary..
        # shld i send the states too for alice to verify?? 
        # (actually it's really not necessarily, Bob can always manipulate what he sends, only commitment coulddd potentially be useful)
        if measured_qber > self.qber:
            logging.info("QBER abnormal, aborting protocol")
            return None
        
        half_key = [key[i] for i in response['rest_indices']]
        if measured_qber == 0.0:
            return half_key
        
        half_key = [key[i] for i in response['rest_indices']]
        logging.info("Starting Error Correction")
        # basically copy code from QOT to do the error correction
        time1=start_time()

        # read matrix
        logging.debug("[S] load H matrix")
        Hldpc, eccblock = read_matrix(len(half_key), measured_qber)
        logging.info(f"[S] H shape : {Hldpc.shape}")
        print_csr_size(Hldpc)

        '''
        if len(X0) < eccblock or len(X1) < eccblock : # Insecure case
            
            logging.debug(f"[S] X0: {X0[:10]}, length: {len(X0)}") 
            logging.debug(f"[S] X1: {X1[:10]}, length: {len(X1)}") 
            logging.error(f"[S] Not enough bits {len(X0)}, {len(X1)} for error correction block size {eccblock}. Aborting!")
            return
        '''

        # receive Salice_x, Salice_y
        # Error correction phase
        logging.debug("[S] wait for syndrome")
        response = await asrecv(self.reader)
        Salice_key = response['syndromes']
        Toeplitz_seed = response['Toeplitz_seed']
        alice_key = await asrecv(self.reader) # only for debugging, pls remove when finalising
        
        # For info/debugging only receive Xx, Xy
        # [Xx,Xy] = await asrecv(self.reader)
        '''
        logging.debug("[S] Select syndrome")
        if self.secret_choice:
            xbob = X1
            Salice = Salice_y
        else:
            xbob = X0
            Salice = Salice_x
        '''

        logging.debug(f"[S] half_key before truncating: {half_key[:10]}, length: {len(half_key)}")

        # compute LDPC syndrome
        EC_key = np.zeros(0, dtype=np.uint8)
        half_key=half_key[:eccblock*(len(half_key)//eccblock)]
        half_key=np.array(half_key, dtype=np.uint8)
        logging.info(f"half_key of length {len(half_key)}")
        
        leak = 0 
        for i in range(0, len(half_key), eccblock):
            logging.debug(f"[S] decoding block {i}")
            half_key_block = half_key[i:i+eccblock]
            try:
                logging.debug("[S] computes syndrome")
                Sbob = Hldpc @ half_key_block %2
                logging.debug(f"[S] Syndrome bob :{Sbob[:10]}, length:{len(Sbob)} ")
                logging.debug("[S] run belief propagation")
                Salice_block=np.array(Salice_key[0], dtype=np.uint8)
                Sbob=np.array(Sbob, dtype=np.uint8)
                tmp = EC_ldpc(Salice_block, Sbob, half_key_block, Hldpc, float(measured_qber), 70)
                logging.debug("[S] BP done")
                Salice_key.pop(0)  # remove the used syndrome
                #logging.debug(f"[S] Decoded tmp :{tmp[:10]}, length:{len(tmp)} ")
                EC_key = np.concatenate([EC_key, tmp])
                logging.debug(f"[S] Decoded Xx_Xy: {EC_key[:10]},length:{len(EC_key)} ")
                leak+=Hldpc.shape[0]

            except Exception as e:
                logging.error(f"[S] End LDPC decoding: {e}")
                
        final_key, s = apply_privacy_amplification(EC_key, measured_qber, length, leak, Toeplitz_seed)
        logging.debug("[S] Error Correction ends")
        time_ecc = delta_time(time1)

        try:
            left_errors = (alice_key ^ final_key).sum()
            logging.info(f"[S] left errors after decoding : {left_errors}/{len(alice_key)}")
        except Exception as e:
            logging.warning(f"[S] left errors after decoding not available : {e}")
        logging.debug(f"[S] Xx_Xy: {final_key}, length:{len(final_key)}")

        logging.info(f"Computed key: {key[:10]}")
        return final_key


class QKDHandlerAlice:
    def __init__(self, reader, writer, path_config, mode = "hwsim", num_qubits=100, qber = 0.08, socket_reader=None, socket_writer=None, csvpath=None):

        self.reader = reader
        self.writer = writer
        self.mode = mode
        self.num_qubits = num_qubits
        self.qber = qber
        self.path_config = path_config
        self.socket_reader = socket_reader
        self.socket_writer = socket_writer
        self.csvpath = csvpath

    async def run_protocol(self):
        #num_bits = self.num_batches * self.batch_size *2
        #lambda_ot = num_bits // 2

        logging.info(f"[QKD] mode: {self.mode}")
        logging.info("Reading Qubit Information.")
        
        #logging.debug(f"[C] client starts")
        # logging.info("[C] Q-RECEIVE")
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
            logging.debug(f"[C] client starts in {self.mode} mode")
            logging.debug(f"[C] reading angles:")

            
            tmptheta = reader_alice(mode=self.mode,num_qubits=self.num_qubits, path_config=self.path_config)
            logging.info(f"num_qubits: {self.num_qubits}")
            time_to_receive=delta_time(time0)

            await send_stop_command(self.mode, self.path_config, self.socket_reader, self.socket_writer)
            if len(tmptheta) == 0:
                return
            logging.info("Processing Qubit Information.")
            theta1, x1 = parse_angle(tmptheta, 'A')
            del tmptheta
        '''  
        if self.mode not in ["hwsim", "real", "test"]:
            logging.error(f"[C] Unknown mode: {self.mode}")
            return
        '''
        logging.debug(f"[C] x1: {x1[:50]}, length: {len(x1)}")
        logging.debug(f"[C] theta1: {theta1[:50]}, length: {len(theta1)}")
        logging.info(f"[S] len x_alice: {len(x1)}, theta_alice: {len(theta1)}") 

        
        #if num_bits//2 > num_bits + 1:
        #    raise ValueError("[C] L can't be larger than the total number of unique indices (n + 1).")
        
        # send remained theta1
        # logging.info("[C] BASIS RECONCILIATION")
        logging.info("Starting Basis Reconciliation.")
        
        logging.info("Sending Alice's chosen bases to Bob")
        await assend(self.writer,theta1)
        
        del theta1
        #del data

        # receive I0,I1
        # logging.debug(f"[C] receiving I")
        logging.info("Receiving indices from Bob")
        I = await asrecv(self.reader)
        logging.debug(f"[C] Indices Ib : {I[:10]}")


        key = [x1[i] for i in I]
        logging.debug(f"[C] key after basis reconciliation: {key[:50]}, length: {len(key)}")
        logging.debug(f"[C] X: {key[:10]},length:{len(key)}")
        del x1


        logging.info("Measuring QBER")
        length = len(I)
        verify_index = list(range(0, length))  # Create a list of numbers from 0 to num_bits
        random.shuffle(verify_index)  # Shuffle the list

        mid = length // 2
        rest_index, verify_index = verify_index[:mid], verify_index[mid:]  # Split the list into two halves

        rest_index.sort()  # Sort the indices for better readability
        verify_index.sort()
        verification_ks = [key[i] for i in verify_index]
        await assend(self.writer, {'verify_indices': verify_index, 'rest_indices': rest_index, 'verification_ks_Alice': verification_ks})
        # Note to self: both Alice and Bob don't want to lie here, whether they are honest or not
        # both want their shared key to be as accurate as possible (if not will not pass later QDS checks)
        measured_qber = await asrecv(self.reader)
        print(measured_qber)

        # add step to check if qber is too high, if yes abort
        if measured_qber > self.qber:
            logging.info("QBER abnormal, aborting protocol")
            return None
        
        half_key = [key[i] for i in rest_index]
        # Hldpc, eccblock = read_matrix(len(half_key), measured_qber)
        if measured_qber == 0.0:
            return half_key
        logging.info("Starting Error Correction")
        # basically copy code from QOT to do the error correction
        time1=start_time()

        logging.debug("[C] start syndrome computation")
        # read matrix
        logging.debug("[S] load matrix")
        Hldpc, eccblock = read_matrix(len(half_key), measured_qber)
        logging.debug("[S] matrix loaded")
        print_csr_size(Hldpc)

        if len(half_key) < eccblock: # Insecure case    
            # Xx = Xx + [0]*(eccblock - len(Xx))
            logging.error(f"[C] Not enough bits for error correction block size! len(Xx):{len(half_key)},eccblock:{eccblock}.")
            return None

        
        Salice_key = []

        half_key=half_key[:eccblock*(len(half_key)//eccblock)]
        minlen = len(half_key)
        leak=0
        for i in range(0, minlen, eccblock):
            block = half_key[i:i+eccblock]
            try:
                Salice_key.append(Hldpc @ block % 2)  # length need to fit the n of matrix
                leak+=Hldpc.shape[0]

            except Exception as e:
                logging.debug(f"[C] left syndrome... {e}")


        #logging.debug(f"[C] syndrome alice Sx:{Salice_x[0][:10]} ,length:{len(Salice_x)}")
        #logging.debug(f"[C] syndrome alice Sy:{Salice_y[0][:10]} ,length:{len(Salice_y)}")

        logging.info("Computing final key and Toeplitz seed from Privacy amplification")
        print(half_key[:10], measured_qber, mid, leak)
        final_key, s = apply_privacy_amplification(half_key, measured_qber, mid, leak)

        logging.debug("[C] send syndromes to Bob")
        # send syndromes to the server
        await assend(self.writer, {'syndromes':Salice_key, 'Toeplitz_seed': s})
        await assend(self.writer, key) # only for debugging, pls remove when finalising

        
        
        time_ecc = delta_time(time1)




        logging.info(f"Computed key: {key[:10]}")
        #return half_key
        return final_key

        