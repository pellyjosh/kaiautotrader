#!/usr/bin/env python3
"""
Enhanced Trade Manager
Provides centralized trade scheduling, monitoring, and database updates
Eliminates queuing delays and ensures immediate signal execution
"""
import time
import threading
import queue
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
import uuid

class TradeManager:
    """
    Centralized trade manager that:
    1. Schedules trades immediately when signals arrive
    2. Updates database in real-time
    3. Prevents command queuing delays
    """
    
    def __init__(self, worker_manager, db_manager, logger_func=None):
        self.worker_manager = worker_manager
        self.db_manager = db_manager
        self.logger = logger_func or print
        
        # Trade tracking
        self.active_trades = {}  # trade_id -> trade_info
        self.scheduled_trades = queue.Queue()  # Immediate execution queue
        self.monitoring_active = False
        
        # Threading
        self.scheduler_thread = None
        self.lock = threading.RLock()
        
        # Statistics
        self.total_trades_placed = 0
        self.total_trades_completed = 0
        self.average_execution_time = 0.0
        self.last_trade_time = 0.0  # Track last trade execution time
        
    def start(self):
        """Start the trade manager threads"""
        with self.lock:
            if self.monitoring_active:
                return
                
            self.monitoring_active = True
            
            # Start trade scheduler thread
            self.scheduler_thread = threading.Thread(
                target=self._trade_scheduler_loop,
                name="TradeScheduler",
                daemon=True
            )
            self.scheduler_thread.start()
            
            self._log("Trade Manager started with scheduler thread", "INFO")
    
    def stop(self):
        """Stop the trade manager"""
        with self.lock:
            self.monitoring_active = False
            if self.scheduler_thread and self.scheduler_thread.is_alive():
                self.scheduler_thread.join(timeout=5)
            self._log("Trade Manager stopped", "INFO")
    
    def schedule_trade(self, signal_data: Dict, tracking_id: str = None) -> str:
        """
        Schedule a trade for immediate execution
        Returns: trade_tracking_id for monitoring
        """
        trade_request = {
            'tracking_id': tracking_id or f"trade_{int(time.time())}_{uuid.uuid4().hex[:8]}",
            'signal_data': signal_data,
            'timestamp': time.time(),
            'priority': 'high',  # All signals are high priority
            'retries': 0
        }
        
        # Add to immediate execution queue
        self.scheduled_trades.put(trade_request)
        self._log(f"Scheduled trade {trade_request['tracking_id']} for immediate execution", "INFO")
        
        return trade_request['tracking_id']
    
    def _trade_scheduler_loop(self):
        """
        Trade scheduler loop - executes trades immediately
        No queuing delays, direct worker communication
        """
        self._log("Trade scheduler started", "DEBUG")
        
        while self.monitoring_active:
            try:
                # Get next trade to execute (blocks until available)
                trade_request = self.scheduled_trades.get(timeout=1.0)
                
                # Rate limiting: ensure minimum 2 seconds between trades
                current_time = time.time()
                time_since_last_trade = current_time - self.last_trade_time
                if time_since_last_trade < 2.0:
                    sleep_time = 2.0 - time_since_last_trade
                    self._log(f"Rate limiting: waiting {sleep_time:.1f}s before next trade", "DEBUG")
                    time.sleep(sleep_time)
                
                # Execute trade immediately
                execution_start = time.time()
                success = self._execute_trade_immediately(trade_request)
                execution_time = time.time() - execution_start
                self.last_trade_time = time.time()
                
                # Update statistics
                self.total_trades_placed += 1
                self.average_execution_time = (
                    (self.average_execution_time * (self.total_trades_placed - 1) + execution_time) 
                    / self.total_trades_placed
                )
                
                if success:
                    self._log(f"Trade {trade_request['tracking_id']} executed in {execution_time:.3f}s", "INFO")
                else:
                    self._log(f"Trade {trade_request['tracking_id']} failed after {execution_time:.3f}s", "ERROR")
                    
            except queue.Empty:
                continue  # No trades to execute, continue monitoring
            except Exception as e:
                self._log(f"Error in trade scheduler: {e}", "ERROR")
    
    def _execute_trade_immediately(self, trade_request: Dict) -> bool:
        """
        Execute trade immediately without worker queue delays
        Returns: True if successful, False otherwise
        """
        signal_data = trade_request['signal_data']
        tracking_id = trade_request['tracking_id']
        
        try:
            # Extract trade parameters
            base_amount = signal_data.get('amount', 1.0)
            pair = signal_data.get('pair')
            action = signal_data.get('action')
            expiration = signal_data.get('expiration', 300)
            target_account = signal_data.get('target_account', 'ALL_ENABLED_WORKERS')
            
            # Get enhanced Martingale manager and determine proper trade amounts
            from enhanced_martingale import get_enhanced_martingale_manager
            enhanced_manager = get_enhanced_martingale_manager()
            
            target_accounts = self._get_target_accounts(target_account)
            if not target_accounts:
                self._log(f"No target accounts found for {target_account}", "ERROR")
                return False
            
            # Execute trade with Enhanced Martingale integration for each account
            success_count = 0
            trade_futures = []  # For concurrent execution
            
            # Prepare trades for concurrent execution
            for account_name in target_accounts:
                # Get the correct trade amount from Enhanced Martingale system
                if enhanced_manager:
                    # Ensure the EnhancedMartingaleManager has the correct method implemented
                    trade_amount, lane_id = enhanced_manager.get_trade_amount_for_signal(account_name, pair)
                    if trade_amount <= 0:
                        self._log(f"Enhanced Martingale blocked trade for {account_name} (amount: ${trade_amount})", "WARNING")
                        continue
                    
                    # Log Enhanced Martingale decision
                    if lane_id:
                        self._log(f"[{account_name}] Enhanced Martingale assigned to lane {lane_id}: ${trade_amount}", "INFO")
                    else:
                        self._log(f"[{account_name}] Enhanced Martingale base trade: ${trade_amount}", "INFO")
                else:
                    # Fallback to base amount if Enhanced Martingale not available
                    trade_amount = base_amount
                    lane_id = None
                    self._log(f"[{account_name}] Using base amount (Enhanced Martingale not available): ${trade_amount}", "WARNING")
                
                # Prepare trade parameters
                trade_params = {
                    'amount': float(trade_amount),
                    'pair': pair,
                    'action': action,
                    'expiration_duration': expiration
                }
                
                # Store trade info for concurrent execution
                trade_futures.append({
                    'account_name': account_name,
                    'trade_params': trade_params,
                    'trade_amount': trade_amount,
                    'lane_id': lane_id
                })
            
            # Execute all trades concurrently (if multiple accounts)
            if len(trade_futures) > 1:
                self._log(f"Executing {len(trade_futures)} concurrent trades for signal", "INFO")
                
            for trade_future in trade_futures:
                account_name = trade_future['account_name']
                trade_params = trade_future['trade_params']
                trade_amount = trade_future['trade_amount']
                lane_id = trade_future['lane_id']
                
                # Use immediate execution method with longer timeout
                result = self.worker_manager.send_command(
                    account_name, 
                    'buy', 
                    params=trade_params,
                    timeout=15  # Increased timeout for trade execution
                )
                
                if result.get('status') == 'success':
                    trade_data = result.get('data', {})
                    real_trade_id = trade_data.get('trade_id')
                    
                    if real_trade_id:
                        # Notify Enhanced Martingale system about the pending trade
                        if enhanced_manager:
                            try:
                                # Use the proper method to handle trade placement
                                enhanced_manager.handle_trade_placed(
                                    trade_id=real_trade_id,
                                    account_name=account_name,
                                    symbol=pair,
                                    amount=trade_amount,
                                    lane_id=lane_id,
                                    expected_payout=0.0  # We don't have payout info at this stage
                                )
                                self._log(f"Registered trade {real_trade_id} with Enhanced Martingale for {account_name}", "DEBUG")
                            except Exception as e:
                                self._log(f"Error registering trade with Enhanced Martingale: {e}", "WARNING")
                        
                        # Start monitoring this trade
                        monitor_params = {
                            'trade_id': real_trade_id,
                            'expiration_time': time.time() + expiration, # Pass actual expiration time
                            'symbol': pair # Pass symbol for Martingale tracking in worker
                        }
                        # Send monitor_trade command to worker. Worker will handle result processing and database updates.
                        self.worker_manager.send_command(
                            account_name,
                            'monitor_trade',
                            params=monitor_params,
                            timeout=5 # Short timeout, just to send the command
                        )
                        self._log(f"Sent monitor_trade command to worker for trade {real_trade_id}", "DEBUG")
                        success_count += 1

                        # Update martingale lane status in the database
                        try:
                            if lane_id is not None:
                                self.db_manager.update_martingale_lane_status(lane_id, 'active')
                                self._log(f"Updated martingale lane status in DB for lane {lane_id} (account: {account_name}, trade: {real_trade_id})", "DEBUG")
                        except Exception as e:
                            self._log(f"Error updating martingale lane status in DB: {e}", "WARNING")
                else:
                    self._log(f"Trade execution failed for {account_name}: {result}", "ERROR")
            return success_count > 0
            
        except Exception as e:
            self._log(f"Error executing trade {tracking_id}: {e}", "ERROR")
            return False
    
    def _get_target_accounts(self, target_account: str) -> List[str]:
        """Get list of target account names for trading"""
        if target_account == 'ALL_ENABLED_WORKERS':
            # Get all enabled and alive workers
            enabled_workers = []
            for worker_name, worker_info in self.worker_manager.workers.items():
                if worker_info['process'].is_alive():
                    enabled_workers.append(worker_name)
            return enabled_workers
        else:
            return [target_account] if target_account in self.worker_manager.workers else []
    
    def get_active_trades_count(self) -> int:
        """Get number of currently active trades"""
        with self.lock:
            return len(self.active_trades)
    
    def get_active_trades_by_account(self) -> Dict[str, int]:
        """Get active trades count per account"""
        account_counts = {}
        with self.lock:
            for trade_info in self.active_trades.values():
                account = trade_info['account_name']
                account_counts[account] = account_counts.get(account, 0) + 1
        return account_counts
    
    def get_statistics(self) -> Dict:
        """Get trade manager statistics"""
        with self.lock:
            return {
                'total_trades_placed': self.total_trades_placed,
                'total_trades_completed': self.total_trades_completed,
                'active_trades_count': len(self.active_trades),
                'average_execution_time': self.average_execution_time,
                'success_rate': (self.total_trades_completed / max(self.total_trades_placed, 1)) * 100,
                'active_trades_by_account': self.get_active_trades_by_account()
            }
    
    def _log(self, message: str, level: str = "INFO"):
        """Log message with TradeManager prefix"""
        if self.logger:
            if hasattr(self.logger, '__call__'):
                self.logger(f"[TradeManager] {message}", level)
            else:
                print(f"[{level}][TradeManager] {message}")
        else:
            print(f"[{level}][TradeManager] {message}")

# Global trade manager instance
_trade_manager_instance = None

def initialize_trade_manager(worker_manager, db_manager, logger_func=None):
    """Initialize the global trade manager"""
    global _trade_manager_instance
    _trade_manager_instance = TradeManager(worker_manager, db_manager, logger_func)
    _trade_manager_instance.start()
    return _trade_manager_instance

def get_trade_manager():
    """Get the global trade manager instance"""
    return _trade_manager_instance

def shutdown_trade_manager():
    """Shutdown the global trade manager"""
    global _trade_manager_instance
    if _trade_manager_instance:
        _trade_manager_instance.stop()
        _trade_manager_instance = None
