# detectsignal.py
import asyncio
import os # Import the os module
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

# --- Configuration for multiple Telegram accounts ---
TELEGRAM_ACCOUNTS_CONFIG = [
    {
        'API_ID': '23324590',
        'API_HASH': 'fdcd53d426aebd07096ff326bb124397',
        'PHONE_NUMBER': '+2348101572723',
        'SESSION_NAME': 'my_signal_listener', # Ensure unique session names
        'TARGET_GROUP_IDENTIFIER': -1002153677822, # Group for Account 1
        # 'TARGET_GROUP_IDENTIFIER' : -1002546061495,  #Test Channel
        'ENABLED': True # Allows you to easily enable/disable this account
    },
    {
        'API_ID': '20304811', # Replace with actual API_ID for Account 2
        'API_HASH': 'abeb329421c4ba8b2958ca3d3e645068', # Replace with actual API_HASH for Account 2
        'PHONE_NUMBER': '+2348085341275', # Replace with actual Phone Number for Account 2
        'SESSION_NAME': 'ton_signal_listener', # Ensure unique session names
        'TARGET_GROUP_IDENTIFIER': -1002360516634, # Example: Group for Account 2
        # 'TARGET_GROUP_IDENTIFIER' : -1002546061495,  #Test Channel
        'ENABLED': True # Allows you to easily enable/disable this account
    }
    # Add more account configurations as dictionaries in this list if needed
]

DEFAULT_TRADE_AMOUNT = 1
DEFAULT_EXPIRATION_SECONDS = 10

# For two-part signals
_pending_first_part_signals = {} # Key: chat_id, Value: {'pair': str, 'timeframe_minutes': int, 'timestamp': float}
PARTIAL_SIGNAL_TIMEOUT_SECONDS = 1000 # Timeout for waiting for the second part of a signal

# This will be a list of booleans, one for each configured and enabled client
_telethon_listeners_started_successfully = []


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
    Parses the second part of a two-part signal, e.g., "🔼UP🔼",\
        \⬆️ UP ⬆️", "🔽DOWN🔽", or "⬇️ DOWN ⬇️".
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

def _place_trade_from_signal(pair, action, amount, expiration_duration, target_po_worker_name_unused=None): # target_po_worker_name_unused to keep signature if needed elsewhere, but will be ignored
    """
    Internal helper to place a trade.
    Now attempts to place the trade on ALL enabled PocketOption workers.
    """
    # ... (initial checks for module initialization and websocket connection) ...

    if not _global_value_module.pairs:
        _log("Pair list (global_value.pairs) is empty. Attempting to fetch.", "WARNING")
        # Fetch pairs using a default worker (first enabled) for the main process's list.
        # This list is for preliminary checks; actual tradeability is per worker.
        # The _prepare_history_function is `prepare_history_via_worker_manager` from bot.py
        # Passing None will make it use its default logic (e.g., first enabled worker).
        if not _prepare_history_function(target_po_account_name=None):
            _log("Could not fetch/verify pair list from PocketOption. Trade aborted.", "ERROR")
            return
        _log(f"Pair list refreshed. {len(_global_value_module.pairs)} pairs loaded.", "INFO")
        
    # Check if the exact pair from the signal is in our list of (presumably active) pairs
    if pair not in _global_value_module.pairs:
        warning_msg = (f"Warning: Pair '{pair}' not found in the pre-loaded list of tradable assets "
                       f"(main process's global_value.pairs). This list might not reflect individual worker states. "
                       f"This could mean '{pair}' is currently inactive or doesn't meet payout criteria. "
                       f"Attempting trade with '{pair}' as specified in the signal.")
        _log(warning_msg, "WARNING") # Log the warning
        # In a multi-worker setup, the main process's `global_value.pairs` might not be the
        # single source of truth. The worker itself will ultimately decide if it can trade the pair.
        # So, we might allow the trade attempt to proceed to the worker.
        # However, if `prepare_history_func` (now `prepare_history_via_worker_manager`)
        # populates a main process list of known active pairs per worker, that could be checked here.
        # For now, we'll let the worker handle the final pair validation.
        # If you want to pre-filter:
        # _log(f"Trade for '{pair}' will NOT be placed as it's not in the main process's active/valid list.", "INFO")
        # return
        _log(f"Pair '{pair}' not in main process's global_value.pairs. Worker will perform final validation.", "DEBUG")

    else:
        _log(f"Pair '{pair}' from signal found in the pre-loaded list of tradable assets.", "INFO")

    _log(f"Attempting trade from signal: Amount: {amount}, Pair: {pair}, Action: {action}, Expiration: {expiration_duration}s", "INFO") # Using original 'pair'

    # _buy_function is `place_trade_via_worker_manager` from bot.py
    # It expects (amount, pair, action, expiration_duration, target_po_account_name=None)
    # We pass 'ALL_ENABLED_WORKERS' to target all.
    trade_thread = threading.Thread(target=_buy_function, args=(amount, pair, action, expiration_duration, 'ALL_ENABLED_WORKERS'))
    trade_thread.start()
    
    _log(f"Trade order for {pair}: {action.upper()} ${amount} for {expiration_duration}s initiated via Telethon signal.", "INFO")

