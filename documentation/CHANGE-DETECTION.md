# Change Detection & Incremental Deployment

## Overview

The deployment system now includes **automatic change detection** using Git to track which artifacts have been modified since the last successful deployment. This dramatically reduces deployment time and API calls by only deploying changed artifacts.

## How It Works

### 1. Git-Based Tracking

The system uses Git to detect changes:
- **First deployment**: No previous commit → deploys all artifacts
- **Subsequent deployments**: Compares current commit with last deployment commit
- **Changed files**: Uses `git diff` to identify modified files in `wsartifacts/` folder
- **Commit tracking**: Saves commit hash in `.deployment_tracking/{env}_last_commit.txt`

### 2. Change Detection Flow

```
┌─────────────────────────────────────────────────────────────┐
│  1. Read last deployment commit from tracking file          │
│     (.deployment_tracking/dev_last_commit.txt)              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Run git diff between last commit and HEAD               │
│     git diff --name-only {last_commit} HEAD -- wsartifacts/ │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Extract artifact names from changed file paths           │
│     wsartifacts/Notebooks/MyNotebook.ipynb → "MyNotebook"   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Include dependent artifacts (e.g., SQL views)            │
│     If lakehouse changed → include its SQL views            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  5. Filter discovered artifacts to only changed ones         │
│     Deploy only the filtered subset                          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  6. After successful deployment, save current commit hash    │
│     Used as baseline for next deployment                     │
└─────────────────────────────────────────────────────────────┘
```

## Usage

### Default Behavior (Change Detection Enabled)

```bash
# Deploy only changed artifacts (recommended)
python scripts/deploy_artifacts.py dev
```

**Output example:**
```
CHANGE DETECTION
============================================================
Last deployment: abc123de (2025-12-20 10:30:00)
Current commit: xyz789gh (2025-12-22 14:45:00)
Changed artifacts: 2
  Notebook: ProcessSalesData
  Lakehouse: SalesDataLakehouse
Skipped (unchanged): 13
============================================================
```

### Force Deploy All Artifacts

```bash
# Ignore change detection, deploy everything
python scripts/deploy_artifacts.py dev --force-all
```

Use when:
- Infrastructure changes require full redeployment
- Testing deployment pipeline
- Recovering from failed deployment
- API changes that affect all artifacts

### Deploy Specific Artifacts

```bash
# Deploy only specified artifacts
python scripts/deploy_artifacts.py dev --artifacts "ProcessSalesData,SalesDataLakehouse"
```

Use when:
- Need to redeploy specific artifact(s)
- Testing individual artifact changes
- Manual deployment override

### Dry Run with Change Detection

```bash
# See what would be deployed without making changes
python scripts/deploy_artifacts.py dev --dry-run
```

## Special Cases

### 1. First Deployment

When no previous deployment commit exists:
- **Behavior**: Deploys all discovered artifacts
- **Log**: `First deployment detected, deploying all artifacts`
- **Creates**: `.deployment_tracking/{env}_last_commit.txt`

### 2. Configuration File Changes

When `config/{env}.json` changes:
- **Behavior**: Deploys **ALL** artifacts (config is used for parameter substitution)
- **Log**: `Configuration files changed, deploying all artifacts`
- **Reason**: Config changes may affect any artifact's parameters

### 3. No Changes Detected

When no files have changed:
- **Behavior**: Skips deployment entirely
- **Log**: `No changes detected since last deployment`
- **Override**: Use `--force-all` to deploy anyway

### 4. Git Not Available

When Git is not installed or not a Git repository:
- **Behavior**: Falls back to deploying all artifacts
- **Log**: `Git not available, deploying all artifacts`
- **Recommendation**: Use Git for optimal change detection

### 5. Dependency Tracking

When a lakehouse changes:
- **Behavior**: Automatically includes dependent SQL views
- **Log**: `Including N SQL view(s) due to lakehouse changes`
- **Reason**: SQL views depend on lakehouse schemas

## File Structure

### Tracking Files

```
.deployment_tracking/
├── README.md
├── dev_last_commit.txt       # Development environment
├── uat_last_commit.txt       # UAT environment
└── prod_last_commit.txt      # Production environment
```

