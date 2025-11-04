"""MCP server implementation for Swarm stamp management."""

import asyncio
import json
import logging
import re
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

# Validation patterns
STAMP_ID_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")
REFERENCE_HASH_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")


def validate_and_clean_stamp_id(stamp_id: str) -> str:
    """Validate and clean stamp ID, removing 0x prefix if present.

    Args:
        stamp_id: The stamp ID to validate

    Returns:
        Cleaned stamp ID without 0x prefix

    Raises:
        ValueError: If stamp ID format is invalid
    """
    if not stamp_id:
        raise ValueError("Stamp ID cannot be empty")

    # Remove 0x prefix if present
    if stamp_id.startswith("0x") or stamp_id.startswith("0X"):
        stamp_id = stamp_id[2:]

    # Validate format
    if not STAMP_ID_PATTERN.match(stamp_id):
        raise ValueError(f"Invalid stamp ID format. Expected 64-character hexadecimal string (without 0x prefix), got: {stamp_id}")

    return stamp_id


def validate_and_clean_reference_hash(reference: str) -> str:
    """Validate and clean reference hash, removing 0x prefix if present.

    Args:
        reference: The reference hash to validate

    Returns:
        Cleaned reference hash without 0x prefix

    Raises:
        ValueError: If reference hash format is invalid
    """
    if not reference:
        raise ValueError("Reference hash cannot be empty")

    # Remove 0x prefix if present
    if reference.startswith("0x") or reference.startswith("0X"):
        reference = reference[2:]

    # Validate format
    if not REFERENCE_HASH_PATTERN.match(reference):
        raise ValueError(f"Invalid reference hash format. Expected 64-character hexadecimal string (without 0x prefix), got: {reference}")

    return reference


def validate_stamp_amount(amount: int) -> None:
    """Validate stamp amount.

    Args:
        amount: The amount to validate

    Raises:
        ValueError: If amount is invalid
    """
    if amount < 1000000:
        raise ValueError(f"Stamp amount must be at least 1,000,000 wei, got: {amount}")


def validate_stamp_depth(depth: int) -> None:
    """Validate stamp depth.

    Args:
        depth: The depth to validate

    Raises:
        ValueError: If depth is invalid
    """
    if not (16 <= depth <= 24):
        raise ValueError(f"Stamp depth must be between 16 and 24, got: {depth}")


def validate_data_size(data: str) -> None:
    """Validate data size for upload.

    Args:
        data: The data to validate

    Raises:
        ValueError: If data size is invalid
    """
    data_bytes = data.encode('utf-8')
    if len(data_bytes) > 4096:
        raise ValueError(f"Data size {len(data_bytes)} bytes exceeds 4KB limit (4096 bytes)")
    if len(data_bytes) == 0:
        raise ValueError("Data cannot be empty")


