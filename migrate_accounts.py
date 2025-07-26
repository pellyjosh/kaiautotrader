#!/usr/bin/env python3
"""
Migration Script for KaiSignalTrade Bot
Migrates hardcoded account configurations to database
"""

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

def migrate_accounts():
    """Migrate hardcoded accounts to database"""
    
    # Your current account configurations
    hardcoded_accounts = [
        {'name': 'pelly_demo', 'ssid': """42["auth",{"session":"bpajv9apd668u8qkcdp4i34vc0","isDemo":1,"uid":104296609,"platform":1,"isFastHistory":true,"isOptimized":true}]""", 'demo': True, 'enabled': True},
        {'name': 'pelly_real30294', 'ssid': """42["auth",{"session":"a:4:{s:10:\\"session_id\\";s:32:\\"2fdde4172af95443a5c227621595c835\\";s:10:\\"ip_address\\";s:14:\\"105.113.62.151\\";s:10:\\"user_agent\\";s:117:\\"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36\\";s:13:\\"last_activity\\";i:1750091525;}e7561b1ef34608df6bc9731d4119ef1c","isDemo":0,"uid":104296609,"platform":1,"isFastHistory":true}]""", 'demo': False, 'enabled': False},
        {'name': 'tonami_demo', 'ssid': """42["auth",{"session":"1620e72bltrkeb5e290f3etbcb","isDemo":1,"uid":34048913,"platform":1,"isFastHistory":true}]""", 'demo': True, 'enabled': False},
        {'name': 'tonami_real', 'ssid': """42["auth",{"session":"a:4:{s:10:\\"session_id\\";s:32:\\"09c3b588878f166204395267d358bfc2\\";s:10:\\"ip_address\\";s:14:\\"105.113.62.151\\";s:10:\\"user_agent\\";s:84:\\"Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:140.0) Gecko/20100101 Firefox/140.0\\";s:13:\\"last_activity\\";i:1750090512;}7abd18c3d9e5f0da2a9b4da0361ee5bd","isDemo":0,"uid":34048913,"platform":1,"isFastHistory":true}]""", 'demo': False, 'enabled': False},
    ]
    
    db = initialize_db()
    if not db:
        return False
    
    print(f"Migrating {len(hardcoded_accounts)} accounts to database...")
    
    success_count = 0
    for account in hardcoded_accounts:
        print(f"  Adding account: {account['name']} (Demo: {account['demo']}, Enabled: {account['enabled']})")
        
        success = db.add_account(
            worker_name=account['name'],
            ssid=account['ssid'],
            is_demo=account['demo'],
            enabled=account['enabled'],
            balance=0.00,
            base_amount=1.00,  # Default base amount
            martingale_multiplier=2.5,  # Default multiplier 
            martingale_enabled=True  # Enable Martingale by default
        )
        
        if success:
            success_count += 1
            print(f"    ✓ Success")
        else:
            print(f"    ✗ Failed")
    
    print(f"\nMigration completed: {success_count}/{len(hardcoded_accounts)} accounts migrated successfully")
    
    # Show current accounts in database
    print("\nCurrent accounts in database:")
    accounts = db.get_all_accounts()
    for account in accounts:
        status = "✓ Enabled" if account['enabled'] else "✗ Disabled"
        demo_status = "Demo" if account['is_demo'] else "Real"
        print(f"  - {account['worker_name']} ({demo_status}) {status}")
    
    return True

def main():
    print("=== KaiSignalTrade Account Migration ===")
    print("This script will migrate your hardcoded account configurations to the database.")
    print("Note: If accounts already exist, they will be updated with new values.")
    print()
    
    confirm = input("Do you want to proceed with migration? (y/N): ").strip().lower()
    if confirm not in ['y', 'yes']:
        print("Migration cancelled.")
        return
    
    if migrate_accounts():
        print("\n✓ Migration completed successfully!")
        print("\nNext steps:")
        print("1. Your bot will now load accounts from the database")
        print("2. Use 'python manage_accounts.py list' to view accounts")
        print("3. Use 'python manage_accounts.py enable <name>' to enable accounts")
        print("4. Use 'python manage_accounts.py disable <name>' to disable accounts")
    else:
        print("\n✗ Migration failed. Please check your database configuration.")

if __name__ == "__main__":
    main()
