# Operations Workflows Plan

Day-2 operations, monitoring, and maintenance workflows.

## Workflows

### 1. daily-ops-report.yaml (HIGH PRIORITY)
**Status:** ✅ Implemented

Morning operations report:
- Get AWS cost summary (last 24h)
- Check for cost anomalies
- List overnight PagerDuty incidents
- Get current Grafana alert status
- List recent deployments
- Post summary to ops Slack channel

**Tools:** AWS Cost, PagerDuty, Grafana, Slack

**Variables:**
- `slack_channel`: Channel for report (default: #ops)
- `cost_threshold`: Alert if daily cost exceeds this

---

### 2. weekly-cost-review.yaml (QUICK WIN)
**Status:** ✅ Implemented

Weekly cost analysis:
- Get 7-day cost breakdown by service
- Run rightsizing recommendations
- Find unused resources
- Generate cost optimization suggestions
- Post report to Slack
- Create Jira tickets for significant savings opportunities

**Tools:** AWS Cost, Slack, Jira

**Variables:**
- `slack_channel`: Channel for report
- `savings_threshold`: Min savings to create Jira ticket ($)
- `jira_project`: Project for cost tickets

---

### 3. pod-restart-investigation.yaml
**Status:** Planned

Investigate pod crash loops:
- Get pod events and status
- Fetch recent logs (before crash)
- Check resource usage (CPU/memory)
- Get node conditions
- Check for OOMKilled
- Create summary report

**Tools:** Kubernetes, Logs, Grafana

**Variables:**
- `pod_name`: Pod name or pattern
- `namespace`: Kubernetes namespace
- `lookback`: Time to look back (default: 1h)

---

### 4. certificate-rotation.yaml
**Status:** Planned

TLS certificate rotation:
- Backup existing certificate
- Generate or fetch new certificate
- Update Kubernetes secret
- Trigger deployment rollout
- Verify HTTPS endpoint
- Notify security team

**Tools:** Kubernetes, Slack

**Variables:**
- `secret_name`: K8s secret name
- `namespace`: Namespace
- `cert_source`: Where to get new cert (vault/acm/manual)

---

### 5. database-maintenance.yaml
**Status:** Planned

Database maintenance window:
- Create Grafana maintenance annotation
- Silence database alerts
- Notify stakeholders
- Execute maintenance commands
- Re-enable alerts
- Post completion status

**Tools:** Grafana, Slack

**Variables:**
- `database`: Database identifier
- `maintenance_type`: Type of maintenance
- `duration`: Expected duration
- `slack_channel`: Notification channel

---

### 6. log-analysis.yaml
**Status:** Planned

Analyze logs for patterns:
- Search CloudWatch/Loki for error patterns
- Aggregate error counts by type
- Identify top error sources
- Generate report
- Create Jira tickets for critical issues

**Tools:** Logs, Jira, Slack

**Variables:**
- `service`: Service to analyze
- `time_range`: Analysis period
- `error_patterns`: Patterns to search for
