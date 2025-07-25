#!/usr/bin/env python3
"""
Test script to verify Telethon authentication with 2FA support.
This script will help you authenticate your Telegram account with 2FA enabled.
"""

import asyncio
import os
from telethon import TelegramClient

# Your account configuration (from detectsignal.py)
API_ID = '23324590'
API_HASH = 'fdcd53d426aebd07096ff326bb124397'
PHONE_NUMBER = '+2348101572723'
SESSION_NAME = 'my_signal_listener'
TARGET_BOT_ID = 1385109737  # Pocket Option Official Signal Bot

async def test_auth():
    # Ensure session directory exists
    session_folder = "../telegram_sessions"
    if not os.path.exists(session_folder):
        os.makedirs(session_folder)
        print(f"Created directory: {session_folder}")
    
    full_session_path = os.path.join(session_folder, SESSION_NAME)
    
    client = TelegramClient(full_session_path, API_ID, API_HASH)
    
    try:
        print("Connecting to Telegram...")
        await client.connect()
        
        if not await client.is_user_authorized():
            print(f"User not authorized. Sending code request to {PHONE_NUMBER}...")
            await client.send_code_request(PHONE_NUMBER)
            print(f"Please check your Telegram messages for the verification code.")
            
            while True:
                try:
                    code = input(f"Enter the verification code for {PHONE_NUMBER}: ")
                    await client.sign_in(PHONE_NUMBER, code)
                    print("✅ Successfully signed in with verification code!")
                    break
                except Exception as e:
                    error_str = str(e).lower()
                    print(f"❌ Sign-in error: {e}")
                    
                    # Enhanced 2FA detection
                    if any(keyword in error_str for keyword in ['password', 'two-factor', '2fa', 'two factor', 'cloud password']):
                        try:
                            password = input(f"Enter your 2FA password for {PHONE_NUMBER}: ")
                            await client.sign_in(password=password)
                            print("✅ Successfully signed in with 2FA password!")
                            break
                        except Exception as p_err:
                            print(f"❌ 2FA password error: {p_err}")
                            return False
                    elif 'invalid' in error_str or 'wrong' in error_str:
                        retry_choice = input("Code failed. Try 2FA password? (y/n): ").lower().strip()
                        if retry_choice == 'y':
                            try:
                                password = input(f"Enter your 2FA password for {PHONE_NUMBER}: ")
                                await client.sign_in(password=password)
                                print("✅ Successfully signed in with 2FA password!")
                                break
                            except Exception as p_err:
                                print(f"❌ 2FA password error: {p_err}. Will retry with code.")
                                continue
                    else:
                        print("Authentication failed. Please try again or check your credentials.")
                        return False
        else:
            print("✅ User already authorized!")
        
        # Test that we can get user info
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"✅ Authentication successful!")
            print(f"   User: {me.first_name} {me.last_name or ''}")
            print(f"   Username: @{me.username or 'None'}")
            print(f"   Phone: {me.phone}")
            print(f"   Session saved as: {full_session_path}.session")
            return True
        else:
            print("❌ Authentication failed")
            return False
            
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False
    finally:
        if client.is_connected():
            await client.disconnect()
            print("Disconnected from Telegram")

def main():
    print("🔐 Telethon 2FA Authentication Test")
    print("=" * 40)
    print(f"Phone: {PHONE_NUMBER}")
    print(f"Session: {SESSION_NAME}")
    print("=" * 40)
    
    success = asyncio.run(test_auth())
    
    if success:
        print("\n✅ SUCCESS: Your Telethon is now configured and ready!")
        print("   You can now run your main bot and it should authenticate automatically.")
    else:
        print("\n❌ FAILED: Authentication was not successful.")
        print("   Please check your API_ID, API_HASH, and phone number.")

if __name__ == "__main__":
    main()
