"""Customer conversation node for customer support agent.

This module contains the customer conversation agent that uses create_agent
to interact with customers and provide assistance based on all available context.
"""

from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from agent.configuration import Configuration
from agent.state import CustomerSupportState
from agent.prompts import get_customer_conversation_system_prompt
from agent.middleware import AgentCoreMemoryMiddleware
from tools.database import (
    find_customer,
    find_order,
    find_transaction,
    get_transaction_for_order,
    get_refund_for_order,
    initialize_customer_validation_tools,
)
from services.bedrock import BedrockService


def customer_conversation_node(
    state: CustomerSupportState, config: RunnableConfig
) -> CustomerSupportState:
    """Handle customer conversation using create_agent with all context from state.
    
    This agent has access to all collected information and tools to assist
    the customer with their issue. If no issue_no is present, it will ask for
    email and issue number. Otherwise, it will answer customer queries.
    
    Args:
        state: Current state with all context
        config: Runtime configuration
        
    Returns:
        Updated state with agent's response
    """
    cfg = Configuration.from_environment()
    bedrock_service = BedrockService(cfg)
    llm = bedrock_service.get_reasoning_llm()
    messages = state.get("messages", [])
    
    # Initialize database tools
    initialize_customer_validation_tools(cfg)
    
    # Check if issue_no is present
    issue_no = state.get("issue_no")
    
    # If no issue_no, route to collect customer information
    if not issue_no:
        # Return empty dict to allow routing without adding messages
        return {}
    
    # If issue_no exists, create agent with all context and tools
    system_prompt = get_customer_conversation_system_prompt(state)
    
    # Create agent with all available database tools and memory middleware
    # Pass actor_id and session_id from state to middleware
    agent = create_agent(
        model=llm,
        tools=[
            find_customer,
            find_order,
            find_transaction,
            get_transaction_for_order,
            get_refund_for_order,
        ],
        system_prompt=system_prompt,
        middleware=[AgentCoreMemoryMiddleware(
            cfg,
            actor_id=config.get("configurable", {}).get("actor_id") if config else None,
            session_id=config.get("configurable", {}).get("thread_id") if config else None
        )],
    )
    
    # Invoke agent with current messages
    try:
        result = agent.invoke({"messages": messages})
        
        # Extract incremental messages from agent result
        updates = {}
        if isinstance(result, dict) and "messages" in result:
            agent_messages = result["messages"]
            
            # Get only the new messages (those not already in state)
            if len(agent_messages) > len(messages):
                updates["messages"] = agent_messages[len(messages):]
        
        return updates
    except Exception as e:
        import traceback
        print(f"ERROR in customer_conversation_node: {str(e)}")
        print(traceback.format_exc())
        return {
            "messages": [AIMessage(content="I apologize, but I encountered an error. Please try again or provide your email and issue number.")]
        }
