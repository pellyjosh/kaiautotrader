import time
from pocketoptionapi.stable_api import PocketOption
import pocketoptionapi.global_value as global_value

# --- Configuration ---
# ssid = """42["auth",{"session":"a:4:{s:10:\\"session_id\\";s:32:\\"4f46be8b31aea45b89855a575d82518a\\";s:10:\\"ip_address\\";s:14:\\"105.113.62.151\\";s:10:\\"user_agent\\";s:84:\\"Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:140.0) Gecko/20100101 Firefox/140.0\\";s:13:\\"last_activity\\";i:1750081924;}ea246a0c444dc18d9f286568ceb8e280","isDemo":0,"uid":104296609,"platform":1,"isFastHistory":true}]"""
ssid = """42["auth",{"session":"bpajv9apd668u8qkcdp4i34vc0","isDemo":1,"uid":104296609,"platform":1,"isFastHistory":true}]"""
demo = True

_api_instance = None
_logger_initialized = False

def _ensure_logger_initialized(name="PocketConnector"):
    """Initializes logger if not already done by the main application."""
    global _logger_initialized
    if not _logger_initialized:
        # Attempt to use existing loglevel if set by main app, else default.
        if not hasattr(global_value, 'loglevel'):
            global_value.loglevel = 'INFO' # Default loglevel for connector if not set
        # The logger in global_value is typically initialized when global_value itself is imported
        # and pocketoptionapi.stable_api.PocketOption is instantiated, which sets up logging.
        # This function primarily ensures we can log from here.
        _logger_initialized = True # Ensure this is set before logging
        global_value.logger(f"[{name}] PocketConnector logger is active.", "DEBUG")


def get_api_instance():
    """
    Returns the PocketOption API instance, creating it if it doesn't exist.
    The PocketOption constructor itself attempts to connect.
    """
    global _api_instance
    _ensure_logger_initialized()

    if _api_instance is None:
        try:
            global_value.logger("[PocketConnector] Creating new PocketOption API instance...", "INFO")
            _api_instance = PocketOption(ssid, demo) # ssid and demo are global in this module
            
            global_value.logger("[PocketConnector] PocketOption instance created. Attempting explicit connect()...", "INFO")
            _api_instance.connect() # Crucial step to start the WebSocket connection process

            # A short pause to allow the connection thread (started by .connect()) to initialize.
            # The actual confirmation of connection (global_value.websocket_is_connected becoming True)
            # will be handled by the check_connection() function, which typically follows this call.
            time.sleep(1) # Brief pause, check_connection will do the longer wait.
            
            global_value.logger("[PocketConnector] connect() called on new instance. Status will be verified by check_connection.", "DEBUG")

        except Exception as e:
            # Log the error with more specific context if possible
            global_value.logger(f"[PocketConnector] Error during PocketOption API instance creation or connect() call: {e}", "CRITICAL")
            _api_instance = None # Ensure instance is None if there was a critical error here
            raise
    return _api_instance

def ensure_connected(timeout_seconds=10):
    """
    Ensures an API instance exists and is connected.
    Returns the API instance if connected, otherwise raises ConnectionError.
    """
    _ensure_logger_initialized()
    global_value.logger(f"[PocketConnector] Attempting to ensure connection (timeout: {timeout_seconds}s)...", "INFO")

    # First, try to get/create an API instance.
    # get_api_instance() attempts connection during initialization and logs.
    # It will raise an exception if PocketOption(ssid, demo) fails critically.
    try:
        api = get_api_instance()
    except Exception as e:
        # get_api_instance already logs this, but we re-raise as ConnectionError
        # for consistency in what ensure_connected signals.
        global_value.logger(f"[PocketConnector] ensure_connected: Failed during get_api_instance: {e}", "ERROR")
        raise ConnectionError(f"Failed to initialize PocketOption API instance: {e}")

    if not api:
        # This case should ideally be covered by exceptions from get_api_instance,
        # but as a safeguard:
        global_value.logger("[PocketConnector] ensure_connected: get_api_instance returned None without an exception.", "CRITICAL")
        raise ConnectionError("Failed to obtain PocketOption API instance (returned None).")

    # Now, explicitly check the connection status, potentially waiting.
    # check_connection uses the _api_instance set by get_api_instance.
    if check_connection(timeout_seconds):
        global_value.logger("[PocketConnector] ensure_connected: Connection successfully established and verified.", "INFO")
        return api  # Return the instance, as expected by bot.py
    else:
        # check_connection would have logged the specific reason for timeout/failure.
        global_value.logger("[PocketConnector] ensure_connected: Failed to verify connection after checks.", "ERROR")
        raise ConnectionError(f"Failed to connect to PocketOption and verify within {timeout_seconds} seconds.")

def check_connection(timeout_seconds=10):
    """
    Checks if the WebSocket is connected and API is ready (balance retrievable).
    Waits up to timeout_seconds.
    Returns True if fully connected and ready, False otherwise.
    """
    _ensure_logger_initialized()
    start_time = time.time()
    global_value.logger(f"[PocketConnector] Verifying connection and API readiness (timeout: {timeout_seconds}s)...", "DEBUG")

    # Phase 1: Wait for WebSocket to be connected
    while not global_value.websocket_is_connected:
        if time.time() - start_time > timeout_seconds:
            global_value.logger(f"[PocketConnector] Timeout: WebSocket not connected within {timeout_seconds}s (global_value.websocket_is_connected is False).", "WARNING")
            return False
        time.sleep(0.2) # Short sleep while polling websocket_is_connected

    global_value.logger("[PocketConnector] WebSocket is connected. Now checking for API readiness (e.g., balance).", "DEBUG")

    # Phase 2: Wait for balance to be available (indicates API is more fully initialized)
    # Ensure _api_instance is available
    if not _api_instance:
        global_value.logger("[PocketConnector] _api_instance is None during readiness check. This is unexpected.", "ERROR")
        return False

    balance_value = None
    # Loop to check for balance, but respect the overall timeout
    while True: 
        # Check overall timeout first
        if time.time() - start_time > timeout_seconds:
            global_value.logger(f"[PocketConnector] Timeout: Balance not available (current value: {balance_value}) within overall {timeout_seconds}s.", "WARNING")
            return False

        if not global_value.websocket_is_connected:
            # If websocket disconnects during this phase
            global_value.logger("[PocketConnector] WebSocket disconnected while waiting for balance. Connection lost.", "WARNING")
            return False

        try:
            balance_value = _api_instance.get_balance()
        except Exception as e:
            global_value.logger(f"[PocketConnector] Error calling get_balance(): {e}. Retrying...", "WARNING")
            # Continue to retry within the timeout

        if balance_value is not None:
            green_color_code = "\033[92m"
            reset_color_code = "\033[0m"
            log_message = f'{green_color_code}[PocketConnector] Account Balance successfully retrieved: {balance_value}{reset_color_code}'
            global_value.logger(log_message, "INFO")
            return True
        
        # If balance is None, but websocket is connected, it means the profile/balance data
        # hasn't arrived or been processed by the underlying library yet.
        time.sleep(0.5) # Wait a bit longer for balance data to arrive

    # Fallback, though the loop logic should handle returning True or False based on timeout/success
    # This part of the original code is now covered by the loop above.
    # If it reaches here, it implies an issue with the loop logic, which shouldn't happen.
    global_value.logger("[PocketConnector] Exited check_connection logic unexpectedly.", "ERROR")
    return False
