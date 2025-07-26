#!/usr/bin/env python3

# Test if the issue is specifically with multiprocessing.Process.start()
import multiprocessing
import time
import os

def simple_worker():
    print(f"Worker PID: {os.getpid()}")
    print("Worker started successfully!")
    time.sleep(2)
    print("Worker completing...")

def test_process_start():
    print(f"Main PID: {os.getpid()}")
    print("Testing multiprocessing.Process.start()...")
    
    try:
        multiprocessing.set_start_method('fork', force=True)
        print("Set start method to fork")
    except RuntimeError:
        pass
    
    print("Creating process...")
    process = multiprocessing.Process(target=simple_worker)
    print("Process created, about to start...")
    
    # This is where the bot hangs
    process.start()
    print("Process started! Waiting for completion...")
    
    process.join(timeout=10)
    if process.is_alive():
        print("Process timeout!")
        process.terminate()
        process.join()
    else:
        print("Process completed successfully!")

if __name__ == "__main__":
    test_process_start()
