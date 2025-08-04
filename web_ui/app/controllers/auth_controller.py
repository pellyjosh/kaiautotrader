#!/usr/bin/env python3
"""
Authentication Controller for HuboluxTradingBot Web UI
Handles user login, logout, signup, and session management
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash, generate_password_hash
from app.services.user_service import user_service
from app.utils.decorators import login_required
import logging
import re

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')
logger = logging.getLogger(__name__)

def validate_password(password):
    """Validate password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"
    
    if not re.search(r"\d", password):
        return False, "Password must contain at least one number"
    
    return True, "Password is valid"

def validate_username(username):
    """Validate username format"""
    if len(username) < 3:
        return False, "Username must be at least 3 characters long"
    
    if len(username) > 20:
        return False, "Username must be no more than 20 characters long"
    
    if not re.match(r"^[a-zA-Z0-9_]+$", username):
        return False, "Username can only contain letters, numbers, and underscores"
    
    return True, "Username is valid"

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    """Handle user registration"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate inputs
        if not all([username, email, password, confirm_password]):
            flash('All fields are required', 'error')
            return render_template('auth/signup.html')
        
        # Validate username
        username_valid, username_msg = validate_username(username)
        if not username_valid:
            flash(username_msg, 'error')
            return render_template('auth/signup.html')
        
        # Validate email format
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            flash('Please enter a valid email address', 'error')
            return render_template('auth/signup.html')
        
        # Validate password
        password_valid, password_msg = validate_password(password)
        if not password_valid:
            flash(password_msg, 'error')
            return render_template('auth/signup.html')
        
        # Check if passwords match
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('auth/signup.html')
        
        try:
            # Check if username already exists
            existing_user = user_service.get_user_by_username(username)
            if existing_user:
                flash('Username already exists. Please choose a different one.', 'error')
                return render_template('auth/signup.html')
            
            # Check if email already exists
            existing_email = user_service.get_user_by_email(email)
            if existing_email:
                flash('Email already registered. Please use a different email.', 'error')
                return render_template('auth/signup.html')
            
            # Create new user
            new_user = user_service.create_user(
                username=username,
                email=email,
                password=password,  # user_service.create_user will hash it
                # role='user'  # Default role
            )
            
            if new_user:
                logger.info(f"New user registered: {username}")
                flash('Account created successfully! You can now log in.', 'success')
                return redirect(url_for('auth.login'))
            else:
                flash('Failed to create account. Please try again.', 'error')
                
        except Exception as e:
            logger.error(f"Signup error: {e}")
            flash('An error occurred during registration. Please try again.', 'error')
    
    return render_template('auth/signup.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    logger.debug("Login route accessed")
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password')
        logger.debug(f"Login POST data - username: {username}")

        if not username or not password:
            logger.warning("Username or password missing in login form")
            flash('Please enter both username and password', 'error')
            return render_template('auth/login.html')
        
        try:
            # Get user by username
            user = user_service.get_user_by_username(username)
            logger.debug(f"User fetched from DB: {user}")

            if user and 'password_hash' in user and check_password_hash(user['password_hash'], password):
                # Login successful
                session['user_id'] = user.get('id')
                session['username'] = user.get('username')
                session['role'] = user.get('role', 'user')
                session['is_authenticated'] = True
                
                logger.info(f"User {username} logged in successfully")
                
                # Redirect to next page or dashboard
                next_page = request.args.get('next')
                logger.debug(f"Next page after login: {next_page}")
                if next_page:
                    return redirect(next_page)
                return redirect(url_for('main.dashboard'))
            else:
                flash('Invalid username or password', 'error')
                logger.warning(f"Failed login attempt for username: {username}")
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            flash('An error occurred during login', 'error')
    
    return render_template('auth/login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    """Handle user logout"""
    username = session.get('username', 'Unknown')
    session.clear()
    logger.info(f"User {username} logged out")
    flash('You have been logged out successfully', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/profile')
@login_required
def profile():
    """User profile page"""
    try:
        user_id = session.get('user_id')
        user = user_service.get_user_by_id(user_id)
        
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('main.dashboard'))
        
        return render_template('auth/profile.html', user=user)
        
    except Exception as e:
        logger.error(f"Profile error: {e}")
        flash('An error occurred loading your profile', 'error')
        return redirect(url_for('main.dashboard'))
