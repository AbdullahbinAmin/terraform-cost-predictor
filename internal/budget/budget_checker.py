"""
Budget Checker — Policy Enforcement

Reads a budget.yaml config and checks estimated costs against defined limits.
Returns a BudgetResult that the CLI uses to determine exit code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class BudgetViolation:
    """A single budget limit violation."""

    environment: str
    limit: float
    estimated_cost: float
    overage: float
    overage_percent: float


@dataclass
class BudgetWarning:
    """A budget warning (approaching limit but not exceeded)."""

    environment: str
    limit: float
    estimated_cost: float
    threshold_percent: float
    usage_percent: float


@dataclass
class BudgetResult:
    """Result of budget policy check."""

    passed: bool
    violations: list[BudgetViolation] = field(default_factory=list)
    warnings: list[BudgetWarning] = field(default_factory=list)
    message: str = ""
    exit_code: int = 0


class BudgetChecker:
    """
    Loads budget.yaml and validates estimated costs.

    Usage:
        checker = BudgetChecker("budget.yaml")
        result = checker.check(total_cost, environment="production")
        if not result.passed:
            sys.exit(1)
    """

    def __init__(self, config_path: str | Path | None = None):
        self._config: dict[str, Any] = {}
        if config_path:
            self.load_config(config_path)

    def load_config(self, path: str | Path) -> None:
        """Load a budget YAML configuration file."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Budget config not found: {path}")
        with open(p, encoding="utf-8") as f:
            self._config = yaml.safe_load(f) or {}
        logger.debug("Budget config loaded from %s", p)

    def check(
        self,
        estimated_cost: float,
        environment: str = "default",
    ) -> BudgetResult:
        """
        Check estimated cost against budget policy.

        Args:
            estimated_cost: Total estimated monthly cost in USD
            environment:    Environment name (e.g., "production", "staging")

        Returns:
            BudgetResult with pass/fail status and exit code
        """
        if not self._config:
            # No budget config — always pass
            return BudgetResult(passed=True, message="No budget policy configured.")

        budget_conf = self._config.get("budget", {})
        violations: list[BudgetViolation] = []
        warnings: list[BudgetWarning] = []

        # --- Global limit ---
        global_limit = budget_conf.get("monthly_limit")
        alert_threshold = budget_conf.get("alert_threshold", 0.8)
        currency = budget_conf.get("currency", "USD")

        if global_limit is not None:
            result = self._check_limit(
                label="global",
                limit=float(global_limit),
                cost=estimated_cost,
                threshold=float(alert_threshold),
            )
            if isinstance(result, BudgetViolation):
                violations.append(result)
            elif isinstance(result, BudgetWarning):
                warnings.append(result)

        # --- Environment-specific limit ---
        envs = budget_conf.get("environments", {})
        if environment in envs:
            env_conf = envs[environment]
            env_limit = env_conf.get("monthly_limit")
            env_threshold = env_conf.get("alert_threshold", alert_threshold)
            if env_limit is not None:
                result = self._check_limit(
                    label=environment,
                    limit=float(env_limit),
                    cost=estimated_cost,
                    threshold=float(env_threshold),
                )
                if isinstance(result, BudgetViolation):
                    violations.append(result)
                elif isinstance(result, BudgetWarning):
                    warnings.append(result)

        if violations:
            msgs = []
            for v in violations:
                msgs.append(
                    f"Budget EXCEEDED for '{v.environment}': "
                    f"${v.estimated_cost:.2f} > ${v.limit:.2f} "
                    f"(+{v.overage_percent:.1f}% over limit)"
                )
            return BudgetResult(
                passed=False,
                violations=violations,
                warnings=warnings,
                message="\n".join(msgs),
                exit_code=1,
            )

        if warnings:
            msgs = []
            for w in warnings:
                msgs.append(
                    f"Budget WARNING for '{w.environment}': "
                    f"${w.estimated_cost:.2f} / ${w.limit:.2f} "
                    f"({w.usage_percent:.1f}% of limit)"
                )
            return BudgetResult(
                passed=True,
                warnings=warnings,
                message="\n".join(msgs),
                exit_code=0,
            )

        limit_str = f"${global_limit:.2f}" if global_limit else "N/A"
        return BudgetResult(
            passed=True,
            message=f"Estimated cost ${estimated_cost:.2f} is within budget {limit_str}",
            exit_code=0,
        )

    def _check_limit(
        self,
        label: str,
        limit: float,
        cost: float,
        threshold: float,
    ) -> BudgetViolation | BudgetWarning | None:
        """Check a single limit and return a violation, warning, or None."""
        if cost > limit:
            overage = cost - limit
            overage_percent = (overage / limit) * 100
            return BudgetViolation(
                environment=label,
                limit=limit,
                estimated_cost=cost,
                overage=round(overage, 2),
                overage_percent=round(overage_percent, 2),
            )
        elif threshold and cost >= limit * threshold:
            usage_percent = (cost / limit) * 100
            return BudgetWarning(
                environment=label,
                limit=limit,
                estimated_cost=cost,
                threshold_percent=threshold * 100,
                usage_percent=round(usage_percent, 2),
            )
        return None

    @property
    def monthly_limit(self) -> float | None:
        return self._config.get("budget", {}).get("monthly_limit")

    @property
    def currency(self) -> str:
        return self._config.get("budget", {}).get("currency", "USD")
