# /Users/Hubolux/Documents/Project 001/HuboluxJobs/Trading/HuboluxTradingBot/pocket_worker.py
import time
import json # Import the json module
import multiprocessing
import threading
import signal
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

# Enhanced Martingale imports
try:
    from enhanced_martingale import initialize_enhanced_martingale, get_enhanced_martingale_manager, EnhancedMartingaleManager
    MARTINGALE_AVAILABLE = True
except ImportError:
    MARTINGALE_AVAILABLE = False
    print("[WARNING] Enhanced Martingale modules not available. Worker will run without Martingale support.")

# Worker specific logger
def worker_log(worker_name, message, level="INFO"):
    """Simple logger for the worker process."""
    print(f"[{level}][{worker_name}] {message}")

def timeout_api_call(api_func, timeout_seconds=10, *args, **kwargs):
    """
    Execute an API call with a timeout to prevent hanging.
    """
    result = [None]
    exception = [None]
    
    def target():
        try:
            result[0] = api_func(*args, **kwargs)
        except Exception as e:
            exception[0] = e
    
    thread = threading.Thread(target=target)
    thread.daemon = True
    thread.start()
    thread.join(timeout_seconds)
    
    if thread.is_alive():
        # Thread is still running, meaning timeout occurred
        raise TimeoutError(f"API call timed out after {timeout_seconds} seconds")
    
    if exception[0]:
        raise exception[0]
    
    return result[0]

def monitor_trade_thread(worker_name, api, trade_id, expiration_time, symbol, request_id, response_queue, db_instance=None, martingale_manager_instance=None):
    """
    Monitor a trade in a separate thread to avoid blocking the main worker loop.
    """
    try:
        monitor_timeout = expiration_time + 30  # 30 seconds buffer after expiration
        start_time = time.time()
        
        while time.time() < monitor_timeout:
            try:
                profit, status = api.check_win(trade_id)
                if status in ["win", "loose"]:
                    # Process trade result directly in worker thread
                    parsed_status = 'loss' if status == 'loose' else status
                    if DATABASE_AVAILABLE and db_instance:
                        try:
                            # Update database
                            db_instance.update_trade_result(trade_id, parsed_status, profit)
                            worker_log(worker_name, f"Database updated for trade {trade_id}: {status}", "DEBUG")
                            
                            # Notify Enhanced Martingale Manager
                            if MARTINGALE_AVAILABLE and martingale_manager_instance:
                                martingale_status = 'loss' if status == 'loose' else status
                                martingale_manager_instance.handle_trade_result(trade_id, martingale_status, profit)
                                worker_log(worker_name, f"Enhanced Martingale handled trade {trade_id} result: {martingale_status}", "DEBUG")
                        except Exception as e_process_result:
                            worker_log(worker_name, f"Error processing trade result in monitor thread (DB/Martingale): {e_process_result}", "ERROR")
                            import traceback
                            worker_log(worker_name, f"Monitor thread result processing traceback: {traceback.format_exc()}", "ERROR")

                    # Trade completed - send result
                    result_response = {
                        'request_id': f'{request_id}_result',
                        'status': 'trade_completed',
                        'data': {
                            'trade_id': trade_id,
                            'symbol': symbol,
                            'profit': profit,
                            'result': status,
                            'monitoring_duration': time.time() - start_time
                        }
                    }
                    response_queue.put(result_response)
                    worker_log(worker_name, f"Trade {trade_id} completed: {status}, profit: {profit}", "INFO")
                    return  # Exit monitoring thread
                elif status == "unknown":
                    worker_log(worker_name, f"Trade {trade_id} status unknown, continuing to monitor...", "DEBUG")
            except Exception as e_monitor:
                worker_log(worker_name, f"Error monitoring trade {trade_id}: {e_monitor}", "ERROR")
            
            time.sleep(2)  # Check every 2 seconds
        
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
        
    except Exception as e_thread:
        worker_log(worker_name, f"Error in monitor thread for trade {trade_id}: {e_thread}", "ERROR")
        error_response = {
            'request_id': f'{request_id}_error',
            'status': 'monitor_error',
            'data': {
                'trade_id': trade_id,
                'symbol': symbol,
                'message': f'Monitor thread error: {str(e_thread)}'
            }
        }
        response_queue.put(error_response)

