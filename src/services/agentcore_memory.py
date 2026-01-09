"""AgentCore Memory service for storing and retrieving conversation memories.

This service uses AWS Bedrock AgentCore Memory API to:
- Store conversation events (short-term memory)
- List conversation events
- Retrieve semantic memories (long-term memory)

AWS Credentials:
- Credentials are automatically picked up from boto3's credential chain:
  1. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN)
  2. AWS credentials file (~/.aws/credentials)
  3. IAM role (if running on EC2/ECS/Lambda)
- Region is explicitly set from AWS_REGION environment variable (defaults to us-west-2)
"""

import os
from datetime import datetime
from typing import Optional, List, Dict, Any

import boto3
from botocore.exceptions import ClientError

from agent.configuration import Configuration


class AgentCoreMemoryService:
    """Service for interacting with Amazon Bedrock AgentCore Memory.
    
    Provides methods to:
    - Create events (store conversation interactions)
    - List events (retrieve conversation history)
    - Retrieve memories (semantic search for relevant memories)
    
    All operations use boto3, which handles authentication and API calls.
    """
    
    @staticmethod
    def _sanitize_id(identifier: str) -> str:
        """Sanitize an identifier to match AgentCore Memory ID pattern.
        
        AgentCore Memory requires IDs to match: [a-zA-Z0-9][a-zA-Z0-9-_/]*(?::[a-zA-Z0-9-_/]+)*[a-zA-Z0-9-_/]*
        This means:
        - Must start with alphanumeric
        - Can contain alphanumeric, hyphens, underscores, forward slashes
        - Can contain colons in specific patterns
        
        Args:
            identifier: Original identifier (e.g., email address, issue number)
            
        Returns:
            Sanitized identifier that matches the pattern
        """
        if not identifier:
            return identifier
        
        # Replace invalid characters with valid ones
        # Replace @ with -at-, . with -, and ensure it starts with alphanumeric
        sanitized = identifier.replace("@", "-at-").replace(".", "-")
        
        # Remove any other invalid characters (keep only alphanumeric, -, _, /, :)
        import re
        # Keep only valid characters: alphanumeric, hyphen, underscore, forward slash, colon
        sanitized = re.sub(r'[^a-zA-Z0-9\-_/:]', '-', sanitized)
        
        # Ensure it starts with alphanumeric (required by pattern)
        if sanitized and not sanitized[0].isalnum():
            sanitized = 'id-' + sanitized
        
        return sanitized
    
    def __init__(self, config: Configuration):
        """Initialize AgentCore Memory service with configuration.
        
        Args:
            config: Configuration object containing AgentCore Memory settings
            
        Note:
            Requires agentcore_memory_id to be set in configuration or environment variables.
            AWS credentials are automatically picked up by boto3 from the credential chain.
            Region is read from AWS_REGION environment variable (defaults to us-west-2).
        """
        self.config = config
        self.memory_id = config.agentcore_memory_id
        self.aws_region = os.environ.get("AWS_REGION", "us-west-2")
        
        if not self.memory_id:
            raise ValueError(
                "AgentCore Memory ID is not configured. Set AGENTCORE_MEMORY_ID environment variable."
            )
        
        # Initialize boto3 client for Bedrock AgentCore
        # Credentials are automatically picked up by boto3 from the credential chain
        self.client = boto3.client('bedrock-agentcore', region_name=self.aws_region)
    
    def create_event(
        self,
        actor_id: str,
        session_id: str,
        messages: List[Dict[str, str]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create an event in AgentCore Memory (short-term memory).
        
        Stores conversation interactions as events that can be retrieved later.
        
        Args:
            actor_id: Identifier for the actor/user (e.g., customer email)
            session_id: Identifier for the session (e.g., issue number)
            messages: List of message dictionaries with 'content' and 'role' keys.
                     Role can be 'USER', 'ASSISTANT', 'TOOL', etc.
                     Format: [{"content": "text", "role": "USER"}, ...]
            metadata: Optional metadata dictionary to attach to the event
            
        Returns:
            Dictionary containing the event creation response
            
        Raises:
            ClientError: If the AWS API call fails
            ValueError: If required parameters are missing or invalid
            
        Example:
            >>> service = AgentCoreMemoryService(config)
            >>> service.create_event(
            ...     actor_id="customer@example.com",
            ...     session_id="AS-123",
            ...     messages=[
            ...         {"content": "Hello", "role": "USER"},
            ...         {"content": "Hi there!", "role": "ASSISTANT"}
            ...     ]
            ... )
        """
        if not actor_id or not session_id:
            raise ValueError("actor_id and session_id are required")
        
        if not messages or not isinstance(messages, list):
            raise ValueError("messages must be a non-empty list")
        
        # Sanitize actor_id and session_id to match AgentCore Memory ID pattern
        # The pattern requires: [a-zA-Z0-9][a-zA-Z0-9-_/]*(?::[a-zA-Z0-9-_/]+)*[a-zA-Z0-9-_/]*
        sanitized_actor_id = self._sanitize_id(actor_id)
        sanitized_session_id = self._sanitize_id(session_id)
        
        # Validate message format
        for msg in messages:
            if not isinstance(msg, dict) or 'content' not in msg or 'role' not in msg:
                raise ValueError("Each message must be a dict with 'content' and 'role' keys")
        
        # Convert messages to AgentCore Memory payload format
        # The boto3 API expects: payload = [{"conversational": {"content": {"text": "..."}, "role": "USER"}}]
        payload = []
        for msg in messages:
            payload.append({
                "conversational": {
                    "content": {
                        "text": msg["content"]
                    },
                    "role": msg["role"].upper()  # Ensure uppercase (USER, ASSISTANT, TOOL, etc.)
                }
            })
        
        try:
            # Generate event timestamp (required by API)
            # boto3 expects datetime object, which it will serialize to ISO 8601 format
            event_timestamp = datetime.utcnow()
            
            params = {
                'memoryId': self.memory_id,
                'actorId': sanitized_actor_id,  # Use sanitized ID
                'sessionId': sanitized_session_id,  # Use sanitized ID
                'payload': payload,
                'eventTimestamp': event_timestamp  # Required parameter - datetime object
            }
            
            if metadata:
                params['metadata'] = metadata
            
            response = self.client.create_event(**params)
            return response
        except ClientError as e:
            raise RuntimeError(f"Failed to create event in AgentCore Memory: {e}") from e
    
    def list_events(
        self,
        actor_id: str,
        session_id: str,
        max_results: int = 10,
        next_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """List events from AgentCore Memory (short-term memory).
        
        Retrieves conversation events for a specific actor and session.
        
        Args:
            actor_id: Identifier for the actor/user (e.g., customer email)
            session_id: Identifier for the session (e.g., issue number)
            max_results: Maximum number of events to retrieve (default: 10, max: 100)
            next_token: Token for pagination (from previous list_events call)
            
        Returns:
            Dictionary containing:
            - events: List of event dictionaries
            - nextToken: Token for retrieving next page (if more events exist)
            
        Raises:
            ClientError: If the AWS API call fails
            ValueError: If required parameters are missing or invalid
            
        Example:
            >>> service = AgentCoreMemoryService(config)
            >>> result = service.list_events(
            ...     actor_id="customer@example.com",
            ...     session_id="AS-123",
            ...     max_results=20
            ... )
            >>> events = result.get('events', [])
        """
        if not actor_id or not session_id:
            raise ValueError("actor_id and session_id are required")
        
        if max_results < 1 or max_results > 100:
            raise ValueError("max_results must be between 1 and 100")
        
        try:
            params = {
                'memoryId': self.memory_id,
                'actorId': actor_id,
                'sessionId': session_id,
                'maxResults': max_results
            }
            
            if next_token:
                params['nextToken'] = next_token
            
            response = self.client.list_events(**params)
            return response
        except ClientError as e:
            raise RuntimeError(f"Failed to list events from AgentCore Memory: {e}") from e
    
    def retrieve_memories(
        self,
        query: str,
        namespace: Optional[str] = None,
        max_results: int = 10,
        next_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Retrieve memories from AgentCore Memory using semantic search (long-term memory).
        
        Performs semantic search to find relevant memories based on a query.
        
        Args:
            query: Semantic query string to search for relevant memories
            namespace: Optional namespace to filter memories (default: None for all namespaces)
            max_results: Maximum number of memories to retrieve (default: 10, max: 100)
            next_token: Token for pagination (from previous retrieve_memories call)
            
        Returns:
            Dictionary containing:
            - memoryRecords: List of memory record dictionaries with relevance scores
            - nextToken: Token for retrieving next page (if more memories exist)
            
        Raises:
            ClientError: If the AWS API call fails
            ValueError: If required parameters are missing or invalid
            
        Example:
            >>> service = AgentCoreMemoryService(config)
            >>> result = service.retrieve_memories(
            ...     query="customer refund request",
            ...     namespace="customer-support",
            ...     max_results=5
            ... )
            >>> memories = result.get('memoryRecords', [])
        """
        if not query or not isinstance(query, str):
            raise ValueError("query must be a non-empty string")
        
        if max_results < 1 or max_results > 100:
            raise ValueError("max_results must be between 1 and 100")
        
        try:
            params = {
                'memoryId': self.memory_id,
                'query': query,
                'maxResults': max_results
            }
            
            if namespace:
                params['namespace'] = namespace
            
            if next_token:
                params['nextToken'] = next_token
            
            response = self.client.retrieve_memories(**params)
            return response
        except ClientError as e:
            raise RuntimeError(f"Failed to retrieve memories from AgentCore Memory: {e}") from e
