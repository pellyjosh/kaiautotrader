#!/usr/bin/env python3
"""
Database Administration Tool for HuboluxTradingBot Bot
Provides database management, statistics, and maintenance functions
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from db.database_manager import DatabaseManager, DatabaseConfig
import db.database_config as db_config

def get_database_manager():
    """Get database manager instance"""
    try:
        if db_config.DATABASE_TYPE.lower() == "mysql":
            config = DatabaseConfig.mysql_config(**db_config.MYSQL_CONFIG)
        else:
            config = DatabaseConfig.sqlite_config(db_config.SQLITE_DB_PATH)
        
        return DatabaseManager(**config)
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        return None

def show_statistics(db):
    """Show database statistics"""
    print("📊 DATABASE STATISTICS")
    print("=" * 50)
    
    stats = db.get_statistics()
    if not stats:
        print("❌ Failed to get statistics")
        return
    
    print(f"Total Accounts: {stats.get('total_accounts', 0)}")
    print(f"Total Trades: {stats.get('total_trades', 0)}")
    print(f"Pending Trades: {stats.get('pending_trades', 0)}")
    print(f"Total Wins: {stats.get('total_wins', 0)}")
    print(f"Total Losses: {stats.get('total_losses', 0)}")
    print(f"Overall Win Rate: {stats.get('win_rate', 0):.2f}%")
    
    # Martingale state
    martingale = stats.get('martingale_state', {})
    print(f"\n🎯 MARTINGALE STATE")
    print(f"Consecutive Losses: {martingale.get('consecutive_losses', 0)}")
    print(f"Current Multiplier: {martingale.get('current_multiplier', 1.0):.2f}")
    print(f"Base Amount: ${martingale.get('base_amount', 1.0):.2f}")
    print(f"Max Consecutive Losses: {martingale.get('max_consecutive_losses', 0)}")
    print(f"Total Sequences: {martingale.get('total_sequences', 0)}")

def show_accounts(db):
    """Show all accounts"""
    print("👥 CONNECTED ACCOUNTS")
    print("=" * 50)
    
    accounts = db.get_all_accounts()
    if not accounts:
        print("No accounts found")
        return
    
    for account in accounts:
        demo_text = "Demo" if account['is_demo'] else "Real"
        status = account['status'].upper()
        print(f"🔹 {account['worker_name']} ({demo_text})")
        print(f"   Balance: ${account['balance']:.2f}")
        print(f"   Status: {status}")
        print(f"   Last Updated: {account['last_updated']}")
        print()

def show_recent_trades(db, limit=10, worker_name=None):
    """Show recent trades"""
    print(f"📈 RECENT TRADES (Last {limit})")
    print("=" * 50)
    
    trades = db.get_recent_trades(limit=limit, worker_name=worker_name)
    if not trades:
        print("No trades found")
        return
    
    for trade in trades:
        result_emoji = "✅" if trade['result'] == 'win' else "❌" if trade['result'] == 'loss' else "⏳"
        martingale_text = f" (M{trade['martingale_level']})" if trade['is_martingale_trade'] else ""
        
        print(f"{result_emoji} {trade['symbol']} {trade['direction'].upper()}")
        print(f"   Amount: ${trade['amount']:.2f}{martingale_text}")
        print(f"   Worker: {trade['worker_name']}")
        print(f"   Entry: {trade['entry_time']}")
        print(f"   Result: {trade['result'].upper()}")
        if trade['payout'] > 0:
            print(f"   Payout: ${trade['payout']:.2f}")
        print()

def show_performance(db, days=7, worker_name=None):
    """Show performance summary"""
    print(f"📊 PERFORMANCE SUMMARY (Last {days} days)")
    print("=" * 50)
    
    performance = db.get_performance_summary(worker_name=worker_name, days=days)
    if not performance:
        print("No performance data found")
        return
    
    for perf in performance:
        print(f"📅 {perf['date']} - {perf['worker_name']}")
        print(f"   Trades: {perf['total_trades']} (W:{perf['winning_trades']} L:{perf['losing_trades']})")
        print(f"   Win Rate: {perf['win_rate']:.2f}%")
        print(f"   Invested: ${perf['total_invested']:.2f}")
        print(f"   Payout: ${perf['total_payout']:.2f}")
        print(f"   Net Profit: ${perf['net_profit']:.2f}")
        print(f"   Martingale Recoveries: {perf['martingale_recoveries']}")
        print(f"   Max Consecutive Losses: {perf['max_consecutive_losses']}")
        print()

def reset_martingale(db):
    """Reset Martingale state"""
    print("🔄 RESETTING MARTINGALE STATE")
    print("=" * 30)
    
    confirm = input("Are you sure you want to reset Martingale state? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Operation cancelled")
        return
    
    if db.reset_martingale_state():
        print("✅ Martingale state reset successfully")
    else:
        print("❌ Failed to reset Martingale state")

def backup_database(db, backup_path=None):
    """Backup database"""
    print("💾 CREATING DATABASE BACKUP")
    print("=" * 30)
    
    if not backup_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"backup_trades_{timestamp}.json"
    
    if db.backup_data(backup_path):
        print(f"✅ Database backup created: {backup_path}")
    else:
        print("❌ Backup failed")

def cleanup_old_trades(db, days=90):
    """Clean up old trades"""
    print(f"🧹 CLEANING UP TRADES OLDER THAN {days} DAYS")
    print("=" * 40)
    
    confirm = input(f"Are you sure you want to delete trades older than {days} days? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Operation cancelled")
        return
    
    # This would need to be implemented in DatabaseManager
    print("⚠️  Cleanup functionality needs to be implemented in DatabaseManager")

def add_test_data(db):
    """Add test data for demonstration"""
    print("🧪 ADDING TEST DATA")
    print("=" * 20)
    
    confirm = input("Add test account and trades? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Operation cancelled")
        return
    
    # Add test account
    db.add_account("test_worker", "test_ssid_123", True, 1000.0)
    print("✅ Test account added")
    
    # Add test trades
    import time
    base_time = int(time.time())
    
    test_trades = [
        ("test_trade_1", "EURUSD_otc", "call", 10.0, 300, "win", 18.0),
        ("test_trade_2", "GBPUSD_otc", "put", 10.0, 300, "loss", 0.0),
        ("test_trade_3", "USDCAD_otc", "call", 25.0, 300, "win", 45.0),  # Martingale recovery
    ]
    
    for i, (trade_id, symbol, direction, amount, duration, result, payout) in enumerate(test_trades):
        unique_trade_id = f"{trade_id}_{base_time + i}"
        
        # Add trade
        db.add_trade(unique_trade_id, "test_worker", symbol, direction, amount, duration,
                    martingale_level=1 if i == 2 else 0, is_martingale_trade=i == 2)
        
        # Update result
        db.update_trade_result(unique_trade_id, result, payout)
        
        # Update performance
        db.update_daily_performance("test_worker", result, amount, payout, 
                                   is_martingale_recovery=i == 2)
    
    print("✅ Test trades added")

def main():
    parser = argparse.ArgumentParser(description="HuboluxTradingBot Database Administration")
    parser.add_argument("command", choices=[
        "stats", "accounts", "trades", "performance", "reset-martingale",
        "backup", "cleanup", "test-data"
    ], help="Command to execute")
    parser.add_argument("--limit", type=int, default=10, help="Limit for trades display")
    parser.add_argument("--days", type=int, default=7, help="Days for performance summary")
    parser.add_argument("--worker", type=str, help="Filter by worker name")
    parser.add_argument("--backup-path", type=str, help="Backup file path")
    parser.add_argument("--cleanup-days", type=int, default=90, help="Days to keep for cleanup")
    
    args = parser.parse_args()
    
    # Get database connection
    db = get_database_manager()
    if not db:
        sys.exit(1)
    
    try:
        # Execute command
        if args.command == "stats":
            show_statistics(db)
        elif args.command == "accounts":
            show_accounts(db)
        elif args.command == "trades":
            show_recent_trades(db, limit=args.limit, worker_name=args.worker)
        elif args.command == "performance":
            show_performance(db, days=args.days, worker_name=args.worker)
        elif args.command == "reset-martingale":
            reset_martingale(db)
        elif args.command == "backup":
            backup_database(db, args.backup_path)
        elif args.command == "cleanup":
            cleanup_old_trades(db, args.cleanup_days)
        elif args.command == "test-data":
            add_test_data(db)
    
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
