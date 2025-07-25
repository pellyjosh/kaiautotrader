import time, math, asyncio, json, threading, multiprocessing, uuid
from datetime import datetime
# from pocketoptionapi.stable_api import PocketOption # Now handled by pocket_connector
import pocketoptionapi.global_value as global_value
# import talib.abstract as ta
import numpy as np
import pandas as pd
# from tools import indicators as qtpylib

# Import the new connector and the signal detector
import pocket_connector
import detectsignal
import worker # Import the new worker module
# import tools.pocket_functions as pocket_functions # Import the new functions module

# Database imports
from db.database_manager import DatabaseManager
from db.database_config import DATABASE_TYPE, SQLITE_DB_PATH, MYSQL_CONFIG

global_value.loglevel = 'DEBUG' # Changed to DEBUG for more verbose Telethon logs initially

# Session configuration
start_counter = time.perf_counter()

# --- Database Configuration and Account Management ---
def initialize_database_and_accounts():
    """Initialize database connection and load accounts from database"""
    try:
        # Initialize database connection
        if DATABASE_TYPE.lower() == "mysql":
            db = DatabaseManager(db_type="mysql", **MYSQL_CONFIG)
            global_value.logger("[BotMain] Connected to MySQL database", "INFO")
        else:
            db = DatabaseManager(db_type="sqlite", db_path=SQLITE_DB_PATH)
            global_value.logger("[BotMain] Connected to SQLite database", "INFO")
        
        # Check if accounts exist in database
        existing_accounts = db.get_all_accounts()
        if not existing_accounts:
            global_value.logger("[BotMain] No accounts found in database.", "WARNING")
            global_value.logger("[BotMain] Please add accounts using: python manage_accounts.py add <name> <ssid> --demo <true/false> --enabled <true/false>", "INFO")
            global_value.logger("[BotMain] Or run: python migrate_accounts.py to migrate from hardcoded accounts", "INFO")
        else:
            enabled_count = len(db.get_enabled_accounts())
            global_value.logger(f"[BotMain] Found {len(existing_accounts)} total accounts in database ({enabled_count} enabled)", "INFO")
        
        return db
        
    except Exception as e:
        global_value.logger(f"[BotMain] Failed to initialize database: {e}", "CRITICAL")
        return None

def load_pocket_option_accounts_from_db(db):
    """Load enabled PocketOption accounts from database"""
    try:
        enabled_accounts = db.get_enabled_accounts()
        pocket_option_accounts = []
        
        for account in enabled_accounts:
            config = {
                'name': account['worker_name'],
                'ssid': account['ssid'],
                'demo': bool(account['is_demo']),
                'enabled': bool(account['enabled'])
            }
            pocket_option_accounts.append(config)
            global_value.logger(f"[BotMain] Loaded account from DB: {config['name']} (Demo: {config['demo']}, Enabled: {config['enabled']})", "DEBUG")
        
        global_value.logger(f"[BotMain] Loaded {len(pocket_option_accounts)} enabled accounts from database", "INFO")
        return pocket_option_accounts
        
    except Exception as e:
        global_value.logger(f"[BotMain] Failed to load accounts from database: {e}", "ERROR")
        return []


worker_manager = None # Will be an instance of PocketWorkerManager

# Default trading parameters (can be overridden by signals if logic is added)
min_payout = 1
period = 60
expiration = 60
single_trade_policy = True

# All functions like get_payout, get_df, buy, buy2, make_df, strategie, etc.,
# are now moved to pocket_functions.py

# ... imports and initial global declarations (like api = None, min_payout, etc.)

