# Configuration

devctl uses a layered configuration system that allows flexible setup across different environments.

## Configuration Hierarchy

Configuration is loaded in order (later sources override earlier):

| Priority | Source | Example |
|----------|--------|---------|
| 1 (lowest) | Default values | Built into code |
| 2 | User config | `~/.devctl/config.yaml` |
| 3 | Project config | `./devctl.yaml` |
| 4 | Environment variables | `DEVCTL_AWS_REGION` |
| 5 (highest) | CLI flags | `--profile production` |

## Configuration File

### Location

devctl looks for configuration in:

1. Path specified by `--config` flag
2. `./devctl.yaml` (current directory)
3. `~/.devctl/config.yaml` (user home)

### Full Schema

```yaml
version: "1"

# Global settings apply to all commands
global:
  output_format: table    # table, json, yaml, raw
  color: auto             # auto, always, never
  verbosity: info         # debug, info, warning, error
  dry_run: false          # Default dry-run mode
  confirm_destructive: true  # Prompt before destructive ops
  timeout: 300            # Default timeout in seconds

# Named profiles for different environments
profiles:
  default:
    aws:
      profile: default           # AWS CLI profile name
      region: us-east-1          # Default region
      # access_key_id: from_env  # Use DEVCTL_AWS_ACCESS_KEY_ID
      # secret_access_key: from_env
    grafana:
      url: https://your-stack.grafana.net
      api_key: from_env          # Use DEVCTL_GRAFANA_API_KEY
    github:
      token: from_env            # Use DEVCTL_GITHUB_TOKEN
      org: your-org              # Default organization

  production:
    aws:
      profile: prod-account
      region: us-west-2
    grafana:
      url: https://prod.grafana.net
    github:
      org: your-org-prod

  staging:
    aws:
      profile: staging-account
      region: us-east-1
    grafana:
      url: https://staging.grafana.net

# Custom workflows (see workflows.md)
workflows:
  deploy:
    description: "Deploy service"
    steps:
      - name: Build
        command: aws ecr build
        params:
          repository: "{{ service }}"
```

## Environment Variables

### AWS

| Variable | Description | Fallback |
|----------|-------------|----------|
| `DEVCTL_AWS_PROFILE` | AWS CLI profile name | `AWS_PROFILE` |
| `DEVCTL_AWS_REGION` | AWS region | `AWS_REGION`, `AWS_DEFAULT_REGION` |
| `DEVCTL_AWS_ACCESS_KEY_ID` | Access key (if not using profile) | `AWS_ACCESS_KEY_ID` |
| `DEVCTL_AWS_SECRET_ACCESS_KEY` | Secret key | `AWS_SECRET_ACCESS_KEY` |

### Grafana

| Variable | Description | Fallback |
|----------|-------------|----------|
| `DEVCTL_GRAFANA_URL` | Grafana instance URL | - |
| `DEVCTL_GRAFANA_API_KEY` | API key (Service Account token) | `GRAFANA_API_KEY` |

### GitHub

| Variable | Description | Fallback |
|----------|-------------|----------|
| `DEVCTL_GITHUB_TOKEN` | Personal access token or app token | `GITHUB_TOKEN`, `GH_TOKEN` |
| `DEVCTL_GITHUB_ORG` | Default organization | - |

### devctl Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `DEVCTL_PROFILE` | Active configuration profile | `default` |
| `DEVCTL_OUTPUT_FORMAT` | Output format | `table` |
| `DEVCTL_NO_COLOR` | Disable colors | `false` |
| `DEVCTL_DEBUG` | Enable debug logging | `false` |

## Profiles

Profiles allow switching between environments without changing credentials.

### Using profiles

```bash
# CLI flag (highest priority)
devctl -p production aws iam whoami

# Environment variable
export DEVCTL_PROFILE=production
devctl aws iam whoami

# In config file
profiles:
  default:
    aws:
      region: us-east-1
  production:
    aws:
      region: us-west-2
```

### Profile inheritance

