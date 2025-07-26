#!/usr/bin/env python3
"""
Database Manager for KaiSignalTrade Bot
Supports both SQLite (local) and MySQL (remote) databases
Tracks trades, Martingale state, and account performance
"""

import sqlite3
try:
    import mysql.connector
    from mysql.connector import Error
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False
    print("[WARNING] MySQL connector not available. Only SQLite will be supported.")
import json
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union
import os
import logging

class DatabaseManager:
    def __init__(self, db_type=None, **kwargs):
        """
        Initialize database manager
        
        Args:
            db_type: "sqlite" or "mysql" (if None, reads from database_config.py)
            **kwargs: Database connection parameters (overrides config file values)
                For SQLite: db_path (optional, defaults to 'trades.db')
                For MySQL: host, user, password, database, port (optional)
        """
        self.connection = None
        self.logger = logging.getLogger(__name__)
        
        # Load configuration from database_config.py if not specified
        if db_type is None or not kwargs:
            try:
                from .database_config import DATABASE_TYPE, MYSQL_CONFIG, SQLITE_DB_PATH
                
                if db_type is None:
                    db_type = DATABASE_TYPE
                
                # Load MySQL config if using MySQL and no kwargs provided
                if db_type.lower() == "mysql" and not kwargs:
                    kwargs = MYSQL_CONFIG.copy()
                elif db_type.lower() == "sqlite" and 'db_path' not in kwargs:
                    kwargs['db_path'] = SQLITE_DB_PATH
                    
                self.logger.info(f"Loaded database configuration: {db_type}")
                
            except ImportError as e:
                self.logger.warning(f"Could not load database_config.py: {e}. Using defaults.")
                if db_type is None:
                    db_type = "sqlite"
        
        self.db_type = db_type.lower()
        
        if self.db_type == "sqlite":
            self.db_path = kwargs.get('db_path', 'trades.db')
            self._init_sqlite()
        elif self.db_type == "mysql":
            if not MYSQL_AVAILABLE:
                raise ValueError("MySQL connector not available. Please install mysql-connector-python or use SQLite.")
            self.mysql_config = {
                'host': kwargs.get('host', 'localhost'),
                'user': kwargs.get('user'),
                'password': kwargs.get('password'),
                'database': kwargs.get('database'),
                'port': kwargs.get('port', 3306),
                'autocommit': True
            }
            self._init_mysql()
        else:
            raise ValueError("db_type must be 'sqlite' or 'mysql'")
        
        self._create_tables()
    
    def _init_sqlite(self):
        """Initialize SQLite connection with optimized settings for concurrent access"""
        try:
            self.connection = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
            self.connection.execute("PRAGMA foreign_keys = ON")
            # Enable WAL mode for better concurrent access
            self.connection.execute("PRAGMA journal_mode = WAL")
            # Set busy timeout to handle concurrent access
            self.connection.execute("PRAGMA busy_timeout = 30000")  # 30 seconds
            # Optimize for concurrent operations
            self.connection.execute("PRAGMA synchronous = NORMAL")
            self.connection.execute("PRAGMA cache_size = 1000")
            self.connection.execute("PRAGMA temp_store = memory")
            self.logger.info(f"SQLite database connected with WAL mode: {self.db_path}")
        except Exception as e:
            self.logger.error(f"SQLite connection failed: {e}")
            raise
    
    def _init_mysql(self):
        """Initialize MySQL connection"""
        try:
            # Add buffered=True to avoid "Unread result found" errors
            self.mysql_config['buffered'] = True
            self.connection = mysql.connector.connect(**self.mysql_config)
            self.logger.info(f"MySQL database connected: {self.mysql_config['host']}")
        except Error as e:
            self.logger.error(f"MySQL connection failed: {e}")
            raise
    
    def _execute_query(self, query: str, params: tuple = None, fetch: str = None):
        """Execute database query with error handling and retry logic for locked database"""
        max_retries = 5
        retry_delay = 0.1  # 100ms initial delay
        
        for attempt in range(max_retries):
            cursor = None
            try:
                # For MySQL, use buffered cursor to avoid "Unread result found" errors
                if self.db_type == "mysql":
                    cursor = self.connection.cursor(buffered=True)
                else:
                    cursor = self.connection.cursor()
                    
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                
                if fetch == "one":
                    result = cursor.fetchone()
                elif fetch == "all":
                    result = cursor.fetchall()
                else:
                    result = cursor.rowcount
                
                # For MySQL, consume all results to avoid "Unread result found" error
                if self.db_type == "mysql" and cursor.with_rows:
                    cursor.fetchall()  # Consume any remaining results
                
                if self.db_type == "sqlite":
                    self.connection.commit()
                
                return result
                
            except sqlite3.OperationalError as e:
                error_msg = str(e).lower()
                if ("database is locked" in error_msg or "database is busy" in error_msg) and attempt < max_retries - 1:
                    if cursor:
                        try:
                            cursor.close()
                        except:
                            pass
                    
                    self.logger.warning(f"Database locked/busy, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, 2.0)  # Exponential backoff up to 2 seconds
                    continue
                else:
                    self.logger.error(f"Database query failed: {query} | Error: {e}")
                    raise
            except Exception as e:
                self.logger.error(f"Database query failed: {query} | Error: {e}")
                raise
            finally:
                if cursor:
                    try:
                        cursor.close()
                    except:
                        pass
        
        # If we get here, all retries failed
        raise sqlite3.OperationalError(f"Database operation failed after {max_retries} attempts")
    
    def _create_tables(self):
        """Create all required tables"""
        
        # Accounts table - track connected PocketOption accounts
        accounts_table = """
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            worker_name VARCHAR(100) UNIQUE NOT NULL,
            ssid TEXT NOT NULL,
            is_demo BOOLEAN NOT NULL,
            enabled BOOLEAN DEFAULT TRUE,
            balance DECIMAL(10,2) DEFAULT 0.00,
            base_amount DECIMAL(10,2) DEFAULT 1.00,
            martingale_multiplier DECIMAL(5,2) DEFAULT 2.00,
            martingale_enabled BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            status ENUM('active', 'inactive', 'error') DEFAULT 'active'
        )
        """ if self.db_type == "mysql" else """
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_name TEXT UNIQUE NOT NULL,
            ssid TEXT NOT NULL,
            is_demo BOOLEAN NOT NULL,
            enabled BOOLEAN DEFAULT 1,
            balance REAL DEFAULT 0.00,
            base_amount REAL DEFAULT 1.00,
            martingale_multiplier REAL DEFAULT 2.00,
            martingale_enabled BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'error'))
        )
        """
        
        # Trades table - track all executed trades
        trades_table = """
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            trade_id VARCHAR(255) UNIQUE NOT NULL,
            worker_name VARCHAR(100) NOT NULL,
            symbol VARCHAR(50) NOT NULL,
            direction ENUM('call', 'put') NOT NULL,
            amount DECIMAL(10,2) NOT NULL,
            expiration_duration INTEGER NOT NULL,
            entry_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expiration_time TIMESTAMP,
            result ENUM('win', 'loss', 'pending', 'cancelled') DEFAULT 'pending',
            payout DECIMAL(10,2) DEFAULT 0.00,
            martingale_level INTEGER DEFAULT 0,
            is_martingale_trade BOOLEAN DEFAULT FALSE,
            signal_source VARCHAR(100),
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (worker_name) REFERENCES accounts(worker_name) ON DELETE CASCADE
        )
        """ if self.db_type == "mysql" else """
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id TEXT UNIQUE NOT NULL,
            worker_name TEXT NOT NULL,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('call', 'put')),
            amount REAL NOT NULL,
            expiration_duration INTEGER NOT NULL,
            entry_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expiration_time TIMESTAMP,
            result TEXT DEFAULT 'pending' CHECK (result IN ('win', 'loss', 'pending', 'cancelled')),
            payout REAL DEFAULT 0.00,
            martingale_level INTEGER DEFAULT 0,
            is_martingale_trade BOOLEAN DEFAULT FALSE,
            signal_source TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (worker_name) REFERENCES accounts(worker_name) ON DELETE CASCADE
        )
        """
        
        # Martingale state table - persist Martingale memory per account
        martingale_state_table = """
        CREATE TABLE IF NOT EXISTS martingale_state (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            account_name VARCHAR(100) UNIQUE NOT NULL,
            consecutive_losses INTEGER DEFAULT 0,
            last_trade_id VARCHAR(255),
            last_trade_result ENUM('win', 'loss', 'pending') DEFAULT 'pending',
            current_multiplier DECIMAL(5,2) DEFAULT 1.00,
            base_amount DECIMAL(10,2) DEFAULT 1.00,
            queue_amounts TEXT,
            max_consecutive_losses INTEGER DEFAULT 0,
            total_sequences INTEGER DEFAULT 0,
            last_reset_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (account_name) REFERENCES accounts(worker_name) ON DELETE CASCADE
        )
        """ if self.db_type == "mysql" else """
        CREATE TABLE IF NOT EXISTS martingale_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_name TEXT UNIQUE NOT NULL,
            consecutive_losses INTEGER DEFAULT 0,
            last_trade_id TEXT,
            last_trade_result TEXT DEFAULT 'pending' CHECK (last_trade_result IN ('win', 'loss', 'pending')),
            current_multiplier REAL DEFAULT 1.00,
            base_amount REAL DEFAULT 1.00,
            queue_amounts TEXT DEFAULT '[]',
            max_consecutive_losses INTEGER DEFAULT 0,
            total_sequences INTEGER DEFAULT 0,
            last_reset_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_name) REFERENCES accounts(worker_name) ON DELETE CASCADE
        )
        """
        
        # Performance tracking table
        performance_table = """
        CREATE TABLE IF NOT EXISTS performance (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            worker_name VARCHAR(100) NOT NULL,
            date DATE NOT NULL,
            total_trades INTEGER DEFAULT 0,
            winning_trades INTEGER DEFAULT 0,
            losing_trades INTEGER DEFAULT 0,
            total_invested DECIMAL(10,2) DEFAULT 0.00,
            total_payout DECIMAL(10,2) DEFAULT 0.00,
            net_profit DECIMAL(10,2) DEFAULT 0.00,
            win_rate DECIMAL(5,2) DEFAULT 0.00,
            martingale_recoveries INTEGER DEFAULT 0,
            max_consecutive_losses INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY unique_worker_date (worker_name, date),
            FOREIGN KEY (worker_name) REFERENCES accounts(worker_name) ON DELETE CASCADE
        )
        """ if self.db_type == "mysql" else """
        CREATE TABLE IF NOT EXISTS performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_name TEXT NOT NULL,
            date DATE NOT NULL,
            total_trades INTEGER DEFAULT 0,
            winning_trades INTEGER DEFAULT 0,
            losing_trades INTEGER DEFAULT 0,
            total_invested REAL DEFAULT 0.00,
            total_payout REAL DEFAULT 0.00,
            net_profit REAL DEFAULT 0.00,
            win_rate REAL DEFAULT 0.00,
            martingale_recoveries INTEGER DEFAULT 0,
            max_consecutive_losses INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (worker_name, date),
            FOREIGN KEY (worker_name) REFERENCES accounts(worker_name) ON DELETE CASCADE
        )
        """
        
        # Enhanced Martingale lanes table for smart concurrent trading
        martingale_lanes_table = """
        CREATE TABLE IF NOT EXISTS martingale_lanes (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            lane_id VARCHAR(100) UNIQUE NOT NULL,
            account_name VARCHAR(100) NOT NULL,
            symbol VARCHAR(50) NOT NULL,
            status ENUM('active', 'completed', 'cancelled') DEFAULT 'active',
            current_level INTEGER DEFAULT 1,
            base_amount DECIMAL(10,2) NOT NULL,
            current_amount DECIMAL(10,2) NOT NULL,
            multiplier DECIMAL(5,2) NOT NULL,
            max_level INTEGER DEFAULT 7,
            total_invested DECIMAL(10,2) DEFAULT 0.00,
            total_potential_payout DECIMAL(10,2) DEFAULT 0.00,
            trade_ids TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            completed_at TIMESTAMP NULL,
            FOREIGN KEY (account_name) REFERENCES accounts(worker_name) ON DELETE CASCADE,
            INDEX idx_account_status (account_name, status),
            INDEX idx_lane_status (lane_id, status)
        )
        """ if self.db_type == "mysql" else """
        CREATE TABLE IF NOT EXISTS martingale_lanes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lane_id TEXT UNIQUE NOT NULL,
            account_name TEXT NOT NULL,
            symbol TEXT NOT NULL,
            status TEXT DEFAULT 'active' CHECK (status IN ('active', 'completed', 'cancelled')),
            current_level INTEGER DEFAULT 1,
            base_amount REAL NOT NULL,
            current_amount REAL NOT NULL,
            multiplier REAL NOT NULL,
            max_level INTEGER DEFAULT 7,
            total_invested REAL DEFAULT 0.00,
            total_potential_payout REAL DEFAULT 0.00,
            trade_ids TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP NULL,
            FOREIGN KEY (account_name) REFERENCES accounts(worker_name) ON DELETE CASCADE
        )
        """

        # Trading settings table for concurrency control and other settings
        trading_settings_table = """
        CREATE TABLE IF NOT EXISTS trading_settings (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            account_name VARCHAR(100) UNIQUE NOT NULL,
            concurrent_trading_enabled BOOLEAN DEFAULT FALSE,
            max_concurrent_lanes INTEGER DEFAULT 3,
            lane_assignment_strategy ENUM('fifo', 'round_robin', 'symbol_priority') DEFAULT 'fifo',
            auto_create_lanes BOOLEAN DEFAULT TRUE,
            cool_down_seconds INTEGER DEFAULT 0,
            max_daily_lanes INTEGER DEFAULT 10,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (account_name) REFERENCES accounts(worker_name) ON DELETE CASCADE
        )
        """ if self.db_type == "mysql" else """
        CREATE TABLE IF NOT EXISTS trading_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_name TEXT UNIQUE NOT NULL,
            concurrent_trading_enabled BOOLEAN DEFAULT 0,
            max_concurrent_lanes INTEGER DEFAULT 3,
            lane_assignment_strategy TEXT DEFAULT 'fifo' CHECK (lane_assignment_strategy IN ('fifo', 'round_robin', 'symbol_priority')),
            auto_create_lanes BOOLEAN DEFAULT 1,
            cool_down_seconds INTEGER DEFAULT 0,
            max_daily_lanes INTEGER DEFAULT 10,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_name) REFERENCES accounts(worker_name) ON DELETE CASCADE
        )
        """

        # Execute table creation
        self._execute_query(accounts_table)
        self._execute_query(trades_table)
        self._execute_query(martingale_state_table)
        self._execute_query(performance_table)
        self._execute_query(martingale_lanes_table)
        self._execute_query(trading_settings_table)
        
        # Check and migrate existing schema if needed
        self._check_and_migrate_schema()
        
        # Initialize Martingale state if not exists
        self._initialize_martingale_state()
        
        # Initialize default trading settings for existing accounts
        self._initialize_trading_settings()
        
        self.logger.info("Database tables created successfully")
    
    def _initialize_martingale_state(self):
        """Initialize Martingale state table - per-account states will be created as needed"""
        # No longer creating a global state since we use per-account states
        # Account-specific states will be initialized when accounts are first used
        self.logger.info("Martingale state table ready for per-account states")
    
    def _initialize_trading_settings(self):
        """Initialize default trading settings for all existing accounts"""
        try:
            # Get all accounts
            accounts = self.get_all_accounts()
            
            for account in accounts:
                account_name = account['worker_name']
                
                # Check if trading settings already exist
                query = "SELECT id FROM trading_settings WHERE account_name = ?" if self.db_type == "sqlite" else "SELECT id FROM trading_settings WHERE account_name = %s"
                existing = self._execute_query(query, (account_name,), fetch="one")
                
                if not existing:
                    # Create default trading settings
                    if self.db_type == "mysql":
                        insert_query = """
                        INSERT INTO trading_settings (account_name, concurrent_trading_enabled, max_concurrent_lanes, 
                                                    lane_assignment_strategy, auto_create_lanes, cool_down_seconds, max_daily_lanes)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """
                    else:
                        insert_query = """
                        INSERT INTO trading_settings (account_name, concurrent_trading_enabled, max_concurrent_lanes, 
                                                    lane_assignment_strategy, auto_create_lanes, cool_down_seconds, max_daily_lanes)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """
                    
                    # Default settings: concurrent trading disabled, conservative settings
                    default_params = (account_name, False, 3, 'fifo', True, 0, 10)
                    self._execute_query(insert_query, default_params)
                    self.logger.info(f"Initialized default trading settings for account: {account_name}")
            
            if self.db_type == "mysql":
                self.connection.commit()
                
        except Exception as e:
            self.logger.error(f"Failed to initialize trading settings: {e}")
    
    
    def _check_and_migrate_schema(self):
        """Check if schema needs migration and apply updates"""
        try:
            # Check if 'enabled' column exists in accounts table
            if self.db_type == "mysql":
                query = """
                SELECT COLUMN_NAME 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'accounts' AND COLUMN_NAME = 'enabled'
                """
                result = self._execute_query(query, (self.mysql_config.get('database', ''),), fetch="one")
            else:
                # For SQLite, check table info
                query = "PRAGMA table_info(accounts)"
                columns = self._execute_query(query, fetch="all")
                result = any(col[1] == 'enabled' for col in columns) if columns else False
            
            if not result:
                self.logger.info("Migrating accounts table: Adding 'enabled' column")
                
                # Add enabled column with default value TRUE
                if self.db_type == "mysql":
                    migrate_query = "ALTER TABLE accounts ADD COLUMN enabled BOOLEAN DEFAULT TRUE"
                else:
                    migrate_query = "ALTER TABLE accounts ADD COLUMN enabled BOOLEAN DEFAULT 1"
                
                self._execute_query(migrate_query)
                self.logger.info("Successfully added 'enabled' column to accounts table")
            
            # Check if 'base_amount' column exists in accounts table
            if self.db_type == "mysql":
                query = """
                SELECT COLUMN_NAME 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'accounts' AND COLUMN_NAME = 'base_amount'
                """
                result = self._execute_query(query, (self.mysql_config.get('database', ''),), fetch="one")
            else:
                # For SQLite, check table info
                query = "PRAGMA table_info(accounts)"
                columns = self._execute_query(query, fetch="all")
                result = any(col[1] == 'base_amount' for col in columns) if columns else False
            
            if not result:
                self.logger.info("Migrating accounts table: Adding 'base_amount' column")
                
                if self.db_type == "mysql":
                    migrate_query = "ALTER TABLE accounts ADD COLUMN base_amount DECIMAL(10,2) DEFAULT 1.00"
                else:
                    migrate_query = "ALTER TABLE accounts ADD COLUMN base_amount REAL DEFAULT 1.00"
                
                self._execute_query(migrate_query)
                self.logger.info("Successfully added 'base_amount' column to accounts table")
            
            # Check if 'martingale_multiplier' column exists in accounts table
            if self.db_type == "mysql":
                query = """
                SELECT COLUMN_NAME 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'accounts' AND COLUMN_NAME = 'martingale_multiplier'
                """
                result = self._execute_query(query, (self.mysql_config.get('database', ''),), fetch="one")
            else:
                # For SQLite, check table info
                query = "PRAGMA table_info(accounts)"
                columns = self._execute_query(query, fetch="all")
                result = any(col[1] == 'martingale_multiplier' for col in columns) if columns else False
            
            if not result:
                self.logger.info("Migrating accounts table: Adding 'martingale_multiplier' column")
                
                if self.db_type == "mysql":
                    migrate_query = "ALTER TABLE accounts ADD COLUMN martingale_multiplier DECIMAL(5,2) DEFAULT 2.00"
                else:
                    migrate_query = "ALTER TABLE accounts ADD COLUMN martingale_multiplier REAL DEFAULT 2.00"
                
                self._execute_query(migrate_query)
                self.logger.info("Successfully added 'martingale_multiplier' column to accounts table")
            
            # Check if 'martingale_enabled' column exists in accounts table
            if self.db_type == "mysql":
                query = """
                SELECT COLUMN_NAME 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'accounts' AND COLUMN_NAME = 'martingale_enabled'
                """
                result = self._execute_query(query, (self.mysql_config.get('database', ''),), fetch="one")
            else:
                # For SQLite, check table info
                query = "PRAGMA table_info(accounts)"
                columns = self._execute_query(query, fetch="all")
                result = any(col[1] == 'martingale_enabled' for col in columns) if columns else False
            
            if not result:
                self.logger.info("Migrating accounts table: Adding 'martingale_enabled' column")
                
                if self.db_type == "mysql":
                    migrate_query = "ALTER TABLE accounts ADD COLUMN martingale_enabled BOOLEAN DEFAULT TRUE"
                else:
                    migrate_query = "ALTER TABLE accounts ADD COLUMN martingale_enabled BOOLEAN DEFAULT 1"
                
                self._execute_query(migrate_query)
                self.logger.info("Successfully added 'martingale_enabled' column to accounts table")
            
            # Check and migrate martingale_state table
            self._migrate_martingale_table()
                
        except Exception as e:
            self.logger.warning(f"Schema migration check failed (this is normal for new installations): {e}")
    
    def _migrate_martingale_table(self):
        """Migrate martingale_state table to include missing columns"""
        try:
            # Check if martingale_state table exists and get its columns
            if self.db_type == "mysql":
                query = """
                SELECT COLUMN_NAME 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'martingale_state'
                ORDER BY ORDINAL_POSITION
                """
                result = self._execute_query(query, (self.mysql_config.get('database', ''),), fetch="all")
                existing_columns = [row[0] for row in result] if result else []
            else:
                query = "PRAGMA table_info(martingale_state)"
                result = self._execute_query(query, fetch="all")
                existing_columns = [col[1] for col in result] if result else []
            
            # Required columns for the new schema
            required_columns = {
                'account_name': 'VARCHAR(100) UNIQUE' if self.db_type == "mysql" else 'TEXT UNIQUE',
                'current_multiplier': 'DECIMAL(5,2) DEFAULT 1.00' if self.db_type == "mysql" else 'REAL DEFAULT 1.00',
                'queue_amounts': 'TEXT' if self.db_type == "mysql" else 'TEXT DEFAULT "[]"',
                'max_consecutive_losses': 'INTEGER DEFAULT 0',
                'total_sequences': 'INTEGER DEFAULT 0',
                'last_reset_time': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
            }
            
            # Add missing columns
            for column_name, column_def in required_columns.items():
                if column_name not in existing_columns:
                    self.logger.info(f"Adding missing column '{column_name}' to martingale_state table")
                    alter_query = f"ALTER TABLE martingale_state ADD COLUMN {column_name} {column_def}"
                    self._execute_query(alter_query)
            
            # If account_name doesn't exist but we have old data, we might need to populate it
            if 'account_name' not in existing_columns:
                self.logger.info("Migrating old martingale_state data - clearing old entries")
                # Clear old data that doesn't have account_name
                self._execute_query("DELETE FROM martingale_state WHERE account_name IS NULL OR account_name = ''")
            
            self.logger.info("Martingale table migration completed")
            
        except Exception as e:
            self.logger.warning(f"Martingale table migration failed: {e}")
    
    # === ACCOUNT MANAGEMENT ===
    
    def add_account(self, worker_name: str, ssid: str, is_demo: bool, enabled: bool = True, 
                   balance: float = 0.00, base_amount: float = 1.00, martingale_multiplier: float = 2.00, 
                   martingale_enabled: bool = True) -> bool:
        """Add or update a PocketOption account"""
        try:
            query = """
            INSERT INTO accounts (worker_name, ssid, is_demo, enabled, balance, base_amount, 
                                martingale_multiplier, martingale_enabled, last_updated)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                ssid = VALUES(ssid),
                is_demo = VALUES(is_demo),
                enabled = VALUES(enabled),
                balance = VALUES(balance),
                base_amount = VALUES(base_amount),
                martingale_multiplier = VALUES(martingale_multiplier),
                martingale_enabled = VALUES(martingale_enabled),
                last_updated = VALUES(last_updated),
                status = 'active'
            """ if self.db_type == "mysql" else """
            INSERT OR REPLACE INTO accounts (worker_name, ssid, is_demo, enabled, balance, 
                                          base_amount, martingale_multiplier, martingale_enabled, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            current_time = datetime.now()
            
            # Convert boolean values to integers for MySQL compatibility
            if self.db_type == "mysql":
                is_demo_val = int(is_demo)
                enabled_val = int(enabled) 
                martingale_enabled_val = int(martingale_enabled)
            else:
                is_demo_val = is_demo
                enabled_val = enabled
                martingale_enabled_val = martingale_enabled
            
            params = (worker_name, ssid, is_demo_val, enabled_val, balance, base_amount, 
                     martingale_multiplier, martingale_enabled_val, current_time)
            self._execute_query(query, params)
            
            self.logger.info(f"Account added/updated: {worker_name} (Demo: {is_demo}, Enabled: {enabled}, "
                            f"Base: ${base_amount}, Multiplier: {martingale_multiplier}x, Martingale: {martingale_enabled})")
            return True
        except Exception as e:
            self.logger.error(f"Failed to add account {worker_name}: {e}")
            return False
    
    def update_account_balance(self, worker_name: str, balance: float) -> bool:
        """Update account balance"""
        try:
            query = """
            UPDATE accounts 
            SET balance = %s, last_updated = %s 
            WHERE worker_name = %s
            """ if self.db_type == "mysql" else """
            UPDATE accounts 
            SET balance = ?, last_updated = ? 
            WHERE worker_name = ?
            """
            
            current_time = datetime.now()
            params = (balance, current_time, worker_name)
            rows_affected = self._execute_query(query, params)
            
            if rows_affected > 0:
                self.logger.debug(f"Balance updated for {worker_name}: ${balance}")
                return True
            else:
                self.logger.warning(f"Account not found for balance update: {worker_name}")
                return False
        except Exception as e:
            self.logger.error(f"Failed to update balance for {worker_name}: {e}")
            return False
    
    def get_account(self, worker_name: str) -> Optional[Dict]:
        """Get account information"""
        try:
            query = "SELECT * FROM accounts WHERE worker_name = %s" if self.db_type == "mysql" else "SELECT * FROM accounts WHERE worker_name = ?"
            result = self._execute_query(query, (worker_name,), fetch="one")
            
            if result:
                columns = ['id', 'worker_name', 'ssid', 'is_demo', 'enabled', 'balance', 
                          'base_amount', 'martingale_multiplier', 'martingale_enabled', 
                          'created_at', 'last_updated', 'status']
                return dict(zip(columns, result))
            return None
        except Exception as e:
            self.logger.error(f"Failed to get account {worker_name}: {e}")
            return None
    
    def get_all_accounts(self) -> List[Dict]:
        """Get all accounts"""
        try:
            query = "SELECT * FROM accounts ORDER BY worker_name"
            results = self._execute_query(query, fetch="all")
            
            columns = ['id', 'worker_name', 'ssid', 'is_demo', 'enabled', 'balance', 
                      'base_amount', 'martingale_multiplier', 'martingale_enabled', 
                      'created_at', 'last_updated', 'status']
            return [dict(zip(columns, row)) for row in results]
        except Exception as e:
            self.logger.error(f"Failed to get all accounts: {e}")
            return []
    
    def get_enabled_accounts(self) -> List[Dict]:
        """Get all enabled accounts"""
        try:
            query = "SELECT * FROM accounts WHERE enabled = %s ORDER BY worker_name" if self.db_type == "mysql" else "SELECT * FROM accounts WHERE enabled = 1 ORDER BY worker_name"
            params = (True,) if self.db_type == "mysql" else ()
            results = self._execute_query(query, params, fetch="all")
            
            columns = ['id', 'worker_name', 'ssid', 'is_demo', 'enabled', 'balance', 
                      'base_amount', 'martingale_multiplier', 'martingale_enabled', 
                      'created_at', 'last_updated', 'status']
            return [dict(zip(columns, row)) for row in results]
        except Exception as e:
            self.logger.error(f"Failed to get enabled accounts: {e}")
            return []
    
    def update_account_enabled_status(self, worker_name: str, enabled: bool) -> bool:
        """Update account enabled status"""
        try:
            query = """
            UPDATE accounts 
            SET enabled = %s, last_updated = %s 
            WHERE worker_name = %s
            """ if self.db_type == "mysql" else """
            UPDATE accounts 
            SET enabled = ?, last_updated = ? 
            WHERE worker_name = ?
            """
            
            current_time = datetime.now()
            # Convert boolean to integer for MySQL compatibility
            enabled_val = int(enabled) if self.db_type == "mysql" else enabled
            params = (enabled_val, current_time, worker_name)
            rows_affected = self._execute_query(query, params)
            
            if rows_affected > 0:
                self.logger.info(f"Account {worker_name} enabled status updated to: {enabled}")
                return True
            else:
                self.logger.warning(f"Account not found for enabled status update: {worker_name}")
                return False
        except Exception as e:
            self.logger.error(f"Failed to update enabled status for {worker_name}: {e}")
            return False
    
    def update_account_martingale_settings(self, worker_name: str, base_amount: float = None, 
                                         martingale_multiplier: float = None, 
                                         martingale_enabled: bool = None) -> bool:
        """Update account Martingale settings"""
        try:
            # Build dynamic query based on provided parameters
            updates = []
            params = []
            
            if base_amount is not None:
                updates.append("base_amount = %s" if self.db_type == "mysql" else "base_amount = ?")
                params.append(base_amount)
            
            if martingale_multiplier is not None:
                updates.append("martingale_multiplier = %s" if self.db_type == "mysql" else "martingale_multiplier = ?")
                params.append(martingale_multiplier)
            
            if martingale_enabled is not None:
                updates.append("martingale_enabled = %s" if self.db_type == "mysql" else "martingale_enabled = ?")
                # Convert boolean to integer for MySQL compatibility
                martingale_enabled_val = int(martingale_enabled) if self.db_type == "mysql" else martingale_enabled
                params.append(martingale_enabled_val)
            
            if not updates:
                self.logger.warning("No Martingale settings provided to update")
                return False
            
            # Add timestamp and worker_name to params
            updates.append("last_updated = %s" if self.db_type == "mysql" else "last_updated = ?")
            params.extend([datetime.now(), worker_name])
            
            query = f"""
            UPDATE accounts 
            SET {', '.join(updates)}
            WHERE worker_name = %s
            """ if self.db_type == "mysql" else f"""
            UPDATE accounts 
            SET {', '.join(updates)}
            WHERE worker_name = ?
            """
            
            rows_affected = self._execute_query(query, tuple(params))
            
            if rows_affected > 0:
                settings_info = []
                if base_amount is not None:
                    settings_info.append(f"Base: ${base_amount}")
                if martingale_multiplier is not None:
                    settings_info.append(f"Multiplier: {martingale_multiplier}x")
                if martingale_enabled is not None:
                    settings_info.append(f"Enabled: {martingale_enabled}")
                
                self.logger.info(f"Martingale settings updated for {worker_name}: {', '.join(settings_info)}")
                return True
            else:
                self.logger.warning(f"Account not found for Martingale settings update: {worker_name}")
                return False
        except Exception as e:
            self.logger.error(f"Failed to update Martingale settings for {worker_name}: {e}")
            return False
    
    def get_account_martingale_settings(self, worker_name: str) -> Optional[Dict]:
        """Get account Martingale settings"""
        try:
            query = """
            SELECT base_amount, martingale_multiplier, martingale_enabled 
            FROM accounts WHERE worker_name = %s
            """ if self.db_type == "mysql" else """
            SELECT base_amount, martingale_multiplier, martingale_enabled 
            FROM accounts WHERE worker_name = ?
            """
            result = self._execute_query(query, (worker_name,), fetch="one")
            
            if result:
                base_amount, martingale_multiplier, martingale_enabled = result
                return {
                    'base_amount': float(base_amount) if base_amount else 1.00,
                    'martingale_multiplier': float(martingale_multiplier) if martingale_multiplier else 2.00,
                    'martingale_enabled': bool(martingale_enabled) if martingale_enabled is not None else True
                }
            return None
        except Exception as e:
            self.logger.error(f"Failed to get Martingale settings for {worker_name}: {e}")
            return None
    
    # === TRADE MANAGEMENT ===
    
    def add_trade(self, trade_id: str, worker_name: str, symbol: str, direction: str, 
                  amount: float, expiration_duration: int, expiration_time: datetime = None,
                  martingale_level: int = 0, is_martingale_trade: bool = False,
                  signal_source: str = None) -> bool:
        """Add a new trade record"""
        try:
            if not expiration_time:
                expiration_time = datetime.now() + timedelta(seconds=expiration_duration)
            
            query = """
            INSERT INTO trades (trade_id, worker_name, symbol, direction, amount, 
                              expiration_duration, expiration_time, martingale_level, 
                              is_martingale_trade, signal_source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """ if self.db_type == "mysql" else """
            INSERT INTO trades (trade_id, worker_name, symbol, direction, amount, 
                              expiration_duration, expiration_time, martingale_level, 
                              is_martingale_trade, signal_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            params = (trade_id, worker_name, symbol, direction, amount, 
                     expiration_duration, expiration_time, martingale_level, 
                     is_martingale_trade, signal_source)
            self._execute_query(query, params)
            
            self.logger.info(f"Trade added: {trade_id} | {symbol} | {direction} | ${amount}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to add trade {trade_id}: {e}")
            return False
    
    def update_trade_result(self, trade_id: str, result: str, payout: float = 0.00) -> bool:
        """Update trade result (win/loss) and payout"""
        try:
            query = """
            UPDATE trades 
            SET result = %s, payout = %s, updated_at = %s 
            WHERE trade_id = %s
            """ if self.db_type == "mysql" else """
            UPDATE trades 
            SET result = ?, payout = ?, updated_at = ? 
            WHERE trade_id = ?
            """
            
            current_time = datetime.now()
            params = (result, payout, current_time, trade_id)
            rows_affected = self._execute_query(query, params)
            
            if rows_affected > 0:
                self.logger.info(f"Trade result updated: {trade_id} | {result} | ${payout}")
                return True
            else:
                self.logger.warning(f"Trade not found for result update: {trade_id}")
                return False
        except Exception as e:
            self.logger.error(f"Failed to update trade result {trade_id}: {e}")
            return False
    
    def get_trade(self, trade_id: str) -> Optional[Dict]:
        """Get trade information"""
        try:
            query = "SELECT * FROM trades WHERE trade_id = %s" if self.db_type == "mysql" else "SELECT * FROM trades WHERE trade_id = ?"
            result = self._execute_query(query, (trade_id,), fetch="one")
            
            if result:
                columns = ['id', 'trade_id', 'worker_name', 'symbol', 'direction', 'amount', 
                          'expiration_duration', 'entry_time', 'expiration_time', 'result', 
                          'payout', 'martingale_level', 'is_martingale_trade', 'signal_source', 
                          'notes', 'created_at', 'updated_at']
                return dict(zip(columns, result))
            return None
        except Exception as e:
            self.logger.error(f"Failed to get trade {trade_id}: {e}")
            return None
    
    def get_recent_trades(self, limit: int = 10, worker_name: str = None) -> List[Dict]:
        """Get recent trades"""
        try:
            if worker_name:
                query = """
                SELECT * FROM trades 
                WHERE worker_name = %s 
                ORDER BY entry_time DESC 
                LIMIT %s
                """ if self.db_type == "mysql" else """
                SELECT * FROM trades 
                WHERE worker_name = ? 
                ORDER BY entry_time DESC 
                LIMIT ?
                """
                params = (worker_name, limit)
            else:
                query = """
                SELECT * FROM trades 
                ORDER BY entry_time DESC 
                LIMIT %s
                """ if self.db_type == "mysql" else """
                SELECT * FROM trades 
                ORDER BY entry_time DESC 
                LIMIT ?
                """
                params = (limit,)
            
            results = self._execute_query(query, params, fetch="all")
            
            columns = ['id', 'trade_id', 'worker_name', 'symbol', 'direction', 'amount', 
                      'expiration_duration', 'entry_time', 'expiration_time', 'result', 
                      'payout', 'martingale_level', 'is_martingale_trade', 'signal_source', 
                      'notes', 'created_at', 'updated_at']
            return [dict(zip(columns, row)) for row in results]
        except Exception as e:
            self.logger.error(f"Failed to get recent trades: {e}")
            return []
    
    # === MARTINGALE STATE MANAGEMENT ===
    
    def get_martingale_state(self) -> Dict:
        """Get current Martingale state"""
        try:
            query = "SELECT * FROM martingale_state ORDER BY id DESC LIMIT 1"
            result = self._execute_query(query, fetch="one")
            
            if result:
                columns = ['id', 'consecutive_losses', 'last_trade_id', 'last_trade_result',
                          'current_multiplier', 'base_amount', 'max_consecutive_losses',
                          'total_sequences', 'last_reset_time', 'created_at', 'updated_at']
                return dict(zip(columns, result))
            else:
                # Return default state if none exists
                return {
                    'consecutive_losses': 0,
                    'last_trade_id': None,
                    'last_trade_result': 'pending',
                    'current_multiplier': 1.00,
                    'base_amount': 1.00,
                    'max_consecutive_losses': 0,
                    'total_sequences': 0
                }
        except Exception as e:
            self.logger.error(f"Failed to get Martingale state: {e}")
            return {}
    
    def update_martingale_state(self, consecutive_losses: int, last_trade_id: str = None,
                               last_trade_result: str = 'pending', current_multiplier: float = 1.00,
                               reset_sequence: bool = False) -> bool:
        """Update Martingale state"""
        try:
            current_state = self.get_martingale_state()
            
            # Update max consecutive losses if needed
            max_consecutive_losses = max(current_state.get('max_consecutive_losses', 0), consecutive_losses)
            
            # Increment total sequences if resetting
            total_sequences = current_state.get('total_sequences', 0)
            if reset_sequence:
                total_sequences += 1
            
            query = """
            UPDATE martingale_state 
            SET consecutive_losses = %s, last_trade_id = %s, last_trade_result = %s,
                current_multiplier = %s, max_consecutive_losses = %s, total_sequences = %s,
                last_reset_time = %s, updated_at = %s
            WHERE id = (SELECT id FROM (SELECT id FROM martingale_state ORDER BY id DESC LIMIT 1) AS temp)
            """ if self.db_type == "mysql" else """
            UPDATE martingale_state 
            SET consecutive_losses = ?, last_trade_id = ?, last_trade_result = ?,
                current_multiplier = ?, max_consecutive_losses = ?, total_sequences = ?,
                last_reset_time = ?, updated_at = ?
            WHERE id = (SELECT id FROM martingale_state ORDER BY id DESC LIMIT 1)
            """
            
            current_time = datetime.now()
            reset_time = current_time if reset_sequence else current_state.get('last_reset_time', current_time)
            
            params = (consecutive_losses, last_trade_id, last_trade_result, current_multiplier,
                     max_consecutive_losses, total_sequences, reset_time, current_time)
            rows_affected = self._execute_query(query, params)
            
            if rows_affected > 0:
                self.logger.info(f"Martingale state updated: Losses={consecutive_losses}, Multiplier={current_multiplier}")
                return True
            else:
                self.logger.warning("No Martingale state found to update")
                return False
        except Exception as e:
            self.logger.error(f"Failed to update Martingale state: {e}")
            return False
    
    def reset_martingale_state(self, base_amount: float = 1.00) -> bool:
        """Reset Martingale state after a win"""
        return self.update_martingale_state(
            consecutive_losses=0,
            current_multiplier=1.00,
            reset_sequence=True
        )
    
    # === PER-ACCOUNT MARTINGALE PERSISTENCE ===
    
    def save_account_martingale_state(self, account_name: str, consecutive_losses: int, martingale_queue: list) -> bool:
        """Save per-account Martingale state to database"""
        try:
            # Convert queue to JSON string for storage
            import json
            queue_json = json.dumps(martingale_queue) if martingale_queue else '[]'
            
            # Calculate current multiplier from queue or use 1.0 as default
            current_multiplier = martingale_queue[0] if martingale_queue else 1.0
            
            # Use INSERT ... ON DUPLICATE KEY UPDATE for MySQL or INSERT OR REPLACE for SQLite
            if self.db_type == "mysql":
                query = """
                INSERT INTO martingale_state (account_name, consecutive_losses, current_multiplier, queue_amounts, updated_at) 
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                consecutive_losses = VALUES(consecutive_losses),
                current_multiplier = VALUES(current_multiplier),
                queue_amounts = VALUES(queue_amounts),
                updated_at = VALUES(updated_at)
                """
            else:
                query = """
                INSERT OR REPLACE INTO martingale_state 
                (account_name, consecutive_losses, current_multiplier, queue_amounts, updated_at) 
                VALUES (?, ?, ?, ?, ?)
                """
            
            current_time = datetime.now()
            params = (account_name, consecutive_losses, current_multiplier, queue_json, current_time)
            
            self._execute_query(query, params)
            self.logger.debug(f"[DatabaseManager] Saved Martingale state for account {account_name}: {consecutive_losses} losses, {len(martingale_queue)} queued")
            return True
            
        except Exception as e:
            self.logger.error(f"[DatabaseManager] Error saving account Martingale state for {account_name}: {e}")
            return False
    
    def load_account_martingale_state(self, account_name: str) -> tuple:
        """Load per-account Martingale state from database"""
        try:
            query = """
            SELECT consecutive_losses, queue_amounts FROM martingale_state 
            WHERE account_name = %s
            """ if self.db_type == "mysql" else """
            SELECT consecutive_losses, queue_amounts FROM martingale_state 
            WHERE account_name = ?
            """
            
            result = self._execute_query(query, (account_name,), fetch="one")
            
            if result:
                consecutive_losses, queue_json = result
                # Parse JSON queue - handle NULL or empty values
                import json
                try:
                    if queue_json:
                        martingale_queue = json.loads(queue_json)
                    else:
                        martingale_queue = []
                except (json.JSONDecodeError, TypeError):
                    martingale_queue = []
                
                self.logger.debug(f"[DatabaseManager] Loaded Martingale state for account {account_name}: {consecutive_losses} losses, {len(martingale_queue)} queued")
                return consecutive_losses or 0, martingale_queue
            else:
                # No state found, return defaults
                self.logger.debug(f"[DatabaseManager] No Martingale state found for account {account_name}, using defaults")
                return 0, []
                
        except Exception as e:
            self.logger.error(f"[DatabaseManager] Error loading account Martingale state for {account_name}: {e}")
            return 0, []
    
    def reset_account_martingale_state(self, account_name: str) -> bool:
        """Reset per-account Martingale state after a win"""
        return self.save_account_martingale_state(account_name, 0, [])
    
    def get_all_account_martingale_states(self) -> Dict[str, Dict]:
        """Get all account martingale states for persistence across restarts"""
        try:
            query = """
            SELECT account_name, consecutive_losses, queue_amounts, current_multiplier, 
                   max_consecutive_losses, total_sequences, last_reset_time, updated_at
            FROM martingale_state 
            WHERE account_name IS NOT NULL AND account_name != ''
            ORDER BY account_name
            """
            
            results = self._execute_query(query, fetch="all")
            
            if not results:
                self.logger.debug("[DatabaseManager] No account martingale states found")
                return {}
            
            account_states = {}
            for result in results:
                (account_name, consecutive_losses, queue_json, current_multiplier, 
                 max_consecutive_losses, total_sequences, last_reset_time, updated_at) = result
                
                # Parse JSON queue
                import json
                try:
                    if queue_json:
                        martingale_queue = json.loads(queue_json)
                    else:
                        martingale_queue = []
                except (json.JSONDecodeError, TypeError):
                    martingale_queue = []
                
                account_states[account_name] = {
                    'consecutive_losses': consecutive_losses or 0,
                    'martingale_queue': martingale_queue,
                    'current_multiplier': float(current_multiplier) if current_multiplier else 1.0,
                    'max_consecutive_losses': max_consecutive_losses or 0,
                    'total_sequences': total_sequences or 0,
                    'last_reset_time': last_reset_time,
                    'updated_at': updated_at
                }
            
            self.logger.debug(f"[DatabaseManager] Loaded martingale states for {len(account_states)} accounts")
            return account_states
            
        except Exception as e:
            self.logger.error(f"[DatabaseManager] Error loading all account martingale states: {e}")
            return {}
    
    def initialize_account_martingale_state(self, account_name: str) -> bool:
        """Initialize martingale state for a new account if it doesn't exist"""
        try:
            # Check if state already exists
            existing_state = self.load_account_martingale_state(account_name)
            if existing_state != (0, []):  # State exists
                return True
            
            # Initialize with defaults
            return self.save_account_martingale_state(account_name, 0, [])
            
        except Exception as e:
            self.logger.error(f"[DatabaseManager] Error initializing martingale state for {account_name}: {e}")
            return False
    
    # === PERFORMANCE TRACKING ===
    
    def update_daily_performance(self, worker_name: str, trade_result: str, 
                                invested_amount: float, payout_amount: float = 0.00,
                                is_martingale_recovery: bool = False) -> bool:
        """Update daily performance statistics"""
        try:
            today = datetime.now().date()
            
            # Get current day's performance or create new record
            query = """
            SELECT * FROM performance 
            WHERE worker_name = %s AND date = %s
            """ if self.db_type == "mysql" else """
            SELECT * FROM performance 
            WHERE worker_name = ? AND date = ?
            """
            
            result = self._execute_query(query, (worker_name, today), fetch="one")
            
            if result:
                # Update existing record
                columns = ['id', 'worker_name', 'date', 'total_trades', 'winning_trades', 
                          'losing_trades', 'total_invested', 'total_payout', 'net_profit',
                          'win_rate', 'martingale_recoveries', 'max_consecutive_losses', 
                          'created_at', 'updated_at']
                current_perf = dict(zip(columns, result))
                
                # Calculate updates
                total_trades = current_perf['total_trades'] + 1
                winning_trades = current_perf['winning_trades'] + (1 if trade_result == 'win' else 0)
                losing_trades = current_perf['losing_trades'] + (1 if trade_result == 'loss' else 0)
                
                # Convert Decimal to float to avoid type conflicts
                current_invested = float(current_perf['total_invested']) if current_perf['total_invested'] else 0.0
                current_payout = float(current_perf['total_payout']) if current_perf['total_payout'] else 0.0
                
                total_invested = current_invested + float(invested_amount)
                total_payout = current_payout + float(payout_amount)
                net_profit = total_payout - total_invested
                win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
                martingale_recoveries = current_perf['martingale_recoveries'] + (1 if is_martingale_recovery else 0)
                
                # For max consecutive losses tracking, we should check the account-specific state
                # instead of the global martingale state since we use per-account states
                account_losses, _ = self.load_account_martingale_state(worker_name)
                current_max = int(current_perf['max_consecutive_losses']) if current_perf['max_consecutive_losses'] else 0
                max_consecutive_losses = max(current_max, int(account_losses))
                
                update_query = """
                UPDATE performance 
                SET total_trades = %s, winning_trades = %s, losing_trades = %s,
                    total_invested = %s, total_payout = %s, net_profit = %s, win_rate = %s,
                    martingale_recoveries = %s, max_consecutive_losses = %s, updated_at = %s
                WHERE worker_name = %s AND date = %s
                """ if self.db_type == "mysql" else """
                UPDATE performance 
                SET total_trades = ?, winning_trades = ?, losing_trades = ?,
                    total_invested = ?, total_payout = ?, net_profit = ?, win_rate = ?,
                    martingale_recoveries = ?, max_consecutive_losses = ?, updated_at = ?
                WHERE worker_name = ? AND date = ?
                """
                
                current_time = datetime.now()
                params = (total_trades, winning_trades, losing_trades, total_invested, 
                         total_payout, net_profit, win_rate, martingale_recoveries, 
                         max_consecutive_losses, current_time, worker_name, today)
                self._execute_query(update_query, params)
                
            else:
                # Create new record
                winning_trades = 1 if trade_result == 'win' else 0
                losing_trades = 1 if trade_result == 'loss' else 0
                net_profit = payout_amount - invested_amount
                win_rate = (winning_trades / 1) * 100
                martingale_recoveries = 1 if is_martingale_recovery else 0
                
                # For new records, get account-specific consecutive losses
                account_losses, _ = self.load_account_martingale_state(worker_name)
                max_consecutive_losses = int(account_losses) if account_losses else 0
                
                insert_query = """
                INSERT INTO performance (worker_name, date, total_trades, winning_trades, 
                                       losing_trades, total_invested, total_payout, net_profit,
                                       win_rate, martingale_recoveries, max_consecutive_losses)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """ if self.db_type == "mysql" else """
                INSERT INTO performance (worker_name, date, total_trades, winning_trades, 
                                       losing_trades, total_invested, total_payout, net_profit,
                                       win_rate, martingale_recoveries, max_consecutive_losses)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                
                params = (worker_name, today, 1, winning_trades, losing_trades, 
                         invested_amount, payout_amount, net_profit, win_rate, 
                         martingale_recoveries, max_consecutive_losses)
                self._execute_query(insert_query, params)
            
            self.logger.debug(f"Performance updated for {worker_name}: {trade_result}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update performance for {worker_name}: {e}")
            return False
    
    def get_performance_summary(self, worker_name: str = None, days: int = 7) -> List[Dict]:
        """Get performance summary for last N days"""
        try:
            start_date = datetime.now().date() - timedelta(days=days)
            
            if worker_name:
                query = """
                SELECT * FROM performance 
                WHERE worker_name = %s AND date >= %s 
                ORDER BY date DESC
                """ if self.db_type == "mysql" else """
                SELECT * FROM performance 
                WHERE worker_name = ? AND date >= ? 
                ORDER BY date DESC
                """
                params = (worker_name, start_date)
            else:
                query = """
                SELECT * FROM performance 
                WHERE date >= %s 
                ORDER BY date DESC, worker_name
                """ if self.db_type == "mysql" else """
                SELECT * FROM performance 
                WHERE date >= ? 
                ORDER BY date DESC, worker_name
                """
                params = (start_date,)
            
            results = self._execute_query(query, params, fetch="all")
            
            columns = ['id', 'worker_name', 'date', 'total_trades', 'winning_trades', 
                      'losing_trades', 'total_invested', 'total_payout', 'net_profit',
                      'win_rate', 'martingale_recoveries', 'max_consecutive_losses', 
                      'created_at', 'updated_at']
            return [dict(zip(columns, row)) for row in results]
            
        except Exception as e:
            self.logger.error(f"Failed to get performance summary: {e}")
            return []
    
    # === ENHANCED MARTINGALE LANES METHODS ===
    
    def create_martingale_lane(self, account_name: str, symbol: str, base_amount: float, multiplier: float = 2.5, max_level: int = 7) -> str:
        """Create a new Martingale lane and return its lane_id"""
        try:
            import uuid
            lane_id = f"{account_name}_{symbol}_{int(time.time())}_{str(uuid.uuid4())[:8]}"
            
            if self.db_type == "mysql":
                query = """
                INSERT INTO martingale_lanes (lane_id, account_name, symbol, base_amount, current_amount, multiplier, max_level)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
            else:
                query = """
                INSERT INTO martingale_lanes (lane_id, account_name, symbol, base_amount, current_amount, multiplier, max_level)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """
            
            params = (lane_id, account_name, symbol, base_amount, base_amount, multiplier, max_level)
            self._execute_query(query, params)
            
            if self.db_type == "mysql":
                self.connection.commit()
            
            self.logger.info(f"Created Martingale lane {lane_id} for {account_name} - {symbol}")
            return lane_id
            
        except Exception as e:
            self.logger.error(f"Failed to create Martingale lane: {e}")
            return None
    
    def get_active_martingale_lanes(self, account_name: str = None, symbol: str = None) -> List[Dict]:
        """Get active Martingale lanes, optionally filtered by account or symbol"""
        try:
            base_query = "SELECT * FROM martingale_lanes WHERE status = 'active'"
            params = []
            
            if account_name:
                base_query += " AND account_name = " + ("%s" if self.db_type == "mysql" else "?")
                params.append(account_name)
            
            if symbol:
                base_query += " AND symbol = " + ("%s" if self.db_type == "mysql" else "?")
                params.append(symbol)
            
            base_query += " ORDER BY created_at ASC"  # FIFO ordering
            
            results = self._execute_query(base_query, tuple(params), fetch="all")
            
            lanes = []
            for row in results:
                lane = {
                    'lane_id': row[1],
                    'account_name': row[2], 
                    'symbol': row[3],
                    'status': row[4],
                    'current_level': row[5],
                    'base_amount': float(row[6]),
                    'current_amount': float(row[7]),
                    'multiplier': float(row[8]),
                    'max_level': row[9],
                    'total_invested': float(row[10]),
                    'total_potential_payout': float(row[11]),
                    'trade_ids': json.loads(row[12]) if row[12] else [],
                    'created_at': row[13],
                    'updated_at': row[14],
                    'completed_at': row[15]
                }
                lanes.append(lane)
            
            return lanes
            
        except Exception as e:
            self.logger.error(f"Failed to get active Martingale lanes: {e}")
            return []
    
    def get_next_lane_for_assignment(self, account_name: str, symbol: str = None) -> Dict:
        """Get the next Martingale lane for trade assignment based on strategy"""
        try:
            # Get trading settings for this account
            settings = self.get_trading_settings(account_name)
            strategy = settings.get('lane_assignment_strategy', 'round_robin')
            
            if strategy == 'symbol_priority':
                # For symbol_priority, first try to get lanes with matching symbol
                if symbol:
                    symbol_lanes = self.get_active_martingale_lanes(account_name, symbol)
                    if symbol_lanes:
                        return symbol_lanes[0]  # Return oldest matching symbol lane
                # Fallback to all lanes if no matching symbol
                lanes = self.get_active_martingale_lanes(account_name, None)
            else:
                # For fifo and round_robin, get ALL active lanes (no symbol filter)
                lanes = self.get_active_martingale_lanes(account_name, None)
            
            if not lanes:
                return None
            
            if strategy == 'fifo':
                # Return oldest lane first (already sorted by created_at ASC)
                return lanes[0]
            elif strategy == 'round_robin':
                # Find lane with least trades for balanced assignment
                return min(lanes, key=lambda x: len(x['trade_ids']))
            elif strategy == 'symbol_priority':
                # Fallback to FIFO if no matching symbol found
                return lanes[0]
            else:
                return lanes[0]  # Default to FIFO
                
        except Exception as e:
            self.logger.error(f"Failed to get next lane for assignment: {e}")
            return None
    
    def update_martingale_lane_on_trade(self, lane_id: str, trade_id: str, trade_amount: float, expected_payout: float = 0.0) -> bool:
        """Update Martingale lane when a trade is placed"""
        try:
            # Get current lane data
            query = "SELECT trade_ids, total_invested, total_potential_payout, current_level, base_amount, multiplier FROM martingale_lanes WHERE lane_id = " + ("%s" if self.db_type == "mysql" else "?")
            result = self._execute_query(query, (lane_id,), fetch="one")
            
            if not result:
                self.logger.error(f"Martingale lane {lane_id} not found")
                return False
            
            trade_ids_json, total_invested, total_potential_payout, current_level, base_amount, multiplier = result
            trade_ids = json.loads(trade_ids_json) if trade_ids_json else []
            
            # Add new trade
            trade_ids.append(trade_id)
            new_total_invested = float(total_invested) + trade_amount
            new_total_potential_payout = float(total_potential_payout) + expected_payout
            
            # Calculate next level amount for future use
            next_level = current_level + 1
            next_amount = float(base_amount) * (float(multiplier) ** (next_level - 1))
            
            # Update the lane
            if self.db_type == "mysql":
                update_query = """
                UPDATE martingale_lanes 
                SET trade_ids = %s, total_invested = %s, total_potential_payout = %s, 
                    current_level = %s, current_amount = %s, updated_at = NOW()
                WHERE lane_id = %s
                """
            else:
                update_query = """
                UPDATE martingale_lanes 
                SET trade_ids = ?, total_invested = ?, total_potential_payout = ?, 
                    current_level = ?, current_amount = ?, updated_at = CURRENT_TIMESTAMP
                WHERE lane_id = ?
                """
            
            params = (json.dumps(trade_ids), new_total_invested, new_total_potential_payout, 
                     next_level, next_amount, lane_id)
            self._execute_query(update_query, params)
            
            if self.db_type == "mysql":
                self.connection.commit()
            
            self.logger.info(f"Updated Martingale lane {lane_id} with trade {trade_id} - Level {current_level}, Amount ${trade_amount}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update Martingale lane: {e}")
            return False
    
    def complete_martingale_lane(self, lane_id: str, status: str = 'completed') -> bool:
        """Mark a Martingale lane as completed or cancelled"""
        try:
            if self.db_type == "mysql":
                query = "UPDATE martingale_lanes SET status = %s, completed_at = NOW(), updated_at = NOW() WHERE lane_id = %s"
            else:
                query = "UPDATE martingale_lanes SET status = ?, completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE lane_id = ?"
            
            self._execute_query(query, (status, lane_id))
            
            if self.db_type == "mysql":
                self.connection.commit()
            
            self.logger.info(f"Completed Martingale lane {lane_id} with status: {status}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to complete Martingale lane: {e}")
            return False
    
    def get_trading_settings(self, account_name: str) -> Dict:
        """Get trading settings for an account"""
        try:
            query = "SELECT * FROM trading_settings WHERE account_name = " + ("%s" if self.db_type == "mysql" else "?")
            result = self._execute_query(query, (account_name,), fetch="one")
            
            if result:
                return {
                    'account_name': result[1],
                    'concurrent_trading_enabled': bool(result[2]),
                    'max_concurrent_lanes': result[3],
                    'lane_assignment_strategy': result[4],
                    'auto_create_lanes': bool(result[5]),
                    'cool_down_seconds': result[6],
                    'max_daily_lanes': result[7],
                    'created_at': result[8],
                    'updated_at': result[9]
                }
            else:
                # Return default settings if not found
                return {
                    'account_name': account_name,
                    'concurrent_trading_enabled': True,  # Enable concurrent trading by default
                    'max_concurrent_lanes': 5,
                    'lane_assignment_strategy': 'round_robin',  # Use round_robin as default
                    'auto_create_lanes': True,
                    'cool_down_seconds': 0,
                    'max_daily_lanes': 10
                }
                
        except Exception as e:
            self.logger.error(f"Failed to get trading settings: {e}")
            return {
                'account_name': account_name,
                'concurrent_trading_enabled': True,  # Enable concurrent trading by default
                'max_concurrent_lanes': 5,
                'lane_assignment_strategy': 'round_robin',  # Use round_robin as default
                'auto_create_lanes': True,
                'cool_down_seconds': 0,
                'max_daily_lanes': 10
            }
    
    def update_trading_settings(self, account_name: str, **settings) -> bool:
        """Update trading settings for an account"""
        try:
            # Build dynamic query based on provided settings
            valid_fields = [
                'concurrent_trading_enabled', 'max_concurrent_lanes', 'lane_assignment_strategy',
                'auto_create_lanes', 'cool_down_seconds', 'max_daily_lanes'
            ]
            
            updates = []
            params = []
            
            for field, value in settings.items():
                if field in valid_fields:
                    updates.append(f"{field} = " + ("%s" if self.db_type == "mysql" else "?"))
                    params.append(value)
            
            if not updates:
                return True  # Nothing to update
            
            if self.db_type == "mysql":
                query = f"UPDATE trading_settings SET {', '.join(updates)}, updated_at = NOW() WHERE account_name = %s"
            else:
                query = f"UPDATE trading_settings SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE account_name = ?"
            
            params.append(account_name)
            
            self._execute_query(query, tuple(params))
            
            if self.db_type == "mysql":
                self.connection.commit()
            
            self.logger.info(f"Updated trading settings for {account_name}: {settings}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update trading settings: {e}")
            return False
    
    def get_lane_statistics(self, account_name: str = None, days: int = 30) -> Dict:
        """Get Martingale lane statistics"""
        try:
            base_query = """
            SELECT 
                COUNT(*) as total_lanes,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_lanes,
                SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active_lanes,
                SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled_lanes,
                AVG(current_level) as avg_level,
                MAX(current_level) as max_level,
                SUM(total_invested) as total_invested,
                SUM(total_potential_payout) as total_potential_payout
            FROM martingale_lanes 
            WHERE created_at >= """ + ("DATE_SUB(NOW(), INTERVAL %s DAY)" if self.db_type == "mysql" else "date('now', '-' || ? || ' days')")
            
            params = [days]
            
            if account_name:
                base_query += " AND account_name = " + ("%s" if self.db_type == "mysql" else "?")
                params.append(account_name)
            
            result = self._execute_query(base_query, tuple(params), fetch="one")
            
            if result:
                return {
                    'total_lanes': result[0] or 0,
                    'completed_lanes': result[1] or 0,
                    'active_lanes': result[2] or 0,
                    'cancelled_lanes': result[3] or 0,
                    'avg_level': float(result[4]) if result[4] else 0.0,
                    'max_level': result[5] or 0,
                    'total_invested': float(result[6]) if result[6] else 0.0,
                    'total_potential_payout': float(result[7]) if result[7] else 0.0
                }
            else:
                return {
                    'total_lanes': 0, 'completed_lanes': 0, 'active_lanes': 0, 'cancelled_lanes': 0,
                    'avg_level': 0.0, 'max_level': 0, 'total_invested': 0.0, 'total_potential_payout': 0.0
                }
                
        except Exception as e:
            self.logger.error(f"Failed to get lane statistics: {e}")
            return {}
    
    # === UTILITY METHODS ===
    
    def close(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()
            self.logger.info("Database connection closed")
    
    def backup_data(self, backup_path: str = None) -> bool:
        """Backup database data to JSON file"""
        try:
            if not backup_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = f"backup_trades_{timestamp}.json"
            
            # Export all data
            backup_data = {
                'accounts': self.get_all_accounts(),
                'trades': self.get_recent_trades(limit=1000),
                'martingale_state': self.get_martingale_state(),
                'performance': self.get_performance_summary(days=30),
                'backup_timestamp': datetime.now().isoformat()
            }
            
            with open(backup_path, 'w') as f:
                json.dump(backup_data, f, indent=2, default=str)
            
            self.logger.info(f"Database backup created: {backup_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Database backup failed: {e}")
            return False
    
    def get_statistics(self) -> Dict:
        """Get overall database statistics"""
        try:
            stats = {}
            
            # Total accounts
            result = self._execute_query("SELECT COUNT(*) FROM accounts", fetch="one")
            stats['total_accounts'] = result[0] if result else 0
            
            # Total trades
            result = self._execute_query("SELECT COUNT(*) FROM trades", fetch="one")
            stats['total_trades'] = result[0] if result else 0
            
            # Pending trades
            query = "SELECT COUNT(*) FROM trades WHERE result = %s" if self.db_type == "mysql" else "SELECT COUNT(*) FROM trades WHERE result = ?"
            result = self._execute_query(query, ('pending',), fetch="one")
            stats['pending_trades'] = result[0] if result else 0
            
            # Overall win rate
            win_query = "SELECT COUNT(*) FROM trades WHERE result = %s" if self.db_type == "mysql" else "SELECT COUNT(*) FROM trades WHERE result = ?"
            win_result = self._execute_query(win_query, ('win',), fetch="one")
            wins = win_result[0] if win_result else 0
            
            loss_query = "SELECT COUNT(*) FROM trades WHERE result = %s" if self.db_type == "mysql" else "SELECT COUNT(*) FROM trades WHERE result = ?"
            loss_result = self._execute_query(loss_query, ('loss',), fetch="one")
            losses = loss_result[0] if loss_result else 0
            
            total_completed = wins + losses
            stats['win_rate'] = (wins / total_completed * 100) if total_completed > 0 else 0
            stats['total_wins'] = wins
            stats['total_losses'] = losses
            
            # Martingale state
            stats['martingale_state'] = self.get_martingale_state()
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Failed to get statistics: {e}")
            return {}
    
    def populate_initial_accounts(self, accounts_config: List[Dict]) -> bool:
        """Populate database with initial account configurations
        
        Args:
            accounts_config: List of dictionaries with keys: name, ssid, demo, enabled
        """
        try:
            self.logger.info("Populating database with initial account configurations...")
            
            for config in accounts_config:
                worker_name = config.get('name')
                ssid = config.get('ssid')
                is_demo = config.get('demo', True)
                enabled = config.get('enabled', True)
                
                if not worker_name or not ssid:
                    self.logger.warning(f"Skipping invalid account config: {config}")
                    continue
                
                success = self.add_account(
                    worker_name=worker_name,
                    ssid=ssid,
                    is_demo=is_demo,
                    enabled=enabled,
                    balance=0.00
                )
                
                if success:
                    self.logger.info(f"Successfully added/updated account: {worker_name}")
                else:
                    self.logger.error(f"Failed to add account: {worker_name}")
            
            self.logger.info("Finished populating initial account configurations")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to populate initial accounts: {e}")
            return False


# === CONFIGURATION CLASS ===
class DatabaseConfig:
    """Database configuration helper"""
    
    @staticmethod
    def sqlite_config(db_path: str = "trades.db") -> Dict:
        """SQLite configuration"""
        return {
            'db_type': 'sqlite',
            'db_path': db_path
        }
    
    @staticmethod
    def mysql_config(host: str, user: str, password: str, database: str, port: int = 3306) -> Dict:
        """MySQL configuration"""
        return {
            'db_type': 'mysql',
            'host': host,
            'user': user,
            'password': password,
            'database': database,
            'port': port
        }
    
    @staticmethod
    def from_env() -> Dict:
        """Load database config from environment variables"""
        db_type = os.getenv('DB_TYPE', 'sqlite').lower()
        
        if db_type == 'mysql':
            return DatabaseConfig.mysql_config(
                host=os.getenv('DB_HOST', 'localhost'),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PASSWORD'),
                database=os.getenv('DB_NAME'),
                port=int(os.getenv('DB_PORT', 3306))
            )
        else:
            return DatabaseConfig.sqlite_config(
                db_path=os.getenv('DB_PATH', 'trades.db')
            )


if __name__ == "__main__":
    # Example usage and testing
    logging.basicConfig(level=logging.INFO)
    
    # Test SQLite
    print("Testing SQLite database...")
    db = DatabaseManager("sqlite", db_path="test_trades.db")
    
    # Add test account
    db.add_account("test_worker", "test_ssid", True, 1000.0)
    
    # Add test trade
    db.add_trade("test_trade_1", "test_worker", "EURUSD_otc", "call", 10.0, 300)
    
    # Update trade result
    db.update_trade_result("test_trade_1", "win", 18.0)
    
    # Update performance
    db.update_daily_performance("test_worker", "win", 10.0, 18.0)
    
    # Get statistics
    stats = db.get_statistics()
    print(f"Statistics: {stats}")
    
    # Backup
    db.backup_data("test_backup.json")
    
    db.close()
    print("SQLite test completed successfully!")
