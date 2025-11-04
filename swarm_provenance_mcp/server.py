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
from .provenance_schemas import ProvenanceBuilder, ProvenanceGuidance

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
                            "description": f"Amount of the stamp in wei. Higher amounts provide longer TTL (time-to-live) before stamp expires (default: {settings.default_stamp_amount})",
                            "default": settings.default_stamp_amount,
                            "minimum": 1000000
                        },
                        "depth": {
                            "type": "integer",
                            "description": f"Depth of the stamp (16-24). Depth determines storage capacity - higher depth allows storing more chunks (default: {settings.default_stamp_depth})",
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
                description="Extend an existing stamp with additional funds to increase its TTL (time-to-live). This extends the expiration date but does NOT increase storage capacity. The stamp must be owned by this node. AGENT GUIDANCE: Show before/after comparison if possible. Note that extension info takes time to propagate through blockchain - suggest user to check stamp status again in ~1 minute to see new expiration time.",
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
                description="Upload data to Swarm decentralized storage. Creates a fresh postage stamp, waits for it to become usable, then uploads the data. For structured data uploads, will guide you through collecting necessary metadata. Returns a Swarm reference hash for later retrieval.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "data": {
                            "description": "The actual data content to upload. Can be any format - text, JSON object, etc.",
                            "maxLength": 4096
                        },
                        "title": {
                            "type": "string",
                            "description": "Brief descriptive title for this data (e.g., 'Temperature Readings', 'Interview Notes')"
                        },
                        "creator": {
                            "type": "string",
                            "description": "Who created this data (your name, organization, or 'AI Assistant')"
                        },
                        "purpose": {
                            "type": "string",
                            "description": "Why this data was created or what it's for (e.g., 'research', 'documentation', 'backup')"
                        },
                        "source": {
                            "type": "string",
                            "description": "Where this data came from (optional - e.g., 'sensor readings', 'user input', 'analysis results')"
                        },
                        "content_type": {
                            "type": "string",
                            "description": "MIME type of the content",
                            "default": "application/json"
                        }
                    },
                    "required": ["data"]
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
                name="create_provenance_record",
                description="Create a structured metadata record with title, creator, and purpose information. Useful for organizing data with proper attribution and context.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Human-readable title describing this data"
                        },
                        "data": {
                            "description": "The actual data content to wrap with provenance"
                        },
                        "creator": {
                            "type": "string",
                            "description": "Name or ID of the creator (person, AI agent, system, etc.)"
                        },
                        "purpose": {
                            "type": "string",
                            "description": "Why this data was created or collected"
                        },
                        "format": {
                            "type": "string",
                            "enum": ["simple", "data_standard"],
                            "default": "simple",
                            "description": "Provenance format: 'simple' for basic use or 'data_standard' for research-grade DaTA compliance"
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional tags for categorization (e.g., ['research', 'temperature', 'climate'])"
                        },
                        "source": {
                            "type": "string",
                            "description": "Optional: where this data originated from"
                        }
                    },
                    "required": ["title", "data", "creator"]
                }
            ),
            Tool(
                name="show_provenance_examples",
                description="Show examples of structured data formats with metadata. Displays templates for organizing information with proper context.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "use_case": {
                            "type": "string",
                            "enum": ["research", "journalism", "general", "all"],
                            "default": "all",
                            "description": "Show examples for specific use case or all examples"
                        }
                    },
                    "required": []
                }
            ),
            Tool(
                name="create_swip_record",
                description="Wrap structured data in SWIP format for Swarm storage. Adds integrity verification and stamp management for decentralized storage.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "provenance_data": {
                            "type": "object",
                            "description": "The inner provenance record (DaTA, simple, or custom format)"
                        },
                        "stamp_id": {
                            "type": "string",
                            "description": "Swarm stamp ID for TTL management (64-character hex, 0x prefix will be removed)"
                        },
                        "provenance_standard": {
                            "type": "string",
                            "default": "DaTA v1.0.0",
                            "description": "Standard used for the inner provenance data"
                        },
                        "encryption": {
                            "type": "string",
                            "enum": ["none", "aes-256-gcm"],
                            "default": "none",
                            "description": "Encryption method (currently only 'none' supported)"
                        }
                    },
                    "required": ["provenance_data", "stamp_id"]
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
            elif name == "create_provenance_record":
                return await handle_create_provenance_record(arguments)
            elif name == "show_provenance_examples":
                return await handle_show_provenance_examples(arguments)
            elif name == "create_swip_record":
                return await handle_create_swip_record(arguments)
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

        # Check if purchase was actually successful
        batch_id = result.get('batchID')
        if not batch_id:
            error_msg = f"❌ Stamp purchase failed - no stamp ID returned!\n\nGateway response: {result}"
            logger.error(f"Purchase failed - missing batchID in response: {result}")
            return CallToolResult(
                content=[TextContent(type="text", text=error_msg)],
                isError=True
            )

        response_text = f"🎉 Stamp purchased successfully!\n\n"
        response_text += f"📋 Your Stamp Details:\n"
        response_text += f"   Batch ID: `{batch_id}`\n"
        response_text += f"   Amount: {amount:,} wei\n"
        response_text += f"   Depth: {depth}\n"
        if label:
            response_text += f"   Label: {label}\n"
        response_text += f"\n✅ Stamp ID: `{batch_id}` (immediately available)\n"
        response_text += f"⏱️  IMPORTANT: Wait ~1 minute before using this stamp!\n"
        response_text += f"📋 The stamp info must propagate through the blockchain before it can be used for uploads.\n"
        response_text += f"💡 Save this Stamp ID (without 0x prefix) and check its status in about 1 minute before uploading."

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
    """Handle data upload with guided metadata collection and fresh stamp creation."""
    try:
        data = arguments.get("data")
        title = arguments.get("title")
        creator = arguments.get("creator")
        purpose = arguments.get("purpose")
        source = arguments.get("source")
        content_type = arguments.get("content_type", "application/json")

        if not data:
            return CallToolResult(
                content=[TextContent(type="text", text="❌ Error: 'data' is required for upload")],
                isError=True
            )

        # Validate data size
        validate_data_size(data)

        # Guide user through missing information
        missing_info = []
        if not title:
            missing_info.append("**Title**: What should we call this data? (e.g., 'Research Notes', 'Temperature Data')")
        if not creator:
            missing_info.append("**Creator**: Who created this data? (your name, organization, or 'AI Assistant')")
        if not purpose:
            missing_info.append("**Purpose**: Why was this data created? (e.g., 'research', 'backup', 'documentation')")

        if missing_info:
            response_text = f"📝 **Additional Information Needed**\n"
            response_text += f"=" * 45 + "\n\n"
            response_text += f"To create a complete record, please provide:\n\n"
            for i, info in enumerate(missing_info, 1):
                response_text += f"{i}. {info}\n"
            response_text += f"\nPlease call this tool again with the missing information."

            return CallToolResult(
                content=[TextContent(type="text", text=response_text)]
            )

        # Step 1: Create fresh stamp
        response_text = f"🚀 **Starting Upload Process**\n"
        response_text += f"=" * 40 + "\n\n"
        response_text += f"📦 **Step 1**: Creating fresh postage stamp...\n"

        try:
            stamp_result = gateway_client.purchase_stamp(
                amount=settings.default_stamp_amount,
                depth=settings.default_stamp_depth,
                label=f"upload-{title[:20]}"
            )
            stamp_id = stamp_result.get('batchID')
            if not stamp_id:
                raise ValueError("No stamp ID returned from purchase")

            response_text += f"✅ Stamp created: `{stamp_id}`\n\n"

        except Exception as e:
            return CallToolResult(
                content=[TextContent(type="text", text=f"❌ Failed to create stamp: {str(e)}")],
                isError=True
            )

        # Step 2: Wait for stamp to become usable
        response_text += f"⏱️ **Step 2**: Waiting for stamp to propagate...\n"

        import time
        max_wait = 60  # 1 minute
        check_interval = 5  # 5 seconds
        start_time = time.time()
        stamp_ready = False

        while (time.time() - start_time) < max_wait:
            try:
                stamp_details = gateway_client.get_stamp_details(stamp_id)
                if stamp_details.get('usable', False):
                    stamp_ready = True
                    elapsed = time.time() - start_time
                    response_text += f"✅ Stamp ready after {elapsed:.1f} seconds\n\n"
                    break
                else:
                    response_text += f"   Checking... (stamp not ready yet)\n"
            except Exception:
                response_text += f"   Checking... (waiting for propagation)\n"

            time.sleep(check_interval)

        if not stamp_ready:
            response_text += f"⚠️ Stamp may still be propagating. Attempting upload anyway...\n\n"

        # Step 3: Create structured data record
        response_text += f"📋 **Step 3**: Creating structured data record...\n"

        # Create a simple provenance record
        structured_data = ProvenanceBuilder.create_simple_record(
            title=title,
            data=data,
            creator=creator,
            purpose=purpose,
            source=source
        )

        # Create SWIP wrapper
        swip_record = ProvenanceBuilder.create_swip_record(
            provenance_data=structured_data,
            stamp_id=stamp_id,
            provenance_standard="simple"
        )

        response_text += f"✅ Structured record created with metadata\n\n"

        # Step 4: Upload to Swarm
        response_text += f"📤 **Step 4**: Uploading to Swarm network...\n"

        try:
            upload_data_str = json.dumps(swip_record)
            upload_result = gateway_client.upload_data(upload_data_str, stamp_id, content_type)
            reference = upload_result.get('reference')

            if not reference:
                raise ValueError("No reference returned from upload")

            response_text += f"✅ Upload successful!\n\n"

            # Final summary
            response_text += f"🎉 **Upload Complete**\n"
            response_text += f"=" * 30 + "\n\n"
            response_text += f"📄 **Reference**: `{reference}`\n"
            response_text += f"📦 **Stamp ID**: `{stamp_id}`\n"
            response_text += f"📊 **Record Details**:\n"
            response_text += f"   • Title: {title}\n"
            response_text += f"   • Creator: {creator}\n"
            response_text += f"   • Purpose: {purpose}\n"
            if source:
                response_text += f"   • Source: {source}\n"
            response_text += f"   • Size: {len(upload_data_str)} bytes\n\n"
            response_text += f"🔗 Use the reference hash to retrieve your data anytime!"

            return CallToolResult(
                content=[TextContent(type="text", text=response_text)]
            )

        except Exception as e:
            response_text += f"❌ Upload failed: {str(e)}\n\n"
            response_text += f"💡 The stamp `{stamp_id}` was created and can be reused for another upload attempt."

            return CallToolResult(
                content=[TextContent(type="text", text=response_text)],
                isError=True
            )

    except Exception as e:
        error_msg = f"Upload process failed: {str(e)}"
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


