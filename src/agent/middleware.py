"""Custom middleware for AgentCore Memory integration.

This module provides middleware hooks to automatically store conversation events
in AgentCore Memory after each model call.
"""

import logging
from typing import Any, Optional
from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
    BaseMessage,
)
from langgraph.runtime import Runtime

from agent.configuration import Configuration
from services.agentcore_memory import AgentCoreMemoryService

# Set up logger for this module
logger = logging.getLogger(__name__)


class AgentCoreMemoryMiddleware(AgentMiddleware):
    """Middleware to automatically store conversation events in AgentCore Memory.
    
    This middleware intercepts model responses and stores them as events in
    AgentCore Memory for short-term memory persistence.
    
    The middleware:
    - Extracts messages from the agent state
    - Converts them to AgentCore Memory format
    - Stores them using the AgentCore Memory service
    - Uses actor_id (sanitized username/email) and thread_id (LangGraph thread ID) as session_id
    - These values are typically passed via config.configurable from the UI
    """
    
    def __init__(self, config: Configuration, actor_id: Optional[str] = None, session_id: Optional[str] = None):
        """Initialize the middleware with configuration.
        
        Args:
            config: Configuration object containing AgentCore Memory settings
            actor_id: Optional actor ID (sanitized username/email from UI). 
                     Typically passed via config.configurable.actor_id.
            session_id: Optional session ID (LangGraph thread_id). 
                       Typically passed via config.configurable.thread_id.
                       This should be the LangGraph thread ID, not issue_no.
        """
        super().__init__()
        self.config = config
        self.memory_service = None
        self.actor_id = actor_id
        self.session_id = session_id
        
        logger.info("Initializing AgentCoreMemoryMiddleware...")
        if actor_id or session_id:
            logger.info(f"📋 Middleware initialized with actor_id: {actor_id}, session_id: {session_id}")
        
        # Initialize memory service if memory_id is configured
        if config.agentcore_memory_id:
            try:
                logger.info(f"AgentCore Memory ID configured: {config.agentcore_memory_id}")
                self.memory_service = AgentCoreMemoryService(config)
                logger.info("✅ AgentCore Memory service initialized successfully")
            except Exception as e:
                logger.warning(f"⚠️ Could not initialize AgentCore Memory service: {e}")
                logger.warning("Middleware will continue without memory storage.")
        else:
            logger.warning("⚠️ AgentCore Memory ID not configured. Middleware will skip memory storage.")
    
    def after_model(
        self, state: AgentState, runtime: Runtime
    ) -> Optional[dict[str, Any]]:
        """Store conversation events in AgentCore Memory after each model call.
        
        This hook is called after each model response. It extracts the latest
        messages from the state and stores them in AgentCore Memory.
        
        Args:
            state: Current agent state containing messages
            runtime: Runtime context for the agent execution
            
        Returns:
            None (does not modify state)
        """
        logger.info("🔔 after_model hook called")
        
        # Log state structure for debugging
        state_keys = list(state.keys()) if hasattr(state, 'keys') else []
        logger.info(f"🔍 State keys available: {state_keys}")
        logger.info(f"🔍 State type: {type(state)}")
        
        # Skip if memory service is not initialized
        if not self.memory_service:
            logger.info("⏭️ Skipping: Memory service not initialized")
            return None
        
        try:
            # Extract actor_id and session_id
            # Priority: 1) Instance variables (passed during init), 2) Try from state, 3) Try from runtime
            actor_id = self.actor_id
            session_id = self.session_id
            
            # If not set during init, try to get from runtime config (preferred) or state (fallback)
            # Priority: 1) Instance variables (from config.configurable), 2) Runtime config, 3) State (legacy)
            if not actor_id or not session_id:
                try:
                    # Try to get config from runtime
                    if hasattr(runtime, 'config') and runtime.config:
                        runtime_config = runtime.config if isinstance(runtime.config, dict) else getattr(runtime.config, 'configurable', {})
                        if isinstance(runtime_config, dict):
                            configurable = runtime_config.get("configurable", {})
                            if not actor_id and configurable.get("actor_id"):
                                actor_id = configurable.get("actor_id")
                                logger.info(f"📋 Retrieved actor_id from runtime config: {actor_id}")
                            if not session_id and configurable.get("thread_id"):
                                session_id = configurable.get("thread_id")
                                logger.info(f"📋 Retrieved session_id (thread_id) from runtime config: {session_id}")
                except Exception as e:
                    logger.debug(f"Could not access runtime config: {e}")
            
            # Fallback: Try to get from state (legacy support, but not recommended)
            if not actor_id:
                actor_id = state.get("customer_email") if hasattr(state, 'get') else None
                if not actor_id and isinstance(state, dict):
                    actor_id = state.get("customer_email")
            
            if not session_id:
                # Legacy: try issue_no as fallback, but prefer thread_id from config
                session_id = state.get("issue_no") if hasattr(state, 'get') else None
                if not session_id and isinstance(state, dict):
                    session_id = state.get("issue_no")
                if session_id:
                    logger.warning(f"⚠️ Using issue_no as session_id (legacy fallback). Prefer thread_id from config.configurable.")
            
            logger.info(f"📋 Final state extraction - actor_id: {actor_id}, session_id: {session_id}")
            
            # Skip if we don't have required identifiers
            if not actor_id or not session_id:
                logger.info(f"⏭️ Skipping: Missing required identifiers (actor_id: {actor_id}, session_id: {session_id})")
                return None
            
            # Get messages from state
            messages = state.get("messages", [])
            logger.info(f"📨 Found {len(messages)} messages in state")
            
            if not messages:
                logger.info("⏭️ Skipping: No messages in state")
                return None
            
            # Log message types for debugging (last 10 messages)
            message_types = [type(msg).__name__ for msg in messages[-10:]]
            logger.info(f"🔍 Last 10 message types: {message_types}")
            
            # Extract the latest conversation turn
            # In a React agent, after_model is called after each model invocation.
            # The messages we see are typically AIMessage and ToolMessage from the current agent execution.
            # We should capture all AIMessage and ToolMessage from the current turn.
            conversation_messages = []
            
            # Strategy: Find the last HumanMessage to identify the start of the current turn.
            # If no HumanMessage, capture recent AIMessage and ToolMessage (the current agent execution).
            last_user_idx = -1
            for i in range(len(messages) - 1, -1, -1):
                if isinstance(messages[i], HumanMessage):
                    last_user_idx = i
                    logger.info(f"🔍 Found HumanMessage at index: {i}")
                    break
            
            # Determine which messages to process
            if last_user_idx >= 0:
                # Collect all messages from the last user message onwards
                # This includes the user message, AI responses, and tool messages
                messages_to_process = messages[last_user_idx:]
                logger.info(f"📝 Processing {len(messages_to_process)} messages starting from HumanMessage at index {last_user_idx}")
            else:
                # No HumanMessage found - this is common in React agents where after_model
                # is called after tool calls or intermediate AI responses.
                # Capture the last 10 messages (should cover the current agent execution turn)
                # These will be AIMessage and ToolMessage from the agent's current execution
                messages_to_process = messages[-10:] if len(messages) >= 10 else messages
                logger.info(f"📝 No HumanMessage found. Processing last {len(messages_to_process)} messages (current agent turn: AIMessage + ToolMessage)")
            
            # Convert messages to AgentCore Memory format
            for idx, msg in enumerate(messages_to_process):
                logger.info(f"  🔍 Processing message {idx}: type={type(msg).__name__}, has_content={hasattr(msg, 'content')}")
                # Convert LangChain messages to AgentCore Memory format
                role, content = self._convert_message_to_memory_format(msg)
                if role and content:
                    conversation_messages.append({
                        "content": content,
                        "role": role
                    })
                    logger.info(f"  ✓ Converted message {idx}: {role} ({len(content)} chars)")
                else:
                    logger.info(f"  ✗ Skipped message {idx}: Could not convert (type: {type(msg).__name__}, role: {role}, content: {bool(content)})")
                    # Log more details about why conversion failed
                    if hasattr(msg, 'content'):
                        logger.info(f"    Message content type: {type(msg.content)}, value: {str(msg.content)[:100] if msg.content else 'None'}")
            
            logger.info(f"📦 Prepared {len(conversation_messages)} messages for storage")
            
            # Only store if we have messages to store
            if conversation_messages:
                logger.info(f"💾 Storing event in AgentCore Memory - actor_id: {actor_id}, session_id: {session_id}, messages: {len(conversation_messages)}")
                
                # Store the event in AgentCore Memory
                result = self.memory_service.create_event(
                    actor_id=actor_id,
                    session_id=session_id,
                    messages=conversation_messages
                )
                
                # Extract event_id from response
                # According to AWS API docs, response structure is: {"event": {"eventId": "...", ...}}
                event_id = None
                if isinstance(result, dict):
                    # The API returns: {"event": {"eventId": "...", ...}}
                    event_obj = result.get("event", {})
                    if isinstance(event_obj, dict):
                        event_id = event_obj.get("eventId")
                    # Fallback: try direct access (in case response structure differs)
                    if not event_id:
                        event_id = result.get("eventId")
                else:
                    logger.debug(f"🔍 create_event response type: {type(result)}, value: {result}")
                
                if event_id:
                    logger.info(f"✅ Successfully stored event in AgentCore Memory - event_id: {event_id}")
                else:
                    # Log full response for debugging
                    logger.debug(f"🔍 create_event response keys: {list(result.keys()) if isinstance(result, dict) else 'N/A'}")
                    logger.debug(f"🔍 create_event full response: {result}")
                    logger.info(f"✅ Successfully stored event in AgentCore Memory - event_id: None (could not extract from response)")
            else:
                logger.info("⏭️ Skipping: No conversation messages to store")
        
        except Exception as e:
            # Log error but don't fail the agent execution
            logger.error(f"❌ Failed to store event in AgentCore Memory: {e}", exc_info=True)
        
        return None
    
    def _convert_message_to_memory_format(
        self, message: BaseMessage
    ) -> tuple[Optional[str], Optional[str]]:
        """Convert a LangChain message to AgentCore Memory format.
        
        Args:
            message: LangChain message object
            
        Returns:
            Tuple of (role, content) or (None, None) if message type is not supported
        """
        # Extract text content from message
        content = None
        if hasattr(message, "content"):
            if isinstance(message.content, str):
                content = message.content
            elif isinstance(message.content, list):
                # Handle content blocks (e.g., text blocks in structured content)
                text_parts = []
                for block in message.content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        text_parts.append(block)
                content = " ".join(text_parts) if text_parts else None
        
        if not content:
            logger.debug(f"  ⚠️ Message has no extractable content (type: {type(message).__name__})")
            return None, None
        
        # Map LangChain message types to AgentCore Memory roles
        # In React agents, we primarily see AIMessage and ToolMessage during agent execution
        if isinstance(message, HumanMessage):
            return "USER", content
        elif isinstance(message, AIMessage):
            return "ASSISTANT", content
        elif isinstance(message, ToolMessage):
            # Tool messages represent tool execution results
            # Store them as TOOL role to capture the full agent execution context
            return "TOOL", content
        elif isinstance(message, SystemMessage):
            # System messages are instructions, not conversational events
            # Skip them - they're not part of the conversation flow
            logger.debug(f"  ⚠️ Skipping SystemMessage (not a conversational event)")
            return None, None
        else:
            # Unknown message type - log it but don't fail
            logger.debug(f"  ⚠️ Skipping unknown message type: {type(message).__name__}")
            return None, None
