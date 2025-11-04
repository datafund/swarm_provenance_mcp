"""
Provenance record schemas and validation for the MCP server.
Supports multiple standards including DaTA, PROV-O, and custom formats.
"""

import json
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
    def validate_record(record: Dict[str, Any], schema_type: str = "simple") -> tuple[bool, List[str]]:
        """
        Validate a provenance record against a schema.

        Args:
            record: The provenance record to validate
            schema_type: "simple", "data", or "custom"

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        try:
            import jsonschema

            if schema_type == "simple":
                schema = ProvenanceStandards.SIMPLE_SCHEMA
            elif schema_type == "data":
                schema = ProvenanceStandards.DATA_SCHEMA
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
        }
    }