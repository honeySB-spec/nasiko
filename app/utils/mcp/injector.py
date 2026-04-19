import os
import shutil
import ast
import astor
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


class MCPInjector:
    """Handles automatic injection of MCP tool proxy into agent containers"""

    def __init__(self, mcp_source_path: str = "/app/utils/mcp"):
        self.mcp_source = mcp_source_path

    def inject_into_agent(self, agent_code_path: str, agent_name: str) -> bool:
        """
        Complete MCP injection process

        Args:
            agent_code_path: Path to agent source code
            agent_name: Name of the agent

        Returns:
            bool: Success/failure status
        """
        try:
            logger.info(f"🔄 Starting MCP tool injection for {agent_name}")

            # 1. Copy MCP module
            self._copy_mcp_module(agent_code_path)

            # 2. Find and modify main entry point
            main_file = self._find_main_file(agent_code_path)
            self._inject_mcp_code(main_file, agent_name)

            # 3. Update dependencies
            self._update_requirements(agent_code_path)

            # 4. Update Dockerfile if needed
            self._update_dockerfile(agent_code_path)

            logger.info(f"✅ MCP tool injection completed for {agent_name}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to inject MCP tools for {agent_name}: {e}")
            return False

    def _copy_mcp_module(self, agent_code_path: str):
        """Copy MCP module into agent directory"""
        utils_dir = os.path.join(agent_code_path, "utils")
        os.makedirs(utils_dir, exist_ok=True)

        dest_path = os.path.join(utils_dir, "mcp")
        if os.path.exists(dest_path):
            shutil.rmtree(dest_path)

        def ignore_patterns(dir, files):
            exclude = {"injector.py", "__pycache__"}
            return [f for f in files if f in exclude]

        shutil.copytree(self.mcp_source, dest_path, ignore=ignore_patterns)
        logger.info(f"📁 Copied MCP module to {dest_path}")

    def _find_main_file(self, agent_code_path: str) -> str:
        """Find the main entry point file"""
        candidates = ["__main__.py", "main.py", "app.py", "run.py", "server.py"]
        for candidate in candidates:
            full_path = os.path.join(agent_code_path, candidate)
            if os.path.exists(full_path):
                return full_path
        
        # Check src/
        src_dir = os.path.join(agent_code_path, "src")
        if os.path.exists(src_dir):
            for candidate in candidates:
                full_path = os.path.join(src_dir, candidate)
                if os.path.exists(full_path):
                    return full_path

        raise ValueError(f"No main entry point found in {agent_code_path}")

    def _inject_mcp_code(self, main_file: str, agent_name: str):
        """Inject MCP bootstrap code using AST"""
        try:
            with open(main_file, "r", encoding="utf-8") as f:
                source = f.read()

            tree = ast.parse(source)

            # Create import statement
            import_stmt = ast.ImportFrom(
                module="utils.mcp.proxy",
                names=[ast.alias("bootstrap_mcp", None)],
                level=0,
            )

            # Create bootstrap call
            bootstrap_call = ast.Expr(
                ast.Call(
                    func=ast.Name("bootstrap_mcp", ast.Load()),
                    args=[],
                    keywords=[],
                )
            )

            # Find insertion point (after existing imports)
            last_import_idx = -1
            for i, node in enumerate(tree.body):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    last_import_idx = i

            # Insert after last import
            tree.body.insert(last_import_idx + 1, import_stmt)
            tree.body.insert(last_import_idx + 2, bootstrap_call)

            # Write back
            modified_source = astor.to_source(tree)
            with open(main_file, "w", encoding="utf-8") as f:
                f.write(modified_source)

            logger.info(f"🔧 Injected MCP bootstrap code into {main_file}")

        except Exception as e:
            logger.error(f"Failed to inject MCP code: {e}")
            raise

    def _update_requirements(self, agent_code_path: str):
        """Add MCP dependencies to requirements.txt"""
        req_file = os.path.join(agent_code_path, "requirements.txt")
        dependencies = ["mcp[sse]>=0.1.0", "astor>=0.8.1"]

        if os.path.exists(req_file):
            with open(req_file, "a") as f:
                f.write("\n\n# MCP dependencies\n")
                for dep in dependencies:
                    f.write(f"{dep}\n")
        else:
            with open(req_file, "w") as f:
                f.write("# MCP dependencies\n")
                for dep in dependencies:
                    f.write(f"{dep}\n")

    def _update_dockerfile(self, agent_code_path: str):
        """Update Dockerfile to include utils/mcp"""
        dockerfile_path = os.path.join(agent_code_path, "Dockerfile")
        if not os.path.exists(dockerfile_path):
            return

        with open(dockerfile_path, "r") as f:
            content = f.read()

        if "COPY utils/" not in content and "COPY . /" not in content:
            # Add it before the CMD or after some other COPY
            if "COPY src/" in content:
                content = content.replace("COPY src/", "COPY utils/ /app/utils/\nCOPY src/")
            else:
                # Add before last line
                lines = content.splitlines()
                lines.insert(-1, "COPY utils/ /app/utils/")
                content = "\n".join(lines)

        with open(dockerfile_path, "w") as f:
            f.write(content)
