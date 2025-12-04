# ArgoCD Commands

devctl integrates with ArgoCD for GitOps application management.

## Prerequisites

- ArgoCD server access
- ArgoCD API token or credentials

## Configuration

```yaml
profiles:
  default:
    argocd:
      url: https://argocd.company.com
      token: from_env          # Use DEVCTL_ARGOCD_TOKEN
      insecure: false          # Skip TLS verification
      timeout: 30
```

Environment variables:
```bash
export DEVCTL_ARGOCD_URL=https://argocd.company.com
export DEVCTL_ARGOCD_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

## Application Operations

### List applications

```bash
# List all applications
devctl argocd apps list

# Filter by project
devctl argocd apps list --project default

# Filter by label selector
devctl argocd apps list --selector team=platform
```

### Get application status

```bash
# View application status
devctl argocd apps status my-app

# Detailed output
devctl -o yaml argocd apps status my-app
```

Output includes:
- Sync status (Synced, OutOfSync, Unknown)
- Health status (Healthy, Degraded, Progressing, Suspended, Missing)
- Current revision
- Last sync time
- Resource summary

### Sync application

```bash
# Sync to latest Git revision
devctl argocd apps sync my-app

# Sync to specific revision
devctl argocd apps sync my-app --revision v1.2.3

# Sync with pruning (remove resources not in Git)
devctl argocd apps sync my-app --prune

# Force sync (replace resources)
devctl argocd apps sync my-app --force

# Dry run (preview changes)
devctl argocd apps sync my-app --dry-run
```

### View diff

```bash
# Show pending changes
devctl argocd apps diff my-app

# Compare with specific revision
devctl argocd apps diff my-app --revision main
```

### View history

```bash
# View deployment history
devctl argocd apps history my-app

# Limit results
devctl argocd apps history my-app --limit 10
```

### Rollback application

```bash
# Rollback to previous revision
devctl argocd apps rollback my-app

# Rollback to specific revision ID
devctl argocd apps rollback my-app --revision-id 5
```

### Refresh application

```bash
# Refresh application manifest
devctl argocd apps refresh my-app

# Hard refresh (invalidate cache)
devctl argocd apps refresh my-app --hard
```

## Common Patterns

### Deploy a new version

```bash
# 1. Check current status
devctl argocd apps status my-app

# 2. Preview changes
devctl argocd apps diff my-app

# 3. Sync to deploy
devctl argocd apps sync my-app

# 4. Monitor status
devctl argocd apps status my-app
```

### Rollback a bad deployment

```bash
# 1. Check history to find good revision
devctl argocd apps history my-app

# 2. Rollback to that revision
devctl argocd apps rollback my-app --revision-id 3

# 3. Verify status
devctl argocd apps status my-app
```

### Sync multiple apps

```bash
# Use a script with JSON output
for app in $(devctl -o json argocd apps list --selector team=platform | jq -r '.[].name'); do
  devctl argocd apps sync "$app"
done
```

### Check OutOfSync apps

```bash
# List all apps and filter by sync status
devctl -o json argocd apps list | jq '.[] | select(.sync_status != "Synced")'
```

## Integration with Deployment Command

For more complex deployment strategies, combine ArgoCD with the deployment command:

```bash
# Create a canary deployment
devctl deploy create --name my-app --image myrepo/app:v2.0.0 --strategy canary

# ArgoCD will sync the changes automatically if auto-sync is enabled
# Or manually trigger sync
devctl argocd apps sync my-app

# Check deployment progress
devctl deploy status DEPLOYMENT_ID

# Promote when ready
devctl deploy promote DEPLOYMENT_ID
```

## Output Formats

```bash
# Table format (default)
devctl argocd apps list

# JSON for scripting
devctl -o json argocd apps list

# YAML for detailed view
devctl -o yaml argocd apps status my-app
```
