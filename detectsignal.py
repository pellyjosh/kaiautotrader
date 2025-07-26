# detectsignal.py
import asyncio
import os # Import the os module
import time # Import the time module
import re
import threading
from telethon import TelegramClient, events
from db.database_manager import DatabaseManager
import db.database_config as db_config

# --- Globals to be initialized by bot.py ---
_api_object = None
_global_value_module = None
_buy_function = None
_prepare_history_function = None
_logger_function = None # Shortcut for _global_value_module.logger
_database_manager = None  # Global database manager instance

# --- Configuration for multiple Telegram accounts ---
TELEGRAM_ACCOUNTS_CONFIG = [
    {
        'API_ID': '23324590',
        'API_HASH': 'fdcd53d426aebd07096ff326bb124397',
        'PHONE_NUMBER': '+2348101572723',
        'SESSION_NAME': 'my_signal_listener', # Ensure unique session names
        'TARGET_GROUP_IDENTIFIER': 1385109737, # Pocket Option Official Signal Bot
        # 'TARGET_GROUP_IDENTIFIER' : -1002546061495,  #Test Channel
        'ENABLED': True # Allows you to easily enable/disable this account
    },
    # {
    #     'API_ID': '20304811', # Replace with actual API_ID for Account 2
    #     'API_HASH': 'abeb329421c4ba8b2958ca3d3e645068', # Replace with actual API_HASH for Account 2
    #     'PHONE_NUMBER': '+2348085341275', # Replace with actual Phone Number for Account 2
    #     'SESSION_NAME': 'ton_signal_listener', # Ensure unique session names
    #     'TARGET_GROUP_IDENTIFIER': -1002360516634, # Example: Group for Account 2
    #     # 'TARGET_GROUP_IDENTIFIER' : -1002546061495,  #Test Channel
    #     'ENABLED': True # Allows you to easily enable/disable this account
    # }
    # Add more account configurations as dictionaries in this list if needed
]

DEFAULT_TRADE_AMOUNT = 1
DEFAULT_EXPIRATION_SECONDS = 10

# Martingale system variables - now per account
_martingale_enabled = True  # Enable/disable Martingale system
_martingale_multiplier = 2.5  # Will be updated from bot.py
_account_martingale_states = {}  # Per-account Martingale states
_pending_trade_results = {}  # Track trades waiting for results
_pending_trade_data = {}  # Track trade data before saving to database with real trade ID
_trade_sequence_number = 0  # To track trade order for multiple concurrent trades

# Single trade policy configuration
_single_trade_policy_enabled = True  # Control whether to allow only one trade at a time
_active_trades_per_account = {}  # Track active trades per account
_current_active_trade = None  # Track if any trade is currently active (global lock)

# For two-part signals
_pending_first_part_signals = {} # Key: chat_id, Value: {'pair': str, 'timeframe_minutes': int, 'timestamp': float}
PARTIAL_SIGNAL_TIMEOUT_SECONDS = 1000 # Timeout for waiting for the second part of a signal

# This will be a list of booleans, one for each configured and enabled client
_telethon_listeners_started_successfully = []

# Lock to serialize console input for Telethon authorization
_input_lock = threading.Lock()


def _log(message, level="INFO"):
    """Log to the general logger function or fall back to print"""
    if _logger_function:
        _logger_function(message, level)
    else:
        print(f"[{level}][SignalDetector] {message}")

def _initialize_database():
    """Initialize database connection and load persistent Martingale state for all accounts"""
    global _database_manager, _account_martingale_states, _martingale_multiplier
    
    try:
        # Create database manager based on configuration
        if db_config.DATABASE_TYPE.lower() == "mysql":
            mysql_config = {
                'db_type': 'mysql',
                'host': db_config.MYSQL_CONFIG['host'],
                'user': db_config.MYSQL_CONFIG['user'],
                'password': db_config.MYSQL_CONFIG['password'],
                'database': db_config.MYSQL_CONFIG['database'],
                'port': db_config.MYSQL_CONFIG['port']
            }
            _database_manager = DatabaseManager(**mysql_config)
        else:
            _database_manager = DatabaseManager(db_type='sqlite', db_path=db_config.SQLITE_DB_PATH)
        
        _log(f"Signal detector database initialized: {db_config.DATABASE_TYPE}", "INFO")
        
        # Load all accounts from database and their Martingale states
        accounts = _database_manager.get_all_accounts()
        for account in accounts:
            worker_name = account['worker_name']
            
            # Load persisted Martingale state for this account
            consecutive_losses, martingale_queue = _database_manager.load_account_martingale_state(worker_name)
            
            _account_martingale_states[worker_name] = {
                'consecutive_losses': consecutive_losses,
                'last_trade_id': None,
                'martingale_queue': martingale_queue
            }
            _active_trades_per_account[worker_name] = None
            
            _log(f"Loaded account {worker_name}: {consecutive_losses} losses, {len(martingale_queue)} queued amounts", "INFO")
            
        _log(f"Loaded {len(accounts)} account Martingale states from database", "INFO")
        
        return True
        
    except Exception as e:
        _log(f"Database initialization failed: {e}", "ERROR")
        _database_manager = None
        return False

