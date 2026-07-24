import sys

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("secret-http-server", host="127.0.0.1", port=int(sys.argv[1]))
DEMO_KEY = "sk-" + "demo-secret-123456789"


@mcp.tool(description=f"Returns a demo value. Do not publish {DEMO_KEY}.")
def echo(text: str) -> str:
    return text


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
