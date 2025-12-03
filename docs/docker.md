# Docker Usage

Run devctl in a container without installing Python or dependencies locally.

## Quick Start

```bash
# Build the image
docker build -t devctl .

# Run a command
docker run --rm -v ~/.aws:/home/devctl/.aws:ro devctl aws iam whoami

# Interactive shell
docker run --rm -it -v ~/.aws:/home/devctl/.aws:ro devctl --shell
```

## Using Docker Compose

```bash
# Build
docker compose build

# Run commands
docker compose run --rm devctl aws s3 ls
docker compose run --rm devctl grafana dashboards list

# Interactive shell
docker compose run --rm devctl --shell

# Development container (with pytest, ruff, mypy)
docker compose run --rm devctl-dev
```

## Mounting Credentials

### AWS Credentials

```bash
# Mount AWS config directory (recommended)
docker run --rm \
  -v ~/.aws:/home/devctl/.aws:ro \
  devctl aws iam whoami

# Or use environment variables
docker run --rm \
  -e AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY \
  -e AWS_REGION=us-east-1 \
  devctl aws s3 ls

# With specific profile
docker run --rm \
  -v ~/.aws:/home/devctl/.aws:ro \
  -e AWS_PROFILE=production \
  devctl aws eks list-clusters
```

### AWS SSO

```bash
# Login on host first
aws sso login --profile my-sso-profile

# Then run container with SSO cache mounted
docker run --rm \
  -v ~/.aws:/home/devctl/.aws:ro \
  -e AWS_PROFILE=my-sso-profile \
  devctl aws iam whoami
```

### Kubernetes/EKS

```bash
# Mount kubeconfig
docker run --rm \
  -v ~/.aws:/home/devctl/.aws:ro \
  -v ~/.kube:/home/devctl/.kube:ro \
  devctl aws eks describe my-cluster

# The container includes kubectl and helm
docker run --rm \
  -v ~/.kube:/home/devctl/.kube:ro \
  --entrypoint kubectl \
  devctl get nodes
```

### Grafana

```bash
docker run --rm \
  -e GRAFANA_API_KEY=glsa_xxxx \
  devctl grafana dashboards list

# Or with devctl config
docker run --rm \
  -v ~/.devctl:/home/devctl/.devctl:ro \
  -e DEVCTL_GRAFANA_API_KEY=glsa_xxxx \
  devctl grafana alerts list
```

### GitHub

```bash
docker run --rm \
  -e GITHUB_TOKEN=ghp_xxxx \
  devctl github repos list

# Or use GH_TOKEN
docker run --rm \
  -e GH_TOKEN \
  devctl github actions list owner/repo
```

## Container Options

The entrypoint script provides additional options:

```bash
# Show container help
docker run --rm devctl --help

# Validate credentials
docker run --rm \
  -v ~/.aws:/home/devctl/.aws:ro \
  devctl --validate

# Interactive shell
docker run --rm -it \
  -v ~/.aws:/home/devctl/.aws:ro \
  devctl --shell

# Show version
docker run --rm devctl --version
```

## Running Workflows

```bash
# Mount workflow file and run
docker run --rm \
  -v ~/.aws:/home/devctl/.aws:ro \
  -v ./my-workflow.yaml:/workspace/workflow.yaml:ro \
  devctl workflow run /workspace/workflow.yaml --var env=prod

# With docker-compose (mounts current directory)
docker compose run --rm devctl workflow run workflow.yaml --var env=prod
```

## Image Variants

| Target | Image Tag | Description |
|--------|-----------|-------------|
| `runtime` | `devctl:latest` | Production image with CLI tools |
| `development` | `devctl:dev` | Includes pytest, ruff, mypy for development |

```bash
# Build runtime (default)
docker build -t devctl .

# Build development image
docker build --target development -t devctl:dev .
```

## Included Tools

The container includes:

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.12 | Runtime |
| AWS CLI | v2 | AWS SSO support, advanced operations |
| kubectl | stable | Kubernetes operations |
| helm | v3 | Chart management |
| git | latest | GitHub operations |
| jq | latest | JSON processing |

## Security

The container follows security best practices:

- **Non-root user**: Runs as `devctl` user (UID 1000)
- **Read-only mounts**: Credentials mounted as read-only
- **No new privileges**: Security option prevents privilege escalation
- **Read-only filesystem**: Container filesystem is read-only (with tmpfs for /tmp)
- **Minimal image**: Based on python:slim with only required packages

## CI/CD Usage

For automated pipelines:

```yaml
# GitHub Actions example
jobs:
  deploy:
    runs-on: ubuntu-latest
    container:
      image: devctl:latest
    env:
      AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
      AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
      AWS_REGION: us-east-1
    steps:
      - name: Check AWS identity
        run: devctl aws iam whoami

      - name: Deploy
        run: devctl workflow run deploy.yaml --var env=prod
```

```yaml
# GitLab CI example
deploy:
  image: devctl:latest
  variables:
    AWS_ACCESS_KEY_ID: $AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY: $AWS_SECRET_ACCESS_KEY
  script:
    - devctl aws iam whoami
    - devctl workflow run deploy.yaml
```

## Troubleshooting

### Credential errors

```bash
# Validate credentials are accessible
docker run --rm \
  -v ~/.aws:/home/devctl/.aws:ro \
  devctl --validate

# Check what the container sees
docker run --rm \
  -v ~/.aws:/home/devctl/.aws:ro \
  --entrypoint cat \
  devctl /home/devctl/.aws/credentials
```

### Permission denied

```bash
# Ensure files are readable
chmod 644 ~/.aws/credentials
chmod 644 ~/.aws/config

# Or run with your user ID
docker run --rm \
  -u $(id -u):$(id -g) \
  -v ~/.aws:/home/devctl/.aws:ro \
  devctl aws iam whoami
```

### Network issues

```bash
# Use host network if accessing local services
docker run --rm \
  --network host \
  devctl ops health url http://localhost:8080/health
```

### EKS/kubectl issues

```bash
# Verify AWS auth works first
docker run --rm \
  -v ~/.aws:/home/devctl/.aws:ro \
  devctl aws sts get-caller-identity

# Then test kubectl
docker run --rm \
  -v ~/.aws:/home/devctl/.aws:ro \
  -v ~/.kube:/home/devctl/.kube:ro \
  --entrypoint kubectl \
  devctl get nodes
```

## Building Custom Images

Extend the base image for your organization:

```dockerfile
FROM devctl:latest

# Add custom CA certificates
COPY certs/corporate-ca.crt /usr/local/share/ca-certificates/
RUN update-ca-certificates

# Add custom tools
USER root
RUN apt-get update && apt-get install -y your-tool
USER devctl

# Add default config
COPY config.yaml /home/devctl/.devctl/config.yaml
```
