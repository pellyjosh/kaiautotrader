#!/usr/bin/env python3
"""
Enhanced Martingale Trading System with Smart Concurrent Lanes
Supports intelligent trade assignment, concurrent lanes, and persistent state management
"""

import time
import json
import threading
import uuid
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from db.database_manager import DatabaseManager
import db.database_config as db_config


class MartingaleLane:
    """Represents a single Martingale trading lane/track"""
    
    def __init__(self, lane_id: str, account_name: str, symbol: str, base_amount: float, 
                 multiplier: float = 2.5, max_level: int = 7, current_level: int = 1):
        self.lane_id = lane_id
        self.account_name = account_name
        self.symbol = symbol
        self.base_amount = base_amount
        self.multiplier = multiplier
        self.max_level = max_level
        self.current_level = current_level  # Start at 1 for first Martingale level
        self.current_amount = base_amount * (multiplier ** (current_level - 1))
        self.total_invested = 0.0
        self.total_potential_payout = 0.0
        self.trade_ids = []
        self.status = 'active'
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.completed_at = None
    
    def get_next_trade_amount(self) -> float:
        """Get the amount for the next trade in this lane"""
        # Level 1 = base_amount * multiplier^0 = base_amount
        # Level 2 = base_amount * multiplier^1 = base_amount * multiplier
        # Level 3 = base_amount * multiplier^2, etc.
        return self.base_amount * (self.multiplier ** (self.current_level - 1))
    
    def can_continue(self) -> bool:
        """Check if this lane can continue (hasn't exceeded max level)"""
        return self.current_level < self.max_level and self.status == 'active'
    
    def to_dict(self) -> Dict:
        """Convert lane to dictionary for serialization"""
        return {
            'lane_id': self.lane_id,
            'account_name': self.account_name,
            'symbol': self.symbol,
            'base_amount': self.base_amount,
            'multiplier': self.multiplier,
            'max_level': self.max_level,
            'current_level': self.current_level,
            'current_amount': self.current_amount,
            'total_invested': self.total_invested,
            'total_potential_payout': self.total_potential_payout,
            'trade_ids': self.trade_ids,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }


