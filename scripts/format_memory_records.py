#!/usr/bin/env python3
"""
Format AWS Bedrock AgentCore Memory records JSON output into a markdown table.

Usage:
    aws bedrock-agentcore list-memory-records ... | python scripts/format_memory_records.py
    # Or with a file:
    python scripts/format_memory_records.py < memory_records.json
"""

import json
import sys
from datetime import datetime
from typing import Dict, Any, List


def truncate_text(text: str, max_length: int = 150) -> str:
    """Truncate text to max_length, adding ellipsis if needed."""
    if not text:
        return ""
    text = text.strip().replace("\n", " ").replace("\r", " ")
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def format_namespaces(namespaces: List[str]) -> str:
    """Format namespace list into a readable string."""
    if not namespaces:
        return ""
    # Extract key parts from namespace
    parts = []
    for ns in namespaces:
        # Extract actor and session from namespace like:
        # "/strategies/strategy-id/actors/actor-id/sessions/session-id"
        ns_parts = ns.split("/")
        actor = next((p for p in ns_parts if "actors" in p.lower() or p.startswith("actor")), None)
        session = next((p for p in ns_parts if "sessions" in p.lower() or p.startswith("session")), None)
        if actor:
            idx = ns_parts.index(actor) if actor in ns_parts else -1
            if idx >= 0 and idx + 1 < len(ns_parts):
                actor_id = ns_parts[idx + 1]
                parts.append(f"actor: {actor_id[:30]}")
        if session:
            idx = ns_parts.index(session) if session in ns_parts else -1
            if idx >= 0 and idx + 1 < len(ns_parts):
                session_id = ns_parts[idx + 1]
                parts.append(f"session: {session_id[:20]}")
    return " | ".join(parts) if parts else ", ".join([ns[:50] for ns in namespaces[:2]])


def format_metadata(metadata: Dict[str, Any]) -> str:
    """Format metadata into a readable string."""
    if not metadata:
        return ""
    parts = []
    for key, value in metadata.items():
        if isinstance(value, dict):
            # Handle nested metadata like {"stringValue": "..."}
            if "stringValue" in value:
                parts.append(f"{key}: {value['stringValue']}")
            elif "numberValue" in value:
                parts.append(f"{key}: {value['numberValue']}")
            else:
                parts.append(f"{key}: {str(value)[:30]}")
        else:
            parts.append(f"{key}: {str(value)[:30]}")
    return " | ".join(parts)


def format_date(date_str: str) -> str:
    """Format ISO date string to readable format."""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return date_str


def format_memory_records(json_data: Dict[str, Any]) -> str:
    """Format memory records into markdown table."""
    records = json_data.get("memoryRecordSummaries", [])
    
    if not records:
        return "## Memory Records\n\nNo memory records found.\n"
    
    # Build markdown table
    md_lines = [
        "# AgentCore Memory Records",
        "",
        f"**Total Records:** {len(records)}",
        "",
        "## Memory Records Table",
        "",
        "| Record ID | Strategy | Created At | Content Preview | Namespaces | Metadata |",
        "|-----------|----------|------------|------------------|------------|----------|"
    ]
    
    for record in records:
        record_id = record.get("memoryRecordId", "N/A")[:20] + "..." if len(record.get("memoryRecordId", "")) > 20 else record.get("memoryRecordId", "N/A")
        strategy_id = record.get("memoryStrategyId", "N/A")[:15] + "..." if len(record.get("memoryStrategyId", "")) > 15 else record.get("memoryStrategyId", "N/A")
        created_at = format_date(record.get("createdAt", ""))
        
        # Extract content text
        content = record.get("content", {})
        content_text = content.get("text", "") if isinstance(content, dict) else str(content)
        # Don't truncate - show full content, but clean up newlines for table display
        content_preview = content_text.replace("\n", " ").replace("\r", " ").strip()
        
        # Format namespaces
        namespaces = record.get("namespaces", [])
        namespace_str = format_namespaces(namespaces)
        
        # Format metadata
        metadata = record.get("metadata", {})
        metadata_str = format_metadata(metadata)
        
        # Escape pipe characters in content for markdown
        content_preview = content_preview.replace("|", "\\|")
        namespace_str = namespace_str.replace("|", "\\|")
        metadata_str = metadata_str.replace("|", "\\|")
        
        md_lines.append(
            f"| `{record_id}` | `{strategy_id}` | {created_at} | {content_preview} | {namespace_str} | {metadata_str} |"
        )
    
    # Add detailed view section
    md_lines.extend([
        "",
        "## Detailed Records",
        ""
    ])
    
    for idx, record in enumerate(records, 1):
        record_id = record.get("memoryRecordId", "N/A")
        strategy_id = record.get("memoryStrategyId", "N/A")
        created_at = format_date(record.get("createdAt", ""))
        
        content = record.get("content", {})
        content_text = content.get("text", "") if isinstance(content, dict) else str(content)
        
        namespaces = record.get("namespaces", [])
        metadata = record.get("metadata", {})
        
        md_lines.extend([
            f"### Record {idx}: {record_id}",
            "",
            f"- **Strategy ID:** `{strategy_id}`",
            f"- **Created At:** {created_at}",
            f"- **Namespaces:**",
        ])
        
        for ns in namespaces:
            md_lines.append(f"  - `{ns}`")
        
        md_lines.append(f"- **Metadata:**")
        for key, value in metadata.items():
            if isinstance(value, dict):
                if "stringValue" in value:
                    md_lines.append(f"  - `{key}`: {value['stringValue']}")
                elif "numberValue" in value:
                    md_lines.append(f"  - `{key}`: {value['numberValue']}")
                else:
                    md_lines.append(f"  - `{key}`: {json.dumps(value)}")
            else:
                md_lines.append(f"  - `{key}`: {value}")
        
        md_lines.extend([
            f"- **Content:**",
            "",
            "```",
            content_text,
            "```",
            ""
        ])
    
    return "\n".join(md_lines)


def main():
    """Main entry point."""
    try:
        # Read JSON from stdin
        if sys.stdin.isatty():
            print("Error: No input provided. Pipe JSON data to this script.", file=sys.stderr)
            print("Usage: aws bedrock-agentcore list-memory-records ... | python scripts/format_memory_records.py", file=sys.stderr)
            sys.exit(1)
        
        json_input = sys.stdin.read()
        data = json.loads(json_input)
        
        # Format and output
        markdown = format_memory_records(data)
        print(markdown)
        
        return 0
        
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
