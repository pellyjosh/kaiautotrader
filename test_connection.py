import time
from pocketoptionapi.stable_api import PocketOption
import pocketoptionapi.global_value as global_value

# --- Configuration ---
# PASTE YOUR LATEST SSID HERE
ssid = """42["auth",{"session":"1620e72bltrkeb5e290f3etbcb","isDemo":1,"uid":34048913,"platform":1,"isFastHistory":true}]"""
demo = True # Make sure this matches your SSID type

global_value.loglevel = 'DEBUG' # Enable debug logging for the library

print(f"Attempting to connect with SSID: {ssid[:60]}...")
print(f"Demo mode: {demo}")

try:
    api = PocketOption(ssid, demo)
    print(f"PocketOption instance created.")
    print(f"websocket_is_connected immediately after init: {global_value.websocket_is_connected}")

    print("Sleeping for 5 seconds to allow connection...")
    time.sleep(5) # Give it a bit more time

    print(f"websocket_is_connected after 5s sleep: {global_value.websocket_is_connected}")

    if global_value.websocket_is_connected:
        print("SUCCESS: WebSocket connection appears to be established!")
        balance = api.get_balance()
        print(f"Account Balance: {balance}")
    else:
        print("FAILURE: WebSocket connection NOT established after 5 seconds.")
        # You could try to see if any specific error is stored in global_value if the lib does that
        if hasattr(global_value, 'websocket_error_message'):
             print(f"Websocket error message from global_value: {global_value.websocket_error_message}")


except Exception as e:
    print(f"An error occurred during PocketOption instantiation or connection: {e}")

print("Test finished.")
