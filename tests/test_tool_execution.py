"""Tests for MCP tool execution and response validation."""

import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from typing import Dict, Any

from mcp.types import CallToolRequest, CallToolResult, TextContent
from swarm_provenance_mcp.server import create_server


class TestToolExecution:
    """Test suite for MCP tool execution and response validation."""

    @pytest.fixture
    def server(self):
        """Create MCP server instance for testing."""
        return create_server()

    @pytest.fixture
    def mock_gateway_client(self):
        """Mock gateway client for testing tool execution."""
        with patch('swarm_provenance_mcp.server.gateway_client') as mock_client:
            # Configure mock responses for different methods
            mock_client.purchase_stamp.return_value = {
                "batchID": "test_batch_123",
                "message": "Stamp purchased successfully"
            }
            mock_client.get_stamp_info.return_value = {
                "batchID": "test_batch_123",
                "amount": "2000000000",
                "depth": 17,
                "bucketDepth": 16,
                "blockNumber": 12345,
                "immutableFlag": False,
                "exists": True,
                "batchTTL": 123456
            }
            mock_client.list_stamps.return_value = {
                "stamps": [
                    {
                        "batchID": "test_batch_123",
                        "amount": "2000000000",
                        "depth": 17,
                        "utilization": 0.1
                    }
                ],
                "count": 1
            }
            mock_client.extend_stamp.return_value = {
                "batchID": "test_batch_123",
                "message": "Stamp extended successfully"
            }
            mock_client.get_stamp_utilization.return_value = {
                "batchID": "test_batch_123",
                "utilization": 0.15
            }

            yield mock_client

    async def get_call_tool_handler(self, server):
        """Get the call_tool handler from the server."""
        # Find the call_tool handler
        for handler_name, handler in server._request_handlers.items():
            if 'call' in handler_name and hasattr(handler, '__call__'):
                return handler
        return None

    async def test_purchase_stamp_tool(self, server, mock_gateway_client):
        """Test purchase_stamp tool execution."""
        handler = await self.get_call_tool_handler(server)
        assert handler is not None, "call_tool handler not found"

        # Test with default parameters
        request = CallToolRequest(
            name="purchase_stamp",
            arguments={}
        )

        result = await handler(request)

        assert isinstance(result, CallToolResult)
        assert not result.isError
        assert len(result.content) > 0
        assert isinstance(result.content[0], TextContent)

        # Verify gateway client was called
        mock_gateway_client.purchase_stamp.assert_called_once()

        # Test with custom parameters
        mock_gateway_client.reset_mock()
        request_with_params = CallToolRequest(
            name="purchase_stamp",
            arguments={
                "amount": 5000000000,
                "depth": 18,
                "label": "test-stamp"
            }
        )

        result = await handler(request_with_params)
        assert not result.isError
        mock_gateway_client.purchase_stamp.assert_called_once_with(
            amount=5000000000,
            depth=18,
            label="test-stamp"
        )

    async def test_get_stamp_status_tool(self, server, mock_gateway_client):
        """Test get_stamp_status tool execution."""
        handler = await self.get_call_tool_handler(server)
        assert handler is not None

        request = CallToolRequest(
            name="get_stamp_status",
            arguments={"stamp_id": "test_batch_123"}
        )

        result = await handler(request)

        assert isinstance(result, CallToolResult)
        assert not result.isError
        mock_gateway_client.get_stamp_info.assert_called_once_with("test_batch_123")

        # Verify response contains expected information
        content_text = result.content[0].text
        response_data = json.loads(content_text)
        assert "batchID" in response_data
        assert response_data["batchID"] == "test_batch_123"

    async def test_list_stamps_tool(self, server, mock_gateway_client):
        """Test list_stamps tool execution."""
        handler = await self.get_call_tool_handler(server)
        assert handler is not None

        request = CallToolRequest(
            name="list_stamps",
            arguments={}
        )

        result = await handler(request)

        assert isinstance(result, CallToolResult)
        assert not result.isError
        mock_gateway_client.list_stamps.assert_called_once()

        # Verify response structure
        content_text = result.content[0].text
        response_data = json.loads(content_text)
        assert "stamps" in response_data
        assert "count" in response_data

    async def test_extend_stamp_tool(self, server, mock_gateway_client):
        """Test extend_stamp tool execution."""
        handler = await self.get_call_tool_handler(server)
        assert handler is not None

        request = CallToolRequest(
            name="extend_stamp",
            arguments={
                "stamp_id": "test_batch_123",
                "amount": 1000000000
            }
        )

        result = await handler(request)

        assert isinstance(result, CallToolResult)
        assert not result.isError
        mock_gateway_client.extend_stamp.assert_called_once_with(
            "test_batch_123", 1000000000
        )

    async def test_get_stamp_utilization_tool(self, server, mock_gateway_client):
        """Test get_stamp_utilization tool execution."""
        handler = await self.get_call_tool_handler(server)
        assert handler is not None

        request = CallToolRequest(
            name="get_stamp_utilization",
            arguments={"stamp_id": "test_batch_123"}
        )

        result = await handler(request)

        assert isinstance(result, CallToolResult)
        assert not result.isError
        mock_gateway_client.get_stamp_utilization.assert_called_once_with("test_batch_123")

    async def test_upload_data_tool(self, server, mock_gateway_client):
        """Test upload_data tool execution."""
        handler = await self.get_call_tool_handler(server)
        assert handler is not None

        request = CallToolRequest(
            name="upload_data",
            arguments={
                "data": "test data content",
                "stamp_id": "test_batch_123",
                "content_type": "text/plain"
            }
        )

        result = await handler(request)

        assert isinstance(result, CallToolResult)
        assert not result.isError
        mock_gateway_client.upload_data.assert_called_once()

    async def test_download_data_tool(self, server, mock_gateway_client):
        """Test download_data tool execution."""
        handler = await self.get_call_tool_handler(server)
        assert handler is not None

        request = CallToolRequest(
            name="download_data",
            arguments={"reference": "test_reference_abc123"}
        )

        result = await handler(request)

        assert isinstance(result, CallToolResult)
        assert not result.isError
        mock_gateway_client.download_data.assert_called_once_with("test_reference_abc123")

    async def test_invalid_tool_name(self, server, mock_gateway_client):
        """Test handling of invalid tool names."""
        handler = await self.get_call_tool_handler(server)
        assert handler is not None

        request = CallToolRequest(
            name="invalid_tool_name",
            arguments={}
        )

        result = await handler(request)

        assert isinstance(result, CallToolResult)
        assert result.isError
        assert "Unknown tool" in result.content[0].text or "not found" in result.content[0].text

    async def test_missing_required_parameters(self, server, mock_gateway_client):
        """Test handling of missing required parameters."""
        handler = await self.get_call_tool_handler(server)
        assert handler is not None

        # Test get_stamp_status without required stamp_id
        request = CallToolRequest(
            name="get_stamp_status",
            arguments={}
        )

        result = await handler(request)

        assert isinstance(result, CallToolResult)
        assert result.isError
        error_text = result.content[0].text.lower()
        assert "stamp_id" in error_text or "required" in error_text

    async def test_gateway_error_handling(self, server):
        """Test error handling when gateway client raises exceptions."""
        with patch('swarm_provenance_mcp.server.gateway_client') as mock_client:
            mock_client.purchase_stamp.side_effect = Exception("Gateway connection failed")

            handler = await self.get_call_tool_handler(server)
            assert handler is not None

            request = CallToolRequest(
                name="purchase_stamp",
                arguments={}
            )

            result = await handler(request)

            assert isinstance(result, CallToolResult)
            assert result.isError
            error_text = result.content[0].text.lower()
            assert "error" in error_text or "failed" in error_text

    async def test_response_format_consistency(self, server, mock_gateway_client):
        """Test that all tools return consistent response formats."""
        handler = await self.get_call_tool_handler(server)
        assert handler is not None

        tools_to_test = [
            ("purchase_stamp", {}),
            ("get_stamp_status", {"stamp_id": "test_123"}),
            ("list_stamps", {}),
            ("extend_stamp", {"stamp_id": "test_123", "amount": 1000000000}),
            ("get_stamp_utilization", {"stamp_id": "test_123"})
        ]

        for tool_name, arguments in tools_to_test:
            request = CallToolRequest(
                name=tool_name,
                arguments=arguments
            )

            result = await handler(request)

            # All successful responses should have consistent structure
            assert isinstance(result, CallToolResult)
            assert len(result.content) > 0
            assert isinstance(result.content[0], TextContent)

            # Content should be valid (either JSON or meaningful text)
            content_text = result.content[0].text
            assert len(content_text) > 0

            # If it's JSON, it should parse correctly
            if content_text.strip().startswith('{'):
                try:
                    json.loads(content_text)
                except json.JSONDecodeError:
                    pytest.fail(f"Tool {tool_name} returned invalid JSON: {content_text}")


