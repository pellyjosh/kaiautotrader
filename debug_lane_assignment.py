#!/usr/bin/env python3
"""
Debug script to check Enhanced Martingale lane assignment
"""

import sys
import os

# Add the project directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from db.database_manager import DatabaseManager
    import db.database_config as db_config
except ImportError as e:
    print(f"Error importing database modules: {e}")
    sys.exit(1)

def debug_lane_assignment():
    """Debug lane assignment for specific accounts and symbols"""
    
    # Initialize database
    try:
        if db_config.DATABASE_TYPE.lower() == "mysql":
            db = DatabaseManager(db_type='mysql', **db_config.MYSQL_CONFIG)
        else:
            db = DatabaseManager(db_type='sqlite', db_path=db_config.SQLITE_DB_PATH)
        
        print("Connected to database successfully.")
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return False
    
    accounts = ['pelly_demo', 'tonami_demo']
    test_symbols = ['JODCNY_otc', 'MATIC_otc']
    
    print("\n" + "="*80)
    print("DEBUGGING LANE ASSIGNMENT")
    print("="*80)
    
    for account in accounts:
        print(f"\n--- Account: {account} ---")
        
        # Check all lanes for this account
        all_lanes = db.get_all_martingale_lanes(account)
        print(f"Total lanes for {account}: {len(all_lanes)}")
        
        for lane in all_lanes:
            print(f"  Lane: {lane['lane_id']}")
            print(f"    Symbol: {lane['symbol']}")
            print(f"    Status: {lane['status']}")
            print(f"    Level: {lane['current_level']}")
            print(f"    Amount: ${lane['current_amount']:.2f}")
            print(f"    Trades: {len(lane['trade_ids'])}")
            print()
        
        # Test lane assignment for each symbol
        for symbol in test_symbols:
            print(f"Testing lane assignment for {account} + {symbol}:")
            
            # Get inactive lanes for this symbol
            inactive_lanes = db.get_inactive_martingale_lanes(account, symbol)
            print(f"  Inactive lanes for {symbol}: {len(inactive_lanes)}")
            for lane in inactive_lanes:
                print(f"    - {lane['lane_id']} (Level {lane['current_level']}, ${lane['current_amount']:.2f})")
            
            # Get next lane for assignment
            next_lane = db.get_next_lane_for_assignment(account, symbol)
            if next_lane:
                print(f"  Next lane assigned: {next_lane['lane_id']} ({next_lane['symbol']})")
                if next_lane['symbol'] != symbol:
                    print(f"  ❌ ERROR: Lane symbol ({next_lane['symbol']}) doesn't match requested ({symbol})")
                else:
                    print(f"  ✅ OK: Lane symbol matches")
            else:
                print(f"  No lane assigned (will use base amount)")
            print()
    
    db.close()
    print("Debug completed.")

if __name__ == "__main__":
    debug_lane_assignment()
