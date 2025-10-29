#!/usr/bin/env python3
"""Test script to connect to the MCP server and demonstrate its capabilities."""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

async def test_mcp_server():
    """Test the MCP server by sending JSON-RPC requests."""
    print("🧪 Testing MCP Server Connection...")

    # Start the MCP server process
    server_cmd = [sys.executable, "-m", "swarm_provenance_mcp.server"]

    try:
        process = await asyncio.create_subprocess_exec(
            *server_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=Path(__file__).parent
        )

        print("✅ MCP Server process started")

        # Send initialization request
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "0.1.0",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            }
        }

        print("📤 Sending initialization request...")
        process.stdin.write((json.dumps(init_request) + "\n").encode())
        await process.stdin.drain()

        # Read initialization response
        response_line = await process.stdout.readline()
        if response_line:
            response = json.loads(response_line.decode().strip())
            print(f"📥 Initialization response: {json.dumps(response, indent=2)}")

        # Send tools/list request
        tools_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }

        print("\n📤 Sending tools/list request...")
        process.stdin.write((json.dumps(tools_request) + "\n").encode())
        await process.stdin.drain()

        # Read tools response
        tools_response_line = await process.stdout.readline()
        if tools_response_line:
            tools_response = json.loads(tools_response_line.decode().strip())
            print(f"📥 Tools list response:")

            if "result" in tools_response and "tools" in tools_response["result"]:
                tools = tools_response["result"]["tools"]
                print(f"   Found {len(tools)} tools:")
                for tool in tools:
                    print(f"   • {tool['name']}: {tool['description'][:60]}...")
            else:
                print(f"   Raw response: {json.dumps(tools_response, indent=2)}")

        # Test a tool call (purchase_stamp with defaults)
        tool_call_request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "health_check",
                "arguments": {}
            }
        }

        print(f"\n📤 Testing health_check tool...")
        process.stdin.write((json.dumps(tool_call_request) + "\n").encode())
        await process.stdin.drain()

        # Read tool call response
        tool_response_line = await process.stdout.readline()
        if tool_response_line:
            tool_response = json.loads(tool_response_line.decode().strip())
            print(f"📥 Tool call response:")
            if "result" in tool_response:
                content = tool_response["result"].get("content", [])
                if content and isinstance(content[0], dict) and "text" in content[0]:
                    print(f"   {content[0]['text']}")
                else:
                    print(f"   Raw result: {json.dumps(tool_response['result'], indent=2)}")
            elif "error" in tool_response:
                print(f"   Error: {tool_response['error']}")

        # Gracefully close
        process.stdin.close()
        await process.wait()

        print("\n✅ MCP Server test completed successfully!")

    except Exception as e:
        print(f"❌ Error testing MCP server: {e}")
        if 'process' in locals():
            process.terminate()
            await process.wait()

def create_claude_desktop_config():
    """Create a sample Claude Desktop configuration."""
    config = {
        "mcpServers": {
            "swarm-provenance": {
                "command": "python",
                "args": [
                    "-m",
                    "swarm_provenance_mcp.server"
                ],
                "cwd": str(Path(__file__).parent),
                "env": {
                    "SWARM_GATEWAY_URL": "http://localhost:8000"
                }
            }
        }
    }

    config_file = Path(__file__).parent / "claude_desktop_config.json"
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)

    print(f"\n📝 Claude Desktop config created at: {config_file}")
    print("To use with Claude Desktop:")
    print("1. Copy this config to your Claude Desktop settings")
    print("2. Make sure the swarm_connect gateway is running on port 8000")
    print("3. Restart Claude Desktop")
    print("4. The swarm-provenance tools will be available in Claude Desktop")

if __name__ == "__main__":
    print("🚀 MCP Server Connection Test")
    print("=" * 50)

    # Test the server
    asyncio.run(test_mcp_server())

    # Create Claude Desktop config
    create_claude_desktop_config()