class PocketWorkerManager:
    def __init__(self, po_configs):
        self.configs = po_configs
        self.workers = {}
        self.running = True
        self.result_monitor_thread = None
    
    def start_result_monitoring(self):
        """Start background thread to monitor trade results from workers"""
        if self.result_monitor_thread and self.result_monitor_thread.is_alive():
            return
            
        def monitor_results():
            global_value.logger("[WorkerManager] Starting trade result monitoring thread", "INFO")
            while self.running:
                try:
                    for worker_name, worker_info in self.workers.items():
                        if not worker_info['process'].is_alive():
                            continue
                            
                        # Check for any pending responses (including trade results)
                        try:
                            while True:
                                response = worker_info['resp_q'].get_nowait()
                                self._handle_worker_response(worker_name, response)
                        except multiprocessing.queues.Empty:
                            pass  # No more responses
                        
                    time.sleep(1)  # Check every second
                except Exception as e:
                    global_value.logger(f"[WorkerManager] Error in result monitoring: {e}", "ERROR")
                    
        self.result_monitor_thread = threading.Thread(target=monitor_results, daemon=True)
        self.result_monitor_thread.start()
    
    def _handle_worker_response(self, worker_name, response):
        """Handle responses from workers, especially trade results"""
        if not response:
            return
            
        status = response.get('status')
        
        if status == 'trade_completed':
            # Trade result received - update Martingale system
            data = response.get('data', {})
            trade_id = data.get('trade_id')
            profit = data.get('profit')
            result = data.get('result')  # "win" or "loose"
            
            global_value.logger(f"[WorkerManager] Trade result received from {worker_name}: {trade_id} -> {result} (${profit})", "INFO")
            
            # Import detectsignal to call the result handler
            try:
                from detectsignal import _handle_trade_result
                # Convert "loose" to "loss" for consistency
                result_status = "win" if result == "win" else "loss"
                symbol = data.get('symbol', 'unknown_symbol')  # Get symbol from trade data
                _handle_trade_result(trade_id, symbol, result_status, profit, worker_name)
                global_value.logger(f"[WorkerManager] Updated Martingale system with trade {trade_id} result: {result_status} for account {worker_name}", "INFO")
            except Exception as e:
                global_value.logger(f"[WorkerManager] Error updating Martingale system: {e}", "ERROR")
                
        elif status == 'trade_timeout':
            # Trade monitoring timed out
            data = response.get('data', {})
            trade_id = data.get('trade_id')
            global_value.logger(f"[WorkerManager] Trade monitoring timeout for {trade_id} from {worker_name}", "WARNING")
            
        else:
            # Regular command response - log for debugging
            global_value.logger(f"[WorkerManager] Response from {worker_name}: {response}", "DEBUG")

    def _start_workers(self):
        if not self.configs:
            global_value.logger("[WorkerManager] No PocketOption accounts configured. Workers not started.", "WARNING")
            return

        enabled_configs = [config for config in self.configs if config.get('enabled', True)] # Default to True if 'enabled' key is missing

        if not enabled_configs:
            global_value.logger("[WorkerManager] No PocketOption accounts are enabled. Workers not started.", "INFO")
            return

        for config in enabled_configs:
            name = config['name']
            cmd_q = multiprocessing.Queue()
            resp_q = multiprocessing.Queue()
            process = multiprocessing.Process(
                target=worker.po_worker_main, # Target the main function in worker.py
                args=(name, config['ssid'], config['demo'], cmd_q, resp_q),
                name=f"PocketWorker-{name}"
            )
            process.daemon = True  # Workers will exit if the main process exits
            process.start()
            self.workers[name] = {'process': process, 'cmd_q': cmd_q, 'resp_q': resp_q}
            global_value.logger(f"[WorkerManager] Launched worker process for account: {name}", "INFO")
        
        # Start trade result monitoring
        self.start_result_monitoring()

    def send_command(self, account_name, action, params=None, timeout=15):
        if account_name not in self.workers:
            global_value.logger(f"[WorkerManager] No worker found for account: {account_name}", "ERROR")
            return {'status': 'error', 'message': f'Worker {account_name} not found.'}

        worker_info = self.workers[account_name]
        if not worker_info['process'].is_alive():
            global_value.logger(f"[WorkerManager] Worker for {account_name} is not alive.", "ERROR")
            # TODO: Implement worker restart logic if desired
            return {'status': 'error', 'message': f'Worker {account_name} not alive.'}

        request_id = str(uuid.uuid4())
        command = {'request_id': request_id, 'action': action, 'params': params or {}}
        
        try:
            worker_info['cmd_q'].put(command)
            # Wait for the specific response matching request_id
            start_wait = time.time()
            while time.time() - start_wait < timeout:
                try:
                    response = worker_info['resp_q'].get(timeout=0.1) # Short non-blocking get
                    if response.get('request_id') == request_id:
                        return response
                    else:
                        # Handle unexpected/late responses if necessary
                        global_value.logger(f"[WorkerManager] Received out-of-order/late response for {account_name}: {response}", "DEBUG")
                except multiprocessing.queues.Empty:
                    pass # No response yet, continue waiting
            
            # If loop finishes, it's a timeout for this specific request_id
            global_value.logger(f"[WorkerManager] Timeout waiting for response (ReqID: {request_id}) from {account_name} for action {action}", "ERROR")
            return {'request_id': request_id, 'status': 'error', 'message': 'Timeout waiting for specific response'}

        except Exception as e:
            global_value.logger(f"[WorkerManager] Error communicating with worker {account_name}: {e}", "ERROR")
            return {'request_id': request_id, 'status': 'error', 'message': str(e)}

    def shutdown_all(self, timeout=5):
        global_value.logger("[WorkerManager] Initiating shutdown of all worker processes...", "INFO")
        self.running = False  # Stop result monitoring
        
        for name, worker_info in self.workers.items():
            if worker_info['process'].is_alive():
                try:
                    global_value.logger(f"[WorkerManager] Sending shutdown to {name}...", "DEBUG")
                    worker_info['cmd_q'].put({'action': 'shutdown'})
                except Exception as e:
                    global_value.logger(f"[WorkerManager] Error sending shutdown command to {name}: {e}", "WARNING")

        # Wait for processes to terminate
        for name, worker_info in self.workers.items():
            try:
                worker_info['process'].join(timeout=timeout)
                if worker_info['process'].is_alive():
                    global_value.logger(f"[WorkerManager] Worker {name} did not terminate gracefully. Forcing termination.", "WARNING")
                    worker_info['process'].terminate() # Force kill
                    worker_info['process'].join(timeout=1) # Wait for force kill
                else:
                    global_value.logger(f"[WorkerManager] Worker {name} has shut down.", "INFO")
            except Exception as e:
                global_value.logger(f"[WorkerManager] Exception during shutdown/join for {name}: {e}", "ERROR")


