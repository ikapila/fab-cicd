# Per-Environment Service Principals & Config-Driven Artifact Creation Guide

## Overview

This guide covers two major enhancements to the Fabric CI/CD system:

1. **Per-Environment Service Principals** - Use separate service principals for each environment (Dev, UAT, Prod)
2. **Config-Driven Artifact Creation** - Define artifacts in configuration files for automatic creation with service principal ownership

## 🔐 Per-Environment Service Principals

### Why Use Per-Environment Service Principals?

**Benefits:**
- ✅ **Enhanced Security** - Limit blast radius if credentials are compromised
- ✅ **Principle of Least Privilege** - Each SP only has access to its environment
- ✅ **Simplified Auditing** - Track which SP made changes in which environment
- ✅ **Independent Rotation** - Rotate secrets per environment without affecting others
- ✅ **Compliance** - Meet regulatory requirements for production isolation

### Setup Instructions

#### Step 1: Create Three Service Principals

Create a separate service principal for each environment in Azure Portal:

**Development Service Principal:**
```bash
# Azure CLI command
az ad app create --display-name "fabric-cicd-dev-sp"

# Note the Application (client) ID and Tenant ID
# Create client secret
az ad app credential reset --id <app-id> --append
```

**UAT Service Principal:**
```bash
az ad app create --display-name "fabric-cicd-uat-sp"
az ad app credential reset --id <app-id> --append
```

**Production Service Principal:**
```bash
az ad app create --display-name "fabric-cicd-prod-sp"
az ad app credential reset --id <app-id> --append
```

#### Step 2: Update Configuration Files

Update each environment's configuration file with its service principal details:

**config/dev.json:**
```json
{
  "service_principal": {
    "client_id": "dev-sp-client-id-here",
    "tenant_id": "your-tenant-id",
    "secret_env_var": "AZURE_CLIENT_SECRET_DEV"
  },
  "workspace": {
    ...
  }
}
```

**config/uat.json:**
```json
{
  "service_principal": {
    "client_id": "uat-sp-client-id-here",
    "tenant_id": "your-tenant-id",
    "secret_env_var": "AZURE_CLIENT_SECRET_UAT"
  },
  "workspace": {
    ...
  }
}
```

**config/prod.json:**
```json
{
  "service_principal": {
    "client_id": "prod-sp-client-id-here",
    "tenant_id": "your-tenant-id",
    "secret_env_var": "AZURE_CLIENT_SECRET_PROD"
  },
  "workspace": {
    ...
  }
}
```

#### Step 3: Grant Workspace Access

Add each service principal to its corresponding workspace:

1. Open Fabric portal → Navigate to workspace
2. Click workspace settings → Manage access
3. Add service principal with **Admin** role
4. Repeat for each environment

#### Step 4: Configure Pipeline Secrets

**For Azure DevOps:**
1. Go to Pipelines → Library → Variable groups
2. Create or update variable group
3. Add three secrets:
   - `AZURE_CLIENT_SECRET_DEV` - Dev SP secret
   - `AZURE_CLIENT_SECRET_UAT` - UAT SP secret
   - `AZURE_CLIENT_SECRET_PROD` - Prod SP secret

**For GitHub Actions:**
1. Go to Settings → Secrets and variables → Actions
2. Add three repository secrets:
   - `AZURE_CLIENT_SECRET_DEV`
   - `AZURE_CLIENT_SECRET_UAT`
   - `AZURE_CLIENT_SECRET_PROD`

#### Step 5: Test Authentication

Test each environment's service principal:

```bash
# Test Dev
export AZURE_CLIENT_SECRET_DEV="dev-secret-here"
python scripts/deploy_artifacts.py dev --dry-run

# Test UAT
export AZURE_CLIENT_SECRET_UAT="uat-secret-here"
python scripts/deploy_artifacts.py uat --dry-run

# Test Prod
export AZURE_CLIENT_SECRET_PROD="prod-secret-here"
python scripts/deploy_artifacts.py prod --dry-run
```

### Secret Rotation Process

To rotate a service principal secret:

1. **Create new secret** in Azure Portal for the SP
2. **Update pipeline secret** with new value
3. **Test deployment** to verify new secret works
4. **Delete old secret** in Azure Portal
5. **Document rotation** in your security log