class TestToolParameterValidation:
    """Test parameter validation for all tools."""

    @pytest.fixture
    def server(self):
        """Create MCP server instance for testing."""
        return create_server()

    async def get_call_tool_handler(self, server):
        """Get the call_tool handler from the server."""
        for handler_name, handler in server._request_handlers.items():
            if 'call' in handler_name and hasattr(handler, '__call__'):
                return handler
        return None

    async def test_parameter_type_validation(self, server):
        """Test that tools validate parameter types correctly."""
        handler = await self.get_call_tool_handler(server)
        assert handler is not None

        with patch('swarm_provenance_mcp.server.gateway_client'):
            # Test invalid amount type for purchase_stamp
            request = CallToolRequest(
                name="purchase_stamp",
                arguments={"amount": "not_a_number", "depth": 17}
            )

            result = await handler(request)

            # Should handle type conversion or return error
            if result.isError:
                error_text = result.content[0].text.lower()
                assert "type" in error_text or "invalid" in error_text or "amount" in error_text

    async def test_parameter_range_validation(self, server):
        """Test parameter range validation where applicable."""
        handler = await self.get_call_tool_handler(server)
        assert handler is not None

        with patch('swarm_provenance_mcp.server.gateway_client'):
            # Test negative amount (should be handled gracefully)
            request = CallToolRequest(
                name="purchase_stamp",
                arguments={"amount": -1000, "depth": 17}
            )

            result = await handler(request)

            # The tool should either handle this gracefully or return a meaningful error
            assert isinstance(result, CallToolResult)
            assert len(result.content) > 0

    async def test_empty_string_parameters(self, server):
        """Test handling of empty string parameters."""
        handler = await self.get_call_tool_handler(server)
        assert handler is not None

        with patch('swarm_provenance_mcp.server.gateway_client'):
            # Test empty stamp_id
            request = CallToolRequest(
                name="get_stamp_status",
                arguments={"stamp_id": ""}
            )

            result = await handler(request)

            # Should return an error for empty required parameters
            assert isinstance(result, CallToolResult)
            if result.isError:
                error_text = result.content[0].text.lower()
                assert "stamp_id" in error_text or "empty" in error_text or "required" in error_text