# detectsignal.py
import asyncio
import time # Import the time module
import re
import threading
from telethon import TelegramClient, events

# --- Globals to be initialized by bot.py ---
_api_object = None
_global_value_module = None
_buy_function = None
_prepare_history_function = None
_logger_function = None # Shortcut for _global_value_module.logger


API_ID ='23324590'
API_HASH ='fdcd53d426aebd07096ff326bb124397'
# TARGET_GROUP_IDENTIFIER = -1002546061495  #Test Channel
TARGET_GROUP_IDENTIFIER = -1002153677822
PHONE_NUMBER = '+2348101572723'
SESSION_NAME = 'my_signal_listener'
DEFAULT_TRADE_AMOUNT = 1

# API_ID ='20304811'
# API_HASH ='abeb329421c4ba8b2958ca3d3e645068'
# TARGET_GROUP_IDENTIFIER = -1002360516634
# PHONE_NUMBER = '+2348085341275'
# SESSION_NAME = 'ton_signal_listener'
# DEFAULT_TRADE_AMOUNT = 1000

DEFAULT_EXPIRATION_SECONDS = 10

# For two-part signals
_pending_first_part_signals = {} # Key: chat_id, Value: {'pair': str, 'timeframe_minutes': int, 'timestamp': float}
PARTIAL_SIGNAL_TIMEOUT_SECONDS = 1000 # Timeout for waiting for the second part of a signal

_telethon_listener_started_successfully = False

def _log(message, level="INFO"):
    if _logger_function:
        _logger_function(f"[SignalDetector] {message}", level)
    else:
        print(f"[{level}][SignalDetector] {message}")

def _normalize_pair_for_new_format(raw_pair_text):
    """
    Normalizes pair string from formats like "BHD/CNY OTC", "EURUSD", "AUD/CAD_otc".
    Output: "BHDCNY_otc", "EURUSD", "AUDCAD_otc" (slash removed, _otc is lowercase, base is uppercase)
    """
    normalized_pair = raw_pair_text.strip() # Keep original case for a moment for OTC checks

    # Standardize OTC suffix to _otc and ensure base is uppercase and slashes removed
    if normalized_pair.upper().endswith(" OTC"): # Handles "BHD/CNY OTC"
        base = normalized_pair[:-4].strip()
        normalized_pair = base.upper().replace("/", "") + "_otc"
    elif "_otc" in normalized_pair.lower(): # Handles "AUD/CAD_otc" or "EURUSD_otc" or "EURUSD_OTC"
        # Split by _otc (case-insensitive), take the first part, uppercase, remove slashes, add _otc
        parts = re.split(r'_otc', normalized_pair, flags=re.IGNORECASE)
        normalized_pair = parts[0].upper().replace("/", "") + "_otc"
    else: # Handles "EURUSD" or "USD/JPY"
        normalized_pair = normalized_pair.upper().replace("/", "")
        
    # Ensure any remaining _OTC (if somehow missed) becomes _otc - defensive
    normalized_pair = normalized_pair.replace("_OTC", "_otc")
    return normalized_pair

def _parse_first_part_signal(message_text):
    """
    Parses the first part of a two-part signal, e.g., "BHD/CNY OTC M1".
    Returns {'pair': 'BHD/CNY_otc', 'timeframe_minutes': 1} or None.
    """
    # Expects message like "BHD/CNY OTC M1" or "EURUSD M5"
    # Regex matches the pair part (including optional OTC) and the M<digits> timeframe
    match = re.fullmatch(r"([\w\/]+(?:\s+OTC)?)\s+M(\d+)", message_text.strip(), re.IGNORECASE)
    if match:
        raw_pair_text = match.group(1)
        timeframe_minutes = int(match.group(2))
        
        normalized_pair = _normalize_pair_for_new_format(raw_pair_text)

        return {'pair': normalized_pair, 'timeframe_minutes': timeframe_minutes}
    return None

