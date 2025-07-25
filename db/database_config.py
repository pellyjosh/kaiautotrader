# Database Configuration for KaiSignalTrade Bot
# Copy this file to config.py and update with your settings

# === DATABASE CONFIGURATION ===

# Database type: "sqlite" or "mysql"
DATABASE_TYPE = "mysql"

# === SQLite Configuration (if using SQLite) ===
SQLITE_DB_PATH = "trades.db"

# === MySQL Configuration (if using MySQL) ===
MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'kai_signal_trade',
    'port': 3306
}

# === Martingale Configuration ===
MARTINGALE_CONFIG = {
    'enabled': True,
    'base_amount': 1.0,
    'multiplier': 2.5,
    'max_consecutive_losses': 5,  # Stop Martingale after this many losses
    'reset_on_win': True
}

# === Performance Tracking ===
PERFORMANCE_CONFIG = {
    'track_daily_stats': True,
    'auto_backup': True,
    'backup_interval_hours': 24,
    'max_backup_files': 30
}

# === Database Maintenance ===
MAINTENANCE_CONFIG = {
    'auto_cleanup_old_trades': True,
    'keep_trades_days': 90,  # Keep trades for 90 days
    'vacuum_interval_hours': 168  # Weekly vacuum for SQLite
}
