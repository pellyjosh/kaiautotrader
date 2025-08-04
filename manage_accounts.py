#!/usr/bin/env python3
"""
Account Management Utility for HuboluxTradingBot Bot
Allows you to manage PocketOption accounts in the database
"""

import sys
import argparse
from db.database_manager import DatabaseManager
from db.database_config import DATABASE_TYPE, SQLITE_DB_PATH, MYSQL_CONFIG

def initialize_db():
    """Initialize database connection"""
    try:
        if DATABASE_TYPE.lower() == "mysql":
            db = DatabaseManager(db_type="mysql", **MYSQL_CONFIG)
            print("✓ Connected to MySQL database")
        else:
            db = DatabaseManager(db_type="sqlite", db_path=SQLITE_DB_PATH)
            print("✓ Connected to SQLite database")
        return db
    except Exception as e:
        print(f"✗ Failed to connect to database: {e}")
        return None

def list_accounts(db):
    """List all accounts in the database"""
    accounts = db.get_all_accounts()
    if not accounts:
        print("No accounts found in database.")
        return
    
    print(f"\n{'ID':<4} {'Name':<20} {'Demo':<6} {'Enabled':<8} {'Balance':<10} {'Status':<10}")
    print("-" * 70)
    
    for account in accounts:
        demo_str = "Yes" if account['is_demo'] else "No"
        enabled_str = "Yes" if account['enabled'] else "No"
        balance = f"${account['balance']:.2f}"
        
        print(f"{account['id']:<4} {account['worker_name']:<20} {demo_str:<6} {enabled_str:<8} {balance:<10} {account['status']:<10}")

def add_account(db, name, ssid, demo, enabled):
    """Add a new account"""
    is_demo = demo.lower() in ['true', 'yes', '1']
    is_enabled = enabled.lower() in ['true', 'yes', '1']
    
    success = db.add_account(
        worker_name=name,
        ssid=ssid,
        is_demo=is_demo,
        enabled=is_enabled,
        balance=0.00
    )
    
    if success:
        print(f"✓ Account '{name}' added successfully")
    else:
        print(f"✗ Failed to add account '{name}'")

def enable_account(db, name):
    """Enable an account"""
    success = db.update_account_enabled_status(name, True)
    if success:
        print(f"✓ Account '{name}' enabled")
    else:
        print(f"✗ Failed to enable account '{name}' (account may not exist)")

def disable_account(db, name):
    """Disable an account"""
    success = db.update_account_enabled_status(name, False)
    if success:
        print(f"✓ Account '{name}' disabled")
    else:
        print(f"✗ Failed to disable account '{name}' (account may not exist)")

def get_account_details(db, name):
    """Get detailed information about an account"""
    account = db.get_account(name)
    if not account:
        print(f"Account '{name}' not found")
        return
    
    print(f"\nAccount Details for '{name}':")
    print(f"  ID: {account['id']}")
    print(f"  Name: {account['worker_name']}")
    print(f"  Demo Account: {'Yes' if account['is_demo'] else 'No'}")
    print(f"  Enabled: {'Yes' if account['enabled'] else 'No'}")
    print(f"  Balance: ${account['balance']:.2f}")
    print(f"  Status: {account['status']}")
    print(f"  Created: {account['created_at']}")
    print(f"  Last Updated: {account['last_updated']}")
    print(f"  SSID: {account['ssid'][:50]}..." if len(account['ssid']) > 50 else f"  SSID: {account['ssid']}")

def main():
    parser = argparse.ArgumentParser(description="Manage PocketOption accounts in database")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # List accounts
    list_parser = subparsers.add_parser('list', help='List all accounts')
    
    # Add account
    add_parser = subparsers.add_parser('add', help='Add a new account')
    add_parser.add_argument('name', help='Account name/worker name')
    add_parser.add_argument('ssid', help='PocketOption SSID')
    add_parser.add_argument('--demo', choices=['true', 'false'], default='true', help='Is demo account (default: true)')
    add_parser.add_argument('--enabled', choices=['true', 'false'], default='true', help='Is account enabled (default: true)')
    
    # Enable account
    enable_parser = subparsers.add_parser('enable', help='Enable an account')
    enable_parser.add_argument('name', help='Account name to enable')
    
    # Disable account
    disable_parser = subparsers.add_parser('disable', help='Disable an account')
    disable_parser.add_argument('name', help='Account name to disable')
    
    # Get account details
    details_parser = subparsers.add_parser('details', help='Get account details')
    details_parser.add_argument('name', help='Account name to get details for')
    
    # List enabled accounts only
    enabled_parser = subparsers.add_parser('enabled', help='List enabled accounts only')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Initialize database
    db = initialize_db()
    if not db:
        sys.exit(1)
    
    try:
        if args.command == 'list':
            list_accounts(db)
        elif args.command == 'add':
            add_account(db, args.name, args.ssid, args.demo, args.enabled)
        elif args.command == 'enable':
            enable_account(db, args.name)
        elif args.command == 'disable':
            disable_account(db, args.name)
        elif args.command == 'details':
            get_account_details(db, args.name)
        elif args.command == 'enabled':
            enabled_accounts = db.get_enabled_accounts()
            if not enabled_accounts:
                print("No enabled accounts found.")
            else:
                print(f"\nEnabled Accounts ({len(enabled_accounts)}):")
                print(f"{'Name':<20} {'Demo':<6} {'Balance':<10} {'Status':<10}")
                print("-" * 50)
                for account in enabled_accounts:
                    demo_str = "Yes" if account['is_demo'] else "No"
                    balance = f"${account['balance']:.2f}"
                    print(f"{account['worker_name']:<20} {demo_str:<6} {balance:<10} {account['status']:<10}")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