class EnhancedMartingaleManager:
    """Enhanced Martingale system with smart concurrent trading support"""
    
    def __init__(self, db_manager: DatabaseManager = None, logger_func=None):
        self.db_manager = db_manager or self._init_database()
        self.logger_func = logger_func or print
        self.lock = threading.RLock()  # For thread-safe operations
        
        # Cache for active lanes (reduces DB queries)
        self._all_lanes_cache = {}
        self._avaliable_lanes_cache = {}
        self._cache_last_updated = 0
        self._cache_ttl = 30  # Cache expires after 30 seconds
        
        # Global settings
        self.global_martingale_enabled = True
        self.single_trade_policy_enabled = False
        
        # Per-account active trade tracking
        self.active_trades_per_account = {}
        self.pending_trade_results = {}
        
        self._log("Enhanced Martingale Manager initialized", "INFO")
    
    def _init_database(self) -> DatabaseManager:
        """Initialize database connection"""
        try:
            if db_config.DATABASE_TYPE.lower() == "mysql":
                return DatabaseManager(db_type='mysql', **db_config.MYSQL_CONFIG)
            else:
                return DatabaseManager(db_type='sqlite', db_path=db_config.SQLITE_DB_PATH)
        except Exception as e:
            self._log(f"Failed to initialize database: {e}", "ERROR")
            return None
    
    def _log(self, message: str, level: str = "INFO"):
        """Log message using provided logger function"""
        if self.logger_func:
            if hasattr(self.logger_func, '__call__'):
                self.logger_func(f"[EnhancedMartingale] {message}", level)
            else:
                print(f"[{level}][EnhancedMartingale] {message}")
        else:
            print(f"[{level}][EnhancedMartingale] {message}")
    
    def _invalidate_cache(self):
        """Invalidate the active lanes cache"""
        with self.lock:
            self._all_lanes_cache.clear()
            self._avaliable_lanes_cache.clear()
            self._cache_last_updated = 0
    
    def _get_avaliable_lanes(self, account_name: str) -> List[Dict]:
        """Get active lanes from cache or database"""
        with self.lock:
            current_time = time.time()
            
            if (current_time - self._cache_last_updated > self._cache_ttl or 
                account_name not in self._avaliable_lanes_cache):
                
                # Refresh cache
                if self.db_manager:
                    lanes = self.db_manager.get_inactive_martingale_lanes(account_name)
                    self._avaliable_lanes_cache[account_name] = lanes
                    self._cache_last_updated = current_time
                else:
                    return []
            
            return self._avaliable_lanes_cache.get(account_name, [])
        
    def _get_all_lanes(self, account_name: str) -> List[Dict]:
        """Get active lanes from cache or database"""
        with self.lock:
            current_time = time.time()
            
            if (current_time - self._cache_last_updated > self._cache_ttl or 
                account_name not in self._all_lanes_cache):
                
                # Refresh cache
                if self.db_manager:
                    lanes = self.db_manager.get_all_martingale_lanes(account_name)
                    self._all_lanes_cache[account_name] = lanes
                    self._cache_last_updated = current_time
                else:
                    return []
            
            return self._all_lanes_cache.get(account_name, [])
    
    def is_concurrent_trading_enabled(self, account_name: str) -> bool:
        """Check if concurrent trading is enabled for an account"""
        if not self.db_manager:
            return False
        
        settings = self.db_manager.get_trading_settings(account_name)
        return settings.get('concurrent_trading_enabled', False)
    
    def has_any_account_with_concurrent_trading(self) -> bool:
        """Check if any account has concurrent trading enabled"""
        if not self.db_manager:
            return False
            
        try:
            # Get all enabled accounts
            accounts = self.db_manager.get_enabled_accounts()
            for account in accounts:
                # Use 'worker_name' as that's the actual field name
                account_name = account.get('worker_name')
                if account_name and self.is_concurrent_trading_enabled(account_name):
                    return True
            return False
        except Exception as e:
            self._log(f"Error checking concurrent trading status: {e}", "ERROR")
            return False
    
    def should_disable_single_trade_policy(self) -> bool:
        """Determine if single trade policy should be disabled (i.e., allow concurrent trades)"""
        return self.has_any_account_with_concurrent_trading()
    
    def can_place_new_trade(self, account_name: str) -> bool:
        """Check if a new trade can be placed based on current policies"""
        if not self.global_martingale_enabled:
            return True  # If Martingale is disabled, always allow trades
        
        # Check single trade policy
        if self.single_trade_policy_enabled:
            # Check if there are any active trades for this account
            return not self.active_trades_per_account.get(account_name, False)
        
        # Check concurrent trading settings
        if not self.is_concurrent_trading_enabled(account_name):
            # Concurrent trading disabled - check if account has any active trades
            return not self.active_trades_per_account.get(account_name, False)
        
        # Concurrent trading enabled - check if we can assign to existing lanes first
        lanes = self._get_all_lanes(account_name)
        avaliable_lane = self._get_avaliable_lanes(account_name)
        if avaliable_lane:
            # If we have existing lanes, we can always assign trades to them (round-robin/fifo)
            return True
        
        # No existing lanes - check if we can create new ones
        settings = self.db_manager.get_trading_settings(account_name) if self.db_manager else {}
        max_lanes = settings.get('max_concurrent_lanes', 5)
        
        return len(lanes) < max_lanes
    
    def get_trade_amount_for_signal(self, account_name: str, symbol: str) -> Tuple[float, Optional[str]]:
        """
        Get trade amount for a new signal and assign to appropriate lane
        Returns (amount, lane_id) - lane_id is None for base trades
        """
        if not self.global_martingale_enabled:
            # Martingale disabled - use base amount
            base_amount = self._get_account_base_amount(account_name)
            self._log(f"[{account_name}] Martingale DISABLED - using base amount: ${base_amount}", "INFO")
            return base_amount, None
        
        if not self.can_place_new_trade(account_name):
            self._log(f"[{account_name}] Cannot place new trade - policy restrictions", "WARNING")
            return 0.0, None
        
        # Check for existing active lanes that can be assigned
        lane = self._get_next_lane_for_assignment(account_name, symbol)
        
        if lane:
            # Assign to existing lane - calculate next trade amount
            # Use the lane's get_next_trade_amount method for consistency
            next_amount = lane['base_amount'] * (lane['multiplier'] ** (lane['current_level'] - 1))
            self._log(f"[{account_name}] Assigned to existing lane {lane['lane_id']}: ${next_amount} (Level {lane['current_level']})", "INFO")
            return next_amount, lane['lane_id']
        else:
            # No existing lanes or auto-create disabled - use base amount
            base_amount = self._get_account_base_amount(account_name)
            self._log(f"[{account_name}] No suitable lanes found - using base amount: ${base_amount}", "INFO")
            return base_amount, None
    
    def _get_next_lane_for_assignment(self, account_name: str, symbol: str) -> Optional[Dict]:
        """Get the next lane for trade assignment based on strategy"""
        if not self.db_manager:
            self._log(f"[{account_name}] No database manager available for lane assignment", "WARNING")
            return None
        
        # Get the next lane from database based on strategy
        lane = self.db_manager.get_next_lane_for_assignment(account_name, symbol)
        
        if lane:
            # Log lane assignment details
            settings = self.db_manager.get_trading_settings(account_name)
            strategy = settings.get('lane_assignment_strategy', 'round_robin')
            trade_count = len(lane['trade_ids'])
            self._log(f"[{account_name}] Lane assignment using {strategy} strategy: Lane {lane['lane_id']} ({lane['symbol']}) with {trade_count} trades", "DEBUG")
        else:
            self._log(f"[{account_name}] No avaliable lanes found for assignment", "DEBUG")
        
        return lane
    
    def _get_account_base_amount(self, account_name: str) -> float:
        """Get base trading amount for an account"""
        if not self.db_manager:
            return 1.0
        
        accounts = self.db_manager.get_all_accounts()
        for account in accounts:
            if account['worker_name'] == account_name:
                return float(account['base_amount'])
        
        return 1.0  # Default fallback
    
    def _get_account_settings(self, account_name: str) -> Dict:
        """Get account-specific Martingale settings"""
        if not self.db_manager:
            return {'base_amount': 1.0, 'martingale_multiplier': 2.5, 'martingale_enabled': True}
        
        accounts = self.db_manager.get_all_accounts()
        for account in accounts:
            if account['worker_name'] == account_name:
                return {
                    'base_amount': float(account['base_amount']),
                    'martingale_multiplier': float(account['martingale_multiplier']),
                    'martingale_enabled': account['martingale_enabled']
                }
        
        return {'base_amount': 1.0, 'martingale_multiplier': 2.5, 'martingale_enabled': True}
    
    def handle_trade_placed(self, trade_id: str, account_name: str, symbol: str, 
                          amount: float, lane_id: str = None, expected_payout: float = 0.0) -> bool:
        """Handle when a trade is placed - update lane state"""
        with self.lock:
            # Debug logging for trade registration
            self._log(f"Registering trade {trade_id} for {account_name} (Symbol: {symbol}, Amount: ${amount}, Lane: {lane_id})", "DEBUG")
            
            # Mark account as having active trade
            self.active_trades_per_account[account_name] = True
            
            # Track pending trade result
            self.pending_trade_results[trade_id] = {
                'account_name': account_name,
                'symbol': symbol,
                'amount': amount,
                'lane_id': lane_id,
                'timestamp': time.time()
            }
            
            self._log(f"Now tracking {len(self.pending_trade_results)} pending trades: {list(self.pending_trade_results.keys())}", "DEBUG")
            
            if lane_id and self.db_manager:
                # Debug: Log lane update attempt
                self._log(f"[{account_name}] Attempting to update lane {lane_id} with trade {trade_id} (Amount: ${amount})", "DEBUG")
                
                # Update the lane with new trade
                success = self.db_manager.update_martingale_lane_on_trade(
                    lane_id, trade_id, amount, expected_payout
                )
                if success:
                    self._invalidate_cache()  # Refresh cache
                    self._log(f"[{account_name}] Successfully updated lane {lane_id} with trade {trade_id}", "INFO")
                else:
                    self._log(f"[{account_name}] Failed to update lane {lane_id} with trade {trade_id}", "ERROR")
                
                return success
            elif lane_id:
                self._log(f"[{account_name}] Cannot update lane {lane_id} - no database manager", "ERROR")
            else:
                self._log(f"[{account_name}] No lane ID provided for trade {trade_id} - base trade", "DEBUG")
            
            return True
    
    def handle_trade_result(self, trade_id: str, result: str, profit_loss: float = 0.0) -> bool:
        """Handle trade result and update Martingale state"""
        with self.lock:
            # Debug logging for trade tracking
            self._log(f"Handling trade result for {trade_id}: {result} (P&L: ${profit_loss})", "DEBUG")
            self._log(f"Currently tracking {len(self.pending_trade_results)} pending trades: {list(self.pending_trade_results.keys())}", "DEBUG")
            
            if trade_id not in self.pending_trade_results:
                self._log(f"Trade {trade_id} not found in pending results", "WARNING")
                return False
            
            trade_info = self.pending_trade_results[trade_id]
            account_name = trade_info['account_name']
            symbol = trade_info['symbol']
            amount = trade_info['amount']
            lane_id = trade_info.get('lane_id')
            
            # Clear active trade flag for this account
            self.active_trades_per_account[account_name] = False
            
            # Remove from pending results
            del self.pending_trade_results[trade_id]
            
            self._log(f"[{account_name}] Trade {trade_id} result: {result}, P&L: ${profit_loss}", "INFO")
            
            if result == "win":
                return self._handle_winning_trade(trade_id, account_name, symbol, lane_id, profit_loss)
            elif result == "loss":
                return self._handle_losing_trade(trade_id, account_name, symbol, lane_id, amount)
            else:
                self._log(f"[{account_name}] Unknown trade result: {result}", "WARNING")
                return False
    
    def _handle_winning_trade(self, trade_id: str, account_name: str, symbol: str, 
                            lane_id: str, profit: float) -> bool:
        """Handle a winning trade - complete lane if applicable"""
        if lane_id and self.db_manager:
            # Complete the lane
            success = self.db_manager.complete_martingale_lane(lane_id)
            if success:
                self._invalidate_cache()
                self._log(f"[{account_name}] Lane {lane_id} completed with WIN - ${profit} profit", "INFO")
            return success
        else:
            # Base trade win - no lane to complete
            self._log(f"[{account_name}] Base trade {trade_id} WON - ${profit} profit", "INFO")
            return True
    
    def _handle_losing_trade(self, trade_id: str, account_name: str, symbol: str, 
                           lane_id: str, amount: float) -> bool:
        """Handle a losing trade - create new lane or advance existing one"""
        account_settings = self._get_account_settings(account_name)
        
        if not account_settings['martingale_enabled']:
            self._log(f"[{account_name}] Martingale disabled - no lane creation for loss", "INFO")
            return True
        
        if lane_id:
            # This was already a Martingale trade - check if we can continue
            if self.db_manager:
                lanes = self.db_manager.get_active_martingale_lanes(account_name)
                current_lane = next((l for l in lanes if l['lane_id'] == lane_id), None)
                
                if current_lane and current_lane['current_level'] >= current_lane['max_level']:
                    # Lane has reached max level - mark as completed
                    self.db_manager.complete_martingale_lane(lane_id)
                    self._invalidate_cache()
                    self._log(f"[{account_name}] Lane {lane_id} reached max level - completed", "WARNING")
                else:
                    self.db_manager.update_martingale_lane_status(lane_id, 'inactive')
                    self._log(f"[{account_name}] Lane {lane_id} Updated matingale Status", "INFO")
                
                return True
        else:
            # Base trade loss - create new lane if auto-create is enabled
            return self._create_new_lane_for_loss(account_name, symbol, account_settings, trade_id, amount)
    
    def _create_new_lane_for_loss(self, account_name: str, symbol: str, account_settings: Dict, failed_trade_id: str = None, failed_amount: float = 0.0) -> bool:
        """Create a new Martingale lane after a base trade loss"""
        if not self.db_manager:
            return False
        
        # Check trading settings
        trading_settings = self.db_manager.get_trading_settings(account_name)
        
        if not trading_settings.get('auto_create_lanes', True):
            self._log(f"[{account_name}] Auto-create lanes disabled - no new lane created", "INFO")
            return True
        
        # Check daily lane limit
        max_daily_lanes = trading_settings.get('max_daily_lanes', 10)
        today_stats = self.db_manager.get_lane_statistics(account_name, days=1)
        
        if today_stats.get('total_lanes', 0) >= max_daily_lanes:
            self._log(f"[{account_name}] Daily lane limit reached ({max_daily_lanes}) - no new lane created", "WARNING")
            return True
        
        # Create new lane
        lane_id = self.db_manager.create_martingale_lane(
            account_name=account_name,
            symbol=symbol,
            base_amount=account_settings['base_amount'],
            multiplier=account_settings['martingale_multiplier'],
            max_level=7  # Default max level
        )
        
        if lane_id:
            # Record the failed trade that triggered this lane creation
            if failed_trade_id and failed_amount > 0:
                success = self.db_manager.update_martingale_lane_on_trade(
                    lane_id, failed_trade_id, failed_amount, 0.0  # No payout for failed trade
                )
                if success:
                    self._log(f"[{account_name}] Recorded failed trade {failed_trade_id} (${failed_amount}) in new lane {lane_id}", "INFO")
                else:
                    self._log(f"[{account_name}] Failed to record failed trade in new lane {lane_id}", "WARNING")
            
            self._invalidate_cache()
            self._log(f"[{account_name}] Created new Martingale lane {lane_id} for {symbol}", "INFO")
            return True
        else:
            self._log(f"[{account_name}] Failed to create new Martingale lane", "ERROR")
            return False
    
    def get_current_status(self) -> Dict:
        """Get current status of the Martingale system"""
        try:
            if not self.db_manager:
                return {'error': 'Database not available'}
            
            # Get all enabled accounts
            accounts = self.db_manager.get_enabled_accounts()
            account_names = [acc['worker_name'] for acc in accounts]
            
            status = {
                'global_martingale_enabled': self.global_martingale_enabled,
                'single_trade_policy_enabled': self.single_trade_policy_enabled,
                'total_active_trades': sum(1 for active in self.active_trades_per_account.values() if active),
                'total_pending_results': len(self.pending_trade_results),
                'accounts': {}
            }
            
            for account_name in account_names:
                active_lanes = self._get_all_lanes(account_name)
                trading_settings = self.db_manager.get_trading_settings(account_name)
                
                status['accounts'][account_name] = {
                    'active_lanes_count': len(active_lanes),
                    'active_trade': self.active_trades_per_account.get(account_name, False),
                    'concurrent_trading_enabled': trading_settings.get('concurrent_trading_enabled', False),
                    'max_concurrent_lanes': trading_settings.get('max_concurrent_lanes', 3),
                    'lanes': [
                        {
                            'lane_id': lane['lane_id'],
                            'symbol': lane['symbol'],
                            'current_level': lane['current_level'],
                            'current_amount': lane['current_amount'],
                            'total_invested': lane['total_invested']
                        }
                        for lane in active_lanes
                    ]
                }
            
            return status
            
        except Exception as e:
            self._log(f"Failed to get current status: {e}", "ERROR")
            return {'error': str(e)}
    
    def configure_account_settings(self, account_name: str, **settings) -> bool:
        """Configure trading settings for an account"""
        if not self.db_manager:
            return False
        
        try:
            success = self.db_manager.update_trading_settings(account_name, **settings)
            if success:
                self._invalidate_cache()
                self._log(f"[{account_name}] Updated trading settings: {settings}", "INFO")
            return success
        except Exception as e:
            self._log(f"Failed to configure account settings: {e}", "ERROR")
            return False
    
    def force_complete_lane(self, lane_id: str) -> bool:
        """Manually complete/cancel a Martingale lane"""
        if not self.db_manager:
            return False
        
        try:
            success = self.db_manager.complete_martingale_lane(lane_id)
            if success:
                self._invalidate_cache()
                self._log(f"Manually completed lane {lane_id}", "INFO")
            return success
        except Exception as e:
            self._log(f"Failed to complete lane: {e}", "ERROR")
            return False
    
    def get_lane_statistics(self, account_name: str = None, days: int = 30) -> Dict:
        """Get Martingale lane statistics"""
        if not self.db_manager:
            return {}
        
        return self.db_manager.get_lane_statistics(account_name, days)
    
    def cleanup_completed_lanes(self, days_old: int = 30) -> int:
        """Clean up old completed lanes from database"""
        # This would be implemented as a maintenance function
        # For now, return 0 as a placeholder
        return 0


# Global instance - will be initialized by detectsignal.py
enhanced_martingale_manager: Optional[EnhancedMartingaleManager] = None


def initialize_enhanced_martingale(db_manager: DatabaseManager = None, logger_func=None) -> EnhancedMartingaleManager:
    """Initialize the global enhanced Martingale manager"""
    global enhanced_martingale_manager
    enhanced_martingale_manager = EnhancedMartingaleManager(db_manager, logger_func)
    return enhanced_martingale_manager


def get_enhanced_martingale_manager() -> Optional[EnhancedMartingaleManager]:
    """Get the global enhanced Martingale manager instance"""
    return enhanced_martingale_manager
