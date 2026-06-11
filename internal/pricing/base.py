"""
Base Pricing Engine Interfaces

Defines the CostEstimate structure and the CloudPricingProvider
abstract base class that all cloud-specific pricing engines must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class CostEstimate:
    """Cost estimate for a single resource."""

    resource_address: str
    resource_type: str
    monthly_cost: float
    currency: str = "USD"
    confidence: str = "medium"  # high | medium | low | unknown
    breakdown: dict[str, float] = None  # component costs
    notes: list[str] = None
    is_estimated: bool = True

    def __post_init__(self):
        if self.breakdown is None:
            self.breakdown = {}
        if self.notes is None:
            self.notes = []

    @property
    def formatted_cost(self) -> str:
        return f"${self.monthly_cost:,.2f}"


class CloudPricingProvider(ABC):
    """
    Abstract base class for cloud-specific pricing engines.
    """

    @abstractmethod
    def estimate(
        self, resource_type: str, config: dict[str, Any], address: str = ""
    ) -> CostEstimate:
        """
        Estimate the monthly cost for a resource.

        Args:
            resource_type: Terraform resource type (e.g., "aws_instance")
            config:        The resource's `after` config dict from the plan
            address:       Full resource address for labeling

        Returns:
            CostEstimate with monthly_cost and breakdown
        """
        pass
