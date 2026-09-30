"""MCP client, with the assignment's optional direct-function mode."""
import asyncio
import os
from pathlib import Path
import sys


async def _write_mcp(request):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    parameters = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).with_name("reservation_mcp.py"))],
    )
    async with asyncio.timeout(20):
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("store_confirmed_reservation", {
                    "request_id": request["id"], "details": request["details"],
                    "approval_time": request["approval_time"],
                })
                if result.isError:
                    raise RuntimeError("Reservation storage failed.")
                payload = result.structuredContent
                if not payload or payload.get("saved") is not True or payload.get("request_id") != request["id"]:
                    raise RuntimeError("Invalid storage acknowledgement.")


def write_approved(request):
    mode = os.getenv("RESERVATION_WRITER", "mcp")
    if mode == "function":
        from reservation_storage import save_confirmed
        save_confirmed(request["id"], request["details"], request["approval_time"])
    elif mode == "mcp":
        asyncio.run(_write_mcp(request))
    else:
        raise ValueError("RESERVATION_WRITER must be mcp or function.")