# Telethon event handler for new messages
async def new_message_handler(event):
    message_text = event.message.message
    sender = await event.get_sender()
    sender_id = sender.id if sender else "UnknownSender"
    chat = await event.get_chat()
    chat_title = chat.title if hasattr(chat, 'title') else (chat.username if hasattr(chat, 'username') else str(chat.id))
    current_time = time.time()

    # Identify which Telethon account received this message for logging/routing
    # This assumes `client.session.filename` gives the session name from TELEGRAM_ACCOUNTS_CONFIG
    # This is a bit of a hack; a cleaner way would be to pass the account_config into the handler if possible,
    # or store a mapping from client instance to account_config. The session filename includes the path.
    raw_session_filename = event.client.session.filename 
    # Extract just the session name part (e.g., "my_signal_listener" from "telegram_sessions/my_signal_listener.session")
    telethon_session_name_only = os.path.basename(raw_session_filename).replace(".session", "")

    # The PO_WORKER_NAME from TELEGRAM_ACCOUNTS_CONFIG is no longer used for direct routing here,
    # as trades are sent to all enabled PO workers.
    # current_telethon_config = next((acc for acc in TELEGRAM_ACCOUNTS_CONFIG if acc['SESSION_NAME'] == telethon_session_name_only), None)
    
    log_prefix_for_handler = f"[SignalDetector-{telethon_session_name_only}]"

    _log(f"{log_prefix_for_handler} Msg from group '{chat_title}' (ID: {event.chat_id}, SenderID: {sender_id}): \"{message_text}\"", "DEBUG")

    # 1. Check if this message is the SECOND PART of a pending two-part signal
    if event.chat_id in _pending_first_part_signals:
        pending_signal_info = _pending_first_part_signals[event.chat_id]
        
        # Check for timeout of the pending first part
        if time.time() - pending_signal_info['timestamp'] > PARTIAL_SIGNAL_TIMEOUT_SECONDS:
            _log(f"{log_prefix_for_handler} Pending signal for chat {event.chat_id} ({pending_signal_info['pair']}) timed out. Clearing.", "INFO")
            del _pending_first_part_signals[event.chat_id]
        else:
            action = _parse_second_part_signal(message_text)
            if action:
                _log(f"{log_prefix_for_handler} Second part '{action.upper()}' received for pending signal: {pending_signal_info['pair']} M{pending_signal_info['timeframe_minutes']}", "INFO")
                
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
                    expiration_duration=signal_data_for_trade['expiration'],
                    # target_po_worker_name is no longer passed here for individual routing
                )
                del _pending_first_part_signals[event.chat_id] # Clear the pending signal
                return # Signal processed

    # 2. If not a second part, check if it's the FIRST PART of the new two-part signal
    first_part_data = _parse_first_part_signal(message_text)
    if first_part_data:
        if event.chat_id in _pending_first_part_signals:
            _log(f"{log_prefix_for_handler} Overwriting previous pending signal for chat {event.chat_id} with new first part: {first_part_data['pair']} M{first_part_data['timeframe_minutes']}", "WARNING")

        _pending_first_part_signals[event.chat_id] = {
            'pair': first_part_data['pair'],
            'timeframe_minutes': first_part_data['timeframe_minutes'],
            'timestamp': time.time()
        }
        _log(f"{log_prefix_for_handler} First part detected: Pair={first_part_data['pair']}, M{first_part_data['timeframe_minutes']}. Waiting for direction in chat {event.chat_id}.", "INFO")
        return # First part stored, wait for second

    # 3. If not a two-part signal (neither first nor second part), try the original single-message parser
    # This is for existing signal formats like TWSBINARY or the fallback pattern.
    original_format_signal_data = parse_signal_from_message(message_text)
    if original_format_signal_data:
        _log(f"{log_prefix_for_handler} Actionable signal (original single-message format) detected: {original_format_signal_data}", "INFO")
        _place_trade_from_signal(
            pair=original_format_signal_data['pair'],
            action=original_format_signal_data['action'],
            amount=original_format_signal_data['amount'],
            expiration_duration=original_format_signal_data['expiration'],
            # target_po_worker_name is no longer passed here
        )
        return