def _parse_second_part_signal(message_text):
    """
    Parses the second part of a two-part signal, e.g., "🔼UP🔼", "⬆️ UP ⬆️", "🔽DOWN🔽", or "⬇️ DOWN ⬇️".
    Returns 'call', 'put', or None.
    """
    txt = message_text.strip()
    # Check for new arrow format first as it was provided in the log
    if re.fullmatch(r"⬆️\s*UP\s*⬆️", txt, re.IGNORECASE):
        return 'call'
    if re.fullmatch(r"⬇️\s*DOWN\s*⬇️", txt, re.IGNORECASE): # Assuming a similar down arrow
        return 'put'
    # Fallback to old arrow format if needed, or remove if only new format is used
    if re.fullmatch(r"🔼\s*UP\s*🔼", txt, re.IGNORECASE): # Original UP pattern
        return 'call'
    if re.fullmatch(r"🔽\s*DOWN\s*🔽", txt, re.IGNORECASE): # Original DOWN pattern
        return 'put'
    return None

def parse_signal_from_message(message_text):
    """
    Parses a message to extract trading signal parameters.
    !!! THIS FUNCTION IS CRITICAL AND MUST BE CUSTOMIZED !!!
    It needs to match the specific format of signals in your target group.

    Returns a dictionary like:
    {'pair': 'EURUSD_otc', 'action': 'call', 'amount': 10, 'expiration': 60}
    or None if no valid signal is found.
    """
    #_log(f"Attempting to parse message: \"{message_text}\"", "DEBUG")

    # --- Parsing Logic for TWSBINARY format ---
    # Example:
    # 🔴 PUT Signal on USDCADm
    # Price: 1.36462
    # Attempt: 1
    # Expiration: 3 minutes

    # Regex to capture Action (PUT/CALL), Pair, and Expiration
    # It looks for lines starting with "🔴 PUT Signal on", "🟢 CALL Signal on", or similar
    # and a line starting with "Expiration:"
    signal_pattern = re.compile(
        r"(?:🔴|🟢)\s*(PUT|CALL)\s*Signal\s*on\s*([\w\/-]+(?:m)?)\s*\n"  # Action and Pair (e.g., USDCADm)
        r".*?"  # Non-greedy match for any lines in between (like Price, Attempt)
        r"Expiration:\s*(\d+)\s*(minute|minutes|second|seconds|hour|hours)",  # Expiration value and unit
        re.IGNORECASE | re.DOTALL  # DOTALL allows . to match newlines
    )

    match = signal_pattern.search(message_text)

    if match:
        action_str = match.group(1).upper()
        raw_pair_str_from_signal = match.group(2).strip() # e.g., "USDCADm", "EUR/USD_otc"
        
        # 1. Handle potential trailing 'm' (specific to TWSBINARY source)
        temp_pair = raw_pair_str_from_signal
        if temp_pair.upper().endswith('M') and len(temp_pair) > 1 and temp_pair[-2].isalpha():
            if not temp_pair.upper().endswith("_OTCM"): # Avoid stripping M from a name like "XYZ_OTCM"
                 temp_pair = temp_pair[:-1] # e.g., "USDCADm" -> "USDCAD"

        # 2. Normalize the processed pair string (e.g., "USDCAD", "EUR/USD_otc")
        #    This logic mirrors _normalize_pair_for_new_format for consistency.
        normalized_intermediate_pair = temp_pair 
        if normalized_intermediate_pair.upper().endswith(" OTC"): # Unlikely for TWSBINARY regex
            base = normalized_intermediate_pair[:-4].strip()
            pair_str = base.upper().replace("/", "") + "_otc"
        elif "_otc" in normalized_intermediate_pair.lower(): # Handles "EUR/USD_otc"
            parts = re.split(r'_otc', normalized_intermediate_pair, flags=re.IGNORECASE)
            pair_str = parts[0].upper().replace("/", "") + "_otc" # e.g. "EURUSD_otc"
        else: # Handles "USDCAD" or "EUR/USD" (if _otc was not part of it)
            pair_str = normalized_intermediate_pair.upper().replace("/", "") # e.g. "USDCAD", "EURUSD"
        
        # Ensure any remaining _OTC becomes _otc - defensive
        pair_str = pair_str.replace("_OTC", "_otc")

        exp_value = int(match.group(3))
        exp_unit = match.group(4).lower()

        action = 'put' if action_str == 'PUT' else 'call'
        
        expiration_seconds = DEFAULT_EXPIRATION_SECONDS 
        if 'minute' in exp_unit: expiration_seconds = exp_value * 60
        elif 'second' in exp_unit: expiration_seconds = exp_value
        elif 'hour' in exp_unit: expiration_seconds = exp_value * 3600
        amount = DEFAULT_TRADE_AMOUNT

        _log(f"Signal parsed: Pair={pair_str}, Action={action}, Amount=${amount}, Expiration={expiration_seconds}s", "INFO")
        return {'pair': pair_str, 'action': action, 'amount': amount, 'expiration': expiration_seconds}

    # --- Fallback to previous Example Parsing Logic (Pattern 1) ---
    # This can be kept if you expect other signal formats as well.
    pattern1_fallback = re.compile(
        r"([\w#/-]+(?:_otc)?)\s+"  # Pair (e.g., EURUSD_otc, #AAPL, BTC/USD)
        r"(CALL|PUT|BUY|SELL)\s+"   # Action
        r"(?:AMT\s*(\d+)\s+)?"      # Optional Amount (e.g., AMT 100)
        r"(?:EXP\s*(\d+)([smh]))?", # Optional Expiration (e.g., EXP 60s, EXP 5m)
        re.IGNORECASE
    )
    match_fallback = pattern1_fallback.match(message_text.strip()) # Use .match() and .strip()
    if match_fallback:
        pair_raw_fallback = match_fallback.group(1).strip()
        action_str = match_fallback.group(2).upper()
        amount_str = match_fallback.group(3)
        exp_val_str = match_fallback.group(4)
        exp_unit = match_fallback.group(5)

        # Normalize pair for fallback pattern
        if pair_raw_fallback.startswith("#"): # Special case for symbols like #AAPL
            pair = pair_raw_fallback.upper() 
        elif pair_raw_fallback.upper().endswith(" OTC"): # Unlikely for this regex pattern
            base_fallback = pair_raw_fallback[:-4].strip()
            pair = base_fallback.upper().replace("/", "") + "_otc"
        elif "_otc" in pair_raw_fallback.lower():
            parts_fallback = re.split(r'_otc', pair_raw_fallback, flags=re.IGNORECASE)
            pair = parts_fallback[0].upper().replace("/", "") + "_otc"
        else: # Handles "BTC/USD", "EURUSD"
            pair = pair_raw_fallback.upper().replace("/", "")

        action_fallback = 'call' if action_str in ['CALL', 'BUY'] else 'put'
        
        amount_fallback = int(amount_str) if amount_str else DEFAULT_TRADE_AMOUNT
        
        expiration_fallback = DEFAULT_EXPIRATION_SECONDS
        if exp_val_str and exp_unit:
            exp_val = int(exp_val_str)
            if exp_unit.lower() == 's':
                expiration_fallback = exp_val
            elif exp_unit.lower() == 'm':
                expiration_fallback = exp_val * 60
            elif exp_unit.lower() == 'h':
                expiration_fallback = exp_val * 3600
        
        # Ensure any remaining _OTC becomes _otc - defensive
        pair = pair.replace("_OTC", "_otc")
        
        _log(f"Signal parsed: Pair={pair}, Action={action_fallback}, Amount=${amount_fallback}, Expiration={expiration_fallback}s", "INFO")
        return {'pair': pair, 'action': action_fallback, 'amount': amount_fallback, 'expiration': expiration_fallback}

    #_log(f"No parsable signal found in message.", "DEBUG")
    return None


