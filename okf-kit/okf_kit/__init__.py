"""okf-kit: Open Knowledge Format (OKF v0.1) core library, CLI, and MCP server.

An OKF bundle is a directory of Markdown files (YAML frontmatter + body); each
file is one *concept*, the file path is its id, and relative Markdown links form
a knowledge graph. This package provides a pure core (parse / validate / links /
search / context / index / templates) exposed via the `okf` CLI and the
`okf-mcp` server.
"""

__version__ = "0.1.0"
