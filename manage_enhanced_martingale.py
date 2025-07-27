#!/usr/bin/env python3
"""
Enhanced Martingale Management Script
Configure and manage Enhanced Martingale trading settings
"""

import sys
import argparse
from db.database_manager import DatabaseManager
import db.database_config as db_config


def get_database_manager():
    """Initialize database connection"""
    try:
        if db_config.DATABASE_TYPE.lower() == "mysql":
            return DatabaseManager(db_type='mysql', **db_config.MYSQL_CONFIG)
        else:
            return DatabaseManager(db_type='sqlite', db_path=db_config.SQLITE_DB_PATH)
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return None


def list_accounts_and_settings(db):
    """List all accounts and their Enhanced Martingale settings"""
    try:
        accounts = db.get_all_accounts()
        if not accounts:
            print("No accounts found in database.")
            return
        
        print("\n=== Account Enhanced Martingale Settings ===")
        print(f"{'Account':<15} {'Enabled':<8} {'Concurrent':<10} {'Max Lanes':<10} {'Strategy':<12} {'Auto Create':<11} {'Cool Down':<10}")
        print("-" * 85)
        
        for account in accounts:
            account_name = account['worker_name']
            enabled = "✓" if account['enabled'] else "✗"
            
            # Get trading settings
            settings = db.get_trading_settings(account_name)
            concurrent = "✓" if settings.get('concurrent_trading_enabled', False) else "✗"
            max_lanes = settings.get('max_concurrent_lanes', 3)
            strategy = settings.get('lane_assignment_strategy', 'fifo')
            auto_create = "✓" if settings.get('auto_create_lanes', True) else "✗"
            cool_down = settings.get('cool_down_seconds', 0)
            
            print(f"{account_name:<15} {enabled:<8} {concurrent:<10} {max_lanes:<10} {strategy:<12} {auto_create:<11} {cool_down:<10}")
        
        # Show active lanes
        print("\n=== Active Martingale Lanes ===")
        active_lanes = db.get_active_martingale_lanes()
        if not active_lanes:
            print("No active Martingale lanes found.")
        else:
            print(f"{'Lane ID':<25} {'Account':<15} {'Symbol':<12} {'Level':<6} {'Amount':<8} {'Invested':<10} {'Created':<20}")
            print("-" * 105)
            for lane in active_lanes:
                lane_id_short = lane['lane_id'][-20:] if len(lane['lane_id']) > 20 else lane['lane_id']
                created = str(lane['created_at'])[:19] if lane['created_at'] else 'N/A'
                print(f"{lane_id_short:<25} {lane['account_name']:<15} {lane['symbol']:<12} {lane['current_level']:<6} ${lane['current_amount']:<7.2f} ${lane['total_invested']:<9.2f} {created:<20}")
        
    except Exception as e:
        print(f"Error listing accounts: {e}")


def configure_account(db, account_name, **settings):
    """Configure Enhanced Martingale settings for an account"""
    try:
        # Validate account exists
        accounts = db.get_all_accounts()
        account_names = [acc['worker_name'] for acc in accounts]
        
        if account_name not in account_names:
            print(f"Error: Account '{account_name}' not found.")
            print(f"Available accounts: {', '.join(account_names)}")
            return False
        
        # Filter out None values
        filtered_settings = {k: v for k, v in settings.items() if v is not None}
        
        if not filtered_settings:
            print("No settings provided to update.")
            return False
        
        # Update settings
        success = db.update_trading_settings(account_name, **filtered_settings)
        
        if success:
            print(f"Successfully updated Enhanced Martingale settings for account '{account_name}':")
            for key, value in filtered_settings.items():
                print(f"  {key}: {value}")
        else:
            print(f"Failed to update settings for account '{account_name}'")
        
        return success
        
    except Exception as e:
        print(f"Error configuring account: {e}")
        return False


