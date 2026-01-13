"""Issue triage workflow nodes.

This module contains nodes for triaging customer support issues:
1. Update assignee - Assign issue to bot user
2. Update Category - Categorize and update issue category in Jira
3. Analyze Attachments - Extract transaction_id or order_no from attachments
4. Analyze Summary - Extract order_no or transaction_id from summary and fetch details
5. Update Response - Generate and update triage response in Jira
"""

import json
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from agent.configuration import Configuration
from agent.state import CustomerSupportState
from agent.prompts import (
    get_categorization_prompt,
    get_extract_transaction_id_prompt,
    get_extract_order_number_prompt,
    get_analyze_attachments_prompt,
)
from agent.utils import add_image_content, extract_json_from_response, extract_text_content
from services.bedrock import BedrockService
from services.jira import JiraService


def fetch_issue_details_node(
    state: CustomerSupportState, config: RunnableConfig
) -> CustomerSupportState:
    """Fetch issue details from Jira.
    
    This node fetches issue details from Jira including summary, description,
    attachments, category, assignee, reporter, and response.
    
    Args:
        state: Current state with issue_no
        config: Runtime configuration
        
    Returns:
        Updated state with issue details from Jira
    """
    issue_no = state.get("issue_no")
    if not issue_no:
        return {}
    
    updates = {}
    cfg = Configuration.from_environment()
    jira_service = JiraService(cfg)
    jira_issue = jira_service.fetch_issue(issue_no)
    
    if jira_issue:
        # Download attachments
        attachments = []
        if jira_issue.fields.attachment:
            for attachment in jira_issue.fields.attachment:
                try:
                    file_path = jira_service.download_attachment_file(attachment, issue_no)
                    attachments.append(file_path)
                except Exception as e:
                    print(f"Warning: Could not download attachment {attachment.filename}: {str(e)}")
        
        # Fetch reporter, category, and response using get_field_value
        reporter_value = jira_service.get_field_value(issue_no, "reporter")
        reporter_email = ""
        if reporter_value and hasattr(reporter_value, 'emailAddress'):
            reporter_email = reporter_value.emailAddress or ""
        
        category_field_id = f'customfield_{cfg.jira_category_field_id}'
        response_field_id = f'customfield_{cfg.jira_response_field_id}'
        
        category = jira_service.get_field_value(issue_no, category_field_id) or ""
        response = jira_service.get_field_value(issue_no, response_field_id) or ""
        
        updates.update({
            "summary": jira_issue.fields.summary or "",
            "description": jira_issue.fields.description or "",
            "attachments": attachments,
            "assignee": jira_issue.fields.assignee.emailAddress if jira_issue.fields.assignee else "",
            "reporter": reporter_email,
            "category": category,
            "response": response
        })

    return updates

def update_assignee_node(
    state: CustomerSupportState, config: RunnableConfig
) -> CustomerSupportState:
    """Assign the issue to the bot user in Jira.
    
    This node assigns the Jira issue to the configured bot user.
    
    Args:
        state: Current state containing issue information
        config: Runtime configuration
        
    Returns:
        Updated state (assignee may be updated)
    """
    cfg = Configuration.from_environment()
    
    issue_no = state.get("issue_no")
    if not issue_no:
        # No issue_no - skip assignment
        return {}
    
    jira_service = JiraService(cfg)
    
    try:
        if cfg.jira_assignee_username:
            jira_service.assign_issue(issue_no, cfg.jira_assignee_username)
            return {"assignee": cfg.jira_assignee_username}
    except Exception as e:
        # Don't fail the workflow if assignment fails
        print(f"Warning: Could not assign ticket to support agent: {str(e)}")
    
    return {}

def update_category_node(
    state: CustomerSupportState, config: RunnableConfig
) -> CustomerSupportState:
    """Categorize the issue and update category in Jira.
    
    This node:
    1. Uses LLM to categorize the issue
    2. Updates the category custom field in Jira
    
    Args:
        state: Current state containing issue information
        config: Runtime configuration
        
    Returns:
        Updated state with category set
    """
    issue_no = state.get("issue_no")
    if not issue_no:
        return {}
    
    cfg = Configuration.from_environment()
    bedrock_service = BedrockService(cfg)
    llm = bedrock_service.get_text_llm()
    
    # Get categorization prompt
    prompt = get_categorization_prompt(state)
    
    # Invoke LLM with prompt
    ai_msg = llm.invoke([HumanMessage(content=prompt)])
    
    # Extract category from response
    category = extract_text_content(ai_msg.content)
    
    # Update category in Jira
    if issue_no:
        jira_service = JiraService(cfg)
        try:
            jira_service.set_category(issue_no, category)
        except Exception as e:
            print(f"Warning: Could not update category in Jira: {str(e)}")
    
    return {
        "category": category
    }