Example rotation schedule:
- **Dev:** Every 6 months
- **UAT:** Every 12 months
- **Production:** Every 12 months (or per compliance requirements)

---

## 🏗️ Config-Driven Artifact Creation

### Why Config-Driven Artifact Creation?

**Benefits:**
- ✅ **Service Principal Ownership** - Artifacts are created by and owned by the SP
- ✅ **Infrastructure as Code** - Define infrastructure in configuration files
- ✅ **Idempotent Deployments** - Safe to run multiple times
- ✅ **Environment Consistency** - Ensure all environments have required artifacts
- ✅ **Reduced Manual Work** - No need to manually create artifacts in portal

### Supported Artifact Types

Currently supported:
- **Lakehouses** - Data storage
- **Environments** - Spark configurations with libraries
- **KQL Databases** - Real-time analytics databases

### Configuration Structure

Add `artifacts_to_create` section to your environment config files:

```json
{
  "service_principal": { ... },
  "workspace": { ... },
  "parameters": { ... },
  "artifacts_to_create": {
    "lakehouses": [
      {
        "name": "SalesDataLakehouse",
        "description": "Lakehouse for sales data",
        "create_if_not_exists": true
      }
    ],
    "environments": [
      {
        "name": "ProdSparkEnvironment",
        "description": "Production Spark environment",
        "create_if_not_exists": true,
        "libraries": [
          {"type": "PyPI", "name": "pandas", "version": "2.1.0"},
          {"type": "PyPI", "name": "numpy", "version": "1.24.0"}
        ]
      }
    ],
    "kql_databases": [
      {
        "name": "AnalyticsDB",
        "description": "Real-time analytics database",
        "create_if_not_exists": true
      }
    ]
  }
}
```

### Adding New Artifacts to Create

To add a new lakehouse:

1. Edit the appropriate environment config file (e.g., `config/prod.json`)
2. Add entry to `artifacts_to_create.lakehouses` array:

```json
{
  "name": "NewLakehouseName",
  "description": "Description of the lakehouse",
  "create_if_not_exists": true
}
```

3. Commit and deploy:

```bash
git add config/prod.json
git commit -m "Add NewLakehouseName lakehouse to production"
git push origin uat  # Push to UAT branch first for testing
```

4. The pipeline will automatically create the lakehouse during deployment

### Creating Artifacts Manually

You can also create artifacts manually using the deployment script:

```bash
# Create artifacts only (no deployment)
python scripts/deploy_artifacts.py dev --create-artifacts --skip-discovery

# Create artifacts and deploy
python scripts/deploy_artifacts.py dev --create-artifacts

# Dry run to see what would be created
python scripts/deploy_artifacts.py dev --create-artifacts --dry-run
```

### Artifact Configuration Options

#### Lakehouse Configuration

```json
{
  "name": "MyLakehouse",
  "description": "Optional description",
  "create_if_not_exists": true,  // Skip if already exists
  "folders": []  // Future: auto-create folder structure
}
```

#### Environment Configuration

```json
{
  "name": "MyEnvironment",
  "description": "Optional description",
  "create_if_not_exists": true,
  "libraries": [
    {
      "type": "PyPI",  // or "Maven", "R", "Custom"
      "name": "package-name",
      "version": "1.0.0"
    }
  ],
  "spark_config": {  // Future: Spark configuration
    "spark.executor.memory": "4g"
  }
}
```

#### KQL Database Configuration

```json
{
  "name": "MyKQLDatabase",
  "description": "Optional description",
  "create_if_not_exists": true
}
```

#### Notebook Configuration

```json
{
  "name": "MyNotebook",
  "description": "Optional description",
  "create_if_not_exists": true,
  "template": "basic_spark",  // or "sql", "empty"
  "default_lakehouse": "SalesDataLakehouse"  // Optional: attach to lakehouse
}
```

**Available Templates:**
- `basic_spark` - PySpark notebook with common imports
- `sql` - SQL-based notebook
- `empty` - Blank notebook

#### Spark Job Definition Configuration

