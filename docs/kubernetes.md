# Kubernetes Commands

devctl provides direct Kubernetes cluster operations without needing to switch kubectl contexts.

## Prerequisites

- Kubernetes cluster access configured via kubeconfig
- Appropriate RBAC permissions for the operations you need

## Configuration

```yaml
profiles:
  default:
    k8s:
      kubeconfig: ~/.kube/config  # Optional, uses default
      context: my-cluster         # Optional, uses current context
      namespace: default          # Default namespace
      timeout: 30                 # Operation timeout in seconds
```

Environment variables:
```bash
export KUBECONFIG=~/.kube/config
export DEVCTL_K8S_CONTEXT=my-cluster
export DEVCTL_K8S_NAMESPACE=production
```

## Pod Operations

### List pods

```bash
# List pods in current namespace
devctl k8s pods list

# List pods in specific namespace
devctl k8s pods list -n production

# List pods across all namespaces
devctl k8s pods list -A

# Filter by label selector
devctl k8s pods list -l app=my-app

# Filter by field selector
devctl k8s pods list --field-selector status.phase=Running
```

### View pod logs

```bash
# Get logs from a pod
devctl k8s pods logs my-pod

# Follow logs in real-time
devctl k8s pods logs my-pod -f

# Get last N lines
devctl k8s pods logs my-pod --tail 100

# Get logs since duration
devctl k8s pods logs my-pod --since 1h

# Get logs from specific container
devctl k8s pods logs my-pod -c sidecar

# Get previous container logs (after restart)
devctl k8s pods logs my-pod --previous
```

### Execute commands

```bash
# Run a command in a pod
devctl k8s pods exec my-pod -- ls -la

# Interactive shell
devctl k8s pods exec my-pod -- /bin/sh

# Specify container
devctl k8s pods exec my-pod -c sidecar -- env
```

### Describe pod

```bash
# Get detailed pod information
devctl k8s pods describe my-pod

# Output as YAML
devctl -o yaml k8s pods describe my-pod
```

### Delete pod

```bash
# Delete a pod
devctl k8s pods delete my-pod

# Force delete
devctl k8s pods delete my-pod --force

# Skip confirmation
devctl k8s pods delete my-pod -y
```

## Deployment Operations

### List deployments

```bash
# List deployments
devctl k8s deployments list

# In specific namespace
devctl k8s deployments list -n production
```

### Describe deployment

```bash
devctl k8s deployments describe my-app
```

### Scale deployment

```bash
# Scale to 5 replicas
devctl k8s deployments scale my-app --replicas 5
```

### Restart deployment

```bash
# Rolling restart
devctl k8s deployments restart my-app
```

### Rollout operations

```bash
# Check rollout status
devctl k8s deployments rollout status my-app

# View rollout history
devctl k8s deployments rollout history my-app

# Undo last rollout
devctl k8s deployments rollout undo my-app

# Rollback to specific revision
devctl k8s deployments rollout undo my-app --to-revision 2
```

## Node Operations

```bash
# List nodes
devctl k8s nodes

# Filter by label
devctl k8s nodes --label node-type=worker

# Show resource usage
devctl k8s resources
```

## Cluster Events

```bash
# List recent events
devctl k8s events

# Watch events in real-time
devctl k8s events --watch

# Filter by type
devctl k8s events --type Warning

# Filter by namespace
devctl k8s events -n production
```

## Resource Summary

```bash
# Show cluster resource usage
devctl k8s resources

# For specific namespace
devctl k8s resources -n production
```

Output includes:
- CPU requests/limits vs capacity
- Memory requests/limits vs capacity
- Pod counts per node
- Resource utilization percentages

## Common Patterns

### Debug a failing pod

```bash
# Check pod status
devctl k8s pods describe my-pod

# Check recent events
devctl k8s events -n my-namespace

# View logs
devctl k8s pods logs my-pod --tail 100

# Check previous container logs if restarting
devctl k8s pods logs my-pod --previous
```

### Rolling update verification

```bash
# Start the update
kubectl set image deployment/my-app app=myrepo/app:v2

# Watch rollout progress
devctl k8s deployments rollout status my-app

# Check events for issues
devctl k8s events --watch

# If issues, rollback
devctl k8s deployments rollout undo my-app
```

### Quick pod shell access

```bash
# Get shell in running pod
devctl k8s pods exec my-pod -- /bin/sh

# Or bash if available
devctl k8s pods exec my-pod -- /bin/bash
```