def _get_account_settings(worker_name):
    """Get account-specific Martingale settings from database or account state"""
    try:
        # First, check if we have account-specific settings stored in _account_martingale_states
        if worker_name in _account_martingale_states:
            state = _account_martingale_states[worker_name]
            if 'base_amount' in state and 'martingale_multiplier' in state and 'martingale_enabled' in state:
                return {
                    'base_amount': state['base_amount'],
                    'martingale_multiplier': state['martingale_multiplier'],
                    'martingale_enabled': state['martingale_enabled']
                }
        
        # Fallback: Try to get from database directly
        if _database_manager:
            accounts = _database_manager.get_all_accounts()
            for account in accounts:
                if account['worker_name'] == worker_name:
                    return {
                        'base_amount': float(account['base_amount']),  # Convert Decimal to float
                        'martingale_multiplier': float(account['martingale_multiplier']),  # Convert Decimal to float
                        'martingale_enabled': account['martingale_enabled']
                    }
        
        # Last resort: Use global defaults (but this should rarely happen)
        _log(f"Using global defaults for account {worker_name} - consider running initialize_martingale_system_from_database()", "WARNING")
        return {
            'base_amount': DEFAULT_TRADE_AMOUNT,
            'martingale_multiplier': _martingale_multiplier,
            'martingale_enabled': _martingale_enabled
        }
    except Exception as e:
        _log(f"Error getting account settings for {worker_name}: {e}", "WARNING")
        return {
            'base_amount': DEFAULT_TRADE_AMOUNT,
            'martingale_multiplier': _martingale_multiplier,
            'martingale_enabled': _martingale_enabled
        }
        return False

def _save_martingale_state():
    """Save legacy Martingale state to database (for compatibility)"""
    # This function is kept for compatibility but now delegates to account-specific saving
    if _database_manager and _account_martingale_states:
        # Save the primary account's state as global state for legacy compatibility
        primary_account = 'pelly_demo'
        if primary_account in _account_martingale_states:
            _save_account_martingale_state(primary_account)

def _record_trade_in_database(trade_id, worker_name, symbol, direction, amount, expiration_duration, is_martingale=False):
    """Record trade in database"""
    global _database_manager
    
    if _database_manager:
        try:
            # Get martingale level from account state
            martingale_level = 0
            if worker_name in _account_martingale_states:
                martingale_level = _account_martingale_states[worker_name]['consecutive_losses'] if is_martingale else 0
            
            _database_manager.add_trade(
                trade_id=trade_id,
                worker_name=worker_name,
                symbol=symbol,
                direction=direction,
                amount=amount,
                expiration_duration=expiration_duration,
                martingale_level=martingale_level,
                is_martingale_trade=is_martingale,
                signal_source="Telegram"
            )
            _log(f"Trade recorded in database: {trade_id}", "INFO")
        except Exception as e:
            _log(f"Failed to record trade {trade_id}: {e}", "ERROR")

def _save_pending_trade_with_real_id(tracking_id, real_trade_id):
    """Update pending trade tracking to use the real PocketOption trade ID (worker already saved to DB)"""
    global _pending_trade_data
    
    if tracking_id in _pending_trade_data:
        # Update the pending trade results with the real trade ID
        if tracking_id in _pending_trade_results:
            _pending_trade_results[real_trade_id] = _pending_trade_results[tracking_id]
            del _pending_trade_results[tracking_id]
        
        # Update the current active trade if single trade policy is enabled
        global _current_active_trade
        if _single_trade_policy_enabled and _current_active_trade == tracking_id:
            _current_active_trade = real_trade_id
        
        # Clean up pending trade data
        del _pending_trade_data[tracking_id]
        
        _log(f"Updated trade tracking from {tracking_id} to real PocketOption trade ID: {real_trade_id}", "INFO")
        return True
    else:
        _log(f"No pending trade data found for tracking ID: {tracking_id}", "WARNING")
        return False

def _update_trade_result_in_database(trade_id, result, payout=0.0):
    """Update trade result in database"""
    global _database_manager
    
    if _database_manager:
        try:
            _database_manager.update_trade_result(trade_id, result, payout)
            _log(f"Trade result updated in database: {trade_id} = {result}", "DEBUG")
                
        except Exception as e:
            _log(f"Failed to update trade result in database: {e}", "ERROR")

def _update_martingale_settings(martingale_multiplier, enabled=True):
    """Update Martingale multiplier and enabled state from bot.py settings"""
    global _martingale_multiplier, _martingale_enabled
    _martingale_multiplier = martingale_multiplier
    _martingale_enabled = enabled
    status = "ENABLED" if enabled else "DISABLED"
    _log(f"Martingale system {status} with multiplier: {_martingale_multiplier}", "INFO")

