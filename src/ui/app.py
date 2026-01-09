"""
AnyCompany Customer Support Agent UI

Streamlit application for interacting with the LangGraph AnyCompany Customer Support Agent.
Integrated with AWS Cognito for authentication.
Shows agent thinking process and tool calls in real-time.
"""

import streamlit as st
import os
import json
import re
import uuid
import logging
from typing import Iterator, Dict, Any, Optional
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime

# Set up logging - logs will appear in the terminal where Streamlit is running
# Using INFO level to filter out noisy DEBUG logs (like watchdog file system events)
# To see logs, just run: streamlit run src/ui/app.py
# Logs will appear in the terminal/console output
logging.basicConfig(
    level=logging.INFO,  # INFO level to reduce noise from watchdog and other DEBUG logs
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Logs to terminal/console (stderr)
    ]
)

# Suppress noisy third-party DEBUG logs
logging.getLogger('watchdog').setLevel(logging.WARNING)
logging.getLogger('watchdog.observers').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# LangGraph SDK imports
try:
    from langgraph_sdk import get_sync_client
    LANGGRAPH_SDK_AVAILABLE = True
    logger.info("✅ LangGraph SDK imported successfully")
except ImportError as e:
    LANGGRAPH_SDK_AVAILABLE = False
    logger.warning(f"⚠️ LangGraph SDK not available: {e}. Will use HTTP requests.")
    # Fallback to requests if SDK not available
    import requests

# Load environment variables from project root
# ui is now in src/ui, so we need to go up 2 levels to reach project root
project_root = Path(__file__).parent.parent.parent
parent_env = project_root / ".env"
if parent_env.exists():
    load_dotenv(parent_env)
load_dotenv()  # Also load from src/ui/.env if it exists

# Import auth module
from auth import authenticate_user, get_user_info, sign_out
from components.agent_display import display_thinking_process, display_tool_calls


def sanitize_actor_id(identifier: str) -> str:
    """
    Sanitize an identifier to match AgentCore Memory ID pattern.
    
    AgentCore Memory requires IDs to match: [a-zA-Z0-9][a-zA-Z0-9-_/]*(?::[a-zA-Z0-9-_/]+)*[a-zA-Z0-9-_/]*
    
    Args:
        identifier: Original identifier (e.g., email address)
        
    Returns:
        Sanitized identifier that matches the pattern
    """
    if not identifier:
        return identifier
    
    # Replace invalid characters with valid ones
    # Replace @ with -at-, . with -, and ensure it starts with alphanumeric
    sanitized = identifier.replace("@", "-at-").replace(".", "-")
    
    # Remove any other invalid characters (keep only alphanumeric, -, _, /, :)
    sanitized = re.sub(r'[^a-zA-Z0-9\-_/:]', '-', sanitized)
    
    # Ensure it starts with alphanumeric (required by pattern)
    if sanitized and not sanitized[0].isalnum():
        sanitized = 'id-' + sanitized
    
    return sanitized


def get_runtime_config(thread_id: Optional[str] = None, username: Optional[str] = None) -> Dict[str, Any]:
    """
    Generate runtime configuration with required thread_id and actor_id.
    
    The configuration always includes:
    - thread_id: LangGraph thread ID (same as session_id for AgentCore Memory)
    - actor_id: Sanitized username/email (maps to Bedrock AgentCore actor_id)
    
    Args:
        thread_id: LangGraph thread ID. If None, uses session state.
        username: Username/email for actor_id. If None, uses session state.
        
    Returns:
        Configuration dictionary with configurable.thread_id and configurable.actor_id
    """
    # Get thread_id from parameter or session state
    if thread_id is None:
        thread_id = st.session_state.get("thread_id")
    
    # Get username from parameter or session state (prefer email if available)
    if username is None:
        username = st.session_state.get("user_email") or st.session_state.get("username")
    
    # Sanitize username/email for actor_id
    actor_id = sanitize_actor_id(username) if username else "unknown-user"
    
    # Use thread_id as session_id (they should be the same for AgentCore Memory)
    # If thread_id is not set yet, it will be created when first message is sent
    if not thread_id:
        thread_id = None  # Will be set when thread is created
    
    config = {
        "configurable": {
            "thread_id": thread_id,  # REQUIRED: Maps to Bedrock AgentCore session_id (will be set when thread created)
            "actor_id": actor_id,    # REQUIRED: Maps to Bedrock AgentCore actor_id (sanitized username/email)
        }
    }
    
    return config

# Page configuration
st.set_page_config(
    page_title="AnyCompany Customer Support Agent",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded"
)

