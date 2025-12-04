# AWS Systems Manager (SSM)

Manage AWS SSM Parameter Store, Run Command, and Session Manager.

## Overview

SSM commands provide:
- **Parameter Store** - Secure configuration and secrets management
- **Run Command** - Execute commands on EC2 instances remotely
- **Session Manager** - Interactive shell access without SSH

## Parameter Store

### List Parameters

```bash
# List all parameters under a path
devctl aws ssm params list --path /app/

# List recursively (include nested paths)
devctl aws ssm params list --path /app/ --recursive

# Decrypt SecureString values
devctl aws ssm params list --path /app/ --decrypt
```

### Get Parameter

```bash
# Get parameter value
devctl aws ssm params get /app/database/url

# Decrypt SecureString
devctl aws ssm params get /app/api/secret --decrypt

# View parameter history
devctl aws ssm params get /app/config/version --history
```

### Set Parameter

```bash
# Create string parameter
devctl aws ssm params set /app/config/endpoint --value "https://api.example.com"

# Create SecureString (encrypted)
devctl aws ssm params set /app/secrets/api-key --value "secret123" --type SecureString

# Update existing parameter
devctl aws ssm params set /app/config/version --value "v2.0" --overwrite

# Add description and tags
devctl aws ssm params set /app/config/feature \
  --value "enabled" \
  --description "Feature flag for new UI" \
  --tags Environment=production --tags Team=platform
```

### Delete Parameter

```bash
# Delete with confirmation
devctl aws ssm params delete /app/old/config

# Force delete (skip confirmation)
devctl aws ssm params delete /app/old/config --force
```

### Copy Parameter

```bash
# Copy to new path
devctl aws ssm params copy /app/staging/config /app/production/config

# Copy with overwrite
devctl aws ssm params copy /app/v1/settings /app/v2/settings --overwrite
```

## Run Command

Execute shell commands on EC2 instances via SSM agent.

### Run Command on Instances

```bash
# Run command on instances by tag
devctl aws ssm run 'uptime' --targets tag:Environment=production

# Run on specific instance
devctl aws ssm run 'df -h' --targets i-1234567890abcdef0

# Run on multiple targets
devctl aws ssm run 'systemctl status nginx' \
  --targets tag:Role=web \
  --targets tag:Environment=staging

# Run with custom timeout
devctl aws ssm run 'apt-get update && apt-get upgrade -y' \
  --targets tag:Environment=staging \
  --timeout 1800

# Run without waiting for completion
devctl aws ssm run 'long-running-script.sh' \
  --targets tag:Role=worker \
  --no-wait
```

### Check Command Status

```bash
# Get status of a command
devctl aws ssm status abc123-command-id
```

### Target Formats

| Format | Description | Example |
|--------|-------------|---------|
| `tag:Key=Value` | Instances with specific tag | `tag:Environment=production` |
| `i-xxxxx` | Specific instance ID | `i-1234567890abcdef0` |

## Managed Instances

### List Instances

```bash
# List all SSM-managed instances
devctl aws ssm instances

# Filter by online status
devctl aws ssm instances --filter online

# Filter by offline status
devctl aws ssm instances --filter offline
```

Output:
```
SSM Managed Instances (5 found)
┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Instance ID          ┃ Name           ┃ Status   ┃ Platform       ┃ Last Ping   ┃
┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ i-0123456789abcdef0  │ web-server-1   │ Online   │ Amazon Linux 2 │ 2024-01-15  │
│ i-0123456789abcdef1  │ api-server-1   │ Online   │ Ubuntu 22.04   │ 2024-01-15  │
│ i-0123456789abcdef2  │ worker-1       │ Offline  │ Amazon Linux 2 │ 2024-01-14  │
└──────────────────────┴────────────────┴──────────┴────────────────┴─────────────┘
```

## Session Manager

Start interactive shell sessions without SSH.

```bash
# Start interactive session
devctl aws ssm session i-1234567890abcdef0
```

**Requirements:**
- AWS CLI installed
- Session Manager plugin installed: [Installation Guide](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)
- SSM agent running on target instance

## Workflow Integration

SSM integrates with devctl workflows for automation:

```yaml
name: deploy-config
description: Deploy configuration to instances

steps:
  - name: Update config parameter
    command: aws ssm params set
    params:
      name: "/app/{{ environment }}/config"
      value: "{{ config_value }}"
      type: String
      overwrite: true

  - name: Restart services
    command: "!devctl aws ssm run 'systemctl restart app' --targets tag:Environment={{ environment }}"
    timeout: 300

  - name: Verify services
    command: "!devctl aws ssm run 'systemctl status app' --targets tag:Environment={{ environment }}"
```

## Common Use Cases

### Configuration Management

```bash
# Deploy config to all environments
for env in staging production; do
  devctl aws ssm params set /app/$env/version --value "v2.0" --overwrite
done
```

### Security Patching

```bash
# Check for updates across fleet
devctl aws ssm run 'yum check-update' --targets tag:OS=amazon-linux

# Apply security patches
devctl aws ssm run 'yum update -y --security' \
  --targets tag:Environment=staging \
  --timeout 1800
```

### Log Collection

```bash
# Collect logs from instances
devctl aws ssm run 'tail -100 /var/log/app/error.log' \
  --targets tag:Role=api
```

### Health Checks

```bash
# Check disk space
devctl aws ssm run 'df -h' --targets tag:Environment=production

# Check memory usage
devctl aws ssm run 'free -m' --targets tag:Environment=production

# Check service status
devctl aws ssm run 'systemctl status nginx' --targets tag:Role=web
```

## Best Practices

1. **Use SecureString for secrets** - Always use `--type SecureString` for sensitive values
2. **Organize with paths** - Use hierarchical paths like `/app/env/service/key`
3. **Tag parameters** - Add tags for easier management and cost allocation
4. **Use Run Command over SSH** - More secure, auditable, and doesn't require open ports
5. **Set appropriate timeouts** - Long-running commands need extended timeouts

## Related Documentation

- [AWS Commands](aws-commands.md) - Other AWS operations
- [Workflows](workflows.md) - Automate SSM operations
- [Configuration](configuration.md) - AWS profile setup
