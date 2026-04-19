# Publishing MCP Servers on Nasiko

With Nasiko's first-class support for the Model Context Protocol (MCP), developers can build tools that interoperate with both the MCP ecosystem and existing LangChain/CrewAI agents within Nasiko, using identical workflows.

## Publishing an MCP Server

Nasiko accepts Zip files and local directories structured as MCP servers—just like standard conversational agents. The backend automatically detects the artifact via your main module signatures logic.

### 1. Directory Structure

Your MCP server should be structured exactly like any other Nasiko agent publish format:

```
my-mcp-server/
├── Dockerfile          (Required)
├── docker-compose.yml  (Required)
├── requirements.txt
├── mcp_manifest.json   (Automatic - The platform generates this by scanning your code)
└── src/
    └── main.py
```

### 2. Creating the Entry Point (`src/main.py`)

Using the official Python `mcp` SDK or `fastmcp`, simply declare your server as standard:

```python
from mcp.server.fastmcp import FastMCP

# Creating the server allows Nasiko to detect it!
mcp = FastMCP("My API Integration Server")

@mcp.tool()
def fetch_weather(location: str) -> str:
    """Fetch the weather for a given query."""
    return f"Weather for {location} is 25°C and sunny."

if __name__ == "__main__":
    # Usually executed directly via Stdout/Stdin
    mcp.run(transport="stdio")
```

### 3. Uploading

You can upload via HTTP API or using the Nasiko CLI:

```bash
# Upload via the CLI
nasiko mcp upload ./my-mcp-server
```

## What happens under the hood?

Nasiko securely analyzes `src/main.py` and detects your MCP artifact.

1. **Manifest Generation:** Using LLMs, Nasiko constructs `mcp_manifest.json` on the fly. Tools like `fetch_weather` are statically analyzed, mapped into the Nasiko Registry, and become discoverable.
2. **Observability Injection:** Nasiko modifies your container to inject OpenTelemetry and Arize Phoenix tracing matching your workspace.
3. **HTTP Bridge Execution:** Nasiko spins up a FastAPI SSE transport bridge on deployment. External agents will communicate with your Stdio scripts effortlessly. 
4. **Dynamic Association:** Legacy agents can now access tools published dynamically onto Nasiko!
