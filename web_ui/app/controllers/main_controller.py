#!/usr/bin/env python3
"""
Main Controller for HuboluxTradingBot Web UI
Handles dashboard and main application routes
"""

from flask import Blueprint, render_template, jsonify, session, redirect, url_for
from app.utils.decorators import login_required
from app.services.system_monitor import system_monitor
from app.services.account_service import account_service
from app.services.user_service import user_service
from datetime import datetime
import logging

main_bp = Blueprint('main', __name__)
logger = logging.getLogger(__name__)

@main_bp.route('/')
def index():
    """Redirect to dashboard"""
    return redirect(url_for('main.dashboard'))

@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard page"""
    try:
        user_id = session.get('user_id')
        
        # Get system info
        system_info = system_monitor.get_system_info()
        
        # Extract bot_status from system_info for easier template access
        bot_status = system_info.get('bot_status', {})
        
        # Get user's accounts
        accounts = account_service.get_accounts_by_user_id(user_id)
        
        # Extract bot_status from system_info for easier template access
        bot_status = system_info.get('bot_status', {})
        
        # Calculate stats for dashboard
        total_balance = 0
        if accounts:
            for account in accounts:
                try:
                    # Handle different possible attribute names
                    balance = getattr(account, 'balance', 0) or getattr(account, 'current_balance', 0) or 0
                    total_balance += float(balance) if balance else 0
                except (AttributeError, TypeError, ValueError):
                    continue
        
        stats = {
            'total_accounts': len(accounts) if accounts else 0,
            'total_balance': total_balance,
            'win_rate': 75.3,  # Demo value - replace with actual calculation
            'active_trades': bot_status.get('process_count', 0)
        }
        
        # Get recent activity (if implemented)
        recent_activity = []
        
        return render_template('dashboard.html', 
                             title='Dashboard',
                             system_info=system_info,
                             bot_status=bot_status,
                             stats=stats,
                             accounts=accounts[:5] if accounts else [],  # Show only first 5
                             recent_activity=recent_activity)
        
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return render_template('dashboard.html', 
                             title='Dashboard',
                             system_info={},
                             bot_status={},
                             accounts=[],
                             recent_activity=[])

@main_bp.route('/api/stats')
@login_required
def api_stats():
    """API endpoint for dashboard stats"""
    try:
        user_id = session.get('user_id')
        
        # Get system info
        system_info = system_monitor.get_system_info()
        
        # Get user's accounts
        accounts = account_service.get_accounts_by_user_id(user_id)
        
        # Calculate stats
        total_accounts = len(accounts)
        active_accounts = len([acc for acc in accounts if acc.get('enabled')])
        demo_accounts = len([acc for acc in accounts if acc.get('is_demo')])
        real_accounts = total_accounts - demo_accounts
        
        stats = {
            'system_status': system_info.get('bot_status', {}).get('is_running', False),
            'total_accounts': total_accounts,
            'active_accounts': active_accounts,
            'demo_accounts': demo_accounts,
            'real_accounts': real_accounts,
            'bot_processes': system_info.get('bot_status', {}).get('process_count', 0)
        }
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"API stats error: {e}")
        return jsonify({
            'system_status': False,
            'total_accounts': 0,
            'active_accounts': 0,
            'demo_accounts': 0,
            'real_accounts': 0,
            'bot_processes': 0
        }), 500

@main_bp.route('/health')
def health_check():
    """Health check endpoint"""
    try:
        # Basic health check
        return jsonify({
            'status': 'healthy',
            'service': 'HuboluxTradingBot Web UI',
            'timestamp': str(datetime.now())
        })
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500
