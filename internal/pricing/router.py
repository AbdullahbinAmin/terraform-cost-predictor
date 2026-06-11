"""
Pricing Router

Delegates pricing estimations to the appropriate cloud provider
based on the resource type.
"""

from __future__ import annotations

import logging
from typing import Any

from internal.pricing.base import CloudPricingProvider, CostEstimate
from internal.pricing.aws_pricing import AWSPricingEngine
from internal.pricing.azure_pricing import AzurePricingEngine
from internal.pricing.gcp_pricing import GCPPricingEngine

logger = logging.getLogger(__name__)


class PricingRouter(CloudPricingProvider):
    """
    Routes cost estimation requests to the appropriate cloud provider
    engine based on the resource type prefix.
    """

    def __init__(self, aws_db_path=None):
        self.aws_engine = AWSPricingEngine(db_path=aws_db_path)
        self.azure_engine = AzurePricingEngine()
        self.gcp_engine = GCPPricingEngine()

    def estimate(
        self, resource_type: str, config: dict[str, Any], address: str = ""
    ) -> CostEstimate:
        """
        Estimate the monthly cost for a resource by routing to the correct cloud provider.
        """
        if resource_type.startswith("aws_"):
            return self.aws_engine.estimate(resource_type, config, address)
        elif resource_type.startswith("azurerm_"):
            return self.azure_engine.estimate(resource_type, config, address)
        elif resource_type.startswith("google_"):
            return self.gcp_engine.estimate(resource_type, config, address)
        
        # Fallback if unknown
        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=0.0,
            confidence="unknown",
            notes=[f"Resource type '{resource_type}' not supported or provider unknown"],
        )
