from mcp.server.fastmcp import FastMCP

mcp = FastMCP("good-server")


@mcp.tool()
def echo(text: str) -> str:
    """Echo the input text back."""
    return text


if __name__ == "__main__":
    mcp.run()
