#!/bin/bash
set -euo pipefail

# =============================================================================
# DevCtl Container Entrypoint
# =============================================================================
#
# This script handles:
# - Credential validation and setup
# - AWS SSO session handling
# - Interactive shell mode
# - Signal handling for graceful shutdown
#

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[devctl]${NC} $*" >&2
}

log_warn() {
    echo -e "${YELLOW}[devctl]${NC} $*" >&2
}

log_error() {
    echo -e "${RED}[devctl]${NC} $*" >&2
}

log_success() {
    echo -e "${GREEN}[devctl]${NC} $*" >&2
}

# =============================================================================
# Credential Validation
# =============================================================================

check_aws_credentials() {
    # Check for AWS credentials in various forms
    if [[ -n "${AWS_ACCESS_KEY_ID:-}" && -n "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
        log_info "Using AWS credentials from environment variables"
        return 0
    fi

    if [[ -f "${HOME}/.aws/credentials" ]]; then
        log_info "Using AWS credentials from ~/.aws/credentials"
        return 0
    fi

    if [[ -n "${AWS_PROFILE:-}" && -f "${HOME}/.aws/config" ]]; then
        log_info "Using AWS profile: ${AWS_PROFILE}"
        return 0
    fi

    if [[ -n "${AWS_ROLE_ARN:-}" ]]; then
        log_info "Using AWS role assumption: ${AWS_ROLE_ARN}"
        return 0
    fi

    if [[ -n "${AWS_WEB_IDENTITY_TOKEN_FILE:-}" ]]; then
        log_info "Using AWS web identity (IRSA/EKS Pod Identity)"
        return 0
    fi

    # Check for SSO configuration
    if [[ -f "${HOME}/.aws/config" ]] && grep -q "sso_start_url" "${HOME}/.aws/config" 2>/dev/null; then
        log_warn "AWS SSO configured but may need login. Run: aws sso login"
        return 0
    fi

    return 1
}

check_grafana_credentials() {
    if [[ -n "${GRAFANA_API_KEY:-}" || -n "${DEVCTL_GRAFANA_API_KEY:-}" ]]; then
        log_info "Grafana API key configured"
        return 0
    fi
    return 1
}

check_github_credentials() {
    if [[ -n "${GITHUB_TOKEN:-}" || -n "${DEVCTL_GITHUB_TOKEN:-}" || -n "${GH_TOKEN:-}" ]]; then
        log_info "GitHub token configured"
        return 0
    fi
    return 1
}

validate_credentials() {
    local has_any=false

    if check_aws_credentials; then
        has_any=true
    else
        log_warn "No AWS credentials found"
    fi

    if check_grafana_credentials; then
        has_any=true
    fi

    if check_github_credentials; then
        has_any=true
    fi

    if [[ "$has_any" == "false" ]]; then
        log_warn "No credentials configured. Some commands may fail."
        log_info "Mount credentials: -v ~/.aws:/home/devctl/.aws:ro"
        log_info "Or set env vars: -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY"
    fi
}

# =============================================================================
# Kubeconfig Handling
# =============================================================================

setup_kubeconfig() {
    # If kubeconfig is mounted, ensure it's usable
    if [[ -f "${HOME}/.kube/config" ]]; then
        log_info "Kubeconfig found at ~/.kube/config"

        # Check if it references AWS EKS (needs AWS auth)
        if grep -q "eks.amazonaws.com" "${HOME}/.kube/config" 2>/dev/null; then
            log_info "EKS cluster detected - AWS credentials required for kubectl"
        fi
    fi

    # Support for KUBECONFIG env var
    if [[ -n "${KUBECONFIG:-}" ]]; then
        log_info "Using KUBECONFIG: ${KUBECONFIG}"
    fi
}

# =============================================================================
# Interactive Shell Mode
# =============================================================================

run_shell() {
    log_info "Starting interactive shell..."
    log_info "Type 'devctl --help' for available commands"
    echo ""
    exec /bin/bash
}

# =============================================================================
# Signal Handling
# =============================================================================

cleanup() {
    log_info "Shutting down..."
    exit 0
}

trap cleanup SIGTERM SIGINT

# =============================================================================
# Main
# =============================================================================

main() {
    # Handle special flags
    case "${1:-}" in
        --shell|-s)
            validate_credentials
            setup_kubeconfig
            run_shell
            ;;
        --validate)
            log_info "Validating configuration..."
            validate_credentials
            setup_kubeconfig

            # Test AWS connectivity if credentials present
            if check_aws_credentials; then
                log_info "Testing AWS connectivity..."
                if aws sts get-caller-identity &>/dev/null; then
                    log_success "AWS credentials valid"
                else
                    log_error "AWS credentials invalid or expired"
                    exit 1
                fi
            fi

            log_success "Validation complete"
            exit 0
            ;;
        --version|-V)
            exec devctl --version
            ;;
        --help|-h)
            echo "DevCtl Docker Container"
            echo ""
            echo "Usage:"
            echo "  docker run devctl [OPTIONS] COMMAND [ARGS]"
            echo ""
            echo "Container Options:"
            echo "  --shell, -s     Start interactive shell"
            echo "  --validate      Validate credentials and exit"
            echo "  --version, -V   Show version"
            echo "  --help, -h      Show this help"
            echo ""
            echo "Mounting Credentials:"
            echo "  -v ~/.aws:/home/devctl/.aws:ro          AWS credentials"
            echo "  -v ~/.kube:/home/devctl/.kube:ro        Kubeconfig"
            echo "  -v ~/.devctl:/home/devctl/.devctl:ro    DevCtl config"
            echo ""
            echo "Environment Variables:"
            echo "  AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY"
            echo "  AWS_PROFILE, AWS_REGION"
            echo "  GRAFANA_API_KEY or DEVCTL_GRAFANA_API_KEY"
            echo "  GITHUB_TOKEN or DEVCTL_GITHUB_TOKEN"
            echo ""
            echo "Examples:"
            echo "  docker run devctl aws iam whoami"
            echo "  docker run -v ~/.aws:/home/devctl/.aws:ro devctl aws s3 ls"
            echo "  docker run -e GITHUB_TOKEN devctl github repos list"
            echo ""
            exit 0
            ;;
    esac

    # Validate credentials (non-blocking)
    validate_credentials
    setup_kubeconfig

    # If no arguments, show help
    if [[ $# -eq 0 ]]; then
        exec devctl --help
    fi

    # Execute devctl with all arguments
    exec devctl "$@"
}

main "$@"