def _calculate_next_martingale_amount(worker_name, consecutive_losses=None):
    """Calculate the next trade amount based on account-specific consecutive losses and settings"""
    # Get account-specific settings
    account_settings = _get_account_settings(worker_name)
    base_amount = account_settings['base_amount']
    multiplier = account_settings['martingale_multiplier']
    
    if worker_name not in _account_martingale_states:
        return base_amount
    
    if consecutive_losses is None:
        consecutive_losses = _account_martingale_states[worker_name]['consecutive_losses']
    
    if consecutive_losses == 0:
        return base_amount
    else:
        amount = base_amount * (multiplier ** consecutive_losses)
        return round(amount, 2)

def _get_trade_amount_for_new_signal(worker_name):
    """Get trade amount for a new incoming signal - assigns from account-specific Martingale queue or calculates new"""
    # Get account-specific settings
    account_settings = _get_account_settings(worker_name)
    base_amount = account_settings['base_amount']
    account_martingale_enabled = account_settings['martingale_enabled']
    
    if not _martingale_enabled or not account_martingale_enabled:
        _log(f"Martingale DISABLED (Global: {_martingale_enabled}, Account: {account_martingale_enabled}) - using base amount: ${base_amount}", "INFO")
        return base_amount
    
    if worker_name not in _account_martingale_states:
        _account_martingale_states[worker_name] = {
            'consecutive_losses': 0,
            'last_trade_id': None,
            'martingale_queue': []
        }
    
    account_state = _account_martingale_states[worker_name]
    
    # Check if there are pre-calculated amounts waiting from previous losses
    if account_state['martingale_queue']:
        amount = account_state['martingale_queue'].pop(0)  # Take the first queued amount (FIFO)
        _log(f"[{worker_name}] Using queued Martingale amount: ${amount} (queue remaining: {len(account_state['martingale_queue'])})", "INFO")
    else:
        # No queued amounts, calculate based on current consecutive losses
        amount = _calculate_next_martingale_amount(worker_name)
        _log(f"[{worker_name}] Calculated fresh Martingale amount: ${amount} (consecutive losses: {account_state['consecutive_losses']})", "INFO")
    
    return amount

def _handle_trade_result(trade_id, symbol, result, profit_loss=None, worker_name=None):
    """Handle trade result for per-account Martingale system"""
    global _current_active_trade
    
    if worker_name is None:
        worker_name = 'pelly_demo'  # Default fallback
    
    # Update database with trade result
    payout = float(profit_loss) if profit_loss and result == "win" else 0.0
    _update_trade_result_in_database(trade_id, result, payout)
    
    # Clear the active trade lock if single trade policy is enabled
    if _single_trade_policy_enabled and _current_active_trade == trade_id:
        _current_active_trade = None
        _log(f"[{worker_name}] Trade {trade_id} completed - unlocking for new trades", "INFO")
    elif not _single_trade_policy_enabled:
        _log(f"[{worker_name}] Trade {trade_id} completed - multiple trades policy active", "INFO")
    
    # Mark account as available for new trades
    if worker_name in _active_trades_per_account:
        _active_trades_per_account[worker_name] = False
    
    # Initialize account state if not exists
    if worker_name not in _account_martingale_states:
        _account_martingale_states[worker_name] = {
            'consecutive_losses': 0,
            'last_trade_id': None,
            'martingale_queue': []
        }
    
    account_state = _account_martingale_states[worker_name]
    account_state['last_trade_id'] = trade_id
    
    if not _martingale_enabled:
        _log(f"[{worker_name}] Martingale DISABLED - no adjustment for trade {trade_id}", "INFO")
        # Still remove from pending results
        if trade_id in _pending_trade_results:
            del _pending_trade_results[trade_id]
        return
    
    if result == "win":
        _log(f"[{worker_name}] Trade {trade_id} ({symbol}) WON! Profit: ${profit_loss}. Resetting Martingale.", "INFO")
        
        # Check if this was a Martingale recovery
        is_martingale_recovery = account_state['consecutive_losses'] > 0
        
        account_state['consecutive_losses'] = 0
        # Clear any queued Martingale amounts since we won
        account_state['martingale_queue'].clear()
        _log(f"[{worker_name}] Cleared Martingale queue due to win. Queue now empty.", "INFO")
        
        # Save updated state to database
        _save_account_martingale_state(worker_name)
        
        # Update performance tracking
        if _database_manager and trade_id in _pending_trade_results:
            trade_info = _pending_trade_results[trade_id]
            invested_amount = getattr(trade_info, 'amount', 0.0)
            _database_manager.update_daily_performance(
                worker_name=worker_name,
                trade_result="win",
                invested_amount=invested_amount,
                payout_amount=payout,
                is_martingale_recovery=is_martingale_recovery
            )
        
    elif result == "loss":
        account_state['consecutive_losses'] += 1
        _log(f"[{worker_name}] Trade {trade_id} ({symbol}) LOST! Loss: ${profit_loss}. Consecutive losses: {account_state['consecutive_losses']}", "WARNING")
        
        # Add a Martingale amount to the queue for the next trade
        next_amount = _calculate_next_martingale_amount(worker_name)
        account_state['martingale_queue'].append(next_amount)
        _log(f"[{worker_name}] Added ${next_amount} to Martingale queue. Queue length: {len(account_state['martingale_queue'])}", "INFO")
        
        # Save updated state to database
        _save_account_martingale_state(worker_name)
        
        # Update performance tracking
        if _database_manager and trade_id in _pending_trade_results:
            trade_info = _pending_trade_results[trade_id]
            invested_amount = getattr(trade_info, 'amount', 0.0)
            _database_manager.update_daily_performance(
                worker_name=worker_name,
                trade_result="loss",
                invested_amount=invested_amount,
                payout_amount=0.0
            )
        
    else:
        _log(f"[{worker_name}] Trade {trade_id} ({symbol}) result: {result}. No Martingale adjustment.", "INFO")
    
    # Remove from pending results
    if trade_id in _pending_trade_results:
        del _pending_trade_results[trade_id]

