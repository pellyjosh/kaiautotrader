#!/usr/bin/env python3
"""
Database Migration Utility
Force run migrations and check database schema status
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database_manager import DatabaseManager
import argparse

def check_schema_status(dm: DatabaseManager):
    """Check current database schema status"""
    print("\n" + "="*60)
    print("DATABASE SCHEMA STATUS")
    print("="*60)
    
    try:
        # Check accounts table columns
        if dm.db_type == "mysql":
            query = """
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'accounts'
            ORDER BY ORDINAL_POSITION
            """
            result = dm._execute_query(query, (dm.mysql_config.get('database', ''),), fetch="all")
            columns_info = [(row[0], row[1], row[2], row[3]) for row in result] if result else []
        else:
            query = "PRAGMA table_info(accounts)"
            result = dm._execute_query(query, fetch="all")
            columns_info = [(row[1], row[2], "YES" if not row[3] else "NO", row[4]) for row in result] if result else []
        
        print("\n📋 ACCOUNTS TABLE COLUMNS:")
        if columns_info:
            print(f"{'Column Name':<25} {'Type':<15} {'Nullable':<10} {'Default':<15}")
            print("-" * 70)
            for col_name, col_type, nullable, default in columns_info:
                default_str = str(default) if default is not None else "NULL"
                print(f"{col_name:<25} {col_type:<15} {nullable:<10} {default_str:<15}")
        else:
            print("❌ No accounts table found!")
        
        # Check for required Martingale columns
        required_columns = ['base_amount', 'martingale_multiplier', 'martingale_enabled']
        existing_columns = [col[0] for col in columns_info]
        
        print(f"\n🎯 MARTINGALE SETTINGS STATUS:")
        for req_col in required_columns:
            status = "✅ EXISTS" if req_col in existing_columns else "❌ MISSING"
            print(f"  {req_col:<25} {status}")
        
        # Check martingale_state table
        if dm.db_type == "mysql":
            query = """
            SELECT COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'martingale_state'
            ORDER BY ORDINAL_POSITION
            """
            result = dm._execute_query(query, (dm.mysql_config.get('database', ''),), fetch="all")
            mart_columns = [row[0] for row in result] if result else []
        else:
            query = "PRAGMA table_info(martingale_state)"
            result = dm._execute_query(query, fetch="all")
            mart_columns = [row[1] for row in result] if result else []
        
        print(f"\n🔄 MARTINGALE_STATE TABLE:")
        if mart_columns:
            print(f"  Columns: {', '.join(mart_columns)}")
            required_mart_columns = ['account_name', 'queue_amounts', 'current_multiplier']
            for req_col in required_mart_columns:
                status = "✅ EXISTS" if req_col in mart_columns else "❌ MISSING"
                print(f"  {req_col:<25} {status}")
        else:
            print("  ❌ No martingale_state table found!")
        
        # Check sample account data
        accounts = dm.get_all_accounts()
        print(f"\n👥 ACCOUNTS COUNT: {len(accounts)}")
        
        if accounts:
            print("Sample account with Martingale settings:")
            sample = accounts[0]
            print(f"  Name: {sample.get('worker_name', 'N/A')}")
            print(f"  Base Amount: ${sample.get('base_amount', 'N/A')}")
            print(f"  Multiplier: {sample.get('martingale_multiplier', 'N/A')}x")
            print(f"  Enabled: {sample.get('martingale_enabled', 'N/A')}")
        
    except Exception as e:
        print(f"❌ Error checking schema: {e}")

def force_migration(dm: DatabaseManager):
    """Force run migrations by calling internal methods"""
    print("\n" + "="*60)
    print("FORCING MIGRATION")
    print("="*60)
    
    try:
        print("🔄 Running schema migration check...")
        dm._check_and_migrate_schema()
        
        print("🔄 Running Martingale table migration...")
        dm._migrate_martingale_table()
        
        print("✅ Force migration completed!")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")

def reset_test_data(dm: DatabaseManager):
    """Reset and add test data"""
    print("\n" + "="*60)
    print("RESETTING TEST DATA")
    print("="*60)
    
    try:
        # Clear existing test accounts
        test_accounts = ['conservative_account', 'aggressive_account', 'no_martingale_account', 'martingale_test_account']
        for acc_name in test_accounts:
            # Note: We don't delete accounts to preserve referential integrity
            pass
        
        # Add/update test accounts with different Martingale settings
        test_data = [
            {
                'worker_name': 'conservative_trader',
                'ssid': 'conservative@test.com',
                'is_demo': True,
                'enabled': True,
                'balance': 500.00,
                'base_amount': 1.00,
                'martingale_multiplier': 2.0,
                'martingale_enabled': True
            },
            {
                'worker_name': 'aggressive_trader', 
                'ssid': 'aggressive@test.com',
                'is_demo': True,
                'enabled': True,
                'balance': 2000.00,
                'base_amount': 10.00,
                'martingale_multiplier': 3.0,
                'martingale_enabled': True
            },
            {
                'worker_name': 'fixed_amount_trader',
                'ssid': 'fixed@test.com', 
                'is_demo': False,
                'enabled': True,
                'balance': 1000.00,
                'base_amount': 5.00,
                'martingale_multiplier': 1.0,
                'martingale_enabled': False
            }
        ]
        
        for acc in test_data:
            success = dm.add_account(**acc)
            status = "✅" if success else "❌"
            print(f"  {status} {acc['worker_name']} - Base: ${acc['base_amount']}, Mult: {acc['martingale_multiplier']}x, Enabled: {acc['martingale_enabled']}")
        
        print("✅ Test data reset completed!")
        
    except Exception as e:
        print(f"❌ Test data reset failed: {e}")

def main():
    """Main migration utility"""
    parser = argparse.ArgumentParser(
        description="Database Migration Utility",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument('action', nargs='?', choices=[
        'status', 'migrate', 'force', 'reset-test', 'help'
    ], default='help', help="""Available actions:
  status    - Check current database schema status
  migrate   - Run normal migration (same as creating DatabaseManager)
  force     - Force run all migrations regardless of current state
  reset-test- Reset test account data with Martingale settings
  help      - Show this help message""")
    
    args = parser.parse_args()
    
    if args.action == 'help':
        parser.print_help()
        return
    
    # Initialize database
    try:
        print("🔗 Connecting to database...")
        dm = DatabaseManager()
        print("✅ Connected successfully")
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        return
    
    # Execute action
    try:
        if args.action == 'status':
            check_schema_status(dm)
        
        elif args.action == 'migrate':
            print("🔄 Running standard migration...")
            # Migration already ran during DatabaseManager initialization
            print("✅ Standard migration completed!")
            check_schema_status(dm)
        
        elif args.action == 'force':
            force_migration(dm)
            check_schema_status(dm)
        
        elif args.action == 'reset-test':
            reset_test_data(dm)
            check_schema_status(dm)
        
    except KeyboardInterrupt:
        print("\n\n🛑 Operation cancelled by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        dm.close()

if __name__ == "__main__":
    main()
