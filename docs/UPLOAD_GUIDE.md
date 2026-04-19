# Nasiko Upload Guide

This guide provides step-by-step instructions on how to upload and deploy your AI agents and MCP servers to the Nasiko platform using the Nasiko CLI.

## Prerequisites

- Nasiko CLI installed.
- Access to a Nasiko cluster.

## Step 1: Authentication

Before uploading, you must log in to your Nasiko cluster.

```bash
nasiko login --access-key <YOUR_ACCESS_KEY> --access-secret <YOUR_ACCESS_SECRET>
```

You can verify your login status with:
```bash
nasiko whoami
```

## Step 2: Prepare Your Artifact

Ensure your agent or MCP server is in a local directory or compressed into a `.zip` file.

### Agent Structure
- Root directory containing your agent code (`main.py`, `app.py`, etc.)
- Optional: `AgentCard.json` (if not present, Nasiko will attempt to auto-generate it during upload)

### MCP Server Structure
- Root directory containing your MCP server implementation.
- Typical entry point: `__main__.py` or `server.py`.

## Step 3: Upload

You can upload either a directory or a ZIP file.

### Option A: Upload a Directory (Recommended)
This is the easiest way to upload your local development folder.

```bash
nasiko agent upload-directory path/to/your/agent --name "My Agent Name"
```

### Option B: Upload a ZIP File
If you have a pre-packaged ZIP file.

```bash
nasiko agent upload-zip path/to/your/agent.zip --name "My Agent Name"
```

> [!TIP]
> The `--name` flag is optional. If omitted, Nasiko will try to auto-detect the name from the directory or zip contents.

## Step 4: Verify Upload

Once the upload is complete, you can check the status of your uploaded agents.

```bash
nasiko agent list-uploaded
```

This will show a list of your agents, their IDs, and their current status (e.g., `Active`, `Setting Up`, or `Failed`).

## Step 5: (Optional) Connect MCP Servers

If you uploaded an MCP server and want to associate it with an existing agent:

```bash
nasiko agent connect-mcp <AGENT_ID> <MCP_SERVER_ID>
```

---

For more details on CLI commands, run:
```bash
nasiko --help
```
