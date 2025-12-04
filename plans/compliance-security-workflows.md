# Compliance & Security Workflows Plan

Workflows for security scanning, access reviews, and compliance reporting.

## Workflows

### 1. access-review-quarterly.yaml
**Status:** ✅ Implemented

Quarterly IAM access review:
- Run IAM access review (inactive users)
- Check for overly permissive policies
- Generate compliance report
- Create Jira tickets for required actions
- Publish report to Confluence
- Notify security team

**Tools:** Compliance, Jira, Confluence, Slack

**Variables:**
- `inactive_days`: Days of inactivity threshold
- `jira_project`: Project for remediation tickets
- `confluence_space`: Space for reports

---

### 2. security-scan-report.yaml
**Status:** Planned

Security scanning and reporting:
- Run PCI DSS compliance scan
- Scan ECR images for vulnerabilities
- Check for exposed secrets in repos
- Aggregate findings
- Create Confluence security report
- Create Jira tickets for critical findings

**Tools:** Compliance, AWS ECR, Confluence, Jira

**Variables:**
- `ecr_repos`: Repositories to scan
- `confluence_space`: Space for report
- `jira_project`: Project for findings

---

### 3. secrets-rotation.yaml
**Status:** Planned

Rotate application secrets:
- Identify secrets due for rotation
- Generate new secrets
- Update in secrets manager
- Trigger application restarts
- Verify applications healthy
- Audit log the rotation

**Tools:** AWS, Kubernetes, Slack

**Variables:**
- `secret_names`: Secrets to rotate
- `namespace`: Kubernetes namespace

---

### 4. vulnerability-triage.yaml
**Status:** Planned

Triage security vulnerabilities:
- Get new vulnerabilities from ECR scans
- Prioritize by CVSS score
- Check if patches available
- Create Jira tickets by severity
- Assign to appropriate teams
- Post summary to security channel

**Tools:** AWS ECR, Jira, Slack

**Variables:**
- `min_severity`: Minimum CVSS to report
- `jira_project`: Project for tickets
- `slack_channel`: Security channel