def analyze_attachments_node(
    state: CustomerSupportState, config: RunnableConfig
) -> CustomerSupportState:
    """Analyze attachments to extract transaction ID.
    
    This node processes attachments (images) using vision model to extract
    transaction_id from images.
    
    Args:
        state: Current state containing attachments
        config: Runtime configuration
        
    Returns:
        Updated state with transaction_id if found in attachments
    """
    cfg = Configuration.from_environment()
    bedrock_service = BedrockService(cfg)
    
    # Check if we have attachments
    attachments = state.get("attachments", [])
    if not attachments or len(attachments) == 0:
        # No attachments - nothing to analyze
        return {}
    
    # Prepare prompt for extracting transaction_id
    prompt_text = get_analyze_attachments_prompt()
    
    human_messages = [{"type": "text", "text": prompt_text}]
    
    # Use first attachment as image
    attachment_path = attachments[0]
    try:
        image_data = add_image_content(attachment_path)
        human_messages.append(image_data)
    except Exception as e:
        print(f"Warning: Could not process image {attachment_path}: {str(e)}")
        return {}
    
    # Invoke vision model
    vision_llm = bedrock_service.get_vision_llm()
    messages = [HumanMessage(content=human_messages)]
    ai_msg = vision_llm.invoke(messages)
    
    # Extract transaction ID from JSON response
    try:
        # Handle case where content might be a list (structured output) or string
        content = ai_msg.content
        if isinstance(content, list):
            # If content is a list, extract text from the first element
            if content and isinstance(content[0], dict) and "text" in content[0]:
                content_str = content[0]["text"]
            elif content and isinstance(content[0], str):
                content_str = content[0]
            else:
                content_str = str(content)
        else:
            content_str = str(content)
        
        json_obj = extract_json_from_response(content_str)
        transaction_id = json_obj.get("transactionid", "") or None
        
        # Update transaction_id in state
        updates = {}
        if transaction_id and not state.get("transaction_id"):
            updates["transaction_id"] = transaction_id
    except Exception as e:
        print(f"Error extracting information from attachment: {str(e)}")
        updates = {}
    
    return updates

def analyze_summary_node(
    state: CustomerSupportState, config: RunnableConfig
) -> CustomerSupportState:
    """Analyze summary and description to extract order_no or transaction_id, then fetch details.
    
    This node:
    1. Extracts order_no or transaction_id from summary/description
    2. Fetches order or transaction details from database
    3. Stores the details in state for response generation
    
    Args:
        state: Current state containing summary and description
        config: Runtime configuration
        
    Returns:
        Updated state with order_no/transaction_id and fetched details
    """
    cfg = Configuration.from_environment()
    bedrock_service = BedrockService(cfg)
    llm = bedrock_service.get_text_llm()
    
    summary = state.get("summary") or ""
    description = state.get("description") or ""
    combined_text = f"{summary}\n{description}".strip()
    
    if not combined_text:
        return {}
    
    # First, check if transaction_id already exists in state
    transaction_id = state.get("transaction_id", "")
    # Only extract from text if not already in state
    if not transaction_id:
        # Extract transaction ID from text
        prompt = get_extract_transaction_id_prompt()
        messages = [HumanMessage(content=f"{combined_text}\n\n{prompt}")]
        ai_msg = llm.invoke(messages)
        
        try:
            # Handle case where content might be a list (structured output) or string
            content = ai_msg.content
            if isinstance(content, list):
                if content and isinstance(content[0], dict) and "text" in content[0]:
                    content_str = content[0]["text"]
                elif content and isinstance(content[0], str):
                    content_str = content[0]
                else:
                    content_str = str(content)
            else:
                content_str = str(content)
            
            json_obj = extract_json_from_response(content_str)
            transaction_id = json_obj.get("transactionid", "")
        except Exception as e:
            print(f"Error extracting transaction ID: {str(e)}")
            transaction_id = ""
    
    # Then, check if order_no already exists in state
    order_no = state.get("order_no", "")
    # Only extract from text if not already in state
    if not order_no:
        # Extract order number from text
        prompt = get_extract_order_number_prompt()
        messages = [HumanMessage(content=f"{combined_text}\n\n{prompt}")]
        ai_msg = llm.invoke(messages)
        
        try:
            # Handle case where content might be a list (structured output) or string
            content = ai_msg.content
            if isinstance(content, list):
                if content and isinstance(content[0], dict) and "text" in content[0]:
                    content_str = content[0]["text"]
                elif content and isinstance(content[0], str):
                    content_str = content[0]
                else:
                    content_str = str(content)
            else:
                content_str = str(content)
            
            json_obj = extract_json_from_response(content_str)
            order_no = json_obj.get("orderno", "")
        except Exception as e:
            print(f"Error extracting order number: {str(e)}")
            order_no = ""
    
    # Update transaction_id and order_no in state
    updates = {}
    if transaction_id and not state.get("transaction_id"):
        updates["transaction_id"] = transaction_id
    if order_no and not state.get("order_no"):
        updates["order_no"] = order_no
    
    return updates