```json
{
  "name": "MySparkJob",
  "description": "Optional description",
  "create_if_not_exists": true,
  "main_file": "notebooks/ProcessSalesData.ipynb",  // Reference to notebook
  "default_lakehouse": "SalesDataLakehouse",  // Optional: attach to lakehouse
  "configuration": {  // Optional: Spark configuration
    "spark.executor.memory": "4g",
    "spark.executor.cores": "2"
  }
}
```

#### Data Pipeline Configuration

```json
{
  "name": "MyPipeline",
  "description": "Optional description",
  "create_if_not_exists": true,
  "activities": [  // Optional: define activities inline
    {
      "name": "Activity1",
      "type": "Script",
      "typeProperties": {
        "scripts": [
          {
            "type": "Query",
            "text": "SELECT * FROM table"
          }
        ]
      }
    }
  ],
  "parameters": {  // Optional: pipeline parameters
    "date": {
      "type": "String",
      "defaultValue": "2024-01-01"
    }
  },
  "variables": {}  // Optional: pipeline variables
}
```

#### Shortcut Configuration

**OneLake Shortcut (link to another Fabric lakehouse):**
```json
{
  "name": "SharedData",
  "description": "Shortcut to shared lakehouse",
  "lakehouse": "MyLakehouse",
  "path": "Tables",  // or "Files"
  "create_if_not_exists": true,
  "target": {
    "oneLake": {
      "workspaceId": "source-workspace-id",
      "itemId": "source-lakehouse-id",
      "path": "Tables/SourceTable"
    }
  }
}
```

**ADLS Gen2 Shortcut (link to Azure Data Lake Storage):**
```json
{
  "name": "ExternalStorage",
  "description": "Shortcut to ADLS Gen2",
  "lakehouse": "MyLakehouse",
  "path": "Files",
  "create_if_not_exists": true,
  "target": {
    "adlsGen2": {
      "location": "https://storageaccount.dfs.core.windows.net/container/path",
      "connectionId": "connection-guid-from-fabric"
    }
  }
}
```

**Available Paths:**
- `Tables` - Create shortcut in Tables folder
- `Files` - Create shortcut in Files folder

**Shortcut Types:**
- `oneLake` - Link to another OneLake lakehouse
- `adlsGen2` - Link to Azure Data Lake Storage Gen2
- `s3` - Link to Amazon S3 (requires connection configuration)

### Best Practices

1. **Always set `create_if_not_exists: true`** - Prevents errors on subsequent deployments

2. **Use descriptive names** - Include environment prefix if needed

3. **Reference dependencies correctly** - For notebooks and spark jobs, ensure lakehouse names match

4. **Start with templates** - Use notebook templates for consistency across environments

5. **Keep pipelines simple initially** - Start with basic activities, enhance later

### Example: Complete Configuration with All Artifact Types