async def handle_create_provenance_record(arguments: Dict[str, Any]) -> CallToolResult:
    """Handle provenance record creation requests."""
    try:
        title = arguments.get("title")
        data = arguments.get("data")
        creator = arguments.get("creator")
        purpose = arguments.get("purpose")
        format_type = arguments.get("format", "simple")
        tags = arguments.get("tags", [])
        source = arguments.get("source")

        if not title:
            raise ValueError("Title is required")
        if not data:
            raise ValueError("Data is required")
        if not creator:
            raise ValueError("Creator is required")

        # Create the provenance record
        if format_type == "data_standard":
            record = ProvenanceBuilder.create_data_record(
                data=data,
                creator_name=creator,
                creator_type="ai_agent" if "ai" in creator.lower() or "claude" in creator.lower() else "human",
                purpose=purpose,
                tags=tags
            )
        else:  # simple format
            record = ProvenanceBuilder.create_simple_record(
                title=title,
                data=data,
                creator=creator,
                description=None,
                purpose=purpose,
                source=source,
                tags=tags
            )

        response_text = f"✅ Provenance record created successfully!\n\n"
        response_text += f"📋 Record Type: {format_type.replace('_', ' ').title()}\n"
        response_text += f"📄 Title: {title}\n"
        response_text += f"👤 Creator: {creator}\n"
        if purpose:
            response_text += f"🎯 Purpose: {purpose}\n"
        if tags:
            response_text += f"🏷️  Tags: {', '.join(tags)}\n"

        response_text += f"\n📝 Complete Provenance Record:\n"
        response_text += f"```json\n{json.dumps(record, indent=2)}\n```\n\n"
        response_text += f"💡 Benefits of this structure:\n"
        response_text += f"   • Data authenticity verification\n"
        response_text += f"   • Clear audit trails\n"
        response_text += f"   • Reproducible processes\n"
        response_text += f"   • Attribution tracking\n\n"
        response_text += f"📤 You can now upload this structured data to Swarm for tamper-proof storage!"

        return CallToolResult(
            content=[TextContent(type="text", text=response_text)]
        )

    except ValueError as e:
        error_msg = f"Provenance creation error: {str(e)}"
        logger.error(error_msg)
        return CallToolResult(
            content=[TextContent(type="text", text=error_msg)],
            isError=True
        )
    except Exception as e:
        error_msg = f"Failed to create provenance record: {str(e)}"
        logger.error(error_msg)
        return CallToolResult(
            content=[TextContent(type="text", text=error_msg)],
            isError=True
        )


