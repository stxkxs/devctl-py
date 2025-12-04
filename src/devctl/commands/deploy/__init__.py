"""Deploy command group."""

import click

from devctl.core.context import pass_context, DevCtlContext
from devctl.core.exceptions import DeploymentError
from devctl.deploy import Deployment, DeploymentStrategy, DeploymentStatus, DeploymentState


@click.group()
@pass_context
def deploy(ctx: DevCtlContext) -> None:
    """Deployment orchestration - create, status, promote, rollback.

    \b
    Examples:
        devctl deploy create --name my-app --image myrepo/app:v1.2.3 --strategy canary
        devctl deploy status abc123
        devctl deploy promote abc123
        devctl deploy rollback abc123
    """
    pass


@deploy.command("create")
@click.option("--name", required=True, help="Deployment name")
@click.option("--image", required=True, help="Container image")
@click.option("--strategy", type=click.Choice(["rolling", "blue-green", "canary"]), default="rolling", help="Deployment strategy")
@click.option("-n", "--namespace", default="default", help="Namespace")
@click.option("--replicas", type=int, default=3, help="Number of replicas")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation")
@pass_context
def create(
    ctx: DevCtlContext,
    name: str,
    image: str,
    strategy: str,
    namespace: str,
    replicas: int,
    yes: bool,
) -> None:
    """Create a deployment.

    \b
    Examples:
        devctl deploy create --name my-app --image myrepo/app:v1.2.3
        devctl deploy create --name my-app --image myrepo/app:v1.2.3 --strategy canary
    """
    try:
        if ctx.dry_run:
            ctx.log_dry_run("create deployment", {"name": name, "image": image, "strategy": strategy})
            return

        if not yes and not ctx.confirm(f"Create {strategy} deployment for {name}?"):
            ctx.output.print_info("Cancelled")
            return

        # Create deployment object
        deployment = Deployment(
            name=name,
            namespace=namespace,
            image=image,
            replicas=replicas,
            strategy=DeploymentStrategy(strategy),
        )

        # Get strategy config from profile
        deploy_config = ctx.config.get_profile(ctx.profile_name).deploy
        if strategy == "canary":
            deployment.strategy_config = deploy_config.canary.model_dump()
        elif strategy == "blue-green":
            deployment.strategy_config = deploy_config.blue_green.model_dump()
        else:
            deployment.strategy_config = deploy_config.rolling.model_dump()

        # Save initial state
        state = DeploymentState()
        state.save(deployment)

        # Execute deployment
        from devctl.deploy.strategies import (
            RollingDeploymentExecutor,
            BlueGreenDeploymentExecutor,
            CanaryDeploymentExecutor,
        )

        if strategy == "rolling":
            executor = RollingDeploymentExecutor(ctx.k8s)
        elif strategy == "blue-green":
            executor = BlueGreenDeploymentExecutor(ctx.k8s)
        else:
            executor = CanaryDeploymentExecutor(ctx.k8s)

        deployment = executor.execute(deployment, dry_run=ctx.dry_run)
        state.save(deployment)

        if deployment.status == DeploymentStatus.SUCCEEDED:
            ctx.output.print_success(f"Deployment {deployment.id} completed")
        elif deployment.status == DeploymentStatus.FAILED:
            ctx.output.print_error(f"Deployment {deployment.id} failed: {deployment.message}")
        else:
            ctx.output.print_info(f"Deployment {deployment.id} status: {deployment.status.value}")
            if strategy in ("canary", "blue-green"):
                ctx.output.print_info(f"Use 'devctl deploy promote {deployment.id}' to complete")

    except DeploymentError as e:
        ctx.output.print_error(f"Deployment failed: {e}")
        raise click.Abort()


@deploy.command("status")
@click.argument("deployment_id")
@pass_context
def status(ctx: DevCtlContext, deployment_id: str) -> None:
    """Show deployment status.

    \b
    Examples:
        devctl deploy status abc123
    """
    try:
        state = DeploymentState()
        deployment = state.load(deployment_id)

        ctx.output.print_header(f"Deployment: {deployment.id}")
        ctx.output.print(f"Name: {deployment.name}")
        ctx.output.print(f"Namespace: {deployment.namespace}")
        ctx.output.print(f"Strategy: {deployment.strategy.value}")
        ctx.output.print(f"Status: {deployment.status.value}")
        ctx.output.print(f"Phase: {deployment.phase.value}")
        ctx.output.print(f"Progress: {deployment.progress}%")

        if deployment.strategy == DeploymentStrategy.CANARY:
            ctx.output.print(f"Canary Weight: {deployment.canary_weight}%")
        elif deployment.strategy == DeploymentStrategy.BLUE_GREEN:
            ctx.output.print(f"Active Color: {deployment.active_color}")

        ctx.output.print(f"\nImage: {deployment.image}")
        if deployment.previous_image:
            ctx.output.print(f"Previous: {deployment.previous_image}")

        # Recent events
        if deployment.events:
            ctx.output.print("\nRecent Events:")
            for event in deployment.events[-5:]:
                ctx.output.print(f"  [{event.timestamp.strftime('%H:%M:%S')}] {event.event_type}: {event.message}")

    except DeploymentError as e:
        ctx.output.print_error(f"Failed to get status: {e}")
        raise click.Abort()


