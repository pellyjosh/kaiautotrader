# /Users/Hubolux/Documents/Project 001/HuboluxJobs/Trading/kaiSignalTrade/pocket_worker.py
import time
import json # Import the json module
import multiprocessing
from pocketoptionapi.stable_api import PocketOption
import pocketoptionapi.global_value as global_value # Each process has its own global_value

# Database imports
try:
    from db.database_manager import DatabaseManager, DatabaseConfig
    import db.database_config as db_config
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    print("[WARNING] Database modules not available. Worker will run without database support.")

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

    # --- Connection Health Check ---
    def check_connection_health():
        """Check if connection is still healthy and attempt reconnection if needed."""
        nonlocal is_connected_and_ready
        if not global_value.websocket_is_connected or not is_connected_and_ready:
            worker_log(worker_name, "Connection unhealthy. Attempting reconnection...", "WARNING")
            return connect_to_pocketoption()
        return True

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
            
            # Register account in database
            # if DATABASE_AVAILABLE:
            #     try:
            #         if db_config.DATABASE_TYPE.lower() == "mysql":
            #             config = DatabaseConfig.mysql_config(**db_config.MYSQL_CONFIG)
            #         else:
            #             config = DatabaseConfig.sqlite_config(db_config.SQLITE_DB_PATH)
                    
            #         db = DatabaseManager(**config)
            #         # When worker registers, assume account is enabled (since it's running)
            #         db.add_account(worker_name, ssid, demo, enabled=True, balance=balance)
            #         db.close()
            #         worker_log(worker_name, f"Account registered in database", "DEBUG")
            #     except Exception as e_db:
            #         worker_log(worker_name, f"Failed to register account in database: {e_db}", "WARNING")
            
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

            worker_log(worker_name, f"Received command - Action: '{action}' (type: {type(action)}), Params: {params}, Request ID: {request_id}", "DEBUG")

            # Ensure connection health before processing command
            if not check_connection_health():
                worker_log(worker_name, "Connection health check failed. Cannot process command.", "ERROR")
                response_queue.put({'request_id': request_id, 'status': 'error', 
                                    'message': 'Connection health check failed.'})
                continue # Skip this command, wait for next

            response = {'request_id': request_id, 'status': 'error', 'message': f'Unknown action: {action}'}

            try:
                worker_log(worker_name, f"Checking action '{action}' against known actions: buy, get_balance, get_active_assets_payout, check_win, monitor_trade", "DEBUG")
                
                if action == 'buy':
                    worker_log(worker_name, f"Executing BUY: {params}", "DEBUG")
                    worker_log(worker_name, f"About to call api.buy with params: amount={params['amount']}, active={params['pair']}, action={params['action']}, expirations={params['expiration_duration']}", "DEBUG")
                    
                    # Retry logic for SSL/connection errors
                    max_retries = 3
                    retry_delay = 2  # seconds
                    
                    for attempt in range(max_retries):
                        try:
                            trade_result = api.buy(
                                amount=params['amount'],
                                active=params['pair'],
                                action=params['action'],
                                expirations=params['expiration_duration']
                            )
                            worker_log(worker_name, f"BUY command raw result: {trade_result}", "DEBUG")
                            # Clear any previous error response on successful API call
                            response = {'request_id': request_id}  # Reset to clean state
                            break  # Success, exit retry loop
                            
                        except (ConnectionError, OSError, Exception) as e:
                            error_str = str(e).lower()
                            if any(keyword in error_str for keyword in ['ssl', 'connection', 'protocol', 'socket', 'network']):
                                worker_log(worker_name, f"SSL/Connection error (attempt {attempt + 1}/{max_retries}): {e}", "WARNING")
                                if attempt < max_retries - 1:
                                    worker_log(worker_name, f"Retrying in {retry_delay} seconds...", "INFO")
                                    time.sleep(retry_delay)
                                    
                                    # Try to reconnect if connection seems lost
                                    if not global_value.websocket_is_connected:
                                        worker_log(worker_name, "WebSocket disconnected, attempting reconnection...", "INFO")
                                        connect_to_pocketoption()
                                    continue
                                else:
                                    worker_log(worker_name, f"Max retries reached. SSL/Connection error: {e}", "ERROR")
                                    response = {'request_id': request_id, 'status': 'error',
                                              'message': f'Connection error after {max_retries} attempts: {str(e)}'}
                                    break
                            else:
                                # Non-connection error, don't retry
                                worker_log(worker_name, f"Non-connection error during BUY: {e}", "ERROR")
                                response = {'request_id': request_id, 'status': 'error',
                                          'message': f'Trade execution error: {str(e)}'}
                                break
                    else:
                        # This executes if the for loop completed without breaking (all retries failed)
                        trade_result = (False, None)
                    
                    # Process successful trade result (only if we didn't set an error response above)
                    if response.get('status') != 'error':
                        worker_log(worker_name, f"Processing trade result: {trade_result}", "DEBUG")
                        try:
                            # Expected successful format: (True, trade_id, expiration_timestamp)
                            # Or sometimes just True if the library doesn't return full details on success.
                            # An error might be False, None, or an empty tuple, or a tuple with False as the first element.
                            if isinstance(trade_result, tuple) and len(trade_result) > 0 and trade_result[0] is True:
                                if len(trade_result) >= 3: # Full success details (True, trade_id, exp_ts)
                                    response = {'request_id': request_id, 'status': 'success', 
                                                'data': {'trade_id': trade_result[1], 'exp_ts': trade_result[2]}}
                                    worker_log(worker_name, f"Trade success with full details: {response}", "DEBUG")
                                elif len(trade_result) == 2: # Success with (True, trade_id)
                                    response = {'request_id': request_id, 'status': 'success',
                                                'data': {'trade_id': trade_result[1], 'message': 'Trade placed, expiration timestamp not provided by library in this response.'}}
                                    worker_log(worker_name, f"Trade success with trade_id: {response}", "DEBUG")
                                else: # Minimal success (e.g., just (True,))
                                    response = {'request_id': request_id, 'status': 'success', 
                                                'data': {'message': 'Trade likely placed, but full details not returned by library.'}}
                                    worker_log(worker_name, f"Trade success minimal: {response}", "DEBUG")
                            elif trade_result is True: # Another form of minimal success
                                response = {'request_id': request_id, 'status': 'success',
                                            'data': {'message': 'Trade reported as successful by library (boolean True).'}}
                                worker_log(worker_name, f"Trade success boolean: {response}", "DEBUG")
                            else:
                                response = {'request_id': request_id, 'status': 'error',
                                            'message': 'Buy command failed or returned non-success result.',
                                            'details': trade_result if trade_result is not None else "None"}
                                worker_log(worker_name, f"Trade failed: {response}", "ERROR")
                                
                            # Log trade to database if we have a successful trade
                            if response.get('status') == 'success' and DATABASE_AVAILABLE:
                                try:
                                    trade_data = response.get('data', {})
                                    trade_id = trade_data.get('trade_id')
                                    if trade_id:
                                        if db_config.DATABASE_TYPE.lower() == "mysql":
                                            config = DatabaseConfig.mysql_config(**db_config.MYSQL_CONFIG)
                                        else:
                                            config = DatabaseConfig.sqlite_config(db_config.SQLITE_DB_PATH)
                                        
                                        db = DatabaseManager(**config)
                                        db.add_trade(
                                            trade_id=trade_id,
                                            worker_name=worker_name,
                                            symbol=params.get('pair', 'unknown'),
                                            direction=params.get('action', 'unknown'),
                                            amount=params.get('amount', 0),
                                            expiration_duration=params.get('expiration_duration', 0)
                                        )
                                        db.close()
                                        worker_log(worker_name, f"Trade {trade_id} logged to database", "DEBUG")
                                except Exception as e_db_trade:
                                    worker_log(worker_name, f"Failed to log trade to database: {e_db_trade}", "WARNING")
                                    
                        except Exception as e_process:
                            worker_log(worker_name, f"Exception during trade result processing: {e_process}", "ERROR")
                            import traceback
                            worker_log(worker_name, f"Processing exception traceback: {traceback.format_exc()}", "ERROR")
                            response = {'request_id': request_id, 'status': 'error',
                                       'message': f'Trade result processing error: {str(e_process)}'}
                    else:
                        worker_log(worker_name, f"Response already set to error: {response}", "ERROR")
                
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
                elif action == 'check_win':
                    worker_log(worker_name, f"Executing CHECK_WIN for trade_id: {params.get('trade_id')}", "DEBUG")
                    trade_id = params.get('trade_id')
                    if not trade_id:
                        response = {'request_id': request_id, 'status': 'error', 'message': 'trade_id required for check_win'}
                    else:
                        try:
                            # check_win returns (profit, status) or (None, "unknown")
                            profit, status = api.check_win(trade_id)
                            if status in ["win", "loose", "unknown"]:
                                response = {'request_id': request_id, 'status': 'success', 
                                           'data': {'trade_id': trade_id, 'profit': profit, 'result': status}}
                                worker_log(worker_name, f"Trade {trade_id} result: {status}, profit: {profit}", "INFO")
                            else:
                                response = {'request_id': request_id, 'status': 'pending', 
                                           'message': f'Trade {trade_id} still pending, status: {status}'}
                        except Exception as e_check:
                            worker_log(worker_name, f"Error checking trade {trade_id}: {e_check}", "ERROR")
                            response = {'request_id': request_id, 'status': 'error', 
                                       'message': f'Error checking trade result: {str(e_check)}'}
                
                elif action == 'monitor_trade':
                    worker_log(worker_name, f"Starting MONITOR_TRADE for trade_id: {params.get('trade_id')}", "DEBUG")
                    trade_id = params.get('trade_id')
                    expiration_time = params.get('expiration_time', time.time() + 120)  # Default 2 min
                    symbol = params.get('symbol', 'unknown_symbol')  # Get symbol for Martingale tracking
                    if not trade_id:
                        response = {'request_id': request_id, 'status': 'error', 'message': 'trade_id required for monitor_trade'}
                    else:
                        # Start monitoring in background and send immediate response
                        response = {'request_id': request_id, 'status': 'success', 
                                   'message': f'Started monitoring trade {trade_id}'}
                        response_queue.put(response)
                        
                        # Now monitor the trade until expiration + buffer
                        monitor_timeout = expiration_time + 30  # 30 seconds buffer after expiration
                        start_time = time.time()
                        
                        while time.time() < monitor_timeout:
                            try:
                                profit, status = api.check_win(trade_id)
                                if status in ["win", "loose"]:
                                    # Trade completed - send result
                                    result_response = {
                                        'request_id': f'{request_id}_result',
                                        'status': 'trade_completed',
                                        'data': {
                                            'trade_id': trade_id,
                                            'symbol': symbol,  # Include symbol for Martingale tracking
                                            'profit': profit,
                                            'result': status,
                                            'monitoring_duration': time.time() - start_time
                                        }
                                    }
                                    response_queue.put(result_response)
                                    worker_log(worker_name, f"Trade {trade_id} completed: {status}, profit: {profit}", "INFO")
                                    break
                                elif status == "unknown":
                                    worker_log(worker_name, f"Trade {trade_id} status unknown, continuing to monitor...", "DEBUG")
                            except Exception as e_monitor:
                                worker_log(worker_name, f"Error monitoring trade {trade_id}: {e_monitor}", "ERROR")
                            
                            time.sleep(2)  # Check every 2 seconds
                        else:
                            # Timeout reached
                            timeout_response = {
                                'request_id': f'{request_id}_timeout',
                                'status': 'trade_timeout',
                                'data': {
                                    'trade_id': trade_id,
                                    'symbol': symbol,
                                    'message': f'Monitoring timeout after {time.time() - start_time:.1f} seconds'
                                }
                            }
                            response_queue.put(timeout_response)
                            worker_log(worker_name, f"Trade {trade_id} monitoring timed out", "WARNING")
                        
                        continue  # Skip the normal response_queue.put since we already sent responses

            except Exception as e_action:
                worker_log(worker_name, f"Error processing action '{action}': {e_action}", "ERROR")
                worker_log(worker_name, f"Exception type: {type(e_action)}", "ERROR")
                import traceback
                worker_log(worker_name, f"Exception traceback: {traceback.format_exc()}", "ERROR")
                response = {'request_id': request_id, 'status': 'error', 'message': str(e_action)}
            
            worker_log(worker_name, f"Final response being sent: {response}", "DEBUG")
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
