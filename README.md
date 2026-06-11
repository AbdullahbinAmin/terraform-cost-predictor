<div align="center">
  <h1>🔮 Terraform Cost Predictor</h1>
  <p><strong>Predict your cloud bill before you deploy.</strong></p>

  <p>
    <a href="https://github.com/AbdullahbinAmin/terraform-cost-predictor/actions"><img src="https://github.com/AbdullahbinAmin/terraform-cost-predictor/actions/workflows/ci.yml/badge.svg" alt="CI Status"></a>
    <a href="https://python.org"><img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python Version"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License: MIT"></a>
  </p>
</div>

Terraform Cost Predictor is a lightning-fast, open-source CLI tool that parses Terraform plans to estimate cloud costs across **AWS, Azure, and GCP**. It empowers DevOps and FinOps teams to catch expensive infrastructure changes *before* they are provisioned, enforce budget policies directly in CI/CD pipelines, and export standard Infracost-compatible metrics.

---

## ✨ Features

- 💰 **Multi-Cloud Cost Estimation:** Automatically analyzes `terraform show -json` output for AWS, Azure, and Google Cloud Platform resources.
- ⚡ **Live & Offline Pricing:** Uses a bundled, lightning-fast offline database by default, with an option to fetch 100% accurate live prices directly from cloud APIs (`--refresh-pricing`).
- 📈 **Diff Analysis:** Compares the current plan against previous runs to highlight exactly *why* your costs changed (e.g., "t3.small → t3.medium").
- 🛡️ **Budget Guardrails:** Block CI/CD pipelines via `exit 1` if the estimated cost exceeds your defined YAML budget policies.
- 🤖 **CI/CD Ready:** Auto-comment cost breakdowns on GitHub PRs and export data natively to Infracost v0.2 JSON format for seamless ecosystem integration.

---

## 🚀 Installation

Install globally via `pip`:

```bash
pip install terraform-cost-predictor
```

*Requires Python 3.11+*

---

## 📖 Usage

### 1. Generate a Terraform Plan
Export your plan to JSON format:
```bash
terraform plan -out=tfplan
terraform show -json tfplan > plan.json
```

### 2. Predict Costs
Run the predictor against your plan file:
```bash
cost-predict predict plan.json
```

**Need 100% accurate, real-time prices?** Use the live API fetcher:
```bash
cost-predict predict plan.json --refresh-pricing
```

### 3. Track Changes over Time
Save your run to local history to compare future plans:
```bash
# Save the current state
cost-predict predict plan.json --save --label production

# Next time, compare against the saved state
cost-predict predict new_plan.json --compare --label production
```

### 4. Export for CI/CD
Export the analysis to an Infracost-compatible JSON file for ingestion by other DevOps tools:
```bash
cost-predict predict plan.json --output infracost-json --output-file costs.json
```

---

## 🛡️ Budget Enforcement

Ensure developers never accidentally blow the cloud budget. Create a `budget.yaml`:

```yaml
budget:
  monthly_limit: 500       # Global limit in USD
  currency: USD
  alert_threshold: 0.8     # Warn at 80% of limit

  environments:
    production:
      monthly_limit: 1000
    staging:
      monthly_limit: 200
```

Run the predictor with your budget policy. If the cost exceeds the threshold, the tool exits with code `1`, blocking the pipeline:
```bash
cost-predict predict plan.json --budget budget.yaml --env staging
```

---

## 🤖 GitHub Actions Integration

Automate cost prediction on every pull request. Add this workflow to `.github/workflows/cost-analysis.yml`:

```yaml
name: Cost Analysis
on: [pull_request]

jobs:
  cost-predict:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3

      - name: Generate Plan
        run: |
          terraform init
          terraform plan -out=tfplan
          terraform show -json tfplan > plan.json

      - name: Install Cost Predictor
        run: pip install terraform-cost-predictor

      - name: Run Cost Analysis
        run: cost-predict predict plan.json --budget configs/budget.yaml
```

---

## 🤝 Contributing

We welcome issues and pull requests! Whether you're adding support for new Terraform resources, improving the pricing logic, or expanding the CLI, your contributions are appreciated. 

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
