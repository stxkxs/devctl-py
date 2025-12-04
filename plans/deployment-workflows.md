# Deployment Workflows Plan

Workflows for deploying, monitoring, and rolling back applications.

## Workflows

### 1. deploy-with-jira.yaml (HIGH PRIORITY)
**Status:** ✅ Implemented

Full deployment with tracking:
- Validate deployment prerequisites
- Sync ArgoCD application (or kubectl apply)
- Wait for rollout completion
- Transition Jira deployment ticket to "Done"
- Create Grafana deployment annotation
- Send Slack notification with deployment details

**Tools:** ArgoCD/Kubernetes, Jira, Grafana, Slack

**Variables:**
- `app_name`: ArgoCD application name
- `version`: Version being deployed
- `jira_ticket`: Deployment ticket ID
- `environment`: Target environment
- `slack_channel`: Notification channel

---

### 2. canary-deploy-monitored.yaml
**Status:** Planned

Canary deployment with automatic rollback:
- Deploy canary version (10% traffic)
- Monitor Grafana error rates for 10 minutes
- If error rate > threshold: automatic rollback
- If healthy: promote to 50%, then 100%
- Create Jira comment with deployment status
- Notify team of outcome

**Tools:** Deploy commands, Grafana, Jira, Slack

**Variables:**
- `app_name`: Application name
- `image`: New container image
- `error_threshold`: Max error rate (default: 5%)
- `canary_duration`: Monitoring period per stage

---

### 3. rollback-notify.yaml (QUICK WIN)
**Status:** ✅ Implemented

Simple rollback with notifications:
- Execute deployment rollback
- Create incident Jira ticket
- Send Slack alert to team
- Create Grafana annotation

**Tools:** Kubernetes/ArgoCD, Jira, Slack, Grafana

**Variables:**
- `app_name`: Application to rollback
- `reason`: Rollback reason
- `jira_project`: Project for incident ticket

---

### 4. blue-green-switch.yaml
**Status:** Planned

Blue-green deployment switch:
- Verify green environment health
- Switch traffic from blue to green
- Monitor for issues (5 min)
- If issues: switch back to blue
- Update service mesh / ingress
- Notify team

**Tools:** Kubernetes, Grafana, Slack

**Variables:**
- `service_name`: Service to switch
- `namespace`: Kubernetes namespace
- `monitoring_duration`: Post-switch monitoring time

---

### 5. hotfix-pipeline.yaml
**Status:** Planned

Emergency hotfix deployment:
- Cherry-pick commit to release branch
- Trigger expedited CI build
- Deploy directly to production (skip staging)
- Create PagerDuty note
- Notify all stakeholders
- Create follow-up Jira for proper fix

**Tools:** GitHub, ArgoCD, PagerDuty, Slack, Jira

**Variables:**
- `commit_sha`: Commit to cherry-pick
- `release_branch`: Target branch
- `incident_id`: Related PagerDuty incident
