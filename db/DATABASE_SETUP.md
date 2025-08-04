# HuboluxTradingBot Database Setup Guide

## 🗄️ Database Integration Overview

Your trading bot now has **comprehensive database support** for:

- **Trade tracking** - Every trade is recorded with full details
- **Martingale persistence** - Bot remembers loss streaks across restarts
- **Account management** - Track multiple PocketOption accounts
- **Performance analytics** - Daily/weekly performance statistics
- **Data backup** - Automated and manual backup capabilities

## 📋 Features Added

### ✅ **Persistent Martingale Memory**

- Bot remembers consecutive losses even after restarts
- Martingale multiplier progression continues correctly
- No loss of trading state due to crashes or restarts

### ✅ **Complete Trade History**

- Every trade recorded with timestamp, amount, result
- Martingale level tracking for each trade
- Signal source attribution (Telegram, manual, etc.)

### ✅ **Multi-Account Support**

- Track multiple demo/real accounts simultaneously
- Individual balance monitoring per account
- Account status tracking (active/inactive/error)

### ✅ **Performance Analytics**

- Daily win/loss statistics per account
- Profit/loss tracking with net results
- Martingale recovery success rates
- Comprehensive performance metrics

### ✅ **Database Flexibility**

- **SQLite** (default) - No setup required, file-based
- **MySQL** (optional) - For remote/shared database access

## 🚀 Quick Start

### 1. **Install Dependencies** (if needed)

```bash
# For MySQL support (optional)
pip install mysql-connector-python
```

### 2. **Configure Database**

Edit `database_config.py`:

```python
# Use SQLite (recommended for most users)
DATABASE_TYPE = "sqlite"
SQLITE_DB_PATH = "trades.db"

# OR use MySQL (for advanced users)
DATABASE_TYPE = "mysql"
MYSQL_CONFIG = {
    'host': 'your-mysql-server.com',
    'user': 'your_username',
    'password': 'your_password',
    'database': 'kaiautotrader',
    'port': 3306
}
```

### 3. **Test Database Setup**

```bash
python3 test_database.py
```

### 4. **Start Trading Bot**

```bash
python3 bot.py
```

The database will be automatically initialized on first run!

## 🔧 Database Management

### **View Statistics**

```bash
python3 db_admin.py stats
```

Shows total trades, win rate, Martingale state, etc.

### **View Connected Accounts**

```bash
python3 db_admin.py accounts
```

Lists all PocketOption accounts with balances.

### **View Recent Trades**

```bash
python3 db_admin.py trades --limit 20
python3 db_admin.py trades --worker pelly_demo
```

### **View Performance**

```bash
python3 db_admin.py performance --days 7
python3 db_admin.py performance --worker pelly_demo --days 30
```

### **Create Backup**

```bash
python3 db_admin.py backup
python3 db_admin.py backup --backup-path my_backup.json
```

### **Reset Martingale State** (if needed)

```bash
python3 db_admin.py reset-martingale
```

## 💾 **Database Files**

- **SQLite**: `trades.db` (created automatically)
- **Backups**: `backup_trades_YYYYMMDD_HHMMSS.json`
- **Config**: `database_config.py`

## 🔄 **Martingale Persistence Example**

**Before Database:**

```
Session 1: Loss -> Loss -> Loss (Bot crashes)
Session 2: Next trade uses base amount ❌ (memory lost)
```

**With Database:**

```
Session 1: Loss -> Loss -> Loss (Bot crashes)
Session 2: Next trade uses Martingale amount ✅ (memory restored)
```

## 📊 **Database Schema**

### **accounts** - PocketOption account tracking

- worker_name, ssid, is_demo, balance, status

### **trades** - Complete trade history

- trade_id, symbol, direction, amount, result, payout
- martingale_level, is_martingale_trade, timestamps

### **martingale_state** - Persistent Martingale memory

- consecutive_losses, current_multiplier, last_trade_id
- max_consecutive_losses, total_sequences

### **performance** - Daily performance statistics

- total_trades, win_rate, net_profit, martingale_recoveries
- per account and per day tracking

## 🚨 **Important Notes**

1. **Automatic Integration** - Database is automatically used by your bot
2. **Zero Downtime** - Database failures won't stop trading (graceful fallback)
3. **Backup Regularly** - Use `db_admin.py backup` for safety
4. **Martingale Recovery** - Bot will resume exact Martingale state after any restart
5. **Multi-Worker Safe** - Supports multiple PocketOption accounts simultaneously

## 🆘 **Troubleshooting**

### **Database Connection Issues**

```bash
# Test database connectivity
python3 test_database.py

# Check database file permissions (SQLite)
ls -la trades.db

# Reset database if corrupted
rm trades.db && python3 test_database.py
```

### **MySQL Setup Issues**

```bash
# Install MySQL connector
pip install mysql-connector-python

# Test MySQL connection
python3 -c "import mysql.connector; print('MySQL OK')"
```

### **Martingale State Issues**

```bash
# Check current Martingale state
python3 db_admin.py stats

# Reset if needed
python3 db_admin.py reset-martingale
```

## 🎯 **What This Solves**

✅ **"Bot lost my Martingale progress after restart"** - Now persisted  
✅ **"I can't track my trading performance"** - Full analytics available  
✅ **"Multiple accounts are confusing"** - Clear account separation  
✅ **"I need trading history for analysis"** - Complete trade records  
✅ **"Bot crashes lose important data"** - Everything saved automatically

Your bot is now **enterprise-ready** with professional data management! 🚀
