"""MCP tool server; the administrator API launches it over private stdio."""
from mcp.server.fastmcp import FastMCP

from reservation_storage import save_confirmed

server = FastMCP("Approved parking reservations")


@server.tool()
def store_confirmed_reservation(request_id: str, details: dict[str, str], approval_time: str) -> dict:
    """Store a human-approved reservation. Only the trusted administrator service calls this tool."""
    return save_confirmed(request_id, details, approval_time)


if __name__ == "__main__":
    server.run(transport="stdio")
