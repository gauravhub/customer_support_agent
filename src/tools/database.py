"""Database query tools for customer support agent.

This module exposes fundamental database query tools that the agent can use
to find customers, orders, transactions, and refunds. The agent can compose these tools
to validate ownership and relationships.
"""

from langchain_core.tools import tool
from typing import Optional

from agent.configuration import Configuration
from services.database import DatabaseService


# Database service instance and config (will be initialized when needed)
_db_service = None
_current_config = None


def initialize_customer_validation_tools(config: Configuration) -> None:
    """Initialize database query tools with configuration.
    
    This function sets the configuration for database query tools.
    The database itself is assumed to be already initialized when the graph loads.
    
    Args:
        config: Configuration object containing database settings
    """
    global _db_service, _current_config
    _current_config = config
    if _db_service is None:
        _db_service = DatabaseService(config)


def _get_db_service() -> DatabaseService:
    """Get or create DatabaseService instance.
    
    Returns:
        DatabaseService instance
        
    Raises:
        RuntimeError: If database tools have not been initialized
    """
    global _db_service, _current_config
    if _current_config is None:
        raise RuntimeError("Database tools not initialized. Call initialize_customer_validation_tools() first.")
    if _db_service is None:
        _db_service = DatabaseService(_current_config)
    return _db_service


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
    
    try:
        db_service = _get_db_service()
        customer = db_service.find_customer(email=email, customer_id=customer_id)
        return customer if customer else {}
    except Exception as e:
        return {"error": f"Could not find customer: {str(e)}"}


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
    
    try:
        db_service = _get_db_service()
        order = db_service.find_order(order_no)
        return order if order else {}
    except Exception as e:
        return {"error": f"Could not find order: {str(e)}"}


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
    
    try:
        db_service = _get_db_service()
        transaction = db_service.find_transaction(transaction_id)
        return transaction if transaction else {}
    except Exception as e:
        return {"error": f"Could not find transaction: {str(e)}"}


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
    
    try:
        db_service = _get_db_service()
        transaction = db_service.get_transaction_for_order(order_no)
        return transaction if transaction else {}
    except Exception as e:
        return {"error": f"Could not find transaction for order: {str(e)}"}


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
    
    try:
        db_service = _get_db_service()
        refund = db_service.get_refund_for_order(order_no)
        return refund if refund else {}
    except Exception as e:
        return {"error": f"Could not find refund for order: {str(e)}"}