async def handle_show_provenance_examples(arguments: Dict[str, Any]) -> CallToolResult:
    """Handle requests to show provenance examples."""
    try:
        use_case = arguments.get("use_case", "all")

        response_text = f"📚 Provenance Record Examples\n"
        response_text += f"=" * 50 + "\n\n"

        if use_case in ["general", "all"]:
            response_text += f"🔹 **Simple Provenance Format** (General Use)\n"
            response_text += f"```json\n{json.dumps(ProvenanceGuidance.SCHEMA_EXAMPLES['simple'], indent=2)}\n```\n\n"

        if use_case in ["research", "all"]:
            response_text += f"🔬 **Research-Grade Format** (DaTA Standard)\n"
            response_text += f"```json\n{json.dumps(ProvenanceGuidance.SCHEMA_EXAMPLES['research'], indent=2)}\n```\n\n"

        if use_case in ["journalism", "all"]:
            response_text += f"📰 **Journalism Example** (Source Verification)\n"
            journalism_example = {
                "title": "Interview Transcript - Climate Research",
                "creator": "Journalist AI Assistant",
                "purpose": "fact_checking_climate_claims",
                "data": {
                    "interview_date": "2024-11-04",
                    "interviewee": "Dr. Smith, Climate Scientist",
                    "location": "University Lab",
                    "key_quotes": [
                        "Temperature data shows clear warming trend",
                        "Ice core samples confirm historical patterns"
                    ],
                    "verification_status": "pending_fact_check"
                },
                "source": "audio_recording_ref_abc123",
                "tags": ["journalism", "climate", "interview", "fact-check"],
                "created_at": "2024-11-04T14:30:00Z"
            }
            response_text += f"```json\n{json.dumps(journalism_example, indent=2)}\n```\n\n"

        if use_case in ["all"]:
            response_text += f"🌐 **SWIP-Wrapped Format** (Swarm Storage)\n"
            response_text += f"```json\n{json.dumps(ProvenanceGuidance.SCHEMA_EXAMPLES['swip'], indent=2)}\n```\n\n"

        response_text += f"💡 **Choose Your Format:**\n"
        response_text += f"• **Simple**: Easy to use, good for general data\n"
        response_text += f"• **DaTA Standard**: Research-grade with content hashing\n"
        response_text += f"• **SWIP**: Wrapped format for Swarm decentralized storage\n"
        response_text += f"• **Custom**: Adapt these examples to your needs\n\n"
        response_text += f"🛠️  Use `create_provenance_record` to build inner records, then `create_swip_record` to wrap for Swarm!"

        return CallToolResult(
            content=[TextContent(type="text", text=response_text)]
        )

    except Exception as e:
        error_msg = f"Failed to show examples: {str(e)}"
        logger.error(error_msg)
        return CallToolResult(
            content=[TextContent(type="text", text=error_msg)],
            isError=True
        )