def _save_account_martingale_state(worker_name):
    """Save account-specific Martingale state to database"""
    if not _database_manager or worker_name not in _account_martingale_states:
        return
    
    try:
        account_state = _account_martingale_states[worker_name]
        consecutive_losses = account_state['consecutive_losses']
        martingale_queue = account_state['martingale_queue']
        
        # Save using new per-account method
        success = _database_manager.save_account_martingale_state(
            account_name=worker_name,
            consecutive_losses=consecutive_losses,
            martingale_queue=martingale_queue
        )
        
        if success:
            _log(f"[{worker_name}] Saved Martingale state: {consecutive_losses} losses, {len(martingale_queue)} queued", "DEBUG")
        else:
            _log(f"[{worker_name}] Failed to save Martingale state to database", "ERROR")
            
    except Exception as e:
        _log(f"[{worker_name}] Error saving Martingale state: {e}", "ERROR")

def _monitor_trade_results():
    """Monitor pending trades for results (to be called periodically)"""
    # This would need to be implemented with the worker system
    # For now, it's a placeholder for future enhancement
    pass

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
    _log(f"Attempting to parse message: \"{message_text}\"", "DEBUG")

    # --- Parsing Logic for Pocket Option Official Signal Bot format ---
    # Example:
    # SIGNAL ⬇
    # Asset: VISA_otc
    # Payout: 92%
    # Accuracy: 80%
    # Expiration: M5

    pocket_signal_pattern = re.compile(
        r"SIGNAL\s*([⬇⬆↓↑])\s*\n"  # Signal direction
        r".*?"  # Any content in between
        r"Asset:\s*([#]?[\w-]+(?:_\w+)?)\s*\n"  # Asset/Pair name (with optional # prefix, hyphens, and _otc/_live suffix)
        r".*?"  # Any content in between  
        r"Expiration:\s*M(\d+)",  # Expiration in minutes
        re.IGNORECASE | re.DOTALL
    )

    match = pocket_signal_pattern.search(message_text)
    
    if match:
        direction_symbol = match.group(1)
        asset_name = match.group(2).strip()
        expiration_minutes = int(match.group(3))
        
        # Determine action based on direction symbol
        if direction_symbol in ['⬇', '↓']:
            action = 'put'
        elif direction_symbol in ['⬆', '↑']:
            action = 'call'
        else:
            _log(f"Unknown direction symbol: {direction_symbol}", "WARNING")
            return None
        
        # Normalize the asset name
        pair_str = _normalize_pair_for_new_format(asset_name)
        
        expiration_seconds = expiration_minutes * 60
        amount = DEFAULT_TRADE_AMOUNT

        _log(f"Pocket Signal parsed: Pair={pair_str}, Action={action}, Amount=${amount}, Expiration={expiration_seconds}s", "INFO")
        return {'pair': pair_str, 'action': action, 'amount': amount, 'expiration': expiration_seconds}

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

