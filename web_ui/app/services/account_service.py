#!/usr/bin/env python3
"""
Account Service for HuboluxTradingBot Web UI
Handles trading account operations
"""

from typing import Optional, List, Dict, Any
from .database_service import db_service
import logging

class AccountService:
    """Service class for trading account management"""
    
    def __init__(self):
        self.db_manager = db_service.get_connection()
        self.logger = logging.getLogger(__name__)
    
    def get_accounts_by_user_id(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all accounts for a specific user"""
        try:
            # For now, get all accounts since we don't have user_id in accounts table yet
            # This should be updated when user-account relationship is implemented
            return self.get_all_accounts()
            
        except Exception as e:
            self.logger.error(f"Failed to get accounts for user {user_id}: {e}")
            return []
    
    def get_all_accounts(self) -> List[Dict[str, Any]]:
        """Get all accounts"""
        try:
            query = "SELECT * FROM accounts ORDER BY worker_name"
            results = self.db_manager._execute_query(query, fetch="all")
            
            columns = ['id', 'worker_name', 'ssid', 'is_demo', 'enabled', 'balance', 
                      'base_amount', 'martingale_multiplier', 'martingale_enabled', 
                      'created_at', 'last_updated', 'status']
            return [dict(zip(columns, row)) for row in results]
        except Exception as e:
            self.logger.error(f"Failed to get all accounts: {e}")
            return []
    
    def get_account_by_name(self, worker_name: str) -> Optional[Dict[str, Any]]:
        """Get account by worker name"""
        try:
            query = "SELECT * FROM accounts WHERE worker_name = %s" if self.db_manager.db_type == "mysql" else "SELECT * FROM accounts WHERE worker_name = ?"
            result = self.db_manager._execute_query(query, (worker_name,), fetch="one")
            
            if result:
                columns = ['id', 'worker_name', 'ssid', 'is_demo', 'enabled', 'balance', 
                          'base_amount', 'martingale_multiplier', 'martingale_enabled', 
                          'created_at', 'last_updated', 'status']
                return dict(zip(columns, result))
            return None
        except Exception as e:
            self.logger.error(f"Failed to get account {worker_name}: {e}")
            return None
    
    def create_account(self, worker_name: str, ssid: str, is_demo: bool = True, 
                      enabled: bool = True, base_amount: float = 1.0, 
                      martingale_multiplier: float = 2.0, martingale_enabled: bool = True) -> bool:
        """Create a new account"""
        try:
            # Use the database manager's add_account method
            success = self.db_manager.add_account(
                worker_name=worker_name,
                ssid=ssid,
                is_demo=is_demo,
                enabled=enabled,
                balance=0.0,
                base_amount=base_amount,
                martingale_multiplier=martingale_multiplier,
                martingale_enabled=martingale_enabled
            )
            
            if success:
                self.logger.info(f"Account {worker_name} created successfully")
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to create account {worker_name}: {e}")
            return False
    
    def update_account(self, worker_name: str, **kwargs) -> bool:
        """Update account information"""
        try:
            # Get current account
            account = self.get_account_by_name(worker_name)
            if not account:
                return False
            
            # Update specific fields
            if 'enabled' in kwargs:
                if kwargs['enabled']:
                    success = self.db_manager.enable_account(worker_name)
                else:
                    success = self.db_manager.disable_account(worker_name)
                if not success:
                    return False
            
            if 'base_amount' in kwargs or 'martingale_multiplier' in kwargs or 'martingale_enabled' in kwargs:
                base_amount = kwargs.get('base_amount', account.get('base_amount', 1.0))
                martingale_multiplier = kwargs.get('martingale_multiplier', account.get('martingale_multiplier', 2.0))
                martingale_enabled = kwargs.get('martingale_enabled', account.get('martingale_enabled', True))
                
                success = self.db_manager.update_account_martingale_settings(
                    worker_name, base_amount, martingale_multiplier, martingale_enabled
                )
                if not success:
                    return False
            
            if 'ssid' in kwargs:
                # Update SSID directly in database
                query = "UPDATE accounts SET ssid = %s WHERE worker_name = %s" if self.db_manager.db_type == "mysql" else "UPDATE accounts SET ssid = ? WHERE worker_name = ?"
                self.db_manager._execute_query(query, (kwargs['ssid'], worker_name))
            
            if 'balance' in kwargs:
                success = self.db_manager.update_account_balance(worker_name, kwargs['balance'])
                if not success:
                    return False
            
            self.logger.info(f"Account {worker_name} updated successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update account {worker_name}: {e}")
            return False
    
    def toggle_account(self, worker_name: str) -> Dict[str, Any]:
        """Toggle account enabled status"""
        try:
            account = self.get_account_by_name(worker_name)
            if not account:
                return {'success': False, 'message': 'Account not found'}
            
            current_status = account.get('enabled', False)
            new_status = not current_status
            
            success = self.update_account(worker_name, enabled=new_status)
            
            if success:
                return {
                    'success': True, 
                    'enabled': new_status,
                    'message': f"Account {'enabled' if new_status else 'disabled'} successfully"
                }
            else:
                return {'success': False, 'message': 'Failed to update account status'}
                
        except Exception as e:
            self.logger.error(f"Failed to toggle account {worker_name}: {e}")
            return {'success': False, 'message': str(e)}
    
    def delete_account(self, worker_name: str) -> bool:
        """Delete an account"""
        try:
            query = "DELETE FROM accounts WHERE worker_name = %s" if self.db_manager.db_type == "mysql" else "DELETE FROM accounts WHERE worker_name = ?"
            rows_affected = self.db_manager._execute_query(query, (worker_name,))
            
            if rows_affected > 0:
                self.logger.info(f"Account {worker_name} deleted successfully")
                return True
            else:
                self.logger.warning(f"No account found with name {worker_name}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to delete account {worker_name}: {e}")
            return False
    
    def get_account_statistics(self) -> Dict[str, Any]:
        """Get account statistics"""
        try:
            accounts = self.get_all_accounts()
            
            total = len(accounts)
            enabled = len([acc for acc in accounts if acc.get('enabled')])
            disabled = total - enabled
            demo = len([acc for acc in accounts if acc.get('is_demo')])
            real = total - demo
            
            return {
                'total': total,
                'enabled': enabled,
                'disabled': disabled,
                'demo': demo,
                'real': real
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get account statistics: {e}")
            return {
                'total': 0,
                'enabled': 0,
                'disabled': 0,
                'demo': 0,
                'real': 0
            }

# Global account service instance
account_service = AccountService()
