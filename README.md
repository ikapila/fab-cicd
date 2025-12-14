# Microsoft Fabric Data Engineering CI/CD

A complete CI/CD solution for deploying Microsoft Fabric Data Engineering artifacts across Dev → UAT → Prod environments using Git integration and automated pipelines.

## 🎯 Overview

This repository provides an end-to-end automated deployment solution for Microsoft Fabric Data Engineering artifacts including:

- **Notebooks** - Spark notebooks for data processing
- **Spark Job Definitions** - Reusable Spark jobs
- **Data Pipelines** - Orchestration workflows
- **Lakehouses** - Data storage layer
- **Environments** - Runtime configurations
- **KQL Databases & Querysets** - Real-time analytics
- **Eventstreams** - Streaming data ingestion

## 📋 Features

✅ Multi-environment deployment (Dev, UAT, Prod)  
✅ **Per-environment service principals** for enhanced security  
✅ **Config-driven artifact creation** with SP ownership  
✅ Automated CI/CD pipelines (Azure DevOps & GitHub Actions)  
✅ Dependency resolution and deployment ordering  
✅ Environment-specific parameter substitution  
✅ Manual approval gates for UAT and Production  
✅ Rollback capabilities  
✅ Artifact validation and testing  
✅ Deployment monitoring and notifications  

## 🏗️ Architecture

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   Dev Env   │      │   UAT Env   │      │  Prod Env   │
│ (Workspace) │ ───▶ │ (Workspace) │ ───▶ │ (Workspace) │
└─────────────┘      └─────────────┘      └─────────────┘
      │                     │                     │
      ▼                     ▼                     ▼
 development              uat                  main
   branch                branch               branch
      │                     │                     │
      └─────────────────────┴─────────────────────┘
                            │
                     Git Repository
```

## 📁 Repository Structure

```
fabric-data-engineering/
├── notebooks/                  # Fabric notebooks (.ipynb)
├── sparkjobdefinitions/        # Spark job definitions
├── datapipelines/              # Data pipeline definitions
├── lakehouses/                 # Lakehouse definitions
├── environments/               # Environment definitions
├── config/                     # Environment-specific configs
│   ├── dev.json
│   ├── uat.json
│   └── prod.json
├── scripts/                    # Deployment automation scripts
│   ├── fabric_auth.py          # Authentication handler
│   ├── fabric_client.py        # REST API client
│   ├── config_manager.py       # Configuration management
│   ├── dependency_resolver.py  # Dependency tracking
│   ├── deploy_artifacts.py     # Main deployment script
│   └── requirements.txt        # Python dependencies
├── .github/workflows/          # GitHub Actions workflows
│   └── deploy.yml
├── azure-pipelines.yml         # Azure DevOps pipeline
├── implementation-plan.md      # Detailed implementation guide
└── README.md                   # This file
```

## 🚀 Quick Start

### Prerequisites

1. **Microsoft Fabric Subscription** with Premium or Fabric capacity
2. **Azure Service Principals** - One per environment (Dev, UAT, Prod) with workspace access
3. **Git Repository** (Azure DevOps or GitHub)
4. **Python 3.11+** installed locally
5. **Azure CLI** (optional, for local testing)

### Step 1: Set Up Fabric Workspaces

Create three workspaces in Microsoft Fabric:

```
DataEng-Dev   (Development)
DataEng-UAT   (UAT)
DataEng-Prod  (Production)
```

### Step 2: Create Service Principals (One Per Environment)

1. Go to Azure Portal → Azure Entra ID → App registrations
2. Create three service principals:
   - `fabric-cicd-dev-sp` for Development
   - `fabric-cicd-uat-sp` for UAT
   - `fabric-cicd-prod-sp` for Production
3. For each SP, copy **Application (client) ID**, **Tenant ID**, and **secret value**
4. Add Dev SP to Dev workspace with **Admin** role
5. Add UAT SP to UAT workspace with **Admin** role
6. Add Prod SP to Prod workspace with **Admin** role

**See [PER-ENVIRONMENT-SP-GUIDE.md](PER-ENVIRONMENT-SP-GUIDE.md) for detailed setup instructions**

### Step 3: Configure Repository

1. Clone this repository:
   ```bash
   git clone <your-repo-url>
   cd fabric-data-engineering
   ```

2. Create branch structure:
   ```bash
   git checkout -b main
   git checkout -b development
   git checkout -b uat
   ```

3. Update configuration files in `config/` directory with your workspace IDs and parameters

### Step 4: Set Up Secrets (Per Environment)

#### For Azure DevOps:
1. Go to Pipelines → Library → Variable groups
2. Create variable group: `fabric-secrets`
3. Add environment-specific secrets:
   - `AZURE_CLIENT_SECRET_DEV` - Development SP secret
   - `AZURE_CLIENT_SECRET_UAT` - UAT SP secret
   - `AZURE_CLIENT_SECRET_PROD` - Production SP secret

#### For GitHub Actions:
1. Go to Settings → Secrets and variables → Actions
2. Add repository secrets:
   - `AZURE_CLIENT_SECRET_DEV`
   - `AZURE_CLIENT_SECRET_UAT`
   - `AZURE_CLIENT_SECRET_PROD`

**Note:** Each environment uses its own service principal for enhanced security.

### Step 5: Connect Dev Workspace to Git

1. Open `DataEng-Dev` workspace in Fabric
2. Go to Workspace settings → Git integration
3. Connect to your repository
4. Select `development` branch
5. Commit existing artifacts

## 🔧 Configuration

### Environment Configuration Files

Each environment has a configuration file in `config/`:

**config/dev.json:**
```json
{
  "workspace": {
    "id": "your-workspace-guid",
    "name": "DataEng-Dev"
  },
  "parameters": {
    "storage_account": "devstorageaccount",
    "key_vault_url": "https://dev-kv.vault.azure.net/",
    "data_lake_path": "abfss://dev@devstorageaccount.dfs.core.windows.net/"
  }
}
```

### Parameter Substitution

Use `{{parameter_name}}` placeholders in your artifacts. They will be automatically replaced with environment-specific values during deployment.

**Example Notebook:**
```python
# Cell 1
storage_account = "{{storage_account}}"
data_lake_path = "{{data_lake_path}}"

