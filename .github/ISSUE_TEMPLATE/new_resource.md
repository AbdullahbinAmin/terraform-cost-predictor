---
name: New AWS Resource Type
about: Request or contribute pricing for a new AWS resource type
title: '[RESOURCE] Add support for aws_XXX'
labels: enhancement, pricing
assignees: ''
---

## Resource Type
<!-- e.g., aws_mq_broker, aws_memorydb_cluster, aws_fsx_lustre_file_system -->
`aws_`

## AWS Service Documentation
<!-- Link to AWS pricing page -->
https://aws.amazon.com/

## Pricing Details
<!-- Please fill in as much as you can -->

| Property | Value |
|----------|-------|
| Pricing model | per-hour / per-GB / per-request |
| Base price (us-east-1) | $X.XX/hour |
| Key configuration attributes | instance_type, size, ... |

## Terraform Resource Attributes
<!-- Which terraform attributes affect pricing? -->
```hcl
resource "aws_XXX" "example" {
  # Pricing-relevant attributes:
  instance_type = "..."
  storage_size  = 100
}
```

## Additional Context
<!-- Any other context about this resource -->
