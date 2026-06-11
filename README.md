# 🔮 Terraform Cost Predictor

[![CI](https://github.com/AbdullahbinAmin/terraform-cost-predictor/actions/workflows/ci.yml/badge.svg)](https://github.com/AbdullahbinAmin/terraform-cost-predictor/actions)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **Predict your cloud bill before you deploy.**

Terraform Cost Predictor is an open-source CLI that analyzes Terraform plans, estimates cloud costs (AWS, Azure, GCP) before deployment, compares infrastructure changes with previous runs, and enforces budget policies in CI/CD pipelines.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 💰 **Cost Estimation** | Estimate monthly AWS costs from `terraform show -json` output |
| 📈 **Cost Diff** | Compare current plan vs previous run — see exactly *why* costs changed |
| 🛡️ **Budget Enforcement** | Block CI/CD pipelines that exceed budget via `exit 1` |
| 🤖 **GitHub PR Comments** | Auto-comment cost analysis on pull requests |
| 📊 **Multiple Outputs** | Table, JSON, and HTML report formats |
| 🗄️ **History** | SQLite-backed history for cross-run comparisons |
| 🔌 **Offline-first & Live** | Bundled static pricing DB for offline speed, plus live API fetching (`boto3`) |

**Supported Cloud Resources:**
- **AWS (20+):** EC2, RDS, Aurora, ALB/NLB, NAT Gateway, EBS, S3, ElastiCache, Lambda, EKS, ECS/Fargate, CloudFront, OpenSearch, Kinesis, SQS, SNS, API Gateway, WAFv2, Route53
- **Azure:** Virtual Machines, Managed Disks, Storage Accounts, SQL Databases, App Services, Kubernetes
- **GCP:** Compute Engine, Persistent Disks, Cloud SQL, Cloud Storage, Cloud Run, GKE

---

## 🚀 Quick Start

### Install

```bash
pip install terraform-cost-predictor
```

Or install from source:

```bash
git clone https://github.com/AbdullahbinAmin/terraform-cost-predictor
cd terraform-cost-predictor
pip install -e .
```

### Generate a Terraform Plan

```bash
terraform plan -out=tfplan
terraform show -json tfplan > plan.json
```

### Predict Costs

```bash
cost-predict predict plan.json
```

**Output:**

```
╭──────────────────────────────────────────────────────╮
│ 🔮 Terraform Cost Predictor                          │
│   Analyzing plan: plan.json                          │
╰──────────────────────────────────────────────────────╯

           💰 Estimated Monthly Costs
┌────────┬────────────────────────────────┬──────────────────────┬────────────┬───────────────┐
│ Action │ Resource                       │ Type                 │ Confidence │  Monthly Cost │
├────────┼────────────────────────────────┼──────────────────────┼────────────┼───────────────┤
│ ✚ create│ aws_instance.web_server       │ aws_instance         │   [high]   │       $32.79 │
│ ✚ create│ aws_db_instance.main_postgres │ aws_db_instance      │   [high]   │       $14.71 │
│ ✚ create│ aws_lb.application_lb         │ aws_lb               │  [medium]  │       $18.00 │
│ ✚ create│ aws_nat_gateway.main          │ aws_nat_gateway      │  [medium]  │       $32.85 │
│ ✚ create│ aws_elasticache_cluster.cache │ aws_elasticache_clus │   [high]   │       $48.91 │
│ ✚ create│ aws_lambda_function.handler   │ aws_lambda_function  │   [low]    │        $5.00 │
└────────┴────────────────────────────────┴──────────────────────┴────────────┴───────────────┘

 📊 Summary                  │  💵 Total
 Total Resources:    13      │  Estimated Monthly Cost
 Priced Resources:   11      │
 Unsupported:        2       │  $152.26 USD / month
                             │  ≈ $1,827.12 / year
```

---

## 📖 Usage

### Basic Cost Estimation

```bash
cost-predict predict plan.json
```

### Live API Pricing (AWS, Azure, GCP)
Fetch real-time costs directly from cloud pricing APIs for maximum accuracy:
```bash
cost-predict predict plan.json --refresh-pricing
```

### Save Run to History

```bash
cost-predict predict plan.json --save --label staging
```

### Compare with Previous Run

```bash
cost-predict predict plan.json --save --compare --label staging
```

**Output (The Killer Feature™):**

```
📌 Cost changed because:
  ✚ aws_nat_gateway.main         +$32.85/mo    ← New NAT Gateway added
  ~ aws_instance.web             +$14.50/mo    ← Instance type: t3.small → t3.medium
  ✚ aws_db_instance.replica      +$12.41/mo    ← New RDS replica added
  ✖ aws_lb.old_lb                -$18.00/mo    ← Load balancer removed
```

### Budget Enforcement (CI/CD)

```bash
cost-predict predict plan.json --budget configs/budget.yaml
```

If cost exceeds the limit:

```
╭────────────────────────────────────────────────────────────╮
│ Budget Policy: global                                       │
│                                                             │
│ ✖  BUDGET EXCEEDED — PIPELINE BLOCKED                      │
│                                                             │
│ Estimated cost:  $285.00                                    │
│ Budget limit:    $200.00                                    │
│ Overage:         +$85.00 (+42.5%)                          │
╰────────────────────────────────────────────────────────────╯
```

Exit code `1` is returned — blocking your CI/CD pipeline.

### JSON Output

```bash
cost-predict predict plan.json --output json
cost-predict predict plan.json --output json --output-file report.json
```

### Infracost-Compatible Output

Export metrics natively supported by CI/CD tools that use the Infracost v0.2 schema:

```bash
cost-predict predict plan.json --output infracost-json --output-file infracost-report.json
```

### HTML Report

```bash
cost-predict predict plan.json --output html --output-file report.html
```

### View History

```bash
cost-predict history list
cost-predict history list --label production
cost-predict history clear
```

---

## 🛡️ Budget Configuration

Create `budget.yaml`:

```yaml
budget:
  monthly_limit: 300       # Global limit in USD
  currency: USD
  alert_threshold: 0.8     # Warn at 80% of limit

  environments:
    production:
      monthly_limit: 500
    staging:
      monthly_limit: 100
    development:
      monthly_limit: 50
```

Use it:

```bash
cost-predict predict plan.json --budget budget.yaml --env production
```

---

## 🤖 GitHub Actions Integration

Add `.github/workflows/terraform-cost.yml` to your repository (see the bundled workflow file) to automatically:

1. Run cost analysis on every PR touching `.tf` files
2. Post a cost breakdown as a PR comment
3. Block merge if the budget is exceeded

### Example PR Comment

```markdown
## 🔮 Terraform Cost Analysis

**Estimated Monthly Cost: $185.00 USD**

| Action | Resource | Type | Monthly Cost |
|--------|----------|------|-------------|
| ✚ create | `aws_instance.web` | `aws_instance` | $30.37 |
| ✚ create | `aws_nat_gateway.main` | `aws_nat_gateway` | $32.85 |

### 📈 Cost Change vs Previous Run
- Previous: **$120.00**
- Current: **$185.00**
- Delta: **+$65.00** (+54.2%)

**Top Cost Drivers:**
- `aws_nat_gateway.main`: +$32.85/mo (Added)
- `aws_instance.web`: +$18.30/mo (t3.micro → t3.medium)
```

---

## 📁 Project Structure

```
terraform-cost-predictor/
├── cmd/
│   └── main.py                    # Typer CLI entry point
├── internal/
│   ├── parser/plan_parser.py      # Terraform plan JSON parser
│   ├── pricing/
│   │   ├── aws_pricing.py         # Pricing engine (20+ resource types)
│   │   └── pricing_db.json        # Bundled static pricing database
│   ├── budget/budget_checker.py   # YAML budget policy enforcement
│   ├── report/reporter.py         # Rich terminal + JSON/HTML output
│   └── compare/comparator.py      # Cost diff analysis engine
├── storage/history.py             # SQLite history store
├── examples/
│   ├── sample_plan.json           # Example Terraform plan JSON
│   └── budget.yaml                # Example budget config
├── configs/budget.yaml            # Default budget policy
├── tests/                         # Pytest test suite (60+ tests)
├── .github/workflows/
│   ├── ci.yml                     # CI with matrix testing
│   └── terraform-cost.yml         # PR cost analysis workflow
├── pyproject.toml                 # Package config
└── README.md
```

---

## 🔬 Development

### Setup

```bash
git clone https://github.com/AbdullahbinAmin/terraform-cost-predictor
cd terraform-cost-predictor
pip install -e ".[dev]"
```

### Run Tests

```bash
pytest tests/ -v
pytest tests/ -v --cov=. --cov-report=term-missing
```

### Run Against Sample Plan

```bash
cost-predict predict examples/sample_plan.json
cost-predict predict examples/sample_plan.json --budget examples/budget.yaml
cost-predict predict examples/sample_plan.json --output json
```

---

## 🗺️ Roadmap

- [x] **Phase 1**: Terraform plan parsing + AWS cost estimation
- [x] **Phase 2**: Cost diff analysis with human-readable explanations
- [x] **Phase 3**: Budget YAML enforcement with CI/CD exit codes
- [x] **Phase 4**: GitHub Actions + PR comments
- [x] **Phase 5**: Azure pricing support
- [x] **Phase 6**: GCP pricing support
- [x] **Phase 7**: AWS Pricing API integration (live price refresh)
- [x] **Phase 8**: Infracost-compatible output format

---

## 📄 License

MIT — see [LICENSE](LICENSE)

---

## 🙏 Contributing

Contributions welcome! Please open an issue or submit a PR.
Adding new AWS resource types is especially appreciated — see `internal/pricing/` for the pattern.
