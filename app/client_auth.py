"""
Client Application Authentication Integration for Parkmas
Connects to K0IRO centralized authentication system
"""

import jwt
import requests
import os
from functools import wraps
from flask import session, redirect, request, url_for
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


# =====================================================
# AUTHENTICATION FUNCTIONS
# =====================================================

def validate_token_local(token):
    """Validate a JWT token locally (fast, no network call)"""
    try:
        payload = jwt.decode(
            token, 
            APP_SECRET, 
            algorithms=['HS256'],
            issuer='k0iro_auth'
        )
        
        if payload.get('app_code') != APP_CODE:
            return None
        
        return payload
        
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def validate_token_remote(token):
    """Validate token by calling central auth API"""
    try:
        response = requests.post(
            f"{CENTRAL_AUTH_URL}/sso/validate",
            json={
                'token': token,
                'app_code': APP_CODE
            },
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('valid'):
                return data
        
        return None
        
    except requests.RequestException:
        return validate_token_local(token)


def init_session_from_token(token, validate_remote=False):
    """Initialize Flask session from a valid JWT token"""
    if validate_remote:
        payload = validate_token_remote(token)
    else:
        payload = validate_token_local(token)
    
    if not payload:
        return False
    
    # Set up session (matching Parkmas existing session structure)
    session['user_id'] = payload['user_id']
    session['user'] = payload['callsign']  # Parkmas uses 'user' for callsign
    session['authenticated'] = True
    session['app_code'] = APP_CODE
    session.permanent = True
    
    # Store permissions
    permissions = payload.get('permissions', {})
    session['roles'] = permissions.get('role_codes', [])
    session['user_is_admin'] = permissions.get('is_admin', False)
    
    return True


def redirect_to_login():
    """Redirect user to central authentication"""
    from urllib.parse import urlencode
    
    # Use configured app URL to ensure correct scheme (https)
    callback_url = f"{THIS_APP_URL}/auth/callback"
    
    params = urlencode({
        'app_code': APP_CODE,
        'redirect_uri': callback_url
    })
    
    login_url = f"{CENTRAL_AUTH_URL}/sso/login?{params}"
    
    return redirect(login_url)


def logout_everywhere():
    """Logout from this app and central auth"""
    session.clear()
    
    from urllib.parse import urlencode
    params = urlencode({
        'redirect_uri': url_for('main.index', _external=True)
    })
    
    return redirect(f"{CENTRAL_AUTH_URL}/sso/logout?{params}")


# =====================================================
# DECORATORS FOR ROUTE PROTECTION
# =====================================================

def login_required(f):
    """Decorator: Require user to be logged in"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            session['next_page'] = request.url
            return redirect_to_login()
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator: Require user to be admin"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            session['next_page'] = request.url
            return redirect_to_login()
        
        if not session.get('user_is_admin'):
            return "Access denied - admin only", 403
        
        return f(*args, **kwargs)
    return decorated_function


# =====================================================
# FLASK ROUTES TO ADD TO YOUR APP
# =====================================================

def setup_auth_routes(app):
    """Register authentication routes with the Flask app"""
    
    @app.route('/auth/callback')
    def auth_callback():
        """Handle callback from central authentication"""
        token = request.args.get('token')
        
        if not token:
            return "No authentication token received", 400
        
        if init_session_from_token(token):
            next_page = session.pop('next_page', None)
            return redirect(next_page or url_for('main.index'))
        else:
            return "Invalid authentication token", 401
    
    
    @app.route('/login')
    def login():
        """Initiate SSO login flow"""
        session['next_page'] = request.args.get('next', url_for('main.index'))
        return redirect_to_login()
    
    
    @app.route('/logout')
    def logout():
        """Logout from this app and central auth"""
        return logout_everywhere()
    
    
    @app.route('/auth/check')
    def auth_check():
        """API endpoint to check authentication status"""
        from flask import jsonify
        
        if session.get('authenticated'):
            return jsonify({
                'authenticated': True,
                'callsign': session.get('user'),
                'roles': session.get('roles', []),
                'is_admin': session.get('user_is_admin', False)
            })
        else:
            return jsonify({'authenticated': False})