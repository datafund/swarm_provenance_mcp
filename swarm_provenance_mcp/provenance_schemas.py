"""
Provenance record schemas and validation for the MCP server.
Supports multiple standards including DaTA, PROV-O, and custom formats.
"""

import json
import base64
from typing import Dict, Any, Optional, List
from datetime import datetime
import hashlib


class ProvenanceStandards:
    """Definitions for various provenance standards."""

    # DaTA (Data Transparency and Accountability) standard
    DATA_SCHEMA = {
        "type": "object",
        "properties": {
            "provenance_standard": {
                "type": "string",
                "enum": ["DaTA v1.0.0", "DaTA v1.1.0"],
                "description": "The provenance standard being used"
            },
            "content_hash": {
                "type": "string",
                "pattern": "^(sha256:|md5:|sha1:)[a-fA-F0-9]+$",
                "description": "Hash of the actual data content"
            },
            "timestamp": {
                "type": "string",
                "format": "date-time",
                "description": "ISO 8601 timestamp when record was created"
            },
            "creator": {
                "type": "object",
                "properties": {
                    "agent_type": {"type": "string"},
                    "agent_id": {"type": "string"},
                    "name": {"type": "string"}
                },
                "required": ["agent_type", "agent_id"]
            },
            "data": {
                "type": "object",
                "description": "The actual data content being stored"
            },
            "lineage": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_reference": {"type": "string"},
                        "transformation": {"type": "string"},
                        "timestamp": {"type": "string", "format": "date-time"}
                    }
                }
            },
            "verification": {
                "type": "object",
                "properties": {
                    "method": {"type": "string"},
                    "signature": {"type": "string"},
                    "public_key": {"type": "string"}
                }
            },
            "metadata": {
                "type": "object",
                "properties": {
                    "purpose": {"type": "string"},
                    "retention_period": {"type": "string"},
                    "access_level": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}}
                }
            }
        },
        "required": ["provenance_standard", "content_hash", "timestamp", "creator", "data"]
    }

    # Simplified provenance schema for basic use cases
    SIMPLE_SCHEMA = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Human-readable title for this data"},
            "description": {"type": "string", "description": "What this data contains"},
            "creator": {"type": "string", "description": "Who created this data"},
            "created_at": {"type": "string", "format": "date-time"},
            "purpose": {"type": "string", "description": "Why this data was created"},
            "data": {"description": "The actual data content"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "source": {"type": "string", "description": "Where this data came from"}
        },
        "required": ["title", "creator", "data"]
    }

    # SWIP (Swarm Interoperability Protocol) wrapper schema
    SWIP_SCHEMA = {
        "type": "object",
        "properties": {
            "content_hash": {
                "type": "string",
                "pattern": "^sha256:[a-fA-F0-9]{64}$",
                "description": "SHA-256 hash of the raw provenance data (before Base64 encoding)"
            },
            "provenance_standard": {
                "type": "string",
                "description": "Standard used for the inner provenance data (e.g., 'DaTA v1.0.0', 'W3C PROV', 'custom')"
            },
            "encryption": {
                "type": "string",
                "enum": ["none", "aes-256-gcm"],
                "default": "none",
                "description": "Encryption method used (default: 'none')"
            },
            "data": {
                "type": "string",
                "description": "Base64-encoded provenance data (actual content in any format)"
            },
            "stamp_id": {
                "type": "string",
                "pattern": "^[a-fA-F0-9]{64}$",
                "description": "Swarm stamp ID used for TTL management"
            }
        },
        "required": ["content_hash", "provenance_standard", "data", "stamp_id"]
    }


