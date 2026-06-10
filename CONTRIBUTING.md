# Contributing to Terraform Cost Predictor

Thank you for considering contributing! This document outlines how to get started.

## Ways to Contribute

- 🐛 **Report bugs** — Open an issue with a reproducible example
- 💡 **Request features** — Open an issue describing the use case
- 📖 **Improve docs** — Fix typos, add examples, improve clarity
- 💰 **Add AWS resource types** — The most impactful contribution
- 🌐 **Add Azure/GCP support** — See the multi-cloud roadmap

## Development Setup

```bash
git clone https://github.com/abdullahbinaminmeo/terraform-cost-predictor
cd terraform-cost-predictor
pip install -e ".[dev]"
```

## Adding a New AWS Resource Type

This is the #1 most needed contribution. Here's the pattern:

### 1. Add pricing to `internal/pricing/pricing_db.json`

```json
"aws_your_resource": {
  "_doc": "Description of the resource",
  "_unit": "per_month",
  "estimated_monthly": 10.00,
  "note": "Estimate based on typical usage"
}
```

### 2. Add a handler in `internal/pricing/aws_pricing.py`

```python
def _estimate_your_resource(self, resource_type: str, config: dict, address: str) -> CostEstimate:
    db = self._db.get("aws_your_resource", {})
    monthly = db.get("estimated_monthly", 10.0)
    return CostEstimate(
        resource_address=address,
        resource_type=resource_type,
        monthly_cost=round(monthly, 2),
        confidence="medium",
        notes=["Your pricing note here"],
    )
```

### 3. Register it in `_get_handler()`

```python
"aws_your_resource": self._estimate_your_resource,
```

### 4. Add to `SUPPORTED_RESOURCE_TYPES` in `internal/parser/plan_parser.py`

```python
"aws_your_resource",
```

### 5. Write tests in `tests/test_pricing.py`

```python
def test_your_resource(self):
    result = self.engine.estimate("aws_your_resource", {}, "aws_your_resource.test")
    assert result.monthly_cost > 0
```

## Running Tests

```bash
pytest tests/ -v
pytest tests/ -v --cov=. --cov-report=term-missing
```

All tests must pass before a PR is merged.

## Pull Request Guidelines

1. **Fork** the repository and create a feature branch: `git checkout -b feat/add-aws-rds-proxy`
2. **Write tests** — all new code should have tests
3. **Update docs** — update `README.md` and `docs/usage.md` if needed
4. **Update CHANGELOG.md** under the `[Unreleased]` section
5. **Open a PR** with a clear description of what and why

## Code Style

- Python 3.11+ syntax
- Type hints on all public functions
- Docstrings on all public classes and methods
- Run `ruff check .` before committing

## Pricing Data Sources

When adding pricing, use these official sources:
- **AWS**: https://aws.amazon.com/pricing/
- **AWS Pricing API**: `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/index.json`

Use **us-east-1** On-Demand Linux pricing as the default baseline.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
