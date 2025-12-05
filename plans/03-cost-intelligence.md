# Cost Intelligence Features

> **Status: ✅ PARTIALLY IMPLEMENTED** (December 2024)
> - ✅ Cost Allocation & Tagging (`devctl aws tagging`, `devctl aws cost by-tag/by-team/by-project`)
> - ✅ Budget Alerts (`devctl aws budget list/status/create/delete/forecast`)
> - ⬜ Cross-Service Optimization (`devctl aws optimize`)
> - ⬜ Cost Attribution Reports (`devctl ops report`)
> - ⬜ FinOps Workflows

Enhanced cost tracking, budgeting, optimization, and automation.

## 3.1 Cost Allocation & Tagging

**Goal**: Track costs by team/project/environment with tag enforcement.

### New Commands

```bash
devctl aws cost by-tag --tag-key Team [--days 30]
devctl aws cost by-team [--days 30]
devctl aws cost by-project [--days 30]
devctl aws cost allocation-report [--format html|csv]

devctl aws tagging audit [--required-tags "team,project,env"]
devctl aws tagging enforce --policy POLICY_FILE
devctl aws tagging report [--days 30]
devctl aws tagging bulk-apply --tag-file FILE
```

### New Files
- `src/devctl/commands/aws/tagging.py`

### Files to Modify
- `src/devctl/commands/aws/cost.py` - Add by-tag grouping
- `src/devctl/config.py` - Add CostAllocationConfig

### Implementation

```python
# In cost.py - extend with tag grouping
def get_costs_by_tag(tag_key: str, days: int = 30):
    ce = boto3.client('cost-explorer')
    response = ce.get_cost_and_usage(
        TimePeriod={...},
        Granularity='MONTHLY',
        Metrics=['UnblendedCost'],
        GroupBy=[{'Type': 'TAG', 'Key': tag_key}]
    )
    return response

# In tagging.py - audit untagged resources
def audit_tags(required_tags: list[str]):
    tagging = boto3.client('resourcegroupstaggingapi')
    resources = tagging.get_resources()
    # Check each resource for required tags
```

### Config Extension

```python
class CostAllocationConfig(BaseModel):
    required_tags: list[str] = ["Team", "Project", "Environment"]
    tag_validation_rules: dict[str, str] = {}  # regex per tag
```

---

## 3.2 Budget Alerts & Forecasting

**Goal**: Proactive budget monitoring with ML-enhanced predictions.

### New Commands

```bash
devctl aws budget list
devctl aws budget create --name NAME --amount N [--filters]
devctl aws budget update BUDGET_NAME [--amount N]
devctl aws budget status [--budget NAME]
devctl aws budget forecast [--months N] [--confidence 0.8]
devctl aws budget slack-alert --budget NAME --channel CH
```

### New File
- `src/devctl/commands/aws/budget.py`

### Files to Modify
- `src/devctl/config.py` - Add BudgetConfig

### Implementation

```python
import boto3

@click.group()
def budget():
    """AWS Budget operations."""
    pass

@budget.command()
def list():
    """List all budgets with status."""
    budgets = boto3.client('budgets')
    response = budgets.describe_budgets(AccountId=get_account_id())
    # Display with actual vs budget comparison

@budget.command()
@click.option('--months', default=3)
def forecast(months: int):
    """Enhanced cost forecast with budget context."""
    # Combine Cost Explorer forecast with budget data
    # Add trend analysis (week-over-week, month-over-month)
```

### Config Extension

```python
class BudgetConfig(BaseModel):
    default_currency: str = "USD"
    alert_thresholds: list[int] = [50, 80, 100]
    forecast_months: int = 3
    slack_channel: str | None = None
```

---

## 3.3 Cross-Service Optimization

**Goal**: Holistic recommendations across EC2, RDS, EKS, Lambda, S3.

### New Commands

```bash
devctl aws optimize scan [--services ec2,rds,eks,lambda,s3]
devctl aws optimize ec2 [--include-reserved]
devctl aws optimize rds [--include-reserved]
devctl aws optimize eks [--cluster NAME]
devctl aws optimize lambda
devctl aws optimize s3 [--bucket NAME]
devctl aws optimize reserved-instances
devctl aws optimize savings-plan-coverage
devctl aws optimize summary [--min-savings N]
devctl aws optimize apply RECOMMENDATION_ID [--dry-run]
```

### New File
- `src/devctl/commands/aws/optimize.py`

### Implementation

```python
@click.group()
def optimize():
    """Cross-service optimization recommendations."""
    pass

@optimize.command()
@click.option('--services', default='ec2,rds,eks,lambda,s3')
def scan(services: str):
    """Full optimization scan."""
    recommendations = []

    if 'ec2' in services:
        # Compute Optimizer recommendations
        co = boto3.client('compute-optimizer')
        recommendations.extend(get_ec2_recommendations(co))

    if 'rds' in services:
        # RDS rightsizing from Cost Explorer
        recommendations.extend(get_rds_recommendations())

    # ... other services

    # Prioritize by savings potential
    recommendations.sort(key=lambda r: r.estimated_savings, reverse=True)
    display_recommendations(recommendations)
```

### Optimization Categories

| Service | Optimizations |
|---------|--------------|
| EC2 | Rightsizing, Spot candidates, RI/SP coverage |
| RDS | Instance sizing, Storage optimization, Multi-AZ analysis |
| EKS | Node rightsizing, Spot node groups, Karpenter |
| Lambda | Memory optimization, ARM64 migration |
| S3 | Lifecycle policies, Storage class optimization |