Profiles don't inherit from each other. Each profile must define all settings it needs.

## Credential Management

### AWS Credentials

Recommended: Use AWS CLI profiles in `~/.aws/credentials`:

```ini
[default]
aws_access_key_id = AKIA...
aws_secret_access_key = ...

[prod-account]
role_arn = arn:aws:iam::123456789012:role/DevOpsRole
source_profile = default
```

Then reference in devctl config:

```yaml
profiles:
  production:
    aws:
      profile: prod-account
```

For SSO:

```bash
aws sso login --profile my-sso-profile
devctl -p my-sso-profile aws iam whoami
```

### Grafana API Keys

1. Go to Grafana → Administration → Service Accounts
2. Create a service account with appropriate permissions
3. Generate a token
4. Set `DEVCTL_GRAFANA_API_KEY=glsa_...`

Required permissions depend on commands used:

| Command | Required Permission |
|---------|---------------------|
| `dashboards list` | `dashboards:read` |
| `dashboards import` | `dashboards:write` |
| `alerts list` | `alert.rules:read` |
| `alerts silence` | `alert.silences:write` |
| `datasources list` | `datasources:read` |
| `annotations create` | `annotations:write` |

### GitHub Tokens

Create a personal access token or fine-grained token at GitHub → Settings → Developer settings → Tokens.

Required scopes:

| Command | Required Scope |
|---------|----------------|
| `repos list` | `repo` (or `public_repo` for public only) |
| `actions run` | `workflow` |
| `prs create` | `repo` |
| `releases create` | `repo` |

## Project-Level Configuration

Create `devctl.yaml` in your project root for project-specific settings:

```yaml
version: "1"

profiles:
  default:
    aws:
      region: eu-west-1  # Project uses EU region

workflows:
  deploy:
    description: "Deploy this project"
    vars:
      service_name: my-service
      cluster: my-cluster
    steps:
      - name: Build
        command: aws ecr build
        params:
          repository: "{{ service_name }}"
```

This overrides user-level `~/.devctl/config.yaml` for this project.

## Secrets Management

Never commit secrets to version control.

### Recommended approaches

1. **Environment variables** - Set in shell profile or CI/CD

```bash
export DEVCTL_GRAFANA_API_KEY=$(vault read -field=key secret/grafana)
```

2. **AWS Secrets Manager** - For team sharing

```bash
export DEVCTL_GRAFANA_API_KEY=$(aws secretsmanager get-secret-value \
  --secret-id devctl/grafana-api-key \
  --query SecretString --output text)
```

3. **1Password CLI**

```bash
export DEVCTL_GRAFANA_API_KEY=$(op read "op://DevOps/Grafana/api-key")
```

4. **.env files** - Local development only

```bash
# .env (add to .gitignore)
DEVCTL_GRAFANA_API_KEY=glsa_xxx
DEVCTL_GITHUB_TOKEN=ghp_xxx
```

Load with:

```bash
source .env
# or
export $(cat .env | xargs)
```

## Validation

Check your configuration:

```bash
# Show loaded configuration
devctl -vvv aws iam whoami 2>&1 | head -20

# Test specific service connectivity
devctl aws iam whoami          # AWS
devctl grafana datasources list  # Grafana
devctl github repos list         # GitHub
```

## Common Issues

### "No credentials found"

```bash
# Check AWS credentials
aws configure list
aws sts get-caller-identity

# Check devctl sees the profile
devctl -vvv aws iam whoami
```

### "Invalid API key"

```bash
# Verify Grafana API key is set
echo $DEVCTL_GRAFANA_API_KEY | head -c 10

# Test with curl
curl -H "Authorization: Bearer $DEVCTL_GRAFANA_API_KEY" \
  https://your-stack.grafana.net/api/health
```

### "Profile not found"

```bash
# List available profiles in config
grep -A1 "profiles:" ~/.devctl/config.yaml

# Check profile exists
devctl -p nonexistent aws iam whoami
# Error: Profile not found: nonexistent
```
