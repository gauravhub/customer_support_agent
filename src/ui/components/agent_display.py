"""
Components for displaying agent thinking process and tool calls.
"""

import streamlit as st
import json
from typing import List, Dict, Any
from datetime import datetime


def display_thinking_process(thinking_steps: List[str]):
    """
    Display agent thinking process in an expandable container.
    
    Args:
        thinking_steps: List of thinking step strings
    """
    if not thinking_steps:
        return
    
    with st.expander("🤔 Agent Thinking Process", expanded=True):
        for i, step in enumerate(thinking_steps, 1):
            st.markdown(f"**Step {i}:**")
            st.markdown(f"💭 {step}")
            if i < len(thinking_steps):
                st.divider()


def display_tool_calls(tool_calls: List[Dict[str, Any]], expanded: bool = False):
    """
    Display tool calls with inputs and results.
    
    Args:
        tool_calls: List of tool call dictionaries
        expanded: Whether the expander should be expanded by default
    """
    if not tool_calls:
        return
    
    with st.expander("🔧 Tool Calls", expanded=expanded):
        for i, tool in enumerate(tool_calls, 1):
            tool_name = tool.get("tool_name", "unknown")
            tool_input = tool.get("tool_input", {})
            result = tool.get("result")
            timestamp = tool.get("timestamp", "")
            status = "✅" if result else "⏳"
            
            st.markdown(f"### {status} {i}. `{tool_name}`")
            
            # Display input
            st.markdown("**Input:**")
            try:
                st.json(tool_input)
            except:
                st.code(str(tool_input), language="text")
            
            # Display result
            if result:
                st.markdown("**Result:**")
                result_str = str(result)
                # Truncate very long results
                if len(result_str) > 1000:
                    with st.expander("View full result"):
                        st.code(result_str, language="text")
                    st.code(result_str[:1000] + "\n... (truncated)", language="text")
                else:
                    st.code(result_str, language="text")
            else:
                st.info("Tool is executing...")
            
            if timestamp:
                st.caption(f"Executed at: {timestamp}")
            
            if i < len(tool_calls):
                st.divider()


def display_node_progress(node_name: str, status: str = "running"):
    """
    Display current node execution status.
    
    Args:
        node_name: Name of the current node
        status: Status (running, completed, error)
    """
    status_icons = {
        "running": "🔄",
        "completed": "✅",
        "error": "❌"
    }
    
    icon = status_icons.get(status, "⏳")
    st.info(f"{icon} **{node_name}** - {status.title()}")
