import json
import logging
import argparse
import time
from utils import read_exactly
# from applications_on_qline.Q_oblivious_transfer.utils import read_exactly


def reader_alice(mode, num_qubits, path_config):
    """Sequentially reads angles from FIFO and returns them."""
    logging.info("[Reader A] Sequential reader started")
    
    with open(path_config, 'r') as f:
        path = json.load(f)
    
    if mode == "hwsim":
        angle_fifo = path["angle"]["hwsim"]
    elif mode == "real":
        angle_fifo = path["angle"]["real"]
    else:
        raise ValueError(f"[Reader A] Unknown mode: {mode}")

    ang_list = []
    logging.info(f"[Reader A] Reading {num_qubits}")
    start = time.time()
    
    try:
        logging.info(f"Opening FIFO {angle_fifo}")
        with open(angle_fifo, "rb") as f:
            logging.debug("[Reader A] reading angles")
            #for _ in range(num_batches):
            data = read_exactly(f, num_qubits//2)
            
            if not data:
                logging.info("[Reader A] FIFO closed.")
            
            if (len(data) != num_qubits//2):
                logging.info(f"[Reader A] data is of length {len(data)} batch_size = {num_qubits//2}")
            
            ang_list.append(list(data))
                
    except Exception as e:
        logging.error(f"[Reader A] Error reading FIFO: {e}")
    
    end = time.time()
    seconds = end - start
    logging.info(f"[Reader A] Finished reading {len(ang_list)} batches in {seconds:.2f}s.")
    
    return ang_list

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reader A for angle data")
    parser.add_argument("-m", "--mode", default="hwsim", choices=["hwsim", "real"],
                        help="Mode: hwsim or real (default: hwsim)")
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
    angles = reader_alice(mode=args.mode, num_qubits=args.num_qubits, path_config=args.config)
    print_idx = 20
    print(f"Angles (first {print_idx}): {angles[:print_idx]}")
