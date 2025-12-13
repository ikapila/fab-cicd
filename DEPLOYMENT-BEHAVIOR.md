# Deployment Behavior Summary

## ✅ Update Support - Artifact Deployment Behavior

The system now properly **creates AND updates** Fabric artifacts when deploying changes.

---

## Deployment Modes

### 1. **Config-Driven Creation** (`--create-artifacts`)
Creates artifacts defined in config files (dev.json, uat.json, prod.json):
- Checks if artifact exists
- Creates only if missing
- Uses `create_if_not_exists` flag

**Use case:** Initial setup, adding new artifacts to existing environments

### 2. **File-Based Deployment** (default)
Deploys artifacts from repository files (notebooks/, datapipelines/, etc.):
- Checks if artifact exists
- **CREATES** if new
- **UPDATES** if exists

**Use case:** Regular deployments, promoting changes across environments

---

## Artifact Update Behavior

| Artifact Type | Create | Update | Notes |
|---------------|--------|--------|-------|
| **Notebooks** | ✅ | ✅ | Full content update via `updateDefinition` API |
| **Spark Job Definitions** | ✅ | ✅ | Definition update via `updateDefinition` API |
| **Data Pipelines** | ✅ | ✅ | Definition update via `updateDefinition` API |
| **Semantic Models** | ✅ | ✅ | Schema update via `updateDefinition` API |
| **Power BI Reports** | ✅ | ✅ | Visuals update via `updateDefinition` API |
| **Paginated Reports** | ✅ | ✅ | Definition update via `updateDefinition` API |
| **Lakehouses** | ✅ | ⚠️ | Immutable - only creates, skips if exists |
| **Environments** | ✅ | ⚠️ | Immutable - only creates, skips if exists |
| **Shortcuts** | ✅ | ⚠️ | Creates if missing, skips if exists |

### Legend:
- ✅ = Fully supported
- ⚠️ = Limited (artifacts are immutable once created)

---

## How Updates Work

### Notebooks
```python
# When notebook exists:
1. Reads notebook file from repository
2. Substitutes environment parameters
3. Calls update_notebook_definition() API
4. Fabric updates notebook content

Result: Notebook changes deployed ✅
```

### Spark Jobs
```python
# When Spark job exists:
1. Reads job definition from repository
2. Substitutes environment parameters
3. Calls update_spark_job_definition() API
4. Fabric updates job configuration

Result: Spark job changes deployed ✅
```

### Pipelines
```python
# When pipeline exists:
1. Reads pipeline definition from repository
2. Substitutes environment parameters
3. Calls update_data_pipeline() API
4. Fabric updates pipeline activities

Result: Pipeline changes deployed ✅
```

### Lakehouses & Environments
```python
# When lakehouse/environment exists:
1. Checks if artifact exists
2. Logs "already exists"
3. Skips (these are infrastructure, rarely change)

Result: No update (by design) ℹ️
```

**Why?** Lakehouses and Environments are typically infrastructure components that contain data or runtime configurations. Updating them could cause data loss or service disruption.

---

## Deployment Workflow Example

### Scenario: Update a Semantic Model

**Step 1: Update model definition**
```bash
# Edit semanticmodels/SalesAnalyticsModel.json
# Add new measure, relationship, or table
```

**Step 2: Deploy update**
```bash
python scripts/deploy_artifacts.py dev
# Output:
# - Found semantic model 'SalesAnalyticsModel'
# - Updating semantic model definition...
# - ✅ Semantic model updated successfully
```

**Step 3: Verify in Fabric**
```
1. Open DataEng-Dev workspace
2. Open SalesAnalyticsModel
3. Verify new measures/relationships appear
4. Test data refresh
```

---

### Scenario: Update a Power BI Report

**Step 1: Edit report definition**
```bash
# Edit reports/SalesDashboard.json
# Update visual configuration or add new pages
```

**Step 2: Deploy update**
```bash
python scripts/deploy_artifacts.py dev
# Output:
# - Found report 'SalesDashboard'
# - Updating report definition...
# - ✅ Report updated successfully
```

**Step 3: Users see changes**
```
- Report consumers automatically see updated visuals
- Bookmarks and personal views are preserved
- No downtime during update
```

---

### Scenario: Update a Notebook

**Step 1: Edit notebook in Dev workspace**
```
1. Open DataEng-Dev workspace in Fabric
2. Edit ProcessSalesData notebook
3. Save changes
4. Commit to Git from Fabric UI
```

**Step 2: Deploy to Dev (automatic)**
```bash
# GitHub Actions automatically triggers on commit to development branch
- Reads ProcessSalesData.ipynb from repo
- Finds existing notebook in Dev workspace
- Calls update_notebook_definition()
- ✅ Changes deployed to Dev
```

**Step 3: Promote to UAT**
```bash
# Create PR: development → uat
# After approval and merge:
- Pipeline triggers on uat branch
- Reads ProcessSalesData.ipynb
- Finds existing notebook in UAT workspace
- Calls update_notebook_definition()
- ✅ Changes deployed to UAT
```

**Step 4: Promote to Prod**
```bash
# Create PR: uat → main
# After approval and merge:
- Pipeline triggers on main branch
- Reads ProcessSalesData.ipynb
- Finds existing notebook in Prod workspace
- Calls update_notebook_definition()
- ✅ Changes deployed to Prod
```

