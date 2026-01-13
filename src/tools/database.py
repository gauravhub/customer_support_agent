"""Database query tools for customer support agent.

This module exposes fundamental database query tools that the agent can use
to find customers, orders, transactions, and refunds. The tools are provided
via an MCP server instead of local database access.
"""

from langchain_core.tools import tool, StructuredTool
from typing import Optional, Dict, Any

from agent.configuration import Configuration
from services.mcp_client import MCPClientService, CognitoOAuth2Client


# MCP client service instance and config (will be initialized when needed)
_mcp_service: Optional[MCPClientService] = None
_current_config: Optional[Configuration] = None
_mcp_tools_cache: Dict[str, StructuredTool] = {}

# Mapping from local tool names to MCP server tool names
# This maps the simple tool names used in the codebase to the actual tool names
# returned by the MCP server (which include API prefixes)
_MCP_TOOL_NAME_MAPPING = {
    "find_customer": "order-management-api___find_customer_api_customer_get",
    "find_order": "order-management-api___find_order_api_order_get",
    "find_transaction": "order-management-api___find_transaction_api_transaction_get",
    "get_transaction_for_order": "order-management-api___get_transaction_for_order_api_transaction_order__order_no__get",
    "get_refund_for_order": "order-management-api___get_refund_for_order_api_refund_order__order_no__get",
}


