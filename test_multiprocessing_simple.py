#!/usr/bin/env python3

import multiprocessing
import time
import sys

def test_worker(name):
    print(f"Worker {name} started successfully!")
    time.sleep(2)
    print(f"Worker {name} finishing...")
    return f"Worker {name} completed"

def main():
    print("Testing multiprocessing under systemd...")
    
    # Set start method
    try:
        multiprocessing.set_start_method('spawn', force=True)
        print("Set multiprocessing start method to 'spawn'")
    except RuntimeError as e:
        print(f"Could not set start method: {e}")
    
    print("Creating worker process...")
    
    try:
        process = multiprocessing.Process(target=test_worker, args=("test1",))
        process.start()
        print("Worker process started, waiting for completion...")
        
        process.join(timeout=10)
        
        if process.is_alive():
            print("ERROR: Worker process is still running after timeout!")
            process.terminate()
            process.join()
            sys.exit(1)
        else:
            print("Worker process completed successfully!")
            print("Multiprocessing test PASSED!")
            
    except Exception as e:
        print(f"ERROR: Exception during multiprocessing test: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
