#!/bin/bash

# Deployment script for HuboluxAutoTrader Bot
# Usage: ./deploy.sh [start|stop|restart|status|logs]

BOT_NAME="HuboluxAutoTrader"
BOT_DIR="/opt/HuboluxAutoTrader"
BOT_USER="tradingbot"
PYTHON_ENV="$BOT_DIR/venv"
LOG_DIR="$BOT_DIR/logs"
PID_FILE="$BOT_DIR/$BOT_NAME.pid"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

# Check if running as root for system setup
check_root() {
    if [[ $EUID -eq 0 ]]; then
        return 0
    else
        return 1
    fi
}

# Install system dependencies
install_dependencies() {
    log "Installing system dependencies..."
    
    # Update package list
    apt update
    
    # Install required packages
    apt install -y python3 python3-pip python3-venv git supervisor nginx mysql-client
    
    # Install Python development headers (needed for some packages)
    apt install -y python3-dev build-essential libssl-dev libffi-dev
    
    log "System dependencies installed successfully"
}

# Create bot user
create_bot_user() {
    if ! id "$BOT_USER" &>/dev/null; then
        log "Creating bot user: $BOT_USER"
        useradd -r -m -s /bin/bash "$BOT_USER"
        usermod -aG sudo "$BOT_USER"
    else
        log "Bot user $BOT_USER already exists"
    fi
}

# Setup bot directory and permissions
setup_directories() {
    log "Setting up directories..."
    
    # Create main directory
    mkdir -p "$BOT_DIR"
    mkdir -p "$LOG_DIR"
    
    # Set ownership
    chown -R "$BOT_USER:$BOT_USER" "$BOT_DIR"
    
    # Set permissions
    chmod 755 "$BOT_DIR"
    chmod 755 "$LOG_DIR"
    
    log "Directories created and configured"
}

# Setup Python virtual environment
setup_python_env() {
    log "Setting up Python virtual environment..."
    
    # Create virtual environment
    sudo -u "$BOT_USER" python3 -m venv "$PYTHON_ENV"
    
    # Activate and upgrade pip
    sudo -u "$BOT_USER" bash -c "source $PYTHON_ENV/bin/activate && pip install --upgrade pip"
    
    log "Python virtual environment created"
}

# Install Python dependencies
install_python_deps() {
    log "Installing Python dependencies..."
    
    if [[ -f "$BOT_DIR/requirements.txt" ]]; then
        sudo -u "$BOT_USER" bash -c "source $PYTHON_ENV/bin/activate && pip install -r $BOT_DIR/requirements.txt"
    else
        warn "requirements.txt not found, skipping Python dependencies"
    fi
}

# Create systemd service
create_systemd_service() {
    log "Creating systemd service..."
    
    cat > /etc/systemd/system/HuboluxAutoTrader.service << EOF
[Unit]
Description=HuboluxAutoTrader Trading Bot
After=network.target mysql.service
Wants=mysql.service

[Service]
Type=simple
User=$BOT_USER
Group=$BOT_USER
WorkingDirectory=$BOT_DIR
Environment=PATH=$PYTHON_ENV/bin
ExecStart=$PYTHON_ENV/bin/python bot.py
Restart=always
RestartSec=10
StandardOutput=append:$LOG_DIR/bot.log
StandardError=append:$LOG_DIR/bot.error.log

# Resource limits
LimitNOFILE=65536
MemoryLimit=1G

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=$BOT_DIR $LOG_DIR /tmp

[Install]
WantedBy=multi-user.target
EOF

    # Reload systemd and enable service
    systemctl daemon-reload
    systemctl enable HuboluxAutoTrader.service
    
    log "Systemd service created and enabled"
}

# Create supervisor configuration (alternative to systemd)
create_supervisor_config() {
    log "Creating supervisor configuration..."
    
    cat > /etc/supervisor/conf.d/HuboluxAutoTrader.conf << EOF
[program:HuboluxAutoTrader]
command=$PYTHON_ENV/bin/python bot.py
directory=$BOT_DIR
user=$BOT_USER
autostart=true
autorestart=true
startsecs=10
startretries=3
redirect_stderr=true
stdout_logfile=$LOG_DIR/bot.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=5
environment=PATH="$PYTHON_ENV/bin:%(ENV_PATH)s"
EOF

    # Update supervisor configuration
    supervisorctl reread
    supervisorctl update
    
    log "Supervisor configuration created"
}

