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




class ProtocolHandler:
    def __init__(self, reader, writer, role, path_config, secret_choice, m0="", m1="", mode = "hwsim", qber=0.055, k=1, num_batches=100,batch_size=16, socket_reader=None, socket_writer=None, csvpath=None):

        self.reader = reader
        self.writer = writer
        self.role = role  # 'server' or 'client'
        self.m0 = m0
        self.m1 = m1
        self.secret_choice = secret_choice
        self.k = k     # security parameter in algorithm 5 in paper, set k=1 for simplicity
        self.mode = mode
        self.num_batches = num_batches
        self.batch_size = batch_size
        self.qber = qber
        self.path_config = path_config
        self.socket_reader = socket_reader
        self.socket_writer = socket_writer
        self.csvpath = csvpath

    async def run_protocol(self):
        num_bits = self.num_batches * self.batch_size *2
        lambda_ot = num_bits // 2

        logging.debug(f"[handler] mode: {self.mode}")
        if self.role == 'server':

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
                tmptheta, tmpRes = reader_bob(mode=self.mode, num_batches=self.num_batches
                                            , batch_size=self.batch_size,  path_config=self.path_config)
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

            logging.info("[S] COMMITMENT")

            # Commit to x2 and theta2
            logging.info(f"[S] len x_bob: {len(x2)}, theta_bob: {len(theta2)}") 
            x2 = np.array(x2, dtype=np.uint8)
            theta2 = np.array(theta2, dtype=np.uint8)
            time1=start_time()
            verify_inx = await server_eec_dual_compact(64, x2, theta2, self.reader, self.writer)


            logging.info("[S] ERROR ESTIMATION")

            # received qber from Alice
            measured_qber = await asrecv(self.reader)

            logging.info(f"[S] measured qber: {measured_qber}")
            time_commit=delta_time(time1)

            logging.info("[S] BASIS RECONCILIATION")

            # Receive remained theta1 for calculating I0, I1
            logging.info(f"[S] waiting for theta from Alice to continue...if not aborted")

            try:
                length_bytes = await asyncio.wait_for(self.reader.readexactly(4), timeout=2000)
                length = struct.unpack('>I', length_bytes)[0]
                tmp_data = await asyncio.wait_for(self.reader.readexactly(length), timeout=2000)
                theta1_half = pickle.loads(tmp_data) # theta1 = pickle.loads(tmp_data)
                #verify_index = tmp["verify_index"]
                #theta1_half = tmp["remain_theta"]
            
            except (asyncio.TimeoutError, asyncio.IncompleteReadError) as e:
                # If EOF/zero-bytes read happened, report more state
                eof = self.reader.at_eof()
                writer_closed = getattr(self.writer, "is_closing", lambda: False)()
                logging.error(f"[S] Error while waiting for theta from Bob: {e}. reader.at_eof={eof}, writer.is_closing={writer_closed}. Maybe the client aborted.")
                return

            if self.secret_choice == None:
                self.secret_choice = np.random.randint(0, 2)
                logging.info(f"[S] choosen random secret_choice : {self.secret_choice}")
            else:
                logging.info(f"[S] choosen secret_choice : {self.secret_choice}")

            #logging.debug(f"[S] self.num_qubits = {self.num_qubits}")
            #num_bits = self.num_batches * self.batch_size *2
            logging.debug(f"[S] N = {num_bits}")
            logging.debug(f"[S] len(theta1_half) = {len(theta1_half)}")

            
            
            #verify_set = set(verify_inx)
            #theta2_half = [x for i, x in enumerate(theta2) if i not in verify_set]
            #x2_half = [x for i, x in enumerate(x2) if i not in verify_set]
            

            logging.info("[S] filter x and theta bob over non open commitment")
            
            all_idx = set(range(len(theta2)))
            # is that diff from theta1_half ?
            remain_idx = sorted(all_idx - set(verify_inx))
            
            theta2_half = [theta2[i] for i in remain_idx]
            x2_half = [x2[i] for i in remain_idx]
            
            # free memory 
            del remain_idx
            del all_idx 
            del verify_inx
            del x2
            del theta2

            logging.debug(f"[S] len(theta2_half) = {len(theta2_half)}")
            logging.debug(f"[S] len(x2_half) = {len(x2_half)}")

            logging.debug(f"[S] reconcile basis")

            if self.secret_choice:
                I0 = [i for i in range(num_bits//2) if theta1_half[i] != theta2_half[i]]
                I1 = [i for i in range(num_bits//2) if theta1_half[i] == theta2_half[i]]
            else:
                I0 = [i for i in range(num_bits//2) if theta1_half[i] == theta2_half[i]]
                I1 = [i for i in range(num_bits//2) if theta1_half[i] != theta2_half[i]]

            logging.debug(f"[S] Indices I0 : {I0[:10]}")
            logging.debug(f"[S] Indices I1 : {I1[:10]}")


            logging.debug("[S] send basis to Alice")
            # send I0, I1 to B
            await assend(self.writer,[I0,I1])

            X0 = [x2_half[i] for i in I0]
            X1 = [x2_half[i] for i in I1]
            logging.debug(f"[S] X0: {X0[:10]}, length:{len(X0)}")
            logging.debug(f"[S] X1: {X1[:10]}, length:{len(X1)}")


            logging.info("[S] ERROR CORRECTION")
            time1=start_time()

            # read matrix
            logging.debug("[S] load H matrix")
            Hldpc, eccblock = read_matrix(min(len(X0), len(X1)), measured_qber)
            logging.info(f"[S] H shape : {Hldpc.shape}")
            print_csr_size(Hldpc)

            if len(X0) < eccblock or len(X1) < eccblock : # Insecure case
                
                logging.debug(f"[S] X0: {X0[:10]}, length: {len(X0)}") 
                logging.debug(f"[S] X1: {X1[:10]}, length: {len(X1)}") 
                logging.error(f"[S] Not enough bits {len(X0)}, {len(X1)} for error correction block size {eccblock}. Aborting!")
                return


            # receive Salice_x, Salice_y
            # Error correction phase
            logging.debug("[S] wait for syndrome")
            [Salice_x,Salice_y] = await asrecv(self.reader)
            
            # For info/debugging only receive Xx, Xy
            [Xx,Xy] = await asrecv(self.reader)

            logging.debug("[S] Select syndrome")
            if self.secret_choice:
                xbob = X1
                Salice = Salice_y
            else:
                xbob = X0
                Salice = Salice_x


            logging.debug(f"[S] xbob before truncating: {xbob[:10]}, length: {len(xbob)}")

            # compute LDPC syndrome
            Xx_Xy = np.zeros(0, dtype=np.uint8)
            xbob=xbob[:eccblock*(len(xbob)//eccblock)]
            xbob=np.array(xbob, dtype=np.uint8)
            logging.info(f"xbob of length {len(xbob)}")
            
            leak = 0 
            for i in range(0, len(xbob), eccblock):
                logging.debug(f"[S] decoding block {i}")
                xbob_block = xbob[i:i+eccblock]
                try:
                    logging.debug("[S] computes syndrome")
                    Sbob = Hldpc @ xbob_block %2
                    logging.debug(f"[S] Syndrome bob :{Sbob[:10]}, length:{len(Sbob)} ")
                    logging.debug("[S] run belief propagation")
                    Salice_block=np.array(Salice[0], dtype=np.uint8)
                    Sbob=np.array(Sbob, dtype=np.uint8)
                    tmp = EC_ldpc(Salice_block, Sbob, xbob_block, Hldpc, float(measured_qber), 70)
                    logging.debug("[S] BP done")
                    Salice.pop(0)  # remove the used syndrome
                    #logging.debug(f"[S] Decoded tmp :{tmp[:10]}, length:{len(tmp)} ")
                    Xx_Xy = np.concatenate([Xx_Xy, tmp])
                    logging.debug(f"[S] Decoded Xx_Xy: {Xx_Xy[:10]},length:{len(Xx_Xy)} ")
                    leak+=Hldpc.shape[0]

                except Exception as e:
                    logging.error(f"[S] End LDPC decoding: {e}")
                    
            logging.debug("[S] Error Correction ends")
            time_ecc = delta_time(time1)


            # to use the new matrix, we need to send hash(Xx),hash(Xy) 

             # For info/debugging check errors after decoding with secret keys Xx, Xy
            if self.secret_choice:
                xalice = Xy
            else:
                xalice = Xx
            try:
                left_errors = (xalice ^ Xx_Xy).sum()
                logging.info(f"[S] left errors after decoding : {left_errors}/{len(xalice)}")
            except Exception as e:
                logging.warning(f"[S] left errors after decoding not available : {e}")
            logging.debug(f"[S] Xx_Xy: {Xx_Xy}, length:{len(Xx_Xy)}")


           
            logging.info("[S] DECRYPTION")

            # receive s, c
            logging.debug("[S] receiving encrypted message")
            logging.debug(f"[S] receiving  encrypted messages...")

            [s0,c0,s1,c1] = await asrecv(self.reader)

            logging.debug(f"[S] len s0:{len(s0)},c0:{len(c0)} s1:{len(s1)},c1:{len(c1)} ")

            # Decode c
            logging.debug(f"[S] Doing decryption")
            if self.secret_choice: 
                mb = prg_decrypt2(s1,Xx_Xy,c1, measured_qber, lambda_ot, leak)
            else:
                mb = prg_decrypt2(s0,Xx_Xy,c0, measured_qber, lambda_ot, leak)


            logging.info(f"[S] Final decrypted message: mb:{mb[:50]} ")
            time_total=delta_time(time0)

            writecsv(self.csvpath, [round(time_to_receive,2), self.num_batches * 2* self.batch_size, round(time_commit,2), measured_qber, round(time_ecc,2), 0, left_errors, round(time_total,2), self.mode])
            
            self.writer.close()
            await self.writer.wait_closed()

        # =======================================Client=======================================================
        else: 
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

                tmptheta = reader_alice(num_batches=self.num_batches, mode=self.mode
                                            ,batch_size=self.batch_size,path_config=self.path_config)
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

            
            if num_bits//2 > num_bits + 1:
                raise ValueError("[C] L can't be larger than the total number of unique indices (n + 1).")

            logging.info("[C] COMMITMENT")

            # Randomly select num_bits//2 indices to open
            verify_index = list(range(0, num_bits))  # Create a list of numbers from 0 to num_bits
            random.shuffle(verify_index)  # Shuffle the list

            mid = num_bits // 2
            rest_index, verify_index = verify_index[:mid], verify_index[mid:]  # Split the list into two halves

            rest_index.sort()  # Sort the indices for better readability
            verify_index.sort()  # Sort the indices for better readability
            logging.debug(f"[C] rest_index: {rest_index[:10]}, length: {len(rest_index)}")
            logging.debug(f"[C] verify_index: {verify_index[:10]}, length: {len(verify_index)}")


            # Choose the first half to verify, the rest to form the key (old way)
            #verify_index = [x for x in range(0, num_bits//2)] # Take the first num_bits//2 elements
            #rest_index = [x for x in range(num_bits//2, num_bits)]  # The rest of the elements

            # Receive commitment from Bob and check
            logging.info("[C] Waiting for commitment...")
            start = time.time()
            
            try:
                # Receive x2 and theta2 commitments in one call
                received_x_list, received_theta_list = await client_eec_dual_compact(verify_index, self.reader, self.writer)
                
                if received_x_list is None or received_theta_list is None:
                    logging.error("[C] Commitment verification failed!")
                    return
                
                received_commitment = {
                    'x': received_x_list,
                    'theta': received_theta_list
                }
            except Exception as e:
                logging.error(f"[C] Exception during client_eec_dual: {e}", exc_info=True)
                return
            
            #logging.debug(f"[C] received commitment decoded x: {received_commitment['x'][:10]}, length:{len(received_commitment['x'])}")
            #logging.debug(f"[C] received commitment decoded theta: {received_commitment['theta'][:10]}, length:{len(received_commitment['theta'])}")

            step1 = time.time()
            seconds = step1 - start
            logging.info(f"[C] receive commitment in {str(timedelta(seconds=seconds))}")
            time_commit=seconds

            logging.info("[C] ERROR ESTIMATION")
            # Verify half of commitment
            logging.debug("[C] verifying commitment...")
            if len(received_commitment['theta'])*2 != len(theta1):
                logging.error(f"[C] Commitment length mismatch! received_commitment['theta'])*2 :{len(received_commitment['theta'])*2} != len(theta1):{len(theta1)}")
                return

            res = RC_filter(received_commitment, x1, theta1, verify_index)
            x1 = res["remain_x"]
            theta1 = res["remain_theta"]
            end = time.time()
            seconds = end - step1
            logging.info(f"[C] measured qber : {res['x_error']} in {str(timedelta(seconds=seconds))}") # need to send to bob later...
            measured_qber = round(res['x_error'],4)

            await assend(self.writer, measured_qber)

            if res["x_error"] >= self.qber:
                logging.error(f"[C] Protocol received too many errors, rate: {res['x_error']} > {self.qber} Aborting!")
                return
            else:
                logging.info(f"[C] Protocol received acceptable error rate: {res['x_error']} < {self.qber}(threshold)")

            # send remained theta1
            logging.info("[C] BASIS RECONCILIATION")
            
            logging.debug("[C] sending remaining theta1 and verify_index to Bob")
            await assend(self.writer,theta1)
            
            del received_commitment
            del theta1
            del verify_index
            #del data

            # receive I0,I1
            logging.debug(f"[C] receiving Ix, Iy")
            [Ix,Iy] = await asrecv(self.reader)
            logging.debug(f"[C] Indices Ib : {Iy[:10]}")

            # At this point,client should not know which I is the matched one

            Xx = [x1[i] for i in Ix]
            Xy = [x1[i] for i in Iy]
            logging.debug(f"[C] Xx: {Xx[:10]},length:{len(Xx)}")
            logging.debug(f"[C] Xy: {Xy[:10]},length:{len(Xy)}")
            del x1


            logging.info("[C] ERROR CORRECTION")
            time1=start_time()

            logging.debug("[C] start syndrome computation")
            # read matrix
            logging.debug("[S] load matrix")
            H, eccblock = read_matrix(min(len(Xx), len(Xy)), measured_qber)
            logging.debug("[S] matrix loaded")
            print_csr_size(H)

            if len(Xx) < eccblock or len(Xy) < eccblock: # Insecure case    
                #Xx = Xx + [0]*(eccblock - len(Xx))
                logging.error(f"[C] Not enough bits for error correction block size! len(Xx):{len(Xx)},len(Xy):{len(Xy)},eccblock:{eccblock}.")
                return

            # compute LDPC syndrome
            # matrix multiplication
            if len(Xx) < eccblock or len(Xy) < eccblock:
                logging.debug(f"[C] length block_x: {len(Xx)}, length block_y: {len(Xy)}")
                logging.error(f"[C] Not enough bits for error correction block size {eccblock}. Aborting!")
                return

            
            Salice_x = []
            Salice_y = []

            Xx=Xx[:eccblock*(len(Xx)//eccblock)]
            Xy=Xy[:eccblock*(len(Xy)//eccblock)]
            minlen = min(len(Xx), len(Xy))
            leak=0
            for i in range(0, minlen, eccblock):
                block_x = Xx[i:i+eccblock]
                block_y = Xy[i:i+eccblock]
                try:
                    Salice_x.append(H @ block_x % 2)  # length need to fit the n of matrix
                    Salice_y.append(H @ block_y % 2)
                    leak+=H.shape[0]

                except Exception as e:
                    logging.debug(f"[C] left syndrome... {e}")

            if len(Xx) - minlen >= eccblock:
                i += eccblock
                block_x = Xx[i:i+eccblock]
                try:
                    Salice_x.append(H @ block_x % 2)
                except Exception as e:
                    logging.debug(f"[C] left syndrome... {e}")

            elif len(Xy) - minlen >= eccblock:
                i += eccblock
                block_y = Xy[i:i+eccblock]
                try:
                    Salice_y.append(H @ block_y % 2)
                except Exception as e:
                    logging.debug(f"[C] left syndrome... {e}")

            logging.debug(f"[C] syndrome alice Sx:{Salice_x[0][:10]} ,length:{len(Salice_x)}")
            logging.debug(f"[C] syndrome alice Sy:{Salice_y[0][:10]} ,length:{len(Salice_y)}")

            logging.debug("[C] send syndromes to Bob")
            # send syndromes to the server
            await assend(self.writer,[Salice_x,Salice_y])
            
            time_ecc = delta_time(time1)

            logging.debug("[C] For INFO/benchmark only, send secret keys to Bob")
            
            # For Debugging/Information only, sends the secrets to the server.
            # send matched and unmached data to the server
            await assend(self.writer,[Xx,Xy])

            # ==============================================
            # generate random seed to encrept m0,m1

            logging.info("[C] ENCRYPTION")
            

            # encrypt m0,m1
            c0,s0 = prg_encrypt2(Xx, self.m0, measured_qber, lambda_ot, leak)
            c1,s1 = prg_encrypt2(Xy, self.m1, measured_qber, lambda_ot, leak)

            logging.debug(f"[C] message:{self.m0[:10]}, length:{len(self.m0)}")
            logging.debug(f"[C] Encrypted message:{c0[:10]}, length:{len(c0)}")
            logging.debug(f"[C] Seed:{s0[:10]}, length:{len(s0)}")


            logging.debug(f"[C] message:{self.m1[:10]}, length:{len(self.m1)}")
            logging.debug(f"[C] Encrypted message:{c1[:10]}, length:{len(c1)}")
            logging.debug(f"[C] Seed:{s1[:10]}, length:{len(s1)}")

            # send s, c to the server
            await assend(self.writer, [s0,c0,s1,c1])

            logging.info(f"[C] sent encrypted messages and seeds to the server, closing connection.")
            time_total = delta_time(time0)
            writecsv(self.csvpath,[round(time_to_receive,2), self.num_batches * 2* self.batch_size, round(time_commit,2), measured_qber, 0, round(time_ecc,2), 0, round(time_total,2), self.mode])
