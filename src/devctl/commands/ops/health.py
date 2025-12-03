"""Health check operations."""

import time
from typing import Any

import click
import httpx

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import DevCtlError


@click.group()
@pass_context
def health(ctx: DevCtlContext) -> None:
    """Health check operations.

    \b
    Examples:
        devctl ops health check my-service
        devctl ops health wait my-service --timeout 300
        devctl ops health url https://api.example.com/health
    """
    pass


@health.command("check")
@click.argument("target")
@click.option("--type", "check_type", type=click.Choice(["http", "tcp", "ecs", "eks"]), default="http", help="Check type")
@click.option("--port", type=int, help="Port for TCP checks")
@click.option("--path", default="/health", help="Path for HTTP checks")
@click.option("--timeout", type=int, default=10, help="Request timeout in seconds")
@pass_context
def check(
    ctx: DevCtlContext,
    target: str,
    check_type: str,
    port: int | None,
    path: str,
    timeout: int,
) -> None:
    """Perform a health check on a target.

    TARGET can be a URL, hostname, ECS service, or EKS deployment.
    """
    try:
        if check_type == "http":
            result = _check_http(target, path, timeout)
        elif check_type == "tcp":
            if port is None:
                raise click.BadParameter("--port is required for TCP checks")
            result = _check_tcp(target, port, timeout)
        elif check_type == "ecs":
            result = _check_ecs(ctx, target)
        elif check_type == "eks":
            result = _check_eks(ctx, target)
        else:
            raise DevCtlError(f"Unknown check type: {check_type}")

        if result["healthy"]:
            ctx.output.print_success(f"Health check passed: {result.get('message', 'OK')}")
        else:
            ctx.output.print_error(f"Health check failed: {result.get('message', 'Unknown error')}")

        if ctx.verbose >= 1 and result.get("details"):
            ctx.output.print_data(result["details"], title="Details")

    except Exception as e:
        raise DevCtlError(f"Health check failed: {e}")


def _check_http(target: str, path: str, timeout: int) -> dict[str, Any]:
    """Perform HTTP health check."""
    url = target if target.startswith("http") else f"https://{target}"
    if not url.endswith(path) and path:
        url = url.rstrip("/") + path

    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        healthy = 200 <= response.status_code < 400

        return {
            "healthy": healthy,
            "message": f"HTTP {response.status_code}",
            "details": {
                "url": url,
                "status_code": response.status_code,
                "response_time_ms": int(response.elapsed.total_seconds() * 1000),
            },
        }
    except httpx.RequestError as e:
        return {
            "healthy": False,
            "message": str(e),
            "details": {"url": url, "error": str(e)},
        }


def _check_tcp(target: str, port: int, timeout: int) -> dict[str, Any]:
    """Perform TCP health check."""
    import socket

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((target, port))
        sock.close()

        if result == 0:
            return {
                "healthy": True,
                "message": f"TCP connection to {target}:{port} succeeded",
                "details": {"host": target, "port": port},
            }
        else:
            return {
                "healthy": False,
                "message": f"TCP connection to {target}:{port} failed",
                "details": {"host": target, "port": port, "error_code": result},
            }
    except socket.error as e:
        return {
            "healthy": False,
            "message": str(e),
            "details": {"host": target, "port": port, "error": str(e)},
        }


def _check_ecs(ctx: DevCtlContext, service: str) -> dict[str, Any]:
    """Check ECS service health."""
    from botocore.exceptions import ClientError

    # Parse service name (can be cluster/service or just service)
    if "/" in service:
        cluster, service_name = service.split("/", 1)
    else:
        cluster = "default"
        service_name = service

    try:
        ecs = ctx.aws.client("ecs")
        response = ecs.describe_services(cluster=cluster, services=[service_name])

        services = response.get("services", [])
        if not services:
            return {"healthy": False, "message": f"Service not found: {service}"}

        svc = services[0]
        running = svc.get("runningCount", 0)
        desired = svc.get("desiredCount", 0)

        healthy = running >= desired and running > 0

        return {
            "healthy": healthy,
            "message": f"{running}/{desired} tasks running",
            "details": {
                "cluster": cluster,
                "service": service_name,
                "running_count": running,
                "desired_count": desired,
                "status": svc.get("status", "-"),
            },
        }
    except ClientError as e:
        return {"healthy": False, "message": str(e)}


