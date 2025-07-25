#!/usr/bin/env python3
"""
Health Check Script for HuboluxAutoTrader Bot
Monitors various aspects of the bot and sends alerts if issues are detected.
"""

import os
import sys
import time
import json
import smtplib
import requests
import subprocess
from datetime import datetime, timedelta
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart

# Add the bot directory to Python path
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BOT_DIR)

try:
    from db.database_manager import DatabaseManager
    from db.database_config import DATABASE_TYPE, SQLITE_DB_PATH, MYSQL_CONFIG
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    print("Warning: Database modules not available for health check")

class HealthChecker:
    def __init__(self, config_file='health_config.json'):
        self.config_file = os.path.join(BOT_DIR, config_file)
        self.load_config()
        self.alerts = []
        
    def load_config(self):
        """Load health check configuration"""
        default_config = {
            "check_interval": 300,  # 5 minutes
            "alerts": {
                "email": {
                    "enabled": False,
                    "smtp_server": "smtp.gmail.com",
                    "smtp_port": 587,
                    "from_email": "",
                    "from_password": "",
                    "to_emails": []
                },
                "webhook": {
                    "enabled": False,
                    "url": "",
                    "headers": {"Content-Type": "application/json"}
                }
            },
            "checks": {
                "process_running": True,
                "database_connection": True,
                "log_activity": True,
                "memory_usage": True,
                "disk_space": True,
                "trade_activity": True
            },
            "thresholds": {
                "memory_limit_mb": 1024,
                "disk_space_limit_percent": 90,
                "log_inactivity_minutes": 30,
                "trade_inactivity_hours": 24
            }
        }
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    self.config = json.load(f)
                # Merge with defaults to ensure all keys exist
                for key, value in default_config.items():
                    if key not in self.config:
                        self.config[key] = value
                    elif isinstance(value, dict):
                        for subkey, subvalue in value.items():
                            if subkey not in self.config[key]:
                                self.config[key][subkey] = subvalue
            except Exception as e:
                print(f"Error loading config: {e}. Using defaults.")
                self.config = default_config
        else:
            self.config = default_config
            self.save_config()
    
    def save_config(self):
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def log(self, message, level="INFO"):
        """Log message with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
        
        # Also log to file
        log_file = os.path.join(BOT_DIR, "logs", "health_check.log")
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        try:
            with open(log_file, 'a') as f:
                f.write(f"[{timestamp}] [{level}] {message}\n")
        except Exception:
            pass  # Don't fail if we can't write to log
    
    def add_alert(self, title, message, severity="WARNING"):
        """Add an alert to be sent"""
        self.alerts.append({
            "title": title,
            "message": message,
            "severity": severity,
            "timestamp": datetime.now().isoformat()
        })
        self.log(f"{severity}: {title} - {message}", severity)
    
    def check_process_running(self):
        """Check if the bot process is running"""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "HuboluxAutoTrader"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                self.add_alert(
                    "Bot Process Not Running",
                    "The HuboluxAutoTrader systemd service is not active",
                    "CRITICAL"
                )
                return False
            
            return True
        except Exception as e:
            self.add_alert(
                "Process Check Failed",
                f"Could not check process status: {e}",
                "ERROR"
            )
            return False
    
    def check_database_connection(self):
        """Check database connectivity"""
        if not DATABASE_AVAILABLE:
            return True  # Skip if database modules not available
        
        try:
            if DATABASE_TYPE.lower() == "mysql":
                db = DatabaseManager(db_type="mysql", **MYSQL_CONFIG)
            else:
                db = DatabaseManager(db_type="sqlite", db_path=SQLITE_DB_PATH)
            
            # Try a simple query
            accounts = db.get_all_accounts()
            db.close()
            
            self.log(f"Database connection OK. Found {len(accounts)} accounts.")
            return True
            
        except Exception as e:
            self.add_alert(
                "Database Connection Failed",
                f"Could not connect to database: {e}",
                "CRITICAL"
            )
            return False
    
    def check_log_activity(self):
        """Check if bot is generating recent log entries"""
        log_file = os.path.join(BOT_DIR, "logs", "bot.log")
        
        if not os.path.exists(log_file):
            self.add_alert(
                "Log File Missing",
                f"Bot log file not found: {log_file}",
                "WARNING"
            )
            return False
        
        try:
            # Check if log file has been modified recently
            last_modified = datetime.fromtimestamp(os.path.getmtime(log_file))
            time_diff = datetime.now() - last_modified
            
            threshold_minutes = self.config["thresholds"]["log_inactivity_minutes"]
            
            if time_diff.total_seconds() > threshold_minutes * 60:
                self.add_alert(
                    "Log Inactivity Detected",
                    f"Log file hasn't been updated for {time_diff.total_seconds()/60:.1f} minutes",
                    "WARNING"
                )
                return False
            
            return True
            
        except Exception as e:
            self.add_alert(
                "Log Check Failed",
                f"Could not check log activity: {e}",
                "ERROR"
            )
            return False
    
    def check_memory_usage(self):
        """Check memory usage"""
        try:
            # Get memory usage of bot process
            result = subprocess.run(
                ["systemctl", "show", "HuboluxAutoTrader", "--property=MemoryCurrent"],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0 and "MemoryCurrent=" in result.stdout:
                memory_bytes = int(result.stdout.split("=")[1].strip())
                memory_mb = memory_bytes / (1024 * 1024)
                
                limit_mb = self.config["thresholds"]["memory_limit_mb"]
                
                if memory_mb > limit_mb:
                    self.add_alert(
                        "High Memory Usage",
                        f"Bot is using {memory_mb:.1f}MB (limit: {limit_mb}MB)",
                        "WARNING"
                    )
                    return False
                
                self.log(f"Memory usage OK: {memory_mb:.1f}MB")
                return True
            
            return True  # Skip if can't determine memory usage
            
        except Exception as e:
            self.log(f"Memory check failed: {e}", "ERROR")
            return True  # Don't alert on check failure
    
    def check_disk_space(self):
        """Check available disk space"""
        try:
            result = subprocess.run(
                ["df", BOT_DIR],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:
                    parts = lines[1].split()
                    if len(parts) >= 5:
                        use_percent = int(parts[4].rstrip('%'))
                        
                        limit_percent = self.config["thresholds"]["disk_space_limit_percent"]
                        
                        if use_percent > limit_percent:
                            self.add_alert(
                                "Low Disk Space",
                                f"Disk usage is {use_percent}% (limit: {limit_percent}%)",
                                "WARNING"
                            )
                            return False
                        
                        self.log(f"Disk space OK: {use_percent}% used")
                        return True
            
            return True  # Skip if can't determine disk usage
            
        except Exception as e:
            self.log(f"Disk space check failed: {e}", "ERROR")
            return True  # Don't alert on check failure
    
    def check_trade_activity(self):
        """Check for recent trade activity"""
        if not DATABASE_AVAILABLE:
            return True  # Skip if database modules not available
        
        try:
            if DATABASE_TYPE.lower() == "mysql":
                db = DatabaseManager(db_type="mysql", **MYSQL_CONFIG)
            else:
                db = DatabaseManager(db_type="sqlite", db_path=SQLITE_DB_PATH)
            
            # Get recent trades (this would need to be implemented in DatabaseManager)
            # For now, just check if we can query the database
            accounts = db.get_enabled_accounts()
            db.close()
            
            # Could add more sophisticated trade activity checking here
            return True
            
        except Exception as e:
            self.log(f"Trade activity check failed: {e}", "ERROR")
            return True
    
    def send_email_alert(self, subject, body):
        """Send email alert"""
        if not self.config["alerts"]["email"]["enabled"]:
            return
        
        try:
            msg = MimeMultipart()
            msg['From'] = self.config["alerts"]["email"]["from_email"]
            msg['Subject'] = subject
            msg.attach(MimeText(body, 'plain'))
            
            server = smtplib.SMTP(
                self.config["alerts"]["email"]["smtp_server"],
                self.config["alerts"]["email"]["smtp_port"]
            )
            server.starttls()
            server.login(
                self.config["alerts"]["email"]["from_email"],
                self.config["alerts"]["email"]["from_password"]
            )
            
            for to_email in self.config["alerts"]["email"]["to_emails"]:
                msg['To'] = to_email
                server.send_message(msg)
                del msg['To']
            
            server.quit()
            self.log("Email alerts sent successfully")
            
        except Exception as e:
            self.log(f"Failed to send email alert: {e}", "ERROR")
    
    def send_webhook_alert(self, subject, body):
        """Send webhook alert"""
        if not self.config["alerts"]["webhook"]["enabled"]:
            return
        
        try:
            payload = {
                "text": f"**{subject}**\n{body}",
                "timestamp": datetime.now().isoformat()
            }
            
            response = requests.post(
                self.config["alerts"]["webhook"]["url"],
                json=payload,
                headers=self.config["alerts"]["webhook"]["headers"],
                timeout=10
            )
            
            if response.status_code == 200:
                self.log("Webhook alert sent successfully")
            else:
                self.log(f"Webhook alert failed: {response.status_code}", "ERROR")
                
        except Exception as e:
            self.log(f"Failed to send webhook alert: {e}", "ERROR")
    
    def send_alerts(self):
        """Send all accumulated alerts"""
        if not self.alerts:
            return
        
        # Group alerts by severity
        critical_alerts = [a for a in self.alerts if a["severity"] == "CRITICAL"]
        warning_alerts = [a for a in self.alerts if a["severity"] == "WARNING"]
        error_alerts = [a for a in self.alerts if a["severity"] == "ERROR"]
        
        # Create alert message
        subject = "HuboluxAutoTrader Bot Health Alert"
        if critical_alerts:
            subject += " - CRITICAL ISSUES DETECTED"
        
        body_parts = []
        body_parts.append(f"Health check completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        body_parts.append("")
        
        if critical_alerts:
            body_parts.append("🚨 CRITICAL ISSUES:")
            for alert in critical_alerts:
                body_parts.append(f"  • {alert['title']}: {alert['message']}")
            body_parts.append("")
        
        if error_alerts:
            body_parts.append("❌ ERRORS:")
            for alert in error_alerts:
                body_parts.append(f"  • {alert['title']}: {alert['message']}")
            body_parts.append("")
        
        if warning_alerts:
            body_parts.append("⚠️ WARNINGS:")
            for alert in warning_alerts:
                body_parts.append(f"  • {alert['title']}: {alert['message']}")
        
        body = "\n".join(body_parts)
        
        # Send alerts
        self.send_email_alert(subject, body)
        self.send_webhook_alert(subject, body)
    
    def run_health_checks(self):
        """Run all enabled health checks"""
        self.log("Starting health checks...")
        
        checks = self.config["checks"]
        
        if checks.get("process_running", True):
            self.check_process_running()
        
        if checks.get("database_connection", True):
            self.check_database_connection()
        
        if checks.get("log_activity", True):
            self.check_log_activity()
        
        if checks.get("memory_usage", True):
            self.check_memory_usage()
        
        if checks.get("disk_space", True):
            self.check_disk_space()
        
        if checks.get("trade_activity", True):
            self.check_trade_activity()
        
        # Send alerts if any issues found
        if self.alerts:
            self.send_alerts()
            self.log(f"Health check completed with {len(self.alerts)} alerts")
        else:
            self.log("Health check completed - all systems OK")

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="HuboluxAutoTrader Bot Health Checker")
    parser.add_argument("--config", help="Path to config file", default="health_config.json")
    parser.add_argument("--setup", action="store_true", help="Setup initial configuration")
    
    args = parser.parse_args()
    
    checker = HealthChecker(args.config)
    
    if args.setup:
        print("Setting up health check configuration...")
        print(f"Configuration will be saved to: {checker.config_file}")
        
        # Interactive setup
        checker.config["alerts"]["email"]["enabled"] = input("Enable email alerts? (y/n): ").lower() == 'y'
        if checker.config["alerts"]["email"]["enabled"]:
            checker.config["alerts"]["email"]["from_email"] = input("From email: ")
            checker.config["alerts"]["email"]["from_password"] = input("Email password: ")
            checker.config["alerts"]["email"]["to_emails"] = input("To emails (comma-separated): ").split(',')
        
        checker.config["alerts"]["webhook"]["enabled"] = input("Enable webhook alerts? (y/n): ").lower() == 'y'
        if checker.config["alerts"]["webhook"]["enabled"]:
            checker.config["alerts"]["webhook"]["url"] = input("Webhook URL: ")
        
        checker.save_config()
        print("Configuration saved!")
    else:
        checker.run_health_checks()

if __name__ == "__main__":
    main()
