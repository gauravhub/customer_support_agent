"""Tests for Configuration."""

import os
from typing import Any

from agent.configuration import Configuration
from langchain_core.runnables import RunnableConfig


def test_configuration(config: Configuration) -> dict[str, Any]:
    """Test configuration loading and display.
    
    Collects environment variables and configuration object for display.
    
    Args:
        config: Configuration object to test
        
    Returns:
        Dictionary with environment variables and configuration dump
    """
    result: dict[str, Any] = {}
    
    # Collect relevant environment variables
    env_vars = {}
    relevant_prefixes = ["AWS_", "JIRA_", "LANGSMITH_"]
    
    # List of safe keys that should not be masked (even if they contain sensitive-sounding words)
    safe_keys = ["AWS_REGION", "AWS_DEFAULT_REGION", "JIRA_PROJECT_KEY"]
    
    for key, value in os.environ.items():
        if any(key.startswith(prefix) for prefix in relevant_prefixes):
            # Mask sensitive values, but not safe keys
            if key in safe_keys:
                env_vars[key] = value
            elif "TOKEN" in key or "PASSWORD" in key or "SECRET" in key or ("KEY" in key and "ACCESS_KEY" in key):
                env_vars[key] = "***MASKED***" if value else None
            else:
                env_vars[key] = value
    
    # If no environment variables found, add a note
    if not env_vars:
        env_vars["_note"] = "No environment variables found with prefixes: AWS_, JIRA_, LANGSMITH_"
        env_vars["_hint"] = "Make sure your .env file is loaded or variables are set in the environment"
    
    # Format configuration as dictionary
    config_dict = config.model_dump()
    
    result["environment_variables"] = env_vars
    result["configuration"] = config_dict
    
    return result


def test_configuration_from_runnable_config(runnable_config: RunnableConfig) -> dict[str, Any]:
    """Test configuration loading from RunnableConfig.
    
    Args:
        runnable_config: RunnableConfig object (from LangGraph)
        
    Returns:
        Dictionary with environment variables and configuration dump
    """
    # Load configuration from the config parameter
    cfg = Configuration.from_runnable_config(runnable_config)
    
    return test_configuration(cfg)