def _check_eks(ctx: DevCtlContext, deployment: str) -> dict[str, Any]:
    """Check EKS deployment health (requires kubectl)."""
    import subprocess

    # Parse deployment name (can be namespace/deployment or just deployment)
    if "/" in deployment:
        namespace, deploy_name = deployment.split("/", 1)
    else:
        namespace = "default"
        deploy_name = deployment

    try:
        cmd = [
            "kubectl", "get", "deployment", deploy_name,
            "-n", namespace,
            "-o", "jsonpath={.status.readyReplicas}/{.spec.replicas}",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            return {
                "healthy": False,
                "message": result.stderr or "kubectl failed",
            }

        output = result.stdout.strip()
        if "/" in output:
            ready, total = output.split("/")
            ready = int(ready) if ready else 0
            total = int(total) if total else 0
            healthy = ready >= total and ready > 0

            return {
                "healthy": healthy,
                "message": f"{ready}/{total} pods ready",
                "details": {
                    "namespace": namespace,
                    "deployment": deploy_name,
                    "ready": ready,
                    "total": total,
                },
            }

        return {"healthy": False, "message": f"Unexpected output: {output}"}

    except subprocess.TimeoutExpired:
        return {"healthy": False, "message": "kubectl timed out"}
    except FileNotFoundError:
        return {"healthy": False, "message": "kubectl not found"}


@health.command("wait")
@click.argument("target")
@click.option("--type", "check_type", type=click.Choice(["http", "tcp", "ecs", "eks"]), default="http", help="Check type")
@click.option("--timeout", type=int, default=300, help="Total wait timeout in seconds")
@click.option("--interval", type=int, default=10, help="Check interval in seconds")
@click.option("--path", default="/health", help="Path for HTTP checks")
@pass_context
def wait(
    ctx: DevCtlContext,
    target: str,
    check_type: str,
    timeout: int,
    interval: int,
    path: str,
) -> None:
    """Wait for a target to become healthy."""
    ctx.output.print_info(f"Waiting for {target} to become healthy (timeout: {timeout}s)...")

    start_time = time.time()

    while True:
        elapsed = time.time() - start_time
        if elapsed >= timeout:
            raise DevCtlError(f"Timeout waiting for {target} after {timeout}s")

        if check_type == "http":
            result = _check_http(target, path, 10)
        elif check_type == "ecs":
            result = _check_ecs(ctx, target)
        elif check_type == "eks":
            result = _check_eks(ctx, target)
        else:
            raise DevCtlError(f"Unsupported check type for wait: {check_type}")

        if result["healthy"]:
            ctx.output.print_success(f"Target is healthy: {result.get('message', 'OK')}")
            return

        ctx.output.print(f"[dim]Not healthy yet ({int(elapsed)}s): {result.get('message', '-')}[/dim]")
        time.sleep(interval)


@health.command("url")
@click.argument("url")
@click.option("--expected-status", type=int, default=200, help="Expected HTTP status code")
@click.option("--expected-body", help="Expected string in response body")
@click.option("--timeout", type=int, default=10, help="Request timeout")
@pass_context
def check_url(
    ctx: DevCtlContext,
    url: str,
    expected_status: int,
    expected_body: str | None,
    timeout: int,
) -> None:
    """Check a specific URL health."""
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)

        checks = []

        # Status check
        status_ok = response.status_code == expected_status
        checks.append({
            "Check": "Status Code",
            "Expected": expected_status,
            "Actual": response.status_code,
            "Result": "[green]PASS[/green]" if status_ok else "[red]FAIL[/red]",
        })

        # Body check
        if expected_body:
            body_ok = expected_body in response.text
            checks.append({
                "Check": "Body Contains",
                "Expected": expected_body[:30],
                "Actual": "Found" if body_ok else "Not found",
                "Result": "[green]PASS[/green]" if body_ok else "[red]FAIL[/red]",
            })

        # Response time
        response_time = int(response.elapsed.total_seconds() * 1000)
        checks.append({
            "Check": "Response Time",
            "Expected": "-",
            "Actual": f"{response_time}ms",
            "Result": "[green]OK[/green]",
        })

        ctx.output.print_data(checks, headers=["Check", "Expected", "Actual", "Result"], title=f"Health Check: {url}")

        all_passed = all(c.get("Result", "").find("PASS") >= 0 or c.get("Result", "").find("OK") >= 0 for c in checks)
        if all_passed:
            ctx.output.print_success("All checks passed")
        else:
            ctx.output.print_error("Some checks failed")

    except httpx.RequestError as e:
        ctx.output.print_error(f"Request failed: {e}")