def show_lane_statistics(db, account_name=None, days=30):
    """Show Martingale lane statistics"""
    try:
        stats = db.get_lane_statistics(account_name, days)
        
        print(f"\n=== Martingale Lane Statistics ({days} days) ===")
        if account_name:
            print(f"Account: {account_name}")
        else:
            print("All accounts")
        
        print(f"Total lanes created: {stats.get('total_lanes', 0)}")
        print(f"Completed lanes: {stats.get('completed_lanes', 0)}")
        print(f"Active lanes: {stats.get('active_lanes', 0)}")
        print(f"Cancelled lanes: {stats.get('cancelled_lanes', 0)}")
        print(f"Average level reached: {stats.get('avg_level', 0):.2f}")
        print(f"Maximum level reached: {stats.get('max_level', 0)}")
        print(f"Total invested: ${stats.get('total_invested', 0):.2f}")
        print(f"Total potential payout: ${stats.get('total_potential_payout', 0):.2f}")
        
        if stats.get('total_lanes', 0) > 0:
            completion_rate = (stats.get('completed_lanes', 0) / stats.get('total_lanes', 0)) * 100
            print(f"Completion rate: {completion_rate:.1f}%")
        
    except Exception as e:
        print(f"Error showing statistics: {e}")


def force_complete_lane(db, lane_id):
    """Force complete a Martingale lane"""
    try:
        success = db.complete_martingale_lane(lane_id)
        
        if success:
            print(f"Successfully completed lane '{lane_id}'")
        else:
            print(f"Failed to complete lane '{lane_id}'")
        
        return success
        
    except Exception as e:
        print(f"Error completing lane: {e}")
        return False


def str_to_bool(v):
    """Convert string to boolean"""
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

def main():
    parser = argparse.ArgumentParser(description="Enhanced Martingale Management")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List accounts and settings')
    
    # Configure command
    config_parser = subparsers.add_parser('configure', help='Configure account settings')
    config_parser.add_argument('account', help='Account name')
    config_parser.add_argument('--concurrent', type=str_to_bool, help='Enable concurrent trading (true/false)')
    config_parser.add_argument('--max-lanes', type=int, help='Maximum concurrent lanes')
    config_parser.add_argument('--strategy', choices=['fifo', 'round_robin', 'symbol_priority'], help='Lane assignment strategy')
    config_parser.add_argument('--auto-create', type=str_to_bool, help='Auto-create lanes on loss (true/false)')
    config_parser.add_argument('--cool-down', type=int, help='Cool down seconds between trades')
    config_parser.add_argument('--max-daily-lanes', type=int, help='Maximum daily lanes to create')
    
    # Statistics command
    stats_parser = subparsers.add_parser('stats', help='Show lane statistics')
    stats_parser.add_argument('--account', help='Specific account (optional)')
    stats_parser.add_argument('--days', type=int, default=30, help='Number of days to analyze')
    
    # Complete lane command
    complete_parser = subparsers.add_parser('complete', help='Force complete a lane')
    complete_parser.add_argument('lane_id', help='Lane ID to complete')
    complete_parser.add_argument('--status', default='cancelled', choices=['completed', 'cancelled'], help='Completion status')
    
    # Examples command
    examples_parser = subparsers.add_parser('examples', help='Show usage examples')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    if args.command == 'examples':
        print("""
Enhanced Martingale Management Examples:

1. List all accounts and settings:
   python manage_enhanced_martingale.py list

2. Enable concurrent trading for an account:
   python manage_enhanced_martingale.py configure pelly_demo --concurrent true --max-lanes 5

3. Configure strategy and auto-creation:
   python manage_enhanced_martingale.py configure pelly_demo --strategy round_robin --auto-create true

4. Show statistics for specific account:
   python manage_enhanced_martingale.py stats --account pelly_demo --days 7

5. Force complete a stuck lane:
   python manage_enhanced_martingale.py complete pelly_demo_EURUSD_1234567890_abcd1234 --status cancelled

6. Disable concurrent trading:
   python manage_enhanced_martingale.py configure pelly_demo --concurrent false
        """)
        return
    
    # Initialize database
    db = get_database_manager()
    if not db:
        sys.exit(1)
    
    try:
        if args.command == 'list':
            list_accounts_and_settings(db)
        
        elif args.command == 'configure':
            settings = {
                'concurrent_trading_enabled': args.concurrent,
                'max_concurrent_lanes': args.max_lanes,
                'lane_assignment_strategy': args.strategy,
                'auto_create_lanes': args.auto_create,
                'cool_down_seconds': args.cool_down,
                'max_daily_lanes': args.max_daily_lanes
            }
            configure_account(db, args.account, **settings)
        
        elif args.command == 'stats':
            show_lane_statistics(db, args.account, args.days)
        
        elif args.command == 'complete':
            force_complete_lane(db, args.lane_id)
    
    finally:
        db.close()


if __name__ == "__main__":
    main()
