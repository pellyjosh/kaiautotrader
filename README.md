# 🚀 PocketOption Signal Trading Bot with Advanced Martingale

[![GitHub](https://img.shields.io/badge/GitHub-AdminhuDev-blue?style=flat-square&logo=github)](https://github.com/Mastaaa1987)
[![Website](https://img.shields.io/badge/Website-Portfolio-green?style=flat-square&logo=google-chrome)](https://Mastaaa1987.github.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)

> A comprehensive signal trading bot with global queue-based Martingale system for automated PocketOption trading via Telegram signals.

![Preview of API](pocketoption.png)

## ✨ Signal Trading Bot Features

- 🤖 **Telegram Signal Integration**: Connects to Telegram bots with 2FA support
- 🔄 **Global Martingale System**: Queue-based loss tracking with intelligent amount management
- � **Multi-Format Signal Parsing**: Supports various signal formats from different bots
- 💹 **Automated Trading**: Seamless PocketOption API integration with worker processes
- 🛡️ **Risk Management**: Configurable Martingale with enable/disable toggle
- � **Real-Time Monitoring**: Live trade tracking with comprehensive logging
- 🧪 **Comprehensive Testing**: Full test suite with demo scenarios

## 🎯 Core Components

### 1. Signal Detection (`detectsignal.py`)

- **Telegram Integration**: Telethon client with 2FA authentication
- **Signal Parsing**: Multiple format support with robust parsing logic
- **Global Martingale**: Queue-based system for loss tracking across all symbols
- **Trade Management**: Automated trade placement with result handling

### 2. PocketOption Integration (`worker.py`, `pocket_connector.py`)

- **Worker Processes**: Async trade execution with result feedback
- **API Connection**: Stable WebSocket connections with reconnection logic
- **Balance Management**: Real-time balance tracking and validation

### 3. Global Martingale System

- **Queue-Based Logic**: FIFO queue for tracking multiple concurrent losses
- **Symbol Agnostic**: Applies Martingale to next trade regardless of symbol
- **Win Reset**: Any win resets entire system globally
- **Enable/Disable Toggle**: Runtime control for Martingale activation

## 🛠️ Installation & Setup

### 1. Clone Repository

```bash
git clone <repository-url>
cd kaiSignalTrade
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Bot Settings

Edit `bot.py` to set your preferences:

```python
# Trading Configuration
BASE_AMOUNT = 1.0          # Base trade amount
MARTINGALE_MULTIPLIER = 2.0  # Multiplier for losses
MARTINGALE_ENABLED = True   # Enable/disable Martingale

# Telegram Configuration
API_ID = "your_api_id"
API_HASH = "your_api_hash"
PHONE_NUMBER = "your_phone"

# PocketOption Configuration
SSID = "your_ssid_here"
IS_DEMO = True  # Use demo account
```

## 📖 Basic Usage

### 1. Start the Signal Bot

```bash
python bot.py
```

### 2. Authenticate Telegram (First Run)

- Enter phone number
- Enter 2FA password when prompted
- Bot will save session for future use

### 3. Monitor Trading

The bot will:

- Connect to configured Telegram signal channels
- Parse incoming signals automatically
- Execute trades via PocketOption API
- Apply global Martingale logic for losses
- Log all activities with detailed information

## 🎯 Advanced Configuration

### Global Martingale System

The bot uses a sophisticated queue-based Martingale system:

```python
# How it works:
# 1. Base amount for first trade: $1.00
# 2. If loss: Add to queue, next trade = $2.00 (base * multiplier)
# 3. Another loss: Add to queue, next trade = $4.00 (base * multiplier^2)
# 4. Any win: Reset entire queue, back to base amount

# Example with mixed symbols:
# Trade 1: EURUSD $1.00 → Loss (queue: [1])
# Trade 2: GBPUSD $2.00 → Loss (queue: [1, 2])
# Trade 3: AUDUSD $4.00 → Win  (queue: [] - reset)
# Trade 4: EURUSD $1.00 → Fresh start
```

### Signal Format Support

The bot supports multiple signal formats:

```
Format 1: "EURUSD OTC M1 CALL"
Format 2: "CALL EURUSD-OTC 1MIN"
Format 3: "BUY GBPUSD 60s"
Format 4: "PUT AUDUSD_otc 1m"
```

### Risk Management Controls

```python
# In detectsignal.py
def toggle_martingale(enable: bool):
    """Runtime control of Martingale system"""

def get_current_martingale_status():
    """Monitor current system state"""

def reset_martingale():
    """Manual reset of queue"""
```

## 🧪 Testing & Validation

### Run Test Suite

```bash
# Test Martingale logic
python test/test_martingale_system.py

# Demo Martingale scenarios
python test/demo_enhanced_martingale.py

# Test PocketOption connection
python test/test_connection.py

# Test signal parsing
python test/test_signal_parsing.py
```

### Test Coverage

- ✅ Global queue-based Martingale logic
- ✅ Concurrent trade handling
- ✅ Enable/disable toggle functionality
- ✅ Win/loss scenarios with proper resets
- ✅ Signal parsing for multiple formats
- ✅ PocketOption API connectivity
- ✅ Telegram authentication with 2FA

## 📊 Monitoring & Logging

### Log Output Example

```
2024-01-15 10:30:15 - Telegram client started successfully
2024-01-15 10:30:16 - Connected to PocketOption (Demo: True)
2024-01-15 10:30:17 - Balance: $10,000.00
2024-01-15 10:30:18 - Martingale Status: Enabled | Queue: [] | Losses: 0
2024-01-15 10:31:22 - Signal detected: EURUSD CALL 1M
2024-01-15 10:31:23 - Trade placed: $1.00 EURUSD CALL 60s
2024-01-15 10:32:23 - Trade result: LOSS - Adding to Martingale queue
2024-01-15 10:32:24 - Martingale Status: Enabled | Queue: [1.0] | Losses: 1
2024-01-15 10:33:45 - Signal detected: GBPUSD PUT 1M
2024-01-15 10:33:46 - Trade placed: $2.00 GBPUSD PUT 60s (Martingale)
2024-01-15 10:34:46 - Trade result: WIN - Resetting Martingale queue
2024-01-15 10:34:47 - Martingale Status: Enabled | Queue: [] | Losses: 0
```

## ⚙️ File Structure

```
kaiSignalTrade/
├── bot.py                    # Main bot orchestration
├── detectsignal.py          # Signal detection & Martingale logic
├── worker.py                # PocketOption trading worker
├── pocket_connector.py      # API connection management
├── pocket_functions.py      # Utility functions
├── indicators.py            # Technical analysis tools
├── requirements.txt         # Dependencies
├── README.md               # This file
├── test/                   # Test suite
│   ├── test_martingale_system.py
│   ├── demo_enhanced_martingale.py
│   ├── test_connection.py
│   ├── test_signal_parsing.py
│   └── README.md
├── history/                # Trade history storage
├── telegram_sessions/      # Telegram session files
└── pocketoptionapi/       # PocketOption API library
```

## 🔧 Configuration Details

### Main Dependencies

```txt
telethon>=1.34.0         # Telegram client with 2FA support
websocket-client>=1.6.1  # WebSocket connections
requests>=2.31.0         # HTTP requests
python-dateutil>=2.8.2   # Date/time handling
pandas>=2.1.3            # Data analysis
```

### Getting the SSID

To get the SSID required for PocketOption authentication:

1. Log in to the PocketOption platform via browser
2. Open Developer Tools (F12)
3. Go to the "Network" tab
4. Look for WebSocket connections
5. Find the authentication message that contains the SSID
6. Copy the full SSID in the format shown in the example

How To get SSID.docx [HERE](https://github.com/Mastaaa1987/PocketOptionAPI/raw/refs/heads/master/How%20to%20get%20SSID.docx)

### Telegram API Setup

1. Go to https://my.telegram.org/
2. Create a new application
3. Get your `API_ID` and `API_HASH`
4. Configure in `bot.py`

## ⚠️ Risk Management

### Martingale Considerations

- **Exponential Growth**: Losses compound quickly (1→2→4→8→16...)
- **Capital Requirements**: Ensure sufficient balance for potential sequences
- **Max Loss Limits**: Consider implementing stop-loss after X consecutive losses
- **Win Probability**: System assumes eventual wins to reset the queue

### Recommended Settings

```python
# Conservative approach
BASE_AMOUNT = 0.5           # Start small
MARTINGALE_MULTIPLIER = 1.5 # Lower multiplier
MAX_CONSECUTIVE_LOSSES = 5  # Stop after 5 losses

# Aggressive approach
BASE_AMOUNT = 1.0           # Standard amount
MARTINGALE_MULTIPLIER = 2.0 # Double on loss
MAX_CONSECUTIVE_LOSSES = 7  # Higher tolerance
```

## 🤝 Contributing

Your contribution is very welcome! Follow these steps:

1. 🍴 Fork this repository
2. 🔄 Create a branch for your feature
   ```bash
   git checkout -b feature/MinhaFeature
   ```
3. 💻 Make your changes
4. ✅ Commit using conventional messages
   ```bash
   git commit -m "feat: Adds new functionality"
   ```
5. 📤 Push to your branch
   ```bash
   git push origin feature/MinhaFeature
   ```
6. 🔍 Open a Pull Request

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

This project is an unofficial implementation and has no connection with PocketOption. Use at your own risk.

## 📞 Support

- 📧 Email: [sebastianspaaa@gmail.com](mailto:sebastianspaaa@gmail.com)
- 💬 Telegram: [@devAdminhu](https://t.me/mastaaa667)
- 🌐 Website: [mastaaa1987.site](https://mastaaa1987.github.io)

---

<p align="center">
  Powered ❤️ by <a href="https://github.com/Mastaaa1987">Mastaaa1987</a>
</p>


# Add your pelly_demo account
python manage_accounts.py add "pelly_demo" '42["auth",{"session":"bpajv9apd668u8qkcdp4i34vc0","isDemo":1,"uid":104296609,"platform":1,"isFastHistory":true,"isOptimized":true}]' --demo true --enabled true

# Add other accounts as needed
python manage_accounts.py add "account_name" "ssid_string" --demo true/false --enabled true/false

# View all accounts
python manage_accounts.py list

# Enable/disable accounts dynamically
python manage_accounts.py enable account_name
python manage_accounts.py disable account_name