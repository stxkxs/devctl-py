# On-Call Workflows Plan

Workflows for on-call engineers and shift management.

## Workflows

### 1. oncall-handoff.yaml (QUICK WIN)
**Status:** ✅ Implemented

End-of-shift handoff:
- Get current on-call engineer
- List incidents during shift
- List open/unresolved issues
- Get pending Jira tickets assigned to on-call
- Generate handoff summary
- Post to ops Slack channel
- Tag incoming on-call engineer

**Tools:** PagerDuty, Jira, Slack

**Variables:**
- `shift_hours`: Hours to look back (default: 12)
- `slack_channel`: Handoff channel
- `jira_project`: Project to check for tickets

---

### 2. escalation-path.yaml
**Status:** Planned

Alert escalation when not acknowledged:
- Check if incident was acked within SLA
- If not: escalate to backup on-call
- If still not acked: page engineering manager
- Post escalation to incident channel
- Update PagerDuty incident

**Tools:** PagerDuty, Slack

**Variables:**
- `incident_id`: PagerDuty incident
- `ack_sla_minutes`: Minutes before escalation
- `escalation_policy`: PagerDuty policy to use

---

### 3. oncall-start-shift.yaml
**Status:** Planned

Start of shift checklist:
- Get handoff notes from previous shift
- Check current system health
- List active Grafana alerts
- List open PagerDuty incidents
- Check deployment schedule
- Post "on-call started" to Slack

**Tools:** PagerDuty, Grafana, Slack

**Variables:**
- `slack_channel`: Announcement channel

---

### 4. pager-fatigue-report.yaml
**Status:** Planned

Analyze on-call burden:
- Get incidents per on-call engineer (30 days)
- Calculate pages per shift
- Identify noisiest alerts
- Find repeat incidents
- Generate report for team lead
- Create Jira tickets for top noise sources

**Tools:** PagerDuty, Jira, Slack

**Variables:**
- `days`: Analysis period
- `jira_project`: Project for improvement tickets
