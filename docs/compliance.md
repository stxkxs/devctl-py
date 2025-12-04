# Compliance Commands

devctl provides PCI DSS compliance scanning and IAM access reviews for AWS environments.

## Overview

The compliance module helps maintain security standards:
- PCI DSS v4.0 control validation
- IAM access reviews for inactive users
- Automated reporting in multiple formats
- Integration with existing security workflows

## Configuration

```yaml
profiles:
  default:
    compliance:
      pci:
        enabled_controls:
          - PCI-1.3
          - PCI-3.4
          - PCI-7.1
          - PCI-8.1
          - PCI-8.2
          - PCI-8.3
          - PCI-10.1
          - PCI-10.2
          - PCI-10.7
        excluded_resources: []
        severity_threshold: medium
      notifications:
        slack_channel: "#security"
        email: security@company.com
```

## PCI DSS Scanning

### Run a scan

```bash
# Full PCI scan
devctl compliance pci scan

# Scan specific controls
devctl compliance pci scan --controls PCI-7.1,PCI-8.1

# Scan specific regions
devctl compliance pci scan --regions us-east-1,us-west-2
```

### Check specific control

```bash
# Check a single control
devctl compliance pci check PCI-8.1

# With verbose output
devctl -v compliance pci check PCI-8.2
```

### View summary

```bash
# Summary of last scan
devctl compliance pci summary
```

### Generate report

```bash
# JSON report
devctl compliance pci report --format json --output pci-report.json

# CSV report
devctl compliance pci report --format csv --output pci-findings.csv

# HTML report (for sharing)
devctl compliance pci report --format html --output pci-report.html
```

## PCI DSS Controls Implemented

| Control ID | Requirement | What It Checks |
|------------|-------------|----------------|
| PCI-1.3 | Network Security | Security groups allowing 0.0.0.0/0 on sensitive ports |
| PCI-3.4 | Encryption at Rest | Unencrypted S3 buckets, EBS volumes, RDS instances |
| PCI-4.1 | Encryption in Transit | ALB listeners without HTTPS, CloudFront without TLS 1.2+ |
| PCI-7.1 | Least Privilege | Overly permissive IAM policies (*, admin access) |
| PCI-8.1 | Root Account | Root account usage, root access keys |
| PCI-8.2 | Key Rotation | Access keys older than 90 days |
| PCI-8.3 | MFA | Console users without MFA enabled |
| PCI-10.1 | CloudTrail | Multi-region CloudTrail enabled |
| PCI-10.2 | VPC Flow Logs | VPCs without flow logs enabled |
| PCI-10.7 | Log Retention | CloudWatch log groups without retention policies |

## Access Reviews

Review IAM users and their access patterns:

### Run access review

```bash
# Default: users inactive for 90+ days
devctl compliance access-review

# Custom inactivity threshold
devctl compliance access-review --days 60

# Include service accounts
devctl compliance access-review --include-service-accounts
```

### Export access review

```bash
# CSV export for audit
devctl compliance access-review export --format csv --output access-review.csv

# JSON for automation
devctl compliance access-review export --format json
```

Access review includes:
- User name and ARN
- Last activity date
- Days since last activity
- MFA status
- Access key age
- Attached policies
- Group memberships

## Scan Output

### Finding Severity Levels

| Severity | Description |
|----------|-------------|
| `critical` | Immediate action required (e.g., root access keys) |
| `high` | Address within 24 hours (e.g., missing MFA) |
| `medium` | Address within 7 days (e.g., old access keys) |
| `low` | Address within 30 days (e.g., missing log retention) |
| `info` | Informational findings |

### Finding Structure

```json
{
  "control_id": "PCI-8.3",
  "title": "MFA Not Enabled",
  "severity": "high",
  "resource_type": "IAM User",
  "resource_id": "arn:aws:iam::123456789012:user/admin",
  "description": "User 'admin' does not have MFA enabled",
  "remediation": "Enable MFA for this user via IAM console or CLI",
  "region": "global"
}
```

## Common Patterns

### Scheduled compliance scan

```bash
#!/bin/bash
# Run weekly PCI scan and notify

devctl compliance pci scan

# Generate report
devctl compliance pci report --format html --output /tmp/pci-$(date +%Y%m%d).html

# Get summary
SUMMARY=$(devctl -o json compliance pci summary)
CRITICAL=$(echo $SUMMARY | jq '.critical')
HIGH=$(echo $SUMMARY | jq '.high')

# Notify if issues found
if [ "$CRITICAL" -gt 0 ] || [ "$HIGH" -gt 0 ]; then
  devctl slack send "#security" "PCI Scan completed: $CRITICAL critical, $HIGH high findings"
fi
```

### Pre-deployment compliance check

```yaml
# CI/CD pipeline step
- name: Compliance Check
  run: |
    devctl compliance pci scan --controls PCI-7.1,PCI-3.4

    # Fail if critical findings
    CRITICAL=$(devctl -o json compliance pci summary | jq '.critical')
    if [ "$CRITICAL" -gt 0 ]; then
      echo "Critical compliance issues found!"
      exit 1
    fi
```

### Quarterly access review

```bash
# Generate access review for audit
devctl compliance access-review --days 90 \
  export --format csv --output Q4-access-review.csv

# Create Jira ticket for review
devctl jira issues create \
  --project SEC \
  --type Task \
  --summary "Q4 IAM Access Review" \
  --description "Please review attached access review report and remediate inactive accounts."
```

## Integration with Other Tools

### With Slack notifications

```bash
# Notify on critical findings
FINDINGS=$(devctl -o json compliance pci scan)
CRITICAL=$(echo $FINDINGS | jq '[.[] | select(.severity == "critical")] | length')

if [ "$CRITICAL" -gt 0 ]; then
  devctl slack notify --type incident \
    --title "Critical PCI Compliance Findings" \
    --severity critical \
    --channel "#security"
fi
```

### With Confluence documentation

```bash
# Generate and publish compliance report
devctl compliance pci report --format html --output /tmp/pci-report.html
devctl confluence pages update $COMPLIANCE_PAGE_ID --file /tmp/pci-report.html
```

## Dry Run Mode

```bash
# Preview what would be scanned
devctl --dry-run compliance pci scan
devctl --dry-run compliance access-review
```

## Output Formats

```bash
# Table (default)
devctl compliance pci scan

# JSON for automation
devctl -o json compliance pci scan

# YAML
devctl -o yaml compliance pci summary
```