### Commit File Format

```
4f7660e86215276c8fa628f56f968ffa3328eb75
# Last deployment: 2025-12-22T14:45:30.123456
# Environment: dev
```

## Artifact-to-File Mapping

| Artifact Type | File Pattern | Example |
|--------------|--------------|---------|
| Lakehouse | `wsartifacts/Lakehouses/{name}.json`<br>`wsartifacts/Lakehouses/{name}.Lakehouse/` | `SalesDataLakehouse.json`<br>`SalesDataLakehouse.Lakehouse/.platform` |
| Notebook | `wsartifacts/Notebooks/{name}.ipynb` | `ProcessSalesData.ipynb` |
| Variable Library | `wsartifacts/Variablelibraries/{name}.json`<br>`wsartifacts/Variablelibraries/{name}.VariableLibrary/` | `DevVariables.json`<br>`DevVariables.VariableLibrary/valueSets/dev.json` |
| Data Pipeline | `wsartifacts/Datapipelines/{name}.json` | `SalesDailyOrchestration.json` |
| Environment | `wsartifacts/Environments/{name}.json` | `ProdEnvironment.json` |
| Spark Job | `wsartifacts/Sparkjobdefinitions/{name}.json` | `DailySalesAggregation.json` |
| SQL View | `wsartifacts/Views/{lakehouse}/{view}.sql` | `SalesDataLakehouse/SalesSummary.sql` |
| Report | `wsartifacts/Reports/{name}.json` | `SalesDashboard.json` |

## CI/CD Integration

### Azure DevOps Pipeline

The change detection works seamlessly with Azure DevOps:

```yaml
- script: |
    # Change detection is automatic - just run normally
    python scripts/deploy_artifacts.py $(Environment)
  displayName: 'Deploy Changed Artifacts'
  env:
    FABRIC_SP_CLIENT_ID: $(FABRIC_SP_CLIENT_ID)
    FABRIC_SP_TENANT_ID: $(FABRIC_SP_TENANT_ID)
    FABRIC_SP_SECRET: $(FABRIC_SP_SECRET)
```

**Note**: Commit hashes are stored in the repository, so they persist across pipeline runs.

### GitHub Actions

```yaml
- name: Deploy Changed Artifacts
  run: |
    python scripts/deploy_artifacts.py ${{ matrix.environment }}
  env:
    FABRIC_SP_CLIENT_ID: ${{ secrets.FABRIC_SP_CLIENT_ID }}
    FABRIC_SP_TENANT_ID: ${{ secrets.FABRIC_SP_TENANT_ID }}
    FABRIC_SP_SECRET: ${{ secrets.FABRIC_SP_SECRET }}
```

## Performance Impact

### Before (Without Change Detection)

- **Artifacts discovered**: 15
- **Artifacts deployed**: 15
- **Deployment time**: ~5-10 minutes
- **API calls**: ~45-60

### After (With Change Detection)

**Typical change (2-3 files):**
- **Artifacts discovered**: 15
- **Artifacts deployed**: 2-3
- **Deployment time**: ~1-2 minutes ⚡ (**80% faster**)
- **API calls**: ~6-9 ⚡ (**85% reduction**)

**No changes:**
- **Artifacts discovered**: 15
- **Artifacts deployed**: 0
- **Deployment time**: <10 seconds ⚡ (**95% faster**)
- **API calls**: 0 ⚡ (**100% reduction**)

## Troubleshooting

### Problem: "Git not available, deploying all artifacts"

**Solution**: Install Git or ensure you're in a Git repository
```bash
git --version
git status
```

### Problem: All artifacts deploying despite no changes

**Possible causes:**
1. Config file changed → expected behavior
2. Missing tracking file → delete and redeploy once
3. Git repository issue → check `git status`

**Solution**:
```bash
# Check last deployment commit
cat .deployment_tracking/dev_last_commit.txt

# Check for config changes
git diff HEAD~1 config/dev.json
```

### Problem: Specific artifact not deploying

**Possible causes:**
1. File wasn't actually changed in Git
2. File in `.gitignore`
3. File name doesn't match artifact name

