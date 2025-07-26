#!/usr/bin/env python3
"""
Script to start a conversation with the Pocket Option Signal Bot and verify access.
This will send a /start command to the bot to initiate communication.
"""

import asyncio
import os
from telethon import TelegramClient, events

# Your account configuration
API_ID = '23324590'
API_HASH = 'fdcd53d426aebd07096ff326bb124397'
PHONE_NUMBER = '+2348101572723'
SESSION_NAME = 'my_signal_listener'
BOT_USERNAME = '@PocketSignalBot'  # Bot username
BOT_ID = 1385109737  # Bot ID

async def start_conversation_with_bot():
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
            print("❌ User not authorized. Please run test_telethon_auth.py first.")
            return False
        
        print("✅ User authorized!")
        
        # Try to get the bot by username first
        try:
            print(f"🔍 Looking up bot by username: {BOT_USERNAME}")
            bot_entity = await client.get_entity(BOT_USERNAME)
            print(f"✅ Found bot: {bot_entity.first_name}")
            print(f"   Username: @{bot_entity.username}")
            print(f"   ID: {bot_entity.id}")
            print(f"   Is Bot: {bot_entity.bot}")
            
            # Send /start command to initiate conversation
            print(f"\n📤 Sending /start command to {BOT_USERNAME}...")
            await client.send_message(bot_entity, '/start')
            print("✅ /start command sent successfully!")
            
            # Wait a moment for any auto-reply
            print("⏳ Waiting for bot response...")
            await asyncio.sleep(3)
            
            # Try to get recent messages from the bot
            print("📬 Checking for messages from the bot...")
            async for message in client.iter_messages(bot_entity, limit=5):
                print(f"   📩 {message.date}: {message.message}")
            
            return True
            
        except Exception as e:
            print(f"❌ Could not find bot by username {BOT_USERNAME}: {e}")
            
            # Try direct message to bot ID
            try:
                print(f"🔍 Trying to access bot by ID: {BOT_ID}")
                bot_entity = await client.get_entity(BOT_ID)
                print(f"✅ Found bot by ID: {bot_entity.first_name}")
                return True
            except Exception as e2:
                print(f"❌ Could not access bot by ID either: {e2}")
                print("\n🔧 SOLUTION:")
                print("1. Open Telegram app on your phone/computer")
                print(f"2. Search for '{BOT_USERNAME}' or 'Pocket Option Official Signal Bot'")
                print("3. Start a conversation by sending /start to the bot")
                print("4. Wait for the bot to respond")
                print("5. Then run this script again")
                return False
        
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False
    finally:
        if client.is_connected():
            await client.disconnect()
            print("🔌 Disconnected from Telegram")

async def test_bot_access_after_conversation():
    """Test if we can now access the bot after starting conversation"""
    session_folder = "../telegram_sessions"
    full_session_path = os.path.join(session_folder, SESSION_NAME)
    
    client = TelegramClient(full_session_path, API_ID, API_HASH)
    
    try:
        await client.connect()
        
        if not await client.is_user_authorized():
            print("❌ User not authorized.")
            return False
        
        # Test both username and ID access
        print(f"\n🧪 Testing bot access...")
        
        # Test by ID
        try:
            bot_entity = await client.get_entity(BOT_ID)
            print(f"✅ Bot accessible by ID: {bot_entity.first_name} (ID: {bot_entity.id})")
            
            # Set up a temporary message listener
            print("🎯 Setting up message listener for 10 seconds...")
            
            @client.on(events.NewMessage(chats=[BOT_ID]))
            async def temp_handler(event):
                print(f"📩 Received message: {event.message.message}")
            
            await asyncio.sleep(10)  # Listen for 10 seconds
            print("✅ Message listener test completed!")
            return True
            
        except Exception as e:
            print(f"❌ Still cannot access bot: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Test error: {e}")
        return False
    finally:
        if client.is_connected():
            await client.disconnect()

def main():
    print("🤖 Pocket Option Signal Bot - Start Conversation")
    print("=" * 55)
    print("This script will help you start a conversation with the bot")
    print("so that your trading bot can receive signals from it.")
    print("=" * 55)
    
    # Step 1: Try to start conversation
    success = asyncio.run(start_conversation_with_bot())
    
    if success:
        print("\n✅ SUCCESS: Conversation started with the bot!")
        print("🔄 Now testing bot access...")
        
        # Step 2: Test access
        test_success = asyncio.run(test_bot_access_after_conversation())
        
        if test_success:
            print("\n🎉 PERFECT: Bot is now accessible!")
            print("   Your signal detector should now work correctly.")
            print("   You can run your main trading bot.")
        else:
            print("\n⚠️  Bot conversation started but access test failed.")
            print("   Try running the bot connection test again in a few minutes.")
    else:
        print("\n❌ FAILED: Could not start conversation with bot.")
        print("   Please follow the manual steps above.")

if __name__ == "__main__":
    main()
