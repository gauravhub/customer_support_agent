"""Utility functions for the customer support agent.

This module contains helper functions used throughout the workflow.
"""

import base64
import re
from pathlib import Path
from typing import Any, Dict

from agent.configuration import Configuration
from services.database import DatabaseService


def clean_json_string(json_string: str) -> str:
    """Clean JSON string from LLM response by removing markdown code blocks.
    
    Removes triple backticks and 'json' identifier that LLMs often add
    when returning JSON responses.
    
    Args:
        json_string: Raw JSON string from LLM (may include markdown formatting)
        
    Returns:
        Cleaned JSON string ready for parsing
        
    Example:
        Input: "```json\\n{\"key\": \"value\"}\\n```"
        Output: "{\"key\": \"value\"}"
    """
    # Pattern to match ```json\n...\n``` blocks
    pattern = r'```json\n(.*?)```'
    cleaned_string = re.search(pattern, json_string, flags=re.DOTALL)
    
    if cleaned_string:
        return cleaned_string.group(1).strip()
    return json_string.strip()


def get_image_format(image_path: str) -> str:
    """Get image format/MIME type from file extension.
    
    Args:
        image_path: Path to image file
        
    Returns:
        Image format string (e.g., 'jpeg', 'png', 'gif')
        
    Note:
        Converts 'jpg' to 'jpeg' for MIME type consistency
    """
    file_extension = Path(image_path).suffix.lower().lstrip('.')
    if file_extension == 'jpg':
        file_extension = 'jpeg'
    return file_extension


def add_image_content(image_path: str) -> Dict[str, Any]:
    """Read image file and convert to base64 format for vision model input.
    
    Args:
        image_path: Path to image file
        
    Returns:
        Dictionary with image data in format expected by vision models:
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": "<base64_encoded_data>"
            }
        }
        
    Raises:
        FileNotFoundError: If image file doesn't exist
        IOError: If image file cannot be read
    """
    image_path_obj = Path(image_path)
    if not image_path_obj.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")
    
    with open(image_path, 'rb') as image_file:
        image_bytes = image_file.read()
        base64_encoded = base64.b64encode(image_bytes).decode('utf-8')
    
    image_format = get_image_format(image_path)
    media_type = f"image/{image_format}"
    
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64_encoded
        }
    }


def extract_json_from_response(response_content: str) -> Dict[str, Any]:
    """Extract and parse JSON from LLM response.
    
    Handles cases where LLM wraps JSON in markdown code blocks or adds
    extra text before/after the JSON.
    
    Args:
        response_content: Raw response content from LLM
        
    Returns:
        Parsed JSON as dictionary
        
    Raises:
        ValueError: If no valid JSON can be extracted
        json.JSONDecodeError: If extracted string is not valid JSON
    """
    import json
    
    # First, try to clean the string
    cleaned = clean_json_string(response_content)
    
    # Try to parse directly
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # If that fails, try to find JSON object in the string
        # Look for {...} pattern
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        # If still no luck, raise error
        raise ValueError(f"Could not extract valid JSON from response: {response_content[:200]}")


def initialize_database() -> None:
    """Initialize the customer support database.
    
    This function loads sample data from JSON files into the SQLite database.
    It should be called when the graph is loaded to ensure the database is ready.
    
    The database path and other settings are read from environment variables/defaults.
    
    Note:
        This function is idempotent - it can be called multiple times safely.
        If the database is already initialized, it will be re-initialized with
        fresh data from the JSON files.
    """
    try:
        # Create configuration from environment variables/defaults
        # Configuration() will automatically use defaults and load from env vars
        config = Configuration()
        
        # Create database service and initialize
        db_service = DatabaseService(config)
        init_results = db_service.initialize()
        
        # Log initialization results
        success_count = sum(1 for r in init_results.values() if r.get("status") == "SUCCESS")
        total_tables = len(init_results)
        
        print(f"Database initialization: {success_count}/{total_tables} tables imported successfully (path: {config.database_path})")
        
        # Print any errors
        for table_name, result in init_results.items():
            if result.get("status") == "ERROR":
                print(f"Warning: Failed to import {table_name}: {result.get('error')}")
    except Exception as e:
        print(f"Warning: Database initialization failed: {str(e)}")
        # Don't raise - allow graph to load even if database init fails
        # The database will be initialized when first accessed


def extract_text_content(content) -> str:
    """Extract text content from LLM response which might be string or list.
    
    Args:
        content: Content from LLM response (can be string or list)
        
    Returns:
        Extracted text as string
    """
    if isinstance(content, list):
        # If content is a list, extract text from the first element
        if content and isinstance(content[0], dict) and "text" in content[0]:
            return content[0]["text"].strip()
        elif content and isinstance(content[0], str):
            return content[0].strip()
        else:
            return str(content).strip()
    else:
        return str(content).strip()