def create_langgraph_thread(api_url: str) -> Optional[str]:
    """
    Create a new thread in LangGraph API.
    
    Args:
        api_url: LangGraph API endpoint URL
        
    Returns:
        Thread ID if successful, None otherwise
    """
    try:
        if LANGGRAPH_SDK_AVAILABLE:
            # Use SDK to create thread
            client = get_sync_client(url=api_url)
            thread = client.threads.create()
            logger.info(f"📋 Thread creation response: {thread}")
            
            # Handle both dict and object responses
            if isinstance(thread, dict):
                thread_id = thread.get("thread_id")
            elif hasattr(thread, 'thread_id'):
                thread_id = thread.thread_id
            else:
                # Try to get thread_id from any attribute
                thread_id = getattr(thread, 'thread_id', None) or (thread.get("thread_id") if hasattr(thread, 'get') else None)
            
            if thread_id:
                logger.info(f"✅ Thread created successfully: {thread_id}")
                return thread_id
            else:
                logger.warning(f"⚠️ Thread created but no thread_id found in response: {thread}")
                return None
        else:
            # Use HTTP request to create thread
            import requests
            logger.info(f"🌐 Creating thread via HTTP: {api_url}/threads")
            response = requests.post(
                f"{api_url}/threads",
                headers={"Content-Type": "application/json"},
                json={}
            )
            logger.info(f"📥 HTTP response status: {response.status_code}")
            if response.status_code == 200:
                thread_data = response.json()
                thread_id = thread_data.get("thread_id")
                if thread_id:
                    logger.info(f"✅ Thread created successfully via HTTP: {thread_id}")
                    return thread_id
                else:
                    logger.warning(f"⚠️ Thread created but no thread_id in response: {thread_data}")
                    return None
            else:
                logger.error(f"❌ Failed to create thread: {response.status_code} - {response.text}")
                st.warning(f"Failed to create thread: {response.text}")
                return None
    except Exception as e:
        logger.error(f"❌ Exception creating thread: {e}", exc_info=True)
        st.warning(f"Could not create thread via API: {e}")
        return None


def main():
    """Main application entry point."""
    
    # Initialize session state
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = None
    if "current_run_id" not in st.session_state:
        st.session_state.current_run_id = None
    
    # Authentication check
    if not st.session_state.authenticated:
        show_login_page()
    else:
        # Create thread if not exists (after login)
        # Thread will be created when user sends first message if not already created
        show_chat_interface()

def show_login_page():
    """Display Cognito login page."""
    st.title("🔐 AnyCompany Customer Support Agent")
    st.markdown("Please sign in to access the AnyCompany customer support agent.")
    
    # Check if Cognito is configured
    cognito_pool_id = os.getenv("COGNITO_USER_POOL_ID")
    cognito_client_id = os.getenv("COGNITO_CLIENT_ID")
    cognito_client_secret = os.getenv("COGNITO_CLIENT_SECRET")  # Optional
    
    if not cognito_pool_id or not cognito_client_id:
        st.error("⚠️ Cognito is not configured. Please set COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID in your .env file.")
        st.info("💡 **Note:** COGNITO_CLIENT_SECRET is optional. Only required if your App Client was created with a client secret (confidential client).")
        st.info("For development, you can use placeholder credentials below.")
        use_placeholder = True
    else:
        use_placeholder = False
        if cognito_client_secret:
            st.info("🔒 Using confidential client (with client secret)")
        else:
            st.info("🔓 Using public client (no client secret required)")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.form("login_form"):
            st.subheader("Sign In")
            username = st.text_input("Username or Email")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Sign In", use_container_width=True)
            
            if submit:
                if not username or not password:
                    st.error("Please enter both username and password")
                elif use_placeholder:
                    # Development mode - allow any credentials
                    st.warning("⚠️ Development mode: Using placeholder authentication")
                    st.session_state.authenticated = True
                    st.session_state.username = username
                    # Thread will be created on first message
                    st.rerun()
                else:
                    # Real Cognito authentication
                    tokens = authenticate_user(username, password)
                    if tokens:
                        user_info = get_user_info()
                        if user_info:
                            st.session_state.authenticated = True
                            # Use email as username (for actor_id), fallback to Cognito username
                            user_email = user_info.get("attributes", {}).get("email", "")
                            st.session_state.username = user_email if user_email else user_info.get("username", username)
                            st.session_state.user_email = user_email
                            # Thread will be created on first message
                            st.success("✅ Authentication successful!")
                            st.rerun()

