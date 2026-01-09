"""
AWS Cognito Authentication Module

Handles user authentication using AWS Cognito User Pool.
Supports both public clients (no secret) and confidential clients (with secret).
"""

import os
import boto3
import hmac
import hashlib
import base64
from typing import Optional, Dict
import streamlit as st
from botocore.exceptions import ClientError

# Initialize Cognito client
cognito_client = boto3.client('cognito-idp', region_name=os.getenv('AWS_REGION', 'us-west-2'))


def compute_secret_hash(username: str, client_id: str, client_secret: str) -> str:
    """
    Compute SECRET_HASH for Cognito authentication when using a confidential client.
    
    Args:
        username: Username or email
        client_id: Cognito App Client ID
        client_secret: Cognito App Client Secret
        
    Returns:
        Base64-encoded secret hash
    """
    message = username + client_id
    dig = hmac.new(
        client_secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).digest()
    return base64.b64encode(dig).decode()


def authenticate_user(username: str, password: str) -> Optional[Dict]:
    """
    Authenticate user with AWS Cognito.
    
    Args:
        username: Username or email
        password: User password
        
    Returns:
        Authentication result with tokens, or None if authentication fails
    """
    user_pool_id = os.getenv('COGNITO_USER_POOL_ID')
    client_id = os.getenv('COGNITO_CLIENT_ID')
    client_secret = os.getenv('COGNITO_CLIENT_SECRET')  # Optional - only for confidential clients
    
    if not user_pool_id or not client_id:
        return None
    
    # Build auth parameters
    auth_params = {
        'USERNAME': username,
        'PASSWORD': password
    }
    
    # Add SECRET_HASH if client secret is provided (confidential client)
    if client_secret:
        auth_params['SECRET_HASH'] = compute_secret_hash(username, client_id, client_secret)
    
    try:
        response = cognito_client.initiate_auth(
            ClientId=client_id,
            AuthFlow='USER_PASSWORD_AUTH',
            AuthParameters=auth_params
        )
        
        if response.get('ChallengeName'):
            # Handle MFA or other challenges
            st.warning(f"Additional authentication required: {response['ChallengeName']}")
            return None
        
        # Store tokens in session state
        tokens = response['AuthenticationResult']
        st.session_state.access_token = tokens['AccessToken']
        st.session_state.id_token = tokens['IdToken']
        st.session_state.refresh_token = tokens.get('RefreshToken')
        
        return tokens
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'NotAuthorizedException':
            st.error("Invalid username or password")
        elif error_code == 'UserNotConfirmedException':
            st.error("User account not confirmed. Please check your email.")
        else:
            st.error(f"Authentication error: {e}")
        return None
    except Exception as e:
        st.error(f"Unexpected error during authentication: {e}")
        return None


def get_user_info() -> Optional[Dict]:
    """
    Get current user information from Cognito.
    
    Returns:
        User information dictionary, or None if not authenticated
    """
    if 'access_token' not in st.session_state:
        return None
    
    try:
        response = cognito_client.get_user(
            AccessToken=st.session_state.access_token
        )
        return {
            'username': response['Username'],
            'attributes': {attr['Name']: attr['Value'] for attr in response['UserAttributes']}
        }
    except ClientError as e:
        st.error(f"Error retrieving user info: {e}")
        return None


def sign_out():
    """Sign out the current user."""
    if 'access_token' in st.session_state:
        try:
            cognito_client.global_sign_out(
                AccessToken=st.session_state.access_token
            )
        except ClientError:
            pass  # Ignore errors during sign out
    
    # Clear session state
    for key in ['access_token', 'id_token', 'refresh_token', 'authenticated', 'username']:
        if key in st.session_state:
            del st.session_state[key]
