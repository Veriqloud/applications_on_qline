import json
import logging
import argparse
import time 
from datetime import timedelta
from utils import read_exactly

#from applications_on_qline.Q_oblivious_transfer.utils import read_exactly



def reader_bob(mode, num_qubits, path_config):
    """Sequentially reads from FIFOs and returns angles and results."""
    logging.info("[Reader B] Sequential reader started")
    
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

    angles = []
    results = []
    logging.info(f"[readerB] Waiting for {num_qubits} values")
    start = time.time()
    
    try:
        with open(angle_path, "rb") as af, open(result_path, "rb") as rf:
            logging.debug("[Reader B] reading measurement results and angles")
            for _ in range(1):
                result_data = read_exactly(rf, num_qubits)
                angle_data = read_exactly(af, num_qubits//2)
                
                if not result_data or not angle_data:
                    logging.info("[Reader B] FIFO closed.")
                    break
                
                if (len(angle_data) != num_qubits//2):
                    logging.info(f"[Reader B] data is of length {len(angle_data)}")
                if (len(result_data) != 2*num_qubits//2):
                    logging.info(f"[Reader B] data is of length {len(result_data)}")
                
                angles.append(list(angle_data))
                results.append(list(result_data))
                
    except Exception as e:
        logging.error(f"[Reader B] Error reading FIFO: {e}")
    
    end = time.time()
    seconds = end - start
    logging.info(f"[readerB] Reading values in: {str(timedelta(seconds=seconds))}")

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
    angles, results = reader_bob(mode=args.mode, num_qubits=args.num_qubits, path_config=args.config)
    print_idx = 20
    print(f"Angles first {print_idx}: {angles[:print_idx]}")
    print(f"Results first {print_idx}: {results[:print_idx]}")
