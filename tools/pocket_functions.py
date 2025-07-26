# /Users/Hubolux/Documents/Project 001/HuboluxJobs/Trading/PocketOptionAPI-v2/pocket_functions.py
import time
import math
import json
import threading
from datetime import datetime
import numpy as np
import pandas as pd

# Module-level placeholders to be initialized
_api = None
_global_value = None
_qtpylib = None
_ta = None
_period = None
_min_payout = None
# _expiration is not directly used by the functions being moved,
# but if any strategy needed it, it could be passed via initialize too.

def initialize_pocket_functions(api_instance, global_value_module, qtpylib_module, ta_module, period_val, min_payout_val):
    """Initializes module-level variables for pocket_functions."""
    global _api, _global_value, _qtpylib, _ta, _period, _min_payout
    _api = api_instance
    _global_value = global_value_module
    _qtpylib = qtpylib_module
    _ta = ta_module
    _period = period_val
    _min_payout = min_payout_val
    _global_value.logger("[PocketFunctions] pocket_functions initialized.", "INFO")

def get_payout():
    try:
        d = _global_value.PayoutData
        d = json.loads(d)
        for pair_data in d: # Renamed 'pair' to 'pair_data' to avoid conflict with pair name
            # |0| |  1  |  |  2  |  |  3  | |4 | 5 |6 | 7 | 8| 9| 10 |11| 12| 13        | 14   | | 15, ...
            if len(pair_data) == 19:
                _global_value.logger(f"[PocketFunctions] id: {str(pair_data[1])}, name: {str(pair_data[2])}, typ: {str(pair_data[3])}, active: {str(pair_data[14])}", "DEBUG")
                # Example filter:
                if pair_data[14] == True and pair_data[5] >= _min_payout: # Allow both OTC and non-OTC if active and meets payout
                    p = {}
                    p['id'] = pair_data[0]
                    p['payout'] = pair_data[5]
                    p['type'] = pair_data[3]
                    _global_value.pairs[pair_data[1]] = p
        return True
    except Exception as e:
        _global_value.logger(f"[PocketFunctions] Error in get_payout: {e}", "ERROR")
        return False

def get_df():
    try:
        if not _api:
            _global_value.logger("[PocketFunctions] API object not initialized in get_df. Cannot fetch candles.", "ERROR")
            return False

        i = 0
        for pair_name in _global_value.pairs: # Renamed 'pair' to 'pair_name'
            i += 1
            df = _api.get_candles(pair_name, _period)
            _global_value.logger(f"[PocketFunctions] {str(pair_name)} ({str(i)}/{str(len(_global_value.pairs))})", "INFO")
            time.sleep(1) # Consider if this sleep is essential or can be configured/removed
        return True
    except Exception as e:
        _global_value.logger(f"[PocketFunctions] Error in get_df: {e}", "ERROR")
        return False

def buy(amount, pair, action, expiration_duration): # Renamed 'expiration' to 'expiration_duration'
    _global_value.logger(f"[PocketFunctions] Buy: {str(amount)}, {str(pair)}, {str(action)}, {str(expiration_duration)}", "INFO")
    if not _api:
        _global_value.logger("[PocketFunctions] API object not initialized in buy. Cannot place trade.", "ERROR")
        return

    result = _api.buy(amount=amount, active=pair, action=action, expirations=expiration_duration)
    if result and len(result) > 1:
        trade_id = result[1]
        win_result = _api.check_win(trade_id)
        if win_result:
            _global_value.logger(f"[PocketFunctions] Trade result for {trade_id}: {win_result}", "INFO")
    else:
        _global_value.logger(f"[PocketFunctions] Buy command did not return expected result for {pair}.", "WARNING")


def buy2(amount, pair, action, expiration_duration): # Renamed 'expiration' to 'expiration_duration'
    # This line was causing the TypeError and is redundant with the f-string log below
    # _global_value.logger('%s, %s, %s, %s' % (str(amount), str(pair), str(action), str(expiration_duration)), "INFO", "PocketFunctions")
    if not _api:
        _global_value.logger("[PocketFunctions] API object not initialized in buy2. Cannot place trade.", "ERROR")
        return
    _global_value.logger(f"[PocketFunctions] Buy2: {str(amount)}, {str(pair)}, {str(action)}, {str(expiration_duration)}", "INFO")
    _api.buy(amount=amount, active=pair, action=action, expirations=expiration_duration)