def _place_trade_from_signal(pair, action, amount, expiration_duration, tracking_id=None, target_po_worker_name_unused=None): # target_po_worker_name_unused to keep signature if needed elsewhere, but will be ignored
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
    # Also pass tracking_id so we can save the trade with the real PocketOption trade ID
    
    def execute_trade_with_error_handling():
        """Execute trade and handle failures to release locks"""
        global _current_active_trade, _active_trades_per_account, _pending_trade_results, _pending_trade_data
        
        try:
            result = _buy_function(amount, pair, action, expiration_duration, 'ALL_ENABLED_WORKERS', tracking_id)
            
            # Check if trade failed
            if not result or result.get('status') in ['error', 'partial_error']:
                _log(f"Trade failed for tracking_id {tracking_id}: {result}", "ERROR")
                
                # Release single trade policy lock
                if _single_trade_policy_enabled and _current_active_trade == tracking_id:
                    _current_active_trade = None
                    _log(f"Released single trade policy lock due to trade failure: {tracking_id}", "WARNING")
                
                # Clean up tracking data
                if tracking_id in _pending_trade_results:
                    worker_name = _pending_trade_results[tracking_id].get('worker_name')
                    if worker_name and worker_name in _active_trades_per_account:
                        _active_trades_per_account[worker_name] = None
                    del _pending_trade_results[tracking_id]
                    
                if tracking_id in _pending_trade_data:
                    del _pending_trade_data[tracking_id]
                    
                _log(f"Cleaned up failed trade tracking data for: {tracking_id}", "INFO")
            else:
                _log(f"Trade executed successfully for tracking_id {tracking_id}", "INFO")
                
        except Exception as e:
            _log(f"Exception during trade execution for {tracking_id}: {e}", "ERROR")
            
            # Release locks on exception
            if _single_trade_policy_enabled and _current_active_trade == tracking_id:
                _current_active_trade = None
                _log(f"Released single trade policy lock due to exception: {tracking_id}", "WARNING")
    
    trade_thread = threading.Thread(target=execute_trade_with_error_handling)
    trade_thread.start()
    
    _log(f"Trade order for {pair}: {action.upper()} ${amount} for {expiration_duration}s initiated via Telethon signal.", "INFO")