async def _run_telethon_listener_loop(account_config, success_flags_list, listener_index):
    """
    Internal async function to run the Telethon client for a single account.
    Updates the success_flags_list for its specific index.
    """
    session_name = account_config['SESSION_NAME']
    api_id = account_config['API_ID']
    api_hash = account_config['API_HASH']
    phone_number = account_config['PHONE_NUMBER']
    target_group = account_config['TARGET_GROUP_IDENTIFIER']

    log_prefix = f"[SignalDetector-{session_name}]"

    # Ensure success_flags_list is initialized for this listener
    if listener_index >= len(success_flags_list):
        _log(f"{log_prefix} Internal error: listener_index out of bounds for success_flags_list.", "CRITICAL")
        return # Should not happen if called correctly

    success_flags_list[listener_index] = False # Default to False

    if not api_id or str(api_id) == '1234567' or not api_hash or api_hash == 'YOUR_API_HASH' or not phone_number or phone_number == '+12345678900':
        _log(f"{log_prefix} API_ID, API_HASH, or PHONE_NUMBER not configured correctly. Listener will not start.", "CRITICAL")
        return

    if not target_group or (isinstance(target_group, int) and target_group == -1001234567890): # Example placeholder check
        _log(f"{log_prefix} TARGET_GROUP_IDENTIFIER ({target_group}) is invalid or a placeholder. Listener will not start.", "CRITICAL")
        return

    # Construct session path
    session_folder = "telegram_sessions"
    if not os.path.exists(session_folder):
        os.makedirs(session_folder)
        _log(f"{log_prefix} Created directory: {session_folder}", "INFO")
    full_session_path = os.path.join(session_folder, session_name)

    client = TelegramClient(full_session_path, api_id, api_hash)

    try:
        _log(f"{log_prefix} Connecting Telethon client...", "INFO")
        await client.connect()

        if not await client.is_user_authorized():
            _log(f"{log_prefix} User not authorized. Sending code request to {phone_number}...", "INFO")
            await client.send_code_request(phone_number)
            _log(f"{log_prefix} Telethon is waiting for you to enter the code sent to {phone_number}. Please check your Telegram messages.", "IMPORTANT")
            while True:
                try:
                    code = input(f"Telethon ({session_name}): Enter the code for {phone_number}: ")
                    await client.sign_in(phone_number, code)
                    break
                except EOFError:
                    _log(f"{log_prefix} Could not read code from input (EOFError). Ensure interactive session for first login.", "ERROR")
                    await client.disconnect()
                    return
                except Exception as e:
                    _log(f"{log_prefix} Sign-in error: {e}. If 2FA, provide password. Try code again.", "ERROR")
                    if 'password' in str(e).lower(): # Basic check for 2FA password needed
                         try:
                            password = input(f"Telethon ({session_name}): 2FA Password for {phone_number}: ")
                            await client.sign_in(password=password)
                            break
                         except Exception as p_err:
                            _log(f"{log_prefix} 2FA password error: {p_err}", "ERROR")
                            # Decide if to return or continue loop for code entry

        if await client.is_user_authorized():
            _log(f"{log_prefix} Client connected and authorized successfully.", "INFO")
            client.add_event_handler(new_message_handler, events.NewMessage(chats=[target_group]))
            _log(f"{log_prefix} Event handler added for target: {target_group}", "INFO")
            _log(f"{log_prefix} Listener started. Monitoring for new messages...")
            success_flags_list[listener_index] = True # Mark as successfully started
            await client.run_until_disconnected()
        else:
            _log(f"{log_prefix} Authorization failed. Listener will not start.", "ERROR")
            # success_flags_list[listener_index] remains False

    except ConnectionRefusedError:
        _log(f"{log_prefix} Connection refused. Check network or Telegram status/firewall.", "CRITICAL")
        # success_flags_list[listener_index] remains False
    except Exception as e:
        _log(f"{log_prefix} An unexpected error occurred: {e}", "CRITICAL")
        # success_flags_list[listener_index] remains False
    finally:
        if client.is_connected():
            _log(f"{log_prefix} Disconnecting Telethon client...", "INFO")
            await client.disconnect()
        _log(f"{log_prefix} Client session ended.", "INFO")
        # If an error occurred before success_flags_list[listener_index] was set to True,
        # it will remain False, correctly indicating failure for this listener.

