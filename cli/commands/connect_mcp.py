"""
MCP Server association commands for the Nasiko CLI.
"""

import json

import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.settings import APIEndpoints
from core.api_client import get_api_client

console = Console()


def connect_mcp_command(agent_id: str, mcp_server_ids: list[str]):
    """Connect one or more MCP servers to an agent"""

    try:
        client = get_api_client()
        endpoint = APIEndpoints.MCP_CONNECT.format(agent_id=agent_id)

        payload = {"mcp_server_ids": mcp_server_ids}

        response = client.put(endpoint, json=payload, require_auth=True)
        data = client.handle_response(
            response,
            success_message=f"MCP servers connected to agent '{agent_id}'",
        )

        if not data:
            return

        # Display results
        connected = data.get("connected_mcp_servers", [])
        message = data.get("message", "Success")

        console.print(f"\n[bold green]✅ {message}[/bold green]\n")

        if connected:
            table = Table(
                show_header=True,
                header_style="bold magenta",
                title="Connected MCP Servers",
            )
            table.add_column("MCP Server ID", style="cyan", justify="center")

            for server_id in connected:
                table.add_row(server_id)

            console.print(table)

        console.print(
            "\n[yellow]💡 Note: The agent will use these MCP tools after redeployment.[/yellow]"
        )
        console.print(
            "[yellow]   Run 'nasiko agent update <agent-name>' to redeploy.[/yellow]"
        )

    except requests.exceptions.ConnectionError:
        console.print(
            "[red]Error: Could not connect to Nasiko API. Make sure the server is running.[/red]"
        )
    except requests.exceptions.HTTPError as e:
        console.print(
            f"[red]Error: HTTP {e.response.status_code} - {e.response.text}[/red]"
        )
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")


def get_connected_mcp_command(agent_id: str):
    """Get MCP servers connected to an agent"""

    try:
        client = get_api_client()
        endpoint = APIEndpoints.MCP_GET_CONNECTED.format(agent_id=agent_id)

        response = client.get(endpoint, require_auth=True)
        data = client.handle_response(
            response,
            success_message=f"Retrieved connected MCP servers for '{agent_id}'",
        )

        if not data:
            return

        mcp_servers = data.get("connected_mcp_servers", [])

        if not mcp_servers:
            console.print(
                f"[yellow]No MCP servers connected to agent '{agent_id}'[/yellow]"
            )
            return

        console.print(
            f"\n[bold magenta]MCP Servers Connected to '{agent_id}' ({len(mcp_servers)})[/bold magenta]\n"
        )

        for server in mcp_servers:
            server_info = f"""[bold]ID:[/bold] {server.get('id', 'N/A')}
[bold]Name:[/bold] {server.get('name', 'N/A')}
[bold]Description:[/bold] {server.get('description', 'N/A')}
[bold]URL:[/bold] {server.get('url', 'N/A')}"""

            skills = server.get("skills", [])
            if skills:
                skill_names = [s.get("name", "unnamed") for s in skills]
                server_info += f"\n[bold]Tools:[/bold] {', '.join(skill_names)}"

            console.print(
                Panel(
                    server_info,
                    title=f"MCP Server: {server.get('name', 'Unknown')}",
                    border_style="cyan",
                )
            )

    except requests.exceptions.ConnectionError:
        console.print(
            "[red]Error: Could not connect to Nasiko API. Make sure the server is running.[/red]"
        )
    except requests.exceptions.HTTPError as e:
        console.print(
            f"[red]Error: HTTP {e.response.status_code} - {e.response.text}[/red]"
        )
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")


def disconnect_mcp_command(agent_id: str):
    """Disconnect all MCP servers from an agent"""

    try:
        client = get_api_client()
        endpoint = APIEndpoints.MCP_CONNECT.format(agent_id=agent_id)

        # Send empty list to disconnect all
        payload = {"mcp_server_ids": []}

        response = client.put(endpoint, json=payload, require_auth=True)
        data = client.handle_response(
            response,
            success_message=f"All MCP servers disconnected from agent '{agent_id}'",
        )

        if not data:
            return

        console.print(
            f"\n[bold green]✅ All MCP servers disconnected from agent '{agent_id}'[/bold green]"
        )

    except requests.exceptions.ConnectionError:
        console.print(
            "[red]Error: Could not connect to Nasiko API. Make sure the server is running.[/red]"
        )
    except requests.exceptions.HTTPError as e:
        console.print(
            f"[red]Error: HTTP {e.response.status_code} - {e.response.text}[/red]"
        )
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