class ProvenanceBuilder:
    """Helper class for building provenance records."""

    @staticmethod
    def create_data_record(
        data: Any,
        creator_name: str,
        creator_type: str = "ai_agent",
        purpose: str = None,
        tags: List[str] = None,
        standard: str = "DaTA v1.0.0"
    ) -> Dict[str, Any]:
        """
        Create a DaTA-compliant provenance record.

        Args:
            data: The actual data content
            creator_name: Name/ID of the creator
            creator_type: Type of creator (ai_agent, human, system, etc.)
            purpose: Purpose/reason for creating this data
            tags: Optional tags for categorization
            standard: Provenance standard to use

        Returns:
            Complete provenance record
        """
        # Serialize data to calculate hash
        data_str = json.dumps(data, sort_keys=True) if not isinstance(data, str) else data
        content_hash = f"sha256:{hashlib.sha256(data_str.encode()).hexdigest()}"

        record = {
            "provenance_standard": standard,
            "content_hash": content_hash,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "creator": {
                "agent_type": creator_type,
                "agent_id": creator_name,
                "name": creator_name
            },
            "data": data
        }

        # Add optional fields
        if purpose or tags:
            record["metadata"] = {}
            if purpose:
                record["metadata"]["purpose"] = purpose
            if tags:
                record["metadata"]["tags"] = tags

        return record

    @staticmethod
    def create_simple_record(
        title: str,
        data: Any,
        creator: str,
        description: str = None,
        purpose: str = None,
        source: str = None,
        tags: List[str] = None
    ) -> Dict[str, Any]:
        """
        Create a simple provenance record for basic use cases.

        Args:
            title: Human-readable title
            data: The actual data content
            creator: Who created this
            description: What this data contains
            purpose: Why this was created
            source: Where this came from
            tags: Categorization tags

        Returns:
            Simple provenance record
        """
        record = {
            "title": title,
            "creator": creator,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "data": data
        }

        # Add optional fields
        if description:
            record["description"] = description
        if purpose:
            record["purpose"] = purpose
        if source:
            record["source"] = source
        if tags:
            record["tags"] = tags

        return record

    @staticmethod
    def create_swip_record(
        provenance_data: Dict[str, Any],
        stamp_id: str,
        provenance_standard: str = "DaTA v1.0.0",
        encryption: str = "none"
    ) -> Dict[str, Any]:
        """
        Create a SWIP-compliant wrapper record for Swarm storage.

        Args:
            provenance_data: The inner provenance record (DaTA, simple, etc.)
            stamp_id: Swarm stamp ID for TTL management
            provenance_standard: Standard used for inner data
            encryption: Encryption method (default: "none")

        Returns:
            SWIP-wrapped record ready for Swarm upload
        """
        # Clean stamp_id (remove 0x prefix if present)
        if stamp_id.startswith("0x"):
            stamp_id = stamp_id[2:]

        # Serialize the inner provenance data
        data_str = json.dumps(provenance_data, sort_keys=True)
        data_bytes = data_str.encode('utf-8')

        # Calculate hash of raw data (before Base64 encoding)
        content_hash = f"sha256:{hashlib.sha256(data_bytes).hexdigest()}"

        # Base64 encode the data
        data_b64 = base64.b64encode(data_bytes).decode('utf-8')

        # Create SWIP wrapper
        swip_record = {
            "content_hash": content_hash,
            "provenance_standard": provenance_standard,
            "encryption": encryption,
            "data": data_b64,
            "stamp_id": stamp_id
        }

        return swip_record

    @staticmethod
    def extract_from_swip(swip_record: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
        """
        Extract and verify provenance data from a SWIP record.

        Args:
            swip_record: SWIP-wrapped record from Swarm

        Returns:
            Tuple of (inner_provenance_data, is_valid)
        """
        try:
            # Extract and decode the data
            data_b64 = swip_record.get("data", "")
            data_bytes = base64.b64decode(data_b64)

            # Verify hash
            expected_hash = swip_record.get("content_hash", "")
            actual_hash = f"sha256:{hashlib.sha256(data_bytes).hexdigest()}"

            if expected_hash != actual_hash:
                return {}, False

            # Parse JSON
            provenance_data = json.loads(data_bytes.decode('utf-8'))
            return provenance_data, True

        except Exception:
            return {}, False

    @staticmethod
    def validate_record(record: Dict[str, Any], schema_type: str = "simple") -> tuple[bool, List[str]]:
        """
        Validate a provenance record against a schema.

        Args:
            record: The provenance record to validate
            schema_type: "simple", "data", "swip", or "custom"

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        try:
            import jsonschema

            if schema_type == "simple":
                schema = ProvenanceStandards.SIMPLE_SCHEMA
            elif schema_type == "data":
                schema = ProvenanceStandards.DATA_SCHEMA
            elif schema_type == "swip":
                schema = ProvenanceStandards.SWIP_SCHEMA
            else:
                return False, ["Unknown schema type"]

            jsonschema.validate(record, schema)
            return True, []

        except ImportError:
            # If jsonschema not available, do basic validation
            return ProvenanceBuilder._basic_validate(record, schema_type)
        except Exception as e:
            return False, [str(e)]

    @staticmethod
    def _basic_validate(record: Dict[str, Any], schema_type: str) -> tuple[bool, List[str]]:
        """Basic validation without jsonschema library."""
        errors = []

        if schema_type == "simple":
            required_fields = ["title", "creator", "data"]
        elif schema_type == "data":
            required_fields = ["provenance_standard", "content_hash", "timestamp", "creator", "data"]
        elif schema_type == "swip":
            required_fields = ["content_hash", "provenance_standard", "data", "stamp_id"]
        else:
            return False, ["Unknown schema type"]

        for field in required_fields:
            if field not in record:
                errors.append(f"Missing required field: {field}")

        return len(errors) == 0, errors


class ProvenanceGuidance:
    """Provides guidance text for creating proper provenance records."""

    UPLOAD_GUIDANCE = """
🔍 PROVENANCE BEST PRACTICES:

For research data, journalism, or any data requiring verification, consider creating a structured provenance record:

📋 **Simple Provenance Structure:**
```json
{
  "title": "Brief description of what this is",
  "creator": "Your name or AI agent ID",
  "purpose": "Why this data was created",
  "data": { /* your actual data here */ },
  "created_at": "2024-11-04T10:30:00Z",
  "tags": ["research", "experiment", "analysis"]
}
```

🔬 **For Research/Scientific Data:**
```json
{
  "provenance_standard": "DaTA v1.0.0",
  "content_hash": "sha256:abc123...",
  "timestamp": "2024-11-04T10:30:00Z",
  "creator": {"agent_type": "ai_agent", "agent_id": "claude", "name": "Claude"},
  "data": { /* your research data */ },
  "lineage": [{"source_reference": "original_dataset_ref", "transformation": "analysis"}],
  "metadata": {"purpose": "climate_analysis", "tags": ["climate", "temperature"]}
}
```

🌐 **SWIP-Wrapped Format (for Swarm storage):**
```json
{
  "content_hash": "sha256:hash_of_inner_data...",
  "provenance_standard": "DaTA v1.0.0",
  "encryption": "none",
  "data": "base64_encoded_provenance_data...",
  "stamp_id": "your_swarm_stamp_id"
}
```

💡 **Benefits:**
- Verifiable data authenticity
- Clear audit trails
- Reproducible research
- Legal compliance
- Attribution tracking

You can upload any JSON structure, but provenance-aware formats help establish trust and traceability.
"""

    SCHEMA_EXAMPLES = {
        "simple": {
            "title": "Daily Temperature Readings",
            "creator": "Weather Station AI",
            "purpose": "Climate monitoring for research",
            "data": {
                "location": "San Francisco, CA",
                "readings": [
                    {"time": "2024-11-04T09:00:00Z", "temp_c": 18.5},
                    {"time": "2024-11-04T12:00:00Z", "temp_c": 22.1}
                ]
            },
            "tags": ["weather", "temperature", "monitoring"]
        },
        "research": {
            "provenance_standard": "DaTA v1.0.0",
            "content_hash": "sha256:a1b2c3d4e5f6...",
            "timestamp": "2024-11-04T10:30:00Z",
            "creator": {
                "agent_type": "ai_agent",
                "agent_id": "claude-3-sonnet",
                "name": "Claude AI Assistant"
            },
            "data": {
                "experiment_id": "EXP-2024-001",
                "hypothesis": "Temperature affects plant growth rate",
                "results": [
                    {"condition": "20C", "growth_rate": 2.3},
                    {"condition": "25C", "growth_rate": 3.1}
                ]
            },
            "lineage": [
                {
                    "source_reference": "sensor_data_ref_123",
                    "transformation": "statistical_analysis",
                    "timestamp": "2024-11-04T09:00:00Z"
                }
            ],
            "metadata": {
                "purpose": "botanical_research",
                "retention_period": "10_years",
                "access_level": "public",
                "tags": ["botany", "temperature", "growth"]
            }
        },
        "swip": {
            "content_hash": "sha256:a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4",
            "provenance_standard": "DaTA v1.0.0",
            "encryption": "none",
            "data": "eyJ0aXRsZSI6IlJlc2VhcmNoIERhdGEiLCJjcmVhdG9yIjoiQUkgQWdlbnQi...",
            "stamp_id": "fe2f1db89065c8c11d10b87a5a2e8bc0e1c9a8a7c1b2e0f8c7e6d5c4b3a21234"
        }
    }