def make_df(df0, history):
    if not _api:
        _global_value.logger("[PocketFunctions] API object not available in make_df.", "ERROR")
        return pd.DataFrame()
    
    df1 = pd.DataFrame(history).reset_index(drop=True)
    df1 = df1.sort_values(by='time').reset_index(drop=True)
    df1['time'] = pd.to_datetime(df1['time'], unit='s')
    df1.set_index('time', inplace=True)

    df = df1['price'].resample(f'{_period}s').ohlc()
    df.reset_index(inplace=True)
    df = df.loc[df['time'] < datetime.fromtimestamp(wait(False))] # Uses wait() from this module

    if df0 is not None and not df.empty: # Added check for df not empty
        ts = datetime.timestamp(df.loc[0]['time'])
        for x in range(0, len(df0)):
            ts2 = datetime.timestamp(df0.loc[x]['time'])
            if ts2 < ts:
                # Use pd.concat instead of _append which is deprecated
                df_row = pd.DataFrame([df0.loc[x]])
                df = pd.concat([df_row, df], ignore_index=True)
            else:
                break
        df = df.sort_values(by='time').reset_index(drop=True)
        # df.set_index('time', inplace=True) # This might be redundant if reset_index is last
        # df.reset_index(inplace=True)
    elif df.empty and df0 is not None: # If df is empty but df0 exists
        df = df0.copy() # Or handle as appropriate

    df.set_index('time', inplace=True)
    df.reset_index(inplace=True)
    return df

def accelerator_oscillator(dataframe, fastPeriod=5, slowPeriod=34, smoothPeriod=5):
    # Ensure 'hl2' column exists or is calculated
    if 'hl2' not in dataframe.columns and 'high' in dataframe.columns and 'low' in dataframe.columns:
        dataframe['hl2'] = (dataframe['high'] + dataframe['low']) / 2
    elif 'hl2' not in dataframe.columns:
        _global_value.logger("[PocketFunctions] accelerator_oscillator: 'hl2' column missing and cannot be calculated.", "ERROR")
        return pd.Series(index=dataframe.index, dtype=float) # Return empty/NaN series

    ao = _ta.SMA(dataframe["hl2"], timeperiod=fastPeriod) - _ta.SMA(dataframe["hl2"], timeperiod=slowPeriod)
    ac = _ta.SMA(ao, timeperiod=smoothPeriod)
    return ac

def DeMarker(dataframe, Period=14):
    dataframe['dem_high'] = dataframe['high'] - dataframe['high'].shift(1)
    dataframe['dem_low'] = dataframe['low'].shift(1) - dataframe['low']
    dataframe.loc[(dataframe['dem_high'] < 0), 'dem_high'] = 0
    dataframe.loc[(dataframe['dem_low'] < 0), 'dem_low'] = 0

    dem = _ta.SMA(dataframe['dem_high'], Period) / (_ta.SMA(dataframe['dem_high'], Period) + _ta.SMA(dataframe['dem_low'], Period))
    return dem

