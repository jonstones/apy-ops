# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Clean Python-based Azure APIM deployment tool that reads the APIOps git-extracted format and deploys APIM artifacts via Azure REST API using a **Terraform-style plan & apply** workflow. Uses an external **state file** (Azure Blob Storage or local file) to track what was last deployed, producing a delta of only the changes needed.

## Project Structure

```
claude-apiops/
├── deploy.py              # CLI entry point: plan, apply, init, extract
├── apim_client.py         # Azure REST API client (auth + HTTP)
├── artifact_reader.py     # Reads APIOps directory, resolves $ref-*, computes hashes
├── state.py               # State backend: Azure Blob Storage + local file, with locking
├── differ.py              # Diff local artifacts vs state → list of changes
├── planner.py             # Orchestrates plan generation
├── applier.py             # Executes plan against APIM REST API, updates state
├── extractor.py           # Extracts all artifacts from live APIM, writes APIOps files
├── artifacts/             # Per-artifact-type deploy logic
│   ├── __init__.py        # DEPLOY_ORDER list, artifact type registry
│   ├── named_values.py
│   ├── gateways.py
│   ├── tags.py
│   ├── version_sets.py
│   ├── backends.py
│   ├── loggers.py
│   ├── diagnostics.py
│   ├── policy_fragments.py
│   ├── service_policy.py  # Global policy
│   ├── products.py
│   ├── groups.py
│   ├── apis.py            # APIs + operations (atomic unit)
│   ├── subscriptions.py
│   ├── api_policies.py
│   ├── api_tags.py
│   ├── api_diagnostics.py
│   ├── gateway_apis.py
│   ├── product_policies.py
│   ├── product_groups.py
│   ├── product_tags.py
│   ├── product_apis.py
│   └── api_operation_policies.py
└── requirements.txt       # azure-identity, azure-storage-blob, requests
```

## Commands

```bash
pip install -r requirements.txt

# Initialize empty state
python deploy.py init \
  --backend local --state-file ~/.apim-state/myproject/apim-state.json
# or
python deploy.py init \
  --backend azure --backend-storage-account SA --backend-container apim-state --backend-blob myproject/apim-state.json

# Plan: diff local artifacts against state file, show delta
python deploy.py plan \
  --source-dir /path/to/api-management \
  --subscription-id SUB --resource-group RG --service-name APIM \
  --backend local --state-file ~/.apim-state/myproject/apim-state.json

# Plan with saved output
python deploy.py plan ... --out plan.json

# Apply: execute changes, update state
python deploy.py apply \
  --source-dir /path/to/api-management \
  --subscription-id SUB --resource-group RG --service-name APIM \
  --backend local --state-file ~/.apim-state/myproject/apim-state.json

# Apply a saved plan
python deploy.py apply --plan plan.json ...

# Force: bypass state diff, push ALL artifacts, rebuild state
python deploy.py apply --force ...

# Auto-approve (skip confirmation, for CI/CD pipelines)
python deploy.py apply --auto-approve ...

# Deploy specific artifact type only
python deploy.py plan --only apis ...

# Extract: pull all artifacts from live APIM into APIOps-format files
python deploy.py extract \
  --subscription-id SUB --resource-group RG --service-name APIM \
  --output-dir ./api-management

# Extract specific types only
python deploy.py extract ... --only apis,products,policies

# Extract and populate state file (so subsequent plan shows no changes)
python deploy.py extract ... --update-state \
  --backend local --state-file ~/.apim-state/myproject/apim-state.json

# Service principal auth
python deploy.py plan ... --client-id CID --client-secret SEC --tenant-id TID
```

## Architecture

### Plan & Apply Workflow (State-File Based)

```
┌─────────────┐     ┌──────────────┐     ┌───────────┐
│ Local Files  │     │  State File  │     │           │
│ (APIOps git) │     │ (Blob/Local) │     │   Plan    │
└──────┬───────┘     └──────┬───────┘     │  Output   │
       │                    │             │           │
       ▼                    ▼             │  + create │
  ┌─────────┐        ┌───────────┐       │  ~ update │
  │ Desired  │        │   Last    │       │  - delete │
  │  State   │──diff──│ Deployed  │──────►│  . no-op  │
  └─────────┘        └───────────┘       └─────┬─────┘
                                               │
                                          apply │ (with confirmation)
                                               ▼
                                        ┌───────────┐
                                        │  PUT/DEL   │
                                        │  REST API  │
                                        └─────┬─────┘
                                               │
                                          update state file
```

Plan compares local artifacts (hashed) against the state file — no APIM API calls needed for plan.
Apply pushes changes to APIM REST API, then updates the state file after each success.

### State Storage (Two Backends)

State is stored **externally** to the config repo so it survives repo reverts.

**Azure Blob Storage** (pipelines/team): `--backend azure` with storage account, container, blob path.
Locking via blob lease (60s, auto-renewed). `--force-unlock` for stuck leases.

