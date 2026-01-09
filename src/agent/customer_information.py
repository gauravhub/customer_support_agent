"""Customer information collection node for customer support agent.

This module contains the customer information collection node that uses
tools from the tools package to validate and record customer information.
"""

from langchain.agents import create_agent
from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from agent.configuration import Configuration
from agent.state import CustomerSupportState
from agent.prompts import get_customer_information_system_prompt
from agent.middleware import AgentCoreMemoryMiddleware
from tools.database import (
    find_customer,
    initialize_customer_validation_tools,
)
from tools.jira import get_jira_field_value, initialize_jira_tools
from services.bedrock import BedrockService
from services.database import DatabaseService


@tool
def record_customer_info(
    email: str = "",
    issue_no: str = ""
) -> str:
    """Record customer information that has been collected from the conversation.
    
    Use this tool to store information as you extract it from the user's messages.
    You MUST call this tool whenever you extract any information from the user's message.
    You can call this multiple times as you collect different pieces of information.
    
    Args:
        email: Customer's email address (use exactly as provided by user, empty string if not provided)
        issue_no: Support issue/ticket number (use exactly as provided by user, e.g., "64", "AS-5", etc., empty string if not provided)
    
    Returns:
        Confirmation of what was recorded
    """
    recorded = []
    
    if email and email.strip():
        recorded.append("email")
    if issue_no and issue_no.strip():
        recorded.append("issue_no")
    
    if recorded:
        return f"Successfully recorded: {', '.join(recorded)}"
    else:
        return "No new information to record"


def _extract_info_from_tool_calls(messages: list) -> dict:
    """Extract customer information from record_customer_info tool calls in agent messages.
    
    This function parses the agent's tool calls to extract the information that was recorded.
    This makes the node self-contained without relying on global state.
    
    Args:
        messages: List of messages from agent result
        
    Returns:
        Dictionary with extracted information (customer_email, issue_no)
    """
    extracted = {}
    
    for msg in messages:
        if isinstance(msg, AIMessage):
            tool_calls = getattr(msg, "tool_calls", None)
            if tool_calls:
                for tool_call in tool_calls:
                    if tool_call.get("name") == "record_customer_info":
                        args = tool_call.get("args", {})
                        # Extract non-empty values
                        if args.get("email", "").strip():
                            extracted["customer_email"] = args["email"].strip()
                        if args.get("issue_no", "").strip():
                            extracted["issue_no"] = args["issue_no"].strip()
    
    return extracted


def collect_customer_information_node(
    state: CustomerSupportState, config: RunnableConfig
) -> CustomerSupportState:
    """Collect customer information using create_agent.
    
    The agent handles its own looping - it will extract information, check what's missing,
    and ask for more details until all required information is collected.
    """
    cfg = Configuration.from_runnable_config(config)
    bedrock_service = BedrockService(cfg)
    llm = bedrock_service.get_reasoning_llm()
    messages = state.get("messages", [])
    
    # Initialize customer validation tools and Jira tools
    initialize_customer_validation_tools(cfg)
    initialize_jira_tools(cfg)
    
    # Check if we already have all required information (email + issue)
    has_required_info = all([
        state.get("customer_email"),
        state.get("issue_no")
    ])
    if has_required_info:
        # Fetch customer name from database
        db_service = DatabaseService(cfg)
        customer = db_service.find_customer(email=state.get("customer_email"))
        
        return {
            "customer_name": customer.get("name")
        }
    
    # Create agent with database query and recording tools and memory middleware
    # Pass actor_id and session_id from state to middleware
    customer_information_agent = create_agent(
        model=llm,
        tools=[
            find_customer,
            get_jira_field_value,
            record_customer_info
        ],
        system_prompt=get_customer_information_system_prompt(state.get("customer_email"), state.get("issue_no")),
        middleware=[AgentCoreMemoryMiddleware(
            cfg,
            actor_id=config.get("configurable", {}).get("actor_id") if config else None,
            session_id=config.get("configurable", {}).get("thread_id") if config else None
        )],
    )
    
    # Invoke agent - it will process the user's message and ask for missing info if needed
    try:
        result = customer_information_agent.invoke({"messages": messages})
        
        # In LangGraph, nodes return a dictionary of state updates (not modify state directly)
        # LangGraph automatically merges these updates into the state
        # Extract information from tool calls in agent messages
        updates = {}
        
        # Extract information from record_customer_info tool calls
        if isinstance(result, dict) and "messages" in result:
            extracted_info = _extract_info_from_tool_calls(result["messages"])
            
            # Update state with extracted information (only if new values were provided)
            if extracted_info.get("customer_email"):
                updates["customer_email"] = extracted_info["customer_email"]
            if extracted_info.get("issue_no"):
                updates["issue_no"] = extracted_info["issue_no"]
            
            # Check if we now have both email and issue (either from updates or existing state)
            final_email = updates.get("customer_email") or state.get("customer_email")
            final_issue = updates.get("issue_no") or state.get("issue_no")
            
            # If we now have both email and issue, fetch customer name
            if final_email and final_issue:
                db_service = DatabaseService(cfg)
                customer = db_service.find_customer(email=final_email)
                
                if customer:
                    updates["customer_name"] = customer.get("name")
        
        # Extract new messages from agent result (incremental messages only)
        if isinstance(result, dict) and "messages" in result:
            agent_messages = result["messages"]

            if len(agent_messages) > len(messages):
                updates["messages"] = agent_messages[len(messages):]
        
        # Return updates - LangGraph will merge these into the state automatically
        # The conditional edge will check if all info is collected and loop back if needed
        return updates
    except Exception as e:
        import traceback
        print(f"ERROR in collect_customer_information_node: {str(e)}")
        print(traceback.format_exc())
        return {
            "messages": [AIMessage(content="I need your email address and support issue/ticket number. Please provide these details.")]
        }