def initialize_customer_validation_tools(config: Configuration) -> None:
    """Initialize database query tools with MCP server configuration.
    
    This function sets up the MCP client service to connect to the remote
    MCP server that provides database tools.
    
    Args:
        config: Configuration object containing MCP server settings
        
    Raises:
        ValueError: If MCP server configuration is missing
        RuntimeError: If MCP client initialization fails
    """
    global _mcp_service, _current_config, _mcp_tools_cache
    
    _current_config = config
    
    # Check if MCP server URL is configured
    if not config.mcp_server_url:
        raise ValueError(
            "MCP server URL not configured. Set MCP_SERVER_URL environment variable."
        )
    
    # Initialize OAuth client if credentials are provided
    oauth_client = None
    if config.mcp_cognito_client_id and config.mcp_cognito_client_secret:
        if not config.mcp_cognito_token_endpoint:
            raise ValueError(
                "MCP Cognito token endpoint is required when using OAuth. "
                "Set MCP_COGNITO_TOKEN_ENDPOINT environment variable."
            )
        try:
            oauth_client = CognitoOAuth2Client(
                client_id=config.mcp_cognito_client_id,
                client_secret=config.mcp_cognito_client_secret,
                token_endpoint=config.mcp_cognito_token_endpoint
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize OAuth client: {str(e)}")
    
    # Initialize MCP client service
    try:
        _mcp_service = MCPClientService(
            mcp_server_url=config.mcp_server_url,
            oauth_client=oauth_client
        )
        
        # Pre-load tools from MCP server
        _load_mcp_tools()
    except Exception as e:
        raise RuntimeError(f"Failed to initialize MCP client: {str(e)}")


def _get_mcp_service() -> MCPClientService:
    """Get or create MCPClientService instance.
    
    Returns:
        MCPClientService instance
        
    Raises:
        RuntimeError: If MCP tools have not been initialized
    """
    global _mcp_service, _current_config
    if _current_config is None:
        raise RuntimeError("Database tools not initialized. Call initialize_customer_validation_tools() first.")
    if _mcp_service is None:
        initialize_customer_validation_tools(_current_config)
    return _mcp_service


def _load_mcp_tools() -> None:
    """Load tools from MCP server and cache them."""
    global _mcp_service, _mcp_tools_cache
    
    if _mcp_service is None:
        return
    
    try:
        langchain_tools = _mcp_service.get_langchain_tools()
        for tool in langchain_tools:
            _mcp_tools_cache[tool.name] = tool
    except Exception as e:
        raise RuntimeError(f"Failed to load MCP tools: {str(e)}")


def _get_mcp_tool(tool_name: str) -> StructuredTool:
    """Get a specific tool from MCP server.
    
    Args:
        tool_name: Name of the tool to retrieve
        
    Returns:
        LangChain StructuredTool instance
        
    Raises:
        RuntimeError: If tool is not found or MCP service is not initialized
    """
    global _mcp_tools_cache, _mcp_service
    
    # Reload tools if cache is empty
    if not _mcp_tools_cache:
        _load_mcp_tools()
    
    if tool_name in _mcp_tools_cache:
        return _mcp_tools_cache[tool_name]
    
    # Tool not found in cache, try to reload
    _load_mcp_tools()
    if tool_name in _mcp_tools_cache:
        return _mcp_tools_cache[tool_name]
    
    raise RuntimeError(f"Tool '{tool_name}' not found on MCP server")


def _get_mcp_tool_name(local_tool_name: str) -> str:
    """Get the MCP server tool name for a local tool name.
    
    Args:
        local_tool_name: Local tool name (e.g., "find_customer")
        
    Returns:
        MCP server tool name (e.g., "order-management-api___find_customer_api_customer_get")
        
    Raises:
        ValueError: If tool mapping is not found or tool is not available
    """
    mcp_tool_name = _MCP_TOOL_NAME_MAPPING.get(local_tool_name)
    
    if mcp_tool_name is None:
        if local_tool_name in _MCP_TOOL_NAME_MAPPING:
            # Tool is explicitly mapped to None (not available)
            raise ValueError(f"Tool '{local_tool_name}' is not available on the MCP server")
        else:
            # Tool mapping doesn't exist
            raise ValueError(f"No mapping found for tool '{local_tool_name}'. Available tools: {list(_MCP_TOOL_NAME_MAPPING.keys())}")
    
    return mcp_tool_name


def _call_mcp_tool(tool_name: str, **kwargs) -> Dict[str, Any]:
    """Call a tool on the MCP server.
    
    Args:
        tool_name: Local tool name (e.g., "find_customer")
        **kwargs: Arguments to pass to the tool
        
    Returns:
        Tool execution result as a dictionary
    """
    mcp_service = _get_mcp_service()
    
    # Get the actual MCP server tool name
    mcp_tool_name = _get_mcp_tool_name(tool_name)
    
    try:
        result = mcp_service.call_tool(mcp_tool_name, kwargs)
        
        # Handle different result formats
        if isinstance(result, dict):
            return result
        elif isinstance(result, str):
            # Try to parse as JSON if it's a string
            try:
                import json
                return json.loads(result)
            except:
                return {"result": result}
        else:
            return {"result": str(result)}
    except Exception as e:
        return {"error": f"Could not call {tool_name}: {str(e)}"}


@tool
def find_customer(email: str = "", customer_id: str = "") -> dict:
    """Find a customer by email or customer ID.
    
    Use this tool to look up customer information in the database.
    
    Args:
        email: Customer's email address (optional)
        customer_id: Customer ID (optional)
    
    Returns:
        Dictionary with customer information if found, empty dict if not found.
        Contains: customer_id, name, email
    """
    if not email and not customer_id:
        return {}
    
    return _call_mcp_tool("find_customer", email=email, customer_id=customer_id)


@tool
def find_order(order_no: str = "") -> dict:
    """Find an order by order number.
    
    Use this tool to look up order information in the database.
    
    Args:
        order_no: Order number (e.g., "ORD00009998")
    
    Returns:
        Dictionary with order information if found, empty dict if not found.
        Contains: order_no, customer_id, order_status, order_date_time, etc.
    """
    if not order_no:
        return {}
    
    return _call_mcp_tool("find_order", order_no=order_no)


@tool
def find_transaction(transaction_id: str = "") -> dict:
    """Find a transaction by transaction ID.
    
    Use this tool to look up transaction information in the database.
    
    Args:
        transaction_id: Transaction ID to search for
    
    Returns:
        Dictionary with transaction information if found, empty dict if not found.
        Contains: transaction_id, order_no, customer_id, transaction_status, amount, etc.
    """
    if not transaction_id:
        return {}
    
    return _call_mcp_tool("find_transaction", transaction_id=transaction_id)


@tool
def get_transaction_for_order(order_no: str = "") -> dict:
    """Get transaction information for an order.
    
    Use this tool to look up transaction information associated with an order number.
    
    Args:
        order_no: Order number (e.g., "ORD00009998")
    
    Returns:
        Dictionary with transaction information if found, empty dict if not found.
        Contains: transaction_id, order_no, customer_id, transaction_status, amount, etc.
    """
    if not order_no:
        return {}
    
    return _call_mcp_tool("get_transaction_for_order", order_no=order_no)


@tool
def get_refund_for_order(order_no: str = "") -> dict:
    """Get refund information for an order.
    
    Use this tool to look up refund information associated with an order number.
    
    Args:
        order_no: Order number (e.g., "ORD00009998")
    
    Returns:
        Dictionary with refund information if found, empty dict if not found.
        Contains: refund_id, order_no, transaction_id, refund_status, refund_amount, etc.
    """
    if not order_no:
        return {}
    
    return _call_mcp_tool("get_refund_for_order", order_no=order_no)
