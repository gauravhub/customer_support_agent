#!/usr/bin/env python3
"""
Generate AWS Console login URL from environment variables.

This script reads AWS credentials from environment variables and generates
a federated sign-in URL for the AWS Management Console.

Usage:
    python scripts/aws_console_login.py
    # Or make it executable:
    chmod +x scripts/aws_console_login.py
    ./scripts/aws_console_login.py
"""

import os
import sys
import json
import urllib.parse
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import ClientError, NoCredentialsError


def get_aws_credentials():
    """
    Get AWS credentials from environment variables.
    
    Returns:
        dict: Dictionary with access_key, secret_key, session_token (if present), and region
    """
    access_key = os.getenv('AWS_ACCESS_KEY_ID')
    secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    session_token = os.getenv('AWS_SESSION_TOKEN')  # Optional, for temporary credentials
    region = os.getenv('AWS_REGION', os.getenv('AWS_DEFAULT_REGION', 'us-east-1'))
    
    if not access_key or not secret_key:
        raise ValueError(
            "AWS credentials not found in environment variables.\n"
            "Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.\n"
            "Optionally set AWS_SESSION_TOKEN for temporary credentials.\n"
            "Set AWS_REGION or AWS_DEFAULT_REGION for the region (default: us-east-1)."
        )
    
    return {
        'access_key': access_key,
        'secret_key': secret_key,
        'session_token': session_token,
        'region': region
    }


def generate_console_url(credentials: dict, duration: int = 3600) -> str:
    """
    Generate AWS Console login URL using federated sign-in.
    
    Args:
        credentials: Dictionary with AWS credentials
        duration: Session duration in seconds (default: 1 hour, max: 12 hours)
        
    Returns:
        str: AWS Console login URL
    """
    # Create STS client with credentials
    sts_client = boto3.client(
        'sts',
        aws_access_key_id=credentials['access_key'],
        aws_secret_access_key=credentials['secret_key'],
        aws_session_token=credentials.get('session_token'),
        region_name=credentials['region']
    )
    
    try:
        # Get caller identity to verify credentials
        identity = sts_client.get_caller_identity()
        account_id = identity.get('Account')
        user_arn = identity.get('Arn', 'Unknown')
        
        print(f"✓ Authenticated as: {user_arn}", file=sys.stderr)
        print(f"✓ Account ID: {account_id}", file=sys.stderr)
        
        # For temporary credentials (with session token), we need to use GetSessionToken
        # For permanent credentials, we can use GetFederationToken
        if credentials.get('session_token'):
            # Already have temporary credentials, use them directly
            print("ℹ️  Using existing temporary credentials", file=sys.stderr)
            signin_token = get_signin_token_with_session(
                credentials['access_key'],
                credentials['secret_key'],
                credentials['session_token'],
                duration
            )
        else:
            # Permanent credentials - use GetFederationToken
            print("ℹ️  Getting federation token...", file=sys.stderr)
            try:
                federation_token = sts_client.get_federation_token(
                    Name='ConsoleAccess',
                    DurationSeconds=min(duration, 43200),  # Max 12 hours
                    Policy=json.dumps({
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": "*",
                                "Resource": "*"
                            }
                        ]
                    })
                )
                
                signin_token = get_signin_token(
                    federation_token['Credentials']['AccessKeyId'],
                    federation_token['Credentials']['SecretAccessKey'],
                    federation_token['Credentials']['SessionToken'],
                    duration
                )
            except ClientError as e:
                if 'AccessDenied' in str(e) or 'InvalidUserType' in str(e):
                    # Fallback: Try using GetSessionToken instead
                    print("⚠️  GetFederationToken not available, trying GetSessionToken...", file=sys.stderr)
                    session_token = sts_client.get_session_token(DurationSeconds=min(duration, 43200))
                    signin_token = get_signin_token(
                        session_token['Credentials']['AccessKeyId'],
                        session_token['Credentials']['SecretAccessKey'],
                        session_token['Credentials']['SessionToken'],
                        duration
                    )
                else:
                    raise
        
        # Construct console URL
        console_url = (
            "https://signin.aws.amazon.com/federation?"
            f"Action=login&"
            f"Destination=https%3A%2F%2Fconsole.aws.amazon.com%2F&"
            f"SigninToken={signin_token}"
        )
        
        return console_url
        
    except NoCredentialsError:
        raise ValueError("AWS credentials not found or invalid.")
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get('Message', str(e))
        raise ValueError(f"AWS API error ({error_code}): {error_message}")


def get_signin_token(access_key: str, secret_key: str, session_token: str, duration: int) -> str:
    """
    Get sign-in token from AWS federation endpoint.
    
    Args:
        access_key: AWS access key ID
        secret_key: AWS secret access key
        session_token: Session token
        duration: Session duration in seconds
        
    Returns:
        str: Sign-in token
    """
    import requests
    
    # Create session document
    session_doc = {
        "sessionId": access_key,
        "sessionKey": secret_key,
        "sessionToken": session_token
    }
    
    # Get sign-in token
    federation_url = "https://signin.aws.amazon.com/federation"
    params = {
        "Action": "getSigninToken",
        "SessionDuration": str(duration),
        "Session": json.dumps(session_doc)
    }
    
    response = requests.get(federation_url, params=params, timeout=10)
    response.raise_for_status()
    
    result = response.json()
    return result['SigninToken']


def get_signin_token_with_session(access_key: str, secret_key: str, session_token: str, duration: int) -> str:
    """
    Get sign-in token when already using temporary credentials.
    
    Args:
        access_key: AWS access key ID
        secret_key: AWS secret access key
        session_token: Session token
        duration: Session duration in seconds
        
    Returns:
        str: Sign-in token
    """
    return get_signin_token(access_key, secret_key, session_token, duration)


def main():
    """Main entry point."""
    try:
        # Get credentials from environment
        credentials = get_aws_credentials()
        
        # Generate console URL
        console_url = generate_console_url(credentials)
        
        # Output the URL
        print("\n" + "="*80)
        print("AWS Console Login URL:")
        print("="*80)
        print(console_url)
        print("="*80)
        print("\n💡 Tip: Copy the URL above and paste it into your browser to access the AWS Console.")
        print("   The session will be valid for 1 hour (or until your credentials expire).\n")
        
        # Try to open in browser (optional)
        try:
            import webbrowser
            if '--open' in sys.argv or '-o' in sys.argv:
                print("🌐 Opening browser...")
                webbrowser.open(console_url)
        except ImportError:
            pass
        
        return 0
        
    except ValueError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
