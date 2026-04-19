"""
AgentCard Service

Service layer for generating A2A-compliant AgentCard.json files
using LLM-based analysis.
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any

from app.utils.agentcard_generator import AgentCardGeneratorAgent, MCPManifestGeneratorAgent


class AgentCardService:
    """
    Service for generating and managing A2A-compliant AgentCards
    """

    def __init__(self, logger, openai_api_key: Optional[str] = None):
        self.logger = logger
        self.openai_api_key = (
            openai_api_key
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("MINIMAX_API_KEY")
        )

    async def generate_and_save_agentcard(
        self,
        agent_path: str,
        agent_name: str,
        n8n_agent: bool,
        base_url: str = "http://localhost:8000",
        is_mcp: bool = False,
    ) -> bool:
        """
        Generate AgentCard.json file for an agent and save it to the agent directory

        Args:
            agent_path: Path to the agent directory
            agent_name: Name of the agent
            base_url: Base URL for the agent service
            n8n_agent: whether to generate n8n registry data
        Returns:
            True if AgentCard was generated successfully, False otherwise

        """

        try:
            self.logger.info(f"Generating AgentCard for {agent_name} at {agent_path}")

            # Initialize the appropriate generator agent
            if is_mcp:
                self.logger.info("Using MCP Manifest Generator Agent")
                generator = MCPManifestGeneratorAgent(
                    api_key=self.openai_api_key,
                    model="gpt-4o",
                )
            else:
                generator = AgentCardGeneratorAgent(
                    api_key=self.openai_api_key,
                    model="gpt-4o",
                    n8n_agent=n8n_agent,
                )

            # Generate AgentCard using the agent
            result = generator.generate_agentcard(agent_path=agent_path, verbose=False)

            if result["status"] != "success" or not result.get("agentcard"):
                self.logger.error(
                    f"Failed to generate AgentCard: {result.get('message')}"
                )
                return False

            agentcard = result["agentcard"]

            # Save AgentCard.json to the agent directory
            file_name = "mcp_manifest.json" if is_mcp else "AgentCard.json"
            agentcard_path = Path(agent_path) / file_name
            with open(agentcard_path, "w") as f:
                json.dump(agentcard, f, indent=2, ensure_ascii=False)

            self.logger.info(f"Successfully saved {file_name} to {agentcard_path}")
            return True

        except Exception as e:
            self.logger.error(
                f"Failed to generate AgentCard for {agent_name}: {str(e)}"
            )
            return False

    async def load_agentcard_from_file(
        self, agent_path: str
    ) -> Optional[Dict[str, Any]]:
        """
        Load AgentCard.json from an agent directory

        Args:
            agent_path: Path to the agent directory

        Returns:
            Dict containing AgentCard or None if file doesn't exist
        """

        try:
            agentcard_path = Path(agent_path) / "AgentCard.json"

            if not agentcard_path.exists():
                mcp_path = Path(agent_path) / "mcp_manifest.json"
                if mcp_path.exists():
                    agentcard_path = mcp_path
                else:
                    self.logger.warning(f"Manifest not found in {agent_path}")
                    return None

            with open(agentcard_path, "r") as f:
                agentcard = json.load(f)

            self.logger.info(f"Successfully loaded AgentCard from {agentcard_path}")
            return agentcard

        except Exception as e:
            self.logger.error(f"Failed to load AgentCard from {agent_path}: {str(e)}")
            return None

    async def generate_registry_data(
        self,
        agent_path: str,
        agent_name: str,
        url: str,
        base_url: str = "http://localhost:8000",
        n8n_agent: bool = False,
        is_mcp: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate registry data for an agent from AgentCard

        Args:
            agent_path: Path to the agent directory
            agent_name: Name of the agent
            url: URL where the agent is deployed
            base_url: Base URL for the agent service
            n8n_agent: whether to generate n8n registry data

        Returns:
            Dict in registry format ready for database insertion
        """

        try:
            # First try to load existing AgentCard.json
            agentcard = await self.load_agentcard_from_file(agent_path)

            if not agentcard:
                # Generate new AgentCard if file doesn't exist
                self.logger.info(
                    f"No existing AgentCard found, generating new one for {agent_name}"
                )
                await self.generate_and_save_agentcard(
                    agent_path, agent_name, n8n_agent, base_url, is_mcp=True if agent_name.endswith('-mcp') else False # We need to properly propagate is_mcp down here if necessary, but this happens after upload. Let's fix this up by accepting is_mcp here as well.
                )
                agentcard = await self.load_agentcard_from_file(agent_path)

            if not agentcard:
                # Fallback if generation failed
                self.logger.warning(
                    f"Failed to generate AgentCard for {agent_name}, using minimal registry data"
                )
                return self._create_minimal_registry_data(agent_name, url)

            # Convert AgentCard to registry format
            registry_data = self._convert_to_registry_format(agentcard, url)

            self.logger.info(f"Successfully generated registry data for {agent_name}")
            return registry_data

        except Exception as e:
            self.logger.error(
                f"Failed to generate registry data for {agent_name}: {str(e)}"
            )
            return self._create_minimal_registry_data(agent_name, url)

    def _create_minimal_registry_data(
        self, agent_name: str, url: str
    ) -> Dict[str, Any]:
        """
        Create minimal registry data when AgentCard generation fails

        Args:
            agent_name: Name of the agent
            url: URL where the agent is deployed

        Returns:
            Minimal registry data following A2A schema
        """

        return {
            "name": agent_name,
            "description": f"Auto-uploaded agent: {agent_name}",
            "url": url,
            "version": "1.0.0",
            "capabilities": {
                "streaming": False,
                "pushNotifications": False,
                "stateTransitionHistory": False,
            },
            "defaultInputModes": ["application/json", "text/plain"],
            "defaultOutputModes": ["application/json"],
            "skills": [],
        }

    async def validate_agentcard_file(self, agent_path: str) -> bool:
        """
        Validate that AgentCard.json exists and has proper structure

        Args:
            agent_path: Path to the agent directory

        Returns:
            True if AgentCard file is valid, False otherwise
        """

        try:
            agentcard = await self.load_agentcard_from_file(agent_path)

            if not agentcard:
                return False

            # Basic validation for A2A AgentCard
            required_keys = [
                "name",
                "description",
                "url",
                "version",
                "capabilities",
                "skills",
            ]
            for key in required_keys:
                if key not in agentcard:
                    self.logger.error(f"Missing required key in AgentCard: {key}")
                    return False

            # Validate capabilities section
            capabilities = agentcard.get("capabilities", {})
            capability_keys = [
                "streaming",
                "pushNotifications",
                "stateTransitionHistory",
            ]

            for key in capability_keys:
                if key not in capabilities:
                    self.logger.warning(f"Missing capability key in AgentCard: {key}")

            self.logger.info("AgentCard file validation passed")
            return True

        except Exception as e:
            self.logger.error(f"Error validating AgentCard file: {str(e)}")
            return False

    def _convert_to_registry_format(
        self, agentcard: Dict[str, Any], url: str
    ) -> Dict[str, Any]:
        """
        Convert AgentCard.json format to registry database format

        Args:
            agentcard: Dict containing the A2A AgentCard structure
            url: URL where the agent is deployed

        Returns:
            Dict in registry format for database storage
        """

        # Update the url field for registry
        registry_data = agentcard.copy()
        registry_data["url"] = url

        self.logger.info(
            f"Converted AgentCard for {agentcard.get('name', 'unknown')} with {len(agentcard.get('skills', []))} skills"
        )

        return registry_data
