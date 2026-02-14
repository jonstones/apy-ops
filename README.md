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
pip install -r requirements.txt
```

## Quick Start

### 1. Initialize state

State tracks what was last deployed. Choose a backend:

```bash
# Local file (for dev/testing)
python deploy.py init \
  --backend local \
  --state-file ~/.apim-state/myproject/apim-state.json \
  --subscription-id <SUB> --resource-group <RG> --service-name <APIM>

# Azure Blob Storage (for pipelines/teams)
python deploy.py init \
  --backend azure \
  --backend-storage-account <SA> \
  --backend-container apim-state \
  --backend-blob myproject/apim-state.json \
  --subscription-id <SUB> --resource-group <RG> --service-name <APIM>
```

### 2. Plan

Compare your local APIOps files against the state file to see what would change. No calls are made to APIM.

```bash
python deploy.py plan \
  --source-dir ./api-management \
  --subscription-id <SUB> --resource-group <RG> --service-name <APIM> \
  --backend local --state-file ~/.apim-state/myproject/apim-state.json
```

Output:
```
Plan: 2 to create, 1 to update, 0 to delete, 5 unchanged.

  + api          "Weather API"       (new)
  + named_value  "api-key"           (new)
  ~ product      "Starter"           (changed: subscriptionsLimit 1→5)
```

Save a plan for later:
```bash
python deploy.py plan ... --out plan.json
```

### 3. Apply

Push changes to APIM. You'll be prompted to confirm.

```bash
python deploy.py apply \
  --source-dir ./api-management \
  --subscription-id <SUB> --resource-group <RG> --service-name <APIM> \
  --backend local --state-file ~/.apim-state/myproject/apim-state.json
```

Apply a saved plan:
```bash
python deploy.py apply --plan plan.json \
  --subscription-id <SUB> --resource-group <RG> --service-name <APIM> \
  --backend local --state-file ~/.apim-state/myproject/apim-state.json
```

Skip the confirmation prompt (for CI/CD):
```bash
python deploy.py apply --auto-approve ...
```

Force-push all artifacts, ignoring state (useful when APIM was changed manually):
```bash
python deploy.py apply --force ...
```

### 4. Extract

Pull all artifacts from a live APIM instance into APIOps-format files:

```bash
python deploy.py extract \
  --subscription-id <SUB> --resource-group <RG> --service-name <APIM> \
  --output-dir ./api-management
```

Extract and sync the state file so a subsequent `plan` shows no changes:
```bash
python deploy.py extract --update-state \
  --backend local --state-file ~/.apim-state/myproject/apim-state.json \
  --subscription-id <SUB> --resource-group <RG> --service-name <APIM> \
  --output-dir ./api-management
```

## Authentication

By default, uses `DefaultAzureCredential` (works with `az login`, managed identity, etc.).

For service principal auth, pass credentials explicitly:
```bash
python deploy.py plan ... \
  --client-id <CLIENT_ID> \
  --client-secret <CLIENT_SECRET> \
  --tenant-id <TENANT_ID>
```

## Filtering

Deploy or extract only specific artifact types:

```bash
python deploy.py plan --only apis ...
python deploy.py extract --only apis,products ...
```

## Environment Variables

State backend settings can be set via environment variables instead of CLI flags:

| Variable | Equivalent flag |
|----------|----------------|
| `APIM_STATE_BACKEND` | `--backend` |
| `APIM_STATE_FILE` | `--state-file` |
| `APIM_STATE_STORAGE_ACCOUNT` | `--backend-storage-account` |
| `APIM_STATE_CONTAINER` | `--backend-container` |
| `APIM_STATE_BLOB` | `--backend-blob` |

## Troubleshooting

**Stuck lock**: If a previous run crashed and left the state locked:
```bash
python deploy.py force-unlock --backend local --state-file ~/.apim-state/myproject/apim-state.json
```

**State drift**: If someone made manual changes on APIM, use `--force` to push all local artifacts and rebuild state from scratch.

**Partial failure**: If `apply` fails mid-way, the state file reflects what actually succeeded. Re-run `plan` to see what remains, then `apply` again.