def main():
    global worker_manager # Make worker_manager accessible globally if needed by other functions
    main_setup_start_time = time.perf_counter()

    success_color_code = "\033[92m"
    reset_color_code = "\033[0m"

    # Initialize database and load accounts
    global_value.logger("[BotMain] Initializing database and loading account configurations...", "INFO")
    db = initialize_database_and_accounts()
    if not db:
        global_value.logger("[BotMain] CRITICAL: Failed to initialize database. Terminating.", "CRITICAL")
        exit(1)
    
    # Load PocketOption accounts from database
    pocket_option_accounts = load_pocket_option_accounts_from_db(db)
    if not pocket_option_accounts:
        global_value.logger("[BotMain] WARNING: No enabled accounts found in database. Please check your account configurations.", "WARNING")
    
    # Initialize the PocketWorkerManager with accounts from database
    worker_manager = PocketWorkerManager(pocket_option_accounts)
    
    # Start the workers
    worker_manager._start_workers()

    # Optional: Check initial connectivity of workers (example for the first one)
    # Check connectivity for ALL enabled workers
    successfully_connected_workers = 0
    enabled_po_accounts = [acc for acc in pocket_option_accounts if acc.get('enabled', True)]

    if enabled_po_accounts and worker_manager.workers:
        for acc_config in enabled_po_accounts:
            account_name = acc_config['name']
            if account_name in worker_manager.workers: # Check if worker was actually started
                global_value.logger(f"[BotMain] Checking initial connection for worker: {account_name}...", "INFO")
                balance_response = worker_manager.send_command(account_name, 'get_balance', timeout=35) # Increased timeout
                if balance_response and balance_response.get('status') == 'success':
                    global_value.logger(f"[BotMain] Worker {account_name} connected. Balance: {balance_response['data']['balance']}", "INFO")
                    successfully_connected_workers += 1
                    
                    # Update balance in database
                    try:
                        balance = float(balance_response['data']['balance'])
                        db.update_account_balance(account_name, balance)
                    except (ValueError, KeyError):
                        global_value.logger(f"[BotMain] Could not parse balance for {account_name}", "WARNING")
                else:
                    global_value.logger(f"[BotMain] Worker {account_name} failed initial check or timed out. Response: {balance_response}", "ERROR")
    
    if enabled_po_accounts and successfully_connected_workers == 0:
        global_value.logger("[BotMain] CRITICAL: No PocketOption workers connected successfully. Terminating.", "CRITICAL")
        worker_manager.shutdown_all()
        exit(1)

    # The pocket_functions module might not be needed in the same way if all PO operations go via workers.
    # If strategies run in the main process, they'll use worker_manager.send_command().
    # For now, we'll adapt the functions passed to detectsignal.

    # --- Define functions to be used by detectsignal ---
    def place_trade_via_worker_manager(amount, pair, action, expiration_duration, target_po_account_name=None, tracking_id=None):
        """Places a trade using a specified (or default) PO worker."""
        # Ensure amount is a float, not Decimal for JSON serialization
        amount = float(amount) if hasattr(amount, '__float__') else amount
        trade_params = {'amount': amount, 'pair': pair, 'action': action, 'expiration_duration': expiration_duration}
        
        success_color_code = "\033[92m"  # Green
        failure_color_code = "\033[91m"  # Red
        reset_color_code = "\033[0m"

        all_responses = {}
        overall_success = True

        target_workers_to_trade = []

        if target_po_account_name == 'ALL_ENABLED_WORKERS':
            global_value.logger(f"[BotMain] Relaying trade to ALL ENABLED workers: {pair} {action} ${amount} for {expiration_duration}s", "INFO")
            for worker_name in worker_manager.workers.keys():
                # Check if this worker corresponds to an enabled account in pocket_option_accounts
                config = next((acc for acc in pocket_option_accounts if acc['name'] == worker_name and acc.get('enabled', True)), None)
                if config and worker_manager.workers[worker_name]['process'].is_alive():
                    target_workers_to_trade.append(worker_name)
            if not target_workers_to_trade:
                global_value.logger("[BotMain] No enabled and alive workers found to place trade on.", "ERROR")
                return {'status': 'error', 'message': 'No enabled/alive workers found'}
        elif target_po_account_name is None:
            # Default to the first enabled account if no specific target and not "ALL"
            enabled_accounts_for_trade = [acc['name'] for acc in pocket_option_accounts if acc.get('enabled', True) and acc['name'] in worker_manager.workers and worker_manager.workers[acc['name']]['process'].is_alive()]
            if not enabled_accounts_for_trade:
                global_value.logger("[BotMain] No PocketOption accounts configured for trading.", "ERROR")
                return {'status': 'error', 'message': 'No default enabled/alive worker found'}
            target_workers_to_trade.append(enabled_accounts_for_trade[0])
            global_value.logger(f"[BotMain] No specific target, defaulting trade to worker '{target_workers_to_trade[0]}': {pair} {action} ${amount} for {expiration_duration}s", "INFO")
        else: # Specific worker name provided
            target_workers_to_trade.append(target_po_account_name)
            global_value.logger(f"[BotMain] Relaying trade to specific worker '{target_po_account_name}': {pair} {action} ${amount} for {expiration_duration}s", "INFO")

        for worker_name_to_trade in target_workers_to_trade:
            response = worker_manager.send_command(worker_name_to_trade, 'buy', params=trade_params)
            all_responses[worker_name_to_trade] = response
            if not (response and response.get('status') == 'success'):
                global_value.logger(f"{failure_color_code}[BotMain] Failed to send/confirm trade command to '{worker_name_to_trade}'. Worker response: {response}{reset_color_code}", "ERROR")
                overall_success = False
            else:
                global_value.logger(f"{success_color_code}[BotMain] Trade command sent to '{worker_name_to_trade}' successfully. Worker response: {response.get('data')}{reset_color_code}", "INFO")
                
                # Extract trade ID for Martingale tracking if available
                trade_data = response.get('data', {})
                if isinstance(trade_data, dict) and 'trade_id' in trade_data:
                    trade_id = trade_data['trade_id']
                    expiration_time = trade_data.get('exp_ts', time.time() + expiration_duration)
                    global_value.logger(f"[BotMain] Tracking trade {trade_id} for Martingale system", "INFO")
                    
                    # Update pending trade tracking with real PocketOption trade ID
                    # The worker already saved the trade to database, so we just need to update our tracking
                    if tracking_id:
                        from detectsignal import _save_pending_trade_with_real_id
                        if _save_pending_trade_with_real_id(tracking_id, trade_id):
                            global_value.logger(f"[BotMain] Updated trade tracking to use PocketOption ID: {trade_id}", "DEBUG")
                        else:
                            global_value.logger(f"[BotMain] Failed to update trade tracking - no pending data for tracking ID: {tracking_id}", "WARNING")
                    
                    # Start monitoring trade result for Martingale system
                    monitor_params = {
                        'trade_id': trade_id,
                        'expiration_time': expiration_time,
                        'symbol': pair  # Pass the symbol for Martingale tracking
                    }
                    monitor_response = worker_manager.send_command(worker_name_to_trade, 'monitor_trade', params=monitor_params, timeout=5)
                    if monitor_response and monitor_response.get('status') == 'success':
                        global_value.logger(f"[BotMain] Started monitoring trade {trade_id} for results", "DEBUG")
                    else:
                        global_value.logger(f"[BotMain] Failed to start trade monitoring for {trade_id}: {monitor_response}", "WARNING")
        
        return {'status': 'success' if overall_success else 'partial_error', 'details': all_responses}

    def prepare_history_via_worker_manager(target_po_account_name=None):
        """
        Placeholder for 'prepare_history'. In a multi-process model, each worker manages its own
        pair data. This function could ensure a worker is active and perhaps fetch its active pairs.
        """
        if target_po_account_name is None:
            # If no specific target, use the first *enabled* PO account
            enabled_accounts_for_history = [acc['name'] for acc in pocket_option_accounts if acc.get('enabled', True)]
            if not enabled_accounts_for_history:
                global_value.logger("[BotMain] No PocketOption accounts configured for prepare_history.", "ERROR")
                return False
            target_po_account_name = enabled_accounts_for_history[0]
            global_value.logger(f"[BotMain] No specific PO worker for history, defaulting to '{target_po_account_name}'.", "DEBUG")


        global_value.logger(f"[BotMain] Requesting active assets from worker '{target_po_account_name}' for main process pair list...", "INFO")
        response = worker_manager.send_command(target_po_account_name, 'get_active_assets_payout', timeout=25) # Increased timeout for asset fetching

        if response and response.get('status') == 'success':
            active_assets = response['data'].get('active_assets', {})
            global_value.logger(f"[BotMain] Worker '{target_po_account_name}' reported {len(active_assets)} active assets.", "INFO")
            # Populate the main process's global_value.pairs
            temp_pairs = {}
            for asset, payout_val in active_assets.items():
                temp_pairs[asset] = {
                    'id': asset, # Placeholder, original get_payout gets an ID from raw data
                    'payout': payout_val,
                    'type': 'currency' if '_otc' not in asset.lower() and '/' in asset else ('stock' if asset.startswith('#') else 'otc_currency') # Crude type guess
                }
            global_value.pairs.clear() # Clear existing
            global_value.pairs.update(temp_pairs) # Update the global_value directly
            global_value.logger(f"[BotMain] Main process global_value.pairs updated with {len(global_value.pairs)} assets from worker.", "DEBUG")
            return True # Indicates worker is responsive and provided data
        else:
            global_value.logger(f"[BotMain] Failed to get active assets from '{target_po_account_name}'. Response: {response}", "ERROR")
            return False

    # Start the Telethon signal detector
    telethon_started = detectsignal.start_signal_detector(
        api_instance=None, # No longer passing a single API instance from main
        global_value_mod=global_value,
        buy_func=place_trade_via_worker_manager, # Pass the new worker-based function
        prep_history_func=prepare_history_via_worker_manager # Pass the new worker-based function
    )

    if not telethon_started:
        global_value.logger("[BotMain] Failed to start Telethon signal detector. Please check configurations in detectsignal.py (API_ID, HASH, Phone, Target Group). Terminating.", "CRITICAL")
        # Perform any necessary cleanup before exiting
        total_runtime = time.perf_counter() - start_counter # Use the global start_counter
        global_value.logger(f"[BotMain] Bot shutting down due to Telethon startup failure. Total runtime: {total_runtime:.2f} seconds", "INFO")
        exit(1)

    # Initialize Martingale system - settings will be loaded per-account from database
    # Note: No longer passing hardcoded values - each account uses its own DB settings
    detectsignal.initialize_martingale_system_from_database()
    global_value.logger(f"[BotMain] Martingale system initialized with per-account settings from database", "INFO")
    
    # Configure single trade policy
    detectsignal.configure_single_trade_policy(single_trade_policy)
    policy_status = "ENABLED" if single_trade_policy else "DISABLED"
    global_value.logger(f"[BotMain] Single trade policy: {policy_status}", "INFO")

    global_value.logger(f"[BotMain] Main setup finished in {time.perf_counter() - main_setup_start_time:.2f} seconds. Signal detector is running.", "INFO")
    global_value.logger(f'{success_color_code}[BotMain] Bot is now listening for Telegram signals. Press Ctrl+C to exit.{reset_color_code}', "INFO")

    try:
        # Keep the main thread alive. The Telethon listener runs in a daemon thread
        # started by detectsignal.py. If this main thread exits, the daemon thread will also exit.
        # We can use an event or a simple loop.
        last_martingale_status_check = 0
        while True:
            time.sleep(1) # Keep main thread alive, checking for KeyboardInterrupt
            
            # Periodically log Martingale status (every 60 seconds)
            current_time = time.time()
            if current_time - last_martingale_status_check >= 60:
                martingale_status = detectsignal.get_current_martingale_status()
                single_trade_policy_status = "ENABLED" if martingale_status.get('single_trade_policy_enabled', True) else "DISABLED"
                status_msg = f"[BotMain] Trading Status - Single Trade Policy: {single_trade_policy_status}, Martingale: "
                if martingale_status['martingale_enabled']:
                    status_msg += f"ENABLED, "
                    status_msg += f"Total Active Trades: {martingale_status['active_trades_count']}, "
                    status_msg += f"Current Active Trade: {martingale_status['current_active_trade']}"
                    
                    # Show per-account status for ENABLED accounts only
                    account_states = martingale_status.get('account_states', {})
                    active_trades_per_account = martingale_status.get('active_trades_per_account', {})
                    
                    # Get enabled accounts from database
                    enabled_accounts = db.get_enabled_accounts()
                    enabled_account_names = [acc['worker_name'] for acc in enabled_accounts]
                    
                    if account_states and enabled_account_names:
                        status_msg += " | Enabled Account Status: "
                        account_info = []
                        for account in enabled_account_names:
                            if account in account_states:
                                state = account_states[account]
                                consecutive_losses = state['consecutive_losses']
                                queue_length = len(state['martingale_queue'])
                                active_trade = active_trades_per_account.get(account, None)
                                
                                # Get account-specific settings from database
                                account_data = next((acc for acc in enabled_accounts if acc['worker_name'] == account), None)
                                if account_data:
                                    base_amount = account_data['base_amount']
                                    multiplier = account_data['martingale_multiplier']
                                    account_martingale_enabled = account_data['martingale_enabled']
                                    
                                    account_status = f"{account}(Base:${base_amount}, Mult:{multiplier}x, Mart:{'On' if account_martingale_enabled else 'Off'}, Losses:{consecutive_losses}, Queue:{queue_length}"
                                    if active_trade:
                                        account_status += f", Active:{active_trade}"
                                    account_status += ")"
                                    account_info.append(account_status)
                        
                        status_msg += ", ".join(account_info)
                else:
                    status_msg += "DISABLED"
                
                global_value.logger(status_msg, "INFO")
                last_martingale_status_check = current_time
    except KeyboardInterrupt:
        global_value.logger("[BotMain] KeyboardInterrupt received. Shutting down...", "INFO")
    finally:
        if worker_manager:
            worker_manager.shutdown_all()
        # Perform any cleanup if necessary.
        # The Telethon thread is a daemon, so it will be terminated when the main program exits.
        # If graceful shutdown of Telethon was required (e.g. sending a message),
        # detectsignal.py's telethon_thread_runner would need to handle the KeyboardInterrupt
        # and telethon_listener_thread.daemon would be False, requiring a join here.
        total_runtime = time.perf_counter() - start_counter
        global_value.logger(f"[BotMain] Bot shutting down. Total runtime: {total_runtime:.2f} seconds", "INFO")

if __name__ == "__main__":
    main()