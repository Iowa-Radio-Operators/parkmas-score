"""
DEPRECATED: This file is replaced by client_auth.py

Keep this file for backwards compatibility,
but all decorators now come from client_auth.py
"""

# Import from new centralized auth module
from .client_auth import admin_required

# Keep old function as alias for backwards compatibility
__all__ = ['admin_required']