def show_chat_interface():
    """Display the main chat interface."""
    
    # Sidebar
    with st.sidebar:
        st.title("AnyCompany Customer Support Agent")
        st.markdown(f"**User:** {st.session_state.get('username', 'Unknown')}")
        
        if st.button("Sign Out"):
            sign_out()
            st.session_state.authenticated = False
            st.session_state.messages = []
            st.session_state.thread_id = None
            st.rerun()
        
        st.divider()
        st.markdown("### Configuration")
        langgraph_url = st.text_input(
            "LangGraph API URL",
            value=st.session_state.get("langgraph_url", os.getenv("LANGGRAPH_API_URL", "http://localhost:8123")),
            help="URL of your LangGraph API endpoint",
            key="langgraph_url_input"
        )
        # Store in session state for thread creation
        st.session_state.langgraph_url = langgraph_url
        
        assistant_id = st.text_input(
            "Assistant ID",
            value=st.session_state.get("assistant_id", os.getenv("LANGGRAPH_ASSISTANT_ID", "Customer Support Agent")),
            help="LangGraph Assistant ID",
            key="assistant_id_input"
        )
        # Store in session state
        st.session_state.assistant_id = assistant_id
        
        st.divider()
        st.markdown("### Runtime Configuration")
        st.caption("Configuration is automatically set with thread_id and actor_id")
        
        # Show current configuration (read-only)
        current_config = get_runtime_config()
        st.json(current_config)
    
    # Main chat area
    st.title("💬 AnyCompany Customer Support Agent")
    
    # Create thread if it doesn't exist (when chat interface is shown)
    if not st.session_state.thread_id:
        langgraph_url = st.session_state.get("langgraph_url", os.getenv("LANGGRAPH_API_URL", "http://localhost:8123"))
        with st.spinner("Creating conversation thread..."):
            thread_id = create_langgraph_thread(langgraph_url)
            if thread_id:
                st.session_state.thread_id = thread_id
            else:
                st.error("⚠️ Failed to create thread. Please check your LangGraph API connection.")
                st.info("💡 Make sure your LangGraph API is running and accessible at the configured URL.")
                st.stop()
    
    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Chat input
    if prompt := st.chat_input("Type your message here..."):
        
        # Add user message to history
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Get runtime configuration with thread_id and actor_id
        config_dict = get_runtime_config()
        
        # Ensure config has the required structure
        if "configurable" not in config_dict:
            config_dict = {"configurable": {}}
        
        # Get agent response with streaming
        with st.chat_message("assistant"):
            response_text = ""
            thinking_steps = []
            tool_calls = []
            current_node = None
            
            # Create containers for different display sections
            response_placeholder = st.empty()
            thinking_placeholder = st.empty()
            tool_placeholder = st.empty()
            node_placeholder = st.empty()
            
            # Stream agent response
            try:
                # Use stored values from session state
                api_url = st.session_state.get("langgraph_url", langgraph_url)
                asst_id = st.session_state.get("assistant_id", assistant_id)
                logger.info(f"🎯 Starting stream: prompt='{prompt[:50]}...', api_url={api_url}, assistant_id={asst_id}")
                event_count = 0
                response_event_count = 0
                for event in stream_agent_response(prompt, api_url, asst_id, config_dict):
                    event_count += 1
                    logger.debug(f"📥 UI received event #{event_count}: type={event.get('type')}, keys={list(event.keys())}")
                    
                    if event["type"] == "node_start":
                        current_node = event.get("node_name", "Unknown")
                        node_placeholder.info(f"🔄 Executing: **{current_node}**")
                    
                    elif event["type"] == "node_end":
                        node_name = event.get("node_name", "Unknown")
                        node_placeholder.success(f"✅ Completed: **{node_name}**")
                        current_node = None
                    
                    elif event["type"] == "thinking":
                        thinking_steps.append(event["content"])
                        with thinking_placeholder.container():
                            display_thinking_process(thinking_steps)
                    
                    elif event["type"] == "tool_call":
                        tool_calls.append(event)
                        with tool_placeholder.container():
                            display_tool_calls(tool_calls, expanded=False)
                    
                    elif event["type"] == "tool_result":
                        # Update the tool call with result
                        tool_call_id = event.get("tool_call_id")
                        tool_name = event.get("tool_name", "unknown")
                        result_content = event.get("content", "")
                        
                        # Find matching tool call or create new entry
                        tool_found = False
                        for tool in tool_calls:
                            if tool.get("tool_call_id") == tool_call_id:
                                tool["result"] = result_content
                                tool["tool_name"] = tool_name  # Ensure name is set
                                tool_found = True
                                break
                        
                        # If no matching tool call found, create a new entry
                        if not tool_found:
                            tool_calls.append({
                                "tool_name": tool_name,
                                "tool_call_id": tool_call_id,
                                "tool_input": {},
                                "result": result_content,
                                "timestamp": event.get("timestamp", datetime.now().isoformat())
                            })
                        
                        with tool_placeholder.container():
                            display_tool_calls(tool_calls, expanded=False)
                    
                    elif event["type"] == "response":
                        response_event_count += 1
                        content = event.get("content", "")
                        logger.info(f"✅ Response event #{response_event_count}: content_length={len(content)}, preview={content[:100]}...")
                        response_text += content
                        response_placeholder.markdown(response_text)
                
                # Final response
                logger.info(f"📊 Stream complete: total_events={event_count}, response_events={response_event_count}, response_length={len(response_text)}")
                if not response_text:
                    logger.warning(f"⚠️ No response text collected! Total events: {event_count}, Response events: {response_event_count}")
                    response_text = "Agent completed processing."
                    response_placeholder.markdown(response_text)
                
                # Clear node status
                node_placeholder.empty()
            
            except Exception as e:
                st.error(f"Error communicating with agent: {e}")
                response_text = f"Error: {str(e)}"
                node_placeholder.error(f"❌ Error in {current_node or 'agent'}")
        
        # Add assistant response to history
        st.session_state.messages.append({
            "role": "assistant", 
            "content": response_text,
            "thinking": thinking_steps,
            "tool_calls": tool_calls
        })

