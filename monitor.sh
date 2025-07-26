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
