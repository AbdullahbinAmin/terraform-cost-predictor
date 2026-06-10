# Usage Guide — Terraform Cost Predictor

## Prerequisites

- Python 3.11+
- pip

## Installation

```bash
pip install terraform-cost-predictor
# OR from source:
pip install -e .
```

## Generating the Terraform Plan

```bash
# 1. Initialize your Terraform project
terraform init

# 2. Create the binary plan
terraform plan -out=tfplan

# 3. Export to JSON
terraform show -json tfplan > plan.json
```

## Commands

### `predict` — Estimate costs

```bash
cost-predict predict plan.json [OPTIONS]

Options:
  --budget, -b PATH     Budget YAML config file
  --env, -e TEXT        Environment name for budget lookup
  --output, -o TEXT     Output format: table | json | html  [default: table]
  --output-file, -f     Save output to file
  --save, -s            Save run to history
  --compare, -c         Compare with most recent saved run
  --label, -l TEXT      Label for this run (e.g., staging, production)
  --no-color            Disable colors (for CI logs)
  --breakdown           Show detailed cost breakdown per resource
  --all                 Include no-op (unchanged) resources in output
```

### `history` — Manage run history

```bash
# List recent runs
cost-predict history list
cost-predict history list --label staging --limit 10

# Delete all history
cost-predict history clear --yes
```

### `version`

```bash
cost-predict version
```

## CI/CD Integration

### Exit Codes

| Code | Meaning |
|------|---------|
| `0`  | Success — cost is within budget (or no budget configured) |
| `1`  | Budget exceeded — pipeline blocked |

### GitLab CI Example

```yaml
cost-analysis:
  image: python:3.11
  before_script:
    - pip install terraform-cost-predictor
  script:
    - terraform show -json tfplan > plan.json
    - cost-predict predict plan.json --budget budget.yaml --env $CI_ENVIRONMENT_NAME
```

### CircleCI Example

```yaml
- run:
    name: Cost Analysis
    command: |
      pip install terraform-cost-predictor
      cost-predict predict plan.json --budget budget.yaml
```

## Adding New Resource Types

1. Add pricing to `internal/pricing/pricing_db.json`
2. Add a handler method to `PricingEngine` in `internal/pricing/aws_pricing.py`
3. Add the resource type to `SUPPORTED_RESOURCE_TYPES` in `internal/parser/plan_parser.py`
4. Add tests to `tests/test_pricing.py`

## History Database

The history database is stored at:
- **Linux/macOS**: `~/.terraform-cost-predictor/history.db`
- **Windows**: `C:\Users\<user>\.terraform-cost-predictor\history.db`

It is a standard SQLite database and can be inspected with any SQLite browser.
