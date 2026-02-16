"""
Authentication Module
Handles user authentication and username sanitization for the question generator.
"""

import streamlit as st
import re
from typing import List, Optional


def get_all_users() -> List[str]:
    """
    Get all registered usernames from secrets.
    
    Returns:
        List of usernames
    """
    try:
        if hasattr(st.secrets, "users"):
            return list(st.secrets["users"].keys())
        return []
    except Exception:
        return []


def authenticate_user(username: str, password: str) -> bool:
    """
    Authenticate a user with username and password.
    
    Args:
        username: Username to authenticate
        password: Password to verify
        
    Returns:
        True if authentication successful, False otherwise
    """
    try:
        if not username or not password:
            return False
        
        # Check if users section exists in secrets
        if not hasattr(st.secrets, "users"):
            return False
        
        users = st.secrets["users"]
        
        # Check if username exists and password matches
        if username in users and users[username] == password:
            return True
        
        return False
        
    except Exception:
        return False


def sanitize_username(username: str) -> str:
    """
    Sanitize username for filesystem safety.
    Converts to lowercase and removes special characters.
    
    Args:
        username: Raw username
        
    Returns:
        Sanitized username safe for filesystem
    """
    # Convert to lowercase
    sanitized = username.lower()
    
    # Replace spaces with underscores
    sanitized = sanitized.replace(" ", "_")
    
    # Remove any character that's not alphanumeric, underscore, or hyphen
    sanitized = re.sub(r'[^a-z0-9_-]', '', sanitized)
    
    # Ensure it's not empty
    if not sanitized:
        sanitized = "user"
    
    return sanitized


def get_display_name(username: str) -> str:
    """
    Get a display-friendly version of the username.
    
    Args:
        username: Raw username
        
    Returns:
        Display name (capitalized)
    """
    return username.capitalize()
