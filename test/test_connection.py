# In test_connection.py
import time
from pocketoptionapi.stable_api import PocketOption
import pocketoptionapi.global_value as global_value

# Use one of your SSIDs that is failing in the bot
ssid = """42["auth",{"session":"bpajv9apd668u8qkcdp4i34vc0","isDemo":1,"uid":104296609,"platform":1,"isFastHistory":true}]""" # Example: pelly_demo
demo = True

global_value.loglevel = 'DEBUG'
print(f"Testing connection for SSID (demo: {demo}): {ssid[:60]}...")

api = None
try:
    api = PocketOption(ssid, demo)
    print("PocketOption instance created.")
    print(f"websocket_is_connected immediately after init: {global_value.websocket_is_connected}")

    print("Calling api.connect()...")
    api.connect() # Explicit connect
    print("api.connect() called.")

    # Wait for connection
    connection_timeout = 30
    start_time = time.time()
    connected = False
    while time.time() - start_time < connection_timeout:
        if global_value.websocket_is_connected:
            print(f"SUCCESS: WebSocket connected after {time.time() - start_time:.2f} seconds!")
            balance = api.get_balance()
            print(f"Account Balance: {balance}")
            connected = True
            break
        time.sleep(0.2)

    if not connected:
        print(f"FAILURE: WebSocket did NOT connect within {connection_timeout} seconds.")
        if hasattr(global_value, 'websocket_error_message') and global_value.websocket_error_message:
             print(f"Last websocket error from global_value: {global_value.websocket_error_message}")

except Exception as e:
    print(f"An error occurred: {e}")
finally:
    # The library doesn't have an explicit disconnect for the stable_api in the same way.
    # If api object exists and has a way to close, you might call it.
    # For now, just ending the script.
    print("Test finished.")
