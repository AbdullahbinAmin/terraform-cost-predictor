"""
Terraform Plan Parser

Parses the JSON output of `terraform show -json tfplan` and extracts
resource changes with their configuration attributes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# Actions as defined by Terraform plan JSON format
ACTION_CREATE = "create"
ACTION_DELETE = "delete"
ACTION_UPDATE = "update"
ACTION_NO_OP = "no-op"
ACTION_REPLACE = "replace"

# Supported AWS resource types for cost estimation
SUPPORTED_RESOURCE_TYPES = {
    "aws_instance",
    "aws_db_instance",
    "aws_lb",
    "aws_alb",
    "aws_nat_gateway",
    "aws_ebs_volume",
    "aws_s3_bucket",
    "aws_elasticache_cluster",
    "aws_elasticache_replication_group",
    "aws_lambda_function",
    "aws_rds_cluster",
    "aws_eks_cluster",
    "aws_ecs_service",
    "aws_cloudfront_distribution",
    "aws_elasticsearch_domain",
    "aws_opensearch_domain",
    "aws_kinesis_stream",
    "aws_sqs_queue",
    "aws_sns_topic",
    "aws_api_gateway_rest_api",
    "aws_api_gateway_v2_api",
    "aws_wafv2_web_acl",
    "aws_route53_zone",
}


@dataclass
class ResourceChange:
    """Represents a single resource change from the Terraform plan."""

    address: str  # e.g., "aws_instance.web"
    resource_type: str  # e.g., "aws_instance"
    name: str  # e.g., "web"
    module: str  # e.g., "" or "module.vpc"
    provider: str  # e.g., "registry.terraform.io/hashicorp/aws"
    action: str  # create | delete | update | no-op | replace
    before: dict[str, Any]  # config before change (for updates)
    after: dict[str, Any]  # config after change (desired state)
    is_supported: bool = False  # whether cost estimation is supported
    region: str = "us-east-1"  # AWS region


@dataclass
class TerraformPlan:
    """Parsed representation of a Terraform plan."""

    format_version: str
    terraform_version: str
    variables: dict[str, Any]
    resource_changes: list[ResourceChange]
    raw: dict[str, Any]  # full raw plan for debugging

    @property
    def created_resources(self) -> list[ResourceChange]:
        return [r for r in self.resource_changes if r.action == ACTION_CREATE]

    @property
    def deleted_resources(self) -> list[ResourceChange]:
        return [r for r in self.resource_changes if r.action == ACTION_DELETE]

    @property
    def updated_resources(self) -> list[ResourceChange]:
        return [r for r in self.resource_changes if r.action == ACTION_UPDATE]

    @property
    def replaced_resources(self) -> list[ResourceChange]:
        return [r for r in self.resource_changes if r.action == ACTION_REPLACE]

    @property
    def relevant_changes(self) -> list[ResourceChange]:
        """Resources that affect cost (create, delete, update, replace)."""
        return [r for r in self.resource_changes if r.action != ACTION_NO_OP]

    @property
    def supported_resources(self) -> list[ResourceChange]:
        return [r for r in self.resource_changes if r.is_supported]


class PlanParseError(Exception):
    """Raised when the Terraform plan JSON cannot be parsed."""

    pass


class PlanParser:
    """
    Parses terraform plan JSON files.

    Usage:
        parser = PlanParser()
        plan = parser.parse_file("plan.json")
        # or
        plan = parser.parse_json(json_string)
    """

    def parse_file(self, path: str | Path) -> TerraformPlan:
        """Parse a Terraform plan JSON file from disk."""
        p = Path(path)
        if not p.exists():
            raise PlanParseError(f"Plan file not found: {path}")
        if not p.suffix == ".json":
            raise PlanParseError(
                "Expected a JSON file. Run: terraform show -json tfplan > plan.json"
            )

        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise PlanParseError(f"Invalid JSON in plan file: {e}") from e

        return self._parse_data(data)

    def parse_json(self, json_string: str) -> TerraformPlan:
        """Parse a Terraform plan from a JSON string."""
        try:
            data = json.loads(json_string)
        except json.JSONDecodeError as e:
            raise PlanParseError(f"Invalid JSON: {e}") from e
        return self._parse_data(data)

    def parse_dict(self, data: dict[str, Any]) -> TerraformPlan:
        """Parse a Terraform plan from a Python dictionary."""
        return self._parse_data(data)

    def _parse_data(self, data: dict[str, Any]) -> TerraformPlan:
        """Core parsing logic."""
        if not isinstance(data, dict):
            raise PlanParseError("Plan JSON must be a JSON object at the root level.")

        # Validate this looks like a terraform plan
        if "resource_changes" not in data and "planned_values" not in data:
            raise PlanParseError(
                "This does not appear to be a Terraform plan JSON. "
                "Generate it with: terraform show -json tfplan > plan.json"
            )

        format_version = data.get("format_version", "unknown")
        terraform_version = data.get("terraform_version", "unknown")
        variables = data.get("variables", {})

        # Detect region from provider config if available
        default_region = self._extract_region(data)

        resource_changes = []
        for rc in data.get("resource_changes", []):
            parsed = self._parse_resource_change(rc, default_region)
            if parsed:
                resource_changes.append(parsed)

        return TerraformPlan(
            format_version=format_version,
            terraform_version=terraform_version,
            variables=variables,
            resource_changes=resource_changes,
            raw=data,
        )

    def _parse_resource_change(
        self, rc: dict[str, Any], default_region: str
    ) -> ResourceChange | None:
        """Parse a single resource_change entry."""
        if not isinstance(rc, dict):
            return None

        address = rc.get("address", "")
        resource_type = rc.get("type", "")
        name = rc.get("name", "")
        module_address = rc.get("module_address", "")
        provider = rc.get("provider_name", "")

        # Extract change info
        change = rc.get("change", {})
        actions = change.get("actions", ["no-op"])

        # Determine the primary action
        action = self._resolve_action(actions)

        # Extract before/after config
        before = change.get("before") or {}
        after = change.get("after") or {}

        # Use after_unknown values as fallback for unknowns
        after_unknown = change.get("after_unknown") or {}
        after = self._merge_after_unknown(after, after_unknown)

        # Detect region from resource tags or provider
        region = self._extract_resource_region(after, default_region)

        is_supported = resource_type in SUPPORTED_RESOURCE_TYPES

        return ResourceChange(
            address=address,
            resource_type=resource_type,
            name=name,
            module=module_address,
            provider=provider,
            action=action,
            before=before,
            after=after,
            is_supported=is_supported,
            region=region,
        )

    def _resolve_action(self, actions: list[str]) -> str:
        """Resolve the list of actions to a single action string."""
        if not actions:
            return ACTION_NO_OP
        if len(actions) == 1:
            return actions[0]
        # ["delete", "create"] means replace
        if set(actions) == {"delete", "create"} or set(actions) == {"create", "delete"}:
            return ACTION_REPLACE
        # Return the first action if nothing else matches
        return actions[0]

    def _merge_after_unknown(
        self, after: dict[str, Any], after_unknown: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Terraform marks computed values as `true` in after_unknown.
        We preserve the known values and mark unknowns clearly.
        """
        merged = dict(after)
        for key, val in after_unknown.items():
            if val is True and key not in merged:
                merged[key] = "(computed)"
        return merged

    def _extract_region(self, data: dict[str, Any]) -> str:
        """Try to extract AWS region from provider configuration."""
        try:
            configs = data.get("configuration", {}).get("provider_config", {})
            for provider_name, provider_conf in configs.items():
                if "aws" in provider_name.lower():
                    expressions = provider_conf.get("expressions", {})
                    region_expr = expressions.get("region", {})
                    if isinstance(region_expr, dict):
                        return region_expr.get("constant_value", "us-east-1")
        except (KeyError, TypeError, AttributeError):
            pass
        return "us-east-1"

    def _extract_resource_region(self, after: dict[str, Any], default: str) -> str:
        """Try to get region from resource tags or metadata."""
        tags = after.get("tags") or {}
        if isinstance(tags, dict):
            if region := tags.get("Region") or tags.get("region") or tags.get("aws_region"):
                return region
        return default


def parse_plan(path: str | Path) -> TerraformPlan:
    """Convenience function to parse a plan file."""
    return PlanParser().parse_file(path)
