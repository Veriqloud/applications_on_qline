import argparse
import asyncio
import json
import logging
import time
from qkd import QKDHandlerAlice
from utils import read_with_padding, array_flaten, initcsv
from start_stop import *
from datetime import datetime

#logging.basicConfig(level=logging.ERROR)

# format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
'''
async def run_client(
    m0, m1, mode: str, path_config: str, qber: float,
    num_rounds: int = 1, num_batches: int = 100, batch_size: int = 16,
    networkfile: str = "config/network.json", csvpath: str = None
):
'''
async def run_client(mode: str, path_config: str,
    num_rounds: int = 1, num_qubits: int = 10000,
    networkfile: str = "config/network.json", csvpath: str = None
):
    """Run client for a specified number of rounds."""

    counter_rounds = 0
    
    # Load network configuration
    try:
        with open(networkfile, 'r') as f:
            network = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.error(f"[C] Failed to load network config: {e}")
        return []
    
    # Select host and port based on mode
    match mode:
        case "hwsim":
            logging.info("[C] HW simulation mode.")
            host, port = network['ip']['bob_hwsim'], int(network['port']['hwsim'])
        case "real":
            logging.info("[C] Real mode.")
            host, port = network['ip']['bob'], int(network['port']['ot'])
        case "test":
            logging.info("[C] Test mode.")
            host, port = "localhost", 0  # No actual connection in test mode
        case _:
            logging.error(f"[C] Invalid mode: {mode}")
            return []

    print("test5")
    results = []
    if num_rounds <= 0:
        # run non-stop mode
        print("test")
        logging.info("[C] Running in non-stop mode.")

        while True:
            
            # Add delay between rounds to allow FIFOs to reset
            #await asyncio.sleep(2)  # 2 second delay between rounds

             # Send start command
            try: 
                socket_reader, socket_writer = await send_start_command(mode, path_config)
                
            except Exception as e: 
                logging.error(f"[C] Send start failed: {e}")
                continue

                
            try:
                reader, writer = await asyncio.open_connection(host, port)
                logging.info(f"[C] Connected to {host}:{port}")
            except (ConnectionRefusedError, OSError) as e:
                logging.error(f"[C] Connection failed: {e}")
                continue

            handler = QKDHandlerAlice(
                reader, writer, qber=qber, role="client", m0=m0, m1=m1,
                mode=mode, path_config=path_config, num_batches=num_batches, batch_size=batch_size, socket_reader=socket_reader, socket_writer=socket_writer, csvpath=csvpath
            )

            await handler.run_protocol()
            #results.append(handler.m0)

            writer.close()
            await writer.wait_closed()

            logging.info(f"[C] Completed {counter_rounds+1} round(s).")
            counter_rounds += 1
            logging.info("=" * 50)

    else: # fix number of rounds
        for i in range(1):
            # Add delay between rounds to allow FIFOs to reset
            #if i > 0:
            #    await asyncio.sleep(2)  # 2 second delay between rounds
            print("test1")
            try: 
                print("test")
                socket_reader, socket_writer = await send_start_command(mode, path_config)
            except Exception as e: 
                print("test3")
                logging.error(f"[C] Send start failed: {e}")
                continue
            if socket_reader is None or socket_writer is None: 
                logging.error(f"[C] Send start failed, socket none")
                await asyncio.sleep(10)
                continue


                
            try:
                reader, writer = await asyncio.open_connection(host, port)
                logging.info(f"[C] Connected to {host}:{port}")
            except (ConnectionRefusedError, OSError) as e:
                logging.error(f"[C] Connection failed: {e}")
                continue

            handler = QKDHandlerAlice(
                reader, writer, mode=mode, path_config=path_config, num_qubits=num_qubits, socket_reader=socket_reader, socket_writer=socket_writer, csvpath=csvpath
            )

            await handler.run_protocol()
            #results.append(handler.m0)

            writer.close()
            await writer.wait_closed()

            logging.info(f"[C] Completed {i + 1}/{num_rounds} round(s).")
            logging.info("=" * 50)

    #await send_stop_command(mode, path_config,socket_reader, socket_writer)

    logging.info("[C] All connections completed.")
    return results


def main():
    start = time.time()
    logging.debug(f"[C] Starting at {start:.2f}")

    parser = argparse.ArgumentParser(description="Client Protocol Runner")
    parser.add_argument("-m", "--mode", type=str, default="hwsim",
                        help="Operation mode: 'hwsim', or 'real'")
    #parser.add_argument("-p", "--path_config", type=str, default="config/filepath_alice.json",
    #                    help="Path to FIFO config file")
    parser.add_argument("-p", "--path_config", type=str, default="config_test/sim/alice/ot.json",
                        help="Path to FIFO config file (default: config_test/sim/alice/ot.json)")
    parser.add_argument("-n", "--num_qubits", type=int, default=100,
                        help="Number of qubits (default: 100)")
    #parser.add_argument("-b", "--batch_size", type=int, default=16,
    #                    help="Batch size (default: 16)")
    parser.add_argument("-c", "--config_network", type=str, default="config/network.json",
                        help="Path to network config file")
    #parser.add_argument("-q", "--qber", type=float, default=0.055,
    #                    help="Quantum bit error rate (default: 0.055)")
    parser.add_argument("-r", "--num_rounds", type=int, default=1,
                        help="Number of protocol rounds, 0 for non-stop mode (default: 1)")
    parser.add_argument("-l", "--loglive", action="store_true",
                        help="show log in live")

    args = parser.parse_args()
    print(".-.")

    if args.loglive : 
        logging.basicConfig(
            format="%(asctime)s - %(levelname)s - %(message)s",
            #level=logging.INFO, 
            level=logging.DEBUG, 
            force=True
        )
    else:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        if args.mode == "hwsim":
            print("testtest")
            log_filename = f"sim_alice_{timestamp}.log"
        elif args.mode == "real":
            log_filename = f"app_alice_{timestamp}.log"
        else:
            log_filename = f"test_alice_{timestamp}.log"
        # Configure logging
        logging.basicConfig(
            filename=log_filename,
            format="%(asctime)s - %(levelname)s - %(message)s",
            #level=logging.INFO, 
            level=logging.DEBUG, 
            force=True
        )
        

    #csvpath=initcsv("alice")
    csvpath=None

    #num_bits = args.num_batches * args.batch_size
    #m0 = read_with_padding("m0.txt", num_bits // 2)
    #m1 = read_with_padding("m1.txt", num_bits // 2)
    #m0 = read_with_padding("m0.txt", 1024)
    #m1 = read_with_padding("m1.txt", 1024)
    print("trying")
    print(args.path_config)
    results = asyncio.run(run_client(
        #m0=m0,
        #m1=m1,
        mode=args.mode,
        path_config=args.path_config,
        #qber=args.qber,
        num_qubits=args.num_qubits,
        #num_batches=args.num_batches,
        #batch_size=args.batch_size,
        networkfile=args.config_network,
        csvpath=csvpath
    ))

    end = time.time()
    time_cost = end - start

    if time_cost > 0:
        total_bytes = len(array_flaten(results))
        rate = total_bytes / time_cost
        logging.info(f"[C] End time: {end:.2f}")
        logging.info(f"[C] Time cost: {time_cost:.2f}s")
        logging.info(f"[C] Transfer rate: {rate:.2f} bytes/sec")
    else:
        logging.warning("[C] Execution time too short to measure performance.")


if __name__ == "__main__":
    main()
