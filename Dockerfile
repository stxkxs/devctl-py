# syntax=docker/dockerfile:1.4

# DevCtl CLI Container
#
# Build:
#   docker build -t devctl .
#
# Build (development):
#   docker build --target development -t devctl:dev .
#
# Run:
#   docker run --rm -it \
#     -v ~/.aws:/home/devctl/.aws:ro \
#     -v ~/.kube:/home/devctl/.kube:ro \
#     -e GRAFANA_API_KEY \
#     -e GITHUB_TOKEN \
#     devctl aws iam whoami
#
# Interactive shell:
#   docker run --rm -it \
#     -v ~/.aws:/home/devctl/.aws:ro \
#     devctl --shell

# =============================================================================
# Stage 1: Builder
# =============================================================================
FROM python:3.12-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies first (better caching)
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install the package
RUN pip install --no-cache-dir --upgrade pip wheel \
    && pip install --no-cache-dir .

# =============================================================================
# Stage 2: Base runtime (shared by runtime and development)
# =============================================================================
FROM python:3.12-slim AS base

# Labels
LABEL org.opencontainers.image.title="devctl"
LABEL org.opencontainers.image.description="Unified CLI for AWS, Grafana, and GitHub operations"
LABEL org.opencontainers.image.source="https://github.com/stxkxs/devctl"
LABEL org.opencontainers.image.licenses="MIT"

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # AWS CLI v2 dependencies
    curl \
    unzip \
    groff \
    less \
    # Kubernetes tools
    ca-certificates \
    # Git for GitHub operations
    git \
    # SSH for tunneling/git operations
    openssh-client \
    # JSON processing
    jq \
    # Process management
    tini \
    && rm -rf /var/lib/apt/lists/*

# Install AWS CLI v2 (for advanced operations and SSO support)
RUN curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-$(uname -m).zip" -o /tmp/awscliv2.zip \
    && unzip -q /tmp/awscliv2.zip -d /tmp \
    && /tmp/aws/install \
    && rm -rf /tmp/aws /tmp/awscliv2.zip

# Install kubectl (for EKS operations)
RUN KUBECTL_VERSION=$(curl -fsSL https://dl.k8s.io/release/stable.txt) \
    && curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/$(dpkg --print-architecture)/kubectl" -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl

# Install Helm (for Karpenter/chart operations)
RUN curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Create non-root user
RUN groupadd --gid 1000 devctl \
    && useradd --uid 1000 --gid devctl --shell /bin/bash --create-home devctl

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy entrypoint script
COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/entrypoint.sh

# Create directories for configs and credentials
RUN mkdir -p /home/devctl/.aws \
    /home/devctl/.kube \
    /home/devctl/.devctl \
    /home/devctl/.config \
    && chown -R devctl:devctl /home/devctl

# Set working directory
WORKDIR /workspace

# Switch to non-root user
USER devctl

# Environment variables
ENV HOME=/home/devctl \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AWS_PAGER="" \
    DEVCTL_OUTPUT_FORMAT=table \
    FORCE_COLOR=1

# =============================================================================
# Stage 3: Development (for contributors)
# =============================================================================
FROM base AS development

USER root

# Install development tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    vim \
    make \
    && rm -rf /var/lib/apt/lists/*

# Install dev dependencies
RUN pip install --no-cache-dir \
    pytest \
    pytest-cov \
    ruff \
    mypy \
    moto[all]

USER devctl

# Override entrypoint for dev
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/bin/bash"]

# =============================================================================
# Stage 4: Runtime (default - last stage)
# =============================================================================
FROM base AS runtime

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD devctl --version || exit 1

# Use tini as init system with entrypoint
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]

# No default command - entrypoint handles empty args
CMD []