**Local File** (dev/testing): `--backend local` with `--state-file` path.
Locking via `.lock` file.

Environment variables supported: `APIM_STATE_BACKEND`, `APIM_STATE_STORAGE_ACCOUNT`, `APIM_STATE_CONTAINER`, `APIM_STATE_BLOB`, `APIM_STATE_FILE`.

### State File Format
```json
{
  "version": 1,
  "apim_service": "my-apim-instance",
  "resource_group": "my-rg",
  "subscription_id": "xxx",
  "last_applied": "2025-02-14T10:30:00Z",
  "artifacts": {
    "named_value:my-secret": {
      "type": "named_value", "id": "my-secret",
      "hash": "sha256:abc123...",
      "properties": { "displayName": "my-secret", "secret": true, "keyVault": { "..." : "..." } }
    },
    "api:echo-api": {
      "type": "api", "id": "echo-api",
      "hash": "sha256:def456...",
      "properties": { "displayName": "Echo API", "path": "echo", "..." : "..." }
    }
  }
}
```

### Multi-Project Support
Multiple projects manage different slices of the same APIM instance via separate state blobs:
```
apim-state/project-a/apim-state.json  → APIs: payments, orders
apim-state/project-b/apim-state.json  → APIs: auth, users
```

### Authentication
- `DefaultAzureCredential` for `az login` / managed identity (default)
- `ClientSecretCredential` when `--client-id`, `--client-secret`, `--tenant-id` provided
- Token scope: `https://management.azure.com/.default`

### REST Client (`apim_client.py`)
- Base: `https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.ApiManagement/service/{svc}`
- API version: `2024-05-01`
- Methods: `get(path)`, `put(path, body)`, `delete(path)`
- Retry with exponential backoff on 429 (rate limit)

### Artifact Reader (`artifact_reader.py`)
Reads the APIOps git-extracted directory. Resolves cross-references:
- `$ref-policy` → XML policy file content
- `$ref-description` / `$ref-body` → HTML file content
- `$refs-groups` / `$refs-apis` → array of referenced artifact IDs
- `$ref-Original`, `$ref-Production`, `$ref-Preview` → portal template/style content

Computes SHA256 hash of normalized properties per artifact for state comparison.

### Differ (`differ.py`)
Compares local artifact hashes against state file:
- **CREATE**: in local, not in state
- **UPDATE**: in both, hash differs (shows property-level diff)
- **DELETE**: in state, not in local
- **NO-OP**: in both, hash matches

### Plan Output (console)
```
Plan: 2 to create, 3 to update, 0 to delete, 15 unchanged.

  + api          "Weather API"           (new)
  + operation    "GET /forecast"         (new, in Weather API)
  ~ product      "Starter"              (changed: subscriptionsLimit 1→5)
  ~ policy       "global"               (changed: added rate-limit)
  ~ policy       "Starter (product)"    (changed: quota renewal-period)
  . api          "Echo API"             (unchanged)
  . group        "Developers"           (unchanged, built-in)
```

## Artifact Deployment Order (from APIOps source)

### Creates/Updates (dependency order)
1. Named Values → 2. Gateways → 3. Tags → 4. Version Sets → 5. Backends → 6. Loggers → 7. Diagnostics → 8. Policy Fragments → 9. Service Policy (global) → 10. Products → 11. Groups → 12. APIs → 13. Subscriptions → 14. API Policies → 15. API Tags → 16. API Diagnostics → 17. Gateway APIs → 18. Product Policies → 19. Product Groups → 20. Product Tags → 21. Product APIs → 22. API Operation Policies

### Deletions (reverse order)
22→21→20→...→1. Associations/policies deleted before parent resources to maintain referential integrity.

## API Deployment: Atomic Unit

Each API is deployed as an **atomic unit** — if any part changes, ALL parts are redeployed:

1. **apiInformation.json** (or `configuration.json` in older APIOps format) — metadata
2. **Specification file** (one of): `specification.json`, `specification.yaml`, `specification.wsdl`, `specification.wadl`, `specification.graphql`
3. **All operations** — method, urlTemplate, request, responses
4. **Operation descriptions** — HTML files via `$ref-description`

The spec and apiInformation can hold overriding information — both must always be pushed together.

**No format conversion**: specs are sent to APIM as-is. If APIM rejects the format, the apply stops and the developer fixes the source file.

**OpenAPI format mapping** for REST API `format` field:
- JSON v2 (Swagger) → `swagger-json`
- JSON v3 → `openapi+json`
- YAML v2 → `swagger-link-json`
- YAML v3 → `openapi`
- WSDL → `wsdl`, WADL → `wadl`, GraphQL → `graphql`

**Hash scope**: covers ALL associated files. Any file change triggers full API redeploy.

**Format support**: both old (`configuration.json` with inline operations) and new (`apiInformation.json` + separate spec file) APIOps formats.

## Secrets Handling