---

## Parameter Substitution

When deploying, environment-specific parameters are automatically substituted:

**Notebook with parameters:**
```python
# In notebook cell:
storage_account = "{{storage_account}}"
environment = "{{environment}}"
```

**Dev deployment:**
```python
# Becomes:
storage_account = "devstorageaccount"
environment = "dev"
```

**Prod deployment:**
```python
# Becomes:
storage_account = "prodstorageaccount"
environment = "prod"
```

---

## Testing Deployment

### Test Update Locally

```bash
# 1. Make a change to a notebook
vim notebooks/ProcessSalesData.ipynb

# 2. Test deployment (dry run)
export AZURE_CLIENT_SECRET_DEV="your-secret"
python scripts/deploy_artifacts.py dev --dry-run

# 3. Deploy for real
python scripts/deploy_artifacts.py dev

# Expected output:
# Deploying: ProcessSalesData (Notebook)
#   Notebook 'ProcessSalesData' already exists, updating...
#   Updated notebook (ID: abc-123)
# ✅ Successfully deployed: ProcessSalesData
```

### Test via Git Integration

```bash
# 1. Edit artifact in Fabric workspace
# 2. Commit changes via Fabric Git UI
# 3. Pull changes locally
git pull origin development

# 4. Push to trigger pipeline
git push origin development

# 5. Watch GitHub Actions
# Go to: https://github.com/ikapila/fabric-cicd/actions
```

---

## API Endpoints Used

### Create Operations
```
POST /workspaces/{workspaceId}/notebooks
POST /workspaces/{workspaceId}/sparkJobDefinitions
POST /workspaces/{workspaceId}/dataPipelines
POST /workspaces/{workspaceId}/lakehouses
POST /workspaces/{workspaceId}/environments
```

### Update Operations
```
POST /workspaces/{workspaceId}/notebooks/{notebookId}/updateDefinition
POST /workspaces/{workspaceId}/sparkJobDefinitions/{jobId}/updateDefinition
POST /workspaces/{workspaceId}/dataPipelines/{pipelineId}/updateDefinition
```

---

## Common Scenarios

### Scenario 1: Add New Notebook
```bash
# 1. Create notebook in Dev workspace
# 2. Commit to Git
# 3. Pipeline creates notebook in UAT/Prod on promotion

Result: New notebook in all environments ✅
```

### Scenario 2: Update Existing Notebook
```bash
# 1. Edit notebook in Dev workspace
# 2. Commit changes
# 3. Pipeline updates existing notebook in UAT/Prod

Result: Notebook changes propagated ✅
```

### Scenario 3: Change Pipeline Activities
```bash
# 1. Edit datapipelines/MyPipeline.json
# 2. Commit and push
# 3. Pipeline updates pipeline definition

Result: Pipeline activities updated ✅
```

### Scenario 4: Add New Lakehouse (Config-Driven)
```json
// In config/dev.json:
"lakehouses": [
  {"name": "NewLakehouse", "create_if_not_exists": true}
]

// Deploy with:
python scripts/deploy_artifacts.py dev --create-artifacts

Result: Lakehouse created ✅
```

---

## Deployment Logs

### Successful Update Example
```
Starting deployment to dev environment
============================================================
Deploying: ProcessSalesData (Notebook)
  Notebook 'ProcessSalesData' already exists, updating...
  Updated notebook (ID: abc-123-def-456)
✅ Successfully deployed: ProcessSalesData

Deploying: DailySalesAggregation (SparkJobDefinition)
  Spark job 'DailySalesAggregation' already exists, updating...
  Updated Spark job (ID: ghi-789-jkl-012)
✅ Successfully deployed: DailySalesAggregation

DEPLOYMENT SUMMARY
============================================================
Total artifacts: 2
Successful: 2
Failed: 0
```

### Create Example
```
Deploying: NewNotebook (Notebook)
  Created notebook (ID: xyz-111-222-333)
✅ Successfully deployed: NewNotebook
```

### Skip Example (Lakehouse)
```
Deploying: SalesDataLakehouse (Lakehouse)
  Lakehouse 'SalesDataLakehouse' already exists (ID: aaa-bbb-ccc)
✅ Successfully deployed: SalesDataLakehouse
```

---

## Summary

### ✅ What Works
- **Create** new artifacts from Git files
- **Update** notebooks with code changes
- **Update** Spark jobs with configuration changes
- **Update** pipelines with activity changes
- **Parameter substitution** per environment
- **Dependency ordering** (lakehouses before notebooks)
- **Idempotent** operations (safe to run multiple times)

### ⚠️ Limitations
- Lakehouses are immutable (data storage - can't update structure)
- Environments are immutable (runtime config - create new versions instead)
- Shortcuts are immutable (recreate if needed)

### 🎯 Best Practice
Use **Git as source of truth**:
1. Edit artifacts in Dev workspace
2. Commit to Git
3. Let pipeline deploy changes to UAT/Prod
4. Changes are version-controlled and auditable

The system now properly supports **full CI/CD lifecycle** for Fabric Data Engineering artifacts! 🚀