def po_worker_main(worker_name, ssid, demo, command_queue, response_queue):
    """
    Main function for the PocketOption worker process.
    Manages connection and command processing for a single PO account.
    """
    worker_log(worker_name, f"Process started. Demo: {demo}. Initializing PocketOption.")
    api = None
    is_connected_and_ready = False
    
    # Initialize database manager and enhanced martingale manager for this worker
    db_instance = None
    martingale_manager_instance: EnhancedMartingaleManager = None

    if DATABASE_AVAILABLE:
        try:
            if db_config.DATABASE_TYPE.lower() == "mysql":
                db_instance = DatabaseManager(db_type='mysql', **db_config.MYSQL_CONFIG)
            else:
                db_instance = DatabaseManager(db_type='sqlite', db_path=db_config.SQLITE_DB_PATH)
            worker_log(worker_name, "DatabaseManager initialized for worker.", "DEBUG")
        except Exception as e:
            worker_log(worker_name, f"Failed to initialize DatabaseManager in worker: {e}", "ERROR")
            db_instance = None # Ensure it's None if initialization fails

    if MARTINGALE_AVAILABLE and db_instance:
        try:
            # Pass the worker's own db_instance to the Martingale manager
            martingale_manager_instance = initialize_enhanced_martingale(db_manager=db_instance, logger_func=worker_log)
            worker_log(worker_name, "EnhancedMartingaleManager initialized for worker.", "DEBUG")
        except Exception as e:
            worker_log(worker_name, f"Failed to initialize EnhancedMartingaleManager in worker: {e}", "ERROR")
            martingale_manager_instance = None # Ensure it's None if initialization fails


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
                command = command_queue.get(timeout=1)  # Reduced timeout for more responsive processing
            except multiprocessing.queues.Empty:
                # Check connection health periodically during idle time
                if not check_connection_health():
                    worker_log(worker_name, "Connection health check failed during idle time. Attempting reconnection...", "WARNING")
                continue  # Go back to waiting

            if command is None or command.get('action') == 'shutdown':
                worker_log(worker_name, "Shutdown command received.", "INFO")
                break

            action = command.get('action')
            params = command.get('params', {})
            request_id = command.get('request_id', 'unknown_request')
            command_timestamp = command.get('timestamp', time.time())  # Default to current time if not present

            # Check if command is too old (stale) - especially important for trading commands
            command_age = time.time() - command_timestamp
            max_command_age = 60  # Maximum age in seconds before considering command stale
            
            if action == 'buy' and command_age > max_command_age:
                worker_log(worker_name, f"DISCARDING stale trade command (age: {command_age:.1f}s > {max_command_age}s) - Request ID: {request_id}", "WARNING")
                response_queue.put({'request_id': request_id, 'status': 'error', 
                                    'message': f'Command too old ({command_age:.1f}s), discarded to prevent late execution'})
                continue  # Skip processing this stale command

            worker_log(worker_name, f"Received command - Action: '{action}' (type: {type(action)}), Params: {params}, Request ID: {request_id}, Age: {command_age:.1f}s", "DEBUG")

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
                    
                    # Retry logic for SSL/connection errors with reduced delays for faster execution
                    max_retries = 2  # Reduced from 3 to 2 for faster response
                    retry_delay = 1  # Reduced from 2 to 1 second
                    
                    for attempt in range(max_retries):
                        try:
                            # Set a timeout for the buy operation to prevent hanging
                            trade_result = timeout_api_call(
                                api.buy,
                                timeout_seconds=8,  # 8 second timeout for API call
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
                            if any(keyword in error_str for keyword in ['ssl', 'connection', 'protocol', 'socket', 'network', 'timeout']):
                                worker_log(worker_name, f"SSL/Connection/Timeout error (attempt {attempt + 1}/{max_retries}): {e}", "WARNING")
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
                            if response.get('status') == 'success' and DATABASE_AVAILABLE and db_instance:
                                try:
                                    trade_data = response.get('data', {})
                                    trade_id = trade_data.get('trade_id')
                                    if trade_id:
                                        db_instance.add_trade(
                                            trade_id=trade_id,
                                            worker_name=worker_name,
                                            symbol=params.get('pair', 'unknown'),
                                            direction=params.get('action', 'unknown'),
                                            amount=params.get('amount', 0),
                                            expiration_duration=params.get('expiration_duration', 0)
                                        )
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

                                # --- NEW: Process trade result directly in worker ---
                                if status in ["win", "loose"] and DATABASE_AVAILABLE and db_instance:
                                    try:
                                        # Update database
                                        parsed_status = 'loss' if status == 'loose' else status
                                        db_instance.update_trade_result(trade_id, parsed_status, profit)
                                        worker_log(worker_name, f"Database updated for trade {trade_id}: {status}", "DEBUG")
                                        
                                        # Notify Enhanced Martingale Manager
                                        if MARTINGALE_AVAILABLE and martingale_manager_instance:
                                            # The handle_trade_result expects 'loose' as 'loss'
                                            martingale_status = 'loss' if status == 'loose' else 'loss' if status == 'loss' else status
                                            martingale_manager_instance.handle_trade_result(trade_id, martingale_status, profit)
                                            worker_log(worker_name, f"Enhanced Martingale handled trade {trade_id} result: {martingale_status}", "DEBUG")
                                    except Exception as e_process_result:
                                        worker_log(worker_name, f"Error processing trade result in worker (DB/Martingale): {e_process_result}", "ERROR")
                                        import traceback
                                        worker_log(worker_name, f"Result processing traceback: {traceback.format_exc()}", "ERROR")
                                # --- END NEW ---

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
                        # Start monitoring in a separate thread - NON-BLOCKING
                        monitor_thread = threading.Thread(
                            target=monitor_trade_thread,
                            args=(worker_name, api, trade_id, expiration_time, symbol, request_id, response_queue, db_instance, martingale_manager_instance),
                            daemon=True  # Daemon thread will exit when main process exits
                        )
                        monitor_thread.start()
                        
                        # Send immediate response that monitoring has started
                        response = {'request_id': request_id, 'status': 'success', 
                                   'message': f'Started monitoring trade {trade_id} in background thread'}
                        worker_log(worker_name, f"Started background monitoring thread for trade {trade_id}", "DEBUG")

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