# Cell 2
df = spark.read.parquet(f"{data_lake_path}/raw/sales.parquet")
```

### Config-Driven Artifact Creation

Define artifacts in your configuration files to have them automatically created with service principal ownership:

**config/dev.json:**
```json
{
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
        "name": "DevSparkEnvironment",
        "description": "Development Spark environment",
        "create_if_not_exists": true,
        "libraries": [
          {"type": "PyPI", "name": "pandas", "version": "2.1.0"}
        ]
      }
    ],
    "notebooks": [
      {
        "name": "DataPreparation",
        "description": "Data preparation notebook",
        "template": "basic_spark",
        "default_lakehouse": "SalesDataLakehouse",
        "create_if_not_exists": true
      }
    ],
    "spark_job_definitions": [
      {
        "name": "DailySalesProcessing",
        "description": "Daily sales processing job",
        "main_file": "notebooks/DataPreparation.ipynb",
        "default_lakehouse": "SalesDataLakehouse",
        "create_if_not_exists": true
      }
    ],
    "data_pipelines": [
      {
        "name": "SalesOrchestration",
        "description": "Sales data orchestration",
        "create_if_not_exists": true,
        "activities": [
          {
            "name": "RunDataPrep",
            "type": "Notebook",
            "typeProperties": {"notebookName": "DataPreparation"}
          }
        ]
      }
    ]
  }
}
```

**Supported Artifact Types:**
- ✅ Lakehouses
- ✅ Environments (with libraries)
- ✅ KQL Databases
- ✅ Notebooks (with templates: basic_spark, sql, empty)
- ✅ Spark Job Definitions (with configuration)
- ✅ Data Pipelines (with activities and parameters)
- ✅ Shortcuts (OneLake and ADLS Gen2)
- ✅ Variable Libraries (runtime environment variables)
- ✅ SQL Views (lakehouse analytics views with dependency management)
- ✅ Semantic Models (Power BI datasets)
- ✅ Power BI Reports
- ✅ Paginated Reports

Artifacts are automatically created during deployment. See **[PER-ENVIRONMENT-SP-GUIDE.md](PER-ENVIRONMENT-SP-GUIDE.md)** for details and **[QUICK-REFERENCE.md](QUICK-REFERENCE.md)** for quick examples.

## 🚀 Deployment Workflows

### Development Deployment

```bash
# Make changes in Dev workspace
# Commit to development branch
git add .
git commit -m "Add new sales processing notebook"
git push origin development
```

**Result:** Automatic deployment to Dev workspace

### UAT Deployment

```bash
# Create PR from development to uat
git checkout uat
git pull origin uat
gh pr create --base uat --head development --title "Deploy to UAT"
```

**Result:** 
1. Manual approval required
2. Automatic deployment to UAT workspace
3. Validation tests executed

### Production Deployment

```bash
# Create PR from uat to main
git checkout main
git pull origin main
gh pr create --base main --head uat --title "Deploy to Production"
```

**Result:**
1. Two manual approvals required
2. Production backup created
3. Automatic deployment to Production workspace
4. Production validation tests
5. Deployment notification sent

## 💻 Local Testing

### Install Dependencies

```bash
cd scripts
pip install -r requirements.txt
```

### Test Authentication (Per Environment)

```bash
# Test Dev SP
export AZURE_CLIENT_SECRET_DEV="your-dev-secret"
python fabric_auth.py

