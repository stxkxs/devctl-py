# Bedrock AI

Operations for [Amazon Bedrock](https://aws.amazon.com/bedrock/) - managed foundation models, agents, and batch inference.

## Overview

devctl provides commands for:

- Invoking foundation models
- Managing Bedrock agents and knowledge bases
- Running batch inference jobs
- Comparing model responses
- Tracking usage and costs

## Prerequisites

| Requirement | Details |
|-------------|---------|
| AWS Region | Bedrock available regions (us-east-1, us-west-2, etc.) |
| Model Access | Request access in Bedrock console |
| IAM Permissions | `bedrock:*`, `bedrock-agent:*`, `bedrock-agent-runtime:*` |

### IAM Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:ListFoundationModels",
        "bedrock:GetFoundationModel",
        "bedrock:ListModelInvocationJobs",
        "bedrock:CreateModelInvocationJob",
        "bedrock:GetModelInvocationJob",
        "bedrock:StopModelInvocationJob"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "bedrock-agent:*",
        "bedrock-agent-runtime:*"
      ],
      "Resource": "*"
    }
  ]
}
```

## Commands Reference

### list-models

List available foundation models.

```bash
devctl aws bedrock list-models [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--provider` | Filter by provider (anthropic, amazon, meta, etc.) |
| `--output-modality` | Filter by output type (TEXT, IMAGE, EMBEDDING) |

```bash
# All models
devctl aws bedrock list-models

# Anthropic models only
devctl aws bedrock list-models --provider anthropic

# Text generation models
devctl aws bedrock list-models --output-modality TEXT
```

Output:

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Model ID                              ┃ Provider    ┃ Modalities               ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ anthropic.claude-3-5-sonnet-20241022  │ Anthropic   │ TEXT, IMAGE → TEXT       │
│ anthropic.claude-3-5-haiku-20241022   │ Anthropic   │ TEXT, IMAGE → TEXT       │
│ anthropic.claude-3-opus-20240229      │ Anthropic   │ TEXT, IMAGE → TEXT       │
│ anthropic.claude-3-sonnet-20240229    │ Anthropic   │ TEXT, IMAGE → TEXT       │
│ anthropic.claude-3-haiku-20240307     │ Anthropic   │ TEXT, IMAGE → TEXT       │
│ amazon.titan-text-express-v1          │ Amazon      │ TEXT → TEXT              │
│ meta.llama3-70b-instruct-v1:0         │ Meta        │ TEXT → TEXT              │
└───────────────────────────────────────┴─────────────┴──────────────────────────┘
```

### invoke

Invoke a foundation model.

```bash
devctl aws bedrock invoke MODEL_ID [OPTIONS]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--prompt` | Text prompt | Required |
| `--max-tokens` | Maximum tokens to generate | `1024` |
| `--temperature` | Sampling temperature | `0.7` |
| `--system` | System prompt | - |

```bash
# Simple invocation
devctl aws bedrock invoke anthropic.claude-3-haiku-20240307 \
  --prompt "Explain Kubernetes pods in one paragraph"

# With system prompt
devctl aws bedrock invoke anthropic.claude-3-sonnet-20240229 \
  --system "You are a DevOps expert. Be concise." \
  --prompt "What's the difference between StatefulSet and Deployment?"

# Control output length
devctl aws bedrock invoke anthropic.claude-3-haiku-20240307 \
  --prompt "List 5 AWS cost optimization tips" \
  --max-tokens 500
```

### usage

Show Bedrock usage statistics.

```bash
devctl aws bedrock usage [OPTIONS]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--days` | Number of days to analyze | `7` |

```bash
devctl aws bedrock usage --days 30
```

Output:

```
Bedrock Usage (Last 30 Days)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Model                               ┃ Input Tokens  ┃ Output Tokens  ┃ Cost     ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ anthropic.claude-3-sonnet           │ 1,250,000     │ 450,000        │ $12.75   │
│ anthropic.claude-3-haiku            │ 3,500,000     │ 1,200,000      │ $4.35    │
│ amazon.titan-embed-text             │ 5,000,000     │ -              │ $0.50    │
├─────────────────────────────────────┼───────────────┼────────────────┼──────────┤
│ Total                               │ 9,750,000     │ 1,650,000      │ $17.60   │
└─────────────────────────────────────┴───────────────┴────────────────┴──────────┘
```

### compare

Compare responses from multiple models.

```bash
devctl aws bedrock compare [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--models` | Comma-separated model IDs |
| `--prompt` | Prompt to send to all models |
| `--max-tokens` | Maximum tokens per response |

```bash
devctl aws bedrock compare \
  --models anthropic.claude-3-sonnet-20240229,anthropic.claude-3-haiku-20240307 \
  --prompt "Explain the CAP theorem in 2 sentences"
```

Output:

```
Model Comparison
━━━━━━━━━━━━━━━━

Prompt: Explain the CAP theorem in 2 sentences

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Model                          ┃ Response                                    ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ claude-3-sonnet                │ The CAP theorem states that a distributed   │
│                                │ system can only guarantee two of three      │
│                                │ properties: Consistency, Availability, and  │
│                                │ Partition tolerance. In practice, since     │
│                                │ network partitions are inevitable, systems  │
│                                │ must choose between consistency and         │
│                                │ availability during failures.               │
├────────────────────────────────┼─────────────────────────────────────────────┤
│ claude-3-haiku                 │ CAP theorem says distributed databases can  │
│                                │ only have 2 of 3: consistency, availability,│
│                                │ partition tolerance. Pick CP or AP based on │
│                                │ your needs.                                 │
└────────────────────────────────┴─────────────────────────────────────────────┘

Performance:
┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Model                ┃ Latency      ┃ Tokens        ┃ Est. Cost  ┃
┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ claude-3-sonnet      │ 2.3s         │ 89            │ $0.0004    │
│ claude-3-haiku       │ 0.8s         │ 42            │ $0.00005   │
└──────────────────────┴──────────────┴───────────────┴────────────┘
```

## Agents

Manage Bedrock Agents for complex task orchestration.

### agents list

List all agents.

```bash
devctl aws bedrock agents list
```

Output:

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Name                     ┃ Agent ID                                          ┃ Status     ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ DevOps Assistant         │ AGENT123456                                       │ PREPARED   │
│ Documentation Helper     │ AGENT789012                                       │ PREPARED   │
│ Incident Responder       │ AGENT345678                                       │ PREPARING  │
└──────────────────────────┴───────────────────────────────────────────────────┴────────────┘
```

### agents describe

Get agent details.

```bash
devctl aws bedrock agents describe AGENT_ID
```

### agents invoke

Invoke an agent.

```bash
devctl aws bedrock agents invoke AGENT_ID [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--prompt` | Input prompt for the agent |
| `--session-id` | Session ID for conversation continuity |

```bash
# Single invocation
devctl aws bedrock agents invoke AGENT123456 \
  --prompt "What's the current status of the production cluster?"

# Continue conversation
devctl aws bedrock agents invoke AGENT123456 \
  --prompt "Show me the last 5 deployments" \
  --session-id "session-abc123"
```

### agents knowledge-bases

List knowledge bases for an agent.

```bash
devctl aws bedrock agents knowledge-bases AGENT_ID
```

## Batch Inference

Run inference jobs on large datasets.

### batch list

List batch inference jobs.

```bash
devctl aws bedrock batch list [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--status` | Filter by status (Submitted, InProgress, Completed, Failed) |

```bash
# All jobs
devctl aws bedrock batch list

# Only running jobs
devctl aws bedrock batch list --status InProgress
```

Output:

```
┏━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Job Name               ┃ Model                     ┃ Status      ┃ Created     ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ embeddings-batch-001   │ amazon.titan-embed-text   │ Completed   │ 2024-01-15  │
│ summarize-docs-002     │ anthropic.claude-3-haiku  │ InProgress  │ 2024-01-16  │
│ classify-tickets-003   │ anthropic.claude-3-sonnet │ Submitted   │ 2024-01-16  │
└────────────────────────┴───────────────────────────┴─────────────┴─────────────┘
```

### batch submit

Submit a batch inference job.

```bash
devctl aws bedrock batch submit [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--name` | Job name |
| `--model` | Model ID |
| `--input-s3` | S3 URI for input JSONL |
| `--output-s3` | S3 URI for output |
| `--role` | IAM role ARN |

```bash
devctl aws bedrock batch submit \
  --name embeddings-batch \
  --model amazon.titan-embed-text-v1 \
  --input-s3 s3://my-bucket/batch/input.jsonl \
  --output-s3 s3://my-bucket/batch/output/ \
  --role arn:aws:iam::123456789012:role/BedrockBatchRole
```

Input JSONL format:

```jsonl
{"recordId": "1", "modelInput": {"inputText": "Document text 1"}}
{"recordId": "2", "modelInput": {"inputText": "Document text 2"}}
{"recordId": "3", "modelInput": {"inputText": "Document text 3"}}
```

### batch status

Check job status.

```bash
devctl aws bedrock batch status JOB_ARN
```

### batch stop

Stop a running job.

```bash
devctl aws bedrock batch stop JOB_ARN
```

## Model Pricing Reference

Approximate pricing (verify current rates in AWS console):

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------------------|------------------------|
| Claude 3.5 Sonnet | $3.00 | $15.00 |
| Claude 3.5 Haiku | $0.25 | $1.25 |
| Claude 3 Opus | $15.00 | $75.00 |
| Claude 3 Sonnet | $3.00 | $15.00 |
| Claude 3 Haiku | $0.25 | $1.25 |
| Titan Text Express | $0.20 | $0.60 |
| Titan Embeddings | $0.10 | - |
| Llama 3 70B | $2.65 | $3.50 |

## Use Cases

### DevOps Documentation Generation

```bash
# Generate runbook from code
devctl aws bedrock invoke anthropic.claude-3-sonnet-20240229 \
  --system "You are a technical writer. Create concise runbooks." \
  --prompt "$(cat deployment.yaml)" \
  --max-tokens 2000
```

### Incident Analysis

```bash
# Analyze logs for root cause
devctl aws bedrock invoke anthropic.claude-3-sonnet-20240229 \
  --system "You are an SRE. Analyze logs and identify root causes." \
  --prompt "Analyze these error logs: $(tail -100 /var/log/app/error.log)"
```

### Cost Optimization Recommendations

```bash
# Get AI-powered cost recommendations
COST_DATA=$(devctl -o json aws cost by-service --days 30)
devctl aws bedrock invoke anthropic.claude-3-sonnet-20240229 \
  --system "You are a FinOps expert. Analyze AWS costs and recommend optimizations." \
  --prompt "Analyze this cost data and provide 5 specific recommendations: $COST_DATA"
```

### Batch Embeddings for Documentation Search

```bash
# Prepare input
cat docs/*.md | jq -Rs '{recordId: "doc", modelInput: {inputText: .}}' > input.jsonl

# Submit batch job
devctl aws bedrock batch submit \
  --name docs-embeddings \
  --model amazon.titan-embed-text-v1 \
  --input-s3 s3://my-bucket/embeddings/input.jsonl \
  --output-s3 s3://my-bucket/embeddings/output/
```

## Best Practices

1. **Use Haiku for simple tasks** - Faster and cheaper for straightforward queries
2. **Use Sonnet for complex analysis** - Better reasoning for technical problems
3. **Batch similar requests** - Use batch inference for large datasets
4. **Set appropriate max_tokens** - Don't over-allocate output tokens
5. **Use system prompts** - Improve consistency with clear instructions
6. **Monitor usage** - Track costs with `devctl aws bedrock usage`

## Troubleshooting

### Model access denied

```bash
# Check if model is enabled
aws bedrock list-foundation-models --query 'modelSummaries[?modelId==`anthropic.claude-3-sonnet-20240229`]'

# Request access in console if needed
# AWS Console → Bedrock → Model access → Request access
```

### Throttling errors

```bash
# Check current quotas
aws service-quotas get-service-quota \
  --service-code bedrock \
  --quota-code L-XXXXX

# Request quota increase if needed
```

### Agent not responding

```bash
# Check agent status
devctl aws bedrock agents describe AGENT_ID

# Verify agent is in PREPARED state
# If PREPARING, wait for completion
# If FAILED, check agent configuration
```

## Related Documentation

- [Amazon Bedrock User Guide](https://docs.aws.amazon.com/bedrock/latest/userguide/)
- [Bedrock Agents](https://docs.aws.amazon.com/bedrock/latest/userguide/agents.html)
- [Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/)
- [AWS Commands](aws-commands.md) - Other AWS operations
