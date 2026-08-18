import sys

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("good-http-server", host="127.0.0.1", port=int(sys.argv[1]))


@mcp.tool()
def echo(text: str) -> str:
    """Echo the input text back."""
    return text


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
