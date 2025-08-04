#!/usr/bin/env python3
"""
Create initial admin user for HuboluxTradingBot Web UI
"""

import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from db.database_manager import DatabaseManager
import db.database_config as db_config
from werkzeug.security import generate_password_hash

def create_users_table(db_manager):
    """Create users table if it doesn't exist"""
    
    users_table = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTO_INCREMENT,
        username VARCHAR(50) UNIQUE NOT NULL,
        email VARCHAR(100) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        role ENUM('admin', 'user') DEFAULT 'user',
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP NULL
    )
    """ if db_manager.db_type == "mysql" else """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'user' CHECK (role IN ('admin', 'user')),
        is_active BOOLEAN DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP NULL
    )
    """
    
    db_manager._execute_query(users_table)
    print("✅ Users table created/verified")

def create_admin_user(db_manager):
    """Create default admin user"""
    
    # Check if admin user exists
    query = "SELECT id FROM users WHERE username = %s" if db_manager.db_type == "mysql" else "SELECT id FROM users WHERE username = ?"
    result = db_manager._execute_query(query, ('admin',), fetch="one")
    
    if result:
        print("ℹ️  Admin user already exists")
        return
    
    # Create admin user
    password_hash = generate_password_hash('admin123')
    
    query = """
    INSERT INTO users (username, email, password_hash, role, is_active)
    VALUES (%s, %s, %s, %s, %s)
    """ if db_manager.db_type == "mysql" else """
    INSERT INTO users (username, email, password_hash, role, is_active)
    VALUES (?, ?, ?, ?, ?)
    """
    
    params = ('admin', 'admin@huboluxtrade.com', password_hash, 'admin', True)
    db_manager._execute_query(query, params)
    
    print("✅ Admin user created successfully")
    print("   Username: admin")
    print("   Password: admin123")
    print("   Email: admin@huboluxtrade.com")

def main():
    """Main setup function"""
    print("🔧 Setting up HuboluxTradingBot Web UI...")
    
    try:
        # Connect to database
        if db_config.DATABASE_TYPE.lower() == "mysql":
            db_manager = DatabaseManager(db_type='mysql', **db_config.MYSQL_CONFIG)
            print("✅ Connected to MySQL database")
        else:
            db_manager = DatabaseManager(db_type='sqlite', db_path=db_config.SQLITE_DB_PATH)
            print("✅ Connected to SQLite database")
        
        # Create users table
        create_users_table(db_manager)
        
        # Create admin user
        create_admin_user(db_manager)
        
        print("\n🎉 Setup completed successfully!")
        print("\nYou can now start the web UI with:")
        print("   cd web_ui")
        print("   source venv/bin/activate")
        print("   python run.py")
        print("\nThen visit: http://127.0.0.1:9000")
        
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
