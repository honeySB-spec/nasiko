"""
Agent Builder
Handles agent instrumentation, building, and deployment.
"""

import tempfile
import shutil
import yaml
import logging
import asyncio
from pathlib import Path
from docker_utils import run_cmd
from registry_manager import RegistryManager
from instrumentation_injector import InstrumentationInjector
from config import AGENTS_DIRECTORY, DOCKER_NETWORK, Config

logger = logging.getLogger(__name__)


class AgentBuilder:
    """Handles building and deploying agents with instrumentation"""

    def __init__(self, logger=None):
        self.agents_dir = Path(AGENTS_DIRECTORY)
        self.registry_manager = RegistryManager()
        self.injector = InstrumentationInjector()
        self.logger = logger or logging.getLogger(__name__)

    def instrument_and_build_agents(self, owner_id=None):
        """Instrument and build all agents"""
        if not self.agents_dir.exists():
            logger.error(f"Agents directory {AGENTS_DIRECTORY} not found")
            return False

        success_count = 0
        total_count = 0

        for agent_folder in self.agents_dir.iterdir():
            if not agent_folder.is_dir():
                continue

            total_count += 1

            if self.build_single_agent(agent_folder.name, owner_id=owner_id):
                success_count += 1

        logger.info(f"Successfully built {success_count}/{total_count} agents")
        return success_count == total_count

    def build_single_agent(self, agent_folder_name, owner_id=None):
        """Build a single agent with instrumentation"""
        agent_folder = self.agents_dir / agent_folder_name

        if not agent_folder.is_dir():
            logger.error(f"Agent folder not found: {agent_folder}")
            return False

        # Validate docker-compose.yml exists and container names match
        if not self._validate_agent_structure(agent_folder):
            return False

        logger.info(f"Building agent: {agent_folder_name}")

        try:
            # Create temp directory and copy agent files
            temp_dir = Path(tempfile.mkdtemp())
            agent_temp_path = temp_dir / agent_folder_name
            shutil.copytree(agent_folder, agent_temp_path)

            # Build instrumented Docker image
            if not self._build_instrumented_image(
                agent_temp_path, agent_folder_name, None
            ):
                return False

            # Deploy agent with updated compose
            if not self._deploy_agent(agent_temp_path, agent_folder_name):
                return False

            # Update agent registry
            registry_result = self.registry_manager.update_agent_registry(
                agent_folder_name, action="upsert", owner_id=owner_id
            )

            # Cleanup temp directory
            shutil.rmtree(temp_dir)

            if registry_result.get("success", False):
                logger.info(
                    f"Successfully built and registered agent: {agent_folder_name}"
                )
                logger.info(f"Agent URL: {registry_result.get('url')}")
            else:
                logger.warning(
                    f"Agent built but registry update failed: {agent_folder_name}"
                )

            return True

        except Exception as e:
            logger.error(f"Error building agent {agent_folder_name}: {str(e)}")
            return False

    async def build_and_deploy_agent(
        self,
        agent_name: str,
        agent_path: str,
        base_url: str = "http://localhost:8000",
        owner_id=None,
    ):
        """
        Async method to build and deploy a single agent

        Args:
            agent_name: Name of the agent
            agent_path: Full path to agent directory on host
            base_url: Base URL for agent service
            owner_id: Owner ID

        Returns:
            Dict with success status and details
        """
        try:
            self.logger.info(
                f"Starting build and deploy for agent '{agent_name}' at '{agent_path}'"
            )

            agent_folder = Path(agent_path)

            if not agent_folder.exists() or not agent_folder.is_dir():
                return {
                    "success": False,
                    "error": f"Agent directory does not exist: {agent_path}",
                }

            # Validate agent structure
            if not self._validate_agent_structure(agent_folder):
                return {
                    "success": False,
                    "error": f"Invalid agent structure for {agent_name}",
                }

            # Run the build in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, self._build_agent_sync, agent_name, agent_path, base_url, owner_id
            )

            return result

        except Exception as e:
            self.logger.error(f"Error in build_and_deploy_agent for {agent_name}: {e}")
            return {"success": False, "error": f"Build and deploy failed: {str(e)}"}

    def _build_agent_sync(
        self, agent_name: str, agent_path: str, base_url: str, owner_id=None
    ):
        """Synchronous method to build and deploy agent"""
        try:
            agent_folder = Path(agent_path)

            # Create temp directory and copy agent files
            temp_dir = Path(tempfile.mkdtemp())
            agent_temp_path = temp_dir / agent_name
            shutil.copytree(agent_folder, agent_temp_path)

            # Build instrumented Docker image
            if not self._build_instrumented_image(agent_temp_path, agent_name, None):
                shutil.rmtree(temp_dir)
                return {
                    "success": False,
                    "error": f"Failed to build Docker image for {agent_name}",
                }

            # Deploy agent with updated compose
            if not self._deploy_agent(agent_temp_path, agent_name):
                shutil.rmtree(temp_dir)
                return {
                    "success": False,
                    "error": f"Failed to deploy agent {agent_name}",
                }

            # Update agent registry
            registry_result = self.registry_manager.update_agent_registry(
                agent_name, action="upsert", owner_id=owner_id
            )

            # Cleanup temp directory
            shutil.rmtree(temp_dir)

            # Get agent URL from registry result (the actual URL from container port)
            url = registry_result.get("url") or f"{base_url}/agents/{agent_name}"
            registry_success = registry_result.get("success", False)
            registry_id = registry_result.get("registry_id")

            result = {
                "success": True,
                "agent_name": agent_name,
                "url": url,
                "service_name": agent_name,
                "container_id": None,  # Could be retrieved from docker inspect if needed
                "registry_updated": registry_success,
                "registry_id": registry_id,
            }

            if registry_success:
                self.logger.info(
                    f"Successfully built and registered agent: {agent_name}"
                )
                self.logger.info(f"Agent URL: {url}")
                if registry_id:
                    self.logger.info(f"Registry ID: {registry_id}")
            else:
                self.logger.warning(
                    f"Agent built but registry update failed: {agent_name}"
                )
                result["warning"] = "Registry update failed"

            return result

        except Exception as e:
            self.logger.error(f"Error in _build_agent_sync for {agent_name}: {e}")
            return {"success": False, "error": f"Synchronous build failed: {str(e)}"}

    def _validate_agent_structure(self, agent_folder):
        """Validate agent has required structure and container name matches folder name"""
        agent_folder_name = agent_folder.name
        compose_path = agent_folder / "docker-compose.yml"

        if not compose_path.exists():
            # Check if this could be an MCP agent
            agentcard_path = agent_folder / "AgentCard.json"
            if agentcard_path.exists():
                try:
                    with open(agentcard_path, "r") as fac:
                        ac = yaml.safe_load(fac)
                        if ac.get("agentFramework", "").lower() in ("mcp", "fastmcp", "mcp_server"):
                            logger.info("MCP framework detected. Will auto-generate missing docker-compose.")
                            self._ensure_mcp_configs(agent_folder, agent_folder_name)
                except Exception as e:
                    logger.error(f"Failed to read AgentCard.json while checking for MCP framework: {e}")
            if not compose_path.exists():
                logger.error(
                    f"No docker-compose.yml found for {agent_folder_name}, skipping..."
                )
                return False

        # Validate docker-compose.yml has valid structure and container names
        try:
            with open(compose_path, "r") as f:
                compose_data = yaml.safe_load(f)

            # Check if services section exists
            services = compose_data.get("services", {})
            if not services:
                logger.error(
                    f"No services found in docker-compose.yml for {agent_folder_name}, skipping..."
                )
                return False

            # Check if agent folder name matches any container name
            container_names = []
            for service_name, service_config in services.items():
                container_name = service_config.get("container_name", service_name)
                container_names.append(container_name)

            # Enforce that folder name matches at least one container name
            if agent_folder_name not in container_names:
                logger.error(
                    f"Agent folder name '{agent_folder_name}' must match one of the container names {container_names}"
                )
                return False

            logger.info(
                f"Agent '{agent_folder_name}' has valid structure with {len(services)} service(s) and matching container name"
            )
            return True

        except Exception as e:
            logger.error(
                f"Error reading docker-compose.yml for {agent_folder_name}: {e}, skipping..."
            )
            return False
    def _ensure_mcp_configs(self, agent_path: Path, agent_name: str):
        """Generate MCP stdio-to-HTTP bridge and Docker configs if it is an MCP server"""
        from textwrap import dedent
        
        # Determine if it's an MCP server
        is_mcp = False
        # Try both names and casings
        card_paths = [
            agent_path / "mcp_manifest.json", 
            agent_path / "AgentCard.json", 
            agent_path / "Agentcard.json"
        ]
        for cp in card_paths:
            if cp.exists():
                try:
                    import json
                    with open(cp, "r") as f:
                        ac = json.load(f)
                    framework = ac.get("agentFramework", "").lower()
                    if framework in ("mcp", "fastmcp", "mcp_server", "mcp-server"):
                        is_mcp = True
                        break
                except:
                    # Try yaml if json fails
                    try:
                        import yaml
                        with open(cp, "r") as f:
                            ac = yaml.safe_load(f)
                        framework = ac.get("agentFramework", "").lower()
                        if framework in ("mcp", "fastmcp", "mcp_server", "mcp-server"):
                            is_mcp = True
                            break
                    except:
                        pass
        
        if not is_mcp:
            return

        bridge_path = agent_path / "mcp_bridge.py"
        dockerfile_path = agent_path / "Dockerfile"
        compose_path = agent_path / "docker-compose.yml"
        
        if not bridge_path.exists():
            # Robust JSON-RPC bridge that proxies between SSE and Stdio
            bridge_path.write_text(dedent("""\
                import asyncio
                import json
                import os
                import sys
                import logging
                from typing import Optional
                from fastapi import FastAPI, Request
                from fastapi.responses import JSONResponse
                from sse_starlette.sse import EventSourceResponse
                import uvicorn

                # Configure logging
                logging.basicConfig(level=logging.INFO)
                logger = logging.getLogger("mcp-bridge")

                app = FastAPI(title="MCP HTTP Bridge")

                # Configuration for the target stdio server
                # Default to 'python src/main.py' if not specified
                # We assume the server entry point is src/main.py or specified by MCP_TARGET_CMD
                TARGET_CMD = os.environ.get("MCP_TARGET_CMD", "python src/main.py")

                class StdioProxy:
                    def __init__(self, cmd_string):
                        self.cmd_string = cmd_string
                        self.process: Optional[asyncio.subprocess.Process] = None
                        self.queue = asyncio.Queue()
                        self.read_task = None

                    async def start(self):
                        logger.info(f"Starting target MCP server: {self.cmd_string}")
                        try:
                            self.process = await asyncio.create_subprocess_shell(
                                self.cmd_string,
                                stdin=asyncio.subprocess.PIPE,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE
                            )
                            self.read_task = asyncio.create_task(self._read_stdout())
                            asyncio.create_task(self._read_stderr())
                        except Exception as e:
                            logger.error(f"Failed to start target MCP server: {e}")
                            raise

                    async def _read_stdout(self):
                        try:
                            while True:
                                line = await self.process.stdout.readline()
                                if not line:
                                    logger.info("Target MCP server stdout closed")
                                    break
                                await self.queue.put(line.decode())
                        except Exception as e:
                            logger.error(f"Error reading stdout: {e}")

                    async def _read_stderr(self):
                        try:
                            while True:
                                line = await self.process.stderr.readline()
                                if not line:
                                    break
                                logger.warning(f"Target STDERR: {line.decode().strip()}")
                        except Exception as e:
                            logger.error(f"Error reading stderr: {e}")

                    async def send(self, data: str):
                        if not self.process or not self.process.stdin:
                            logger.error("Process not started or stdin not available")
                            return
                        self.process.stdin.write(data.encode() + b"\\n")
                        await self.process.stdin.drain()

                proxy = StdioProxy(TARGET_CMD)

                @app.on_event("startup")
                async def startup():
                    await proxy.start()

                @app.get("/sse")
                async def sse_endpoint(request: Request):
                    async def event_publisher():
                        try:
                            while True:
                                if await request.is_disconnected():
                                    break
                                try:
                                    # Wait for data from the queue (from stdio stdout)
                                    data = await asyncio.wait_for(proxy.queue.get(), timeout=1.0)
                                    yield {"data": data.strip()}
                                except asyncio.TimeoutError:
                                    # Keepalive comment
                                    yield {"comment": "keepalive"}
                        except Exception as e:
                            logger.error(f"SSE Error: {e}")

                    return EventSourceResponse(event_publisher())

                @app.post("/messages")
                async def messages_endpoint(request: Request):
                    try:
                        data = await request.body()
                        await proxy.send(data.decode())
                        return JSONResponse({"status": "ok"})
                    except Exception as e:
                        logger.error(f"Error sending message to stdio: {e}")
                        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)

                if __name__ == "__main__":
                    port = int(os.environ.get("PORT", 8000))
                    uvicorn.run(app, host="0.0.0.0", port=port)
            """))
            logger.info("Generated robust JSON-RPC bridge (mcp_bridge.py)")
        
        if not dockerfile_path.exists() or "mcp_bridge" not in dockerfile_path.read_text():
            dockerfile_path.write_text(dedent("""\
                FROM python:3.11-slim
                WORKDIR /app
                COPY . .
                RUN pip install fastapi uvicorn sse-starlette mcp || true
                RUN if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
                EXPOSE 8000
                ENV PORT=8000
                # Injected by orchestrator if needed
                ENV MCP_TARGET_CMD="python src/main.py"
                CMD ["python", "mcp_bridge.py"]
            """))
            logger.info("Generated Dockerfile for MCP bridge")
            
        if not compose_path.exists():
            # For local testing compat
            compose_path.write_text(dedent(f"""\
                version: '3.8'
                services:
                  {agent_name}:
                    build: .
                    container_name: {agent_name}
                    ports:
                      - "8000:8000"
                    environment:
                      - MCP_TARGET_CMD=python src/main.py
            """))
            logger.info("Generated docker-compose.yml for MCP")

    def _build_instrumented_image(
        self, agent_temp_path, agent_folder_name, agent_api_key
    ):
        """Build Docker image with instrumentation"""
        dockerfile_path = agent_temp_path / "Dockerfile"
        if not dockerfile_path.exists():
            logger.error(f"No Dockerfile found for {agent_folder_name}, skipping...")
            return False

        try:
            # Check if image already exists locally (optimization for re-deployments)
            image_tag = f"{agent_folder_name}_instrumented"
            result = run_cmd(["docker", "image", "inspect", image_tag], check=False)

            if result.returncode == 0:
                logger.info(
                    f"Docker image already exists: {image_tag} - reusing cached image (fast path)"
                )
                return True

            logger.info(f"Building new instrumented image for {agent_folder_name}")

            # Check if image already exists locally (optimization for re-deployments)
            image_tag = f"{agent_folder_name}_instrumented"
            result = run_cmd(["docker", "image", "inspect", image_tag], check=False)

            if result.returncode == 0:
                logger.info(
                    f"Docker image already exists: {image_tag} - reusing cached image (fast path)"
                )
                return True

            logger.info(f"Building new instrumented image for {agent_folder_name}")

            dockerfile_content = dockerfile_path.read_text()

            # Inject comprehensive instrumentation packages
            instrumentation_install = f"""
            # Install exact versions from pyproject.toml
            RUN pip install uv uvicorn \\
                "opentelemetry-distro>=0.57b0" \\
                opentelemetry-sdk \\
                "opentelemetry-exporter-otlp>=1.36.0" \\
                "opentelemetry-exporter-otlp-proto-http>=1.36.0" \\
                opentelemetry-instrumentation \\
                "opentelemetry-instrumentation-asgi>=0.57b0" \\
                "opentelemetry-instrumentation-fastapi>=0.57b0" \\
                opentelemetry-instrumentation-django \\
                opentelemetry-instrumentation-flask \\
                opentelemetry-instrumentation-requests \\
                opentelemetry-instrumentation-httpx \\
                opentelemetry-instrumentation-aiohttp-client \\
                opentelemetry-instrumentation-pymongo \\
                opentelemetry-instrumentation-psycopg2 \\
                opentelemetry-instrumentation-sqlalchemy \\
                opentelemetry-instrumentation-redis \\
                opentelemetry-instrumentation-boto3sqs \\
                
            ENV ROOT_PATH=/{agent_folder_name}
            """

            # Append the instrumentation packages and env vars
            dockerfile_content = dockerfile_content + "\n" + instrumentation_install
            dockerfile_path.write_text(dockerfile_content)

            # Build instrumented image with real-time output
            image_tag = f"{agent_folder_name}_instrumented"
            logger.info(f"Building Docker image: {image_tag}")

            # Use subprocess directly for real-time output
            import subprocess

            process = subprocess.Popen(
                ["docker", "build", "-t", image_tag, str(agent_temp_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            # Stream output in real-time
            output_lines = []
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    print(line.rstrip())  # Print to console in real-time
                    output_lines.append(line.rstrip())

            return_code = process.poll()

            if return_code == 0:
                logger.info(f"Successfully built instrumented image: {image_tag}")
                return True
            else:
                logger.error(
                    f"Failed to build image for {agent_folder_name} (exit code: {return_code})"
                )
                # Full output is already printed, but log the last few lines for context
                if output_lines:
                    logger.error("Last few lines of build output:")
                    for line in output_lines[-10:]:  # Show last 10 lines
                        logger.error(f"  {line}")
                return False

        except Exception as e:
            logger.error(
                f"Error building instrumented image for {agent_folder_name}: {e}"
            )
            return False

    def _deploy_agent(self, agent_temp_path, agent_folder_name):
        """Deploy agent using docker-compose"""
        compose_path = agent_temp_path / "docker-compose.yml"

        if not compose_path.exists():
            logger.error(
                f"No docker-compose.yml found for {agent_folder_name}, skipping deployment"
            )
            return False

        try:
            # Load compose file
            with open(compose_path, "r") as f:
                compose_data = yaml.safe_load(f)

            # Ensure networks section exists
            if "networks" not in compose_data:
                compose_data["networks"] = {}

            # Add agents network
            compose_data["networks"]["agents-net"] = {
                "external": True,
                "name": DOCKER_NETWORK,
            }

            # Attach services to agents network & preserve original networks
            for _, svc_def in compose_data.get("services", {}).items():
                if "networks" not in svc_def:
                    svc_def["networks"] = []

                # Convert dict to list if needed
                if isinstance(svc_def["networks"], dict):
                    svc_def["networks"] = list(svc_def["networks"].keys())

                # Ensure agents network is attached
                if DOCKER_NETWORK not in svc_def["networks"]:
                    svc_def["networks"].append(DOCKER_NETWORK)

            # Update services to use pre-built instrumented image and inject API keys
            image_tag = f"{agent_folder_name}_instrumented"
            api_key_env = {
                "OPENAI_API_KEY": Config.OPENAI_API_KEY,
                "OPENROUTER_API_KEY": Config.OPENROUTER_API_KEY,
                "MINIMAX_API_KEY": Config.MINIMAX_API_KEY,
            }
            for service_name, svc_def in compose_data.get("services", {}).items():
                if service_name == agent_folder_name and "build" in svc_def:
                    svc_def.pop("build", None)
                    svc_def["image"] = image_tag

                # Inject actual API key values directly (bypasses yaml/shell substitution issues)
                env = svc_def.get("environment", [])
                if isinstance(env, list):
                    new_env = []
                    for item in env:
                        if isinstance(item, str):
                            key = item.split("=")[0]
                            if key in api_key_env and api_key_env[key]:
                                new_env.append(f"{key}={api_key_env[key]}")
                                continue
                        new_env.append(item)
                    svc_def["environment"] = new_env

            # Save updated compose
            with open(compose_path, "w") as f:
                yaml.dump(compose_data, f)

            # Deploy agent — use --env-file so docker compose loads the agent's .env
            # regardless of the process working directory (which is the nasiko root, not the agent dir)
            compose_cmd = [
                "docker",
                "compose",
                "-f",
                str(compose_path),
            ]
            env_file = agent_temp_path / ".env"
            if env_file.exists():
                compose_cmd.extend(["--env-file", str(env_file)])
                logger.info(f"Loading agent env file: {env_file}")
            compose_cmd.extend(["up", "-d"])
            result = run_cmd(
                compose_cmd, check=False
            )  # Don't raise exception on failure

            if result.returncode == 0:
                logger.info(f"Successfully deployed agent: {agent_folder_name}")
                return True
            else:
                logger.error(f"Failed to deploy agent {agent_folder_name}:")
                logger.error(f"Return code: {result.returncode}")
                if result.stdout:
                    logger.error(f"Docker compose stdout:\n{result.stdout}")
                if result.stderr:
                    logger.error(f"Docker compose stderr:\n{result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Error deploying agent {agent_folder_name}: {e}")
            return False
