# Deployment Commands

devctl provides deployment orchestration with support for multiple strategies: Rolling, Blue/Green, and Canary.

## Overview

The deployment system provides:
- Strategy-based deployments (rolling, blue-green, canary)
- State tracking and persistence
- Promotion and rollback capabilities
- Integration with Kubernetes

## Configuration

```yaml
profiles:
  default:
    deploy:
      cluster: my-eks-cluster
      namespace: default
      canary:
        initial_weight: 10
        step_weight: 10
        max_weight: 50
        step_interval: 300  # seconds
        analysis_interval: 60
      blue_green:
        preview_replicas: 1
        verification_timeout: 600
      rolling:
        max_surge: 25%
        max_unavailable: 25%
```

## Deployment Strategies

### Rolling Deployment

Gradually replaces old pods with new ones.

```bash
devctl deploy create \
  --name my-app \
  --image myrepo/app:v2.0.0 \
  --strategy rolling
```

### Blue/Green Deployment

Maintains two identical environments, switching traffic instantly.

```bash
devctl deploy create \
  --name my-app \
  --image myrepo/app:v2.0.0 \
  --strategy blue-green
```

Flow:
1. Deploy new version (green) alongside current (blue)
2. Test green environment
3. Promote to switch traffic
4. Or rollback to stay on blue

### Canary Deployment

Gradually shifts traffic to new version.

```bash
devctl deploy create \
  --name my-app \
  --image myrepo/app:v2.0.0 \
  --strategy canary
```

Flow:
1. Deploy new version with small traffic percentage
2. Monitor metrics
3. Gradually increase traffic
4. Promote to 100% or rollback

## Commands

### Create deployment

```bash
# Basic rolling deployment
devctl deploy create --name my-app --image myrepo/app:v2.0.0

# Canary deployment
devctl deploy create \
  --name my-app \
  --image myrepo/app:v2.0.0 \
  --strategy canary \
  --namespace production

# Blue/green with custom replicas
devctl deploy create \
  --name my-app \
  --image myrepo/app:v2.0.0 \
  --strategy blue-green \
  --replicas 5

# Skip confirmation
devctl deploy create --name my-app --image myrepo/app:v2.0.0 -y

# Dry run
devctl deploy create --name my-app --image myrepo/app:v2.0.0 --dry-run
```

### Check deployment status

```bash
# Get status
devctl deploy status DEPLOYMENT_ID

# JSON output for scripting
devctl -o json deploy status DEPLOYMENT_ID
```

Status output includes:
- Deployment ID and name
- Strategy type
- Current status (pending, in_progress, succeeded, failed)
- Current phase
- Progress percentage
- Canary weight (for canary deployments)
- Active color (for blue/green)
- Recent events

### Promote deployment

For canary and blue/green deployments:

```bash
# Promote to full traffic
devctl deploy promote DEPLOYMENT_ID

# Skip confirmation
devctl deploy promote DEPLOYMENT_ID -y
```

### Rollback deployment

```bash
# Rollback to previous version
devctl deploy rollback DEPLOYMENT_ID

# Skip confirmation
devctl deploy rollback DEPLOYMENT_ID -y
```

### Abort deployment

Stop an in-progress deployment:

```bash
devctl deploy abort DEPLOYMENT_ID
```

### List deployments

```bash
# List recent deployments
devctl deploy list

# Filter by namespace
devctl deploy list -n production

# Show only active deployments
devctl deploy list --active

# Limit results
devctl deploy list --limit 10
```

## Deployment Phases

### Rolling Deployment Phases

1. `initializing` - Setting up deployment
2. `updating` - Updating pods
3. `verifying` - Checking rollout status
4. `completed` - All pods updated

### Blue/Green Deployment Phases

1. `initializing` - Setting up green environment
2. `deploying_green` - Deploying new version
3. `testing_green` - Green is ready for testing
4. `switching` - Switching traffic (on promote)
5. `completed` - Traffic switched to green

### Canary Deployment Phases

1. `initializing` - Setting up canary
2. `deploying_canary` - Deploying canary pods
3. `analyzing` - Monitoring canary metrics
4. `shifting_traffic` - Increasing canary weight
5. `promoting` - Moving to 100%
6. `completed` - Full rollout complete

## Common Patterns

### Standard canary workflow

```bash
# 1. Create canary deployment
devctl deploy create \
  --name my-app \
  --image myrepo/app:v2.0.0 \
  --strategy canary

# 2. Monitor status (canary starts at 10%)
devctl deploy status DEPLOYMENT_ID

# 3. Check metrics/logs
devctl logs search "error" --since 10m
devctl grafana dashboards get my-app-metrics

# 4. If healthy, promote
devctl deploy promote DEPLOYMENT_ID

# Or if issues, rollback
devctl deploy rollback DEPLOYMENT_ID
```

### Blue/green with verification

```bash
# 1. Create deployment
devctl deploy create \
  --name my-app \
  --image myrepo/app:v2.0.0 \
  --strategy blue-green

# 2. Status shows green is ready for testing
devctl deploy status DEPLOYMENT_ID

# 3. Test green environment (via preview URL/port)
curl https://green.my-app.company.com/health

# 4. Promote to switch traffic
devctl deploy promote DEPLOYMENT_ID
```

### Automated deployment with notifications

```bash
#!/bin/bash
set -e

# Create deployment
DEPLOY_ID=$(devctl -o json deploy create \
  --name my-app \
  --image myrepo/app:v2.0.0 \
  --strategy canary -y | jq -r '.id')

# Notify start
devctl slack notify --type deployment \
  --service my-app \
  --version v2.0.0 \
  --status started

# Wait and check status
sleep 300
STATUS=$(devctl -o json deploy status $DEPLOY_ID | jq -r '.status')

if [ "$STATUS" = "failed" ]; then
  devctl slack notify --type deployment --service my-app --status failed
  devctl deploy rollback $DEPLOY_ID -y
  exit 1
fi

# Promote
devctl deploy promote $DEPLOY_ID -y

# Notify success
devctl slack notify --type deployment \
  --service my-app \
  --version v2.0.0 \
  --status succeeded
```

## Integration with ArgoCD

If using ArgoCD for GitOps:

```bash
# 1. Update Git repository with new image
# 2. ArgoCD syncs automatically (or trigger sync)
devctl argocd apps sync my-app

# 3. Monitor via deployment status
devctl deploy status DEPLOYMENT_ID

# 4. ArgoCD handles the actual Kubernetes updates
devctl argocd apps status my-app
```

## State Persistence

Deployment state is persisted locally in `~/.devctl/deployments/`. This allows:
- Tracking deployment progress across CLI invocations
- Resuming after interruptions
- Viewing historical deployments
