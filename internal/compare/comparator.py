"""
Cost Comparator — The "Killer Feature"

Compares current plan costs against previous run history and generates
a human-readable explanation of WHY costs changed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResourceDiff:
    """Diff entry for a single resource between two runs."""

    address: str
    resource_type: str
    status: str  # added | removed | changed | unchanged | replaced
    previous_cost: float
    current_cost: float
    delta: float  # current - previous (positive = more expensive)
    reason: str  # human-readable explanation
    config_changes: list[str] = field(default_factory=list)


@dataclass
class CostComparison:
    """Full comparison result between two runs."""

    previous_total: float
    current_total: float
    delta: float
    delta_percent: float
    previous_run_id: str
    previous_timestamp: str
    label: str

    # Resource-level diffs
    added: list[ResourceDiff] = field(default_factory=list)
    removed: list[ResourceDiff] = field(default_factory=list)
    changed: list[ResourceDiff] = field(default_factory=list)
    unchanged: list[ResourceDiff] = field(default_factory=list)

    @property
    def all_diffs(self) -> list[ResourceDiff]:
        return self.added + self.removed + self.changed + self.unchanged

    @property
    def top_drivers(self) -> list[ResourceDiff]:
        """Top cost change drivers sorted by absolute delta."""
        drivers = [d for d in self.all_diffs if d.delta != 0]
        return sorted(drivers, key=lambda d: abs(d.delta), reverse=True)[:5]

    @property
    def is_increase(self) -> bool:
        return self.delta > 0

    @property
    def is_decrease(self) -> bool:
        return self.delta < 0


class CostComparator:
    """
    Compares current resource costs with a previous history run.

    Usage:
        comparator = CostComparator()
        comparison = comparator.compare(current_resources, previous_run)
    """

    def compare(
        self,
        current_resources: list[dict[str, Any]],
        previous_run: dict[str, Any],
    ) -> CostComparison:
        """
        Generate a full cost comparison.

        Args:
            current_resources: List of {address, resource_type, monthly_cost, config}
            previous_run:      Dict from HistoryStore.get_latest_run()

        Returns:
            CostComparison with per-resource diffs and cost drivers
        """
        previous_resources: list[dict] = previous_run.get("resources", [])
        prev_run_id = previous_run.get("run_id", "")
        prev_timestamp = previous_run.get("timestamp", "")
        label = previous_run.get("label", "")

        # Build lookup maps by resource address
        prev_map = {r["address"]: r for r in previous_resources}
        curr_map = {r["address"]: r for r in current_resources}

        added: list[ResourceDiff] = []
        removed: list[ResourceDiff] = []
        changed: list[ResourceDiff] = []
        unchanged: list[ResourceDiff] = []

        all_addresses = set(prev_map) | set(curr_map)

        for addr in sorted(all_addresses):
            prev = prev_map.get(addr)
            curr = curr_map.get(addr)

            if prev is None and curr is not None:
                # New resource
                diff = ResourceDiff(
                    address=addr,
                    resource_type=curr.get("resource_type", ""),
                    status="added",
                    previous_cost=0.0,
                    current_cost=curr.get("monthly_cost", 0.0),
                    delta=curr.get("monthly_cost", 0.0),
                    reason=self._describe_added(curr),
                )
                added.append(diff)

            elif curr is None and prev is not None:
                # Removed resource
                diff = ResourceDiff(
                    address=addr,
                    resource_type=prev.get("resource_type", ""),
                    status="removed",
                    previous_cost=prev.get("monthly_cost", 0.0),
                    current_cost=0.0,
                    delta=-prev.get("monthly_cost", 0.0),
                    reason=self._describe_removed(prev),
                )
                removed.append(diff)

            elif prev is not None and curr is not None:
                prev_cost = prev.get("monthly_cost", 0.0)
                curr_cost = curr.get("monthly_cost", 0.0)
                delta = curr_cost - prev_cost

                if abs(delta) < 0.01:
                    # Unchanged
                    diff = ResourceDiff(
                        address=addr,
                        resource_type=curr.get("resource_type", ""),
                        status="unchanged",
                        previous_cost=prev_cost,
                        current_cost=curr_cost,
                        delta=0.0,
                        reason="No cost change",
                    )
                    unchanged.append(diff)
                else:
                    # Changed
                    config_changes = self._detect_config_changes(
                        prev.get("config", {}), curr.get("config", {})
                    )
                    diff = ResourceDiff(
                        address=addr,
                        resource_type=curr.get("resource_type", ""),
                        status="changed",
                        previous_cost=prev_cost,
                        current_cost=curr_cost,
                        delta=delta,
                        reason=self._describe_changed(prev, curr, config_changes),
                        config_changes=config_changes,
                    )
                    changed.append(diff)

        current_total = sum(r.get("monthly_cost", 0.0) for r in current_resources)
        previous_total = previous_run.get("total_cost", 0.0)
        delta = current_total - previous_total
        delta_percent = (delta / previous_total * 100) if previous_total != 0 else 0.0

        return CostComparison(
            previous_total=round(previous_total, 2),
            current_total=round(current_total, 2),
            delta=round(delta, 2),
            delta_percent=round(delta_percent, 2),
            previous_run_id=prev_run_id,
            previous_timestamp=prev_timestamp,
            label=label,
            added=added,
            removed=removed,
            changed=changed,
            unchanged=unchanged,
        )

    # ─── Human-Readable Descriptions ─────────────────────────────────────────

    def _describe_added(self, resource: dict) -> str:
        rt = resource.get("resource_type", "resource")
        cost = resource.get("monthly_cost", 0.0)
        return f"New {rt} added (+${cost:.2f}/mo)"

    def _describe_removed(self, resource: dict) -> str:
        rt = resource.get("resource_type", "resource")
        cost = resource.get("monthly_cost", 0.0)
        return f"{rt} removed (-${cost:.2f}/mo savings)"

    def _describe_changed(self, prev: dict, curr: dict, config_changes: list[str]) -> str:
        rt = curr.get("resource_type", "resource")
        delta = curr.get("monthly_cost", 0.0) - prev.get("monthly_cost", 0.0)
        sign = "+" if delta >= 0 else ""

        parts = [f"{rt} configuration changed ({sign}${delta:.2f}/mo)"]

        # Describe specific attribute changes for key resource types
        prev_conf = prev.get("config", {})
        curr_conf = curr.get("config", {})

        if rt == "aws_instance":
            prev_it = prev_conf.get("instance_type", "?")
            curr_it = curr_conf.get("instance_type", "?")
            if prev_it != curr_it:
                parts.append(f"  Instance type changed: {prev_it} → {curr_it}")

        elif rt == "aws_db_instance":
            prev_ic = prev_conf.get("instance_class", "?")
            curr_ic = curr_conf.get("instance_class", "?")
            if prev_ic != curr_ic:
                parts.append(f"  Instance class changed: {prev_ic} → {curr_ic}")
            prev_sz = prev_conf.get("allocated_storage")
            curr_sz = curr_conf.get("allocated_storage")
            if prev_sz != curr_sz:
                parts.append(f"  Storage changed: {prev_sz} GB → {curr_sz} GB")

        elif rt == "aws_ebs_volume":
            prev_sz = prev_conf.get("size")
            curr_sz = curr_conf.get("size")
            if prev_sz != curr_sz:
                parts.append(f"  Volume size changed: {prev_sz} GB → {curr_sz} GB")
            prev_t = prev_conf.get("type")
            curr_t = curr_conf.get("type")
            if prev_t != curr_t:
                parts.append(f"  Volume type changed: {prev_t} → {curr_t}")

        for change in config_changes[:3]:
            if not any(change in p for p in parts):
                parts.append(f"  Config: {change}")

        return "\n".join(parts)

    def _detect_config_changes(self, prev_config: dict, curr_config: dict) -> list[str]:
        """Detect key attribute changes between two resource configs."""
        changes = []
        all_keys = set(prev_config) | set(curr_config)

        # Focus on attributes that affect cost
        cost_relevant_attrs = {
            "instance_type",
            "instance_class",
            "node_type",
            "allocated_storage",
            "size",
            "volume_size",
            "volume_type",
            "type",
            "multi_az",
            "num_cache_nodes",
            "shard_count",
            "memory_size",
            "load_balancer_type",
        }

        for key in sorted(all_keys):
            if key not in cost_relevant_attrs:
                continue
            prev_val = prev_config.get(key)
            curr_val = curr_config.get(key)
            if prev_val != curr_val:
                changes.append(f"{key}: {prev_val!r} → {curr_val!r}")

        return changes