# def _place_trade_from_signal(pair, action, amount, expiration_duration):
#     """
#     Internal helper to place a trade.
#     """
#     if not all([_global_value_module, _api_object, _buy_function, _prepare_history_function]):
#         _log("Telethon signal components not fully initialized. Cannot place trade.", "ERROR")
#         return

#     if not _global_value_module.websocket_is_connected:
#         _log("PocketOption API not connected. Cannot place trade.", "ERROR")
#         return

#     if not _global_value_module.pairs:
#         _log("Pair list (global_value.pairs) is empty. Attempting to fetch.", "WARNING")
#         if not _prepare_history_function():
#             _log("Could not fetch/verify pair list from PocketOption. Trade aborted.", "ERROR")
#             return
#         _log(f"Pair list refreshed. {len(_global_value_module.pairs)} pairs loaded.", "INFO")

#     if pair not in _global_value_module.pairs:
#         warning_msg = (f"Warning: Pair '{pair}' not found in the pre-loaded list of tradable assets. "
#                        f"Ensure the pair name is exact (as per PocketOption API) and the asset is currently tradable. "
#                        f"Attempting trade anyway...")
#         _log(warning_msg, "WARNING")

#     _log(f"Attempting trade from signal: Amount: {amount}, Pair: {pair}, Action: {action}, Expiration: {expiration_duration}s", "INFO")

