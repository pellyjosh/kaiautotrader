# VPS Deployment Guide for HuboluxAutoTrader Bot

## Prerequisites

1. **VPS Requirements:**

   - Ubuntu 20.04 LTS or 22.04 LTS
   - Minimum 2GB RAM (4GB recommended)
   - At least 20GB disk space
   - Stable internet connection

2. **Access Requirements:**
   - Root or sudo access to VPS
   - SSH access configured

## Step-by-Step Deployment

### 1. Initial VPS Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install basic tools
sudo apt install -y curl wget git htop nano

# Create swap file (if not exists)
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### 2. Database Setup (MySQL)

```bash
# Install MySQL
sudo apt install -y mysql-server

# Secure MySQL installation
sudo mysql_secure_installation

# Create database and user for the bot
sudo mysql -u root -p
```

SQL commands to run in MySQL:

```sql
CREATE DATABASE HuboluxAutoTrader;
CREATE USER 'tradingbot'@'localhost' IDENTIFIED BY 'your_secure_password';
GRANT ALL PRIVILEGES ON HuboluxAutoTrader.* TO 'tradingbot'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

### 3. Upload Bot Files

Option A: Using git (recommended)

```bash
# Clone your repository
cd /tmp
git clone https://github.com/pellyjosh/kaiautotrader.git
```

Option B: Using SCP

```bash
# From your local machine
scp -r /path/to/kaiSignalTrade user@your-vps-ip:/tmp/
```

### 4. Run Deployment Script

```bash
# Copy files to temporary location if not already there
cd /tmp/HuboluxAutoTrader

# Make deployment script executable
chmod +x deploy.sh

# Run full setup (as root)
sudo ./deploy.sh setup
```

### 5. Configure Database Settings

```bash
# Switch to bot user
sudo su - tradingbot

# Navigate to bot directory
cd /opt/HuboluxAutoTrader

# Edit database configuration
nano db/database_config.py
```

Update the database configuration:

```python
DATABASE_TYPE = "mysql"

MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'tradingbot',
    'password': 'your_secure_password',
    'database': 'kaiSignalTrade',
    'port': 3306
}
```

### 6. Setup Bot Accounts

```bash
# Add your trading accounts
python tools/manage_accounts_enhanced.py add
```

### 7. Start the Bot

```bash
# Exit from bot user back to your user
exit

# Start the bot service
sudo systemctl start kaiSignalTrade

# Check status
sudo systemctl status kaiSignalTrade

# View logs
sudo ./deploy.sh logs
```

## Monitoring and Maintenance

### Service Management Commands

```bash
# Start bot
sudo systemctl start kaiSignalTrade

# Stop bot
sudo systemctl stop kaiSignalTrade

# Restart bot
sudo systemctl restart kaiSignalTrade

# Check status
sudo systemctl status kaiSignalTrade

# View logs
sudo journalctl -u kaiSignalTrade -f

# Or use the deployment script
./deploy.sh status
./deploy.sh logs 100
```

### Log Files Locations

- Main bot log: `/opt/kaiSignalTrade/logs/bot.log`
- Error log: `/opt/kaiSignalTrade/logs/bot.error.log`
- Monitor log: `/opt/kaiSignalTrade/logs/monitor.log`

### Monitoring Setup

The deployment script automatically sets up:

1. **Systemd service** - Automatically restarts bot if it crashes
2. **Monitoring script** - Checks bot health every 5 minutes
3. **Log rotation** - Prevents logs from filling up disk space
4. **Resource limits** - Prevents bot from using too much memory

### Manual Health Checks

```bash
# Check if bot process is running
ps aux | grep bot.py

# Check memory usage
free -h

# Check disk space
df -h

# Check database connection
mysql -u tradingbot -p kaiSignalTrade -e "SHOW TABLES;"

# Check recent bot activity
tail -f /opt/kaiSignalTrade/logs/bot.log
```

## Security Considerations

### 1. Firewall Setup

```bash
# Install UFW firewall
sudo apt install -y ufw

# Default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH (change 22 to your SSH port if different)
sudo ufw allow 22/tcp

# Allow MySQL (only if accessing from external)
# sudo ufw allow from YOUR_IP to any port 3306

# Enable firewall
sudo ufw enable
```

### 2. SSH Security

```bash
# Edit SSH config
sudo nano /etc/ssh/sshd_config
```

Recommended settings:

```
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
Port 2222  # Change from default 22
```

### 3. Automatic Updates

```bash
# Install unattended upgrades
sudo apt install -y unattended-upgrades

# Configure automatic security updates
sudo dpkg-reconfigure -plow unattended-upgrades
```

## Backup Strategy

### 1. Database Backup Script

Create `/opt/kaiSignalTrade/backup_db.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/opt/kaiSignalTrade/backups"
mkdir -p "$BACKUP_DIR"

mysqldump -u tradingbot -p kaiSignalTrade > "$BACKUP_DIR/db_backup_$(date +%Y%m%d_%H%M%S).sql"

# Keep only last 7 days of backups
find "$BACKUP_DIR" -name "db_backup_*.sql" -mtime +7 -delete
```

### 2. Add to Crontab

```bash
# Add daily database backup
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/kaiSignalTrade/backup_db.sh") | crontab -
```

## Troubleshooting

### Common Issues

1. **Bot won't start:**

   ```bash
   # Check service status
   sudo systemctl status kaiSignalTrade

   # Check logs
   sudo journalctl -u kaiSignalTrade -n 50
   ```

2. **Database connection errors:**

   ```bash
   # Test database connection
   mysql -u tradingbot -p kaiSignalTrade

   # Check MySQL service
   sudo systemctl status mysql
   ```

3. **Memory issues:**

   ```bash
   # Check memory usage
   free -h

   # Check swap usage
   swapon -s
   ```

4. **Permission issues:**

   ```bash
   # Fix ownership
   sudo chown -R tradingbot:tradingbot /opt/kaiSignalTrade

   # Fix permissions
   sudo chmod +x /opt/kaiSignalTrade/deploy.sh
   ```

### Performance Monitoring

```bash
# Monitor system resources
htop

# Monitor disk I/O
iotop

# Monitor network connections
netstat -tulpn

# Check bot-specific metrics
./deploy.sh status
```

## Updating the Bot

```bash
# Stop the bot
sudo systemctl stop kaiSignalTrade

# Backup current version
sudo cp -r /opt/kaiSignalTrade /opt/kaiSignalTrade_backup_$(date +%Y%m%d)

# Pull latest changes (if using git)
cd /opt/kaiSignalTrade
sudo -u tradingbot git pull

# Update dependencies if needed
sudo -u tradingbot bash -c "source venv/bin/activate && pip install -r requirements.txt"

# Start the bot
sudo systemctl start kaiSignalTrade

# Check status
./deploy.sh status
```

## Alert Configuration

### Email Alerts (Optional)

1. Install mail utility:

   ```bash
   sudo apt install -y mailutils
   ```

2. Configure email in monitoring script:
   ```bash
   sudo nano /opt/kaiSignalTrade/monitor.sh
   # Update ALERT_EMAIL variable
   ```

### Webhook Alerts (Recommended)

Set up webhook notifications for Discord/Slack:

```bash
# Edit monitoring script to add webhook URL
sudo nano /opt/kaiSignalTrade/monitor.sh
```

This completes the VPS deployment setup for 24/7 operation!
