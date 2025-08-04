#!/usr/bin/env python3
"""
Account Controller for HuboluxTradingBot Web UI
Handles account management routes
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from app.utils.decorators import login_required
from app.services.account_service import account_service
import logging

account_bp = Blueprint('accounts', __name__, url_prefix='/accounts')
logger = logging.getLogger(__name__)

@account_bp.route('/')
@login_required
def list_accounts():
    """List all accounts for the current user"""
    try:
        user_id = session.get('user_id')
        accounts = account_service.get_accounts_by_user_id(user_id)
        stats = account_service.get_account_statistics()
        
        return render_template('accounts/list.html', 
                             title='Account Management',
                             accounts=accounts,
                             stats=stats)
        
    except Exception as e:
        logger.error(f"Failed to list accounts: {e}")
        flash('Error loading accounts', 'error')
        return render_template('accounts/list.html', 
                             title='Account Management',
                             accounts=[],
                             stats={})

@account_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_account():
    """Create a new account"""
    if request.method == 'POST':
        try:
            worker_name = request.form.get('worker_name')
            ssid = request.form.get('ssid')
            is_demo = request.form.get('is_demo') == 'on'
            enabled = request.form.get('enabled') == 'on'
            base_amount = float(request.form.get('base_amount', 1.0))
            martingale_multiplier = float(request.form.get('martingale_multiplier', 2.0))
            martingale_enabled = request.form.get('martingale_enabled') == 'on'
            
            if not worker_name or not ssid:
                flash('Worker name and SSID are required', 'error')
                return render_template('accounts/create.html', title='Create Account')
            
            success = account_service.create_account(
                worker_name=worker_name,
                ssid=ssid,
                is_demo=is_demo,
                enabled=enabled,
                base_amount=base_amount,
                martingale_multiplier=martingale_multiplier,
                martingale_enabled=martingale_enabled
            )
            
            if success:
                flash(f'Account {worker_name} created successfully', 'success')
                return redirect(url_for('accounts.list_accounts'))
            else:
                flash('Failed to create account', 'error')
                
        except ValueError as e:
            flash('Invalid numeric values provided', 'error')
        except Exception as e:
            logger.error(f"Failed to create account: {e}")
            flash('Error creating account', 'error')
    
    return render_template('accounts/create.html', title='Create Account')

@account_bp.route('/<worker_name>')
@login_required
def view_account(worker_name):
    """View account details"""
    try:
        account = account_service.get_account_by_name(worker_name)
        
        if not account:
            flash('Account not found', 'error')
            return redirect(url_for('accounts.list_accounts'))
        
        return render_template('accounts/view.html', 
                             title=f'Account: {worker_name}',
                             account=account)
        
    except Exception as e:
        logger.error(f"Failed to view account {worker_name}: {e}")
        flash('Error loading account', 'error')
        return redirect(url_for('accounts.list_accounts'))

@account_bp.route('/<worker_name>/edit', methods=['GET', 'POST'])
@login_required
def edit_account(worker_name):
    """Edit account settings"""
    try:
        account = account_service.get_account_by_name(worker_name)
        
        if not account:
            flash('Account not found', 'error')
            return redirect(url_for('accounts.list_accounts'))
        
        if request.method == 'POST':
            updates = {}
            
            # Get form data
            if 'ssid' in request.form:
                updates['ssid'] = request.form.get('ssid')
            
            if 'enabled' in request.form:
                updates['enabled'] = request.form.get('enabled') == 'on'
            
            if 'base_amount' in request.form:
                updates['base_amount'] = float(request.form.get('base_amount', 1.0))
            
            if 'martingale_multiplier' in request.form:
                updates['martingale_multiplier'] = float(request.form.get('martingale_multiplier', 2.0))
            
            if 'martingale_enabled' in request.form:
                updates['martingale_enabled'] = request.form.get('martingale_enabled') == 'on'
            
            success = account_service.update_account(worker_name, **updates)
            
            if success:
                flash('Account updated successfully', 'success')
                return redirect(url_for('accounts.view_account', worker_name=worker_name))
            else:
                flash('Failed to update account', 'error')
        
        return render_template('accounts/edit.html', 
                             title=f'Edit Account: {worker_name}',
                             account=account)
        
    except ValueError as e:
        flash('Invalid numeric values provided', 'error')
        return redirect(url_for('accounts.edit_account', worker_name=worker_name))
    except Exception as e:
        logger.error(f"Failed to edit account {worker_name}: {e}")
        flash('Error editing account', 'error')
        return redirect(url_for('accounts.list_accounts'))

@account_bp.route('/<worker_name>/toggle', methods=['POST'])
@login_required
def toggle_account(worker_name):
    """Toggle account enabled status via AJAX"""
    try:
        result = account_service.toggle_account(worker_name)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Failed to toggle account {worker_name}: {e}")
        return jsonify({
            'success': False, 
            'message': f'Error toggling account: {str(e)}'
        }), 500

@account_bp.route('/<worker_name>/delete', methods=['POST'])
@login_required
def delete_account(worker_name):
    """Delete an account"""
    try:
        success = account_service.delete_account(worker_name)
        
        if success:
            flash(f'Account {worker_name} deleted successfully', 'success')
        else:
            flash('Failed to delete account', 'error')
            
        return redirect(url_for('accounts.list_accounts'))
        
    except Exception as e:
        logger.error(f"Failed to delete account {worker_name}: {e}")
        flash('Error deleting account', 'error')
        return redirect(url_for('accounts.list_accounts'))

# API Routes for AJAX operations
@account_bp.route('/toggle', methods=['POST'])
@login_required  
def toggle_account_api():
    """Toggle account enabled status via AJAX"""
    try:
        data = request.get_json()
        worker_name = data.get('worker_name')
        result = account_service.toggle_account(worker_name)
        return jsonify({'success': True, 'message': f'Account {worker_name} toggled successfully'})
    except Exception as e:
        logger.error(f"Failed to toggle account: {e}")
        return jsonify({'success': False, 'message': str(e)})

@account_bp.route('/delete/<account_id>', methods=['DELETE'])
@login_required
def delete_account_api(account_id):
    """Delete an account via API"""
    try:
        success = account_service.delete_account(account_id)
        if success:
            return jsonify({'success': True, 'message': f'Account {account_id} deleted successfully'})
        else:
            return jsonify({'success': False, 'message': 'Failed to delete account'})
    except Exception as e:
        logger.error(f"Failed to delete account {account_id}: {e}")