def create_server() -> Server:
    """Create and configure the MCP server."""
    server = Server(settings.mcp_server_name)

    @server.list_tools()
    async def list_tools() -> List[Tool]:
        """List available tools for stamp management."""
        return [
            Tool(
                name="purchase_stamp",
                description="Purchase a new Swarm postage stamp. Returns a 64-character hexadecimal batch ID (without 0x prefix) that can be used for uploading data to Swarm. AGENT GUIDANCE: Celebrate the success and provide next steps. Emphasize that it takes ~1 minute for stamp info to be available on blockchain. Suggest using it for only one file upload (max 4KB), then purchase another stamp for the next upload.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "amount": {
                            "type": "integer",
                            "description": f"Amount of the stamp in wei. Higher amounts allow more data uploads and longer TTL (default: {settings.default_stamp_amount})",
                            "default": settings.default_stamp_amount,
                            "minimum": 1000000
                        },
                        "depth": {
                            "type": "integer",
                            "description": f"Depth of the stamp (16-24). Higher depth allows more parallel uploads (default: {settings.default_stamp_depth})",
                            "default": settings.default_stamp_depth,
                            "minimum": 16,
                            "maximum": 24
                        },
                        "label": {
                            "type": "string",
                            "description": "Optional human-readable label for easier stamp identification",
                            "maxLength": 100
                        }
                    },
                    "required": []
                }
            ),
            Tool(
                name="get_stamp_status",
                description="Get detailed information about a specific stamp including TTL, expiration time, utilization, and usability status. Essential for checking if a stamp is still valid for uploads. AGENT GUIDANCE: Present results with expiration time and usability status highlighted. If stamp is near expiration or unusable, emphasize this to the user.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "stamp_id": {
                            "type": "string",
                            "description": "The 64-character hexadecimal batch ID of the stamp (without 0x prefix). Example: a1b2c3d4e5f6789abcdef0123456789abcdef0123456789abcdef0123456789a",
                            "pattern": "^[a-fA-F0-9]{64}$"
                        }
                    },
                    "required": ["stamp_id"]
                }
            ),
            Tool(
                name="list_stamps",
                description="List all available postage stamps with their details including batch IDs, amounts, depths, TTL, expiration times, and utilization. Shows both local stamps (owned by this node) and network stamps. AGENT GUIDANCE: Present as a table with columns: Batch ID, Expiration Time, Status. Do not categorize or give recommendations. Note that this might return a long list and may be removed in future versions.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            Tool(
                name="extend_stamp",
                description="Extend an existing stamp with additional funds to increase its TTL and allow more data uploads. The stamp must be owned by this node. AGENT GUIDANCE: Show before/after comparison if possible. Note that extension info takes time to propagate through blockchain - suggest user to check stamp status again in ~1 minute to see new expiration time.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "stamp_id": {
                            "type": "string",
                            "description": "The 64-character hexadecimal batch ID of the stamp to extend (without 0x prefix). Example: a1b2c3d4e5f6789abcdef0123456789abcdef0123456789abcdef0123456789a",
                            "pattern": "^[a-fA-F0-9]{64}$"
                        },
                        "amount": {
                            "type": "integer",
                            "description": "Additional amount to add to the stamp in wei. This will extend the stamp's TTL proportionally.",
                            "minimum": 1000000
                        }
                    },
                    "required": ["stamp_id", "amount"]
                }
            ),
            Tool(
                name="upload_data",
                description="Upload data to the Swarm network using a valid postage stamp. Supports files up to 4KB. Validates that the stamp ID exists and is usable before upload. Returns a Swarm reference hash for retrieving the data. AGENT GUIDANCE: Celebrate successful upload and provide retrieval instructions. Show how to copy the reference hash for later data retrieval.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "data": {
                            "type": "string",
                            "description": "Data content to upload as a string (max 4096 bytes). Can be JSON, text, or any string data.",
                            "maxLength": 4096
                        },
                        "stamp_id": {
                            "type": "string",
                            "description": "64-character hexadecimal batch ID of the postage stamp (without 0x prefix). Example: a1b2c3d4e5f6789abcdef0123456789abcdef0123456789abcdef0123456789a",
                            "pattern": "^[a-fA-F0-9]{64}$"
                        },
                        "content_type": {
                            "type": "string",
                            "description": "MIME type of the content (e.g., application/json, text/plain, image/png)",
                            "default": "application/json"
                        }
                    },
                    "required": ["data", "stamp_id"]
                }
            ),
            Tool(
                name="download_data",
                description="Download data from the Swarm network using a reference hash. Returns the raw data content. For binary data, size and type information is provided instead of content. AGENT GUIDANCE: Present content appropriately - for JSON data, show field names and truncate long fields to one line. For binary data, explain what it is and how to save it.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "reference": {
                            "type": "string",
                            "description": "64-character hexadecimal Swarm reference hash (without 0x prefix). Example: b2c3d4e5f6789abcdef0123456789abcdef0123456789abcdef0123456789ab",
                            "pattern": "^[a-fA-F0-9]{64}$"
                        }
                    },
                    "required": ["reference"]
                }
            ),
            Tool(
                name="health_check",
                description="Check gateway and Swarm network connectivity status. Returns gateway URL, response time, and connection status. Useful for troubleshooting connectivity issues. AGENT GUIDANCE: Show simple 'all good' vs 'issues detected' status. If problems found, suggest checking the gateway server at the URL provided.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
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
            elif name == "upload_data":
                return await handle_upload_data(arguments)
            elif name == "download_data":
                return await handle_download_data(arguments)
            elif name == "health_check":
                return await handle_health_check(arguments)
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

        # Validate inputs
        validate_stamp_amount(amount)
        validate_stamp_depth(depth)

        if label and len(label) > 100:
            return CallToolResult(
                content=[TextContent(type="text", text="Error: Label cannot exceed 100 characters")],
                isError=True
            )

        result = gateway_client.purchase_stamp(amount, depth, label)

        response_text = f"🎉 Stamp purchased successfully!\n\n"
        response_text += f"📋 Your Stamp Details:\n"
        batch_id = result.get('batchID', 'N/A')
        response_text += f"   Batch ID: `{batch_id}`\n"
        response_text += f"   Amount: {amount:,} wei\n"
        response_text += f"   Depth: {depth}\n"
        if label:
            response_text += f"   Label: {label}\n"
        response_text += f"\n⏱️  Important: Stamp info takes ~1 minute to propagate through the blockchain.\n"
        response_text += f"📤 Next steps: Use this stamp for ONE file upload (max 4KB), then purchase another stamp for additional uploads.\n"
        response_text += f"💡 Copy the Batch ID above (without 0x prefix) for your upload."

        return CallToolResult(
            content=[TextContent(type="text", text=response_text)]
        )

    except ValueError as e:
        error_msg = f"Validation error: {str(e)}"
        logger.error(error_msg)
        return CallToolResult(
            content=[TextContent(type="text", text=error_msg)],
            isError=True
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
        stamp_id = arguments.get("stamp_id")
        if not stamp_id:
            raise ValueError("Stamp ID is required")

        # Validate and clean stamp ID
        clean_stamp_id = validate_and_clean_stamp_id(stamp_id)

        result = gateway_client.get_stamp_details(clean_stamp_id)

        response_text = f"Stamp Details for {clean_stamp_id}:\n"
        response_text += f"Amount: {result.get('amount', 'N/A')}\n"
        response_text += f"Depth: {result.get('depth', 'N/A')}\n"
        response_text += f"Bucket Depth: {result.get('bucketDepth', 'N/A')}\n"
        response_text += f"Block Number: {result.get('blockNumber', 'N/A')}\n"

        # Enhanced TTL information
        batch_ttl = result.get('batchTTL', 'N/A')
        if batch_ttl != 'N/A':
            response_text += f"Batch TTL: {batch_ttl:,} seconds ({batch_ttl/86400:.1f} days)\n"
        else:
            response_text += f"Batch TTL: {batch_ttl}\n"

        response_text += f"Expected Expiration: {result.get('expectedExpiration', 'N/A')}\n"

        # Enhanced usability information
        usable = result.get('usable', 'N/A')
        response_text += f"Usable: {usable}"
        if usable is False:
            response_text += " ⚠️  (Cannot be used for uploads)"
        elif usable is True:
            response_text += " ✅ (Ready for uploads)"
        response_text += "\n"

        utilization = result.get('utilization', 'N/A')
        if utilization != 'N/A' and isinstance(utilization, (int, float)):
            response_text += f"Utilization: {utilization}%\n"
        else:
            response_text += f"Utilization: {utilization}\n"

        response_text += f"Immutable: {result.get('immutableFlag', 'N/A')}\n"
        response_text += f"Local: {result.get('local', 'N/A')}\n"

        if result.get('label'):
            response_text += f"Label: {result['label']}\n"

        return CallToolResult(
            content=[TextContent(type="text", text=response_text)]
        )

    except ValueError as e:
        error_msg = f"Validation error: {str(e)}"
        logger.error(error_msg)
        return CallToolResult(
            content=[TextContent(type="text", text=error_msg)],
            isError=True
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
            response_text = "📭 No stamps found.\n\n💡 Use the 'purchase_stamp' tool to create your first stamp!"
        else:
            response_text = f"📋 Found {total_count} stamp(s):\n\n"
            response_text += f"PRESENTATION_HINT: Format as table with columns: Batch ID | Expiration Time | Status\n\n"

            # Header for table format
            response_text += f"{'Batch ID':<20} | {'Expiration':<20} | {'Status':<10}\n"
            response_text += f"{'-'*20} | {'-'*20} | {'-'*10}\n"

            for stamp in stamps:
                batch_id = stamp.get('batchID', 'N/A')
                expiration = stamp.get('expectedExpiration', 'N/A')
                usable = stamp.get('usable', 'N/A')

                # Truncate batch ID for table format
                display_id = batch_id[:16] + "..." if len(str(batch_id)) > 19 else batch_id

                # Status with emoji
                if usable is True:
                    status = "✅ Usable"
                elif usable is False:
                    status = "❌ Expired"
                else:
                    status = "❓ Unknown"

                response_text += f"{display_id:<20} | {str(expiration):<20} | {status:<10}\n"

            response_text += f"\n⚠️  Note: This tool may be removed in future versions due to potentially long lists."

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
        stamp_id = arguments.get("stamp_id")
        amount = arguments.get("amount")

        if not stamp_id:
            raise ValueError("Stamp ID is required")
        if not amount:
            raise ValueError("Amount is required")

        # Validate inputs
        clean_stamp_id = validate_and_clean_stamp_id(stamp_id)
        validate_stamp_amount(amount)

        result = gateway_client.extend_stamp(clean_stamp_id, amount)

        response_text = f"✅ Stamp extended successfully!\n\n"
        response_text += f"📋 Extension Details:\n"
        batch_id = result.get('batchID', 'N/A')
        response_text += f"   Batch ID: `{batch_id}`\n"
        response_text += f"   Additional Amount: {amount:,} wei\n"
        response_text += f"   Status: {result.get('message', 'Extended')}\n\n"
        response_text += f"⏱️  Important: Extension info takes ~1 minute to propagate through the blockchain.\n"
        response_text += f"🔍 Check stamp status again in about 1 minute to see the new expiration time."

        return CallToolResult(
            content=[TextContent(type="text", text=response_text)]
        )

    except ValueError as e:
        error_msg = f"Validation error: {str(e)}"
        logger.error(error_msg)
        return CallToolResult(
            content=[TextContent(type="text", text=error_msg)],
            isError=True
        )
    except RequestException as e:
        error_msg = f"Failed to extend stamp: {str(e)}"
        logger.error(error_msg)
        return CallToolResult(
            content=[TextContent(type="text", text=error_msg)],
            isError=True
        )


async def handle_upload_data(arguments: Dict[str, Any]) -> CallToolResult:
    """Handle data upload requests."""
    try:
        data = arguments.get("data")
        stamp_id = arguments.get("stamp_id")

        if not data:
            raise ValueError("Data cannot be empty")
        if not stamp_id:
            raise ValueError("Stamp ID cannot be empty")
        content_type = arguments.get("content_type", "application/json")

        # Validate inputs
        validate_data_size(data)
        clean_stamp_id = validate_and_clean_stamp_id(stamp_id)

        # First, check if the stamp exists on this gateway
        # Note: Newly purchased stamps may not be immediately available via get_stamp_details
        # so we'll try to validate but allow upload to proceed if validation fails with 404
        stamp_validation_failed = False
        validation_error_msg = ""

        try:
            stamp_details = gateway_client.get_stamp_details(clean_stamp_id)

            # Verify it's a usable stamp
            if not stamp_details.get("usable", False):
                return CallToolResult(
                    content=[TextContent(
                        type="text",
                        text=f"Stamp {clean_stamp_id} exists on this gateway but is not usable for uploads. "
                             f"Please use a different stamp or create a new one with the 'purchase_stamp' tool."
                    )],
                    isError=True
                )

        except RequestException as e:
            # If we can't get stamp details, it might be a timing issue with newly purchased stamps
            if hasattr(e, 'response') and e.response is not None:
                if e.response.status_code == 404:
                    # Don't immediately fail - the stamp might be newly purchased
                    # We'll let the upload attempt proceed and let the gateway handle validation
                    stamp_validation_failed = True
                    validation_error_msg = f"Could not validate stamp {clean_stamp_id} (it may be newly purchased)"
                else:
                    # Other HTTP errors should be re-raised
                    raise
            else:
                # Network errors should be re-raised
                raise

        # Proceed with upload if stamp validation passed
        result = gateway_client.upload_data(data, clean_stamp_id, content_type)

        response_text = f"🎉 Data uploaded successfully to Swarm!\n\n"
        response_text += f"📄 Upload Details:\n"
        response_text += f"   Size: {len(data.encode('utf-8')):,} bytes\n"
        response_text += f"   Content Type: {content_type}\n"
        response_text += f"   Stamp Used: `{clean_stamp_id}`\n\n"
        response_text += f"🔗 Retrieval Information:\n"
        response_text += f"   Reference Hash: `{result['reference']}`\n"
        response_text += f"   💡 Copy this reference hash to download your data later using the 'download_data' tool."

        # Add validation warning if applicable
        if stamp_validation_failed:
            response_text += f"\nNote: {validation_error_msg}"

        return CallToolResult(
            content=[TextContent(type="text", text=response_text)]
        )

    except ValueError as e:
        error_msg = f"Upload validation error: {str(e)}"
        logger.error(error_msg)
        return CallToolResult(
            content=[TextContent(type="text", text=error_msg)],
            isError=True
        )
    except RequestException as e:
        error_msg = f"Failed to upload data: {str(e)}"
        logger.error(error_msg)
        return CallToolResult(
            content=[TextContent(type="text", text=error_msg)],
            isError=True
        )


async def handle_download_data(arguments: Dict[str, Any]) -> CallToolResult:
    """Handle data download requests."""
    try:
        reference = arguments.get("reference")
        if not reference:
            raise ValueError("Reference is required")

        # Validate and clean reference hash
        clean_reference = validate_and_clean_reference_hash(reference)

        result_bytes = gateway_client.download_data(clean_reference)

        # Try to decode as text, handle JSON appropriately
        try:
            result_text = result_bytes.decode('utf-8')

            # Try to parse as JSON for better presentation
            try:
                import json
                parsed_json = json.loads(result_text)

                response_text = f"📥 Successfully downloaded JSON data from `{clean_reference}`:\n\n"
                response_text += f"PRESENTATION_HINT: Show field names and truncate long fields to one line\n\n"

                # Show JSON structure with field truncation
                response_text += "📋 JSON Structure:\n"
                for key, value in parsed_json.items():
                    if isinstance(value, str) and len(value) > 50:
                        truncated_value = value[:47] + "..."
                        response_text += f"   {key}: \"{truncated_value}\"\n"
                    elif isinstance(value, dict):
                        response_text += f"   {key}: {{...}} (object with {len(value)} fields)\n"
                    elif isinstance(value, list):
                        response_text += f"   {key}: [...] (array with {len(value)} items)\n"
                    else:
                        response_text += f"   {key}: {value}\n"

                response_text += f"\n💾 Size: {len(result_bytes):,} bytes"

            except json.JSONDecodeError:
                # Not JSON, show as text
                response_text = f"📥 Successfully downloaded text data from `{clean_reference}`:\n\n{result_text}"

        except UnicodeDecodeError:
            # If not valid UTF-8, show as binary data info
            response_text = f"📥 Successfully downloaded binary data from `{clean_reference}`\n\n"
            response_text += f"📊 File Information:\n"
            response_text += f"   Size: {len(result_bytes):,} bytes\n"
            response_text += f"   Type: Binary data\n\n"
            response_text += f"💡 This appears to be binary data (images, documents, etc.). To save it, you would need to write the bytes to a file."

        return CallToolResult(
            content=[TextContent(type="text", text=response_text)]
        )

    except ValueError as e:
        error_msg = f"Validation error: {str(e)}"
        logger.error(error_msg)
        return CallToolResult(
            content=[TextContent(type="text", text=error_msg)],
            isError=True
        )
    except RequestException as e:
        error_msg = f"Failed to download data: {str(e)}"
        logger.error(error_msg)
        return CallToolResult(
            content=[TextContent(type="text", text=error_msg)],
            isError=True
        )


async def handle_health_check(arguments: Dict[str, Any]) -> CallToolResult:
    """Handle health check requests."""
    try:
        result = gateway_client.health_check()

        status = result.get('status', 'unknown')
        gateway_url = result.get('gateway_url', 'N/A')
        response_time = result.get('response_time_ms', 'N/A')

        if status == 'healthy':
            response_text = f"✅ All systems operational!\n\n"
            response_text += f"🌐 Gateway: {gateway_url}\n"
            if isinstance(response_time, (int, float)):
                response_text += f"⚡ Response Time: {response_time:.0f}ms\n"
        else:
            response_text = f"⚠️  Issues detected!\n\n"
            response_text += f"Status: {status}\n"
            response_text += f"Gateway: {gateway_url}\n"
            if isinstance(response_time, (int, float)):
                response_text += f"Response Time: {response_time:.0f}ms\n"

        if result.get('gateway_response'):
            response_text += f"\n📋 Gateway Response: {result['gateway_response']}"

        return CallToolResult(
            content=[TextContent(type="text", text=response_text)]
        )

    except RequestException as e:
        gateway_url = settings.swarm_gateway_url
        error_msg = f"❌ Connection failed!\n\n"
        error_msg += f"Error: {str(e)}\n"
        error_msg += f"Gateway: {gateway_url}\n\n"
        error_msg += f"🔧 Troubleshooting:\n"
        error_msg += f"   • Check if the gateway server is running\n"
        error_msg += f"   • Verify the gateway URL: {gateway_url}\n"
        error_msg += f"   • Check your internet connection"

        logger.error(f"Health check failed: {str(e)}")
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
                    capabilities={}
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