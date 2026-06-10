"""Tests for the cost comparator."""

from internal.compare.comparator import CostComparator


CURRENT_RESOURCES = [
    {
        "address": "aws_instance.web",
        "resource_type": "aws_instance",
        "monthly_cost": 48.91,
        "config": {"instance_type": "t3.medium"},
    },
    {
        "address": "aws_nat_gateway.main",
        "resource_type": "aws_nat_gateway",
        "monthly_cost": 32.85,
        "config": {},
    },
    {
        "address": "aws_db_instance.pg",
        "resource_type": "aws_db_instance",
        "monthly_cost": 14.71,
        "config": {"instance_class": "db.t3.micro", "allocated_storage": 20},
    },
]

PREVIOUS_RUN = {
    "run_id": "abc12345-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "timestamp": "2025-01-10T10:00:00+00:00",
    "label": "staging",
    "total_cost": 55.61,
    "resources": [
        {
            "address": "aws_instance.web",
            "resource_type": "aws_instance",
            "monthly_cost": 22.77,  # was t3.small
            "config": {"instance_type": "t3.small"},
        },
        {
            "address": "aws_db_instance.pg",
            "resource_type": "aws_db_instance",
            "monthly_cost": 14.71,
            "config": {"instance_class": "db.t3.micro", "allocated_storage": 20},
        },
        # aws_lb.old — was in previous, now removed
        {
            "address": "aws_lb.old_lb",
            "resource_type": "aws_lb",
            "monthly_cost": 18.13,
            "config": {},
        },
    ],
}


class TestCostComparator:
    def setup_method(self):
        self.comparator = CostComparator()

    def test_comparison_basic(self):
        result = self.comparator.compare(CURRENT_RESOURCES, PREVIOUS_RUN)
        assert result is not None

    def test_previous_total_set(self):
        result = self.comparator.compare(CURRENT_RESOURCES, PREVIOUS_RUN)
        assert result.previous_total == 55.61

    def test_current_total_computed(self):
        result = self.comparator.compare(CURRENT_RESOURCES, PREVIOUS_RUN)
        expected = sum(r["monthly_cost"] for r in CURRENT_RESOURCES)
        assert abs(result.current_total - expected) < 0.01

    def test_delta_computed(self):
        result = self.comparator.compare(CURRENT_RESOURCES, PREVIOUS_RUN)
        expected_delta = result.current_total - result.previous_total
        assert abs(result.delta - expected_delta) < 0.01

    def test_delta_percent_computed(self):
        result = self.comparator.compare(CURRENT_RESOURCES, PREVIOUS_RUN)
        assert result.delta_percent != 0

    def test_added_resources(self):
        """aws_nat_gateway.main is new (not in previous)."""
        result = self.comparator.compare(CURRENT_RESOURCES, PREVIOUS_RUN)
        added_addresses = [r.address for r in result.added]
        assert "aws_nat_gateway.main" in added_addresses

    def test_removed_resources(self):
        """aws_lb.old_lb was in previous but not in current."""
        result = self.comparator.compare(CURRENT_RESOURCES, PREVIOUS_RUN)
        removed_addresses = [r.address for r in result.removed]
        assert "aws_lb.old_lb" in removed_addresses

    def test_changed_resources(self):
        """aws_instance.web changed from t3.small to t3.medium."""
        result = self.comparator.compare(CURRENT_RESOURCES, PREVIOUS_RUN)
        changed_addresses = [r.address for r in result.changed]
        assert "aws_instance.web" in changed_addresses

    def test_unchanged_resources(self):
        """aws_db_instance.pg has same cost as before."""
        result = self.comparator.compare(CURRENT_RESOURCES, PREVIOUS_RUN)
        unchanged_addresses = [r.address for r in result.unchanged]
        assert "aws_db_instance.pg" in unchanged_addresses

    def test_removed_has_negative_delta(self):
        result = self.comparator.compare(CURRENT_RESOURCES, PREVIOUS_RUN)
        removed = next(r for r in result.removed if r.address == "aws_lb.old_lb")
        assert removed.delta < 0

    def test_added_has_positive_delta(self):
        result = self.comparator.compare(CURRENT_RESOURCES, PREVIOUS_RUN)
        added = next(r for r in result.added if r.address == "aws_nat_gateway.main")
        assert added.delta > 0

    def test_top_drivers_sorted_by_abs_delta(self):
        result = self.comparator.compare(CURRENT_RESOURCES, PREVIOUS_RUN)
        drivers = result.top_drivers
        assert len(drivers) > 0
        # Verify sorted by absolute delta descending
        for i in range(len(drivers) - 1):
            assert abs(drivers[i].delta) >= abs(drivers[i + 1].delta)

    def test_top_drivers_excludes_unchanged(self):
        result = self.comparator.compare(CURRENT_RESOURCES, PREVIOUS_RUN)
        for d in result.top_drivers:
            assert d.delta != 0

    def test_is_increase_property(self):
        result = self.comparator.compare(CURRENT_RESOURCES, PREVIOUS_RUN)
        if result.delta > 0:
            assert result.is_increase
            assert not result.is_decrease
        elif result.delta < 0:
            assert result.is_decrease
            assert not result.is_increase

    def test_config_changes_detected(self):
        result = self.comparator.compare(CURRENT_RESOURCES, PREVIOUS_RUN)
        changed = next((r for r in result.changed if r.address == "aws_instance.web"), None)
        assert changed is not None
        # instance_type should be detected as a config change
        assert len(changed.config_changes) > 0

    def test_reason_not_empty(self):
        result = self.comparator.compare(CURRENT_RESOURCES, PREVIOUS_RUN)
        for diff in result.all_diffs:
            assert diff.reason is not None
            assert len(diff.reason) > 0

    def test_empty_previous_all_added(self):
        """If previous run has no resources, everything should be 'added'."""
        prev_run = {
            "run_id": "empty",
            "timestamp": "2025-01-01T00:00:00+00:00",
            "label": "",
            "total_cost": 0.0,
            "resources": [],
        }
        result = self.comparator.compare(CURRENT_RESOURCES, prev_run)
        assert len(result.added) == len(CURRENT_RESOURCES)
        assert len(result.removed) == 0
        assert len(result.changed) == 0
