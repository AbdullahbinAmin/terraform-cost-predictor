# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-01-10

### Added
- **Core plan parser** — Parse `terraform show -json` output with full support for create, delete, update, replace, and no-op actions
- **AWS Pricing Engine** — Static pricing database covering 20+ resource types:
  - EC2 (50+ instance types: t2, t3, t3a, m5, m6i, c5, c6i, r5, r6i, g4dn, p3)
  - RDS (Single-AZ and Multi-AZ, gp2/gp3/io1 storage pricing)
  - Aurora (MySQL and PostgreSQL)
  - Application/Network/Gateway Load Balancers
  - NAT Gateway (hourly + data processing)
  - EBS volumes (gp2, gp3, io1, io2, st1, sc1, standard)
  - S3 buckets
  - ElastiCache (Redis/Memcached, all cache.t3/m6g/r6g node types)
  - Lambda functions
  - EKS clusters
  - ECS/Fargate services
  - CloudFront distributions
  - OpenSearch/Elasticsearch domains
  - Kinesis Data Streams
  - SQS queues (Standard and FIFO)
  - SNS topics
  - API Gateway (REST and HTTP)
  - WAFv2 Web ACLs
  - Route53 hosted zones
- **Cost comparison engine** — Compare costs between runs with human-readable explanations of WHY costs changed ("killer feature")
- **Budget enforcement** — YAML-based budget policies with global and per-environment limits; `exit 1` for CI/CD pipeline blocking
- **Rich terminal output** — Colored tables with confidence levels, cost breakdown, and summary panels
- **JSON and HTML export** — Structured machine-readable output and standalone HTML reports
- **SQLite history store** — Persistent run history at `~/.terraform-cost-predictor/history.db`
- **GitHub Actions workflows** — PR cost analysis with auto-comments, artifact upload, and pipeline blocking
- **68 unit tests** — Comprehensive test coverage across all modules

### Technical
- Python 3.11+ support
- Offline-first design (bundled static pricing DB)
- Windows, macOS, Linux compatible
- `pip install`-able with `pyproject.toml`
