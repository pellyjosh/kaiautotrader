#!/usr/bin/env python3
"""
Database Migration Script for Enhanced Martingale Fix
Fixes current_level values and recalculates current_amount for all existing lanes
"""

import sys
import os
import json

# Add the project directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from db.database_manager import DatabaseManager
    import db.database_config as db_config
except ImportError as e:
    print(f"Error importing database modules: {e}")
    print("Make sure you're running this from the project root directory.")
    sys.exit(1)

def migrate_martingale_levels():
    """Migrate existing Martingale lanes to use correct level calculations"""
    
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
    
    try:
        # Get all existing lanes
        if db.db_type == "mysql":
            query = "SELECT lane_id, current_level, base_amount, multiplier FROM martingale_lanes"
        else:
            query = "SELECT lane_id, current_level, base_amount, multiplier FROM martingale_lanes"
        
        result = db._execute_query(query, fetch="all")
        
        if not result:
            print("No existing Martingale lanes found.")
            return True
        
        print(f"Found {len(result)} existing Martingale lanes to migrate.")
        
        # Migrate each lane
        migrated_count = 0
        for row in result:
            lane_id, current_level, base_amount, multiplier = row
            
            # Adjust level if it was incorrectly set to start at 1
            if current_level > 0:
                # Assume this lane was created with the old system (starting at level 1)
                # Adjust to new system (starting at level 0)
                new_level = current_level - 1
                new_amount = float(base_amount) * (float(multiplier) ** new_level)
                
                # Update the lane
                if db.db_type == "mysql":
                    update_query = """
                    UPDATE martingale_lanes 
                    SET current_level = %s, current_amount = %s, updated_at = NOW()
                    WHERE lane_id = %s
                    """
                else:
                    update_query = """
                    UPDATE martingale_lanes 
                    SET current_level = ?, current_amount = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE lane_id = ?
                    """
                
                db._execute_query(update_query, (new_level, new_amount, lane_id))
                
                print(f"Migrated lane {lane_id}: Level {current_level} -> {new_level}, Amount ${new_amount:.2f}")
                migrated_count += 1
            else:
                # Lane already uses the correct level system
                print(f"Lane {lane_id} already uses correct level system (Level {current_level})")
        
        # Commit changes
        if db.db_type == "mysql":
            db.connection.commit()
        
        print(f"\nMigration completed successfully!")
        print(f"Migrated {migrated_count} lanes.")
        print(f"Total lanes processed: {len(result)}")
        
        return True
        
    except Exception as e:
        print(f"Error during migration: {e}")
        return False
    finally:
        db.close()

def verify_calculation_logic():
    """Verify that the calculation logic is working correctly"""
    print("\n" + "="*50)
    print("VERIFICATION: Testing Martingale Calculation Logic")
    print("="*50)
    
    base_amount = 1.0
    multiplier = 1.5
    
    print(f"Base Amount: ${base_amount}")
    print(f"Multiplier: {multiplier}")
    print()
    
    print("Correct sequence should be:")
    for level in range(0, 5):
        amount = base_amount * (multiplier ** level)
        if level == 0:
            print(f"Level {level}: ${amount:.2f} (Base trade)")
        else:
            print(f"Level {level}: ${amount:.2f} (Martingale level {level})")
    
    print()
    print("This means:")
    print("- First trade (after signal): $1.00 (base)")
    print("- If it loses, create lane with Level 0")
    print("- Next trade on that lane: Level 1 = $1.50")
    print("- If it loses again: Level 2 = $2.25")
    print("- If it loses again: Level 3 = $3.38")
    print("- And so on...")

if __name__ == "__main__":
    print("Enhanced Martingale Migration Script")
    print("="*50)
    
    # First verify the calculation logic
    verify_calculation_logic()
    
    # Ask for confirmation
    print("\n" + "="*50)
    response = input("Do you want to proceed with the database migration? (y/N): ")
    
    if response.lower() in ['y', 'yes']:
        print("\nStarting migration...")
        success = migrate_martingale_levels()
        
        if success:
            print("\n✅ Migration completed successfully!")
            print("\nNext steps:")
            print("1. Restart your trading bot")
            print("2. Monitor the logs to ensure Martingale calculations are correct")
            print("3. Test with small amounts first")
        else:
            print("\n❌ Migration failed. Please check the error messages above.")
            sys.exit(1)
    else:
        print("\nMigration cancelled.")
        sys.exit(0)
