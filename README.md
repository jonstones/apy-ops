# apy-ops

A Python-based Azure API Management deployment tool that uses a **Terraform-style plan & apply** workflow. Reads the [APIOps](https://github.com/Azure/apiops) git-extracted format and deploys artifacts via Azure REST API, using an external state file to track deployments and produce minimal diffs.

## Prerequisites

- Python 3.10+
- An Azure APIM instance
- Azure credentials (`az login` or a service principal)

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# For development (includes pytest)
pip install -e ".[dev]"
```

## Quick Start

### 1. Initialize state

State tracks what was last deployed. All parameters are optional at init — APIM connection details can be provided later via flags or env vars.

```bash
# Minimal — creates .apim-state.json in current directory
apy-ops init

# With APIM details (stored in state for later use by apply/extract)
apy-ops init --subscription-id <SUB> --resource-group <RG> --service-name <APIM>

# Custom state file location
apy-ops init --state-file ~/.apim-state/myproject/apim-state.json

# Azure Blob Storage backend (for pipelines/teams)
apy-ops init --backend azure \
  --backend-storage-account <SA> \
  --backend-container apim-state \
  --backend-blob myproject/apim-state.json
```

### 2. Plan

Compare local APIOps files against the state file. Entirely offline — no APIM connection needed.

```bash
# Minimal — reads from current dir, uses .apim-state.json
apy-ops plan

# Explicit source directory
apy-ops plan --source-dir ./api-management

# Save plan for later
apy-ops plan --out plan.json

# Show unchanged artifacts too
apy-ops plan -v
```

Output:
```
Plan: 2 to create, 1 to update, 0 to delete, 5 unchanged.

  + api          "Weather API"       (new)
  + named_value  "api-key"           (new)
  ~ product      "Starter"           (changed: subscriptionsLimit 1→5)
```

### 3. Apply

Push changes to APIM. Requires APIM connection details (from flags, env vars, or state file).

```bash
# If APIM details were set during init or via env vars
apy-ops apply

# With explicit APIM target
apy-ops apply --subscription-id <SUB> --resource-group <RG> --service-name <APIM>

# Apply a saved plan
apy-ops apply --plan plan.json

# Skip confirmation (for CI/CD)
apy-ops apply --auto-approve

# Force-push all artifacts, ignoring state
apy-ops apply --force
```

### 4. Extract

Pull all artifacts from a live APIM instance into APIOps-format files.

```bash
# Minimal — writes to ./api-management, resolves APIM target from state/env
apy-ops extract

# Explicit options
apy-ops extract --output-dir ./my-apis \
  --subscription-id <SUB> --resource-group <RG> --service-name <APIM>

# Sync state file so subsequent plan shows no changes
apy-ops extract --update-state
```

## Defaults

Most parameters have sensible defaults so you can run commands with minimal flags:

| Parameter | Default | Notes |
|---|---|---|
| `--backend` | `local` | |
| `--state-file` | `.apim-state.json` | Current directory |
| `--source-dir` | `.` | Current directory |
| `--output-dir` | `./api-management` | For extract |
| `--subscription-id` | from state file | Fallback: `APIM_SUBSCRIPTION_ID` env var |
| `--resource-group` | from state file | Fallback: `APIM_RESOURCE_GROUP` env var |
| `--service-name` | from state file | Fallback: `APIM_SERVICE_NAME` env var |

APIM connection details are resolved in order: CLI flag → environment variable → state file. They are only required for commands that talk to APIM (`apply`, `extract`). `plan` is entirely offline.

## Authentication

By default, uses `DefaultAzureCredential` (works with `az login`, managed identity, etc.).

For service principal auth:
```bash
apy-ops apply --client-id <CLIENT_ID> --client-secret <CLIENT_SECRET> --tenant-id <TENANT_ID>
```

## Filtering

Deploy or extract only specific artifact types:

```bash
apy-ops plan --only apis
apy-ops extract --only apis,products
```

## Environment Variables

| Variable | Equivalent flag |
|---|---|
| `APIM_SUBSCRIPTION_ID` | `--subscription-id` |
| `APIM_RESOURCE_GROUP` | `--resource-group` |
| `APIM_SERVICE_NAME` | `--service-name` |
| `APIM_STATE_BACKEND` | `--backend` |
| `APIM_STATE_FILE` | `--state-file` |
| `APIM_STATE_STORAGE_ACCOUNT` | `--backend-storage-account` |
| `APIM_STATE_CONTAINER` | `--backend-container` |
| `APIM_STATE_BLOB` | `--backend-blob` |

## Troubleshooting

**Stuck lock**: If a previous run crashed and left the state locked:
```bash
apy-ops force-unlock
```

**State drift**: If someone made manual changes on APIM, use `--force` to push all local artifacts and rebuild state from scratch.

**Partial failure**: If `apply` fails mid-way, the state file reflects what actually succeeded. Re-run `plan` to see what remains, then `apply` again.
