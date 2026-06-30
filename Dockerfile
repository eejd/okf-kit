# okf-hive-dev MCP server — OKF dev-ecosystem knowledge base
# Source: ~/Workspaces/Agents/MCP/okf-kit (WS1 HTTP transport fork of phanijapps/okf-kit)
# Build:  docker build -t mcp-okf-hive-dev:local .
#
# Bundle is volume-mounted at /bundle at runtime — never baked into the image.
# KB edits in knowledge-hive/okf do NOT require a rebuild; rebuild only on server-code changes.
#
# arm64 + amd64: ghcr.io/astral-sh/uv is a multi-platform manifest.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Copy dependency manifest + lockfile first (cache-efficient layer ordering).
# THIRD_PARTY_NOTICES.md is required by hatchling's force-include directive.
COPY pyproject.toml uv.lock THIRD_PARTY_NOTICES.md ./

# Copy the source package (hatchling resolves packages = ["okf-kit/okf_kit"])
COPY okf-kit/ okf-kit/

# Install the package and its runtime deps, locked, no dev extras.
# uv creates /app/.venv with okf-mcp on the PATH.
RUN uv sync --frozen --no-dev

# Put the venv scripts on PATH so okf-mcp is directly executable
ENV PATH="/app/.venv/bin:$PATH"

# Non-root runtime user
RUN adduser --system --uid 1000 --no-create-home okf
USER okf

# Bundle is volume-mounted from outside (knowledge-hive/okf on the host)
VOLUME ["/bundle"]
EXPOSE 4020

# okf-mcp <bundle-path> [--transport http --host 0.0.0.0 --port 4020]
# compose `command:` overrides CMD, prepended after the ENTRYPOINT
ENTRYPOINT ["okf-mcp"]
CMD ["/bundle", "--transport", "http", "--host", "0.0.0.0", "--port", "4020"]
