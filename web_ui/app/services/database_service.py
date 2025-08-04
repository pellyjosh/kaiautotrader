#!/usr/bin/env python3
"""
Database Service for HuboluxTradingBot Web UI
Connects to the same database used by the trading bot
"""

import sys
import os
import time

# Add the parent directory to the path to import from the existing bot project
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

from db.database_manager import DatabaseManager
import db.database_config as db_config
import logging

class DatabaseService:
    """Service class to handle all database operations for the web UI"""
    
    def __init__(self):
        self.db_manager = None
        self.logger = logging.getLogger(__name__)
        self.last_connection_time = 0
        self.connection_timeout = 3600  # 1 hour timeout
        self._connect()
    
    def _connect(self):
        """Initialize database connection using existing bot configuration"""
        try:
            if db_config.DATABASE_TYPE.lower() == "mysql":
                # Add connection timeout and auto-reconnect settings for MySQL
                mysql_config = db_config.MYSQL_CONFIG.copy()
                mysql_config.update({
                    'autocommit': True,
                    'connect_timeout': 60,
                    'buffered': True
                })
                self.db_manager = DatabaseManager(db_type='mysql', **mysql_config)
                self.logger.info("Connected to MySQL database with enhanced settings")
            else:
                self.db_manager = DatabaseManager(db_type='sqlite', db_path=db_config.SQLITE_DB_PATH)
                self.logger.info("Connected to SQLite database")
            
            self.last_connection_time = time.time()
        except Exception as e:
            self.logger.error(f"Failed to connect to database: {e}")
            raise
    
    def get_connection(self):
        """Get the database manager instance with automatic reconnection"""
        current_time = time.time()
        
        # Check if we need to reconnect due to timeout
        if (self.db_manager is None or 
            (current_time - self.last_connection_time) > self.connection_timeout):
            self.logger.info("Reconnecting due to timeout or missing connection")
            self._connect()
        else:
            # Test the connection and reconnect if needed
            try:
                if self.db_manager.db_type == "mysql":
                    # Check if MySQL connection is still alive
                    if not self.db_manager.connection or not self.db_manager.connection.is_connected():
                        self.logger.warning("MySQL connection lost. Reconnecting...")
                        self._connect()
                    else:
                        # Test with a simple query
                        self.db_manager._execute_query("SELECT 1", fetch="one")
                else:
                    # For SQLite, just test with a simple query
                    self.db_manager._execute_query("SELECT 1", fetch="one")
            except Exception as e:
                self.logger.warning(f"Database connection test failed: {e}. Reconnecting...")
                try:
                    self._connect()
                except Exception as reconnect_error:
                    self.logger.error(f"Failed to reconnect to database: {reconnect_error}")
                    raise
        return self.db_manager
    
    def test_connection(self):
        """Test database connection"""
        try:
            accounts = self.db_manager.get_all_accounts()
            return True, f"Connection successful. Found {len(accounts)} accounts."
        except Exception as e:
            return False, f"Connection failed: {str(e)}"

# Global database service instance
db_service = DatabaseService()
