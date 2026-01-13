"""MCP Client Service for connecting to remote MCP servers with OAuth authentication.

This module provides functionality to connect to MCP servers, authenticate using
Cognito OAuth2 client credentials flow, and convert MCP tools to LangChain tools.
"""

import time
import requests
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from langchain_core.tools import StructuredTool


class CognitoOAuth2Client:
    """OAuth2 client for Amazon Cognito using client credentials flow."""
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token_endpoint: str
    ):
        """Initialize Cognito OAuth2 client.
        
        Args:
            client_id: Cognito App Client ID
            client_secret: Cognito App Client Secret
            token_endpoint: Cognito OAuth2 token endpoint URL (required)
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_endpoint = token_endpoint
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        
    def get_access_token(self) -> str:
        """Get a valid access token, refreshing if necessary.
        
        Returns:
            Valid access token string
            
        Raises:
            RuntimeError: If token acquisition fails
        """
        # Check if we have a valid token
        if self._access_token and self._token_expires_at:
            if datetime.now() < self._token_expires_at - timedelta(seconds=60):  # Refresh 1 min before expiry
                return self._access_token
        
        # Acquire new token using client credentials flow
        # Format matches: curl -X POST ... -d "grant_type=client_credentials&client_id=...&client_secret=..."
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        data = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }
        
        try:
            response = requests.post(self.token_endpoint, headers=headers, data=data)
            response.raise_for_status()
            token_data = response.json()
            
            self._access_token = token_data.get('access_token')
            expires_in = token_data.get('expires_in', 3600)  # Default to 1 hour
            self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)
            
            if not self._access_token:
                raise RuntimeError("No access token in response")
                
            return self._access_token
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to acquire access token: {str(e)}")


class MCPClientService:
    """Service for connecting to MCP servers and retrieving tools."""
    
    def __init__(
        self,
        mcp_server_url: str,
        oauth_client: Optional[CognitoOAuth2Client] = None,
        authorization_token: Optional[str] = None
    ):
        """Initialize MCP client service.
        
        Args:
            mcp_server_url: URL of the MCP server endpoint
            oauth_client: Optional OAuth2 client for authentication
            authorization_token: Optional pre-acquired authorization token
        """
        self.mcp_server_url = mcp_server_url
        self.oauth_client = oauth_client
        self._authorization_token = authorization_token
        self._tools_cache: Optional[List[Dict[str, Any]]] = None
        
    def get_authorization_token(self) -> Optional[str]:
        """Get authorization token, refreshing OAuth token if needed.
        
        Returns:
            Authorization token string or None
        """
        if self._authorization_token:
            return self._authorization_token
        
        if self.oauth_client:
            return self.oauth_client.get_access_token()
        
        return None
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools from the MCP server.
        
        Returns:
            List of tool definitions from the MCP server
            
        Raises:
            RuntimeError: If tool listing fails
        """
        if self._tools_cache:
            return self._tools_cache
        
        auth_token = self.get_authorization_token()
        headers = {
            'Content-Type': 'application/json',
        }
        if auth_token:
            headers['Authorization'] = f'Bearer {auth_token}'
        
        # MCP servers use JSON-RPC 2.0 over HTTP
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {}
        }
        
        try:
            response = requests.post(
                self.mcp_server_url,
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            if "result" in result:
                tools = result["result"]
                # Handle both direct tools list and nested structure
                if isinstance(tools, list):
                    self._tools_cache = tools
                elif isinstance(tools, dict) and "tools" in tools:
                    self._tools_cache = tools["tools"]
                else:
                    self._tools_cache = []
                return self._tools_cache
            elif "error" in result:
                raise RuntimeError(f"MCP server error: {result['error']}")
            else:
                raise RuntimeError(f"Unexpected response format: {result}")
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to list MCP tools: {str(e)}")
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on the MCP server.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Arguments to pass to the tool
            
        Returns:
            Tool execution result
            
        Raises:
            RuntimeError: If tool execution fails
        """
        auth_token = self.get_authorization_token()
        headers = {
            'Content-Type': 'application/json',
        }
        if auth_token:
            headers['Authorization'] = f'Bearer {auth_token}'
        
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),  # Use timestamp as ID
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        try:
            response = requests.post(
                self.mcp_server_url,
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            if "error" in result:
                error_info = result["error"]
                error_msg = error_info.get("message", str(error_info))
                raise RuntimeError(f"MCP tool error: {error_msg}")
            
            if "result" in result:
                result_data = result["result"]
                # Handle different result formats
                if isinstance(result_data, dict):
                    # Check for content array (MCP format)
                    if "content" in result_data:
                        content = result_data["content"]
                        if isinstance(content, list) and len(content) > 0:
                            first_item = content[0]
                            if isinstance(first_item, dict):
                                return first_item.get("text", first_item)
                        return content
                    # Return the result dict directly
                    return result_data
                else:
                    return result_data
            else:
                raise RuntimeError(f"Unexpected response format: {result}")
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to call MCP tool {tool_name}: {str(e)}")
    
    def get_langchain_tools(self) -> List[StructuredTool]:
        """Convert MCP tools to LangChain tools.
        
        Returns:
            List of LangChain StructuredTool instances
        """
        tools = self.list_tools()
        langchain_tools = []
        
        for tool_def in tools:
            tool_name = tool_def.get("name")
            tool_description = tool_def.get("description", "")
            
            # Create a LangChain tool that calls the MCP tool
            def make_tool_call(tool_name: str, mcp_service: 'MCPClientService'):
                def tool_func(**kwargs):
                    return mcp_service.call_tool(tool_name, kwargs)
                return tool_func
            
            # Create the tool function
            tool_func = make_tool_call(tool_name, self)
            
            # Create LangChain StructuredTool
            langchain_tool = StructuredTool.from_function(
                func=tool_func,
                name=tool_name,
                description=tool_description,
                args_schema=None  # We'll use the inputSchema from MCP
            )
            
            langchain_tools.append(langchain_tool)
        
        return langchain_tools
