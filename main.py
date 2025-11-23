# main.py
"""
DisasterScout app entrypoint for mcp-agent Cloud.

We have:
- a FastMCP server defined in mcp_server/server.py (variable: mcp)
- we wrap that server in a MCPApp so mcp-agent Cloud can run it.

This satisfies the requirement "MCPApp definition found in main.py".
"""

from mcp_agent.app import MCPApp
from mcp_agent.mcp_server import MCPServerDefinition

from mcp_server.server import mcp  # FastMCP instance


# 1) Create the MCPApp object that mcp-agent Cloud is looking for
app = MCPApp(
    name="disasterscout",
    description="DisasterScout crisis mapping MCP server (MongoDB + Tavily + OpenAI)",
)

# 2) Register our FastMCP server as an MCP server
# mcp.run() is normally used locally over stdio.
# Here, mcp-agent Cloud will manage the IO for us via this server definition.
app.add_mcp_server(
    MCPServerDefinition.from_fastmcp(
        name="disasterscout-mcp",
        mcp=mcp,
    )
)


# 3) Local debug entrypoint (optional — not used by mcp-agent Cloud)
if __name__ == "__main__":
    # This still lets you run the MCP server locally if needed:
    mcp.run()
