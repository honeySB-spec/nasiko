"""
Base Generator Agent
Common scaffolding for manifest/card generation agents
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI
from tools import AgentAnalyzerTools

logger = logging.getLogger(__name__)


class BaseGeneratorAgent:
    """
    Base class for agents that generate manifests (AgentCards, MCP manifests, etc.)
    by analyzing code using an LLM reasoning loop.
    """

    def __init__(
        self,
        api_key: str = None,
        model: str = "gpt-4o",
        base_url: str = None,
    ):
        """
        Initialize the base agent

        Args:
            api_key: OpenAI-compatible API key
            model: Model to use for reasoning
            base_url: Custom base URL for the API
        """
        self.api_key = (
            api_key or os.getenv("OPENAI_API_KEY") or os.getenv("MINIMAX_API_KEY")
        )
        if not self.api_key:
            logger.error("API KEY not found in environment or arguments")
            raise ValueError("API key (OPENAI_API_KEY or MINIMAX_API_KEY) must be set")

        # Auto-detect MiniMax provider if necessary
        if (
            not base_url
            and not api_key
            and not os.getenv("OPENAI_API_KEY")
            and os.getenv("MINIMAX_API_KEY")
        ):
            base_url = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.io/v1")
            if model == "gpt-4o":
                model = os.getenv("MINIMAX_MODEL", "MiniMax-M2.7")

        logger.info(f"Initializing {self.__class__.__name__} with model: {model}")
        self.client = OpenAI(api_key=self.api_key, base_url=base_url)
        self.model = model
        self.tools = AgentAnalyzerTools()
        self.max_iterations = 10

    def _get_system_prompt(self) -> str:
        """Override in subclass to provide the system prompt"""
        raise NotImplementedError("Subclasses must implement _get_system_prompt")

    def _get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Override in subclass to provide tool schemas"""
        raise NotImplementedError("Subclasses must implement _get_tool_schemas")

    def _get_user_message(self, agent_path: str) -> str:
        """Override in subclass to provide the initial user message"""
        raise NotImplementedError("Subclasses must implement _get_user_message")

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool and return result"""
        logger.debug(f"Executing tool: {tool_name} with args: {arguments}")
        if hasattr(self.tools, tool_name):
            method = getattr(self.tools, tool_name)
            try:
                result = method(**arguments)
                logger.debug(f"Tool {tool_name} result status: {result.get('status')}")
                return result
            except Exception as e:
                logger.error(f"Error executing tool {tool_name}: {e}")
                return {"status": "error", "message": str(e)}
        else:
            logger.error(f"Tool '{tool_name}' not found")
            return {"status": "error", "message": f"Tool '{tool_name}' not found"}

    def generate_agentcard(
        self, agent_path: str, verbose: bool = False
    ) -> Dict[str, Any]:
        """
        Common reasoning loop for generating a manifest/card

        Args:
            agent_path: Path to the agent/server directory
            verbose: Whether to print detailed progress

        Returns:
            Dictionary with generated data and status
        """
        success_tool_name = "generate_agentcard_json"
        logger.info(f"Starting generation for: {agent_path}")

        user_message = self._get_user_message(agent_path)

        messages = [
            {"role": "system", "content": self._get_system_prompt()},
            {"role": "user", "content": user_message},
        ]

        iteration = 0
        final_data = None

        while iteration < self.max_iterations:
            iteration += 1
            logger.debug(f"Starting iteration {iteration}/{self.max_iterations}")

            if verbose:
                print(f"\n[Iteration {iteration}]")

            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=self._get_tool_schemas(),
                    tool_choice="auto",
                    temperature=0.1,
                    max_tokens=4000,
                )

                message = response.choices[0].message
                assistant_message = {
                    "role": "assistant",
                    "content": message.content or "",
                }
                if message.tool_calls:
                    assistant_message["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in message.tool_calls
                    ]
                messages.append(assistant_message)

                if verbose and message.content:
                    print(f"Agent: {message.content}")

                if message.tool_calls:
                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        arguments = json.loads(tool_call.function.arguments)

                        if verbose:
                            print(f"  → Calling tool: {tool_name}")

                        result = self._execute_tool(tool_name, arguments)

                        if verbose:
                            if result.get("status") == "success":
                                print(f"    ✓ {result.get('message', 'Success')}")
                            else:
                                print(f"    ✗ {result.get('message', 'Error')}")

                        if (
                            tool_name == success_tool_name
                            and result.get("status") == "success"
                        ):
                            final_data = result.get("agentcard")

                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps(result),
                            }
                        )
                    continue

                break

            except Exception as e:
                logger.exception(f"Error during execution at iteration {iteration}: {e}")
                return {
                    "status": "error",
                    "message": f"Error during execution: {str(e)}",
                    "agentcard": None,
                }

        if iteration >= self.max_iterations:
            logger.warning(f"Maximum iterations ({self.max_iterations}) reached")
            return {
                "status": "error",
                "message": "Maximum iterations reached",
                "agentcard": final_data,
            }

        return {
            "status": "success",
            "message": "Generation completed successfully",
            "agentcard": final_data,
            "iterations": iteration,
        }
