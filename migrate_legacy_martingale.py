#!/usr/bin/env python3
"""
Migration Script: Legacy Martingale to Enhanced Martingale
Converts existing losses and queued amounts to Enhanced Martingale lanes
"""

import sys
from datetime import datetime
from db.database_manager import DatabaseManager
import db.database_config as db_config
from enhanced_martingale import EnhancedMartingaleManager, get_enhanced_martingale_manager, initialize_enhanced_martingale


def migrate_legacy_to_enhanced():
    """Migrate legacy Martingale state to Enhanced Martingale lanes"""
    
    # Initialize database
    print("🔄 Initializing database connection...")
    db_manager = DatabaseManager()
    
    # Initialize Enhanced Martingale
    print("🚀 Initializing Enhanced Martingale system...")
    enhanced_mgr = initialize_enhanced_martingale(db_manager, print)
    
    # Get legacy Martingale states
    print("📊 Fetching legacy Martingale states...")
    legacy_states = db_manager.execute_query(
        "SELECT account_name, losses, multiplier, queue FROM martingale_state WHERE losses > 0 OR JSON_LENGTH(queue) > 0"
    )
    
    if not legacy_states:
        print("✅ No legacy Martingale states to migrate.")
        return
    
    print(f"📋 Found {len(legacy_states)} accounts with legacy Martingale data:")
    
    for state in legacy_states:
        account_name = state['account_name']
        losses = state['losses']
        multiplier = state['multiplier']
        queue = state['queue']
        
        print(f"\n🏦 Account: {account_name}")
        print(f"   📉 Losses: {losses}")
        print(f"   📈 Multiplier: {multiplier}")
        print(f"   📝 Queue: {queue}")
        
        # Get account settings for base amount
        account_settings = db_manager.execute_query(
            "SELECT base_amount FROM trading_settings WHERE account_name = %s",
            (account_name,)
        )
        
        if not account_settings:
            print(f"   ⚠️  No trading settings found for {account_name}, skipping...")
            continue
            
        base_amount = account_settings[0]['base_amount']
        print(f"   💰 Base Amount: ${base_amount}")
        
        # If there are losses, create lanes for each queued amount
        if losses > 0 and queue:
            import json
            try:
                queue_amounts = json.loads(queue) if isinstance(queue, str) else queue
                print(f"   🎯 Creating {len(queue_amounts)} Enhanced Martingale lanes...")
                
                for i, amount in enumerate(queue_amounts):
                    # Calculate what level this amount represents
                    level = 1
                    while base_amount * (multiplier ** (level - 1)) < amount:
                        level += 1
                    
                    # Create a lane for this amount
                    lane_id = enhanced_mgr.create_lane(account_name, "LEGACY_MIGRATION", base_amount, multiplier)
                    if lane_id:
                        # Update the lane to the correct level
                        enhanced_mgr.db_manager.execute_query(
                            """UPDATE martingale_lanes 
                               SET current_level = %s, current_amount = %s, 
                                   total_invested = %s
                               WHERE lane_id = %s""",
                            (level, amount, amount, lane_id)
                        )
                        print(f"   ✅ Created lane {lane_id} at level {level} with ${amount}")
                    else:
                        print(f"   ❌ Failed to create lane for ${amount}")
                        
            except Exception as e:
                print(f"   ❌ Error processing queue: {e}")
                continue
        
        # Clear legacy state after migration
        print(f"   🧹 Clearing legacy Martingale state for {account_name}...")
        db_manager.execute_query(
            "UPDATE martingale_state SET losses = 0, queue = '[]' WHERE account_name = %s",
            (account_name,)
        )
        
    print(f"\n🎉 Migration completed! Legacy states converted to Enhanced Martingale lanes.")
    
    # Show new Enhanced Martingale state
    print("\n📊 Current Enhanced Martingale state:")
    lanes = db_manager.execute_query("SELECT * FROM martingale_lanes WHERE status = 'active'")
    if lanes:
        for lane in lanes:
            print(f"   🛤️  Lane {lane['lane_id']}: {lane['account_name']} - ${lane['current_amount']} (Level {lane['current_level']})")
    else:
        print("   ℹ️  No active Enhanced Martingale lanes found.")


if __name__ == "__main__":
    try:
        migrate_legacy_to_enhanced()
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)
