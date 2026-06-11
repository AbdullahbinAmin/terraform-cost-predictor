"""
Azure Pricing Engine

Fetches live pricing from the Azure Retail Prices API and estimates costs
for Azure resources.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from internal.pricing.base import CloudPricingProvider, CostEstimate

logger = logging.getLogger(__name__)

AZURE_RETAIL_PRICES_API = "https://prices.azure.com/api/retail/prices"


class AzurePricingEngine(CloudPricingProvider):
    """
    Azure pricing engine using the live Azure Retail Prices API.
    """

    def __init__(self):
        self._cache: dict[str, float] = {}

    def _fetch_price(self, filters: str) -> float | None:
        """Fetch price from Azure API based on OData filters."""
        if filters in self._cache:
            return self._cache[filters]

        # Use USD and standard Retail price
        query = f"currencyCode='USD'&$filter=priceType eq 'Consumption' and {filters}"
        url = f"{AZURE_RETAIL_PRICES_API}?{query}"

        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("Items", [])
            if items:
                # Get the lowest retail price (sometimes multiple meters match)
                retail_price = min(item.get("retailPrice", 0.0) for item in items)
                self._cache[filters] = retail_price
                return retail_price
        except Exception as e:
            logger.warning(f"Failed to fetch Azure pricing for '{filters}': {e}")

        return None

    def estimate(
        self, resource_type: str, config: dict[str, Any], address: str = ""
    ) -> CostEstimate:
        handler = self._get_handler(resource_type)
        if handler is None:
            return CostEstimate(
                resource_address=address,
                resource_type=resource_type,
                monthly_cost=0.0,
                confidence="unknown",
                notes=["Azure resource type not supported — cost not estimated"],
            )
        return handler(resource_type, config, address)

    def _get_handler(self, resource_type: str):
        handlers = {
            "azurerm_linux_virtual_machine": self._estimate_vm,
            "azurerm_windows_virtual_machine": self._estimate_vm,
            "azurerm_managed_disk": self._estimate_managed_disk,
            "azurerm_storage_account": self._estimate_storage_account,
        }
        return handlers.get(resource_type)

    def _estimate_vm(self, resource_type: str, config: dict, address: str) -> CostEstimate:
        size = config.get("size", "Standard_B1s")
        location = config.get("location", "eastus")

        # Example filter: armRegionName eq 'eastus' and armSkuName eq 'Standard_B1s' and productName eq 'Virtual Machines'
        # Azure's API is notoriously finicky. Let's try a broad filter.
        f = f"armRegionName eq '{location}' and armSkuName eq '{size}' and serviceName eq 'Virtual Machines'"

        hourly_price = self._fetch_price(f)
        confidence = "high"

        if hourly_price is None:
            # Fallback
            hourly_price = 0.05  # $36/mo default
            confidence = "low"
            notes = [f"Size: {size}", "Live price fetch failed, using fallback estimate"]
        else:
            notes = [f"Size: {size}", "Live price from Azure Retail API"]

        monthly = hourly_price * 730.0

        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(monthly, 2),
            confidence=confidence,
            notes=notes,
        )

    def _estimate_managed_disk(
        self, resource_type: str, config: dict, address: str
    ) -> CostEstimate:
        storage_type = config.get("storage_account_type", "Standard_LRS")
        size_gb = config.get("disk_size_gb") or 30

        # Estimate roughly $0.05 per GB for standard, $0.15 for Premium
        is_premium = "Premium" in storage_type
        price_per_gb = 0.15 if is_premium else 0.05
        monthly = float(size_gb) * price_per_gb

        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(monthly, 2),
            confidence="medium",
            notes=[f"Type: {storage_type}", f"Size: {size_gb} GB"],
        )

    def _estimate_storage_account(
        self, resource_type: str, config: dict, address: str
    ) -> CostEstimate:
        tier = config.get("account_tier", "Standard")
        repl = config.get("account_replication_type", "LRS")

        monthly = 2.00  # Base estimate for a few GBs

        return CostEstimate(
            resource_address=address,
            resource_type=resource_type,
            monthly_cost=round(monthly, 2),
            confidence="low",
            notes=[f"Tier: {tier}", f"Replication: {repl}", "Estimated base cost (data dependent)"],
        )