def start_signal_detector(api_instance, global_value_mod, buy_func, prep_history_func):
    """
    Initializes and starts the Telethon signal detector in a separate thread.
    Returns True if the initial setup checks pass and thread starts, False otherwise.
    """
    global _api_object, _global_value_module, _buy_function, _prepare_history_function, _logger_function
    global _telethon_listeners_started_successfully # This is now a list

    _api_object = api_instance
    _global_value_module = global_value_mod
    _buy_function = buy_func
    _prepare_history_function = prep_history_func
    
    if hasattr(_global_value_module, 'logger'):
        _logger_function = _global_value_module.logger
    else:
        print("[CRITICAL][detectsignal] global_value.logger not found. Logging will be basic.")

    # In multi-worker setup, _api_object is None. Check for essential functions and modules.
    if not all([_global_value_module, _buy_function, _prepare_history_function]):
        _log("Essential components (_global_value_module, _buy_function, _prepare_history_function) "
             "not provided to Telethon signal detector. Cannot start.", "CRITICAL")
        return False

    _log("Initializing Telethon signal detector for multiple accounts...", "INFO")

    enabled_accounts = [acc for acc in TELEGRAM_ACCOUNTS_CONFIG if acc.get('ENABLED', True)]
    if not enabled_accounts:
        _log("No Telegram accounts are enabled in TELEGRAM_ACCOUNTS_CONFIG. Signal detector will not start.", "WARNING")
        return False

    _telethon_listeners_started_successfully = [False] * len(enabled_accounts)
    threads = []

    for idx, account_conf in enumerate(enabled_accounts):
        # Closure to pass specific args to the thread target
        def telethon_thread_runner_for_account(config, flags_list, index):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_run_telethon_listener_loop(config, flags_list, index))
            finally:
                loop.close()

        thread_name = f"TelethonSignalDetectorThread-{account_conf['SESSION_NAME']}"
        listener_thread = threading.Thread(
            target=telethon_thread_runner_for_account,
            args=(account_conf, _telethon_listeners_started_successfully, idx),
            name=thread_name
        )
        listener_thread.daemon = True # Exits when main program exits
        threads.append(listener_thread)
        listener_thread.start()
        _log(f"Telethon signal detector thread started for {account_conf['SESSION_NAME']}.", "INFO")

    # Wait for all threads to attempt startup and set their success flags.
    # This timeout should be generous enough for manual code entry if needed for multiple accounts.
    timeout_for_startup_flags = 120 * len(enabled_accounts) # e.g., 2 minutes per account
    all_listeners_reported_status = False
    processed_listeners_count = 0 # To track how many listeners have finished their startup attempt

    start_wait_time = time.time()
    # We need to wait until all threads have had a chance to set their flag or die.
    # A simple check is to see if all threads are still alive OR their flag is set.
    # This loop waits for all threads to either set their flag or terminate.
    while (time.time() - start_wait_time) < timeout_for_startup_flags:
        # Count how many threads have either set their success flag or are no longer alive (meaning they finished their attempt)
        finished_attempts = 0
        for i, t in enumerate(threads):
            if _telethon_listeners_started_successfully[i] or not t.is_alive():
                finished_attempts +=1
        
        if finished_attempts == len(enabled_accounts):
            all_listeners_reported_status = True
            break
        time.sleep(0.5)

    if not all_listeners_reported_status:
        _log("Timeout waiting for all Telethon listeners to report startup status.", "WARNING")

    final_success_status = all(_telethon_listeners_started_successfully)
    if final_success_status:
        _log("All enabled Telethon listeners started successfully.", "INFO")
    else:
        _log("One or more Telethon listeners failed to start. Check logs for details.", "ERROR")
        for idx, acc_conf in enumerate(enabled_accounts):
            if not _telethon_listeners_started_successfully[idx]:
                _log(f"Listener for {acc_conf['SESSION_NAME']} reported failure or did not start.", "ERROR")

    return final_success_status