# Test UAT SP
export AZURE_CLIENT_SECRET_UAT="your-uat-secret"
python fabric_auth.py

# Test Prod SP
export AZURE_CLIENT_SECRET_PROD="your-prod-secret"
python fabric_auth.py
```

### Test Deployment (Dry Run)

```bash
python deploy_artifacts.py dev --dry-run
```

### Deploy Locally

```bash
python deploy_artifacts.py dev --config-dir ../config --artifacts-dir ..
```

## 📊 Monitoring and Validation

### Check Deployment Status

- **Azure DevOps:** Pipelines → Recent runs
- **GitHub Actions:** Actions tab → Workflows

### View Deployment Logs

All deployment steps are logged with timestamps and status information.

### Run Tests

```bash
# Run all tests
python scripts/run_tests.py --environment dev

# Run critical tests only
python scripts/run_tests.py --environment prod --critical-only
```

## 🔄 Rollback Procedures

### Manual Rollback

1. Identify the target commit SHA from Git history
2. Trigger rollback workflow:

**Azure DevOps:**
```bash
# Set pipeline variables:
ROLLBACK_ENVIRONMENT=prod
ROLLBACK_COMMIT_SHA=abc123def456
# Run Rollback stage manually
```

**GitHub Actions:**
```bash
# Go to Actions → Deploy workflow → Run workflow
# Select rollback option
# Enter target commit SHA
```

### Automated Rollback Script

```bash
python scripts/rollback.py --environment prod --commit abc123def456
```

## 🧪 Testing

### Validate Notebooks

```bash
python scripts/validate_notebooks.py
```

### Validate Pipelines

```bash
python scripts/validate_pipelines.py
```

### Check Dependencies

```bash
python scripts/dependency_resolver.py
```

## 📖 Detailed Documentation

- **[Implementation Plan](implementation-plan.md)** - Complete step-by-step implementation guide
- **[Per-Environment SP Guide](PER-ENVIRONMENT-SP-GUIDE.md)** - Setup guide for per-environment service principals and config-driven artifacts
- **[Original Plan](plan.md)** - High-level project plan and considerations

## 🛠️ Troubleshooting

### Common Issues

**Authentication Failed:**
- Verify service principal credentials
- Check workspace access permissions
- Ensure service principal has "Admin" role

**Deployment Failed:**
- Check deployment logs for specific errors
- Verify configuration files are correct
- Ensure all dependencies are defined

**Git Sync Issues:**
- Verify workspace Git connection
- Check branch protection rules
- Ensure proper permissions

### Debug Mode

Enable detailed logging:
```bash
export LOG_LEVEL=DEBUG
python scripts/deploy_artifacts.py dev
```

## 🤝 Contributing

1. Create a feature branch from `development`
2. Make your changes
3. Test locally with dry-run
4. Create PR to `development`
5. After review, merge and deploy

## 📝 Best Practices

1. **Always test in Dev first** before promoting to UAT/Prod
2. **Use descriptive commit messages** for audit trail
3. **Review deployment logs** after each deployment
4. **Keep dependencies updated** in artifact metadata
5. **Document parameter changes** in configuration files
6. **Test rollback procedures** regularly
7. **Monitor capacity usage** to avoid throttling

## 🔐 Security

- Service principal secrets are stored in Azure Key Vault or pipeline secrets
- Configuration files should NOT contain actual secrets
- Use parameter placeholders for sensitive values
- Enable audit logging for all deployments
- Review workspace access permissions regularly

## 📞 Support

For issues or questions:
1. Check troubleshooting section above
2. Review deployment logs
3. Consult implementation plan
4. Contact platform team

## 📄 License

[Your License Here]

## 🎉 Acknowledgments

Built with:
- Microsoft Fabric REST APIs
- Azure Identity SDK
- Python 3.11+
- Azure DevOps / GitHub Actions

---

**Happy Deploying! 🚀**
