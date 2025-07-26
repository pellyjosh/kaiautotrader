#!/bin/bash

# Debug logging
echo "$(date): Starting HuboluxAutoTrader service..." >> /opt/HuboluxAutoTrader/logs/start_debug.log
echo "User: $(whoami)" >> /opt/HuboluxAutoTrader/logs/start_debug.log
echo "Working directory: $(pwd)" >> /opt/HuboluxAutoTrader/logs/start_debug.log
echo "PATH: $PATH" >> /opt/HuboluxAutoTrader/logs/start_debug.log

# Set environment variables
export HOME=/home/hubolux
export PYTHONPATH=/opt/HuboluxAutoTrader
export PATH=/opt/HuboluxAutoTrader/venv/bin:$PATH

# Change to the bot directory
cd /opt/HuboluxAutoTrader

echo "Changed to directory: $(pwd)" >> /opt/HuboluxAutoTrader/logs/start_debug.log
echo "Python executable: $(which python3)" >> /opt/HuboluxAutoTrader/logs/start_debug.log

# Start the bot with full output logging
exec /opt/HuboluxAutoTrader/venv/bin/python3 bot.py 2>&1
