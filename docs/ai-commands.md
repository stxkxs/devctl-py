# AI Commands

AI-powered operations using AWS Bedrock for intelligent DevOps assistance.

## Overview

The `devctl ai` command group provides AI-powered features:
- Natural language to devctl command translation
- Cost anomaly explanation and analysis
- Infrastructure as Code security review

**Requires**: AWS Bedrock access with Claude models enabled.

## Commands

### ask

Translate natural language questions into devctl commands:

```bash
# Ask how to do something
devctl ai ask how do I list S3 buckets

# Get command suggestions
devctl ai ask "what is my AWS account ID"

# Execute suggested command directly
devctl ai ask show me cost breakdown by team --execute
```

Options:
- `--execute, -x`: Execute the suggested command after confirmation
- `--model`: Bedrock model to use (default: claude-3-haiku)

### explain-anomaly

Get AI-powered explanations for AWS cost anomalies:

```bash
# Explain most significant recent anomaly
devctl ai explain-anomaly

# Explain specific anomaly
devctl ai explain-anomaly --anomaly-id ABC123

# Check anomalies from last 30 days
devctl ai explain-anomaly --days 30
```

Options:
- `--anomaly-id, -a`: Specific anomaly ID to explain
- `--days`: Days to check for anomalies (default: 7)
- `--model`: Bedrock model to use

The AI analysis includes:
- Root cause analysis
- Impact assessment
- Recommended actions
- Prevention strategies

### review-iac

Review Infrastructure as Code for security issues and best practices:

```bash
# Review Terraform file
devctl ai review-iac ./main.tf

# Review Kubernetes manifest
devctl ai review-iac ./deployment.yaml --type kubernetes

# Review entire directory
devctl ai review-iac ./terraform/

# Output as JSON
devctl ai review-iac ./infra/ --output-json
```

Options:
- `--type`: File type (`terraform`, `kubernetes`, `auto`)
- `--model`: Bedrock model to use
- `--output-json`: Output results as JSON

The review includes:
- **Security Issues**: Vulnerabilities with severity ratings
- **Cost Optimization**: Resource right-sizing opportunities
- **Best Practices**: Maintainability improvements
- **Compliance**: SOC2, HIPAA, PCI-DSS considerations

## Configuration

Configure AI defaults in `~/.devctl/config.yaml`:

```yaml
ai:
  default_model: anthropic.claude-3-haiku-20240307-v1:0
  max_tokens: 2000
  temperature: 0.3
```

## Examples

### Natural Language Queries

```bash
# Cost queries
devctl ai ask "show me which services are costing the most"
devctl ai ask "are there any cost anomalies this week"

# Infrastructure queries
devctl ai ask "how do I scale up my EKS cluster"
devctl ai ask "list all my Kubernetes pods in production"

# Operations
devctl ai ask "run my daily cost report workflow"
```

### Anomaly Investigation

```bash
# Get explanation for sudden cost spike
devctl ai explain-anomaly --days 3

# Investigate specific anomaly from alert
devctl ai explain-anomaly --anomaly-id ANOMALY-ABC123
```

### IaC Security Review

```bash
# Review before terraform apply
devctl ai review-iac ./terraform/

# Review Kubernetes deployment
devctl ai review-iac ./k8s/deployment.yaml

# CI/CD integration
devctl ai review-iac ./infra/ --output-json > review-results.json
```

## Best Practices

1. **Use haiku for quick queries** - Faster and cheaper for simple questions
2. **Review IaC before deploying** - Catch security issues early
3. **Investigate anomalies promptly** - AI can help triage cost spikes
4. **Combine with workflows** - Use AI insights to trigger automated responses

## Related Documentation

- [Bedrock AI](bedrock-ai.md) - Direct Bedrock model access
- [AWS Cost Commands](aws-commands.md#cost) - Cost analysis commands
- [Workflows](workflows.md) - Workflow automation
