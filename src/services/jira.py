"""Jira service for ticket management and integration.

This service uses the JIRA Python package to interact with Jira.
For ADF (rich text) fields, we use the JIRA package's authenticated session
to make REST API v3 calls directly, as the JIRA package defaults to API v2
and doesn't natively support ADF format for custom fields.

Note: The JIRA Python package (jira>=3.10.0) doesn't have native ADF support
for custom fields. While it can handle ADF for comments and descriptions,
custom fields with ADF format require API v3, which the package doesn't use
by default. Therefore, we use the package's authenticated session to make
API v3 calls directly for ADF fields.
"""

from pathlib import Path
from typing import Optional

from jira import JIRA
from jira.resources import Issue, Attachment

from agent.configuration import Configuration


class JiraService:
    """Service for interacting with Jira tickets and attachments.
    
    Provides methods to:
    - Fetch ticket information
    - Download attachments
    - Update custom fields (category, response)
    - Assign tickets
    
    All operations use the JIRA Python package, which handles
    API versioning and authentication internally.
    """
    
    def __init__(self, config: Configuration):
        """Initialize Jira service with configuration.
        
        Args:
            config: Configuration object containing Jira settings
            
        Note:
            Requires jira_api_username, jira_api_token, and jira_instance_url
            to be set in configuration or environment variables.
        """
        self.config = config
        self.jira_api_username = config.jira_api_username
        self.jira_api_token = config.jira_api_token
        self.jira_instance_url = config.jira_instance_url
        self.jira_project_key = config.jira_project_key
        self.jira_assignee_username = config.jira_assignee_username
        self.jira_category_field_id = config.jira_category_field_id
        self.jira_response_field_id = config.jira_response_field_id
        
        # Setup temp directory for downloads
        project_root = Path(__file__).parent.parent.parent
        self.temp_path = project_root / "tmp-files"
        self.temp_path.mkdir(parents=True, exist_ok=True)
    
    def _get_client(self) -> JIRA:
        """Create and return a JIRA client object.
        
        Returns:
            JIRA client instance configured with credentials
            
        Raises:
            ValueError: If required credentials are not configured
        """
        if not self.jira_api_username or not self.jira_api_token or not self.jira_instance_url:
            raise ValueError(
                "Jira credentials not configured. "
                "Set jira_api_username, jira_api_token, and jira_instance_url in configuration."
            )
        
        options = {'server': self.jira_instance_url}
        jira = JIRA(options, basic_auth=(self.jira_api_username, self.jira_api_token))
        return jira
    
    def fetch_issue(self, issue_key: str) -> Optional[Issue]:
        """Fetch a Jira issue by key.
        
        Args:
            issue_key: Jira issue key (e.g., "AS-5")
            
        Returns:
            Jira Issue object if found, None otherwise
        """
        if not issue_key or len(issue_key) == 0:
            return None
        
        try:
            jira = self._get_client()
            issue = jira.issue(issue_key)
            return issue
        except Exception as e:
            print(f"Error fetching issue {issue_key}: {str(e)}")
            return None
    
    def download_attachment_file(self, attachment: Attachment, issue_key: str) -> str:
        """Download an attachment from a Jira issue and save it locally.
        
        Uses the JIRA package's session for authentication.
        
        Args:
            attachment: Jira Attachment object
            issue_key: Issue key for logging purposes
            
        Returns:
            Full path to the downloaded file
            
        Raises:
            Exception: If download fails
        """
        try:
            jira = self._get_client()
            
            # Get attachment attributes safely
            # JIRA package Attachment object attributes may vary
            attachment_url = getattr(attachment, 'content', getattr(attachment, 'self', None))
            attachment_filename = getattr(attachment, 'filename', getattr(attachment, 'name', 'attachment'))
            
            if not attachment_url:
                raise ValueError("Could not find attachment URL in attachment object")
            
            # Use the JIRA client's session to download the attachment
            # This ensures proper authentication and handles API versioning
            # Note: Don't pass timeout as it may conflict with session defaults
            response = jira._session.get(attachment_url, stream=True)
            response.raise_for_status()
            
            # Create filename with issue key prefix to avoid conflicts
            filename = f"{issue_key}-{attachment_filename}"
            file_path = self.temp_path / filename
            
            with open(file_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=1024):
                    file.write(chunk)
            
            print(f"Downloaded attachment: {file_path} (issue: {issue_key})")
            return str(file_path)
        except Exception as e:
            # Try to get filename for error message
            attachment_filename = getattr(attachment, 'filename', getattr(attachment, 'name', 'unknown'))
            error_msg = f"Error downloading attachment {attachment_filename}: {str(e)}"
            print(f"ERROR: {error_msg}")
            raise Exception(error_msg) from e
    
    def update_field(self, issue_key: str, field_name: str, value) -> None:
        """Update a custom field value in a Jira issue.
        
        For plain text fields, uses the JIRA package's update method.
        For Paragraph (rich text) fields with ADF format, uses REST API v3 directly
        as the JIRA package doesn't fully support ADF format.
        
        Args:
            issue_key: Jira issue key (e.g., "AS-5")
            field_name: Custom field name (e.g., "customfield_10071")
            value: Value to set (string for text fields, will be converted to ADF for rich text)
            
        Raises:
            ValueError: If credentials are not configured
            Exception: If update fails
        """
        if not self.jira_api_username or not self.jira_api_token or not self.jira_instance_url:
            raise ValueError("Jira credentials not configured for field update")
        
        # Check if this is the Response field (Paragraph/rich text field)
        response_field_id = f'customfield_{self.jira_response_field_id}'
        is_adf_field = field_name == response_field_id
        
        if is_adf_field:
            # Convert plain text to ADF format for Paragraph fields
            if isinstance(value, str):
                value = self._convert_text_to_adf(value)
                print(f"Converted text to ADF format for Paragraph field")
            
            # For ADF fields, use REST API v3 via JIRA package's session
            # The JIRA package defaults to API v2 and doesn't support ADF format,
            # so we use its authenticated session to make API v3 calls directly
            try:
                jira = self._get_client()
                base_url = self.jira_instance_url.rstrip('/') + '/'
                url = f"{base_url}rest/api/3/issue/{issue_key}"
                
                headers = {
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "fields": {
                        field_name: value
                    }
                }
                
                print(f"Updating ADF field {field_name} for issue {issue_key} via REST API v3 (using JIRA package session)")
                # Use JIRA package's authenticated session for API v3 call
                response = jira._session.put(url, json=payload, headers=headers)
                
                if response.status_code != 204:  # 204 is success for PUT
                    error_msg = f"Failed to update ADF field {field_name}: {response.status_code} - {response.text}"
                    print(f"ERROR: {error_msg}")
                    response.raise_for_status()
                else:
                    print(f"Successfully updated ADF field {field_name} for issue {issue_key}")
            except Exception as e:
                error_msg = f"Error updating ADF field {field_name} for issue {issue_key}: {str(e)}"
                print(f"ERROR: {error_msg}")
                raise Exception(error_msg) from e
        else:
            # For plain text fields, use JIRA package's update method
            try:
                jira = self._get_client()
                issue = jira.issue(issue_key)
                issue.update(fields={field_name: value})
                print(f"Successfully updated {field_name} for issue {issue_key}")
            except Exception as e:
                error_msg = f"Error updating field {field_name} for issue {issue_key}: {str(e)}"
                print(f"ERROR: {error_msg}")
                raise Exception(error_msg) from e
    
    def set_category(self, issue_key: str, category: str) -> None:
        """Set the category custom field for an issue.
        
        Args:
            issue_key: Jira issue key (e.g., "AS-5")
            category: Category value (e.g., "Transaction", "Delivery", "Refunds", "Other")
        """
        field_name = f'customfield_{self.jira_category_field_id}'
        self.update_field(issue_key, field_name, category)
    
    def set_response(self, issue_key: str, response_text: str) -> None:
        """Set the response custom field for an issue.
        
        Automatically converts plain text to ADF format for rich text fields.
        
        Args:
            issue_key: Jira issue key (e.g., "AS-5")
            response_text: Response text (will be converted to ADF format automatically)
        """
        field_name = f'customfield_{self.jira_response_field_id}'
        self.update_field(issue_key, field_name, response_text)
    
    def assign_issue(self, issue_key: str, assignee: Optional[str] = None) -> None:
        """Assign a Jira issue to a user.
        
        Args:
            issue_key: Jira issue key (e.g., "AS-5")
            assignee: Username/email to assign to. If None, uses jira_assignee_username from config.
            
        Raises:
            ValueError: If no assignee is provided and jira_assignee_username is not configured
            Exception: If assignment fails
        """
        if assignee is None:
            assignee = self.jira_assignee_username
        
        if not assignee:
            raise ValueError("No assignee provided and jira_assignee_username not configured")
        
        try:
            jira = self._get_client()
            jira.assign_issue(issue_key, assignee)
            print(f"Assigned issue {issue_key} to {assignee}")
        except Exception as e:
            error_msg = f"Error assigning issue {issue_key} to {assignee}: {str(e)}"
            print(f"ERROR: {error_msg}")
            raise Exception(error_msg) from e
    
    def get_field_value(self, issue_key: str, field_name: str) -> Optional[any]:
        """Retrieve the current value of a custom field from a Jira issue.
        
        Uses the JIRA package to access issue fields directly.
        
        Args:
            issue_key: Jira issue key (e.g., "AS-5")
            field_name: Custom field name (e.g., "customfield_10071")
            
        Returns:
            Field value if found, None otherwise
        """
        try:
            jira = self._get_client()
            issue = jira.issue(issue_key)
            
            # Access field value through issue.fields
            # The JIRA package handles field name mapping
            field_value = getattr(issue.fields, field_name, None)
            return field_value
        except Exception as e:
            print(f"Error retrieving field value for {issue_key}: {str(e)}")
            return None
    
    def _convert_text_to_adf(self, text: str) -> dict:
        """Convert plain text to Atlassian Document Format (ADF).
        
        ADF is required for Paragraph (rich text) fields in Jira.
        
        Args:
            text: Plain text string to convert
            
        Returns:
            dict: ADF document structure
        """
        # Split text into paragraphs (by newlines)
        paragraphs = text.split('\n')
        
        # Create ADF content with paragraphs
        content = []
        for para_text in paragraphs:
            if para_text.strip():  # Only add non-empty paragraphs
                content.append({
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": para_text.strip()
                        }
                    ]
                })
        
        # If no content, add an empty paragraph
        if not content:
            content.append({
                "type": "paragraph",
                "content": []
            })
        
        # Return ADF document structure
        return {
            "version": 1,
            "type": "doc",
            "content": content
        }
