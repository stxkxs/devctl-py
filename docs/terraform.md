# Terraform

Wrapper commands for Terraform with enhanced output and devctl integration.

## Overview

Terraform commands wrap the Terraform CLI with:
- Consistent output formatting
- Dry-run support
- Integration with devctl workflows
- Workspace awareness

**Prerequisite:** Terraform CLI must be installed. [Download Terraform](https://www.terraform.io/downloads)

## Core Commands

### Plan

Preview infrastructure changes.

```bash
# Basic plan
devctl terraform plan

# Plan with variables
devctl terraform plan --var environment=staging --var replicas=3

# Plan with variable file
devctl terraform plan --var-file vars/production.tfvars

# Plan specific resources
devctl terraform plan --target aws_instance.web --target aws_rds_instance.db

# Save plan to file
devctl terraform plan --out tfplan

# Destroy plan (preview destruction)
devctl terraform plan --destroy

# Refresh-only (update state without changes)
devctl terraform plan --refresh-only

# Different directory
devctl terraform plan --dir ./infrastructure/aws
```

### Apply

Apply infrastructure changes.

```bash
# Interactive apply
devctl terraform apply

# Auto-approve (for automation)
devctl terraform apply --auto-approve

# Apply with variables
devctl terraform apply --var environment=production --auto-approve

# Apply saved plan
devctl terraform apply --plan-file tfplan

# Target specific resources
devctl terraform apply --target aws_instance.web --auto-approve

# Control parallelism
devctl terraform apply --parallelism 20 --auto-approve
```

### Destroy

Destroy managed infrastructure.

```bash
# Interactive destroy
devctl terraform destroy

# Auto-approve destruction
devctl terraform destroy --auto-approve

# Destroy specific resources
devctl terraform destroy --target aws_instance.temp --auto-approve
```

### Init

Initialize Terraform working directory.

```bash
# Initialize
devctl terraform init

# Initialize different directory
devctl terraform init --dir ./modules/vpc
```

### Validate

Check configuration syntax.

```bash
# Validate configuration
devctl terraform validate
```

### Format

Format Terraform files.

```bash
# Format all files
devctl terraform fmt

# Check formatting (dry-run)
devctl --dry-run terraform fmt
```

## State Management

### List State

```bash
# List all resources
devctl terraform state list

# Filter by pattern
devctl terraform state list --filter aws_instance
```

Output:
```
State Resources (15 found)
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┓
┃ Address                                 ┃ Type              ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━┩
│ aws_instance.web                        │ aws_instance      │
│ aws_instance.api                        │ aws_instance      │
│ aws_rds_instance.main                   │ aws_rds_instance  │
│ aws_s3_bucket.assets                    │ aws_s3_bucket     │
└─────────────────────────────────────────┴───────────────────┘
```

### Show Resource

```bash
# Show resource details
devctl terraform state show aws_instance.web
```

### Move Resource

```bash
# Rename resource in state
devctl terraform state mv aws_instance.old aws_instance.new

# Move to module
devctl terraform state mv aws_instance.web module.web.aws_instance.main
```

### Remove from State

```bash
# Remove resource (doesn't destroy infrastructure)
devctl terraform state rm aws_instance.imported

# Force remove
devctl terraform state rm aws_instance.imported --force
```

### Pull State

```bash
# Display current state
devctl terraform state pull

# Save to file
devctl terraform state pull --out backup.tfstate
```

## Workspace Management

### List Workspaces

```bash
devctl terraform workspace list
```

Output:
```
Terraform Workspaces
┏━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Workspace    ┃ Current  ┃
┡━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ default      │ No       │
│ staging      │ Yes      │
│ production   │ No       │
└──────────────┴──────────┘
```

### Select Workspace

```bash
devctl terraform workspace select production
```

### Create Workspace

```bash
devctl terraform workspace new development
```

### Delete Workspace

```bash
# Delete workspace (must not be current)
devctl terraform workspace delete old-workspace

# Force delete (even with state)
devctl terraform workspace delete old-workspace --force
```

## Additional Commands

### Output

```bash
# Show all outputs
devctl terraform output

# Show specific output
devctl terraform output vpc_id

# Output as JSON
devctl terraform output --json
```

### Import

```bash
# Import existing resource
devctl terraform import aws_instance.web i-1234567890abcdef0

# Import with variables
devctl terraform import aws_s3_bucket.data my-bucket-name --var region=us-east-1
```

### Providers

```bash
# Show required providers
devctl terraform providers
```

### Graph

```bash
# Generate dependency graph
devctl terraform graph

# Save to file
devctl terraform graph --out graph.dot
```

Render with GraphViz:
```bash
dot -Tpng graph.dot -o graph.png
```

## Workflow Integration

Terraform integrates with devctl workflows:

```yaml
name: terraform-deploy
description: Plan and apply Terraform changes

vars:
  environment: staging
  auto_approve: false

steps:
  - name: Initialize
    command: "!devctl terraform init --dir ./infrastructure"

  - name: Validate
    command: "!devctl terraform validate --dir ./infrastructure"

  - name: Plan
    command: "!devctl terraform plan --dir ./infrastructure --var environment={{ environment }} --out tfplan"

  - name: Apply
    command: "!devctl terraform apply --dir ./infrastructure --plan-file tfplan {{ '--auto-approve' if auto_approve else '' }}"
    condition: "{{ auto_approve }}"

  - name: Notify
    command: slack send
    params:
      channel: "#deployments"
      message: "Terraform {{ environment }} applied successfully"
    on_failure: continue
```

## Dry Run Mode

All commands support dry-run to preview actions:

```bash
# Preview plan
devctl --dry-run terraform plan --var environment=production

# Preview apply
devctl --dry-run terraform apply --auto-approve

# Preview state changes
devctl --dry-run terraform state mv aws_instance.old aws_instance.new
```

## Best Practices

1. **Use workspaces** - Separate state for each environment
2. **Save plans** - Use `--out` to ensure exact changes are applied
3. **Target carefully** - Use `--target` only when necessary
4. **Version lock providers** - Pin provider versions in `required_providers`
5. **Use variable files** - Keep environment configs in `.tfvars` files
6. **Review plans** - Always review plan output before applying

## Common Patterns

### Environment Promotion

```bash
# Deploy to staging
devctl terraform workspace select staging
devctl terraform apply --var-file vars/staging.tfvars --auto-approve

# Test, then promote to production
devctl terraform workspace select production
devctl terraform plan --var-file vars/production.tfvars --out prod.tfplan
# Review plan...
devctl terraform apply --plan-file prod.tfplan
```

### State Migration

```bash
# Backup state
devctl terraform state pull --out backup.tfstate

# Move resources
devctl terraform state mv aws_instance.web module.compute.aws_instance.web
```

### Import Existing Infrastructure

```bash
# Write resource config first, then import
devctl terraform import aws_vpc.main vpc-12345678
devctl terraform import aws_subnet.public[0] subnet-12345678
```

## Related Documentation

- [Workflows](workflows.md) - Automate Terraform operations
- [AWS Commands](aws-commands.md) - AWS CLI operations
- [Configuration](configuration.md) - Profile setup
