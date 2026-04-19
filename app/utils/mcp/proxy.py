"""
MCP Tool Proxy for Nasiko Agents.
Automatically connects to associated MCP servers and registers their tools
into the agent's framework (CrewAI, LangChain, etc.).
"""

import os
import json
import logging
import asyncio
import threading
import importlib
from typing import List, Dict, Any, Optional

# Configure logging
logger = logging.getLogger("nasiko-mcp")
logger.setLevel(logging.INFO)

# Global list of discovered MCP tools
_MCP_TOOLS = []
_INITIALIZED = False


class MCPToolProxy:
    """A proxy that represents an MCP tool in the native agent framework"""
    
    def __init__(self, server_id: str, tool_name: str, description: str, input_schema: dict, bridge_url: str):
        self.server_id = server_id
        self.name = f"{server_id}_{tool_name}"
        self.tool_name = tool_name
        self.description = description
        self.input_schema = input_schema
        self.bridge_url = bridge_url

    def __call__(self, *args, **kwargs):
        """Execute the tool by calling the MCP server via the SSE bridge"""
        # This needs to be synchronous if called from a sync agent
        return asyncio.run(self.call_mcp_tool(*args, **kwargs))

    async def call_mcp_tool(self, *args, **kwargs):
        """Async implementation of tool call"""
        from mcp import ClientSession
        from mcp.client.sse import sse_client
        
        async with sse_client(self.bridge_url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(self.tool_name, kwargs)
                return result.content


def bootstrap_mcp(framework: Optional[str] = None):
    """
    Initializes MCP tool discovery and patches the agent framework.
    Called automatically at agent startup via injected code.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return
    
    mcp_servers_json = os.getenv("NASIKO_MCP_SERVERS")
    if not mcp_servers_json:
        logger.info("No connected MCP servers found in environment (NASIKO_MCP_SERVERS).")
        return

    try:
        mcp_servers = json.loads(mcp_servers_json)
        logger.info(f"Discovered {len(mcp_servers)} connected MCP servers.")
        
        # Discover tools from all servers (synchronously for bootstrap)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        discovered_tools = loop.run_until_complete(_discover_all_tools(mcp_servers))
        
        if not discovered_tools:
            logger.info("No tools found on the connected MCP servers.")
            return

        # Patch the framework
        _apply_framework_patches(discovered_tools, framework)
        
        _INITIALIZED = True
        logger.info(f"✅ Successfully injected {len(discovered_tools)} MCP tools into the framework.")

    except Exception as e:
        logger.error(f"❌ Failed to bootstrap MCP tools: {e}")


async def _discover_all_tools(mcp_servers: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Connect to each server and list its tools"""
    from mcp import ClientSession
    from mcp.client.sse import sse_client
    
    all_tools = []
    
    for server in mcp_servers:
        server_id = server["id"]
        server_url = server["url"]
        
        try:
            logger.info(f"Connecting to MCP server '{server_id}' at {server_url}...")
            async with sse_client(server_url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools_result = await session.list_tools()
                    
                    for tool in tools_result.tools:
                        all_tools.append({
                            "server_id": server_id,
                            "name": tool.name,
                            "description": tool.description,
                            "input_schema": tool.inputSchema,
                            "url": server_url
                        })
                        logger.info(f"  - Found tool: {server_id}_{tool.name}")
        except Exception as e:
            logger.error(f"Failed to discover tools from server '{server_id}': {e}")
            
    return all_tools


def _apply_framework_patches(tools: List[Dict[str, Any]], framework: Optional[str]):
    """Monkeypatch the agent framework to automatically include MCP tools"""
    
    # Auto-detect framework if not provided
    if not framework:
        if importlib.util.find_spec("crewai"):
            framework = "crewai"
        elif importlib.util.find_spec("langchain"):
            framework = "langchain"

    if framework == "crewai":
        _patch_crewai(tools)
    elif framework == "langchain":
        _patch_langchain(tools)
    else:
        logger.warning(f"Framework '{framework}' not supported for auto-injection. You may need to manually add tools.")


def _patch_crewai(tools: List[Dict[str, Any]]):
    """Patch CrewAI Agent to include MCP tools"""
    try:
        from crewai import Agent
        from langchain.tools import Tool
        
        # Convert MCP tools to LangChain tools (which CrewAI uses)
        lc_tools = []
        for t in tools:
            proxy = MCPToolProxy(t["server_id"], t["name"], t["description"], t["input_schema"], t["url"])
            lc_tool = Tool(
                name=proxy.name,
                description=proxy.description,
                func=proxy.__call__
            )
            lc_tools.append(lc_tool)

        original_init = Agent.__init__

        def patched_init(self, *args, **kwargs):
            if "tools" not in kwargs or kwargs["tools"] is None:
                kwargs["tools"] = []
            
            # Add MCP tools if they aren't already there
            existing_tool_names = {t.name for t in kwargs["tools"]}
            for mcp_tool in lc_tools:
                if mcp_tool.name not in existing_tool_names:
                    kwargs["tools"].append(mcp_tool)
            
            original_init(self, *args, **kwargs)

        Agent.__init__ = patched_init
        logger.info("Monkeypatched crewai.Agent to automatically include MCP tools.")

    except ImportError:
        logger.warning("CrewAI not found, skipping patch.")


def _patch_langchain(tools: List[Dict[str, Any]]):
    """Patch LangChain AgentExecutor to include MCP tools"""
    try:
        from langchain.agents import AgentExecutor
        from langchain.tools import Tool
        
        # Convert MCP tools to LangChain tools
        lc_tools = []
        for t in tools:
            proxy = MCPToolProxy(t["server_id"], t["name"], t["description"], t["input_schema"], t["url"])
            lc_tool = Tool(
                name=proxy.name,
                description=proxy.description,
                func=proxy.__call__
            )
            lc_tools.append(lc_tool)

        original_init = AgentExecutor.__init__

        def patched_init(self, *args, **kwargs):
            if "tools" not in kwargs or kwargs["tools"] is None:
                kwargs["tools"] = []
            
            # Add MCP tools if they aren't already there
            existing_tool_names = {t.name for t in kwargs["tools"]}
            for mcp_tool in lc_tools:
                if mcp_tool.name not in existing_tool_names:
                    kwargs["tools"].append(mcp_tool)
            
            original_init(self, *args, **kwargs)

        AgentExecutor.__init__ = patched_init
        logger.info("Monkeypatched langchain.agents.AgentExecutor to automatically include MCP tools.")

    except ImportError:
        logger.warning("LangChain AgentExecutor not found, skipping patch.")