```json
{
  "service_principal": {
    "client_id": "your-dev-sp-client-id",
    "tenant_id": "your-tenant-id",
    "secret_env_var": "AZURE_CLIENT_SECRET_DEV"
  },
  "workspace": {
    "id": "dev-workspace-id",
    "name": "dev-workspace"
  },
  "artifacts_to_create": {
    "lakehouses": [
      {
        "name": "SalesDataLakehouse",
        "description": "Sales data storage",
        "create_if_not_exists": true
      }
    ],
    "environments": [
      {
        "name": "DataScienceEnvironment",
        "description": "Python environment with ML libraries",
        "create_if_not_exists": true,
        "libraries": [
          {"type": "PyPI", "name": "pandas", "version": "2.0.0"},
          {"type": "PyPI", "name": "scikit-learn", "version": "1.3.0"}
        ]
      }
    ],
    "notebooks": [
      {
        "name": "DataPreparation",
        "description": "Prepare sales data for analysis",
        "template": "basic_spark",
        "default_lakehouse": "SalesDataLakehouse",
        "create_if_not_exists": true
      },
      {
        "name": "SQLAnalysis",
        "description": "SQL-based data analysis",
        "template": "sql",
        "default_lakehouse": "SalesDataLakehouse",
        "create_if_not_exists": true
      }
    ],
    "spark_job_definitions": [
      {
        "name": "DailySalesProcessing",
        "description": "Process daily sales data",
        "main_file": "notebooks/DataPreparation.ipynb",
        "default_lakehouse": "SalesDataLakehouse",
        "create_if_not_exists": true,
        "configuration": {
          "spark.executor.memory": "8g",
          "spark.executor.cores": "4"
        }
      }
    ],
    "data_pipelines": [
      {
        "name": "SalesOrchestration",
        "description": "Orchestrate sales data processing",
        "create_if_not_exists": true,
        "parameters": {
          "process_date": {
            "type": "String",
            "defaultValue": "today"
          }
        },
        "activities": [
          {
            "name": "RunDataPrep",
            "type": "Notebook",
            "typeProperties": {
              "notebookName": "DataPreparation"
            }
          }
        ]
      }
    ],
    "kql_databases": [
      {
        "name": "RealTimeAnalytics",
        "description": "Real-time data analytics",
        "create_if_not_exists": true
      }
    ],
    "shortcuts": [
      {
        "name": "SharedMasterData",
        "description": "OneLake shortcut to shared master data",
        "lakehouse": "SalesDataLakehouse",
        "path": "Tables",
        "create_if_not_exists": true,
        "target": {
          "oneLake": {
            "workspaceId": "shared-workspace-id",
            "itemId": "master-lakehouse-id",
            "path": "Tables/MasterData"
          }
        }
      },
      {
        "name": "ExternalFiles",
        "description": "ADLS shortcut to external storage",
        "lakehouse": "SalesDataLakehouse",
        "path": "Files",
        "create_if_not_exists": true,
        "target": {
          "adlsGen2": {
            "location": "https://devstorageaccount.dfs.core.windows.net/raw/external",
            "connectionId": "adls-connection-id"
          }
        }
      }
    ]
  }
}
```
   ```json
   "name": "Prod_SalesDataLakehouse"
   ```

3. **Document in descriptions** - Explain the purpose of each artifact
   ```json
   "description": "Primary lakehouse for daily sales data processing and storage"
   ```

4. **Version control everything** - All artifact definitions should be in Git

5. **Test in Dev first** - Always add artifacts to Dev config first, test, then promote

6. **Keep environments aligned** - Use same artifact names across environments for consistency

---

## 🔄 Deployment Workflow with New Features

### Initial Setup (One-time)

1. **Create service principals** (3 total - one per environment)
2. **Update config files** with SP details and artifacts to create
3. **Configure pipeline secrets** with environment-specific secrets
4. **Test authentication** for each environment

### Adding New Artifacts

1. **Add to config file** in `artifacts_to_create` section
2. **Commit to Git**:
   ```bash
   git add config/dev.json
   git commit -m "Add new CustomerAnalytics lakehouse"
   git push origin development
   ```
3. **Pipeline automatically creates** the artifact during deployment
4. **Verify creation** in Fabric portal
5. **Promote to UAT** via PR when ready

### Complete Deployment Flow

```
Developer adds artifact to config/dev.json
         ↓
Commit to development branch
         ↓
Pipeline runs with Dev SP credentials
         ↓
Artifact created in Dev workspace (owned by Dev SP)
         ↓
Existing artifacts deployed
         ↓
Tests pass
         ↓
Create PR: development → uat
         ↓
Pipeline runs with UAT SP credentials
         ↓
Artifact created in UAT workspace (owned by UAT SP)
         ↓
Artifacts deployed to UAT
         ↓
Create PR: uat → main
         ↓
Pipeline runs with Prod SP credentials
         ↓
Artifact created in Prod workspace (owned by Prod SP)
         ↓
Artifacts deployed to Production
```

---

## 🧪 Testing Guide

### Test Per-Environment SPs

```bash
# Test Dev SP
export AZURE_CLIENT_SECRET_DEV="your-dev-secret"
python scripts/fabric_auth.py

# Test UAT SP
export AZURE_CLIENT_SECRET_UAT="your-uat-secret"
python scripts/fabric_auth.py

# Test Prod SP
export AZURE_CLIENT_SECRET_PROD="your-prod-secret"
python scripts/fabric_auth.py
```

### Test Artifact Creation

