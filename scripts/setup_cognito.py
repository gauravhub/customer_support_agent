#!/usr/bin/env python3
"""
Setup AWS Cognito User Pool for Customer Support Agent Streamlit UI.

This script creates:
1. A Cognito User Pool with appropriate settings
2. An App Client (public client, no secret)
3. Two test users with temporary passwords

Usage:
    python scripts/setup_cognito.py
    # Or make it executable:
    chmod +x scripts/setup_cognito.py
    ./scripts/setup_cognito.py
"""

import os
import sys
import boto3
import json
from botocore.exceptions import ClientError


# Default password that meets Cognito requirements
# Requirements: 8+ chars, uppercase, lowercase, number, special char
DEFAULT_PASSWORD = "TempPass123!"

# Test users
TEST_USERS = [
    {
        "username": "morgan.taylor@gmail.com",
        "email": "morgan.taylor@gmail.com",
        "temporary_password": DEFAULT_PASSWORD
    },
    {
        "username": "john.smith@gmail.com",
        "email": "john.smith@gmail.com",
        "temporary_password": DEFAULT_PASSWORD
    }
]


def create_user_pool(cognito_client, pool_name: str, region: str) -> dict:
    """
    Create a Cognito User Pool.
    
    Args:
        cognito_client: Boto3 Cognito client
        pool_name: Name for the user pool
        region: AWS region
        
    Returns:
        dict: User pool details
    """
    print(f"Creating Cognito User Pool: {pool_name}...")
    
    try:
        response = cognito_client.create_user_pool(
            PoolName=pool_name,
            Policies={
                'PasswordPolicy': {
                    'MinimumLength': 8,
                    'RequireUppercase': True,
                    'RequireLowercase': True,
                    'RequireNumbers': True,
                    'RequireSymbols': True
                }
            },
            AutoVerifiedAttributes=['email'],
            UsernameAttributes=['email'],
            Schema=[
                {
                    'Name': 'email',
                    'AttributeDataType': 'String',
                    'Required': True,
                    'Mutable': True
                }
            ],
            MfaConfiguration='OFF',
            AccountRecoverySetting={
                'RecoveryMechanisms': [
                    {
                        'Priority': 1,
                        'Name': 'verified_email'
                    }
                ]
            }
        )
        
        pool_id = response['UserPool']['Id']
        print(f"✓ User Pool created: {pool_id}")
        return response['UserPool']
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == 'InvalidParameterException' and 'already exists' in str(e):
            # Pool might already exist, try to find it
            print(f"⚠️  User Pool might already exist. Searching for existing pools...")
            pools = cognito_client.list_user_pools(MaxResults=60)
            for pool in pools.get('UserPools', []):
                if pool['Name'] == pool_name:
                    print(f"✓ Found existing User Pool: {pool['Id']}")
                    return cognito_client.describe_user_pool(UserPoolId=pool['Id'])['UserPool']
            raise
        else:
            raise


def create_app_client(cognito_client, pool_id: str, client_name: str) -> dict:
    """
    Create a Cognito App Client (public client, no secret).
    
    Args:
        cognito_client: Boto3 Cognito client
        pool_id: User Pool ID
        client_name: Name for the app client
        
    Returns:
        dict: App client details
    """
    print(f"Creating App Client: {client_name}...")
    
    try:
        response = cognito_client.create_user_pool_client(
            UserPoolId=pool_id,
            ClientName=client_name,
            GenerateSecret=False,  # Public client (no secret)
            ExplicitAuthFlows=[
                'ALLOW_USER_PASSWORD_AUTH',
                'ALLOW_REFRESH_TOKEN_AUTH'
            ],
            PreventUserExistenceErrors='ENABLED'
        )
        
        client_id = response['UserPoolClient']['ClientId']
        print(f"✓ App Client created: {client_id}")
        return response['UserPoolClient']
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == 'InvalidParameterException' and 'already exists' in str(e):
            # Client might already exist, try to find it
            print(f"⚠️  App Client might already exist. Searching for existing clients...")
            clients = cognito_client.list_user_pool_clients(UserPoolId=pool_id, MaxResults=60)
            for client in clients.get('UserPoolClients', []):
                if client['ClientName'] == client_name:
                    print(f"✓ Found existing App Client: {client['ClientId']}")
                    return cognito_client.describe_user_pool_client(
                        UserPoolId=pool_id,
                        ClientId=client['ClientId']
                    )['UserPoolClient']
            raise
        else:
            raise


