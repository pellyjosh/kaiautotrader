# Test Scripts

This folder contains various test scripts for the HuboluxTradingBot project.

## Available Tests

### 1. `test_telethon_auth.py`

Tests Telethon authentication with 2FA support.

- Verifies your Telegram API credentials
- Handles 2FA authentication
- Creates session files for future use

**Usage:**

```bash
python test/test_telethon_auth.py
```

### 2. `start_bot_conversation.py`

Starts a conversation with the Pocket Option Signal Bot.

- Sends /start command to the bot
- Initiates communication so signals can be received
- Tests basic bot accessibility

**Usage:**

```bash
python test/start_bot_conversation.py
```

### 3. `test_bot_connection.py`

Tests connection to the Pocket Option Official Signal Bot.

- Verifies you can connect to the signal bot
- Listens for incoming messages from the bot
- Tests message handling

**Usage:**

```bash
python test/test_bot_connection.py
```

### 4. `test_signal_parser.py`

Tests signal parsing for Pocket Option bot message format.

- Validates signal parsing logic
- Tests with real bot message formats
- Verifies pair normalization

**Usage:**

```bash
python test/test_signal_parser.py
```

### 5. `test_connection.py`

Tests basic PocketOption API connection.

- Verifies PocketOption API connectivity
- Tests basic trading functions

**Usage:**

```bash
python test/test_connection.py
```

### 6. `test_martingale_system.py`

Tests the global queue-based Martingale trading system logic.

- Tests global loss tracking (not per-symbol)
- Tests queue-based amount assignment for concurrent trades
- Tests FIFO queue management for Martingale amounts
- Tests enable/disable toggle functionality
- Tests win resets entire system globally
- Validates proper Martingale progression regardless of symbols

**Usage:**

```bash
python test/test_martingale_system.py
```

### 7. `demo_enhanced_martingale.py`

Interactive demonstration of the global queue-based Martingale system.

- Shows how mixed symbol signals are handled
- Demonstrates queue buildup with multiple losses
- Shows how any win resets the entire system
- Provides real-world trading scenarios
- Illustrates risk management considerations

**Usage:**

```bash
python test/demo_enhanced_martingale.py
```

## Running Tests

Make sure you're in the project root directory and use the virtual environment:

```bash
cd "/Users/Hubolux/Documents/Project 001/HuboluxJobs/Trading/HuboluxTradingBot"
source venv/bin/activate  # or use the full path to python
python test/test_name.py
```

## Test Order Recommendation

1. First run `test_connection.py` to verify PocketOption API works
2. Then run `test_telethon_auth.py` to set up Telegram authentication
3. Run `start_bot_conversation.py` to start conversation with the signal bot
4. Run `test_bot_connection.py` to test signal bot connectivity
5. Run `test_signal_parser.py` to verify signal parsing works
6. Run `test_martingale_system.py` to verify Martingale logic works

## Notes

- All test scripts use the same configuration from `detectsignal.py`
- Session files will be created in the `telegram_sessions/` folder
- Make sure your API credentials are correctly configured before running tests
