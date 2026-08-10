import asyncio
from qkd import QKDHandlerBob
# from applications_on_qline.Q_oblivious_transfer.handler import ProtocolHandler
import argparse
import logging
import json
from datetime import datetime
from utils import initcsv
# from applications_on_qline.Q_oblivious_transfer.utils import initcsv

#logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)


connections_handled = 0
connections_lock = asyncio.Lock()
all_connections_done = asyncio.Event()

async def handle_connection(reader, writer, args,csvpath):
    global connections_handled
    if args.num_rounds <= 0:
        logging.info("[S] Running in non-stop mode.")
        connections_handled += 1
        handler = QKDHandlerBob(
            reader, writer,
            mode=args.mode,
            path_config=args.path_config,
            num_qubits=args.num_qubits,
            csvpath=csvpath
        )
        await handler.run_protocol()
        writer.close()
        await writer.wait_closed()
        # Add delay after connection closes to ensure FIFOs are reset
        await asyncio.sleep(1)
        logging.info(f"[S] Completed {connections_handled} connections.\n===============================================")
        

    else:
        async with connections_lock:
            if connections_handled >= args.num_rounds:
                writer.close()
                await writer.wait_closed()
                return
            connections_handled += 1
        logging.info("[S] Local: %s", writer.get_extra_info("sockname"))
        logging.info("[S] Remote: %s", writer.get_extra_info("peername"))
        handler = QKDHandlerBob(
            reader, writer,
            mode=args.mode,
            path_config=args.path_config,
            num_qubits=args.num_qubits,
            csvpath=csvpath
        )
        await handler.run_protocol()
        writer.close()
        await writer.wait_closed()
        # Add delay after connection closes to ensure FIFOs are reset
        await asyncio.sleep(1)
        #logging.info(f"[S] Completed {connections_handled}/{args.num_rounds} connections.\n===============================================")
        if connections_handled >= args.num_rounds:
            all_connections_done.set()

async def run_server(args, csvpath):
    # Load network config
    with open(args.config_network, 'r') as f:
        network = json.load(f)

    if args.mode == 'hwsim':
        host = network['ip']['bob_hwsim']
        port = int(network['port']['hwsim'])
    elif args.mode == 'real':
        host = network['ip']['bob']
        port = int(network['port']['ot'])
    elif args.mode == 'test':
        host = '127.0.0.1'
        port = 8888
    else:
        logging.error(f"[S] Invalid mode: {args.mode}")
        return

    server = await asyncio.start_server(
        lambda r, w: handle_connection(r, w, args,csvpath),
        host, port
    )

    async with server: 
        await all_connections_done.wait()
        server.close()
        await server.wait_closed()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bob FIFO reader (async version)")
    parser.add_argument("-m", "--mode", type=str, default="hwsim",
                        help="Operation mode: 'hwsim', or 'real'")
    #parser.add_argument("-p", "--path_config", type=str, default="config/filepath_bob.json",
    #                    help="Path to FIFO config file")
    parser.add_argument("-p", "--path_config", type=str, default="config_test/sim/bob/ot.json",
                        help="Path to FIFO config file (default: config_test/sim/bob/ot.json)")
    parser.add_argument("-n", "--num_qubits", type=int, default=100,
                        help="Number of qubits (default: 10000)")
    #parser.add_argument("-b", "--batch_size", type=int, default=16,
    #                    help="Batch size (default: 16)")
    parser.add_argument("-c", "--config_network", type=str, default="config/network.json",
                        help="Path to network config file")
    #parser.add_argument("-s", "--secret_choice", type=int, default=None,
    #                    help="A secret choice must made by the server (0 or 1) (default: None, random choice)")
    #parser.add_argument("-q", "--qber", type=float, default=0.055,
    #                    help="Quantum bit error rate (default: 0.055)")
    parser.add_argument("-r","--num_rounds", type=int, default=1,
                        help="Number of protocol rounds, 0 for non-stop mode (default: 1)")
    parser.add_argument("-l", "--loglive", action="store_true", 
                        help="show log live")

    args = parser.parse_args()

    if args.loglive : 
        logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
    else:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        if args.mode == "hwsim":
            log_filename = f"sim_bob_{timestamp}.log"
        elif args.mode == "real":
            log_filename = f"app_bob_{timestamp}.log"
        else:
            log_filename = f"test_bob_{timestamp}.log"
        logging.basicConfig(filename=log_filename,format='%(asctime)s - %(levelname)s - %(message)s', level=logging.DEBUG, force=True)
    
    #csvpath=initcsv("bob")
    csvpath=None
    
    asyncio.run(run_server(args, csvpath))