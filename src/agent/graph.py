"""Customer Support Agent - Welcome and Information Collection Graph.

This is the initial graph that welcomes users and collects required information:
- Email address
- Full name
- Order number or support issue number

Once information is collected, the workflow can proceed to issue triage.
"""

from langgraph.graph import StateGraph, START, END, MessagesState
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from langchain_core.runnables import RunnableConfig

from agent.configuration import Configuration
from agent.state import CustomerSupportState
from agent.customer_conversation import customer_conversation_node
from agent.customer_information import collect_customer_information_node
from agent.issue_assessment import (
    fetch_issue_details_node,
    update_assignee_node,
    update_category_node,
    analyze_attachments_node,
    analyze_summary_node,
)
from agent.response_generation import update_response_node
from agent.utils import initialize_database

# Initialize database when graph module is loaded
initialize_database()

# ============================================================================
# GRAPH CONSTRUCTION
# ============================================================================

# Create the graph builder
builder = StateGraph(
    CustomerSupportState,
    input_schema=MessagesState,
    config_schema=Configuration
)

# Add nodes
builder.add_node("Customer Conversation", customer_conversation_node)
builder.add_node("Collect Customer Information", collect_customer_information_node)
builder.add_node("Fetch Issue Details", fetch_issue_details_node)
builder.add_node("Assign Support Contact", update_assignee_node)
builder.add_node("Determine Category", update_category_node)
builder.add_node("Analyze Attachments", analyze_attachments_node)
builder.add_node("Analyze Summary", analyze_summary_node)
builder.add_node("Generate Response", update_response_node)

# Add edges with routing
builder.add_edge(START, "Customer Conversation")

# Conditional edge from Customer Conversation based on issue_no
def route_after_conversation(state: CustomerSupportState) -> str:
    """Route after customer conversation based on whether issue_no exists."""
    issue_no = state.get("issue_no")
    if not issue_no:
        return "Collect Customer Information"
    else:
        return "end"

builder.add_conditional_edges(
    "Customer Conversation",
    route_after_conversation,
    {
        "Collect Customer Information": "Collect Customer Information",
        "end": END
    }
)

builder.add_edge("Collect Customer Information", "Fetch Issue Details")

# Triage workflow sequence
builder.add_edge("Fetch Issue Details", "Assign Support Contact")
builder.add_edge("Assign Support Contact", "Determine Category")
builder.add_edge("Determine Category", "Analyze Attachments")
builder.add_edge("Analyze Attachments", "Analyze Summary")
builder.add_edge("Analyze Summary", "Generate Response")
builder.add_edge("Generate Response", END)  # After triage, end workflow

# Add human interrupts - pause before/after specific nodes for human review
# Example: Add interrupt before generating response (for human review of analysis)
# builder.add_interrupt_before(["Generate Response"])

# Example: Add interrupt after generating response (for human approval before sending)
# builder.add_interrupt_after(["Generate Response"])

# Compile the graph
graph = builder.compile()

