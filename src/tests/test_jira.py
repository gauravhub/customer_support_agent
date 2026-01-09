"""Tests for JiraService."""

from agent.configuration import Configuration
from services.jira import JiraService


def test_jira_service(config: Configuration, test_issue_key: str = "AS-4") -> dict:
    """Test JiraService with a sample issue.
    
    Args:
        config: Configuration object
        test_issue_key: Jira issue key to test with (default: "AS-4")
        
    Returns:
        Dictionary with test results
    """
    result = {}
    issue = None  # Initialize issue variable
    
    try:
        jira_service = JiraService(config)
        
        # Test 1: Fetch issue
        result["fetch_issue"] = {}
        try:
            issue = jira_service.fetch_issue(test_issue_key)
            if issue:
                result["fetch_issue"]["status"] = "SUCCESS"
                result["fetch_issue"]["issue_key"] = issue.key
                result["fetch_issue"]["summary"] = issue.fields.summary
                result["fetch_issue"]["description"] = issue.fields.description[:200] + "..." if issue.fields.description and len(issue.fields.description) > 200 else (issue.fields.description or "No description")
                result["fetch_issue"]["status_name"] = issue.fields.status.name if issue.fields.status else "Unknown"
                result["fetch_issue"]["assignee"] = issue.fields.assignee.emailAddress if issue.fields.assignee else "Unassigned"
                result["fetch_issue"]["attachment_count"] = len(issue.fields.attachment) if issue.fields.attachment else 0
            else:
                result["fetch_issue"]["status"] = "ERROR"
                result["fetch_issue"]["error"] = f"Issue {test_issue_key} not found or could not be fetched"
        except Exception as e:
            result["fetch_issue"]["status"] = "ERROR"
            result["fetch_issue"]["error"] = str(e)
            result["fetch_issue"]["error_type"] = type(e).__name__
        
        # Test 2: Get field values (if issue was fetched successfully)
        if issue:
            result["get_field_values"] = {}
            try:
                category_field = f'customfield_{config.jira_category_field_id}'
                response_field = f'customfield_{config.jira_response_field_id}'
                
                category_value = jira_service.get_field_value(test_issue_key, category_field)
                response_value = jira_service.get_field_value(test_issue_key, response_field)
                
                result["get_field_values"]["status"] = "SUCCESS"
                result["get_field_values"]["category_field"] = category_field
                result["get_field_values"]["category_value"] = str(category_value) if category_value else "Not set"
                result["get_field_values"]["response_field"] = response_field
                # Truncate response if too long
                if response_value:
                    if isinstance(response_value, dict):
                        # ADF format - show a summary
                        result["get_field_values"]["response_value"] = f"ADF format (dict with {len(response_value.get('content', []))} paragraphs)"
                    else:
                        resp_str = str(response_value)
                        result["get_field_values"]["response_value"] = resp_str[:200] + "..." if len(resp_str) > 200 else resp_str
                else:
                    result["get_field_values"]["response_value"] = "Not set"
            except Exception as e:
                result["get_field_values"]["status"] = "ERROR"
                result["get_field_values"]["error"] = str(e)
                result["get_field_values"]["error_type"] = type(e).__name__
            
            # Test 3: Download attachments (if any exist)
            if issue.fields.attachment and len(issue.fields.attachment) > 0:
                result["download_attachments"] = {}
                try:
                    downloaded_files = []
                    for attachment in issue.fields.attachment[:3]:  # Test up to 3 attachments
                        try:
                            file_path = jira_service.download_attachment_file(attachment, test_issue_key)
                            
                            # Get attachment attributes safely (JIRA package uses different attribute names)
                            filename = getattr(attachment, 'filename', getattr(attachment, 'name', 'unknown'))
                            size = getattr(attachment, 'size', None)
                            # Try different possible attribute names for content type
                            content_type = getattr(attachment, 'mimeType', 
                                                 getattr(attachment, 'contentType', 
                                                        getattr(attachment, 'mime_type', 'unknown')))
                            
                            downloaded_files.append({
                                "filename": filename,
                                "size": size,
                                "content_type": content_type,
                                "local_path": file_path,
                                "status": "SUCCESS"
                            })
                        except Exception as e:
                            # Get filename safely even if download fails
                            filename = getattr(attachment, 'filename', getattr(attachment, 'name', 'unknown'))
                            downloaded_files.append({
                                "filename": filename,
                                "status": "ERROR",
                                "error": str(e)
                            })
                    
                    result["download_attachments"]["status"] = "SUCCESS"
                    result["download_attachments"]["total_attachments"] = len(issue.fields.attachment)
                    result["download_attachments"]["tested"] = len(downloaded_files)
                    result["download_attachments"]["results"] = downloaded_files
                except Exception as e:
                    result["download_attachments"]["status"] = "ERROR"
                    result["download_attachments"]["error"] = str(e)
                    result["download_attachments"]["error_type"] = type(e).__name__
            else:
                result["download_attachments"] = {
                    "status": "SKIPPED",
                    "reason": "No attachments found on issue"
                }
            
            # Test 4: Update field values
            result["update_fields"] = {}
            
            # Test 4a: Update category
            try:
                test_category = "Other"  # Test category value
                jira_service.set_category(test_issue_key, test_category)
                # Verify the update
                category_field = f'customfield_{config.jira_category_field_id}'
                updated_category = jira_service.get_field_value(test_issue_key, category_field)
                result["update_fields"]["set_category"] = {
                    "status": "SUCCESS",
                    "test_value": test_category,
                    "verified_value": str(updated_category) if updated_category else "Not set"
                }
            except Exception as e:
                result["update_fields"]["set_category"] = {
                    "status": "ERROR",
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            
            # Test 4b: Update response
            try:
                test_response = "This is a test response from the customer support agent. The issue has been reviewed and processed."
                jira_service.set_response(test_issue_key, test_response)
                # Verify the update (response is in ADF format, so we check if it was set)
                response_field = f'customfield_{config.jira_response_field_id}'
                updated_response = jira_service.get_field_value(test_issue_key, response_field)
                if updated_response:
                    if isinstance(updated_response, dict):
                        # ADF format - extract text content
                        content_paragraphs = updated_response.get('content', [])
                        text_content = " ".join([
                            para.get('content', [{}])[0].get('text', '')
                            for para in content_paragraphs
                            if para.get('type') == 'paragraph' and para.get('content')
                        ])
                        result["update_fields"]["set_response"] = {
                            "status": "SUCCESS",
                            "test_value": test_response[:100] + "..." if len(test_response) > 100 else test_response,
                            "verified_value": text_content[:100] + "..." if len(text_content) > 100 else text_content,
                            "format": "ADF"
                        }
                    else:
                        result["update_fields"]["set_response"] = {
                            "status": "SUCCESS",
                            "test_value": test_response[:100] + "..." if len(test_response) > 100 else test_response,
                            "verified_value": str(updated_response)[:100] + "..." if len(str(updated_response)) > 100 else str(updated_response)
                        }
                else:
                    result["update_fields"]["set_response"] = {
                        "status": "WARNING",
                        "message": "Update appeared successful but could not verify value"
                    }
            except Exception as e:
                result["update_fields"]["set_response"] = {
                    "status": "ERROR",
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            
            # Test 4c: Assign issue
            try:
                if config.jira_assignee_username:
                    # Get current assignee before update
                    current_assignee = issue.fields.assignee.emailAddress if issue.fields.assignee else "Unassigned"
                    jira_service.assign_issue(test_issue_key, config.jira_assignee_username)
                    # Fetch issue again to verify assignment
                    updated_issue = jira_service.fetch_issue(test_issue_key)
                    new_assignee = updated_issue.fields.assignee.emailAddress if updated_issue and updated_issue.fields.assignee else "Unassigned"
                    result["update_fields"]["assign_issue"] = {
                        "status": "SUCCESS",
                        "previous_assignee": current_assignee,
                        "new_assignee": new_assignee,
                        "target_assignee": config.jira_assignee_username
                    }
                else:
                    result["update_fields"]["assign_issue"] = {
                        "status": "SKIPPED",
                        "reason": "jira_assignee_username not configured"
                    }
            except Exception as e:
                result["update_fields"]["assign_issue"] = {
                    "status": "ERROR",
                    "error": str(e),
                    "error_type": type(e).__name__
                }
        
        result["overall_status"] = "SUCCESS"
        result["test_issue_key"] = test_issue_key
        result["note"] = "These tests perform actual updates on the Jira issue. Review the results carefully."
        
    except Exception as e:
        result["overall_status"] = "ERROR"
        result["error"] = str(e)
        result["error_type"] = type(e).__name__
        result["hint"] = "Check Jira credentials (jira_api_username, jira_api_token, jira_instance_url) and network connectivity"
    
    return result

