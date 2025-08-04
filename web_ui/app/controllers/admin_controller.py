#!/usr/bin/env python3
"""
Admin Controller for HuboluxTradingBot Web UI
Handles administrative functions
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from app.utils.decorators import admin_required, login_required
from app.services.user_service import user_service
from app.services.system_monitor import system_monitor
from app.services.database_service import db_service
import logging

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')
logger = logging.getLogger(__name__)

@admin_bp.route('/')
@admin_required
def index():
    """Admin dashboard"""
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    """Admin dashboard"""
    try:
        system_info = system_monitor.get_system_info()
        users = user_service.get_all_users()
        
        return render_template('admin/dashboard.html',
                             title='Admin Dashboard',
                             system_info=system_info,
                             user_count=len(users))
        
    except Exception as e:
        logger.error(f"Admin dashboard error: {e}")
        return render_template('admin/dashboard.html',
                             title='Admin Dashboard',
                             system_info={},
                             user_count=0)

@admin_bp.route('/system-info')
@admin_required
def system_info():
    """System information page"""
    try:
        system_info = system_monitor.get_system_info()
        
        return render_template('admin/system_info.html',
                             title='System Information',
                             system_info=system_info)
        
    except Exception as e:
        logger.error(f"System info error: {e}")
        return render_template('admin/system_info.html',
                             title='System Information',
                             system_info={})

@admin_bp.route('/users')
@admin_required
def users():
    """User management page"""
    try:
        users = user_service.get_all_users()
        
        return render_template('admin/users.html',
                             title='User Management',
                             users=users)
        
    except Exception as e:
        logger.error(f"Admin users error: {e}")
        return render_template('admin/users.html', title='User Management', users=[])

@admin_bp.route('/users/create', methods=['GET', 'POST'])
@admin_required
def create_user():
    """Create new user"""
    if request.method == 'POST':
        try:
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            role = request.form.get('role', 'user')
            
            if not username or not email or not password:
                flash('All fields are required', 'error')
                return render_template('admin/create_user.html', title='Create User')
            
            success = user_service.create_user(username, email, password, role)
            
            if success:
                flash(f'User {username} created successfully', 'success')
                return redirect(url_for('admin.users'))
            else:
                flash('Failed to create user', 'error')
                
        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            flash('Error creating user', 'error')
    
    return render_template('admin/create_user.html', title='Create User')

@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@admin_required
def toggle_user(user_id):
    """Toggle user active status"""
    try:
        user = user_service.get_user_by_id(user_id)
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        new_status = not user['is_active']
        success = user_service.update_user(user_id, is_active=new_status)
        
        if success:
            return jsonify({
                'success': True,
                'is_active': new_status,
                'message': f"User {'activated' if new_status else 'deactivated'} successfully"
            })
        else:
            return jsonify({'success': False, 'message': 'Failed to update user status'}), 500
            
    except Exception as e:
        logger.error(f"Failed to toggle user {user_id}: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    """Delete a user"""
    try:
        # Don't allow deleting yourself
        if user_id == session.get('user_id'):
            flash('Cannot delete your own account', 'error')
            return redirect(url_for('admin.users'))
        
        user = user_service.get_user_by_id(user_id)
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('admin.users'))
        
        success = user_service.delete_user(user_id)
        
        if success:
            flash(f'User {user["username"]} deleted successfully', 'success')
        else:
            flash('Failed to delete user', 'error')
            
        return redirect(url_for('admin.users'))
        
    except Exception as e:
        logger.error(f"Failed to delete user {user_id}: {e}")
        flash('Error deleting user', 'error')
        return redirect(url_for('admin.users'))

@admin_bp.route('/bot/start', methods=['POST'])
@admin_required
def start_bot():
    """Start the trading bot"""
    try:
        result = system_monitor.start_bot()
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@admin_bp.route('/bot/stop', methods=['POST'])
@admin_required
def stop_bot():
    """Stop the trading bot"""
    try:
        result = system_monitor.stop_bot()
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Failed to stop bot: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@admin_bp.route('/bot/restart', methods=['POST'])
@admin_required
def restart_bot():
    """Restart the trading bot"""
    try:
        result = system_monitor.restart_bot()
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Failed to restart bot: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@admin_bp.route('/test-db-connection', methods=['POST'])
@admin_required
def test_db_connection():
    """Test database connection"""
    try:
        success, message = db_service.test_connection()
        return jsonify({
            'success': success,
            'message': message
        })
        
    except Exception as e:
        logger.error(f"Database test failed: {e}")
        return jsonify({
            'success': False,
            'message': f'Database test failed: {str(e)}'
        }), 500
