#!/usr/bin/env python3
"""
System Monitor Service for HuboluxTradingBot Web UI
Monitors bot status, system resources, and provides control functions
"""

import psutil
import subprocess
import os
import time
import logging
from typing import Dict, List, Any

class SystemMonitor:
    """Service class for system monitoring and bot control"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        self.venv_path = os.path.join(self.project_root, "venv")
        self.python_executable = os.path.join(self.venv_path, "bin", "python")
        
    def get_bot_processes(self) -> List[Dict[str, Any]]:
        """Get running bot.py processes"""
        processes = []
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'status', 'create_time']):
                try:
                    if proc.info['cmdline'] and len(proc.info['cmdline']) > 1:
                        # Look for bot.py in command line
                        cmdline_str = ' '.join(proc.info['cmdline'])
                        if 'bot.py' in cmdline_str and self.project_root in cmdline_str:
                            processes.append({
                                'pid': proc.info['pid'],
                                'name': proc.info['name'],
                                'cmdline': proc.info['cmdline'],
                                'status': proc.info['status'],
                                'create_time': proc.info['create_time'],
                                'uptime': time.time() - proc.info['create_time']
                            })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            self.logger.error(f"Error getting bot processes: {e}")
        
        return processes
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get comprehensive system information"""
        try:
            # System resources
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Bot status
            bot_processes = self.get_bot_processes()
            
            # Check if bot is running via systemctl (production)
            is_service_running = False
            try:
                result = subprocess.run(['systemctl', 'is-active', 'HuboluxAutoTrader'], 
                                      capture_output=True, text=True, timeout=5)
                is_service_running = result.returncode == 0 and result.stdout.strip() == 'active'
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
            
            system_info = {
                'cpu_percent': cpu_percent,
                'memory': {
                    'total': memory.total,
                    'available': memory.available,
                    'percent': memory.percent,
                    'used': memory.used
                },
                'disk': {
                    'total': disk.total,
                    'free': disk.free,
                    'percent': (disk.used / disk.total) * 100
                },
                'bot_status': {
                    'is_running': len(bot_processes) > 0 or is_service_running,
                    'process_count': len(bot_processes),
                    'processes': bot_processes,
                    'service_running': is_service_running
                },
                'environment': 'production' if is_service_running else 'development',
                'project_root': self.project_root
            }
            
            return system_info
            
        except Exception as e:
            self.logger.error(f"Error getting system info: {e}")
            return {
                'cpu_percent': 0,
                'memory': {'total': 0, 'available': 0, 'percent': 0, 'used': 0},
                'disk': {'total': 0, 'free': 0, 'percent': 0},
                'bot_status': {'is_running': False, 'process_count': 0, 'processes': []},
                'environment': 'unknown',
                'project_root': self.project_root
            }
    
    def start_bot(self) -> Dict[str, Any]:
        """Start the trading bot"""
        try:
            # Check if already running
            bot_processes = self.get_bot_processes()
            if bot_processes:
                return {'success': False, 'message': 'Bot is already running'}
            
            # Try to start via systemctl first (production)
            try:
                result = subprocess.run(['systemctl', 'start', 'HuboluxAutoTrader'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    return {'success': True, 'message': 'Bot started via systemctl'}
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
            
            # Fallback to direct execution (development)
            if os.path.exists(self.python_executable):
                bot_script = os.path.join(self.project_root, 'bot.py')
                if os.path.exists(bot_script):
                    subprocess.Popen([self.python_executable, bot_script], 
                                   cwd=self.project_root,
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
                    return {'success': True, 'message': 'Bot started in development mode'}
            
            return {'success': False, 'message': 'Could not start bot - check configuration'}
            
        except Exception as e:
            self.logger.error(f"Error starting bot: {e}")
            return {'success': False, 'message': f'Error starting bot: {str(e)}'}
    
    def stop_bot(self) -> Dict[str, Any]:
        """Stop the trading bot"""
        try:
            stopped_processes = 0
            
            # Try to stop via systemctl first (production)
            try:
                result = subprocess.run(['systemctl', 'stop', 'HuboluxAutoTrader'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    return {'success': True, 'message': 'Bot stopped via systemctl'}
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
            
            # Stop direct processes (development)
            bot_processes = self.get_bot_processes()
            for proc_info in bot_processes:
                try:
                    proc = psutil.Process(proc_info['pid'])
                    proc.terminate()
                    stopped_processes += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if stopped_processes > 0:
                return {'success': True, 'message': f'Stopped {stopped_processes} bot process(es)'}
            else:
                return {'success': False, 'message': 'No bot processes found to stop'}
                
        except Exception as e:
            self.logger.error(f"Error stopping bot: {e}")
            return {'success': False, 'message': f'Error stopping bot: {str(e)}'}
    
    def restart_bot(self) -> Dict[str, Any]:
        """Restart the trading bot"""
        try:
            # Stop first
            stop_result = self.stop_bot()
            
            # Wait a moment
            time.sleep(2)
            
            # Start again
            start_result = self.start_bot()
            
            if stop_result['success'] and start_result['success']:
                return {'success': True, 'message': 'Bot restarted successfully'}
            else:
                return {'success': False, 'message': f"Restart failed - Stop: {stop_result['message']}, Start: {start_result['message']}"}
                
        except Exception as e:
            self.logger.error(f"Error restarting bot: {e}")
            return {'success': False, 'message': f'Error restarting bot: {str(e)}'}

# Global system monitor instance
system_monitor = SystemMonitor()
