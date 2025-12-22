# Quick Reference: Per-Environment Service Principals & Config-Driven Artifacts

## 📋 Service Principal Configuration

### In config files (dev.json, uat.json, prod.json):
```json
{
  "service_principal": {
    "client_id": "your-sp-client-id",
    "tenant_id": "your-tenant-id",
    "secret_env_var": "AZURE_CLIENT_SECRET_DEV"  // or _UAT or _PROD
  }
}
```

### Pipeline Secrets Required:
- `AZURE_CLIENT_SECRET_DEV` - Development SP secret
- `AZURE_CLIENT_SECRET_UAT` - UAT SP secret  
- `AZURE_CLIENT_SECRET_PROD` - Production SP secret

---

## 🏗️ Adding Artifacts via Configuration

### Lakehouse Example:
```json
"artifacts_to_create": {
  "lakehouses": [
    {
      "name": "MyLakehouse",
      "description": "Description here",
      "create_if_not_exists": true
    }
  ]
}
```

### Environment Example:
```json
"environments": [
  {
    "name": "MyEnvironment",
    "description": "Spark environment",
    "create_if_not_exists": true,
    "libraries": [
      {"type": "PyPI", "name": "pandas", "version": "2.1.0"}
    ]
  }
]
```

### KQL Database Example:
```json
"kql_databases": [
  {
    "name": "MyKQLDB",
    "description": "Real-time analytics DB",
    "create_if_not_exists": true
  }
]
```

### Notebook Example:
```json
"notebooks": [
  {
    "name": "MyNotebook",
    "description": "Data processing notebook",
    "template": "basic_spark",
    "default_lakehouse": "MyLakehouse",
    "create_if_not_exists": true
  }
]
```
**Templates:** `basic_spark` | `sql` | `empty`

### Spark Job Definition Example:
```json
"spark_job_definitions": [
  {
    "name": "MySparkJob",
    "description": "Scheduled data processing",
    "main_file": "notebooks/MyNotebook.ipynb",
    "default_lakehouse": "MyLakehouse",
    "create_if_not_exists": true,
    "configuration": {
      "spark.executor.memory": "4g"
    }
  }
]
```

### Data Pipeline Example:
```json
"data_pipelines": [
  {
    "name": "MyPipeline",
    "description": "Data orchestration pipeline",
    "create_if_not_exists": true,
    "parameters": {
      "date": {"type": "String", "defaultValue": "today"}
    },
    "activities": [
      {
        "name": "RunNotebook",
        "type": "Notebook",
        "typeProperties": {"notebookName": "MyNotebook"}
      }
    ]
  }
]
```

### Shortcut Examples:

**OneLake Shortcut:**
```json
"shortcuts": [
  {
    "name": "SharedData",
    "description": "Link to shared lakehouse",
    "lakehouse": "MyLakehouse",
    "path": "Tables",
    "create_if_not_exists": true,
    "target": {
      "oneLake": {
        "workspaceId": "source-workspace-id",
        "itemId": "source-lakehouse-id",
        "path": "Tables/SourceTable"
      }
    }
  }
]
```

**ADLS Gen2 Shortcut:**
```json
"shortcuts": [
  {
    "name": "ExternalData",
    "description": "Link to ADLS storage",
    "lakehouse": "MyLakehouse",
    "path": "Files",
    "create_if_not_exists": true,
    "target": {
      "adlsGen2": {
        "location": "https://storage.dfs.core.windows.net/container/path",
        "connectionId": "connection-guid"
      }
    }
  }
]
```

### Semantic Model Example:
```json
"semantic_models": [
  {
    "name": "SalesAnalyticsModel",
    "description": "Sales semantic model",
    "create_if_not_exists": true
  }
]
```

### Power BI Report Example:
```json
"reports": [
  {
    "name": "SalesDashboard",
    "description": "Executive sales dashboard",
    "semantic_model": "SalesAnalyticsModel",
    "create_if_not_exists": true
  }
]
```

### Paginated Report Example:
```json
"paginated_reports": [
  {
    "name": "MonthlySalesReport",
    "description": "Detailed monthly report",
    "create_if_not_exists": true
  }
]
```
  }
]
```
**Paths:** `Tables` | `Files`

---

## 💻 Command Line Usage

### Create artifacts only (no deployment):
```bash
python scripts/deploy_artifacts.py dev --create-artifacts --skip-discovery
```

### Create artifacts and deploy:
```bash
python scripts/deploy_artifacts.py dev --create-artifacts
```

### Deploy only changed artifacts (automatic change detection):
```bash
python scripts/deploy_artifacts.py dev
```

### Force deploy all artifacts (ignore change detection):
```bash
python scripts/deploy_artifacts.py dev --force-all
```

### Deploy specific artifacts only:
```bash
python scripts/deploy_artifacts.py dev --artifacts "Notebook1,Lakehouse1"
```

### Dry run (see what would happen):
```bash
python scripts/deploy_artifacts.py dev --create-artifacts --dry-run
```

### Local testing with environment-specific SP:
```bash
export AZURE_CLIENT_SECRET_DEV="your-dev-secret"
python scripts/deploy_artifacts.py dev --create-artifacts --dry-run
```

---

## 🔄 Deployment Flow

1. **Add artifact to config file** (e.g., config/dev.json)
2. **Commit and push** to development branch
3. **Pipeline automatically:**
   - Uses Dev SP credentials
   - Creates artifact if it doesn't exist
   - **Detects changed artifacts (deploys only modified)** ⚡
   - Deploys with dependency-aware ordering
4. **Promote via PR** to UAT, then Production

---

## ⚡ Change Detection (New!)

**Automatic** - Deploys only artifacts that changed since last deployment:
- 📊 ~80% faster for typical changes
- 🔗 Auto-includes dependent artifacts (e.g., SQL views)
- ⚙️ Config changes trigger full deployment
- 🛡️ Safe fallback to full deployment if needed

See `CHANGE-DETECTION.md` for complete documentation.

---

## ✅ Quick Setup Checklist

- [ ] Create 3 service principals (dev, uat, prod)
- [ ] Update config files with SP details
- [ ] Add 3 secrets to pipeline (per-environment)
- [ ] Add artifacts to `artifacts_to_create` section
- [ ] Test with dry-run
- [ ] Deploy!

---

## 📚 Documentation References

- **Full Guide:** PER-ENVIRONMENT-SP-GUIDE.md
- **Setup:** CHECKLIST.md
- **General Usage:** README.md
- **Implementation:** implementation-plan.md
