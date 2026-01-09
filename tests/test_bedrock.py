"""Tests for BedrockService."""

import base64
import os
from pathlib import Path

from langchain_core.messages import HumanMessage

from agent.configuration import Configuration
from services.bedrock import BedrockService


def test_bedrock_text_llm(config: Configuration) -> dict:
    """Test Bedrock text LLM.
    
    Args:
        config: Configuration object
        
    Returns:
        Dictionary with test results
    """
    result = {}
    try:
        bedrock_service = BedrockService(config)
        text_llm = bedrock_service.get_text_llm()
        
        # Make a simple test call
        test_prompt = "Say 'Hello, Bedrock text service is working!' in one sentence."
        test_response = text_llm.invoke([HumanMessage(content=test_prompt)])
        
        result["status"] = "SUCCESS"
        result["model"] = config.text_model
        result["region"] = os.environ.get("AWS_REGION", "us-west-2")
        result["test_prompt"] = test_prompt
        result["response"] = test_response.content if hasattr(test_response, 'content') else str(test_response)
        result["guardrails_enabled"] = config.guardrail_id is not None
        if config.guardrail_id:
            result["guardrail_id"] = config.guardrail_id
    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)
        result["error_type"] = type(e).__name__
        result["hint"] = "Check AWS credentials, region, and model availability"
    
    return result


def test_bedrock_vision_llm(config: Configuration) -> dict:
    """Test Bedrock vision LLM.
    
    Args:
        config: Configuration object
        
    Returns:
        Dictionary with test results
    """
    result = {}
    try:
        bedrock_service = BedrockService(config)
        vision_llm = bedrock_service.get_vision_llm()
        
        # Use local test image from data/temp folder
        # Get the project root directory (assuming test file is in tests/)
        project_root = Path(__file__).parent.parent
        test_image_path = project_root / "data" / "temp" / "test-vision-llm.jpg"
        
        # Read image from local file and convert to base64 (matching original code format)
        try:
            if not test_image_path.exists():
                raise FileNotFoundError(f"Test image not found at: {test_image_path}")
            
            with open(test_image_path, 'rb') as image_file:
                image_bytes = image_file.read()
                base64_encoded = base64.b64encode(image_bytes).decode('utf-8')
            
            # Determine media type from file extension (matching original code logic)
            file_extension = test_image_path.suffix.lower()
            if file_extension == '.jpg' or file_extension == '.jpeg':
                media_type = "image/jpeg"
            elif file_extension == '.png':
                media_type = "image/png"
            elif file_extension == '.gif':
                media_type = "image/gif"
            else:
                media_type = "image/jpeg"  # Default
            
            # Create message content in the format used by original code
            vision_prompt = "Describe this image in one sentence. What do you see?"
            vision_message_content = [
                {"type": "text", "text": vision_prompt},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64_encoded
                    }
                }
            ]
            
            vision_message = HumanMessage(content=vision_message_content)
            vision_response = vision_llm.invoke([vision_message])
            
            result["status"] = "SUCCESS"
            result["model"] = config.vision_model
            result["region"] = os.environ.get("AWS_REGION", "us-west-2")
            result["test_prompt"] = vision_prompt
            result["test_image_path"] = str(test_image_path)
            result["image_format"] = f"base64 ({media_type})"
            result["response"] = vision_response.content if hasattr(vision_response, 'content') else str(vision_response)
        except FileNotFoundError as file_e:
            result["status"] = "ERROR"
            result["error"] = f"Test image file not found: {str(file_e)}"
            result["error_type"] = type(file_e).__name__
            result["hint"] = f"Ensure test-vision-llm.jpg exists in the data/temp folder at: {test_image_path}"
        except IOError as io_e:
            result["status"] = "ERROR"
            result["error"] = f"Failed to read test image file: {str(io_e)}"
            result["error_type"] = type(io_e).__name__
            result["hint"] = "Check file permissions and ensure the image file is readable"
    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)
        result["error_type"] = type(e).__name__
        result["hint"] = "Check AWS credentials, region, vision model availability, and image format"
    
    return result


def run_all_bedrock_tests(config: Configuration) -> dict:
    """Run all Bedrock service tests.
    
    Args:
        config: Configuration object
        
    Returns:
        Dictionary with all test results
    """
    return {
        "text_llm": test_bedrock_text_llm(config),
        "vision_llm": test_bedrock_vision_llm(config)
    }

