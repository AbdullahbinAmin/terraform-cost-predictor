"""Tests for the budget checker."""

import pytest
import tempfile
from pathlib import Path

from internal.budget.budget_checker import BudgetChecker


BUDGET_YAML = """
budget:
  monthly_limit: 200
  currency: USD
  alert_threshold: 0.8
  environments:
    production:
      monthly_limit: 500
      alert_threshold: 0.85
    staging:
      monthly_limit: 100
      alert_threshold: 0.75
"""


class TestBudgetChecker:
    def _checker_from_yaml(self, yaml_content: str) -> BudgetChecker:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            path = f.name
        checker = BudgetChecker(path)
        Path(path).unlink(missing_ok=True)
        return checker

    def test_no_config_always_passes(self):
        checker = BudgetChecker()
        result = checker.check(9999.99)
        assert result.passed is True
        assert result.exit_code == 0

    def test_under_limit_passes(self):
        checker = self._checker_from_yaml(BUDGET_YAML)
        result = checker.check(150.0)
        assert result.passed is True
        assert result.exit_code == 0
        assert len(result.violations) == 0

    def test_over_limit_fails(self):
        checker = self._checker_from_yaml(BUDGET_YAML)
        result = checker.check(250.0)
        assert result.passed is False
        assert result.exit_code == 1
        assert len(result.violations) == 1
        assert result.violations[0].overage == 50.0

    def test_at_alert_threshold_warns(self):
        checker = self._checker_from_yaml(BUDGET_YAML)
        # 80% of 200 = 160, exactly at threshold
        result = checker.check(165.0)
        assert result.passed is True  # Still passes
        assert len(result.warnings) > 0
        assert result.exit_code == 0

    def test_below_alert_threshold_no_warning(self):
        checker = self._checker_from_yaml(BUDGET_YAML)
        result = checker.check(100.0)
        assert result.passed is True
        assert len(result.warnings) == 0

    def test_production_environment_limit(self):
        checker = self._checker_from_yaml(BUDGET_YAML)
        # 250 is under production limit (500) but over global (200)
        result = checker.check(250.0, environment="production")
        # Should fail on global but pass on production — both are checked
        assert result.passed is False  # global violation

    def test_staging_environment_over_limit(self):
        checker = self._checker_from_yaml(BUDGET_YAML)
        result = checker.check(120.0, environment="staging")
        # 120 > staging limit 100
        assert result.passed is False

    def test_staging_environment_under_limit(self):
        checker = self._checker_from_yaml(BUDGET_YAML)
        result = checker.check(50.0, environment="staging")
        assert result.passed is True

    def test_nonexistent_file_raises(self):
        checker = BudgetChecker()
        with pytest.raises(FileNotFoundError):
            checker.load_config("/nonexistent/budget.yaml")

    def test_monthly_limit_property(self):
        checker = self._checker_from_yaml(BUDGET_YAML)
        assert checker.monthly_limit == 200

    def test_currency_property(self):
        checker = self._checker_from_yaml(BUDGET_YAML)
        assert checker.currency == "USD"

    def test_violation_details(self):
        checker = self._checker_from_yaml(BUDGET_YAML)
        result = checker.check(300.0)
        v = result.violations[0]
        assert v.limit == 200.0
        assert v.estimated_cost == 300.0
        assert v.overage == 100.0
        assert abs(v.overage_percent - 50.0) < 0.1

    def test_result_message_contains_info(self):
        checker = self._checker_from_yaml(BUDGET_YAML)
        result = checker.check(250.0)
        assert "EXCEEDED" in result.message or "250" in result.message
