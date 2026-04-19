"""
MCP Manifest Generator Agent
Uses LLM to analyze MCP server code and generate an AgentCard.json
representing its capabilities (tools, resources, prompts).
"""

import logging
from typing import Any, Dict, List

from .base import BaseGeneratorAgent

logger = logging.getLogger(__name__)


class MCPManifestGeneratorAgent(BaseGeneratorAgent):
    """
    An agent that generates an AgentCard mapped from MCP Server capabilities by analyzing code.
    """

    def __init__(
        self,
        api_key: str = None,
        model: str = "gpt-4o",
        base_url: str = None,
    ):
        super().__init__(api_key=api_key, model=model, base_url=base_url)

    def _get_user_message(self, agent_path: str) -> str:
        return f"Generate an AgentCard for the MCP server at: {agent_path}"

    def _get_system_prompt(self) -> str:
        return """You are an MCP Manifest Generator Agent that analyzes MCP (Model Context Protocol) server code and generates an A2A-compliant AgentCard representing its capabilities.

Your goal: Analyze the MCP server's implementation to accurately extract its exposed Tools, Resources, and Prompts, and generate a compliant AgentCard.json mapping.

Available tools:
- glob_files: Find files matching patterns (like "**/*.py")
- read_file: Read file contents
- grep_code: Search for patterns in files
- analyze_python_functions: Extract function definitions from Python files
- generate_agentcard_json: Create the final AgentCard JSON

CRITICAL WORKFLOW:

1. **Find Files**:
   - Use glob_files to locate: __main__.py, *server*.py, *app*.py, main.py

2. **Read MCP Server Implementation**:
   - Read the main server file to understand what MCP Tools, Resources, and Prompts are defined.
   - Look for FastMCP decorators like @mcp.tool(), @mcp.resource(), @mcp.prompt()
   - Or standard MCP python sdk handlers.

3. **Extract Capabilities**:
   - For each MCP Tool:
     * map to an A2A "skill" with id (kebab-case name), name, description, tags, examples.
     * inputModes: ["application/json"]
     * outputModes: ["application/json", "text/plain"]
   - You MUST extract the name and docstring of every tool carefully.

4. **Determine Transport Protocol**:
   - MCP servers typically use "stdio" when executed directly, or "sse" (Server-Sent Events) over HTTP.
   - For Nasiko, we will wrap them in an HTTP bridge, so set preferred_transport to "HTTP+JSON".
   
5. **Generate AgentCard**:
   - Pass the determined capabilities to generate_agentcard_json.
   - Include streaming=False, push_notifications=False, state_transition_history=False, chat_agent=False unless explicitly custom-implemented.
   - Set agentFramework to "mcp" or "fastmcp".

IMPORTANT:
- Focus on accurately grabbing the list of tools. They will be registered as skills.
- Be accurate and provide clear descriptions for each tool.
"""

    def _get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "glob_files",
                    "description": "Find files matching a glob pattern",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {"type": "string"},
                            "base_path": {"type": "string"},
                        },
                        "required": ["pattern"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read contents of a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                        },
                        "required": ["file_path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "grep_code",
                    "description": "Search for pattern in a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {"type": "string"},
                            "file_path": {"type": "string"},
                            "case_sensitive": {"type": "boolean"},
                        },
                        "required": ["pattern", "file_path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_python_functions",
                    "description": "Extract function definitions from Python file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                        },
                        "required": ["file_path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_agentcard_json",
                    "description": "Generate A2A-compliant AgentCard JSON mapping MCP capabilities.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "agent_name": {"type": "string"},
                            "description": {"type": "string"},
                            "skills": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "name": {"type": "string"},
                                        "description": {"type": "string"},
                                        "tags": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "examples": {
                                            "type": "array",
                                            "items": {"type": "object"},
                                        },
                                        "inputModes": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "outputModes": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                    "required": ["id", "name", "description"],
                                },
                            },
                            "version": {"type": "string"},
                            "streaming": {"type": "boolean"},
                            "push_notifications": {"type": "boolean"},
                            "state_transition_history": {"type": "boolean"},
                            "chat_agent": {"type": "boolean"},
                            "default_input_modes": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "default_output_modes": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "preferred_transport": {"type": "string"},
                            "agentFramework": {"type": "string"},
                        },
                        "required": ["agent_name", "description", "skills"],
                    },
                },
            },
        ]