def create_user(cognito_client, pool_id: str, username: str, email: str, temporary_password: str) -> dict:
    """
    Create a user in the Cognito User Pool.
    
    Args:
        cognito_client: Boto3 Cognito client
        pool_id: User Pool ID
        username: Username (email)
        email: Email address
        temporary_password: Temporary password
        
    Returns:
        dict: User details
    """
    print(f"Creating user: {username}...")
    
    try:
        # Check if user already exists
        try:
            existing_user = cognito_client.admin_get_user(
                UserPoolId=pool_id,
                Username=username
            )
            print(f"⚠️  User {username} already exists. Skipping creation.")
            return existing_user
        except ClientError as e:
            if e.response.get('Error', {}).get('Code') != 'UserNotFoundException':
                raise
        
        # Create user
        response = cognito_client.admin_create_user(
            UserPoolId=pool_id,
            Username=username,
            UserAttributes=[
                {
                    'Name': 'email',
                    'Value': email
                },
                {
                    'Name': 'email_verified',
                    'Value': 'true'
                }
            ],
            TemporaryPassword=temporary_password,
            MessageAction='SUPPRESS'  # Don't send welcome email
        )
        
        print(f"✓ User created: {username}")
        return response['User']
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == 'UsernameExistsException':
            print(f"⚠️  User {username} already exists. Skipping creation.")
            return cognito_client.admin_get_user(UserPoolId=pool_id, Username=username)
        else:
            raise


def set_permanent_password(cognito_client, pool_id: str, username: str, password: str):
    """
    Set a permanent password for a user (after temporary password).
    
    Args:
        cognito_client: Boto3 Cognito client
        pool_id: User Pool ID
        username: Username
        password: New password
    """
    try:
        cognito_client.admin_set_user_password(
            UserPoolId=pool_id,
            Username=username,
            Password=password,
            Permanent=True
        )
        print(f"✓ Set permanent password for: {username}")
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == 'InvalidPasswordException':
            print(f"⚠️  Password for {username} doesn't meet requirements. User will need to change it on first login.")
        else:
            print(f"⚠️  Could not set permanent password for {username}: {e}")


def main():
    """Main entry point."""
    # Configuration
    pool_name = os.getenv('COGNITO_POOL_NAME', 'customer-support-agent-pool')
    client_name = os.getenv('COGNITO_CLIENT_NAME', 'customer-support-agent-client')
    region = os.getenv('AWS_REGION', 'us-west-2')
    
    print("=" * 80)
    print("AWS Cognito User Pool Setup")
    print("=" * 80)
    print(f"Region: {region}")
    print(f"Pool Name: {pool_name}")
    print(f"Client Name: {client_name}")
    print("=" * 80)
    print()
    
    try:
        # Create Cognito client
        cognito_client = boto3.client('cognito-idp', region_name=region)
        
        # Create User Pool
        user_pool = create_user_pool(cognito_client, pool_name, region)
        pool_id = user_pool['Id']
        
        # Create App Client
        app_client = create_app_client(cognito_client, pool_id, client_name)
        client_id = app_client['ClientId']
        
        # Create users
        print()
        print("Creating test users...")
        for user_info in TEST_USERS:
            create_user(
                cognito_client,
                pool_id,
                user_info['username'],
                user_info['email'],
                user_info['temporary_password']
            )
            # Set permanent password (so users don't need to change it on first login)
            set_permanent_password(
                cognito_client,
                pool_id,
                user_info['username'],
                user_info['temporary_password']
            )
        
        # Output configuration
        print()
        print("=" * 80)
        print("Setup Complete!")
        print("=" * 80)
        print()
        print("Add these values to your .env file:")
        print()
        print(f"COGNITO_USER_POOL_ID={pool_id}")
        print(f"COGNITO_CLIENT_ID={client_id}")
        print(f"COGNITO_CLIENT_SECRET=")
        print(f"AWS_REGION={region}")
        print()
        print("Test Users:")
        print(f"  Username: {TEST_USERS[0]['username']}")
        print(f"  Password: {TEST_USERS[0]['temporary_password']}")
        print()
        print(f"  Username: {TEST_USERS[1]['username']}")
        print(f"  Password: {TEST_USERS[1]['temporary_password']}")
        print()
        print("=" * 80)
        print()
        print("⚠️  IMPORTANT: Change these passwords after first login for security!")
        print()
        
        return 0
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get('Message', str(e))
        print(f"❌ AWS API error ({error_code}): {error_message}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
