import time, math, asyncio, json, threading, multiprocessing, uuid
from datetime import datetime
# from pocketoptionapi.stable_api import PocketOption # Now handled by pocket_connector
import pocketoptionapi.global_value as global_value
# import talib.abstract as ta
import numpy as np
import pandas as pd
import indicators as qtpylib

# Import the new connector and the signal detector
import pocket_connector
import detectsignal
import worker # Import the new worker module
import pocket_functions # Import the new functions module

global_value.loglevel = 'DEBUG' # Changed to DEBUG for more verbose Telethon logs initially

# Session configuration
start_counter = time.perf_counter()

# --- PocketOption Account Configurations for Workers ---
POCKET_OPTION_ACCOUNTS = [
    {'name': 'pelly_demo', 'ssid': """42["auth",{"session":"bpajv9apd668u8qkcdp4i34vc0","isDemo":1,"uid":104296609,"platform":1,"isFastHistory":true}]""", 'demo': True, 'enabled': True},
    {'name': 'pelly_real', 'ssid': """42["auth",{"session":"a:4:{s:10:\\"session_id\\";s:32:\\"2fdde4172af95443a5c227621595c835\\";s:10:\\"ip_address\\";s:14:\\"105.113.62.151\\";s:10:\\"user_agent\\";s:117:\\"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36\\";s:13:\\"last_activity\\";i:1750091525;}e7561b1ef34608df6bc9731d4119ef1c","isDemo":0,"uid":104296609,"platform":1,"isFastHistory":true}]""", 'demo': False, 'enabled': False},
    {'name': 'tonami_demo', 'ssid': """42["auth",{"session":"1620e72bltrkeb5e290f3etbcb","isDemo":1,"uid":34048913,"platform":1,"isFastHistory":true}]""", 'demo': True, 'enabled': True},
    {'name': 'tonami_real', 'ssid': """42["auth",{"session":"a:4:{s:10:\\"session_id\\";s:32:\\"09c3b588878f166204395267d358bfc2\\";s:10:\\"ip_address\\";s:14:\\"105.113.62.151\\";s:10:\\"user_agent\\";s:84:\\"Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:140.0) Gecko/20100101 Firefox/140.0\\";s:13:\\"last_activity\\";i:1750090512;}7abd18c3d9e5f0da2a9b4da0361ee5bd","isDemo":0,"uid":34048913,"platform":1,"isFastHistory":true}]""", 'demo': False, 'enabled': False},
]

worker_manager = None # Will be an instance of PocketWorkerManager

# Default trading parameters (can be overridden by signals if logic is added)
min_payout = 1
period = 60
expiration = 60

# All functions like get_payout, get_df, buy, buy2, make_df, strategie, etc.,
# are now moved to pocket_functions.py

# ... imports and initial global declarations (like api = None, min_payout, etc.)

class PocketWorkerManager:
    def __init__(self, account_configs):
        self.configs = account_configs
        self.workers = {}  # {'name': {'process': Process, 'cmd_q': Queue, 'resp_q': Queue}}
        self._start_workers()

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

    # Initialize the PocketWorkerManager
    worker_manager = PocketWorkerManager(POCKET_OPTION_ACCOUNTS)

    # Optional: Check initial connectivity of workers (example for the first one)
    # Check connectivity for ALL enabled workers
    successfully_connected_workers = 0
    enabled_po_accounts = [acc for acc in POCKET_OPTION_ACCOUNTS if acc.get('enabled', True)]

    if enabled_po_accounts and worker_manager.workers:
        for acc_config in enabled_po_accounts:
            account_name = acc_config['name']
            if account_name in worker_manager.workers: # Check if worker was actually started
                global_value.logger(f"[BotMain] Checking initial connection for worker: {account_name}...", "INFO")
                balance_response = worker_manager.send_command(account_name, 'get_balance', timeout=35) # Increased timeout
                if balance_response and balance_response.get('status') == 'success':
                    global_value.logger(f"[BotMain] Worker {account_name} connected. Balance: {balance_response['data']['balance']}", "INFO")
                    successfully_connected_workers += 1
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
    def place_trade_via_worker_manager(amount, pair, action, expiration_duration, target_po_account_name=None):
        """Places a trade using a specified (or default) PO worker."""
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
                # Check if this worker corresponds to an enabled account in POCKET_OPTION_ACCOUNTS
                config = next((acc for acc in POCKET_OPTION_ACCOUNTS if acc['name'] == worker_name and acc.get('enabled', True)), None)
                if config and worker_manager.workers[worker_name]['process'].is_alive():
                    target_workers_to_trade.append(worker_name)
            if not target_workers_to_trade:
                global_value.logger("[BotMain] No enabled and alive workers found to place trade on.", "ERROR")
                return {'status': 'error', 'message': 'No enabled/alive workers found'}
        elif target_po_account_name is None:
            # Default to the first enabled account if no specific target and not "ALL"
            enabled_accounts_for_trade = [acc['name'] for acc in POCKET_OPTION_ACCOUNTS if acc.get('enabled', True) and acc['name'] in worker_manager.workers and worker_manager.workers[acc['name']]['process'].is_alive()]
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
        
        return {'status': 'success' if overall_success else 'partial_error', 'details': all_responses}

    def prepare_history_via_worker_manager(target_po_account_name=None):
        """
        Placeholder for 'prepare_history'. In a multi-process model, each worker manages its own
        pair data. This function could ensure a worker is active and perhaps fetch its active pairs.
        """
        if target_po_account_name is None:
            # If no specific target, use the first *enabled* PO account
            enabled_accounts_for_history = [acc['name'] for acc in POCKET_OPTION_ACCOUNTS if acc.get('enabled', True)]
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

    global_value.logger(f"[BotMain] Main setup finished in {time.perf_counter() - main_setup_start_time:.2f} seconds. Signal detector is running.", "INFO")
    global_value.logger(f'{success_color_code}[BotMain] Bot is now listening for Telegram signals. Press Ctrl+C to exit.{reset_color_code}', "INFO")

    try:
        # Keep the main thread alive. The Telethon listener runs in a daemon thread
        # started by detectsignal.py. If this main thread exits, the daemon thread will also exit.
        # We can use an event or a simple loop.
        while True:
            time.sleep(1) # Keep main thread alive, checking for KeyboardInterrupt
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