#     trade_thread = threading.Thread(target=_buy_function, args=(amount, pair, action, expiration_duration))
#     trade_thread.start()

#     _log(f"Trade order for {pair}: {action.upper()} ${amount} for {expiration_duration}s initiated via Telethon signal.", "INFO")

def _place_trade_from_signal(pair, action, amount, expiration_duration):
    """
    Internal helper to place a trade.
    """
    # ... (initial checks for module initialization and websocket connection) ...

    if not _global_value_module.pairs:
        _log("Pair list (global_value.pairs) is empty. Attempting to fetch.", "WARNING")
        if not _prepare_history_function():
            _log("Could not fetch/verify pair list from PocketOption. Trade aborted.", "ERROR")
            return
        _log(f"Pair list refreshed. {len(_global_value_module.pairs)} pairs loaded.", "INFO")

    # Check if the exact pair from the signal is in our list of (presumably active) pairs
    if pair not in _global_value_module.pairs:
        warning_msg = (f"Warning: Pair '{pair}' not found in the pre-loaded list of tradable assets "
                       f"(which is populated based on active status and payout criteria). "
                       f"This could mean '{pair}' is currently inactive or doesn't meet payout criteria. "
                       f"Attempting trade with '{pair}' as specified in the signal.")
        _log(warning_msg, "WARNING") # Log the warning
        _log(f"Trade for '{pair}' will NOT be placed as it's not in the active/valid list.", "INFO")
        return # Explicitly stop further processing for this signal
    else:
        _log(f"Pair '{pair}' from signal found in the pre-loaded list of tradable assets.", "INFO")

    _log(f"Attempting trade from signal: Amount: {amount}, Pair: {pair}, Action: {action}, Expiration: {expiration_duration}s", "INFO") # Using original 'pair'

    trade_thread = threading.Thread(target=_buy_function, args=(amount, pair, action, expiration_duration))
    trade_thread.start()

    _log(f"Trade order for {pair}: {action.upper()} ${amount} for {expiration_duration}s initiated via Telethon signal.", "INFO")

# Telethon event handler for new messages
async def new_message_handler(event):
    message_text = event.message.message
    sender = await event.get_sender()
    sender_id = sender.id if sender else "UnknownSender"
    chat = await event.get_chat()
    chat_title = chat.title if hasattr(chat, 'title') else (chat.username if hasattr(chat, 'username') else str(chat.id))

    _log(f"Msg from group '{chat_title}' (ID: {event.chat_id}, SenderID: {sender_id}): \"{message_text}\"", "DEBUG")

    # 1. Check if this message is the SECOND PART of a pending two-part signal
    if event.chat_id in _pending_first_part_signals:
        pending_signal_info = _pending_first_part_signals[event.chat_id]
        
        # Check for timeout of the pending first part
        if time.time() - pending_signal_info['timestamp'] > PARTIAL_SIGNAL_TIMEOUT_SECONDS:
            _log(f"Pending signal for chat {event.chat_id} ({pending_signal_info['pair']}) timed out. Clearing.", "INFO")
            del _pending_first_part_signals[event.chat_id]
        else:
            action = _parse_second_part_signal(message_text)
            if action:
                _log(f"Second part '{action.upper()}' received for pending signal: {pending_signal_info['pair']} M{pending_signal_info['timeframe_minutes']}", "INFO")
                
                expiration_seconds = pending_signal_info['timeframe_minutes'] * 60
                
                signal_data_for_trade = {
                    'pair': pending_signal_info['pair'],
                    'action': action,
                    'amount': DEFAULT_TRADE_AMOUNT, # Or customize if amount can be in first/second part
                    'expiration': expiration_seconds
                }
                
                _place_trade_from_signal(
                    pair=signal_data_for_trade['pair'],
                    action=signal_data_for_trade['action'],
                    amount=signal_data_for_trade['amount'],
                    expiration_duration=signal_data_for_trade['expiration']
                )
                del _pending_first_part_signals[event.chat_id] # Clear the pending signal
                return # Signal processed

    # 2. If not a second part, check if it's the FIRST PART of the new two-part signal
    first_part_data = _parse_first_part_signal(message_text)
    if first_part_data:
        if event.chat_id in _pending_first_part_signals:
            _log(f"Overwriting previous pending signal for chat {event.chat_id} with new first part: {first_part_data['pair']} M{first_part_data['timeframe_minutes']}", "WARNING")

        _pending_first_part_signals[event.chat_id] = {
            'pair': first_part_data['pair'],
            'timeframe_minutes': first_part_data['timeframe_minutes'],
            'timestamp': time.time()
        }
        _log(f"First part of two-part signal detected: Pair={first_part_data['pair']}, Timeframe=M{first_part_data['timeframe_minutes']}. Waiting for direction in chat {event.chat_id}.", "INFO")
        return # First part stored, wait for second

    # 3. If not a two-part signal (neither first nor second part), try the original single-message parser
    # This is for existing signal formats like TWSBINARY or the fallback pattern.
    original_format_signal_data = parse_signal_from_message(message_text)
    if original_format_signal_data:
        _log(f"Actionable signal (original single-message format) detected: {original_format_signal_data}", "INFO")
        _place_trade_from_signal(
            pair=original_format_signal_data['pair'],
            action=original_format_signal_data['action'],
            amount=original_format_signal_data['amount'],
            expiration_duration=original_format_signal_data['expiration']
        )
        return

