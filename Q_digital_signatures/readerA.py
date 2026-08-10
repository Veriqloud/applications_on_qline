# not working
import asyncio
import json
import threading
import queue
import logging
import argparse
from utils import read_exactly, DroppingQueue

#from applications_on_qline.Q_oblivious_transfer.utils import read_exactly, DroppingQueue

# --- Global variables for singleton reader ---
_reader_thread = None
_shared_queue = queue.Queue()
_reader_lock = threading.Lock()

plot_queue_A = DroppingQueue(maxsize=1000)

#PATH_CONFIG = "config/filepath_alice.json"
#PATH_CONFIG = "kiwi_hw_control/config/sim/alice/ot.json"
PATH_CONFIG = "config_test/sim/alice/ot.json"


def fifo_reader_alice(angle_fifo, batch_size, data_queue):
    """Thread function: read FIFO continuously and push batches into the queue."""
    logging.info("[Reader A] FIFO reader started")
    try:
        with open(angle_fifo, "rb") as f:
            logging.debug("[Reader A] reading angles")
            logging.info("[Reader A] FIFO opened successfully")
            while True:
                data = read_exactly(f, batch_size)
                if not data:
                    logging.info("[Reader A] FIFO closed.")
                    break
                data_queue.put(data)
                plot_queue_A.put(data)

                #print(f"[Reader A] plot queue size: {plot_queue_A.qsize()}")
    except Exception as e:
        logging.error(f"[Reader A] Error reading FIFO: {e}")
    finally:
        data_queue.put(None)  # sentinel value
        logging.info("[Reader A] Reader thread exiting.")

def start_alice_reader_once(mode, batch_size,path_config=PATH_CONFIG):
    """Start the FIFO reader thread once (singleton)."""
    global _reader_thread, _shared_queue

    with _reader_lock:
        if _reader_thread and _reader_thread.is_alive():
            # Already running, don't start a new one
            return

        with open(path_config, 'r') as f:
            path = json.load(f)
        
        if mode in ("hwsim", "test"):
            angle_fifo = path["angle"]["hwsim"]
        elif mode == "real":
            angle_fifo = path["angle"]["real"]
        else:
            raise ValueError(f"[Reader A] Unknown mode: {mode}")

        _shared_queue = queue.Queue()
        _reader_thread = threading.Thread(
            target=fifo_reader_alice,
            args=(angle_fifo, batch_size, _shared_queue),
            daemon=True,
        )
        _reader_thread.start()
        logging.info("[Reader A] Reader thread started once.")

async def reader_alice(mode, num_batches, batch_size, path_config):
    """Async function that consumes data from the shared FIFO reader."""
    start_alice_reader_once(mode, batch_size, path_config)
    logging.info("Test")
    ang_list = []
    for _ in range(num_batches):
        logging.info("Test1")
        batch = await asyncio.to_thread(_shared_queue.get)
        # batch = _shared_queue.get()
        if batch is None:  # sentinel -> EOF or error
            break
        ang_list.append(list(batch))

    logging.info(f"[Reader A] Finished reading {len(ang_list)} batches.")
    return ang_list

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reader A for angle data")
    parser.add_argument("-m", "--mode", default="hwsim", choices=["hwsim", "test", "real"],
                        help="Mode: hwsim, test, or real (default: hwsim)")
    parser.add_argument("-b", "--batch-size", type=int, default=16,
                        help="Batch size (default: 16)")
    parser.add_argument("-n", "--num-batches", type=int, default=10,
                        help="Number of batches (default: 10)")
    #parser.add_argument("-c", "--config", default="config/filepath_alice.json",
    #                    help="Path to config file (default: config/filepath_alice.json)")
    #parser.add_argument("-c", "--config", default="kiwi_hw_control/config/sim/alice/ot.json",
    #                    help="Path to config file (default: kiwi_hw_control/config/sim/alice/ot.json)")
    
    parser.add_argument("-c", "--config", default="config_test/sim/alice/ot.json",
                        help="Path to config file (default: config_test/sim/alice/ot.json)")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    # Uncomment to send start command before reading
    '''
    async def send_start():
        with open(args.config) as f:
            cfg = json.load(f)
        socket_path = cfg["command"]["hwsim"]
        reader2, writer2 = await asyncio.open_unix_connection(socket_path)
        writer2.write(bytes([0x1, 0x0, 0x0, 0x0, 0x0]))
        await writer2.drain()
        resp = await reader2.read(5)
        await asyncio.sleep(2)
        logging.info(f"[C] Start command sent, response: {list(resp)}")
    asyncio.run(send_start())
    '''
    angles = asyncio.run(reader_alice(num_batches=args.num_batches, mode=args.mode, batch_size=args.batch_size, path_config=args.config))
    print_idx = 20
    print(f"Angles (first {print_idx}): {angles[:print_idx]}")
