# Use a slim Python image for a smaller footprint
FROM python:3.10-slim

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set the working directory
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy project configuration files
COPY pyproject.toml uv.lock README.md ./

# Install dependencies without installing the project itself
# This avoids re-running sync when only source code changes
RUN uv sync --frozen --no-install-project

# Copy the rest of the application code
COPY mcp_everything_server/ ./mcp_everything_server/

# Install the project
RUN uv sync --frozen

# Expose the default port
EXPOSE 3001

# Run the server
CMD ["uv", "run", "-m", "mcp_everything_server", "--port", "3001"]