async def _run_telethon_listener_loop():
    """Internal async function to run the Telethon client."""
    global _telethon_listener_started_successfully

    if not API_ID or API_ID == 1234567 or not API_HASH or API_HASH == 'YOUR_API_HASH' or not PHONE_NUMBER or PHONE_NUMBER == '+12345678900':
        _log("Telethon API_ID, API_HASH, or PHONE_NUMBER not configured correctly. Please update them in detectsignal.py.", "CRITICAL")
        _log("Telethon listener will not start.", "CRITICAL")
        return False # Indicate failure
    
    if not TARGET_GROUP_IDENTIFIER or TARGET_GROUP_IDENTIFIER == -1001234567890 and isinstance(TARGET_GROUP_IDENTIFIER, int):
         _log(f"TARGET_GROUP_IDENTIFIER is set to a placeholder value: {TARGET_GROUP_IDENTIFIER}. Please configure it.", "CRITICAL")
         _log("Telethon listener will not start.", "CRITICAL")
         return False # Indicate failure

    # system_version is sometimes needed for Telethon to work smoothly with Telegram's API layers.
    # You can usually leave it or use a recent version string if you encounter issues.
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

    try:
        _log("Connecting Telethon client...", "INFO")
        await client.connect()

        if not await client.is_user_authorized():
            _log("User not authorized. Sending code request to phone number...", "INFO")
            await client.send_code_request(PHONE_NUMBER)
            # Inform the main thread or user that code input is needed.
            _log(f"Telethon is waiting for you to enter the code sent to {PHONE_NUMBER}. Please check your Telegram messages.", "IMPORTANT") # Custom level or use INFO
            while True:
                try:
                    code = input(f"Telethon: Enter the code you received for {PHONE_NUMBER}: ")
                    await client.sign_in(PHONE_NUMBER, code)
                    break # Exit loop on successful sign-in
                except EOFError: # Happens if input() is called in a non-interactive environment
                    _log("Telethon: Could not read code from input (EOFError). Ensure you are running this interactively for the first login.", "ERROR")
                    await client.disconnect()
                    return False # Indicate failure
                except Exception as e: # Catch specific errors like SessionPasswordNeededError if 2FA is on
                    _log(f"Telethon sign-in error: {e}. If you have 2FA, you might need to provide password.", "ERROR")
                    # Example for 2FA:
                    # if 'password' in str(e).lower(): # Crude check for password needed
                    #     try:
                    #         password = input("Telethon: 2FA Password needed: ")
                    #         await client.sign_in(password=password)
                    #         break
                    #     except Exception as p_err:
                    #         _log(f"Telethon 2FA password error: {p_err}", "ERROR")
                    #         await client.disconnect()
                    #         return False # Indicate failure
                    _log("Try entering code again or check 2FA.", "INFO")
                    # If sign-in fails repeatedly, you might want to break or exit.

        if await client.is_user_authorized():
            _log("Telethon client connected and authorized successfully.", "INFO")
            
            # Add event handler for new messages in the target chat
            client.add_event_handler(new_message_handler, events.NewMessage(chats=[TARGET_GROUP_IDENTIFIER]))
            _log(f"Telethon event handler added for target: {TARGET_GROUP_IDENTIFIER}", "INFO")
            _log("Telethon listener started. Monitoring for new messages...")
            _telethon_listener_started_successfully = True # Set flag on successful start
            await client.run_until_disconnected() # Runs indefinitely until client disconnects or an error
        else:
            _log("Telethon authorization failed. Listener will not start.", "ERROR")
            return False # Indicate failure

    except ConnectionError as e:
        _log(f"Telethon connection error: {e}. Check network or Telegram status.", "CRITICAL")
        return False # Indicate failure
    except Exception as e:
        _log(f"An unexpected error occurred in Telethon listener: {e}", "CRITICAL")
        return False # Indicate failure
    finally:
        if client.is_connected():
            _log("Disconnecting Telethon client...", "INFO")
            await client.disconnect()
        _log("Telethon client session ended.", "INFO")
    return _telethon_listener_started_successfully # Return the status