def vortex_indicator(dataframe, Period=14):
    vm_plus = abs(dataframe['high'] - dataframe['low'].shift(1))
    vm_minus = abs(dataframe['low'] - dataframe['high'].shift(1))

    tr1 = dataframe['high'] - dataframe['low']
    tr2 = abs(dataframe['high'] - dataframe['close'].shift(1))
    tr3 = abs(dataframe['low'] - dataframe['close'].shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    sum_vm_plus = vm_plus.rolling(window=Period).sum()
    sum_vm_minus = vm_minus.rolling(window=Period).sum()
    sum_tr = tr.rolling(window=Period).sum()

    vi_plus = sum_vm_plus / sum_tr
    vi_minus = sum_vm_minus / sum_tr

    return vi_plus, vi_minus

def supertrend(df, multiplier, period_val): # Renamed 'period' to 'period_val' to avoid conflict
    df['TR'] = _ta.TRANGE(df) # Assuming TRANGE is from _ta (talib)
    df['ATR'] = _ta.SMA(df['TR'], period_val)

    st = 'ST'
    stx = 'STX'

    df['basic_ub'] = (df['high'] + df['low']) / 2 + multiplier * df['ATR']
    df['basic_lb'] = (df['high'] + df['low']) / 2 - multiplier * df['ATR']

    df['final_ub'] = 0.00
    df['final_lb'] = 0.00
    for i in range(period_val, len(df)):
        df['final_ub'].iat[i] = df['basic_ub'].iat[i] if df['basic_ub'].iat[i] < df['final_ub'].iat[i - 1] or df['close'].iat[i - 1] > df['final_ub'].iat[i - 1] else df['final_ub'].iat[i - 1]
        df['final_lb'].iat[i] = df['basic_lb'].iat[i] if df['basic_lb'].iat[i] > df['final_lb'].iat[i - 1] or df['close'].iat[i - 1] < df['final_lb'].iat[i - 1] else df['final_lb'].iat[i - 1]

    df[st] = 0.00
    for i in range(period_val, len(df)):
        df[st].iat[i] = df['final_ub'].iat[i] if df[st].iat[i - 1] == df['final_ub'].iat[i - 1] and df['close'].iat[i] <= df['final_ub'].iat[i] else \
                        df['final_lb'].iat[i] if df[st].iat[i - 1] == df['final_ub'].iat[i - 1] and df['close'].iat[i] >  df['final_ub'].iat[i] else \
                        df['final_lb'].iat[i] if df[st].iat[i - 1] == df['final_lb'].iat[i - 1] and df['close'].iat[i] >= df['final_lb'].iat[i] else \
                        df['final_ub'].iat[i] if df[st].iat[i - 1] == df['final_lb'].iat[i - 1] and df['close'].iat[i] <  df['final_lb'].iat[i] else 0.00
    df[stx] = np.where((df[st] > 0.00), np.where((df['close'] < df[st]), 'down',  'up'), np.NaN)

    df.drop(['basic_ub', 'basic_lb', 'final_ub', 'final_lb'], inplace=True, axis=1)
    df.fillna(0, inplace=True)
    return df

def strategie():
    if not _global_value or not _qtpylib or not _ta:
        print("[ERROR][PocketFunctions] strategie: Modules not initialized (_global_value, _qtpylib, _ta)")
        return

    for pair_name in _global_value.pairs: # Renamed 'pair' to 'pair_name'
        if 'history' in _global_value.pairs[pair_name]:
            history_data = [] # Renamed 'history' to 'history_data'
            history_data.extend(_global_value.pairs[pair_name]['history'])
            
            current_df = None
            if 'dataframe' in _global_value.pairs[pair_name]:
                current_df = _global_value.pairs[pair_name]['dataframe']
            
            df = make_df(current_df, history_data) # Uses make_df from this module

            if df.empty:
                _global_value.logger(f"[PocketFunctions] DataFrame for {pair_name} is empty after make_df. Skipping strategy.", "WARNING")
                continue

            # Strategy 9, period: 30 (Assuming _period might be 30 for this strategy)
            # This example uses the global _period. If strategies have different periods,
            # that needs to be handled, e.g., by passing period to strategie or having it in pair_config.
            heikinashi_df = _qtpylib.heikinashi(df.copy()) # Use .copy() to avoid SettingWithCopyWarning
            df['open'] = heikinashi_df['open']
            df['close'] = heikinashi_df['close']
            df['high'] = heikinashi_df['high']
            df['low'] = heikinashi_df['low']
            
            df = supertrend(df.copy(), 1.3, 13) # Uses supertrend from this module, pass period for ST
            
            df['ma1'] = _ta.EMA(df["close"], timeperiod=16)
            df['ma2'] = _ta.EMA(df["close"], timeperiod=165)
            df['buy_signal'], df['cross_signal'] = 0, 0 # Renamed 'buy', 'cross' to avoid conflict
            
            df.loc[(_qtpylib.crossed_above(df['ST'], df['ma1'])), 'cross_signal'] = 1
            df.loc[(_qtpylib.crossed_below(df['ST'], df['ma1'])), 'cross_signal'] = -1
            
            df.loc[(
                    (df['STX'] == "up") &
                    (df['ma1'] > df['ma2']) &
                    (df['cross_signal'] == 1)
                ), 'buy_signal'] = 1
            df.loc[(
                    (df['STX'] == "down") &
                    (df['ma1'] < df['ma2']) &
                    (df['cross_signal'] == -1)
                ), 'buy_signal'] = -1
            
            if not df.empty and df.iloc[-1]['buy_signal'] != 0:
                action = "call" if df.iloc[-1]['buy_signal'] == 1 else "put"
                # Assuming global expiration from bot.py is intended for trades from strategies
                # If not, it should be defined or passed appropriately.
                # For now, let's assume a fixed 60s expiration for this strategy trade.
                trade_expiration = 60
                t = threading.Thread(target=buy2, args=(100, pair_name, action, trade_expiration))
                t.start()
            _global_value.pairs[pair_name]['dataframe'] = df # Save the processed dataframe

def prepare_get_history():
    try:
        data = get_payout() # Uses get_payout from this module
        if data: return True
        else: return False
    except Exception as e:
        _global_value.logger(f"[PocketFunctions] Error in prepare_get_history: {e}", "ERROR")
        return False

def prepare():
    try:
        data = get_payout() # Uses get_payout from this module
        if data:
            data_df = get_df() # Uses get_df from this module
            if data_df: return True
            else: return False
        else: return False
    except Exception as e:
        _global_value.logger(f"[PocketFunctions] Error in prepare: {e}", "ERROR")
        return False

def wait(sleep=True):
    # Ensure _global_value and _period are initialized
    if _global_value is None or _period is None:
        print("[ERROR][PocketFunctions] wait: _global_value or _period not initialized.")
        return 60 # Default wait time

    dt = int(datetime.now().timestamp()) - int(datetime.now().second)
    current_second = datetime.now().second
    
    if _period == 60:
        dt += 60
    elif _period == 30:
        dt += 30 if current_second < 30 else 60
        if not sleep: dt -= 30
    elif _period == 15:
        if current_second < 15: dt += 15
        elif current_second < 30: dt += 30
        elif current_second < 45: dt += 45
        else: dt += 60
        if not sleep: dt -= 15
    # Add other period calculations as in original bot.py if needed
    # ... (e.g., 10, 5, 120, 180, 300, 600)
    else: # Default for unhandled periods
        _global_value.logger(f"[PocketFunctions] Unhandled period {_period} in wait function. Defaulting to _period.", "WARNING")
        dt += _period

    wait_seconds = dt - int(datetime.now().timestamp())
    if sleep:
        if wait_seconds > 0:
            _global_value.logger(f"[PocketFunctions] ======== Sleeping {str(wait_seconds)} Seconds ========", "INFO")
            return wait_seconds
        else: # If calculated wait time is negative or zero, wait for a very short default
            _global_value.logger("[PocketFunctions] ======== Calculated sleep time <= 0. Sleeping 1s. ========", "WARNING")
            return 1 
    return dt # Returns timestamp if not sleeping

def start():
    if not _api:
        _global_value.logger("[PocketFunctions] API object not initialized at start of strategy loop. Exiting strategy.", "CRITICAL")
        return

    while _global_value.websocket_is_connected is False:
        time.sleep(0.1)
    
    time.sleep(2) # Initial delay
    
    balance = _api.get_balance()
    _global_value.logger(f'[PocketFunctions] Account Balance: {balance}', "INFO")
    
    if prepare(): # Uses prepare from this module
        while True:
            if not _global_value.websocket_is_connected:
                _global_value.logger("[PocketFunctions] WebSocket disconnected. Attempting to reconnect or wait.", "WARNING")
                # Basic wait, real reconnect logic should be in pocket_connector or api library
                time.sleep(10) 
                continue # Re-check connection at the start of the loop

            strategie() # Uses strategie from this module
            sleep_duration = wait() # Uses wait from this module
            if sleep_duration > 0:
                time.sleep(sleep_duration)
            else: # Should not happen if wait() is correct
                time.sleep(1) 
    else:
        _global_value.logger("[PocketFunctions] Preparation failed. Strategy loop will not start.", "ERROR")


def start_get_history():
    # This function seems more for historical data download than continuous operation.
    # Its original implementation in bot.py had a check_cache which is not defined here.
    # For now, porting structure, but it might need review based on `global_value.check_cache`
    if not _api:
        _global_value.logger("[PocketFunctions] API object not initialized at start of get_history. Exiting.", "CRITICAL")
        return

    while _global_value.websocket_is_connected is False:
        time.sleep(0.1)
    
    time.sleep(2)
    balance = _api.get_balance()
    _global_value.logger(f'[PocketFunctions] Account Balance (for history): {balance}', "INFO")
    
    if prepare_get_history(): # Uses prepare_get_history from this module
        i = 0
        for pair_name in _global_value.pairs: # Renamed 'pair'
            i += 1
            _global_value.logger(f'[PocketFunctions] Processing history for {pair_name} ({i}/{len(_global_value.pairs)})', "INFO")
            
            # The check_cache logic was in global_value in the original bot.py
            # Assuming global_value.check_cache exists and works as intended.
            # If check_cache is part of the pocketoptionapi library, it should be fine.
            # Otherwise, this part might need adjustment.
            pair_id_str = str(_global_value.pairs[pair_name]["id"])
            if hasattr(_global_value, 'check_cache') and not _global_value.check_cache(pair_id_str):
                # Fetch history for the last 7 days if not in cache
                end_time_ts = int(datetime.now().timestamp()) - (86400 * 7)
                # The API's get_history might take start_time and end_time, or just end_time and count.
                # Adjusting based on typical API patterns. Original used end_time.
                df_history = _api.get_history(pair_name, _period, end_time=end_time_ts)
                # Process df_history as needed (e.g., save to cache)
                _global_value.logger(f"[PocketFunctions] Fetched history for {pair_name}. DF length: {len(df_history) if df_history is not None else 0}", "DEBUG")
            else:
                _global_value.logger(f"[PocketFunctions] Cache hit or check_cache not available for {pair_name}. Skipping history fetch.", "DEBUG")
    else:
        _global_value.logger("[PocketFunctions] Prepare_get_history failed. Cannot fetch history.", "ERROR")
