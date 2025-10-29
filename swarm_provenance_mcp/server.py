"""MCP server implementation for Swarm stamp management."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Sequence

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    CallToolRequest,
    CallToolResult,
    ListToolsRequest,
)
from requests.exceptions import RequestException

from .config import settings
from .gateway_client import SwarmGatewayClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global gateway client instance
gateway_client = SwarmGatewayClient()


def create_server() -> Server:
    """Create and configure the MCP server."""
    server = Server(settings.mcp_server_name)

    @server.list_tools()
    async def list_tools() -> List[Tool]:
        """List available tools for stamp management."""
        return [
            Tool(
                name="purchase_stamp",
                description="Purchase a new Swarm postage stamp",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "amount": {
                            "type": "integer",
                            "description": f"Amount of the stamp in wei (default: {settings.default_stamp_amount})",
                            "default": settings.default_stamp_amount
                        },
                        "depth": {
                            "type": "integer",
                            "description": f"Depth of the stamp (default: {settings.default_stamp_depth})",
                            "default": settings.default_stamp_depth
                        },
                        "label": {
                            "type": "string",
                            "description": "Optional label for the stamp",
                            "required": False
                        }
                    },
                    "required": ["amount", "depth"]
                }
            ),
            Tool(
                name="get_stamp_status",
                description="Get detailed information about a specific stamp",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "stamp_id": {
                            "type": "string",
                            "description": "The batch ID of the stamp to query"
                        }
                    },
                    "required": ["stamp_id"]
                }
            ),
            Tool(
                name="list_stamps",
                description="List all available postage stamps",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            Tool(
                name="extend_stamp",
                description="Extend an existing stamp with additional funds",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "stamp_id": {
                            "type": "string",
                            "description": "The batch ID of the stamp to extend"
                        },
                        "amount": {
                            "type": "integer",
                            "description": "Additional amount to add to the stamp in wei"
                        }
                    },
                    "required": ["stamp_id", "amount"]
                }
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:
        """Handle tool calls."""
        try:
            if name == "purchase_stamp":
                return await handle_purchase_stamp(arguments)
            elif name == "get_stamp_status":
                return await handle_get_stamp_status(arguments)
            elif name == "list_stamps":
                return await handle_list_stamps(arguments)
            elif name == "extend_stamp":
                return await handle_extend_stamp(arguments)
            else:
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text=f"Unknown tool: {name}"
                        )
                    ],
                    isError=True
                )
        except Exception as e:
            logger.error(f"Error in tool {name}: {e}", exc_info=True)
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=f"Error executing {name}: {str(e)}"
                    )
                ],
                isError=True
            )

    return server


async def handle_purchase_stamp(arguments: Dict[str, Any]) -> CallToolResult:
    """Handle stamp purchase requests."""
    try:
        amount = arguments.get("amount", settings.default_stamp_amount)
        depth = arguments.get("depth", settings.default_stamp_depth)
        label = arguments.get("label")

        result = gateway_client.purchase_stamp(amount, depth, label)

        response_text = f"Successfully purchased stamp!\n"
        response_text += f"Batch ID: {result['batchID']}\n"
        response_text += f"Amount: {amount} wei\n"
        response_text += f"Depth: {depth}\n"
        if label:
            response_text += f"Label: {label}\n"
        response_text += f"Message: {result['message']}"

        return CallToolResult(
            content=[TextContent(type="text", text=response_text)]
        )

    except RequestException as e:
        error_msg = f"Failed to purchase stamp: {str(e)}"
        logger.error(error_msg)
        return CallToolResult(
            content=[TextContent(type="text", text=error_msg)],
            isError=True
        )


async def handle_get_stamp_status(arguments: Dict[str, Any]) -> CallToolResult:
    """Handle stamp status requests."""
    try:
        stamp_id = arguments["stamp_id"]
        result = gateway_client.get_stamp_details(stamp_id)

        response_text = f"Stamp Details for {stamp_id}:\n"
        response_text += f"Amount: {result.get('amount', 'N/A')}\n"
        response_text += f"Depth: {result.get('depth', 'N/A')}\n"
        response_text += f"Bucket Depth: {result.get('bucketDepth', 'N/A')}\n"
        response_text += f"Block Number: {result.get('blockNumber', 'N/A')}\n"
        response_text += f"Batch TTL: {result.get('batchTTL', 'N/A')} seconds\n"
        response_text += f"Expected Expiration: {result.get('expectedExpiration', 'N/A')}\n"
        response_text += f"Usable: {result.get('usable', 'N/A')}\n"
        response_text += f"Utilization: {result.get('utilization', 'N/A')}\n"
        response_text += f"Immutable: {result.get('immutableFlag', 'N/A')}\n"
        if result.get('label'):
            response_text += f"Label: {result['label']}\n"

        return CallToolResult(
            content=[TextContent(type="text", text=response_text)]
        )

    except RequestException as e:
        error_msg = f"Failed to get stamp status: {str(e)}"
        logger.error(error_msg)
        return CallToolResult(
            content=[TextContent(type="text", text=error_msg)],
            isError=True
        )


async def handle_list_stamps(arguments: Dict[str, Any]) -> CallToolResult:
    """Handle stamp listing requests."""
    try:
        result = gateway_client.list_stamps()
        stamps = result.get("stamps", [])
        total_count = result.get("total_count", 0)

        if total_count == 0:
            response_text = "No stamps found."
        else:
            response_text = f"Found {total_count} stamp(s):\n\n"
            for i, stamp in enumerate(stamps, 1):
                response_text += f"{i}. Batch ID: {stamp.get('batchID', 'N/A')}\n"
                response_text += f"   Amount: {stamp.get('amount', 'N/A')}\n"
                response_text += f"   Depth: {stamp.get('depth', 'N/A')}\n"
                response_text += f"   Expiration: {stamp.get('expectedExpiration', 'N/A')}\n"
                response_text += f"   Usable: {stamp.get('usable', 'N/A')}\n"
                if stamp.get('label'):
                    response_text += f"   Label: {stamp['label']}\n"
                response_text += "\n"

        return CallToolResult(
            content=[TextContent(type="text", text=response_text)]
        )

    except RequestException as e:
        error_msg = f"Failed to list stamps: {str(e)}"
        logger.error(error_msg)
        return CallToolResult(
            content=[TextContent(type="text", text=error_msg)],
            isError=True
        )


async def handle_extend_stamp(arguments: Dict[str, Any]) -> CallToolResult:
    """Handle stamp extension requests."""
    try:
        stamp_id = arguments["stamp_id"]
        amount = arguments["amount"]

        result = gateway_client.extend_stamp(stamp_id, amount)

        response_text = f"Successfully extended stamp!\n"
        response_text += f"Batch ID: {result['batchID']}\n"
        response_text += f"Additional Amount: {amount} wei\n"
        response_text += f"Message: {result['message']}"

        return CallToolResult(
            content=[TextContent(type="text", text=response_text)]
        )

    except RequestException as e:
        error_msg = f"Failed to extend stamp: {str(e)}"
        logger.error(error_msg)
        return CallToolResult(
            content=[TextContent(type="text", text=error_msg)],
            isError=True
        )




async def main():
    """Main entry point for the MCP server."""
    server = create_server()

    # Set up cleanup
    def cleanup():
        logger.info("Shutting down MCP server...")
        gateway_client.close()

    try:
        async with stdio_server() as (read_stream, write_stream):
            logger.info(f"Starting {settings.mcp_server_name} v{settings.mcp_server_version}")
            logger.info(f"Gateway URL: {settings.swarm_gateway_url}")
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name=settings.mcp_server_name,
                    server_version=settings.mcp_server_version,
                )
            )
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        cleanup()


def main_sync():
    """Synchronous entry point for CLI script."""
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())