def stream_agent_response(
    user_message: str, 
    api_url: str, 
    assistant_id: str,
    config: Optional[Dict[str, Any]] = None
) -> Iterator[Dict[str, Any]]:
    """
    Stream agent response from LangGraph API, including thinking and tool calls.
    
    Uses LangGraph SDK if available, otherwise falls back to direct HTTP requests.
    
    Args:
        user_message: User's input message
        api_url: LangGraph API endpoint URL
        assistant_id: LangGraph Assistant ID
        config: Optional configuration dictionary to pass to the graph
        
    Yields:
        Event dictionaries with type and content
    """
    logger.info(f"🎬 stream_agent_response called: message='{user_message[:50]}...', api_url={api_url}, assistant_id={assistant_id}")
    
    if config is None:
        config = {"configurable": {}}
    
    logger.info(f"📋 SDK available: {LANGGRAPH_SDK_AVAILABLE}")
    
    # Use LangGraph SDK if available
    if LANGGRAPH_SDK_AVAILABLE:
        logger.info("📡 Using LangGraph SDK for streaming")
        yield from _stream_with_sdk(user_message, api_url, assistant_id, config)
    else:
        logger.info("🌐 Using HTTP requests for streaming (SDK not available)")
        yield from _stream_with_requests(user_message, api_url, assistant_id, config)


def _stream_with_sdk(
    user_message: str,
    api_url: str,
    assistant_id: str,
    config: Dict[str, Any]
) -> Iterator[Dict[str, Any]]:
    """Stream using LangGraph SDK."""
    try:
        # Create SDK client
        client = get_sync_client(url=api_url)
        
        # Ensure we have a thread_id (should be created before this function is called)
        if not st.session_state.thread_id:
            raise ValueError("Thread ID is required. Please ensure thread is created before streaming.")
        
        # Ensure config has the correct thread_id and actor_id
        if "configurable" not in config:
            config["configurable"] = {}
        config["configurable"]["thread_id"] = st.session_state.thread_id
        # Preserve actor_id if it exists, or get it from session state
        if "actor_id" not in config["configurable"]:
            username = st.session_state.get("user_email") or st.session_state.get("username")
            if username:
                config["configurable"]["actor_id"] = sanitize_actor_id(username)
        
        # Prepare input
        input_data = {
            "messages": [{"role": "user", "content": user_message}]
        }
        
        # Stream the run
        logger.info(f"🚀 Starting SDK stream: thread_id={st.session_state.thread_id}, assistant_id={assistant_id}")
        logger.info(f"📤 Input data: {json.dumps(input_data, indent=2)}")
        logger.info(f"⚙️ Config: {json.dumps(config, indent=2, default=str)}")
        
        stream_count = 0
        try:
            for event in client.runs.stream(
                thread_id=st.session_state.thread_id,
                assistant_id=assistant_id,
                input=input_data,
                config=config,
                stream_mode=["values", "updates", "messages"]  # Valid StreamMode values
            ):
                stream_count += 1
                logger.info(f"📡 SDK stream event #{stream_count}: type={type(event).__name__}")
                
                # Log event structure for debugging
                if hasattr(event, 'event'):
                    logger.info(f"   Event type: {event.event}")
                if hasattr(event, 'data'):
                    data_preview = str(event.data)[:200] if event.data else "None"
                    logger.info(f"   Data preview: {data_preview}...")
                
                parsed_count = 0
                for parsed_event in parse_langgraph_sdk_event(event):
                    parsed_count += 1
                    logger.info(f"  ✅ Parsed event #{parsed_count}: type={parsed_event.get('type')}")
                    yield parsed_event
                
                if parsed_count == 0:
                    logger.warning(f"⚠️ No events parsed from SDK stream event #{stream_count}")
                    # Log full event structure for debugging
                    logger.info(f"   Full event structure: {event}")
        except Exception as e:
            logger.error(f"❌ Error in SDK stream: {e}", exc_info=True)
            raise
        
        logger.info(f"🏁 SDK stream completed: total_stream_events={stream_count}")
            
    except Exception as e:
        st.error(f"Error with LangGraph SDK: {e}")
        # Fallback to requests
        yield from _stream_with_requests(user_message, api_url, assistant_id, config)