**Solution**:
```bash
# Check if file was modified
git diff HEAD~1 -- wsartifacts/

# Force deploy specific artifact
python scripts/deploy_artifacts.py dev --artifacts "ArtifactName"

# Force deploy all
python scripts/deploy_artifacts.py dev --force-all
```

### Problem: Want to reset change tracking

**Solution**:
```bash
# Delete tracking file for environment
rm .deployment_tracking/dev_last_commit.txt

# Next deployment will be treated as first deployment
python scripts/deploy_artifacts.py dev
```

## Best Practices

### 1. Commit Before Deployment

Always commit your changes before deploying:
```bash
git add wsartifacts/
git commit -m "Update notebooks"
python scripts/deploy_artifacts.py dev
```

### 2. Use Branches for Environments

Follow Git branching strategy:
- `development` → Dev environment
- `uat` → UAT environment
- `main` → Production environment

### 3. Review Changes Before Deploy

```bash
# See what changed
git diff HEAD~1 -- wsartifacts/

# Dry run to preview
python scripts/deploy_artifacts.py dev --dry-run
```

### 4. Keep Tracking Files in Repository

Commit `.deployment_tracking/` files to Git so deployment state is shared:
```bash
git add .deployment_tracking/
git commit -m "Update deployment tracking"
```

### 5. Use Force Deploy Sparingly

Only use `--force-all` when necessary:
- After major API changes
- Infrastructure updates
- Troubleshooting

## Examples

### Example 1: Deploy After Notebook Update

```bash
# Edit notebook
vi wsartifacts/Notebooks/ProcessSalesData.ipynb

# Commit changes
git add wsartifacts/Notebooks/ProcessSalesData.ipynb
git commit -m "Update sales processing logic"

# Deploy (only this notebook will deploy)
python scripts/deploy_artifacts.py dev
```

**Output:**
```
CHANGE DETECTION
============================================================
Changed artifacts: 1
  Notebook: ProcessSalesData
Skipped (unchanged): 14
============================================================
```

### Example 2: Deploy After Multiple Changes

```bash
# Edit multiple files
vi wsartifacts/Notebooks/ProcessSalesData.ipynb
vi wsartifacts/Lakehouses/SalesDataLakehouse.Lakehouse/.platform
vi wsartifacts/Views/SalesDataLakehouse/SalesSummary.sql

# Commit
git add wsartifacts/
git commit -m "Update sales pipeline and views"

# Deploy
python scripts/deploy_artifacts.py dev
```

**Output:**
```
CHANGE DETECTION
============================================================
Changed artifacts: 3
  Lakehouse: SalesDataLakehouse
  Notebook: ProcessSalesData
  SqlView: SalesSummary
Including 2 SQL view(s) due to lakehouse changes
Skipped (unchanged): 12
============================================================
```

### Example 3: Config Change Triggers Full Deploy

```bash
# Update config
vi config/dev.json

# Commit
git add config/dev.json
git commit -m "Update API endpoint"

# Deploy
python scripts/deploy_artifacts.py dev
```

**Output:**
```
CHANGE DETECTION
============================================================
Configuration files changed, deploying all artifacts
Deploying all discovered artifacts
============================================================
```

## Advanced Usage

### Check What Would Be Deployed

```bash
# Dry run shows change detection in action
python scripts/deploy_artifacts.py dev --dry-run
```

### Deploy Subset of Changed Artifacts

```bash
# Even with changes detected, deploy only specific ones
python scripts/deploy_artifacts.py dev --artifacts "ProcessSalesData"
```

### Override Change Detection

```bash
# Deploy all regardless of changes
python scripts/deploy_artifacts.py dev --force-all
```

## Summary

✅ **Change detection is ON by default** - optimal for most deployments  
✅ **Git-based tracking** - uses commit hashes for reliability  
✅ **Automatic dependency handling** - includes dependent artifacts  
✅ **Config-aware** - redeploys all when config changes  
✅ **Fallback safe** - deploys all if Git unavailable  
✅ **Override options** - `--force-all` and `--artifacts` flags  
✅ **CI/CD ready** - works seamlessly with pipelines  

The change detection feature dramatically improves deployment efficiency while maintaining safety and reliability.
