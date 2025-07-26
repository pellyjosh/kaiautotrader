#!/usr/bin/env python3
"""
Test script to verify Telethon can connect to the Pocket Option Official Signal Bot
and receive messages from it.
"""

import asyncio
import os
from telethon import TelegramClient, events

# Your account configuration
API_ID = '23324590'
API_HASH = 'fdcd53d426aebd07096ff326bb124397'
PHONE_NUMBER = '+2348101572723'
SESSION_NAME = 'my_signal_listener'
TARGET_BOT_ID = 1385109737  # Pocket Option Official Signal Bot

async def test_bot_connection():
    # Ensure session directory exists
    session_folder = "../telegram_sessions"
    if not os.path.exists(session_folder):
        os.makedirs(session_folder)
        print(f"Created directory: {session_folder}")
    
    full_session_path = os.path.join(session_folder, SESSION_NAME)
    
    client = TelegramClient(full_session_path, API_ID, API_HASH)
    
    try:
        print("🔗 Connecting to Telegram...")
        await client.connect()
        
        if not await client.is_user_authorized():
            print(f"❌ User not authorized. Please run the basic auth test first.")
            return False
        
        print("✅ User authorized!")
        
        # Try to get the bot entity
        try:
            bot_entity = await client.get_entity(TARGET_BOT_ID)
            print(f"✅ Found bot: {bot_entity.first_name}")
            print(f"   Username: @{bot_entity.username}")
            print(f"   ID: {bot_entity.id}")
            print(f"   Is Bot: {bot_entity.bot}")
        except Exception as e:
            print(f"❌ Could not get bot entity: {e}")
            print("   This might mean:")
            print("   1. You haven't started a conversation with the bot")
            print("   2. The bot ID is incorrect")
            print("   3. The bot is not accessible")
            return False
        
        # Test message handler for the bot
        print(f"\n🎯 Setting up message listener for bot ID: {TARGET_BOT_ID}")
        
        @client.on(events.NewMessage(chats=[TARGET_BOT_ID]))
        async def message_handler(event):
            message = event.message.message
            sender = await event.get_sender()
            print(f"\n📩 New message from {sender.first_name}:")
            print(f"   Message: {message}")
            print(f"   Time: {event.message.date}")
            
        print("✅ Message handler set up successfully!")
        print("\n🔄 Listening for messages from the bot...")
        print("   Send a message to @PocketSignalBot or wait for signals")
        print("   Press Ctrl+C to stop listening")
        
        # Listen for 30 seconds or until interrupted
        try:
            await asyncio.wait_for(client.run_until_disconnected(), timeout=30.0)
        except asyncio.TimeoutError:
            print("\n⏰ Listening timeout reached (30 seconds)")
        except KeyboardInterrupt:
            print("\n⚠️  Stopped by user")
        
        return True
        
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False
    finally:
        if client.is_connected():
            await client.disconnect()
            print("🔌 Disconnected from Telegram")

def main():
    print("🤖 Pocket Option Signal Bot Connection Test")
    print("=" * 50)
    print(f"Phone: {PHONE_NUMBER}")
    print(f"Bot ID: {TARGET_BOT_ID}")
    print(f"Bot: @PocketSignalBot")
    print("=" * 50)
    
    success = asyncio.run(test_bot_connection())
    
    if success:
        print("\n✅ SUCCESS: Bot connection test completed!")
        print("   If you saw messages, your setup is working correctly.")
    else:
        print("\n❌ FAILED: Could not connect to the bot.")
        print("   Make sure you've started a conversation with @PocketSignalBot first.")

if __name__ == "__main__":
    main()