---

## 3.4 Cost Attribution Reports

**Goal**: Automated reports for stakeholders.

### New Commands

```bash
devctl ops report cost-summary [--period weekly|monthly] [--format html|csv]
devctl ops report team-breakdown --team TEAM [--period P]
devctl ops report project-breakdown --project PROJ [--period P]
devctl ops report executive-summary [--period P]
devctl ops report generate --template TEMPLATE [--output FILE]
devctl ops report schedule --template T --cron "0 9 * * 1"
devctl ops report deliver --report FILE --channel slack|confluence
```

### New Files
- `src/devctl/commands/ops/report.py`
- `src/devctl/reports/__init__.py`
- `src/devctl/reports/templates/executive-summary.html.j2`
- `src/devctl/reports/templates/team-breakdown.html.j2`
- `src/devctl/reports/templates/weekly-digest.html.j2`

### Implementation

```python
from jinja2 import Environment, PackageLoader

class ReportGenerator:
    def __init__(self):
        self.env = Environment(
            loader=PackageLoader('devctl.reports', 'templates')
        )

    def generate(self, template_name: str, data: dict) -> str:
        template = self.env.get_template(f'{template_name}.html.j2')
        return template.render(**data)

    def deliver_slack(self, report: str, channel: str):
        # Use existing Slack client
        pass

    def deliver_confluence(self, report: str, page_id: str):
        # Use existing Confluence client
        pass
```

---

## 3.5 FinOps Workflows

**Goal**: Automated cost optimization actions.

### New Commands

```bash
devctl ops finops schedule-instances [--tag Schedule=office-hours]
devctl ops finops stop-instances --tag TAG [--dry-run]
devctl ops finops start-instances --tag TAG [--dry-run]
devctl ops finops cleanup-snapshots [--older-than 90d] [--dry-run]
devctl ops finops cleanup-amis [--older-than 180d] [--dry-run]
devctl ops finops cleanup-volumes [--unattached] [--dry-run]
devctl ops finops cleanup-ips [--unassociated] [--dry-run]
devctl ops finops apply-rightsizing REC_ID [--dry-run]
devctl ops finops enforce-policies [--policy-file FILE]
devctl ops finops run [--workflow cleanup|schedule|optimize]
```

### New Files
- `src/devctl/commands/ops/finops.py`
- `src/devctl/commands/aws/scheduler.py`
- `src/devctl/workflows/templates/finops-cleanup-daily.yaml`
- `src/devctl/workflows/templates/finops-cleanup-weekly.yaml`
- `src/devctl/workflows/templates/finops-instance-schedule.yaml`

### Safety Guardrails

```python
PROTECTED_TAGS = ['DoNotDelete', 'Protected', 'Production']
MIN_RESOURCE_AGE_DAYS = 7

def is_protected(resource: dict) -> bool:
    tags = {t['Key']: t['Value'] for t in resource.get('Tags', [])}
    return any(tags.get(t) == 'true' for t in PROTECTED_TAGS)

@click.option('--dry-run', is_flag=True, default=True)
def cleanup_snapshots(dry_run: bool, older_than: str):
    """Clean old EBS snapshots."""
    if not dry_run:
        click.confirm('This will delete snapshots. Continue?', abort=True)
```

### Workflow Templates

```yaml
# finops-cleanup-weekly.yaml
name: weekly-cleanup
description: Weekly resource cleanup

steps:
  - name: Cleanup old snapshots
    command: ops finops cleanup-snapshots
    params:
      older_than: "90d"
      dry_run: "{{ dry_run | default(true) }}"

  - name: Cleanup unattached volumes
    command: ops finops cleanup-volumes
    params:
      unattached: true
      dry_run: "{{ dry_run | default(true) }}"

  - name: Cleanup unused IPs
    command: ops finops cleanup-ips
    params:
      unassociated: true
```

---

## Config Extensions

Add to `src/devctl/config.py`:

```python
class CostAllocationConfig(BaseModel):
    required_tags: list[str] = ["Team", "Project", "Environment"]
    tag_validation_rules: dict[str, str] = {}

class BudgetConfig(BaseModel):
    default_currency: str = "USD"
    alert_thresholds: list[int] = [50, 80, 100]
    forecast_months: int = 3
    slack_channel: str | None = None
    pagerduty_service: str | None = None

class FinOpsConfig(BaseModel):
    protected_tags: list[str] = ["DoNotDelete", "Protected"]
    min_resource_age_days: int = 7
    dry_run_by_default: bool = True
    schedule_timezone: str = "UTC"
```

---

## Implementation Order

1. **Cost Allocation & Tagging** - Foundation for other features
2. **Cost Attribution Reports** - Depends on #1 for tag-based reports
3. **Budget Alerts & Forecasting** - Medium effort, high value
4. **Cross-Service Optimization** - High effort, aggregates multiple APIs
5. **FinOps Workflows** - High effort, requires safety guardrails

## Key Integrations

- `src/devctl/commands/aws/cost.py` - Existing cost commands
- `src/devctl/commands/ops/cost_report.py` - Existing report patterns
- `src/devctl/clients/slack.py` - Alert delivery
- `src/devctl/workflows/engine.py` - FinOps workflow execution
