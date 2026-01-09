"""Response generation workflow node.

This module contains the node for generating and updating triage responses in Jira
using an agent with access to database tools to fetch complete order, transaction, and refund details.
"""

from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from agent.configuration import Configuration
from agent.state import CustomerSupportState
from agent.prompts import get_response_generation_system_prompt
from agent.utils import extract_text_content
from agent.middleware import AgentCoreMemoryMiddleware
from tools.database import (
    find_transaction,
    find_order,
    get_transaction_for_order,
    get_refund_for_order,
    initialize_customer_validation_tools,
)
from services.bedrock import BedrockService
from services.jira import JiraService


def update_response_node(
    state: CustomerSupportState, config: RunnableConfig
) -> CustomerSupportState:
    """Generate and update triage response in Jira using agent with database tools.
    
    This node:
    1. Creates an agent with access to find_transaction, find_order, get_transaction_for_order, and get_refund_for_order tools
    2. Uses reasoning LLM to generate a comprehensive response
    3. The agent uses tools to fetch complete JSON objects for transaction, order, and refund
    4. Updates the response in Jira
    
    Args:
        state: Current state containing issue information and identifiers
        config: Runtime configuration
        
    Returns:
        Updated state with response set
    """
    issue_no = state.get("issue_no")
    if not issue_no:
        # No issue_no - skip response update
        return {}
    
    cfg = Configuration.from_runnable_config(config)
    bedrock_service = BedrockService(cfg)
    llm = bedrock_service.get_reasoning_llm()
    messages = state.get("messages", [])
    
    # Initialize database tools
    initialize_customer_validation_tools(cfg)
    
    # Get information from state
    category = state.get("category", "N/A")
    summary = state.get("summary", "N/A")
    description = state.get("description", "N/A")
    transaction_id = state.get("transaction_id")
    order_no = state.get("order_no")
    
    # Get system prompt with context
    system_prompt = get_response_generation_system_prompt(
        category=category,
        summary=summary,
        description=description,
        transaction_id=transaction_id,
        order_no=order_no
    )
    
    # Create agent with database query tools and memory middleware
    # Pass actor_id and session_id from state to middleware
    response_agent = create_agent(
        model=llm,
        tools=[
            find_transaction,
            find_order,
            get_transaction_for_order,
            get_refund_for_order,
        ],
        system_prompt=system_prompt,
        middleware=[AgentCoreMemoryMiddleware(
            cfg,
            actor_id=state.get("customer_email"),
            session_id=state.get("issue_no")
        )],
    )
    
    # Invoke agent - it will use tools to fetch details and generate response
    # Use existing messages from state and add a trigger message
    # This message will be visible to the user, so make it conversational
    input_messages = [AIMessage(content="I have completed the analysis and will now generate a comprehensive response for your issue.")]
    result = response_agent.invoke({"messages": input_messages})
    
    # Extract the final response from agent messages
    response = ""
    updates = {}
    
    if isinstance(result, dict) and "messages" in result:
        agent_messages = result["messages"]
        
        # Find the last AI message that contains the actual response
        # (after all tool calls are complete)
        for msg in reversed(agent_messages):
            if isinstance(msg, AIMessage) and msg.content:
                content = extract_text_content(msg.content)
                # Skip very short messages or tool call confirmations
                if content and len(content) > 100:
                    # This should be the final comprehensive response
                    response = content
                    break
        
        # Extract new messages from agent result (incremental messages only)
        if len(agent_messages) > len(input_messages):
            updates["messages"] = agent_messages[len(input_messages):]
    
    # If no response found, raise an error to make it clear something went wrong
    if not response:
        raise ValueError("Agent failed to generate a response. No valid response found in agent messages.")
    
    # Update response in Jira
    jira_service = JiraService(cfg)
    try:
        jira_service.set_response(issue_no, response)
    except Exception as e:
        print(f"Warning: Could not update response in Jira: {str(e)}")
    
    # Add response to updates
    updates["response"] = response
    
    return updates
