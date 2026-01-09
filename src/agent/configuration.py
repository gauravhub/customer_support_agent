"""Configuration management for the Customer Support agent."""

import os
from pathlib import Path
from typing import Optional, Any, get_origin, get_args

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field, model_validator

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    # Load .env file from project root
    project_root = Path(__file__).parent.parent.parent
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    # python-dotenv not installed, rely on environment variables being set externally
    pass


class Configuration(BaseModel):
    """Main configuration class for the Customer Support agent.
    
    Configuration is loaded from environment variables (uppercase) or field defaults.
    Environment variables take precedence over defaults.
    """
    
    # Bedrock model configuration
    text_model: str = Field(
        default="mistral.mistral-large-2407-v1:0",
        description="Bedrock model for text processing"
    )
    vision_model: str = Field(
        default="us.mistral.pixtral-large-2502-v1:0",
        description="Bedrock model for vision/image processing"
    )
    reasoning_model: str = Field(
        default="us.anthropic.claude-sonnet-4-20250514-v1:0",
        description="Bedrock model for reasoning and agent tasks (Claude Sonnet 4 with US regional inference endpoint)"
    )
    max_tokens: int = Field(
        default=4000,
        description="Maximum tokens for LLM responses"
    )
    temperature: float = Field(
        default=0.0,
        description="Temperature for LLM responses (0.0 = deterministic)"
    )
    
    # Bedrock Guardrail configuration
    guardrail_id: Optional[str] = Field(
        default=None,
        description="Bedrock Guardrail ID for content safety (optional)"
    )
    guardrail_version: str = Field(
        default="DRAFT",
        description="Guardrail version to use"
    )
    
    # Jira integration configuration
    jira_api_username: Optional[str] = Field(
        default=None,
        description="Jira username/email for API authentication (used with API token for basic auth)"
    )
    jira_api_token: Optional[str] = Field(
        default=None,
        description="Jira API token for authentication"
    )
    jira_instance_url: Optional[str] = Field(
        default=None,
        description="Jira instance URL (e.g., https://your-domain.atlassian.net)"
    )
    jira_project_key: str = Field(
        default="AS",
        description="Jira project key for customer support tickets"
    )
    jira_assignee_username: Optional[str] = Field(
        default=None,
        description="Jira username/email for ticket assignment (e.g., bot user or default assignee)"
    )
    jira_category_field_id: int = Field(
        default=0,
        description="Jira custom field ID for ticket category (e.g., 10071 for customfield_10071). Set via JIRA_CATEGORY_FIELD_ID environment variable."
    )
    jira_response_field_id: int = Field(
        default=0,
        description="Jira custom field ID for ticket response (e.g., 10072 for customfield_10072). Set via JIRA_RESPONSE_FIELD_ID environment variable."
    )
    
    # Database configuration
    database_path: str = Field(
        default="./data/customer_support.db",
        description="Path to SQLite database file"
    )
    
    @model_validator(mode='before')
    @classmethod
    def load_from_env(cls, data: Any) -> dict[str, Any]:
        """Load configuration from environment variables before Pydantic validation.
        
        This ensures environment variables are always checked, even when LangGraph
        creates Configuration directly from RunnableConfig.
        """
        if not isinstance(data, dict):
            data = {}
        
        # Build values dict from environment variables
        values: dict[str, Any] = {}
        field_names = list(cls.model_fields.keys())
        
        for field_name in field_names:
            env_value = os.environ.get(field_name.upper())
            if env_value is not None and env_value.strip():
                # Convert string to appropriate type based on field type
                field_info = cls.model_fields[field_name]
                field_type = field_info.annotation
                
                # Handle Optional types - extract the inner type
                origin = get_origin(field_type)
                if origin is not None:
                    args = get_args(field_type)
                    if args:
                        field_type = next((arg for arg in args if arg is not type(None)), str)
                
                # Type conversion
                try:
                    if field_type == int:
                        values[field_name] = int(env_value)
                    elif field_type == float:
                        values[field_name] = float(env_value)
                    elif field_type == bool:
                        values[field_name] = env_value.lower() in ('true', '1', 'yes', 'on')
                    else:
                        values[field_name] = env_value
                except (ValueError, TypeError):
                    # If type conversion fails, skip this field
                    pass
        
        # Merge: env vars take precedence, then data (from RunnableConfig), then defaults
        # Start with data, then override with env vars
        result = {**data, **values}
        return result
    
    @classmethod
    def from_runnable_config(
        cls, config: Optional[RunnableConfig] = None
    ) -> "Configuration":
        """Create a Configuration instance from environment variables.
        
        Loads configuration from:
        1. Environment variables (uppercase, e.g., TEXT_MODEL, REASONING_MODEL)
        2. Field defaults (if environment variable not set)
        
        Environment variables take precedence over defaults.
        RunnableConfig is ignored - all configuration must come from environment variables.
        """
        field_names = list(cls.model_fields.keys())
        
        values: dict[str, Any] = {}
        for field_name in field_names:
            env_value = os.environ.get(field_name.upper())
            if env_value is not None and env_value.strip():  # Also check for empty strings
                # Convert string to appropriate type based on field type
                field_info = cls.model_fields[field_name]
                field_type = field_info.annotation
                
                # Handle Optional types - extract the inner type
                origin = get_origin(field_type)
                if origin is not None:
                    # For Optional[Type], get_args returns (Type, NoneType)
                    args = get_args(field_type)
                    if args:
                        # Get the first non-None type
                        field_type = next((arg for arg in args if arg is not type(None)), str)
                
                # Type conversion
                try:
                    if field_type == int:
                        values[field_name] = int(env_value)
                    elif field_type == float:
                        values[field_name] = float(env_value)
                    elif field_type == bool:
                        values[field_name] = env_value.lower() in ('true', '1', 'yes', 'on')
                    else:
                        values[field_name] = env_value
                except (ValueError, TypeError) as e:
                    # If type conversion fails, skip this field and use default
                    print(f"Warning: Could not convert environment variable {field_name.upper()}={env_value} to {field_type}: {e}")
        
        # Create instance with environment values, missing fields will use defaults
        return cls(**values)