```bash
# Dry run to see what would be created
python scripts/deploy_artifacts.py dev --create-artifacts --dry-run

# Actually create artifacts
python scripts/deploy_artifacts.py dev --create-artifacts --skip-discovery

# Create and deploy in one command
python scripts/deploy_artifacts.py dev --create-artifacts
```

### Verify Artifact Ownership

After creation, verify in Fabric portal:
1. Open the workspace
2. Click on an artifact (e.g., lakehouse)
3. Check artifact settings/properties
4. Verify created by service principal

---

## 🚨 Troubleshooting

### Issue: "Authentication validation failed"

**Solution:** Check that:
- Service principal client ID is correct in config file
- Secret environment variable name matches config
- Secret is set in pipeline/environment variables
- Service principal has not expired

### Issue: "Artifact already exists" error

**Solution:** 
- Set `create_if_not_exists: true` in config
- Script will skip existing artifacts automatically

### Issue: "Permission denied" during artifact creation

**Solution:**
- Verify service principal has "Admin" role in workspace
- Check service principal hasn't been removed from workspace
- Verify workspace ID is correct in config

### Issue: Wrong service principal used for environment

**Solution:**
- Check config file has correct `service_principal` section
- Verify secret environment variable name is correct
- Check pipeline is using correct secret for that environment

---

## 📚 Examples

### Example 1: Add Lakehouse to All Environments

**Step 1:** Add to dev.json:
```json
"lakehouses": [
  {
    "name": "MarketingDataLakehouse",
    "description": "Lakehouse for marketing campaign data",
    "create_if_not_exists": true
  }
]
```

**Step 2:** Test in Dev:
```bash
git add config/dev.json
git commit -m "Add MarketingDataLakehouse to dev"
git push origin development
# Watch pipeline create the lakehouse
```

**Step 3:** Add to uat.json and prod.json with same structure

**Step 4:** Promote through environments via PRs

### Example 2: Add Spark Environment with Libraries

```json
"environments": [
  {
    "name": "MLEnvironment",
    "description": "Machine learning environment with required libraries",
    "create_if_not_exists": true,
    "libraries": [
      {"type": "PyPI", "name": "scikit-learn", "version": "1.3.0"},
      {"type": "PyPI", "name": "xgboost", "version": "2.0.0"},
      {"type": "PyPI", "name": "matplotlib", "version": "3.7.0"}
    ]
  }
]
```

### Example 3: Create Multiple Artifacts at Once

```json
"artifacts_to_create": {
  "lakehouses": [
    {"name": "Bronze", "description": "Raw data", "create_if_not_exists": true},
    {"name": "Silver", "description": "Cleaned data", "create_if_not_exists": true},
    {"name": "Gold", "description": "Curated data", "create_if_not_exists": true}
  ],
  "environments": [
    {"name": "DataEngEnvironment", "description": "DE environment", "create_if_not_exists": true}
  ]
}
```

---

## 🔒 Security Checklist

- [ ] Created separate service principal for each environment
- [ ] Each SP only has access to its designated environment
- [ ] Secrets are stored in secure pipeline variables
- [ ] Secret environment variable names are unique per environment
- [ ] Production SP has strongest security controls
- [ ] Secret rotation schedule is documented
- [ ] Access to production secrets is restricted
- [ ] Audit logging is enabled for all deployments
- [ ] Emergency rollback procedures are documented

---

## 📝 Migration from Single SP to Per-Environment SPs

If you're currently using a single service principal:

1. **Create two new service principals** (keep existing as Dev SP)
2. **Update config files** with new SP details
3. **Add new secrets** to pipeline (don't remove old one yet)
4. **Test Dev deployment** with new Dev SP config
5. **Test UAT deployment** with UAT SP
6. **Test Prod deployment** with Prod SP
7. **Remove old single SP secret** once all working
8. **Update documentation** with new setup

---

## 🎯 Summary

With these enhancements:

✅ Each environment has its own dedicated service principal
✅ Artifacts can be defined in config files and created automatically
✅ Service principals own the artifacts they create
✅ Security is improved through isolation
✅ Configuration is fully version-controlled
✅ Deployments are more automated and consistent

For questions or issues, refer to the main README.md or open an issue in the repository.