async def handle_create_swip_record(arguments: Dict[str, Any]) -> CallToolResult:
    """Handle requests to create SWIP-wrapped provenance records."""
    try:
        provenance_data = arguments.get("provenance_data", {})
        stamp_id = arguments.get("stamp_id", "")
        provenance_standard = arguments.get("provenance_standard", "DaTA v1.0.0")
        encryption = arguments.get("encryption", "none")

        # Validate required inputs
        if not provenance_data:
            return CallToolResult(
                content=[TextContent(type="text", text="❌ Error: provenance_data is required")],
                isError=True
            )

        if not stamp_id:
            return CallToolResult(
                content=[TextContent(type="text", text="❌ Error: stamp_id is required")],
                isError=True
            )

        # Create SWIP record
        swip_record = ProvenanceBuilder.create_swip_record(
            provenance_data=provenance_data,
            stamp_id=stamp_id,
            provenance_standard=provenance_standard,
            encryption=encryption
        )

        # Validate the SWIP record
        is_valid, errors = ProvenanceBuilder.validate_record(swip_record, "swip")

        response_text = f"🌐 SWIP-Wrapped Provenance Record Created\n"
        response_text += f"=" * 50 + "\n\n"

        if is_valid:
            response_text += f"✅ **Validation**: SWIP record is valid\n\n"
        else:
            response_text += f"⚠️ **Validation**: {', '.join(errors)}\n\n"

        response_text += f"📋 **SWIP Record Structure**:\n"
        response_text += f"```json\n{json.dumps(swip_record, indent=2)}\n```\n\n"

        response_text += f"🔍 **Record Details**:\n"
        response_text += f"• **Content Hash**: {swip_record['content_hash']}\n"
        response_text += f"• **Standard**: {swip_record['provenance_standard']}\n"
        response_text += f"• **Encryption**: {swip_record['encryption']}\n"
        response_text += f"• **Stamp ID**: {swip_record['stamp_id']}\n"
        response_text += f"• **Data Size**: {len(swip_record['data'])} characters (Base64)\n\n"

        response_text += f"💾 **Ready for Swarm Upload**:\n"
        response_text += f"This SWIP record can be uploaded to Swarm using the `upload_data` tool.\n"
        response_text += f"The wrapper ensures data integrity and provides stamp management.\n\n"

        response_text += f"🔐 **Integrity Protection**:\n"
        response_text += f"The SHA-256 hash ensures your data hasn't been tampered with.\n"
        response_text += f"Anyone can verify authenticity by recalculating the hash."

        return CallToolResult(
            content=[TextContent(type="text", text=response_text)]
        )

    except Exception as e:
        error_msg = f"Failed to create SWIP record: {str(e)}"
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