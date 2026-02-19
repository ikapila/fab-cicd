# Azure DevOps Setup Guide for Fabric CI/CD

Complete guide to setting up automated Microsoft Fabric artifact deployment using Azure DevOps Pipelines.

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Repository Structure](#repository-structure)
4. [Step 1: Create Azure AD App Registrations (Service Principals)](#step-1-create-azure-ad-app-registrations)
5. [Step 2: Grant Fabric Workspace Permissions](#step-2-grant-fabric-workspace-permissions)
6. [Step 3: Set Up Azure DevOps Project](#step-3-set-up-azure-devops-project)
7. [Step 4: Configure Pipeline Variables](#step-4-configure-pipeline-variables)
8. [Step 5: Configure Environment Files](#step-5-configure-environment-files)
9. [Step 6: Configure Fabric Connections (Optional)](#step-6-configure-fabric-connections)
10. [Step 7: Create Pipeline Environments with Approvals](#step-7-create-pipeline-environments-with-approvals)
11. [Step 8: Create the Pipeline](#step-8-create-the-pipeline)
12. [Step 9: Branch Strategy](#step-9-branch-strategy)
13. [Step 10: Run Your First Deployment](#step-10-run-your-first-deployment)
14. [Supported Artifact Types](#supported-artifact-types)
15. [How Change Detection Works](#how-change-detection-works)
16. [Troubleshooting](#troubleshooting)

---

## Overview

This pipeline deploys Microsoft Fabric artifacts (notebooks, semantic models, lakehouses, reports, variable libraries, SQL views, and more) from an Azure DevOps Git repository to Fabric workspaces. It supports:

- **Three environments**: Dev → UAT → Production
- **Per-environment service principals** for secure, isolated access
- **Automatic change detection** — only modified artifacts are deployed (saves ~80% deployment time)
- **Dependency-aware ordering** — deploys lakehouses before semantic models, models before reports, etc.
- **Git-integrated source control sync** — syncs the Fabric workspace from its connected Git branch
- **Post-deploy semantic model refresh** — triggers a refresh after deploying semantic models
- **Paginated report connection binding** — configures ShareableCloud connections after deployment

### Pipeline Flow

```
Push to branch → Build & Validate → Deploy to environment → Update source control → Post-deploy steps
                                                                                      ├── Semantic model refresh
                                                                                      ├── Connection binding
                                                                                      └── Save deployment state
```

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| Azure DevOps | Project with Repos and Pipelines enabled |
| Microsoft Fabric | One workspace per environment (Dev, UAT, Prod) |
| Azure AD | Permissions to create App Registrations |
| Fabric Admin | Admin or Member role on target workspaces |
| Fabric Capacity | F64 or above (for API access); or P1 for Power BI Premium |

---

## Repository Structure

Your repository should follow this layout:

```
├── azure-pipelines.yml          # Pipeline definition
├── config/
│   ├── dev.json                 # Dev environment config
│   ├── uat.json                 # UAT environment config
│   └── prod.json                # Prod environment config
├── scripts/
│   ├── deploy_artifacts.py      # Main deployment orchestrator
│   ├── fabric_auth.py           # Authentication module
│   ├── fabric_client.py         # Fabric REST API client
│   ├── config_manager.py        # Config file loader
│   ├── dependency_resolver.py   # Deployment order resolver
│   ├── change_detector.py       # Git-based change detection
│   ├── validate_artifacts.py    # Artifact validation
│   ├── validate_notebooks.py    # Notebook syntax validation
│   ├── validate_pipelines.py    # Pipeline definition validation
│   └── requirements.txt         # Python dependencies
├── wsartifacts/                  # Fabric artifact definitions
│   ├── Notebooks/
│   ├── Semanticmodels/
│   ├── Reports/
│   ├── Lakehouses/
│   ├── Datapipelines/
│   ├── Environments/
│   ├── Variablelibraries/
│   ├── Paginatedreports/
│   ├── Sparkjobdefinitions/
│   └── Views/
└── .deployment_tracking/         # Auto-generated, tracks last deployed commit
```

> **Note:** The `wsartifacts/` folder name is configurable via `artifacts_root_folder` in each config JSON.

---

## Step 1: Create Azure AD App Registrations

Create one service principal (App Registration) **per environment** for security isolation.

### 1.1 Create the App Registrations

In the [Azure Portal](https://portal.azure.com) → **Azure Active Directory** → **App registrations** → **New registration**:

| Setting | Dev SP | UAT SP | Prod SP |
|---------|--------|--------|---------|
| Name | `FabricCI-Dev` | `FabricCI-UAT` | `FabricCI-Prod` |
| Supported account types | Single tenant | Single tenant | Single tenant |
| Redirect URI | (leave blank) | (leave blank) | (leave blank) |

### 1.2 Create Client Secrets

For each App Registration:

1. Go to **Certificates & secrets** → **New client secret**
2. Set a meaningful description (e.g., `AzDO Pipeline - Dev`)
3. Set expiry (recommended: 12 months; set a calendar reminder to rotate)
4. **Copy the secret value immediately** — it is only shown once

### 1.3 Record the Values

For each SP, note down:

| Value | Where to find it |
|-------|------------------|
| **Application (Client) ID** | App Registration → Overview |
| **Directory (Tenant) ID** | App Registration → Overview (same for all SPs) |
| **Client Secret** | Created in step 1.2 |

### 1.4 API Permissions

For each App Registration, add the following API permissions:

1. Go to **API permissions** → **Add a permission** → **APIs my organization uses**
2. Search for **Power BI Service** → **Delegated permissions**:
   - `Workspace.ReadWrite.All`
   - `Dataset.ReadWrite.All`
   - `Report.ReadWrite.All`
   - `Content.Create`
3. Search for **Microsoft Fabric** (or use the Application ID):
   - `Workspace.ReadWrite.All`
   - `Workspace.GitUpdate.All` (required for Git sync)
   - `Item.ReadWrite.All`
   - `Connection.ReadWrite.All`
4. Click **Grant admin consent** (requires Azure AD admin)

> **Alternative:** If you cannot grant admin consent, the SP must be added as a **Workspace Admin** (not just Member) and the Fabric tenant admin must enable "Service principals can use Fabric APIs" in the Admin portal.

### 1.5 Enable Fabric API Access for Service Principals

In the [Fabric Admin Portal](https://app.fabric.microsoft.com/admin-portal):

1. Go to **Tenant settings** → **Developer settings**
2. Enable **Service principals can use Fabric APIs**
3. Set to **Specific security groups** and add a group containing your SPs
4. Enable **Service principals can access read-only admin APIs** (optional, for monitoring)

---

## Step 2: Grant Fabric Workspace Permissions

For each environment workspace, add the corresponding service principal:

1. Open the Fabric workspace (e.g., `DataEng-Dev`)
2. Click **Manage access** (gear icon or ⋯ menu)
3. Add the service principal by entering its **Application (Client) ID** or name
4. Assign the **Admin** role (required for Git sync, connection binding, and TakeOver operations)

Repeat for each workspace-SP pair:

| Workspace | Service Principal | Role |
|-----------|-------------------|------|
| `DataEng-Dev` | `FabricCI-Dev` | Admin |
| `DataEng-UAT` | `FabricCI-UAT` | Admin |
| `DataEng-Prod` | `FabricCI-Prod` | Admin |

---

## Step 3: Set Up Azure DevOps Project

### 3.1 Create or Use Existing Project

1. Go to [dev.azure.com](https://dev.azure.com)
2. Create a new project or use an existing one
3. Initialize a Git repository (or import from GitHub)

### 3.2 Push Your Code

```bash
git remote add origin https://dev.azure.com/{org}/{project}/_git/{repo}
git push -u origin main
```

### 3.3 Create Branches

The pipeline triggers on three branches:

```bash
git checkout -b dev
git push -u origin dev

git checkout -b uat
git push -u origin uat

# 'main' is the production branch (already exists)
```

---

## Step 4: Configure Pipeline Variables

### 4.1 Create a Variable Group (Recommended)

In Azure DevOps → **Pipelines** → **Library** → **+ Variable group**:

| Variable | Value | Secret? |
|----------|-------|---------|
| `AZURE_TENANT_ID` | Your Azure AD Tenant ID | No |
| `AZURE_CLIENT_ID_DEV` | Dev SP Application (Client) ID | No |
| `AZURE_CLIENT_ID_UAT` | UAT SP Application (Client) ID | No |
| `AZURE_CLIENT_ID_PROD` | Prod SP Application (Client) ID | No |
| `AZURE_CLIENT_SECRET_DEV` | Dev SP Client Secret | **Yes** ✓ |
| `AZURE_CLIENT_SECRET_UAT` | UAT SP Client Secret | **Yes** ✓ |
| `AZURE_CLIENT_SECRET_PROD` | Prod SP Client Secret | **Yes** ✓ |

> **Important:** Mark all client secrets as **secret** variables (🔒 lock icon). Secret variables are not exposed in logs.

### 4.2 Alternative: Pipeline-Level Variables

If you prefer not to use variable groups, you can define the same variables directly in the pipeline YAML or through the pipeline UI (**Pipelines** → select pipeline → **Edit** → **Variables**).

### 4.3 Link Variable Group to Pipeline

If using a variable group, add this to `azure-pipelines.yml` under the `variables:` section:

```yaml
variables:
  pythonVersion: '3.11'
  - group: fabric-cicd-secrets   # Name of your variable group
```

Or link it via the UI: **Pipelines** → select pipeline → **Edit** → **Variables** → **Variable groups** → **Link variable group**.

---

## Step 5: Configure Environment Files

Edit each config file under `config/` with your actual workspace details.

### 5.1 Config File Structure (`config/dev.json` example)

```jsonc
{
  // Root folder containing artifact definitions
  "artifacts_root_folder": "wsartifacts",

  // Per-environment service principal
  "service_principal": {
    // The env var name that holds the client secret for this environment
    // The pipeline sets this variable from the Azure DevOps secret
    "secret_env_var": "AZURE_CLIENT_SECRET_DEV"
    // Optional: override client_id and tenant_id per environment
    // "client_id": "...",
    // "tenant_id": "..."
  },

  // Target Fabric workspace
  "workspace": {
    "id": "<WORKSPACE-GUID>",          // Get from Fabric portal URL
    "name": "DataEng-Dev",
    "capacity_id": "<CAPACITY-GUID>"    // Optional
  },

  // Lakehouse IDs (get from Fabric portal after creating lakehouses)
  "lakehouses": {
    "SalesDataLakehouse": {
      "id": "<LAKEHOUSE-GUID>",
      "description": "Development sales data"
    }
  },

  // Fabric connection names (must be created manually in Fabric portal first)
  "connections": {
    "sql_connection_string": "Server=<sql-endpoint>;Database=<db>;",
    "semantic_model_connection": "",       // Display name of ShareableCloud connection
    "paginated_report_connection": ""      // Display name for paginated reports
  },

  // Parameter substitution — replaces ${param_name} in artifact definitions
  "parameters": {
    "storage_account": "devstorageaccount",
    "key_vault_url": "https://dev-kv.vault.azure.net/"
  },

  // Artifacts to create if they don't exist (ensures lakehouses/environments exist before deployment)
  "artifacts_to_create": {
    "lakehouses": [
      {
        "name": "SalesDataLakehouse",
        "description": "Dev sales data",
        "create_if_not_exists": true
      }
    ]
  },

  // Git integration settings
  "git_integration": {
    "auto_update_from_git": true,                 // Enable post-deploy Git sync
    "conflict_resolution_policy": "PreferRemote",
    "allow_override_items": true
    // "git_credentials_connection_id": ""         // Optional: explicit ADO connection ID
  }
}
```

### 5.2 Finding Your Workspace ID

1. Open your workspace in the [Fabric portal](https://app.fabric.microsoft.com)
2. Look at the URL: `https://app.fabric.microsoft.com/groups/<WORKSPACE-ID>/...`
3. Copy the GUID from the URL

### 5.3 Finding Lakehouse IDs

1. Open the lakehouse in Fabric portal
2. Look at the URL or the lakehouse settings panel
3. Copy the GUID

> **Tip:** If you set `artifacts_to_create.lakehouses[].create_if_not_exists: true`, the pipeline will create the lakehouse automatically. You can then retrieve the ID from the deployment logs.

---

## Step 6: Configure Fabric Connections (Optional)

If your semantic models or paginated reports use data connections, create ShareableCloud connections in Fabric:

### 6.1 Create a ShareableCloud Connection

1. In the Fabric portal, go to **Settings** → **Manage connections and gateways**
2. Click **+ New connection** → **Cloud**
3. Configure the connection:
   - **Connection type**: SQL Server (or appropriate type)
   - **Server**: Your Fabric SQL endpoint (e.g., `xyz.datawarehouse.fabric.microsoft.com`)
   - **Database**: Your database name
   - **Authentication**: OAuth2
4. Name it something descriptive (e.g., `FabricCI-Dev-SQLConnection`)

### 6.2 Grant SP Access to the Connection

1. In the connection settings, add the service principal as a user
2. The SP must have at least **User** access to the connection

### 6.3 Update Config

Set the connection display name in your config file:

```json
"connections": {
  "semantic_model_connection": "FabricCI-Dev-SQLConnection",
  "paginated_report_connection": "FabricCI-Dev-SQLConnection"
}
```

---

## Step 7: Create Pipeline Environments with Approvals

Create approval gates for UAT and Production deployments:

1. Go to **Pipelines** → **Environments**
2. Create three environments:

| Environment Name | Approvals |
|------------------|-----------|
| `fabric-dev` | None (auto-deploy) |
| `fabric-uat` | Add required approvers |
| `fabric-prod` | Add required approvers |

### 7.1 Set Up Approval Gates

For `fabric-uat` and `fabric-prod`:

1. Click the environment name
2. Click **⋮** → **Approvals and checks**
3. Click **+** → **Approvals**
4. Add the required approvers (users or groups)
5. Set **Minimum number of approvers** (e.g., 1 for UAT, 2 for Prod)
6. Optionally set a **Timeout** (e.g., 72 hours)

---

## Step 8: Create the Pipeline

### 8.1 Create Pipeline from YAML

1. Go to **Pipelines** → **New pipeline**
2. Select **Azure Repos Git**
3. Select your repository
4. Select **Existing Azure Pipelines YAML file**
5. Choose `/azure-pipelines.yml`
6. Click **Run** (or **Save** first to review)

### 8.2 Grant Pipeline Permissions

After the first run, you may need to grant permissions:

1. The pipeline will show a "Permission needed" banner
2. Click **View** and approve access to:
   - Variable groups (if using variable groups)
   - Service connections
   - Environments (fabric-dev, fabric-uat, fabric-prod)

### 8.3 Enable `persistCredentials` for Deployment Tracking

The pipeline commits deployment tracking files back to the repo. For this to work:

1. Go to **Project Settings** → **Repositories** → select your repo
2. Under **Security**, find **\<Build Service\>** user
3. Grant **Contribute** and **Create branch** permissions

Alternatively, in **Pipelines** → **Settings**, ensure `Limit job authorization scope to current project` does not block push access.

---

## Step 9: Branch Strategy

The pipeline uses a branch-per-environment strategy:

| Branch | Target Environment | Trigger |
|--------|-------------------|---------|
| `dev` | Development workspace | Automatic on push |
| `uat` | UAT workspace | Automatic on push (with approval gate) |
| `main` | Production workspace | Automatic on push (with approval gate) |

### Recommended Workflow

```
feature/my-change → dev → uat → main
```

1. Create a feature branch from `dev`
2. Develop and test locally
3. Create a PR to `dev` — deploys to Dev workspace
4. After validation, create a PR from `dev` to `uat` — triggers UAT approval
5. After UAT sign-off, create a PR from `uat` to `main` — triggers Prod approval

---

## Step 10: Run Your First Deployment

### 10.1 Trigger a Deployment

1. Push a change to the `dev` branch:

```bash
git checkout dev
# Make changes to artifacts in wsartifacts/
git add .
git commit -m "Initial artifact deployment"
git push origin dev
```

2. The pipeline will:
   - Validate artifacts (Build stage)
   - Deploy to the Dev workspace (DeployDev stage)
   - Commit deployment tracking state back to the repo

### 10.2 Force Full Deployment

To deploy all artifacts (ignoring change detection), modify the deploy command in the pipeline:

```yaml
python scripts/deploy_artifacts.py dev \
  --config-dir config \
  --artifacts-dir . \
  --create-artifacts \
  --force-all    # ← Add this flag
```

### 10.3 Deploy Specific Artifacts

To deploy only specific artifacts:

```yaml
python scripts/deploy_artifacts.py dev \
  --config-dir config \
  --artifacts-dir . \
  --specific-artifacts "SalesAnalyticsModel" "SalesDashboard"
```

---

## Supported Artifact Types

| Artifact Type | Folder | Format |
|---------------|--------|--------|
| Notebooks | `Notebooks/` | `.ipynb` or Fabric Git folder |
| Semantic Models | `Semanticmodels/` | `.json` or `.SemanticModel/` folder (TMDL) |
| Power BI Reports | `Reports/` | `.json` or `.Report/` folder (PBIR) |
| Paginated Reports | `Paginatedreports/` | `.json` or `.PaginatedReport/` folder (RDL) |
| Lakehouses | `Lakehouses/` | `.json` or `.Lakehouse/` folder |
| Data Pipelines | `Datapipelines/` | `.json` |
| Spark Job Definitions | `Sparkjobdefinitions/` | `.json` |
| Environments | `Environments/` | `.json` |
| Variable Libraries | `Variablelibraries/` | `.json` or `.VariableLibrary/` folder |
| SQL Views | `Views/<LakehouseName>/` | `.sql` files + `metadata.json` |

### Deployment Order (Automatic)

The dependency resolver ensures artifacts are deployed in the correct order:

1. Variable Libraries
2. Environments
3. Lakehouses
4. SQL Views (after their target lakehouse)
5. Semantic Models
6. Notebooks
7. Spark Job Definitions
8. Power BI Reports (after their semantic model)
9. Paginated Reports
10. Data Pipelines (last — orchestration layer)

---

## How Change Detection Works

The pipeline tracks which Git commit was last deployed to each environment.

1. **First run:** All artifacts are deployed (no baseline)
2. **Subsequent runs:** Only artifacts with file changes since the last deployed commit are deployed
3. **Tracking file:** `.deployment_tracking/{env}_last_commit.txt` is committed back to the repo after each deployment
4. **Dependencies included:** If a lakehouse changes, its dependent SQL views are also deployed

To override change detection, use `--force-all`.

---

## Troubleshooting

### Authentication Failures

| Error | Cause | Fix |
|-------|-------|-----|
| `AADSTS7000215: Invalid client secret` | Secret expired or wrong | Rotate the secret in Azure AD and update the pipeline variable |
| `AADSTS700016: Application not found` | Wrong Client ID or tenant | Verify `AZURE_CLIENT_ID_*` and `AZURE_TENANT_ID` variables |
| `InsufficientPrivileges` | SP lacks workspace access | Add SP as Workspace Admin |
| `PrincipalTypeNotSupported` | SP can't Git-sync this item type | Normal for paginated reports — they are handled separately |

### Git Sync Failures

| Error | Cause | Fix |
|-------|-------|-----|
| `GitCredentialsNotConfigured` | SP needs Git credentials | The pipeline auto-creates these; if it fails, set `git_integration.git_credentials_connection_id` in config |
| `WorkspaceNotConnectedToGit` | Workspace has no Git connection | Connect the workspace to Git in Fabric portal first |

### Connection Binding Failures

| Error | Cause | Fix |
|-------|-------|-----|
| `Connection 'X' not found` | Connection doesn't exist or SP lacks access | Create the ShareableCloud connection in Fabric portal and grant SP access |
| `bindConnection failed: 400` | Semantic model has no data source refs yet | Deploy + refresh the model first, then re-run |

### Deployment Tracking Push Fails

| Error | Cause | Fix |
|-------|-------|-----|
| `TF402455: Pushes to this branch are not permitted` | Build service lacks push permission | Grant **Contribute** to the Build Service account on the repo (see Step 8.3) |

### Pipeline Not Triggering

| Symptom | Fix |
|---------|-----|
| Push to `dev` doesn't trigger | Check `trigger.branches.include` in YAML matches your branch name |
| Pipeline runs but skips deploy stage | Check `condition:` — each stage checks `Build.SourceBranchName` |
| Changes don't trigger build | Ensure changes are in paths listed under `trigger.paths.include` |

---

## Quick Reference: Pipeline Variables

| Variable | Required | Secret | Description |
|----------|----------|--------|-------------|
| `AZURE_TENANT_ID` | ✅ | No | Azure AD Tenant ID (same for all environments) |
| `AZURE_CLIENT_ID_DEV` | ✅ | No | Dev service principal App (Client) ID |
| `AZURE_CLIENT_ID_UAT` | ✅ | No | UAT service principal App (Client) ID |
| `AZURE_CLIENT_ID_PROD` | ✅ | No | Prod service principal App (Client) ID |
| `AZURE_CLIENT_SECRET_DEV` | ✅ | ✅ | Dev service principal client secret |
| `AZURE_CLIENT_SECRET_UAT` | ✅ | ✅ | UAT service principal client secret |
| `AZURE_CLIENT_SECRET_PROD` | ✅ | ✅ | Prod service principal client secret |

---

## Quick Reference: Config File Keys

| Key | Required | Description |
|-----|----------|-------------|
| `workspace.id` | ✅ | Target Fabric workspace GUID |
| `workspace.name` | ✅ | Workspace display name (for logging) |
| `service_principal.secret_env_var` | ✅ | Env var name holding the SP secret |
| `artifacts_root_folder` | No | Root folder name (default: `wsartifacts`) |
| `lakehouses.<name>.id` | No | Lakehouse GUID (for parameter substitution) |
| `connections.semantic_model_connection` | No | ShareableCloud connection name for semantic models |
| `connections.paginated_report_connection` | No | ShareableCloud connection name for paginated reports |
| `connections.sql_connection_string` | No | SQL endpoint connection string (for SQL views and paginated report datasource updates) |
| `parameters.*` | No | Key-value pairs for `${placeholder}` substitution in artifacts |
| `artifacts_to_create` | No | Artifacts to auto-create (lakehouses, environments, etc.) |
| `git_integration.auto_update_from_git` | No | Enable/disable post-deploy Git sync (default: `true`) |
| `rebind_rules` | No | Rules for rebinding data sources after deployment |