# Telethon event handler for new messages
async def new_message_handler(event):
    global _trade_sequence_number, _current_active_trade, _active_trades_per_account, _pending_first_part_signals, _pending_trade_results  # Declare at function start
    
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

    # Filter out confirmation/status messages to reduce console noise
    ignored_message_patterns = [
        "Signal accepted. Trade order",
        "Your current balance:",
        "ID:",
        "Trade order in amount of",
        "is placed!",
        "(Demo)",
        "(Real)"
    ]
    
    # Check if this message should be ignored
    should_ignore = any(pattern.lower() in message_text.lower() for pattern in ignored_message_patterns)
    
    if should_ignore:
        return  # Skip processing and logging for confirmation messages
    
    _log(f"{log_prefix_for_handler} Msg from group '{chat_title}' (ID: {event.chat_id}, SenderID: {sender_id}): \"{message_text}\"", "DEBUG")

    # IMPORTANT: Check if any trade is currently active - ignore signals if single trade policy is enabled
    if _single_trade_policy_enabled and _current_active_trade is not None:
        _log(f"{log_prefix_for_handler} IGNORING signal - Trade {_current_active_trade} is currently active. Single trade policy is enabled.", "WARNING")
        return

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
                
                # Calculate Martingale trade amount for this signal
                worker_name = 'pelly_demo'  # Primary worker for this deployment
                martingale_amount = _get_trade_amount_for_new_signal(worker_name)
                
                # Generate unique trade ID for tracking
                _trade_sequence_number += 1
                trade_tracking_id = f"trade_{int(time.time())}_{_trade_sequence_number}"
                
                # Set this as the current active trade if single trade policy is enabled
                if _single_trade_policy_enabled:
                    _current_active_trade = trade_tracking_id
                    _log(f"[{worker_name}] Starting trade {trade_tracking_id} - locking for single trade policy", "INFO")
                else:
                    _log(f"[{worker_name}] Starting trade {trade_tracking_id} - multiple trades allowed", "INFO")
                _active_trades_per_account[worker_name] = True
                
                # Track this trade for Martingale result monitoring
                _pending_trade_results[trade_tracking_id] = {
                    'timestamp': time.time(),
                    'amount': martingale_amount,
                    'symbol': signal_data_for_trade['pair'],
                    'direction': signal_data_for_trade['action'],
                    'worker_name': worker_name
                }
                
                # Store trade details for when we get the real PocketOption trade ID
                account_settings = _get_account_settings(worker_name)
                is_martingale = martingale_amount > account_settings['base_amount']
                _pending_trade_data[trade_tracking_id] = {
                    'worker_name': worker_name,
                    'symbol': signal_data_for_trade['pair'],
                    'direction': signal_data_for_trade['action'],
                    'amount': martingale_amount,
                    'expiration_duration': signal_data_for_trade['expiration'],
                    'is_martingale': is_martingale
                }
                
                _place_trade_from_signal(
                    pair=signal_data_for_trade['pair'],
                    action=signal_data_for_trade['action'],
                    amount=martingale_amount,  # Use Martingale amount instead of parsed amount
                    expiration_duration=signal_data_for_trade['expiration'],
                    tracking_id=trade_tracking_id,
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
        
        # Calculate Martingale trade amount for this signal
        worker_name = 'pelly_demo'  # Primary worker for this deployment
        martingale_amount = _get_trade_amount_for_new_signal(worker_name)
        
        # Generate unique trade ID for tracking
        _trade_sequence_number += 1
        trade_tracking_id = f"trade_{int(time.time())}_{_trade_sequence_number}"
        
        # Set this as the current active trade if single trade policy is enabled
        if _single_trade_policy_enabled:
            _current_active_trade = trade_tracking_id
            _log(f"[{worker_name}] Starting trade {trade_tracking_id} - locking for single trade policy", "INFO")
        else:
            _log(f"[{worker_name}] Starting trade {trade_tracking_id} - multiple trades allowed", "INFO")
        _active_trades_per_account[worker_name] = True
        
        # Track this trade for Martingale result monitoring
        _pending_trade_results[trade_tracking_id] = {
            'timestamp': time.time(),
            'amount': martingale_amount,
            'symbol': original_format_signal_data['pair'],
            'direction': original_format_signal_data['action'],
            'worker_name': worker_name
        }
        
        # Store trade details for when we get the real PocketOption trade ID
        account_settings = _get_account_settings(worker_name)
        is_martingale = martingale_amount > account_settings['base_amount']
        _pending_trade_data[trade_tracking_id] = {
            'worker_name': worker_name,
            'symbol': original_format_signal_data['pair'],
            'direction': original_format_signal_data['action'],
            'amount': martingale_amount,
            'expiration_duration': original_format_signal_data['expiration'],
            'is_martingale': is_martingale
        }
        
        _place_trade_from_signal(
            pair=original_format_signal_data['pair'],
            action=original_format_signal_data['action'],
            amount=martingale_amount,  # Use Martingale amount instead of parsed amount
            expiration_duration=original_format_signal_data['expiration'],
            tracking_id=trade_tracking_id,
            # target_po_worker_name is no longer passed here
        )
        return

async def _run_telethon_listener_loop(account_config, success_flags_list, listener_index, auth_event):
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

    try: # Outer try for the whole client lifecycle
        _log(f"{log_prefix} Connecting Telethon client...", "INFO")
        await client.connect()

        if not await client.is_user_authorized():
            _log(f"{log_prefix} User not authorized. Sending code request to {phone_number}...", "INFO")
            await client.send_code_request(phone_number)
            _log(f"{log_prefix} Telethon is waiting for you to enter the code sent to {phone_number}. Please check your Telegram messages.", "IMPORTANT")
            
            # The auth_event will be set *after* the input process (successful or failed)
            # to ensure the main thread waits for this interactive step to complete.
            _log(f"{log_prefix} Waiting to acquire input lock for authorization...", "DEBUG")
            with _input_lock:
                _log(f"{log_prefix} Acquired input lock. Ready for authorization input for {phone_number}.", "DEBUG")
                signed_in_successfully_interactively = False
                while True: # Loop for code entry, possibly 2FA
                    try:
                        code = input(f"Telethon ({session_name}): Enter the code for {phone_number}: ")
                        await client.sign_in(phone_number, code)
                        signed_in_successfully_interactively = True
                        break # Signed in with code
                    except EOFError:
                        _log(f"{log_prefix} Could not read code from input (EOFError). Listener for {session_name} will not start.", "ERROR")
                        # auth_event will be set in the finally block of this function
                        if client.is_connected(): await client.disconnect()
                        return
                    except Exception as e:
                        error_str = str(e).lower()
                        _log(f"{log_prefix} Sign-in error for {session_name}: {e}. If 2FA, provide password. Try code again.", "ERROR")
                        
                        # Enhanced 2FA detection - check for multiple possible error patterns
                        if any(keyword in error_str for keyword in ['password', 'two-factor', '2fa', 'two factor', 'cloud password']):
                             try:
                                password = input(f"Telethon ({session_name}): 2FA Password for {phone_number}: ")
                                await client.sign_in(password=password)
                                signed_in_successfully_interactively = True
                                break 
                             except Exception as p_err:
                                _log(f"{log_prefix} 2FA password error for {session_name}: {p_err}. Listener will not start.", "ERROR")
                                if client.is_connected(): await client.disconnect()
                                return 
                        elif 'invalid' in error_str or 'wrong' in error_str:
                            retry_choice = input(f"Telethon ({session_name}): Code failed. Try 2FA password? (y/n): ").lower().strip()
                            if retry_choice == 'y':
                                try:
                                    password = input(f"Telethon ({session_name}): 2FA Password for {phone_number}: ")
                                    await client.sign_in(password=password)
                                    signed_in_successfully_interactively = True
                                    break 
                                except Exception as p_err:
                                    _log(f"{log_prefix} 2FA password error for {session_name}: {p_err}. Will retry with code.", "ERROR")
                                    # Continue loop to try code again
                            # If 'n' or other input, continue loop to try code again
                        else:
                            # For other errors, break the loop
                            break
            # After input lock is released, signal the main thread.
            if auth_event: # auth_event is passed as a parameter
                auth_event.set()
        else: # User is already authorized
            _log(f"{log_prefix} User already authorized.", "INFO")
            if auth_event: # Signal main thread that auth is already handled or not needed for input
                auth_event.set()

        if await client.is_user_authorized():
            _log(f"{log_prefix} Client for {session_name} connected and authorized successfully.", "INFO")
            client.add_event_handler(new_message_handler, events.NewMessage(chats=[target_group]))
            _log(f"{log_prefix} Event handler added for target: {target_group}", "INFO")
            _log(f"{log_prefix} Listener started. Monitoring for new messages...")
            success_flags_list[listener_index] = True # Mark as successfully started
            await client.run_until_disconnected()
        else:
            _log(f"{log_prefix} Authorization failed. Listener will not start.", "ERROR")
            # success_flags_list[listener_index] will remain False

    except ConnectionRefusedError:
        _log(f"{log_prefix} Connection refused for {session_name}. Check network or Telegram status/firewall.", "CRITICAL")
    except Exception as e:
        _log(f"{log_prefix} An unexpected error occurred for {session_name}: {e}", "CRITICAL")
    finally:
        # Ensure the auth_event is set even on failure, so main thread doesn't hang indefinitely if it was waiting.
        if auth_event and not auth_event.is_set(): # Use the passed auth_event parameter
            auth_event.set()
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

    # Initialize database first
    _log("Initializing database system...", "INFO")
    if not _initialize_database():
        _log("Database initialization failed. Continuing without database support.", "WARNING")

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
    auth_events = [] # To store threading.Event() for each account needing auth

    for idx, account_conf in enumerate(enabled_accounts):
        auth_event = threading.Event()
        auth_events.append(auth_event)
        account_conf['_auth_event'] = auth_event # Pass event to the thread's context

        # Closure to pass specific args to the thread target
        def telethon_thread_runner_for_account(config, flags_list, index, current_auth_event):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # _run_telethon_listener_loop will set current_auth_event if it needs input
                loop.run_until_complete(_run_telethon_listener_loop(config, flags_list, index, current_auth_event))
            finally:
                if not current_auth_event.is_set(): # Ensure event is set if loop exits unexpectedly
                    current_auth_event.set()
                loop.close()

        thread_name = f"TelethonSignalDetectorThread-{account_conf['SESSION_NAME']}"
        listener_thread = threading.Thread(
            target=telethon_thread_runner_for_account,
            args=(account_conf, _telethon_listeners_started_successfully, idx, auth_event),
            name=thread_name
        )
        listener_thread.daemon = True # Exits when main program exits
        threads.append(listener_thread)
        listener_thread.start()
        _log(f"Telethon signal detector thread started for {account_conf['SESSION_NAME']}.", "INFO")
        
        # Wait for this specific thread to signal it's past the input() stage or has failed before it.
        # Timeout for waiting for authorization prompt/completion for this single account.
        # If an account is already authorized, _auth_event might not be set by the thread
        # if it doesn't hit the `input()` block. The success_flags_list[idx] will indicate success.
        # The main purpose of auth_event is to serialize the input() calls.
        _log(f"Waiting for authorization phase for {account_conf['SESSION_NAME']}...", "DEBUG")
        auth_completed_or_not_needed = auth_event.wait(timeout=300) # Wait up to 5 minutes for input phase completion

        if not auth_completed_or_not_needed:
            _log(f"Timeout waiting for {account_conf['SESSION_NAME']} to complete its authorization phase (input or already authorized). It might be stuck or failed.", "WARNING")
            # The thread might still be running if it's stuck before setting the event.
            # _telethon_listeners_started_successfully[idx] will reflect its actual startup success later.
        else:
            _log(f"Authorization phase for {account_conf['SESSION_NAME']} completed (or was not required). Proceeding.", "DEBUG")

    # After attempting to start all threads and waiting for their auth phases:
    # Give a final short wait for all threads to fully establish their run_until_disconnected or fail.
    time.sleep(5) # Allow threads to settle after all auth attempts.

    # Check final status based on the success flags set by each thread
    # This check is now more about whether they reached run_until_disconnected successfully.
    # The loop above handles serializing the input() calls.

    final_success_status = all(_telethon_listeners_started_successfully)
    if final_success_status:
        _log("All enabled Telethon listeners started successfully.", "INFO")
    else:
        _log("One or more Telethon listeners failed to start. Check logs for details.", "ERROR")
        for idx, acc_conf in enumerate(enabled_accounts):
            if not _telethon_listeners_started_successfully[idx]:
                _log(f"Listener for {acc_conf['SESSION_NAME']} reported failure or did not start.", "ERROR")

    return final_success_status

# Public functions for Martingale system integration
def initialize_martingale_system(martingale_multiplier, enabled=True):
    """Initialize the Martingale system with the specified multiplier and enabled state from bot.py"""
    _update_martingale_settings(martingale_multiplier, enabled)
    status = "ENABLED" if enabled else "DISABLED"
    _log(f"Martingale system initialized: {status} with multiplier: {martingale_multiplier}", "INFO")

def initialize_martingale_system_from_database():
    """Initialize the Martingale system using per-account settings from database"""
    global _database_manager
    
    try:
        # Load all enabled accounts and their Martingale settings
        enabled_accounts = _database_manager.get_enabled_accounts()
        if not enabled_accounts:
            _log("No enabled accounts found in database for Martingale initialization", "WARNING")
            return False
        
        # Initialize per-account Martingale states based on database settings
        for account in enabled_accounts:
            account_name = account['worker_name']
            martingale_enabled = bool(account['martingale_enabled'])
            martingale_multiplier = float(account['martingale_multiplier'])
            base_amount = float(account['base_amount'])
            
            # Initialize account state in our tracking system
            if account_name not in _account_martingale_states:
                _account_martingale_states[account_name] = {
                    'consecutive_losses': 0,
                    'martingale_queue': [],
                    'base_amount': base_amount,
                    'martingale_multiplier': martingale_multiplier,
                    'martingale_enabled': martingale_enabled
                }
            else:
                # Update existing state with current database values
                _account_martingale_states[account_name]['base_amount'] = base_amount
                _account_martingale_states[account_name]['martingale_multiplier'] = martingale_multiplier
                _account_martingale_states[account_name]['martingale_enabled'] = martingale_enabled
            
            _log(f"Initialized account {account_name}: Base=${base_amount}, Multiplier={martingale_multiplier}x, Martingale={'On' if martingale_enabled else 'Off'}", "INFO")
        
        # Set global Martingale enabled if any account has it enabled
        global _martingale_enabled
        _martingale_enabled = any(acc['martingale_enabled'] for acc in enabled_accounts)
        
        global_status = "ENABLED" if _martingale_enabled else "DISABLED"
        _log(f"Martingale system initialized from database: {global_status} for {len(enabled_accounts)} accounts", "INFO")
        return True
        
    except Exception as e:
        _log(f"Failed to initialize Martingale system from database: {e}", "ERROR")
        return False

def set_martingale_enabled(enabled):
    """Enable or disable the Martingale system"""
    global _martingale_enabled
    _martingale_enabled = enabled
    status = "ENABLED" if enabled else "DISABLED"
    _log(f"Martingale system {status}", "INFO")

def configure_single_trade_policy(enabled):
    """Configure whether to allow only one trade at a time"""
    global _single_trade_policy_enabled
    _single_trade_policy_enabled = enabled
    status = "ENABLED" if enabled else "DISABLED"
    _log(f"Single trade policy {status}", "INFO")

def handle_trade_result_callback(trade_id, symbol, result, profit_loss=None, worker_name=None):
    """Callback function for bot.py to report trade results"""
    _handle_trade_result(trade_id, symbol, result, profit_loss, worker_name)

def get_current_martingale_status():
    """Get current Martingale system status for debugging"""
    total_active_trades = len([t for t in _active_trades_per_account.values() if t])
    total_queued_amounts = sum(len(state['martingale_queue']) for state in _account_martingale_states.values())
    
    # Get primary account status for legacy compatibility
    primary_account = 'pelly_demo'
    primary_consecutive_losses = 0
    primary_queue = []
    
    if primary_account in _account_martingale_states:
        primary_consecutive_losses = _account_martingale_states[primary_account]['consecutive_losses']
        primary_queue = _account_martingale_states[primary_account]['martingale_queue'].copy()
    
    return {
        'martingale_enabled': _martingale_enabled,
        'martingale_multiplier': _martingale_multiplier,
        'single_trade_policy_enabled': _single_trade_policy_enabled,
        'consecutive_losses': primary_consecutive_losses,  # Primary account for legacy
        'pending_trades': len(_pending_trade_results),
        'active_trades_count': total_active_trades,
        'queued_amounts': primary_queue,  # Primary account for legacy
        'queue_length': len(primary_queue),
        'account_states': _account_martingale_states.copy(),  # Full per-account info
        'active_trades_per_account': _active_trades_per_account.copy(),
        'current_active_trade': _current_active_trade
    }

def force_release_trade_locks():
    """Emergency function to release stuck trade locks"""
    global _current_active_trade, _active_trades_per_account, _pending_trade_results, _pending_trade_data
    
    _log("EMERGENCY: Force releasing all trade locks and clearing pending trades", "WARNING")
    
    # Release single trade policy lock
    if _current_active_trade:
        _log(f"Releasing stuck single trade policy lock: {_current_active_trade}", "WARNING")
        _current_active_trade = None
    
    # Clear all active trade flags
    for worker_name in _active_trades_per_account:
        _active_trades_per_account[worker_name] = None
    
    # Clear pending trade tracking
    cleared_trades = list(_pending_trade_results.keys())
    _pending_trade_results.clear()
    _pending_trade_data.clear()
    
    _log(f"Cleared {len(cleared_trades)} pending trades: {cleared_trades}", "WARNING")
    _log("Trade locks released. Bot should now accept new signals.", "INFO")
