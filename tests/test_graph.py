"""Test graph for running service tests and configuration validation.

This graph is used for testing all services (Bedrock, Jira, Database) and
validating configuration. It's separate from the main customer support agent flow.
"""

import json
from langgraph.graph import StateGraph, START, END, MessagesState
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from agent.configuration import Configuration
from agent.state import CustomerSupportState
from tests.test_bedrock import run_all_bedrock_tests
from tests.test_configuration import test_configuration_from_runnable_config
from tests.test_database import test_database_service
from tests.test_jira import test_jira_service


def test_node(state: CustomerSupportState, config: RunnableConfig):
    """Test node that runs all service tests and displays configuration.
    
    This demonstrates how to access configuration in a node:
    1. Add `config: RunnableConfig` parameter to the node function
    2. Use `Configuration.from_runnable_config(config)` to load config
    3. Access configuration values as attributes (e.g., cfg.text_model)
    4. Access environment variables directly (e.g., AWS_REGION)
    
    Configuration priority:
    1. Environment variables (uppercase, e.g., AWS_REGION)
    2. RunnableConfig configurable dict (from LangGraph Studio UI or API)
    3. Field defaults (defined in Configuration class)
    """
    # Load configuration from the config parameter
    cfg = Configuration.from_runnable_config(config)
    
    # Test configuration
    config_test_result = test_configuration_from_runnable_config(config)
    
    # Run service tests
    bedrock_tests = run_all_bedrock_tests(cfg)
    jira_test_result = test_jira_service(cfg)
    database_test_result = test_database_service(cfg)
    
    # Build output message
    output_lines = [
        "=== Customer Support Agent Initialized ===",
        "",
        "--- Environment Variables ---",
        json.dumps(config_test_result["environment_variables"], indent=2, sort_keys=True),
        "",
        "--- Configuration Object ---",
        json.dumps(config_test_result["configuration"], indent=2, default=str),
        "",
        "--- Bedrock Text Model Test ---",
        json.dumps(bedrock_tests["text_llm"], indent=2, default=str),
        "",
        "--- Bedrock Vision Model Test ---",
        json.dumps(bedrock_tests["vision_llm"], indent=2, default=str),
        "",
        "--- Jira Service Test ---",
        json.dumps(jira_test_result, indent=2, default=str),
        "",
        "--- Database Service Test ---",
        json.dumps(database_test_result, indent=2, default=str),
        "",
        "=== Ready to process tickets ==="
    ]
    
    greeting = "\n".join(output_lines)
    
    return {"messages": [AIMessage(content=greeting)]}


# Create and compile the test graph with MessagesState as input schema
# This makes LangGraph Studio only show Messages in the input panel
# config_schema exposes Configuration fields in LangGraph Studio assistant settings
builder = StateGraph(
    CustomerSupportState,
    input_schema=MessagesState,
    config_schema=Configuration
)
builder.add_node("test", test_node)
builder.add_edge(START, "test")
builder.add_edge("test", END)

# Compile the test graph - this is what langgraph.json references
test_graph = builder.compile()

