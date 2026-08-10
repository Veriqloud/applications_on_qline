import json
import threading
import queue
import logging
import asyncio
import argparse
import time 
from datetime import timedelta
from utils import read_exactly, DroppingQueue
#sfrom applications_on_qline.Q_oblivious_transfer.utils import read_exactly, DroppingQueue


reader_thread = None
shared_queue = queue.Queue()
plot_queue_B = DroppingQueue(maxsize=1000)

#PATH_CONFIG = "config/filepath_bob.json"
#PATH_CONFIG = "kiwi_hw_control/config/sim/bob/ot.json"
PATH_CONFIG = "config_test/sim/bob/ot.json"

def fifo_reader_bob(angle_fifo, result_fifo, batch_size, data_queue):
    """Thread: reads from both FIFOs and pushes a (angle, result) tuple."""
    logging.info("[Reader B] FIFO reader started")
    try:
        print(angle_fifo)
        print(result_fifo)  
        

        with open(angle_fifo, "rb") as af, open(result_fifo, "rb") as rf:
        #with open(angle_fifo, "rb") as af, open(result_fifo, "rb") as rf:
            #logging.info("test test")
            #logging.debug("[Reader B] reading measurement results and angles")
            while True:
                #logging.info("reading result")
                result_data = read_exactly(rf, 2 * batch_size)
                #logging.info("reading angle")
                angle_data = read_exactly(af, batch_size)
                #logging.info("got both")
                if not result_data or not angle_data:
                    #logging.info("[Reader B] FIFO closed.")
                    break
                data_queue.put((angle_data, result_data))
                plot_queue_B.put((angle_data, result_data))

                #print(f"[Reader B] plot queue size: {plot_queue_B.qsize()}")
    except Exception as e:
        logging.info("test")
        logging.error(f"[Reader B] Error reading FIFO: {e}")
    finally:
        logging.info("t")
        data_queue.put(None)

def start_reader_once(mode, batch_size, path_config=PATH_CONFIG):
    global reader_thread, shared_queue
    if reader_thread and reader_thread.is_alive():
        return  # do not create a new thread

    with open(path_config, 'r') as f:
        path = json.load(f)
        
    if mode == "test" or mode == "hwsim":
        angle_path = path["angle"]["hwsim"]
        result_path = path["result"]["hwsim"]
    elif mode == "real":
        angle_path = path["angle"]["real"]
        result_path = path["result"]["real"]
    else:
        raise ValueError("Unknown mode")

    reader_thread = threading.Thread(
        target=fifo_reader_bob,
        args=(angle_path, result_path, batch_size, shared_queue),
        daemon=True,
    )
    reader_thread.start()
    logging.info("[Reader B] Reader thread started once.")

async def reader_bob(mode, num_batches, batch_size, path_config=PATH_CONFIG):
    # launch reader thread
    start_reader_once(mode, batch_size,path_config)

    angles = []
    results = []
    logging.info(f"[readerB] Waiting for {2*num_batches*batch_size} values")
    start = time.time()
    for _ in range(num_batches):
        item = await asyncio.to_thread(shared_queue.get)
        #item = shared_queue.get()
        if item is None:
            break
        a, r = item
        angles.append(list(a))
        results.append(list(r))
    end = time.time()
    seconds = end - start
    logging.info(f"[readerB] Reading values in: {str(timedelta(seconds=seconds))}")

    # run another thread of qber calculation


    return angles, results



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reader B for angle and result data")
    parser.add_argument("-m", "--mode", default="hwsim", choices=["hwsim", "test", "real"],
                        help="Mode: hwsim, test, or real (default: hwsim)")
    parser.add_argument("-b", "--batch-size", type=int, default=16,
                        help="Batch size (default: 16)")
    parser.add_argument("-n", "--num-batches", type=int, default=10,
                        help="Number of batches (default: 10)")
    #parser.add_argument("-c", "--config", default="config/filepath_bob.json",
    #                    help="Path to config file (default: config/filepath_bob.json)")
    #parser.add_argument("-c", "--config", default="kiwi_hw_control/config/sim/bob/ot.json",
    #                    help="Path to config file (default: kiwi_hw_control/config/sim/bob/ot.json)")
    
    parser.add_argument("-c", "--config", default="config_test/sim/bob/ot.json",
                        help="Path to config file (default: config_test/sim/bob/ot.json)")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    angles, results = asyncio.run(reader_bob(num_batches=args.num_batches, mode=args.mode, batch_size=args.batch_size, path_config=args.config))
    print_idx = 20
    print(f"Angles first {print_idx}: {angles[:print_idx]}")
    print(f"Results first {print_idx}: {results[:print_idx]}")
