#!/usr/bin/env python3

# Simple test - just import the bot modules and see what fails
import sys
import os
sys.path.insert(0, '/opt/HuboluxAutoTrader')

print("Testing bot module imports...")

try:
    print("Importing time, math, asyncio, json, threading, multiprocessing, uuid...")
    import time, math, asyncio, json, threading, multiprocessing, uuid
    print("✓ Basic modules imported")
    
    print("Importing datetime...")
    from datetime import datetime
    print("✓ datetime imported")
    
    print("Importing pocketoptionapi.global_value...")
    import pocketoptionapi.global_value as global_value
    print("✓ global_value imported")
    
    print("Importing numpy, pandas...")
    import numpy as np
    import pandas as pd
    print("✓ numpy, pandas imported")
    
    print("Importing pocket_connector...")
    import pocket_connector
    print("✓ pocket_connector imported")
    
    print("Importing detectsignal...")
    import detectsignal
    print("✓ detectsignal imported")
    
    print("Importing worker...")
    import worker
    print("✓ worker imported")
    
    print("Importing database modules...")
    from db.database_manager import DatabaseManager
    from db.database_config import DATABASE_TYPE, SQLITE_DB_PATH, MYSQL_CONFIG
    print("✓ database modules imported")
    
    print("\nAll imports successful! The issue is not with module imports.")
    
except Exception as e:
    print(f"ERROR: Failed to import modules: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("Import test completed successfully!")