def _stream_with_requests(
    user_message: str,
    api_url: str,
    assistant_id: str,
    config: Dict[str, Any]
) -> Iterator[Dict[str, Any]]:
    """Stream using direct HTTP requests (fallback)."""
    import requests
    
    # Ensure we have a thread_id (should be created before this function is called)
    if not st.session_state.thread_id:
        raise ValueError("Thread ID is required. Please ensure thread is created before streaming.")
    
    # Ensure config has the correct thread_id and actor_id
    if "configurable" not in config:
        config["configurable"] = {}
    config["configurable"]["thread_id"] = st.session_state.thread_id
    # Preserve actor_id if it exists, or get it from session state
    if "actor_id" not in config["configurable"]:
        username = st.session_state.get("user_email") or st.session_state.get("username")
        if username:
            config["configurable"]["actor_id"] = sanitize_actor_id(username)
    
    # Prepare request payload
    request_payload = {
        "assistant_id": assistant_id,
        "input": {
            "messages": [{"role": "user", "content": user_message}]
        },
        "config": config,
        "stream_mode": ["values", "updates", "messages"]
    }
    
    url = f"{api_url}/threads/{st.session_state.thread_id}/runs"
    logger.info(f"🌐 HTTP POST to: {url}")
    logger.info(f"📤 Request payload: {json.dumps(request_payload, indent=2, default=str)}")
    
    # Create a run with streaming
    try:
        run_response = requests.post(
            url,
            json=request_payload,
            headers={"Content-Type": "application/json"},
            stream=True,
            timeout=30
        )
        
        logger.info(f"📥 HTTP Response status: {run_response.status_code}")
        logger.info(f"📥 HTTP Response headers: {dict(run_response.headers)}")
        
        if run_response.status_code != 200:
            error_text = run_response.text
            logger.error(f"❌ HTTP request failed: {error_text}")
            raise Exception(f"Failed to start run: {error_text}")
        
        st.session_state.current_run_id = run_response.headers.get("x-langgraph-run-id")
        logger.info(f"🆔 Run ID: {st.session_state.current_run_id}")
        
        # Parse Server-Sent Events (SSE) stream
        buffer = ""
        chunk_count = 0
        event_count = 0
        
        logger.info("📡 Starting to read SSE stream...")
        for chunk in run_response.iter_content(chunk_size=1024, decode_unicode=True):
            if chunk:
                chunk_count += 1
                logger.info(f"📦 Received chunk #{chunk_count}: length={len(chunk)}, preview={chunk[:100]}...")
                buffer += chunk
                
                # Process complete SSE messages
                while "\n\n" in buffer:
                    message, buffer = buffer.split("\n\n", 1)
                    logger.info(f"📨 Processing SSE message: {message[:200]}...")
                    
                    if message.startswith("data: "):
                        data = message[6:]  # Remove "data: " prefix
                        logger.info(f"📋 SSE data: {data[:200]}...")
                        
                        if data == "[DONE]":
                            logger.info("🏁 Received [DONE] signal, ending stream")
                            return
                        
                        try:
                            event_data = json.loads(data)
                            event_count += 1
                            logger.info(f"✅ Parsed SSE event #{event_count}: {json.dumps(event_data, indent=2, default=str)[:500]}")
                            
                            parsed_count = 0
                            for parsed_event in parse_langgraph_event(event_data):
                                parsed_count += 1
                                logger.info(f"  ✅ Parsed event #{parsed_count}: type={parsed_event.get('type')}")
                                yield parsed_event
                            
                            if parsed_count == 0:
                                logger.warning(f"⚠️ No events parsed from HTTP SSE event #{event_count}")
                        except json.JSONDecodeError as e:
                            logger.warning(f"⚠️ JSON decode error: {e}, data={data[:200]}")
                            continue
        
        logger.info(f"🏁 HTTP stream completed: chunks={chunk_count}, events={event_count}")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ HTTP request exception: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error in HTTP stream: {e}", exc_info=True)
        raise