Named values that are secrets use **Azure Key Vault references** natively. The config file contains the Key Vault secret URI; APIM resolves it at runtime. No secrets flow through the deployment tool.

```json
{
  "displayName": "api-key",
  "secret": true,
  "keyVault": {
    "secretIdentifier": "https://my-keyvault.vault.azure.net/secrets/api-key"
  }
}
```

## Error Handling & Partial Deployments

**Strategy: Stop on first failure + partial state (Terraform-style)**

1. Apply changes in dependency order
2. After each successful change: update state immediately (flush to backend)
3. On first failure: **stop**, log error, report what succeeded and what remains
4. State file accurately reflects what's actually deployed on APIM

**Recovery path:**
- Revert the PR in the config repo
- State file (external to repo) still reflects what was actually deployed
- Re-run `plan` — shows delta between reverted config and partially-applied state
- Run `apply` — brings APIM back to the desired state

**Force mode** (`--force`): bypasses state diff, pushes ALL local artifacts to APIM, rebuilds state from scratch. Use when manual changes on APIM have made the state file stale.

**Console output on failure:**
```
Applying changes...
  [1/8] + named_value "api-key"              ✓
  [2/8] + backend "payment-service"          ✓
  [3/8] + api "payment-api"                  ✗ ERROR: 400 Bad Request
         → "The API path 'payments' conflicts with existing API 'legacy-payments'"

Apply failed. 2 of 8 changes applied successfully.
State file updated. Re-run 'plan' to see remaining changes.
```

## Extract Command

`extract` pulls all artifacts from a live APIM instance and writes them as APIOps-format files.

1. Calls `read_live(client)` on each artifact module (in deployment order)
2. Calls `write_local(output_dir, artifacts)` to write APIOps-format files
3. Optionally updates state file to match extracted state (`--update-state`)

**Use cases:**
- Bootstrap a new project from existing APIM
- Audit: compare extracted files against repo to detect manual drift
- Migration: extract from one APIM, apply to another

## Per-Artifact Modules (`artifacts/*.py`)

Each module exports the full CRUD interface:
- `read_local(source_dir) → dict[key, artifact]` — parse from APIOps files on disk
- `read_live(client) → dict[key, artifact]` — GET/LIST from APIM REST API
- `write_local(output_dir, artifacts)` — write APIOps-format files to disk (for extract)
- `to_rest_payload(artifact) → dict` — Azure REST API PUT body (for apply)
- `resource_path(id) → str` — REST path segment for this artifact

Key REST patterns:

| Artifact | REST Path | Create/Update | Delete |
|----------|-----------|---------------|--------|
| API | `/apis/{apiId}` | PUT | DELETE |
| Operation | `/apis/{apiId}/operations/{opId}` | PUT | DELETE |
| Product | `/products/{productId}` | PUT | DELETE |
| Product-Group | `/products/{pid}/groups/{gid}` | PUT | DELETE |
| Product-API | `/products/{pid}/apis/{aid}` | PUT | DELETE |
| Policy (global) | `/policies/policy` | PUT | DELETE |
| Policy (product) | `/products/{id}/policies/policy` | PUT | DELETE |
| Policy (API) | `/apis/{id}/policies/policy` | PUT | DELETE |
| Policy (op) | `/apis/{id}/operations/{opId}/policies/policy` | PUT | DELETE |
| Group | `/groups/{groupId}` | PUT | DELETE |
| Named Value | `/namedValues/{id}` | PUT | DELETE |
| Backend | `/backends/{id}` | PUT | DELETE |
| Gateway | `/gateways/{id}` | PUT | DELETE |
| Gateway-API | `/gateways/{gid}/apis/{aid}` | PUT | DELETE |
| Tag | `/tags/{tagId}` | PUT | DELETE |
| API-Tag | `/apis/{aid}/tags/{tid}` | PUT | DELETE |
| Product-Tag | `/products/{pid}/tags/{tid}` | PUT | DELETE |
| Version Set | `/apiVersionSets/{id}` | PUT | DELETE |
| Logger | `/loggers/{id}` | PUT | DELETE |
| Diagnostic | `/diagnostics/{id}` | PUT | DELETE |
| API-Diagnostic | `/apis/{aid}/diagnostics/{did}` | PUT | DELETE |
| Policy Fragment | `/policyFragments/{id}` | PUT | DELETE |
| Subscription | `/subscriptions/{id}` | PUT | DELETE |

## APIOps Naming Conventions
- API dirs: `[DisplayName]__[Version]_[InternalId]-[HASH]`
- Operation files: `[METHOD]__[urlTemplate]_[operationId]-[HASH].[ext]`
- API ID extracted from `configuration.json` → `"id": "/apis/echo-api"` → `echo-api`
- Product ID from `"id": "/products/starter"` → `starter`
- Operation ID from `"id": "/apis/echo-api/operations/create-resource"` → `create-resource`

## Future Scope (not in v1)
- API revisions
- OAuth2 authorization servers
- OpenID Connect providers
- Workspace artifacts
