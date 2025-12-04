# GitOps & CI/CD Workflows Plan

Workflows for source control, releases, and continuous deployment.

## Workflows

### 1. pr-to-deploy.yaml (HIGH PRIORITY)
**Status:** ✅ Implemented

Full PR-to-production pipeline:
- Merge approved PR
- Wait for CI build to complete
- Sync ArgoCD application
- Wait for rollout
- Verify health checks pass
- Create Grafana annotation
- Post deployment notification to Slack

**Tools:** GitHub, ArgoCD, Grafana, Slack

**Variables:**
- `pr_number`: Pull request number
- `repo`: Repository (owner/name)
- `argocd_app`: ArgoCD application name
- `slack_channel`: Notification channel

---

### 2. release-train.yaml
**Status:** Planned

Cut a new release:
- Create release branch from main
- Update version in package files
- Generate changelog from merged PRs
- Create Jira version
- Tag release in git
- Create GitHub release with notes
- Notify team

**Tools:** GitHub, Jira, Slack

**Variables:**
- `version`: New version number
- `repo`: Repository
- `jira_project`: Jira project for version

---

### 3. feature-branch-cleanup.yaml
**Status:** Planned

Clean up stale branches:
- List branches older than N days
- Check if PRs are merged
- Delete merged branches
- Report unmerged stale branches
- Create Slack reminder for owners

**Tools:** GitHub, Slack

**Variables:**
- `repo`: Repository
- `days_stale`: Days before considered stale
- `protected_branches`: Branches to never delete

---

### 4. sync-environments.yaml
**Status:** Planned

Sync staging to match production:
- Get production ArgoCD app status
- Update staging app to same revision
- Sync staging
- Run smoke tests
- Report differences

**Tools:** ArgoCD, Slack

**Variables:**
- `prod_app`: Production ArgoCD app
- `staging_app`: Staging ArgoCD app

---

### 5. dependency-update.yaml
**Status:** Planned

Automated dependency updates:
- Check for outdated dependencies
- Create PR with updates
- Link to security advisories if applicable
- Assign to on-call developer
- Create Jira ticket for tracking

**Tools:** GitHub, Jira

**Variables:**
- `repo`: Repository
- `package_manager`: npm/pip/go
- `jira_project`: Project for tickets
