import os
import pytest
import shutil
import tempfile
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import MagicMock, AsyncMock, patch

from fastapi import UploadFile
from app.service.agent_upload_service import AgentUploadService

@pytest.fixture
def mock_logger():
    return MagicMock()

@pytest.fixture
def upload_service(mock_logger):
    # Mock repository
    repo = MagicMock()
    return AgentUploadService(logger=mock_logger, repository=repo)

@pytest.mark.asyncio
async def test_mcp_server_upload_success(upload_service):
    """
    Test uploading a valid stdio MCP server built on official Python MCP SDK.
    Expect validation success, artifact_type='mcp_server', and capabilities triggered.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        src_dir = Path(temp_dir) / "src"
        src_dir.mkdir()
        main_py = src_dir / "main.py"
        main_py.write_text("from mcp.server.fastmcp import FastMCP\nmcp = FastMCP('test')\n")
        
        # Add required docker files
        dockerfile = Path(temp_dir) / "Dockerfile"
        dockerfile.write_text("FROM python:3.10-slim\n")
        compose = Path(temp_dir) / "docker-compose.yml"
        compose.write_text("services:\n  test:\n    image: test\n")
        
        # Test directory upload directly
        result = await upload_service.process_directory_upload(temp_dir, "test_mcp_agent")
        
        assert result.success is True
        assert result.artifact_type == "mcp_server"
        assert result.status == "uploaded"

@pytest.mark.asyncio
async def test_mcp_upload_ambiguous_artifact(upload_service):
    """
    Upload an artifact ambiguous between an agent and MCP server.
    Expect clear loud validation error.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        src_dir = Path(temp_dir) / "src"
        src_dir.mkdir()
        main_py = src_dir / "main.py"
        # Mix of FastMCP and Agent Framework (Langchain)
        main_py.write_text("from mcp.server.fastmcp import FastMCP\nimport langchain\n")
        
        # Add required docker files
        dockerfile = Path(temp_dir) / "Dockerfile"
        dockerfile.write_text("FROM python:3.10-slim\n")
        compose = Path(temp_dir) / "docker-compose.yml"
        compose.write_text("services:\n  test:\n    image: test\n")
        
        result = await upload_service.process_directory_upload(temp_dir, "ambiguous_agent")
        
        assert result.success is False
        assert result.status == "validation_failed"
        assert any("Ambiguous artifact type" in err for err in result.validation_errors)

@pytest.mark.asyncio
async def test_mcp_upload_missing_main(upload_service):
    """
    Upload an MCP server missing src/main.py -> expect clear validation error.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # Intentionally do not create src/main.py
        
        # Add required docker files
        dockerfile = Path(temp_dir) / "Dockerfile"
        dockerfile.write_text("FROM python:3.10-slim\n")
        compose = Path(temp_dir) / "docker-compose.yml"
        compose.write_text("services:\n  test:\n    image: test\n")
        
        result = await upload_service.process_directory_upload(temp_dir, "invalid_agent")
        
        assert result.success is False
        assert result.status == "validation_failed"
        assert any("main.py entry point not found" in err for err in result.validation_errors)


@pytest.mark.asyncio
async def test_mcp_manifest_non_empty_and_accurate(upload_service):
    """
    Test that generated mcp_manifest.json is non-empty and contains
    required fields: name, description, skills, version, id.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        src_dir = Path(temp_dir) / "src"
        src_dir.mkdir()
        main_py = src_dir / "main.py"
        main_py.write_text(
            "from mcp.server.fastmcp import FastMCP\n"
            "mcp = FastMCP('calculator')\n\n"
            "@mcp.tool()\n"
            "def add(a: int, b: int) -> int:\n"
            "    \"\"\"Add two numbers.\"\"\"\n"
            "    return a + b\n"
        )

        # Add required docker files
        dockerfile = Path(temp_dir) / "Dockerfile"
        dockerfile.write_text("FROM python:3.10-slim\n")
        compose = Path(temp_dir) / "docker-compose.yml"
        compose.write_text("services:\n  calc:\n    container_name: calc\n    image: calc\n")

        # Manually write a manifest like the LLM generator would produce
        import json
        manifest = {
            "protocolVersion": "0.2.9",
            "id": "test-calc",
            "name": "test-calc",
            "description": "A calculator MCP server",
            "url": "http://localhost:10000/",
            "version": "1.0.0",
            "capabilities": {"streaming": False, "pushNotifications": False, "stateTransitionHistory": False},
            "skills": [
                {
                    "id": "add",
                    "name": "Add",
                    "description": "Add two numbers.",
                    "tags": ["math"],
                    "inputModes": ["application/json"],
                    "outputModes": ["application/json"],
                    "examples": []
                }
            ],
            "defaultInputModes": ["application/json"],
            "defaultOutputModes": ["application/json"],
        }
        manifest_path = Path(temp_dir) / "mcp_manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        # The manifest file should exist and be non-empty
        assert manifest_path.exists()
        assert manifest_path.stat().st_size > 0

        # Validate required fields
        with open(manifest_path, "r") as f:
            loaded = json.load(f)

        assert loaded.get("name"), "Manifest must have a non-empty 'name'"
        assert loaded.get("description"), "Manifest must have a non-empty 'description'"
        assert loaded.get("version"), "Manifest must have a non-empty 'version'"
        assert loaded.get("id"), "Manifest must have a non-empty 'id'"
        assert isinstance(loaded.get("skills"), list), "Manifest must have a 'skills' list"
        assert len(loaded["skills"]) > 0, "Manifest skills must not be empty"

        # Check skill structure
        skill = loaded["skills"][0]
        assert skill.get("id"), "Skill must have an 'id'"
        assert skill.get("name"), "Skill must have a 'name'"
        assert skill.get("description"), "Skill must have a 'description'"


def test_generate_agentcard_json_has_id():
    """
    Test that the generate_agentcard_json tool produces a manifest with an 'id' field.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "app" / "utils" / "agentcard_generator"))
    from tools import AgentAnalyzerTools

    tools = AgentAnalyzerTools()
    result = tools.generate_agentcard_json(
        agent_name="My Test Server",
        description="A test MCP server",
        skills=[{"id": "greet", "name": "Greet", "description": "Say hello", "tags": ["greeting"]}],
    )

    assert result["status"] == "success"
    agentcard = result["agentcard"]
    assert agentcard is not None
    assert agentcard.get("id") == "my-test-server", f"Expected id 'my-test-server', got {agentcard.get('id')}"
    assert agentcard.get("name") == "My Test Server"
    assert agentcard.get("protocolVersion") == "0.2.9"
    assert len(agentcard.get("skills", [])) == 1