@deploy.command("promote")
@click.argument("deployment_id")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation")
@pass_context
def promote(ctx: DevCtlContext, deployment_id: str, yes: bool) -> None:
    """Promote a canary/blue-green deployment.

    \b
    Examples:
        devctl deploy promote abc123
    """
    try:
        state = DeploymentState()
        deployment = state.load(deployment_id)

        if deployment.strategy == DeploymentStrategy.ROLLING:
            ctx.output.print_error("Rolling deployments don't need promotion")
            return

        if ctx.dry_run:
            ctx.log_dry_run("promote deployment", {"id": deployment_id})
            return

        if not yes and not ctx.confirm(f"Promote deployment {deployment_id}?"):
            ctx.output.print_info("Cancelled")
            return

        from devctl.deploy.strategies import BlueGreenDeploymentExecutor, CanaryDeploymentExecutor

        if deployment.strategy == DeploymentStrategy.BLUE_GREEN:
            executor = BlueGreenDeploymentExecutor(ctx.k8s)
        else:
            executor = CanaryDeploymentExecutor(ctx.k8s)

        deployment = executor.promote(deployment, dry_run=ctx.dry_run)
        state.save(deployment)

        if deployment.status == DeploymentStatus.SUCCEEDED:
            ctx.output.print_success(f"Deployment {deployment_id} promoted")
        else:
            ctx.output.print_error(f"Promotion failed: {deployment.message}")

    except DeploymentError as e:
        ctx.output.print_error(f"Promote failed: {e}")
        raise click.Abort()


@deploy.command("rollback")
@click.argument("deployment_id")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation")
@pass_context
def rollback(ctx: DevCtlContext, deployment_id: str, yes: bool) -> None:
    """Rollback a deployment.

    \b
    Examples:
        devctl deploy rollback abc123
    """
    try:
        state = DeploymentState()
        deployment = state.load(deployment_id)

        if ctx.dry_run:
            ctx.log_dry_run("rollback deployment", {"id": deployment_id})
            return

        if not yes and not ctx.confirm(f"Rollback deployment {deployment_id}?"):
            ctx.output.print_info("Cancelled")
            return

        from devctl.deploy.strategies import (
            RollingDeploymentExecutor,
            BlueGreenDeploymentExecutor,
            CanaryDeploymentExecutor,
        )

        if deployment.strategy == DeploymentStrategy.ROLLING:
            executor = RollingDeploymentExecutor(ctx.k8s)
        elif deployment.strategy == DeploymentStrategy.BLUE_GREEN:
            executor = BlueGreenDeploymentExecutor(ctx.k8s)
        else:
            executor = CanaryDeploymentExecutor(ctx.k8s)

        deployment = executor.rollback(deployment, dry_run=ctx.dry_run)
        state.save(deployment)

        ctx.output.print_success(f"Rollback initiated for {deployment_id}")

    except DeploymentError as e:
        ctx.output.print_error(f"Rollback failed: {e}")
        raise click.Abort()


@deploy.command("abort")
@click.argument("deployment_id")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation")
@pass_context
def abort(ctx: DevCtlContext, deployment_id: str, yes: bool) -> None:
    """Abort an in-progress deployment.

    \b
    Examples:
        devctl deploy abort abc123
    """
    try:
        state = DeploymentState()
        deployment = state.load(deployment_id)

        if not deployment.is_active:
            ctx.output.print_info(f"Deployment is not active (status: {deployment.status.value})")
            return

        if ctx.dry_run:
            ctx.log_dry_run("abort deployment", {"id": deployment_id})
            return

        if not yes and not ctx.confirm(f"Abort deployment {deployment_id}?"):
            ctx.output.print_info("Cancelled")
            return

        from devctl.deploy.strategies import (
            RollingDeploymentExecutor,
            BlueGreenDeploymentExecutor,
            CanaryDeploymentExecutor,
        )

        if deployment.strategy == DeploymentStrategy.ROLLING:
            executor = RollingDeploymentExecutor(ctx.k8s)
        elif deployment.strategy == DeploymentStrategy.BLUE_GREEN:
            executor = BlueGreenDeploymentExecutor(ctx.k8s)
        else:
            executor = CanaryDeploymentExecutor(ctx.k8s)

        deployment = executor.abort(deployment, dry_run=ctx.dry_run)
        state.save(deployment)

        ctx.output.print_success(f"Deployment {deployment_id} aborted")

    except DeploymentError as e:
        ctx.output.print_error(f"Abort failed: {e}")
        raise click.Abort()


@deploy.command("list")
@click.option("-n", "--namespace", default=None, help="Filter by namespace")
@click.option("--active", is_flag=True, help="Show only active deployments")
@click.option("--limit", default=20, help="Max results")
@pass_context
def list_deployments(
    ctx: DevCtlContext,
    namespace: str | None,
    active: bool,
    limit: int,
) -> None:
    """List deployments.

    \b
    Examples:
        devctl deploy list
        devctl deploy list --active
    """
    try:
        state = DeploymentState()

        if active:
            deployments = state.list_active()
        else:
            deployments = state.list(namespace=namespace, limit=limit)

        if not deployments:
            ctx.output.print_info("No deployments found")
            return

        rows = []
        for dep in deployments:
            rows.append({
                "id": dep.id,
                "name": dep.name,
                "namespace": dep.namespace,
                "strategy": dep.strategy.value,
                "status": dep.status.value,
                "progress": f"{dep.progress}%",
                "created": dep.created_at.strftime("%Y-%m-%d %H:%M"),
            })

        ctx.output.print_table(
            rows,
            columns=["id", "name", "namespace", "strategy", "status", "progress", "created"],
            title="Deployments",
        )

    except DeploymentError as e:
        ctx.output.print_error(f"Failed to list deployments: {e}")
        raise click.Abort()