def start_signal_detector(api_instance, global_value_mod, buy_func, prep_history_func):
    """
    Initializes and starts the Telethon signal detector in a separate thread.
    Returns True if the initial setup checks pass and thread starts, False otherwise.
    """
    global _api_object, _global_value_module, _buy_function, _prepare_history_function, _logger_function
    _api_object = api_instance
    _global_value_module = global_value_mod
    _buy_function = buy_func
    _prepare_history_function = prep_history_func
    
    if hasattr(_global_value_module, 'logger'):
        _logger_function = _global_value_module.logger
    else:
        print("[CRITICAL][detectsignal] global_value.logger not found. Telegram logging will be basic")

    if not all([_api_object, _global_value_module, _buy_function, _prepare_history_function]):
        _log("One or more essential components not provided to Telethon signal detector. Cannot start.", "CRITICAL")
        return False

    #_log("Start Check", "CRITICAL")
    _log("Initializing Telethon signal detector...", "INFO")

    # Reset flag before starting
    global _telethon_listener_started_successfully
    _telethon_listener_started_successfully = False

    # Telethon uses asyncio. We run its event loop in a dedicated thread
    # because the main bot.py might not be asyncio-based.
    def telethon_thread_runner():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # The _run_telethon_listener_loop now handles its own try/except/finally for client.disconnect
        # and returns a status. The thread_runner's main job is to run this loop.
        loop.run_until_complete(_run_telethon_listener_loop())
        # Loop closure is handled if _run_telethon_listener_loop exits or errors out.
        # For graceful shutdown on KeyboardInterrupt, _run_telethon_listener_loop would need to catch it.


    telethon_listener_thread = threading.Thread(target=telethon_thread_runner, name="TelethonSignalDetectorThread")
    # Set daemon to True so this thread exits when the main program exits.
    # If you need more graceful shutdown (e.g., Telethon sending a "goodbye"),
    # you'd set daemon=False and manage its lifecycle more explicitly (e.g., with an event).
    telethon_listener_thread.daemon = True
    telethon_listener_thread.start()
    _log("Telethon signal detector thread started.", "INFO")
    
    # Wait for a short period to see if the Telethon thread sets the success flag
    # This indicates that initial config checks passed and client.run_until_disconnected() was reached.
    # This doesn't guarantee long-term connection, but that initial setup was okay.
    # A more complex solution would use threading.Event for explicit signaling.    
    # Increase timeout to allow for manual code entry if needed.
    timeout_for_startup_flag = 120  # seconds (2 minutes) - Adjust as needed

    start_wait_time = time.time()
    while not _telethon_listener_started_successfully and (time.time() - start_wait_time) < timeout_for_startup_flag:
        if not telethon_listener_thread.is_alive():
            _log("Telethon listener thread terminated prematurely during startup check.", "ERROR")
            return False # Thread died, so it definitely didn't start successfully
        time.sleep(0.5)

    if not _telethon_listener_started_successfully:
        _log("Telethon listener did not confirm successful startup within timeout or config check failed.", "WARNING")
        # The thread itself would have logged the CRITICAL config error if that was the cause.
    return _telethon_listener_started_successfully
