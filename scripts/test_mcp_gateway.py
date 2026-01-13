#!/usr/bin/env python3
"""Test script for MCP Gateway.

This script tests the MCP gateway connection, authenticates with Cognito OAuth,
and lists all available tools from the MCP server.
"""

import os
import sys
import json
from pathlib import Path

# Add project root to path to import modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from dotenv import load_dotenv
from services.mcp_client import MCPClientService, CognitoOAuth2Client


def load_config():
    """Load configuration from environment variables."""
    # Load .env file if it exists
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        print("⚠️  Warning: .env file not found. Using environment variables.")
    
    # Get MCP configuration
    mcp_server_url = os.getenv("MCP_SERVER_URL")
    mcp_client_id = os.getenv("MCP_COGNITO_CLIENT_ID")
    mcp_client_secret = os.getenv("MCP_COGNITO_CLIENT_SECRET")
    mcp_token_endpoint = os.getenv("MCP_COGNITO_TOKEN_ENDPOINT")
    
    if not mcp_server_url:
        raise ValueError("MCP_SERVER_URL environment variable is required")
    
    if not mcp_client_id or not mcp_client_secret:
        raise ValueError("MCP_COGNITO_CLIENT_ID and MCP_COGNITO_CLIENT_SECRET are required")
    
    if not mcp_token_endpoint:
        raise ValueError("MCP_COGNITO_TOKEN_ENDPOINT environment variable is required")
    
    return {
        "mcp_server_url": mcp_server_url,
        "mcp_client_id": mcp_client_id,
        "mcp_client_secret": mcp_client_secret,
        "mcp_token_endpoint": mcp_token_endpoint
    }


def test_oauth_authentication(config):
    """Test OAuth authentication with Cognito."""
    print("🔐 Testing OAuth Authentication...")
    print(f"   Token Endpoint: {config['mcp_token_endpoint']}")
    print(f"   Client ID: {config['mcp_client_id']}")
    
    try:
        oauth_client = CognitoOAuth2Client(
            client_id=config['mcp_client_id'],
            client_secret=config['mcp_client_secret'],
            token_endpoint=config['mcp_token_endpoint']
        )
        
        access_token = oauth_client.get_access_token()
        print(f"✅ OAuth authentication successful!")
        print(f"   Access Token: {access_token[:50]}... (truncated)")
        return oauth_client
    except Exception as e:
        print(f"❌ OAuth authentication failed: {str(e)}")
        raise


def test_mcp_connection(config, oauth_client):
    """Test MCP server connection and list tools."""
    print("\n🔌 Testing MCP Server Connection...")
    print(f"   Server URL: {config['mcp_server_url']}")
    
    try:
        mcp_service = MCPClientService(
            mcp_server_url=config['mcp_server_url'],
            oauth_client=oauth_client
        )
        
        print("✅ MCP server connection successful!")
        return mcp_service
    except Exception as e:
        print(f"❌ MCP server connection failed: {str(e)}")
        raise


def list_tools(mcp_service):
    """List all available tools from the MCP server."""
    print("\n📋 Listing Available Tools...")
    
    try:
        tools = mcp_service.list_tools()
        
        if not tools:
            print("⚠️  No tools found on the MCP server.")
            return
        
        print(f"✅ Found {len(tools)} tool(s):\n")
        
        for i, tool in enumerate(tools, 1):
            tool_name = tool.get("name", "Unknown")
            tool_description = tool.get("description", "No description")
            input_schema = tool.get("inputSchema", {})
            
            print(f"{i}. {tool_name}")
            print(f"   Description: {tool_description}")
            
            # Show input schema if available
            if input_schema:
                properties = input_schema.get("properties", {})
                required = input_schema.get("required", [])
                
                if properties:
                    print(f"   Parameters:")
                    for param_name, param_info in properties.items():
                        param_type = param_info.get("type", "unknown")
                        param_desc = param_info.get("description", "")
                        is_required = param_name in required
                        required_marker = " (required)" if is_required else " (optional)"
                        print(f"      - {param_name}: {param_type}{required_marker}")
                        if param_desc:
                            print(f"        {param_desc}")
            
            print()
        
        return tools
    except Exception as e:
        print(f"❌ Failed to list tools: {str(e)}")
        raise




def main():
    """Main function to test MCP gateway."""
    print("=" * 70)
    print("MCP Gateway Test Script")
    print("=" * 70)
    print()
    
    try:
        # Load configuration
        config = load_config()
        print("✅ Configuration loaded successfully")
        print()
        
        # Test OAuth authentication
        oauth_client = test_oauth_authentication(config)
        
        # Test MCP connection
        mcp_service = test_mcp_connection(config, oauth_client)
        
        # List available tools
        tools = list_tools(mcp_service)
        
        print("=" * 70)
        print("✅ All tests completed successfully!")
        print("=" * 70)
        
    except ValueError as e:
        print(f"\n❌ Configuration Error: {str(e)}")
        print("\nPlease ensure the following environment variables are set:")
        print("  - MCP_SERVER_URL")
        print("  - MCP_COGNITO_CLIENT_ID")
        print("  - MCP_COGNITO_CLIENT_SECRET")
        print("  - MCP_COGNITO_TOKEN_ENDPOINT")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