def parse_langgraph_sdk_event(event: Any) -> Iterator[Dict[str, Any]]:
    """
    Parse LangGraph SDK StreamPart event and yield formatted events.
    
    StreamPart is a NamedTuple with:
    - event: str (e.g., "values", "updates", "messages", "end")
    - data: dict (contains the actual payload)
    - id: str | None (optional event ID)
    
    Args:
        event: StreamPart from LangGraph SDK
        
    Yields:
        Formatted event dictionaries
    """
    logger.debug(f"🔍 SDK Event received: type={type(event)}, dir={[attr for attr in dir(event) if not attr.startswith('_')]}")
    
    # StreamPart has 'event' and 'data' attributes
    if not hasattr(event, 'event') or not hasattr(event, 'data'):
        logger.warning(f"⚠️ Event missing 'event' or 'data' attribute: {event}")
        return
    
    event_type = event.event
    event_data = event.data
    
    logger.info(f"📨 SDK Event: event_type={event_type}, data_type={type(event_data)}")
    logger.debug(f"📦 SDK Event data: {json.dumps(event_data, indent=2, default=str)[:500]}")
    
    # Handle "values" events - these contain the current state with messages
    if event_type == "values" and isinstance(event_data, dict):
        messages = event_data.get("messages", [])
        logger.info(f"📬 Found {len(messages)} messages in 'values' event")
        
        # Process all message types
        for idx, msg in enumerate(messages):
            logger.debug(f"  Message {idx}: type={type(msg)}, keys={list(msg.keys()) if isinstance(msg, dict) else 'N/A'}")
            if isinstance(msg, dict):
                msg_type = msg.get("type", "")
                
                # Handle AI messages - extract both content and tool calls
                if msg_type == "ai":
                    # Extract tool calls from AI message
                    tool_calls = msg.get("tool_calls", [])
                    if tool_calls:
                        logger.info(f"🔧 Found {len(tool_calls)} tool calls in AI message")
                        for tool_call in tool_calls:
                            tool_name = tool_call.get("name", "unknown")
                            tool_id = tool_call.get("id", "")
                            tool_args = tool_call.get("args", {})
                            logger.info(f"  🔧 Tool call: {tool_name} (id: {tool_id})")
                            yield {
                                "type": "tool_call",
                                "tool_name": tool_name,
                                "tool_call_id": tool_id,
                                "tool_input": tool_args,
                                "timestamp": datetime.now().isoformat()
                            }
                    
                    # Extract text content from AI message
                    content = msg.get("content", "")
                    if content:
                        # Handle both string and list content
                        if isinstance(content, str):
                            logger.info(f"✅ Extracting AI response (string): {content[:100]}...")
                            yield {
                                "type": "response",
                                "content": content
                            }
                        elif isinstance(content, list):
                            logger.info(f"✅ Extracting AI response (list with {len(content)} blocks)")
                            # Extract text from content blocks
                            for block_idx, block in enumerate(content):
                                logger.debug(f"      Block {block_idx}: {block}")
                                if isinstance(block, dict) and block.get("type") == "text":
                                    text_content = block.get("text", "")
                                    logger.info(f"✅ Extracting text block: {text_content[:100]}...")
                                    yield {
                                        "type": "response",
                                        "content": text_content
                                    }
                
                # Handle Tool messages - these are tool execution results
                elif msg_type == "tool":
                    tool_call_id = msg.get("tool_call_id", "")
                    content = msg.get("content", "")
                    name = msg.get("name", "unknown_tool")
                    logger.info(f"🔧 Tool result: {name} (call_id: {tool_call_id})")
                    yield {
                        "type": "tool_result",
                        "tool_call_id": tool_call_id,
                        "tool_name": name,
                        "content": content if isinstance(content, str) else str(content),
                        "timestamp": datetime.now().isoformat()
                    }
                
                # Handle Human messages (for debugging)
                elif msg_type == "human":
                    logger.debug(f"👤 Human message: {msg.get('content', '')[:100]}...")
                
                else:
                    logger.debug(f"    Skipping message: type={msg_type}")
    
    # Handle "messages" events - direct message updates
    elif event_type == "messages" and isinstance(event_data, dict):
        messages = event_data.get("messages", [])
        if not isinstance(messages, list):
            messages = [messages] if messages else []
        
        logger.info(f"📬 Found {len(messages)} messages in 'messages' event")
        for idx, msg in enumerate(messages):
            logger.debug(f"  Message {idx}: type={msg.get('type') if isinstance(msg, dict) else 'unknown'}")
            if isinstance(msg, dict):
                msg_type = msg.get("type", "")
                
                # Handle AI messages - extract tool calls and content
                if msg_type == "ai":
                    # Extract tool calls
                    tool_calls = msg.get("tool_calls", [])
                    if tool_calls:
                        logger.info(f"🔧 Found {len(tool_calls)} tool calls in 'messages' event")
                        for tool_call in tool_calls:
                            tool_name = tool_call.get("name", "unknown")
                            tool_id = tool_call.get("id", "")
                            tool_args = tool_call.get("args", {})
                            yield {
                                "type": "tool_call",
                                "tool_name": tool_name,
                                "tool_call_id": tool_id,
                                "tool_input": tool_args,
                                "timestamp": datetime.now().isoformat()
                            }
                    
                    # Extract content
                    content = msg.get("content", "")
                    if content:
                        logger.info(f"✅ Extracting AI response from 'messages' event")
                        if isinstance(content, str):
                            yield {
                                "type": "response",
                                "content": content
                            }
                        elif isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    yield {
                                        "type": "response",
                                        "content": block.get("text", "")
                                    }
                
                # Handle Tool messages
                elif msg_type == "tool":
                    tool_call_id = msg.get("tool_call_id", "")
                    content = msg.get("content", "")
                    name = msg.get("name", "unknown_tool")
                    logger.info(f"🔧 Tool result from 'messages' event: {name}")
                    yield {
                        "type": "tool_result",
                        "tool_call_id": tool_call_id,
                        "tool_name": name,
                        "content": content if isinstance(content, str) else str(content),
                        "timestamp": datetime.now().isoformat()
                    }
    
    # Handle "updates" events - incremental state updates
    elif event_type == "updates" and isinstance(event_data, dict):
        logger.info(f"📬 Processing 'updates' event")
        # Updates may contain message deltas
        if "messages" in event_data:
            messages = event_data["messages"]
            if not isinstance(messages, list):
                messages = [messages] if messages else []
            
            logger.info(f"📬 Found {len(messages)} messages in 'updates' event")
            for msg in messages:
                if isinstance(msg, dict):
                    msg_type = msg.get("type", "")
                    
                    # Handle AI messages - extract tool calls and content
                    if msg_type == "ai":
                        # Extract tool calls
                        tool_calls = msg.get("tool_calls", [])
                        if tool_calls:
                            logger.info(f"🔧 Found {len(tool_calls)} tool calls in 'updates' event")
                            for tool_call in tool_calls:
                                tool_name = tool_call.get("name", "unknown")
                                tool_id = tool_call.get("id", "")
                                tool_args = tool_call.get("args", {})
                                yield {
                                    "type": "tool_call",
                                    "tool_name": tool_name,
                                    "tool_call_id": tool_id,
                                    "tool_input": tool_args,
                                    "timestamp": datetime.now().isoformat()
                                }
                        
                        # Extract content
                        content = msg.get("content", "")
                        if content:
                            logger.info(f"✅ Extracting AI response from 'updates' event")
                            if isinstance(content, str):
                                yield {
                                    "type": "response",
                                    "content": content
                                }
                            elif isinstance(content, list):
                                for block in content:
                                    if isinstance(block, dict) and block.get("type") == "text":
                                        yield {
                                            "type": "response",
                                            "content": block.get("text", "")
                                        }
                    
                    # Handle Tool messages
                    elif msg_type == "tool":
                        tool_call_id = msg.get("tool_call_id", "")
                        content = msg.get("content", "")
                        name = msg.get("name", "unknown_tool")
                        logger.info(f"🔧 Tool result from 'updates' event: {name}")
                        yield {
                            "type": "tool_result",
                            "tool_call_id": tool_call_id,
                            "tool_name": name,
                            "content": content if isinstance(content, str) else str(content),
                            "timestamp": datetime.now().isoformat()
                        }
        else:
            logger.debug(f"  No 'messages' key in 'updates' event. Keys: {list(event_data.keys())}")
    
    else:
        logger.debug(f"⚠️ Unhandled event type: {event_type}")


