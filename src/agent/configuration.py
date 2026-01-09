"""Configuration management for the Customer Support agent."""

import os
from typing import Optional

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field


class Configuration(BaseModel):
    """Main configuration class for the Customer Support agent."""
    
    # Bedrock model configuration
    text_model: str = Field(
        default="mistral.mistral-large-2407-v1:0",
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "default": "mistral.mistral-large-2407-v1:0",
                "description": "Bedrock model for text processing"
            }
        }
    )
    vision_model: str = Field(
        default="us.mistral.pixtral-large-2502-v1:0",
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "default": "us.mistral.pixtral-large-2502-v1:0",
                "description": "Bedrock model for vision/image processing"
            }
        }
    )
    reasoning_model: str = Field(
        default="us.anthropic.claude-sonnet-4-20250514-v1:0",
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "default": "us.anthropic.claude-sonnet-4-20250514-v1:0",
                "description": "Bedrock model for reasoning and agent tasks (Claude Sonnet 4 with US regional inference endpoint)"
            }
        }
    )
    max_tokens: int = Field(
        default=4000,
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "default": 4000,
                "min": 100,
                "max": 8000,
                "description": "Maximum tokens for LLM responses"
            }
        }
    )
    temperature: float = Field(
        default=0.0,
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "default": 0.0,
                "min": 0.0,
                "max": 2.0,
                "step": 0.1,
                "description": "Temperature for LLM responses (0.0 = deterministic)"
            }
        }
    )
    
    # Bedrock Guardrail configuration
    guardrail_id: Optional[str] = Field(
        default=None,
        optional=True,
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "description": "Bedrock Guardrail ID for content safety (optional)"
            }
        }
    )
    guardrail_version: str = Field(
        default="DRAFT",
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "default": "DRAFT",
                "description": "Guardrail version to use"
            }
        }
    )
    
    # Jira integration configuration
    jira_api_username: Optional[str] = Field(
        default=None,
        optional=True,
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "description": "Jira username/email for API authentication (used with API token for basic auth)"
            }
        }
    )
    jira_api_token: Optional[str] = Field(
        default=None,
        optional=True,
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "description": "Jira API token for authentication"
            }
        }
    )
    jira_instance_url: Optional[str] = Field(
        default=None,
        optional=True,
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "description": "Jira instance URL (e.g., https://your-domain.atlassian.net)"
            }
        }
    )
    jira_project_key: str = Field(
        default="AS",
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "default": "AS",
                "description": "Jira project key for customer support tickets"
            }
        }
    )
    jira_assignee_username: Optional[str] = Field(
        default=None,
        optional=True,
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "description": "Jira username/email for ticket assignment (e.g., bot user or default assignee)"
            }
        }
    )
    jira_category_field_id: int = Field(
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "description": "Jira custom field ID for ticket category (e.g., customfield_10071)"
            }
        }
    )
    jira_response_field_id: int = Field(
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "description": "Jira custom field ID for ticket response (e.g., customfield_10072)"
            }
        }
    )
    
    # Database configuration
    database_path: str = Field(
        default="./data/customer_support.db",
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "default": "./data/customer_support.db",
                "description": "Path to SQLite database file"
            }
        }
    )
    
    @classmethod
    def from_runnable_config(
        cls, config: Optional[RunnableConfig] = None
    ) -> "Configuration":
        """Create a Configuration instance from a RunnableConfig.
        
        Loads configuration from:
        1. Environment variables (uppercase, e.g., AWS_REGION)
        2. RunnableConfig configurable dict
        3. Field defaults
        """
        configurable = config.get("configurable", {}) if config else {}
        field_names = list(cls.model_fields.keys())
        
        values: dict[str, Optional[str]] = {}
        for field_name in field_names:
            env_value = os.environ.get(field_name.upper())
            config_value = configurable.get(field_name)
            values[field_name] = env_value if env_value is not None else config_value
        
        return cls(**{k: v for k, v in values.items() if v is not None})

