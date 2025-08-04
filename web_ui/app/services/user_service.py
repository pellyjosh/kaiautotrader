#!/usr/bin/env python3
"""
User Service for HuboluxTradingBot Web UI
Handles user management operations
"""

from typing import Optional, List, Dict, Any
from .database_service import db_service
from werkzeug.security import generate_password_hash
import logging

class UserService:
    """Service class for user management"""
    
    def __init__(self):
        self.db_manager = db_service.get_connection()
        self.logger = logging.getLogger(__name__)
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by ID"""
        try:
            query = "SELECT * FROM users WHERE id = %s" if self.db_manager.db_type == "mysql" else "SELECT * FROM users WHERE id = ?"
            result = self.db_manager._execute_query(query, (user_id,), fetch="one")
            
            if result:
                columns = ['id', 'username', 'password_hash', 'email', 'full_name', 'is_active', 'is_admin', 'created_at', 'last_login', 'failed_login_attempts', 'locked_until']
                user_dict = dict(zip(columns, result))
                # Add role field for compatibility with existing code
                user_dict['role'] = 'admin' if user_dict.get('is_admin') else 'user'
                return user_dict
            return None
        except Exception as e:
            self.logger.error(f"Failed to get user by ID {user_id}: {e}")
            return None
    
    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username"""
        try:
            query = "SELECT * FROM users WHERE username = %s" if self.db_manager.db_type == "mysql" else "SELECT * FROM users WHERE username = ?"
            result = self.db_manager._execute_query(query, (username,), fetch="one")
            
            if result:
                columns = ['id', 'username', 'password_hash', 'email', 'full_name', 'is_active', 'is_admin', 'created_at', 'last_login', 'failed_login_attempts', 'locked_until']
                user_dict = dict(zip(columns, result))
                # Add role field for compatibility with existing code
                user_dict['role'] = 'admin' if user_dict.get('is_admin') else 'user'
                return user_dict
            return None
        except Exception as e:
            self.logger.error(f"Failed to get user by username {username}: {e}")
            return None
    
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email"""
        try:
            query = "SELECT * FROM users WHERE email = %s" if self.db_manager.db_type == "mysql" else "SELECT * FROM users WHERE email = ?"
            result = self.db_manager._execute_query(query, (email,), fetch="one")
            
            if result:
                columns = ['id', 'username', 'password_hash', 'email', 'full_name', 'is_active', 'is_admin', 'created_at', 'last_login', 'failed_login_attempts', 'locked_until']
                user_dict = dict(zip(columns, result))
                # Add role field for compatibility with existing code
                user_dict['role'] = 'admin' if user_dict.get('is_admin') else 'user'
                return user_dict
            return None
        except Exception as e:
            self.logger.error(f"Failed to get user by email {email}: {e}")
            return None
    
    def create_user(self, username: str, email: str, password: str) -> bool:
        """Create a new user"""
        try:
            # Check if user already exists
            if self.get_user_by_username(username):
                self.logger.warning(f"User {username} already exists")
                return False
            
            if self.get_user_by_email(email):
                self.logger.warning(f"Email {email} already exists")
                return False
            
            # Hash password
            password_hash = generate_password_hash(password)
            
            # Create user
            query = """
            INSERT INTO users (username, email, password_hash, is_active)
            VALUES (%s, %s, %s, %s)
            """ if self.db_manager.db_type == "mysql" else """
            INSERT INTO users (username, email, password_hash, is_active)
            VALUES (?, ?, ?, ?)
            """
            
            params = (username, email, password_hash, 1)
            self.db_manager._execute_query(query, params)
            
            self.logger.info(f"User {username} created successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create user {username}: {e}")
            return False
    
    def update_user(self, user_id: int, **kwargs) -> bool:
        """Update user information"""
        try:
            # Build dynamic query
            updates = []
            params = []
            
            for field, value in kwargs.items():
                if field in ['username', 'email', 'is_active']:
                    updates.append(f"{field} = %s" if self.db_manager.db_type == "mysql" else f"{field} = ?")
                    params.append(value)
                elif field == 'role':
                    # Convert role to is_admin boolean
                    is_admin = 1 if value == 'admin' else 0
                    updates.append("is_admin = %s" if self.db_manager.db_type == "mysql" else "is_admin = ?")
                    params.append(is_admin)
                elif field == 'password':
                    updates.append("password_hash = %s" if self.db_manager.db_type == "mysql" else "password_hash = ?")
                    params.append(generate_password_hash(value))
            
            if not updates:
                return False
            
            params.append(user_id)
            query = f"""
            UPDATE users 
            SET {', '.join(updates)}
            WHERE id = %s
            """ if self.db_manager.db_type == "mysql" else f"""
            UPDATE users 
            SET {', '.join(updates)}
            WHERE id = ?
            """
            
            rows_affected = self.db_manager._execute_query(query, tuple(params))
            
            if rows_affected > 0:
                self.logger.info(f"User {user_id} updated successfully")
                return True
            else:
                self.logger.warning(f"No user found with ID {user_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to update user {user_id}: {e}")
            return False
    
    def delete_user(self, user_id: int) -> bool:
        """Delete a user"""
        try:
            query = "DELETE FROM users WHERE id = %s" if self.db_manager.db_type == "mysql" else "DELETE FROM users WHERE id = ?"
            rows_affected = self.db_manager._execute_query(query, (user_id,))
            
            if rows_affected > 0:
                self.logger.info(f"User {user_id} deleted successfully")
                return True
            else:
                self.logger.warning(f"No user found with ID {user_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to delete user {user_id}: {e}")
            return False
    
    def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all users"""
        try:
            query = "SELECT * FROM users ORDER BY created_at DESC"
            results = self.db_manager._execute_query(query, fetch="all")
            
            columns = ['id', 'username', 'password_hash', 'email', 'full_name', 'is_active', 'is_admin', 'created_at', 'last_login', 'failed_login_attempts', 'locked_until']
            users = []
            for row in results:
                user_dict = dict(zip(columns, row))
                # Add role field for compatibility with existing code
                user_dict['role'] = 'admin' if user_dict.get('is_admin') else 'user'
                users.append(user_dict)
            return users
            
        except Exception as e:
            self.logger.error(f"Failed to get all users: {e}")
            return []
    
    def update_last_login(self, user_id: int) -> bool:
        """Update user's last login timestamp"""
        try:
            from datetime import datetime
            query = """
            UPDATE users 
            SET last_login = %s 
            WHERE id = %s
            """ if self.db_manager.db_type == "mysql" else """
            UPDATE users 
            SET last_login = ? 
            WHERE id = ?
            """
            
            current_time = datetime.now()
            rows_affected = self.db_manager._execute_query(query, (current_time, user_id))
            
            return rows_affected > 0
            
        except Exception as e:
            self.logger.error(f"Failed to update last login for user {user_id}: {e}")
            return False

# Global user service instance
user_service = UserService()
