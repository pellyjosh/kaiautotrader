# /Users/Hubolux/Documents/Project 001/HuboluxJobs/Trading/kaiSignalTrade/pocket_worker.py
import time
import json # Import the json module
import multiprocessing
from pocketoptionapi.stable_api import PocketOption
import pocketoptionapi.global_value as global_value # Each process has its own global_value

# Worker specific logger
def worker_log(worker_name, message, level="INFO"):
    """Simple logger for the worker process."""
    print(f"[{level}][{worker_name}] {message}")

def po_worker_main(worker_name, ssid, demo, command_queue, response_queue):
    """
    Main function for the PocketOption worker process.
    Manages connection and command processing for a single PO account.
    """
    worker_log(worker_name, f"Process started. Demo: {demo}. Initializing PocketOption.")
    api = None
    is_connected_and_ready = False

    # --- Connection Sub-function ---
    def connect_to_pocketoption():
        nonlocal api, is_connected_and_ready
        try:
            worker_log(worker_name, "Attempting to connect to PocketOption...")
            # Ensure global_value.logger is available for the PocketOption library
            # The library itself usually sets up a basic logger if none exists.
            # We can also set a default loglevel for this worker's global_value.
            if not hasattr(global_value, 'logger_instance_created_flag'): # A way to check if logger is setup
                 global_value.loglevel = 'INFO' # Default for this worker's instance of global_value

            api = PocketOption(ssid, demo) # This initiates the connection process
            worker_log(worker_name, "PocketOption instance created. Attempting explicit api.connect()...", "DEBUG")
            api.connect() # Explicitly call connect, similar to pocket_connector.py
            # A short pause to allow the connection thread (started by .connect()) to initialize.
            time.sleep(0.5) # Brief pause

            # Wait for WebSocket connection
            timeout_seconds = 30  # Generous timeout for worker connection
            connection_start_time = time.time()
            while not global_value.websocket_is_connected:
                if time.time() - connection_start_time > timeout_seconds:
                    worker_log(worker_name, f"Timeout: WebSocket not connected. global_value.websocket_is_connected is False.", "ERROR")
                    if hasattr(global_value, 'websocket_error_message') and global_value.websocket_error_message:
                        worker_log(worker_name, f"Last websocket error from global_value: {global_value.websocket_error_message}", "ERROR")
                    
                    is_connected_and_ready = False
                    return False
                time.sleep(0.2)
            worker_log(worker_name, "WebSocket connected.")

            # Wait for API to be ready (e.g., balance available)
            worker_log(worker_name, "Checking API readiness (fetching balance)...")
            balance = None
            readiness_start_time = time.time() # Reset timer for readiness check
            while balance is None:
                if time.time() - readiness_start_time > timeout_seconds: # Use overall timeout
                    worker_log(worker_name, f"Timeout: Balance not available (current: {balance}).", "ERROR")
                    is_connected_and_ready = False
                    return False
                if not global_value.websocket_is_connected: # Check if disconnected during wait
                    worker_log(worker_name, "WebSocket disconnected while waiting for balance.", "ERROR")
                    is_connected_and_ready = False
                    return False
                try:
                    balance = api.get_balance()
                except Exception as e_bal:
                    worker_log(worker_name, f"Error getting balance: {e_bal}. Retrying...", "WARNING")
                time.sleep(0.5) # Wait before retrying get_balance

            success_color_code = "\033[92m"
            reset_color_code = "\033[0m"
            worker_log(worker_name, f"{success_color_code} {worker_name} PocketOption Connected and Ready. Balance: {balance}{reset_color_code}", "INFO")
            is_connected_and_ready = True
            return True
        except Exception as e_conn:
            worker_log(worker_name, f"Critical connection/initialization failed: {e_conn}", "CRITICAL")
            api = None
            is_connected_and_ready = False
            return False

    # --- Initial Connection Attempt ---
    if not connect_to_pocketoption():
        # Send an error message back if initial connection fails, so the main process knows.
        response_queue.put({'request_id': 'initial_connection', 'status': 'error', 
                            'message': 'Worker failed to connect to PocketOption on startup.'})
        worker_log(worker_name, "Exiting due to initial connection failure.", "ERROR")
        return # End the worker process

    # --- Main Command Loop ---
    try:
        while True:
            try:
                command = command_queue.get(timeout=3600) # Block with a very long timeout
            except multiprocessing.queues.Empty: # Should not happen with long timeout
                continue # Go back to waiting

            if command is None or command.get('action') == 'shutdown':
                worker_log(worker_name, "Shutdown command received.", "INFO")
                break

            action = command.get('action')
            params = command.get('params', {})
            request_id = command.get('request_id', 'unknown_request')

            # Ensure connection before processing command
            if not is_connected_and_ready:
                worker_log(worker_name, "Not connected. Attempting to reconnect before processing command...", "WARNING")
                if not connect_to_pocketoption():
                    response_queue.put({'request_id': request_id, 'status': 'error', 
                                        'message': 'Not connected and reconnect failed.'})
                    continue # Skip this command, wait for next

            response = {'request_id': request_id, 'status': 'error', 'message': f'Unknown action: {action}'}

            try:
                if action == 'buy':
                    worker_log(worker_name, f"Executing BUY: {params}", "DEBUG")
                    trade_result = api.buy(
                        amount=params['amount'],
                        active=params['pair'],
                        action=params['action'],
                        expirations=params['expiration_duration']
                    )
                    worker_log(worker_name, f"BUY command raw result: {trade_result}", "DEBUG")

                    # Expected successful format: (True, trade_id, expiration_timestamp)
                    # Or sometimes just True if the library doesn't return full details on success.
                    # An error might be False, None, or an empty tuple, or a tuple with False as the first element.
                    if isinstance(trade_result, tuple) and len(trade_result) > 0 and trade_result[0] is True:
                        if len(trade_result) >= 3: # Full success details (True, trade_id, exp_ts)
                            response = {'request_id': request_id, 'status': 'success', 
                                        'data': {'trade_id': trade_result[1], 'exp_ts': trade_result[2]}}
                        elif len(trade_result) == 2: # Success with (True, trade_id)
                            response = {'request_id': request_id, 'status': 'success',
                                        'data': {'trade_id': trade_result[1], 'message': 'Trade placed, expiration timestamp not provided by library in this response.'}}
                        else: # Minimal success (e.g., just (True,))
                            response = {'request_id': request_id, 'status': 'success', 
                                        'data': {'message': 'Trade likely placed, but full details not returned by library.'}}
                    elif trade_result is True: # Another form of minimal success
                        response = {'request_id': request_id, 'status': 'success',
                                    'data': {'message': 'Trade reported as successful by library (boolean True).'}}
                    else:
                        response = {'request_id': request_id, 'status': 'error',
                                    'message': 'Buy command failed or returned non-success result.',
                                    'details': trade_result if trade_result is not None else "None"}
                
                elif action == 'get_balance':
                    worker_log(worker_name, "Executing GET_BALANCE", "DEBUG")
                    balance = api.get_balance()
                    if balance is not None:
                        response = {'request_id': request_id, 'status': 'success', 'data': {'balance': balance}}
                    else:
                        response = {'request_id': request_id, 'status': 'error', 'message': 'Failed to get balance'}
                
                elif action == 'get_active_assets_payout': # For prepare_get_history type functionality
                    worker_log(worker_name, "Executing GET_ACTIVE_ASSETS_PAYOUT", "DEBUG")
                    # This is a placeholder for how you'd get active assets and their payouts.
                    # The actual implementation depends on the library's capabilities.
                    # For now, let's assume it returns a dict like {'EURUSD_otc': 80, ...}
                    # The original `get_payout` in `pocket_functions` parses `global_value.PayoutData`.
                    # We can replicate a simplified version here.
                    active_assets = {}
                    if global_value.PayoutData:
                        try:
                            payout_data_list = json.loads(global_value.PayoutData)
                            for asset_info in payout_data_list:
                                if len(asset_info) == 19 and asset_info[14] is True: # Check if active
                                    active_assets[asset_info[1]] = asset_info[5] # pair_name: payout
                        except Exception as e_payout:
                             worker_log(worker_name, f"Error parsing PayoutData: {e_payout}", "ERROR")
                    
                    response = {'request_id': request_id, 'status': 'success', 'data': {'active_assets': active_assets}}


                # Add other actions as needed (e.g., get_candles, check_win)

            except Exception as e_action:
                worker_log(worker_name, f"Error processing action '{action}': {e_action}", "ERROR")
                response = {'request_id': request_id, 'status': 'error', 'message': str(e_action)}
            
            response_queue.put(response)

    except KeyboardInterrupt:
        worker_log(worker_name, "KeyboardInterrupt received in worker.", "INFO")
    except Exception as e_loop:
        worker_log(worker_name, f"Unhandled exception in worker's main loop: {e_loop}", "CRITICAL")
        # Try to inform the main process about this critical failure
        try:
            response_queue.put({'request_id': 'critical_worker_failure', 'status': 'critical_error', 
                                'message': f"Worker unhandled exception: {str(e_loop)}"})
        except Exception:
            pass # If queue is broken, can't do much
    finally:
        worker_log(worker_name, "Worker process terminating.", "INFO")
        # The PocketOption library doesn't have an explicit api.disconnect() or api.close().
        # The WebSocket connection is managed internally and should close when the process ends.
