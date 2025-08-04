#!/usr/bin/env python3
"""
Test login functionality
"""

from flask import Flask, request, session
from app import create_app
from app.services.user_service import user_service
from werkzeug.security import check_password_hash

def test_login():
    """Test the login functionality"""
    print("Testing login functionality...")
    
    # Create Flask app
    app = create_app('development')
    
    with app.test_client() as client:
        # Test GET request to login page
        print("\n1. Testing GET /auth/login")
        response = client.get('/auth/login')
        print(f"Status: {response.status_code}")
        print(f"Content-Type: {response.content_type}")
        
        # Test POST request with valid credentials
        print("\n2. Testing POST /auth/login with admin credentials")
        response = client.post('/auth/login', data={
            'username': 'admin',
            'password': 'admin123'
        }, follow_redirects=False)
        print(f"Status: {response.status_code}")
        print(f"Location: {response.location if response.status_code in [301, 302] else 'None'}")
        
        # Check if session was created
        with client.session_transaction() as sess:
            print(f"Session user_id: {sess.get('user_id')}")
            print(f"Session username: {sess.get('username')}")
            print(f"Session role: {sess.get('role')}")
            print(f"Session authenticated: {sess.get('is_authenticated')}")
        
        # Test POST request with invalid credentials
        print("\n3. Testing POST /auth/login with invalid credentials")
        response = client.post('/auth/login', data={
            'username': 'admin',
            'password': 'wrongpassword'
        }, follow_redirects=False)
        print(f"Status: {response.status_code}")
        
        # Test access to dashboard after login
        print("\n4. Testing access to dashboard")
        response = client.get('/dashboard', follow_redirects=False)
        print(f"Status: {response.status_code}")

if __name__ == '__main__':
    test_login()
