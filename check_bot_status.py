#!/usr/bin/env python3
"""
Bot Status Checker
Demonstrates how the web UI detects if bot.py is running
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from web_ui.app.services.system_monitor import system_monitor

def main():
    print("=== Trading Bot Status Checker ===\n")
    
    try:
        # Get comprehensive system status
        print("1. Getting comprehensive system status...")
        status = system_monitor.get_system_status()
        
        print(f"   - Bot running: {status['bot']['is_running']}")
        print(f"   - Process count: {status['bot']['process_count']}")
        print(f"   - System CPU: {status['system'].get('cpu_percent', 'N/A')}%")
        print(f"   - System Memory: {status['system'].get('memory_percent', 'N/A')}%")
        
        # Get just bot status
        print("\n2. Getting bot-only status...")
        is_running, bot_status = system_monitor.is_bot_running()
        print(f"   - Bot running: {is_running}")
        
        if bot_status.get('processes'):
            print("\n3. Bot process details:")
            for i, process in enumerate(bot_status['processes'], 1):
                print(f"   Process {i}:")
                print(f"     - PID: {process['pid']}")
                print(f"     - Command: {process['cmdline']}")
                print(f"     - CPU: {process['cpu_percent']}%")
                print(f"     - Memory: {process['memory_mb']} MB")
                print(f"     - Status: {process['status']}")
                print(f"     - Uptime: {process['uptime_seconds']:.1f} seconds")
        else:
            print("\n3. No bot processes found")
        
        # Demonstrate log retrieval
        print("\n4. Getting recent bot logs...")
        logs = system_monitor.get_bot_logs(5)  # Last 5 lines
        if logs and logs[0] != "No log files found or accessible":
            print("   Recent log entries:")
            for log_line in logs:
                print(f"     {log_line.strip()}")
        else:
            print("   No accessible log files found")
        
        # Web UI Integration
        print("\n=== Web UI Integration ===")
        print("The web UI uses this same system monitor service to:")
        print("• Display bot status in real-time on dashboards")
        print("• Allow admins to start/stop bot processes")
        print("• Show system performance metrics")
        print("• Display bot logs in a web interface")
        print("• Auto-refresh status every 30 seconds")
        
        print("\nAPI Endpoints available:")
        print("• GET  /api/bot-status           - Get bot status (all users)")
        print("• GET  /admin/api/system-status  - Full system status (admin)")
        print("• POST /admin/api/bot/start      - Start bot (admin)")
        print("• POST /admin/api/bot/stop       - Stop bot (admin)")
        print("• GET  /admin/api/bot/logs       - Get bot logs (admin)")
        
    except ImportError as e:
        print(f"Error: Missing dependency - {e}")
        print("\nTo fix this, run:")
        print("pip install psutil")
        
    except Exception as e:
        print(f"Error checking bot status: {e}")
        print("\nThis could be due to:")
        print("• Missing psutil package (run: pip install psutil)")
        print("• Permission issues accessing process information")
        print("• Bot not running or not named 'bot.py'")

if __name__ == '__main__':
    main()
