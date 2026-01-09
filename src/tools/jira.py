"""Jira query tools for customer support agent.

This module exposes Jira query tools that the agent can use
to retrieve field values from Jira issues.
"""

from langchain_core.tools import tool
from typing import Optional

from agent.configuration import Configuration
from services.jira import JiraService


# Jira service instance and config (will be initialized when needed)
_jira_service = None
_current_config = None


def initialize_jira_tools(config: Configuration) -> None:
    """Initialize Jira query tools with configuration.
    
    This function sets the configuration for Jira query tools.
    
    Args:
        config: Configuration object containing Jira settings
    """
    global _jira_service, _current_config
    _current_config = config
    if _jira_service is None:
        _jira_service = JiraService(config)


def _get_jira_service() -> JiraService:
    """Get or create JiraService instance.
    
    Returns:
        JiraService instance
        
    Raises:
        RuntimeError: If Jira tools have not been initialized
    """
    global _jira_service, _current_config
    if _current_config is None:
        raise RuntimeError("Jira tools not initialized. Call initialize_jira_tools() first.")
    if _jira_service is None:
        _jira_service = JiraService(_current_config)
    return _jira_service


@tool
def get_jira_field_value(issue_key: str = "", field_name: str = "") -> dict:
    """Get a field value from a Jira issue.
    
    Use this tool to retrieve the value of any field from a Jira issue.
    This is useful for accessing custom fields or standard fields like reporter.
    
    Args:
        issue_key: Jira issue key (e.g., "AS-4", "AS-5")
        field_name: Field name to retrieve (e.g., "reporter" for reporter email, "customfield_10071" for custom fields)
    
    Returns:
        Dictionary with field value if found, empty dict if not found or error.
        For reporter field, returns: {{"reporter": "email@example.com"}} or {{"reporter": null}}
        For other fields, returns: {{field_name: value}}
    """
    if not issue_key or not field_name:
        return {}
    
    try:
        jira_service = _get_jira_service()
        field_value = jira_service.get_field_value(issue_key, field_name)
        
        if field_value is None:
            return {}
        
        # Handle reporter field specifically - extract email if it's a user object
        if field_name == "reporter":
            if hasattr(field_value, 'emailAddress'):
                return {"reporter": field_value.emailAddress}
            else:
                return {"reporter": None}
        
        # For other fields, return the value directly
        return {field_name: field_value}
    except Exception as e:
        return {"error": f"Could not get field value: {str(e)}"}