def parse_langgraph_event(event_data: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    """
    Parse LangGraph HTTP SSE event and yield formatted events.
    
    HTTP events come in different formats:
    - Direct StreamPart-like format: {"event": "values", "data": {...}}
    - LangChain callback format: {"event": "on_chain_start", ...}
    
    Args:
        event_data: Raw event data from LangGraph API (HTTP SSE)
        
    Yields:
        Formatted event dictionaries
    """
    # Check if this is a StreamPart-like event (from HTTP SSE)
    if "event" in event_data and "data" in event_data:
        event_type = event_data.get("event")
        data = event_data.get("data", {})
        
        # Handle "values" events
        if event_type == "values" and isinstance(data, dict):
            messages = data.get("messages", [])
            for msg in messages:
                if isinstance(msg, dict):
                    msg_type = msg.get("type", "")
                    
                    # Handle AI messages - extract tool calls and content
                    if msg_type == "ai":
                        # Extract tool calls
                        tool_calls = msg.get("tool_calls", [])
                        if tool_calls:
                            logger.info(f"🔧 Found {len(tool_calls)} tool calls in HTTP 'values' event")
                            for tool_call in tool_calls:
                                tool_name = tool_call.get("name", "unknown")
                                tool_id = tool_call.get("id", "")
                                tool_args = tool_call.get("args", {})
                                yield {
                                    "type": "tool_call",
                                    "tool_name": tool_name,
                                    "tool_call_id": tool_id,
                                    "tool_input": tool_args,
                                    "timestamp": datetime.now().isoformat()
                                }
                        
                        # Extract content
                        content = msg.get("content", "")
                        if content:
                            if isinstance(content, str):
                                yield {
                                    "type": "response",
                                    "content": content
                                }
                            elif isinstance(content, list):
                                for block in content:
                                    if isinstance(block, dict) and block.get("type") == "text":
                                        yield {
                                            "type": "response",
                                            "content": block.get("text", "")
                                        }
                    
                    # Handle Tool messages
                    elif msg_type == "tool":
                        tool_call_id = msg.get("tool_call_id", "")
                        content = msg.get("content", "")
                        name = msg.get("name", "unknown_tool")
                        logger.info(f"🔧 Tool result from HTTP 'values' event: {name}")
                        yield {
                            "type": "tool_result",
                            "tool_call_id": tool_call_id,
                            "tool_name": name,
                            "content": content if isinstance(content, str) else str(content),
                            "timestamp": datetime.now().isoformat()
                        }
        
        # Handle "messages" events
        elif event_type == "messages" and isinstance(data, dict):
            messages = data.get("messages", [])
            if not isinstance(messages, list):
                messages = [messages] if messages else []
            
            for msg in messages:
                if isinstance(msg, dict):
                    msg_type = msg.get("type", "")
                    
                    # Handle AI messages - extract tool calls and content
                    if msg_type == "ai":
                        # Extract tool calls
                        tool_calls = msg.get("tool_calls", [])
                        if tool_calls:
                            logger.info(f"🔧 Found {len(tool_calls)} tool calls in HTTP 'messages' event")
                            for tool_call in tool_calls:
                                tool_name = tool_call.get("name", "unknown")
                                tool_id = tool_call.get("id", "")
                                tool_args = tool_call.get("args", {})
                                yield {
                                    "type": "tool_call",
                                    "tool_name": tool_name,
                                    "tool_call_id": tool_id,
                                    "tool_input": tool_args,
                                    "timestamp": datetime.now().isoformat()
                                }
                        
                        # Extract content
                        content = msg.get("content", "")
                        if content:
                            if isinstance(content, str):
                                yield {
                                    "type": "response",
                                    "content": content
                                }
                            elif isinstance(content, list):
                                for block in content:
                                    if isinstance(block, dict) and block.get("type") == "text":
                                        yield {
                                            "type": "response",
                                            "content": block.get("text", "")
                                        }
                    
                    # Handle Tool messages
                    elif msg_type == "tool":
                        tool_call_id = msg.get("tool_call_id", "")
                        content = msg.get("content", "")
                        name = msg.get("name", "unknown_tool")
                        logger.info(f"🔧 Tool result from HTTP 'messages' event: {name}")
                        yield {
                            "type": "tool_result",
                            "tool_call_id": tool_call_id,
                            "tool_name": name,
                            "content": content if isinstance(content, str) else str(content),
                            "timestamp": datetime.now().isoformat()
                        }
        
        # Handle "updates" events
        elif event_type == "updates" and isinstance(data, dict):
            if "messages" in data:
                messages = data["messages"]
                if not isinstance(messages, list):
                    messages = [messages] if messages else []
                
                for msg in messages:
                    if isinstance(msg, dict):
                        msg_type = msg.get("type", "")
                        
                        # Handle AI messages - extract tool calls and content
                        if msg_type == "ai":
                            # Extract tool calls
                            tool_calls = msg.get("tool_calls", [])
                            if tool_calls:
                                logger.info(f"🔧 Found {len(tool_calls)} tool calls in HTTP 'updates' event")
                                for tool_call in tool_calls:
                                    tool_name = tool_call.get("name", "unknown")
                                    tool_id = tool_call.get("id", "")
                                    tool_args = tool_call.get("args", {})
                                    yield {
                                        "type": "tool_call",
                                        "tool_name": tool_name,
                                        "tool_call_id": tool_id,
                                        "tool_input": tool_args,
                                        "timestamp": datetime.now().isoformat()
                                    }
                            
                            # Extract content
                            content = msg.get("content", "")
                            if content:
                                if isinstance(content, str):
                                    yield {
                                        "type": "response",
                                        "content": content
                                    }
                                elif isinstance(content, list):
                                    for block in content:
                                        if isinstance(block, dict) and block.get("type") == "text":
                                            yield {
                                                "type": "response",
                                                "content": block.get("text", "")
                                            }
                        
                        # Handle Tool messages
                        elif msg_type == "tool":
                            tool_call_id = msg.get("tool_call_id", "")
                            content = msg.get("content", "")
                            name = msg.get("name", "unknown_tool")
                            logger.info(f"🔧 Tool result from HTTP 'updates' event: {name}")
                            yield {
                                "type": "tool_result",
                                "tool_call_id": tool_call_id,
                                "tool_name": name,
                                "content": content if isinstance(content, str) else str(content),
                                "timestamp": datetime.now().isoformat()
                            }
        return
    
    # Fallback: Handle LangChain callback format (if used)
    event_type = event_data.get("event")
    
    if event_type == "on_chain_start":
        # Agent thinking/reasoning
        if "name" in event_data and "reasoning" in event_data.get("name", "").lower():
            yield {
                "type": "thinking",
                "content": event_data.get("input", {}).get("messages", [{}])[-1].get("content", "")
            }
    
    elif event_type == "on_tool_start":
        # Tool call started
        tool_name = event_data.get("name", "unknown_tool")
        tool_input = event_data.get("input", {})
        yield {
            "type": "tool_call",
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_call_id": event_data.get("run_id"),
            "timestamp": datetime.now().isoformat()
        }
    
    elif event_type == "on_tool_end":
        # Tool call completed
        tool_output = event_data.get("output", "")
        yield {
            "type": "tool_result",
            "tool_call_id": event_data.get("run_id"),
            "content": str(tool_output),
            "timestamp": datetime.now().isoformat()
        }
    
    elif event_type == "on_chain_stream":
        # Streaming response chunks
        chunk = event_data.get("chunk", {})
        if "messages" in chunk:
            for message in chunk["messages"]:
                if message.get("type") == "ai" and "content" in message:
                    content = message["content"]
                    if isinstance(content, str):
                        yield {
                            "type": "response",
                            "content": content
                        }
                    elif isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                yield {
                                    "type": "response",
                                    "content": item.get("text", "")
                                }
    
    elif event_type == "on_chain_end":
        # Final response
        output = event_data.get("output", {})
        if "messages" in output:
            for message in output["messages"]:
                if message.get("type") == "ai" and "content" in message:
                    content = message["content"]
                    if isinstance(content, str):
                        yield {
                            "type": "response",
                            "content": content
                        }
    
    # LangGraph specific events
    elif event_type == "on_chain_stream" and "node" in str(event_data):
        # Node execution events
        node_name = event_data.get("name", "Unknown")
        yield {
            "type": "node_start",
            "node_name": node_name
        }
    
    elif event_type == "on_chain_end" and "node" in str(event_data):
        # Node completion
        node_name = event_data.get("name", "Unknown")
        yield {
            "type": "node_end",
            "node_name": node_name
        }



if __name__ == "__main__":
    main()
