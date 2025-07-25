import time, math, asyncio, json, threading
from datetime import datetime
from pocketoptionapi.stable_api import PocketOption
import pocketoptionapi.global_value as global_value
import talib.abstract as ta
import numpy as np
import pandas as pd
#import freqtrade.vendor.qtpylib.indicators as qtpylib

global_value.loglevel = 'INFO'

# Session configuration
start_counter = time.perf_counter()

### REAL SSID Format::
#ssid = """42["auth",{"session":"a:4:{s:10:\\"session_id\\";s:32:\\"aa11b2345c67d89e0f1g23456h78i9jk\\";s:10:\\"ip_address\\";s:11:\\"11.11.11.11\\";s:10:\\"user_agent\\";s:111:\\"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36\\";s:13:\\"last_activity\\";i:1234567890;}1234a5b678901cd2efghi34j5678kl90","isDemo":0,"uid":12345678,"platform":2}]"""
#ssid = """42["auth",{"session":"a:4:{s:10:\"session_id\";s:32:\"9b4dcc08de7b80bea558465493b51d00\";s:10:\"ip_address\";s:13:\"105.113.81.31\";s:10:\"user_agent\";s:84:\"Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:140.0) Gecko/20100101 Firefox/140.0\";s:13:\"last_activity\";i:1749932489;}d8061221af16bc4365cadb486106c099","isDemo":0,"uid":34048913,"platform":1,"isFastHistory":true}]"""

#demo = False

### DEMO SSID Format::
#ssid = """42["auth",{"session":"abcdefghijklm12nopqrstuvwx","isDemo":1,"uid":12345678,"platform":2}]"""
#demo = True

ssid = """42["auth",{"session":"1620e72bltrkeb5e290f3etbcb","isDemo":1,"uid":34048913,"platform":1,"isFastHistory":true}]"""
demo = True

days = 365
min_payout = 80
period = 60
expiration = 60
api = PocketOption(ssid,demo)

# Connect to API
api.connect()


def get_payout():
    try:
        d = json.loads(global_value.PayoutData)
        for pair in d:
            # |0| |  1  |  |  2  |  |  3  | |4 | 5 |6 | 7 | 8| 9| 10 |11| 12| 13        | 14   | | 15,                                                                                                                                                                                     |  16| 17| 18        |
            # [5, '#AAPL', 'Apple', 'stock', 2, 50, 60, 30, 3, 0, 170, 0, [], 1743724800, False, [{'time': 60}, {'time': 120}, {'time': 180}, {'time': 300}, {'time': 600}, {'time': 900}, {'time': 1800}, {'time': 2700}, {'time': 3600}, {'time': 7200}, {'time': 10800}, {'time': 14400}], -1, 60, 1743784500],
            if len(pair) == 19:
                global_value.logger('id: %s, name: %s, typ: %s, active: %s' % (str(pair[1]), str(pair[2]), str(pair[3]), str(pair[14])), "DEBUG")
                #if pair[14] == True and pair[5] >= min_payout and "_otc" not in pair[1] and pair[3] == "currency":         # Get all non OTC Currencies with min_payout
                #if pair[14] == True and pair[5] >= min_payout and "_otc" in pair[1]:                                       # Get all OTC Markets with min_payout
                #if pair[14] == True and pair[3] == "cryptocurrency" and pair[5] >= min_payout and "_otc" not in pair[1]:   # Get all non OTC Cryptocurrencies
                #if pair[14] == True:                                                                                       # Get All that online
                p = {}
                p['id'] = pair[0]
                p['payout'] = pair[5]
                p['type'] = pair[3]
                global_value.pairs[pair[1]] = p
        return True
    except:
        return False


def prepare_get_history():
    try:
        data = get_payout()
        if data: return True
        else: return False
    except:
        return False


def start_get_history():
    while global_value.websocket_is_connected is False:
        time.sleep(0.1)
    time.sleep(2)
    saldo = api.get_balance()
    global_value.logger('Account Balance: %s' % str(saldo), "INFO")
    prep = prepare_get_history()
    if prep:
        i = 0
        for pair in global_value.pairs:
            time_start = int(datetime.now().timestamp())
            time_red = int(datetime.now().timestamp()) - 86400 * days
            i += 1
            global_value.logger('! %s (%s/%s)' % (str(pair), str(i), str(len(global_value.pairs))), "INFO")
            if global_value.check_csv(pair, 'data'):
                csv = global_value.get_csv(pair, 'data')
                d = csv[1].split(',')[0]
                if csv[len(csv)-1] == '': c = csv[len(csv)-2].split(',')[0]
                else: c = csv[len(csv)-1].split(',')[0]
                if int(c) > time_red: time_start = int(c)
                else: time_start = 0
                if not time_start == 0:
                    df = api.get_history(pair, period, start_time=time_start, end_time=time_red)
                    if int(d) < time_start:
                        time_red = int(d)
                        if not time_start == 0:
                            df = api.get_history(pair, period, start_time=time_start, end_time=time_red)
            else:
                df = api.get_history(pair, period, start_time=time_start, end_time=time_red)


if __name__ == "__main__":
    start_get_history()
    end_counter = time.perf_counter()
    rund = math.ceil(end_counter - start_counter)
    # print(f'CPU-gebundene Task-Zeit: {rund} {end_counter - start_counter} Sekunden')
    global_value.logger("CPU-gebundene Task-Zeit: %s Sekunden" % str(int(end_counter - start_counter)), "INFO")