# Setup log rotation
setup_log_rotation() {
    log "Setting up log rotation..."
    
    cat > /etc/logrotate.d/HuboluxAutoTrader << EOF
$LOG_DIR/*.log {
    daily
    missingok
    rotate 30
    compress
    notifempty
    create 644 $BOT_USER $BOT_USER
    postrotate
        systemctl reload HuboluxAutoTrader || true
    endscript
}
EOF

    log "Log rotation configured"
}

# Setup monitoring script
create_monitoring_script() {
    log "Creating monitoring script..."
    
    cat > "$BOT_DIR/monitor.sh" << 'EOF'
#!/bin/bash

# Bot monitoring script
BOT_NAME="HuboluxAutoTrader"
LOG_FILE="/opt/HuboluxAutoTrader/logs/monitor.log"
ALERT_EMAIL="your-email@example.com"  # Change this to your email

log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

check_bot_status() {
    if systemctl is-active --quiet HuboluxAutoTrader; then
        return 0
    else
        return 1
    fi
}

check_database_connection() {
    # Add your database connection check here
    # Example for MySQL:
    # mysql -h your-host -u your-user -p your-password -e "SELECT 1;" >/dev/null 2>&1
    return 0
}

restart_bot() {
    log_message "Restarting bot due to health check failure"
    systemctl restart HuboluxAutoTrader
    sleep 30
}

send_alert() {
    local message="$1"
    log_message "ALERT: $message"
    
    # Send email alert (requires mail command to be configured)
    # echo "$message" | mail -s "KaiSignalTrade Alert" "$ALERT_EMAIL"
    
    # Or use webhook notification
    # curl -X POST -H 'Content-type: application/json' \
    #      --data "{\"text\":\"$message\"}" \
    #      YOUR_WEBHOOK_URL
}

# Main monitoring logic
main() {
    if ! check_bot_status; then
        log_message "Bot is not running, attempting to restart..."
        restart_bot
        
        if ! check_bot_status; then
            send_alert "Failed to restart HuboluxAutoTrader bot"
        else
            log_message "Bot restarted successfully"
        fi
    fi
    
    if ! check_database_connection; then
        send_alert "Database connection failed"
    fi
}

main "$@"
EOF

    chmod +x "$BOT_DIR/monitor.sh"
    chown "$BOT_USER:$BOT_USER" "$BOT_DIR/monitor.sh"
    
    log "Monitoring script created"
}

# Setup cron job for monitoring
setup_monitoring_cron() {
    log "Setting up monitoring cron job..."
    
    # Add cron job to check bot every 5 minutes
    (crontab -u "$BOT_USER" -l 2>/dev/null; echo "*/5 * * * * $BOT_DIR/monitor.sh") | crontab -u "$BOT_USER" -
    
    log "Monitoring cron job added"
}

# Start the bot
start_bot() {
    log "Starting HuboluxAutoTrader bot..."
    
    if systemctl is-active --quiet HuboluxAutoTrader; then
        warn "Bot is already running"
        return 0
    fi
    
    systemctl start HuboluxAutoTrader
    
    if systemctl is-active --quiet HuboluxAutoTrader; then
        log "Bot started successfully"
    else
        error "Failed to start bot"
        return 1
    fi
}

# Stop the bot
stop_bot() {
    log "Stopping HuboluxAutoTrader bot..."
    
    systemctl stop HuboluxAutoTrader
    log "Bot stopped"
}

# Restart the bot
restart_bot() {
    log "Restarting HuboluxAutoTrader bot..."
    
    systemctl restart HuboluxAutoTrader
    
    if systemctl is-active --quiet HuboluxAutoTrader; then
        log "Bot restarted successfully"
    else
        error "Failed to restart bot"
        return 1
    fi
}

# Show bot status
show_status() {
    echo "=== HuboluxAutoTrader Bot Status ==="
    systemctl status HuboluxAutoTrader --no-pager
    echo
    echo "=== Recent Logs ==="
    tail -20 "$LOG_DIR/bot.log" 2>/dev/null || echo "No logs found"
}

# Show logs
show_logs() {
    local lines=${1:-50}
    echo "=== Bot Logs (last $lines lines) ==="
    tail -n "$lines" "$LOG_DIR/bot.log" 2>/dev/null || echo "No logs found"
    
    echo
    echo "=== Error Logs (last $lines lines) ==="
    tail -n "$lines" "$LOG_DIR/bot.error.log" 2>/dev/null || echo "No error logs found"
}

# Full system setup (run once)
full_setup() {
    if ! check_root; then
        error "Full setup must be run as root"
        exit 1
    fi
    
    log "Starting full system setup..."
    
    install_dependencies
    create_bot_user
    setup_directories
    setup_python_env
    install_python_deps
    create_systemd_service
    setup_log_rotation
    create_monitoring_script
    setup_monitoring_cron
    
    log "Full setup completed successfully!"
    log "Next steps:"
    log "1. Copy your bot files to $BOT_DIR"
    log "2. Configure your database settings"
    log "3. Run: ./deploy.sh start"
}

# Main script logic
case "$1" in
    setup)
        full_setup
        ;;
    start)
        start_bot
        ;;
    stop)
        stop_bot
        ;;
    restart)
        restart_bot
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs "$2"
        ;;
    *)
        echo "Usage: $0 {setup|start|stop|restart|status|logs [lines]}"
        echo
        echo "Commands:"
        echo "  setup    - Full system setup (run once as root)"
        echo "  start    - Start the bot"
        echo "  stop     - Stop the bot"
        echo "  restart  - Restart the bot"
        echo "  status   - Show bot status"
        echo "  logs     - Show recent logs (optional: specify number of lines)"
        echo
        echo "Examples:"
        echo "  sudo ./deploy.sh setup"
        echo "  ./deploy.sh start"
        echo "  ./deploy.sh logs 100"
        exit 1
        ;;
esac
