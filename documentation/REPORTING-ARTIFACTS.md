# Power BI and Reporting Artifacts Support

This guide explains how to deploy Power BI reports, paginated reports, and semantic models using the Fabric CI/CD pipeline.

## Overview

The deployment system now supports three reporting artifact types:

1. **Semantic Models** (Power BI Datasets) - Data models with relationships and measures
2. **Power BI Reports** - Interactive visualizations connected to semantic models
3. **Paginated Reports** - Pixel-perfect formatted reports for printing/export

## Deployment Order

Artifacts deploy in dependency order:

```
1. Lakehouses (Priority 1)
2. Environments (Priority 2)
3. KQL Databases (Priority 3)
4. Shortcuts (Priority 4)
5. Semantic Models (Priority 5) ← Data models first
6. Notebooks (Priority 6)
7. Spark Jobs (Priority 7)
8. KQL Querysets (Priority 8)
9. Power BI Reports (Priority 9) ← Then reports
10. Paginated Reports (Priority 10)
11. Eventstreams (Priority 11)
12. Data Pipelines (Priority 12)
```

**Important:** Semantic models deploy before reports because reports reference semantic models.

## Configuration-Driven Creation

### Semantic Models

Add to `config/dev.json` (or uat.json, prod.json):

```json
{
  "artifacts_to_create": {
    "semantic_models": [
      {
        "name": "SalesAnalyticsModel",
        "description": "Semantic model for sales analytics",
        "create_if_not_exists": true
      },
      {
        "name": "InventoryModel",
        "description": "Inventory tracking model",
        "create_if_not_exists": true
      }
    ]
  }
}
```

The system will create a basic semantic model definition. You can then:
- Connect to data sources (lakehouses, SQL, etc.)
- Define relationships between tables
- Add DAX measures and calculated columns
- Configure refresh schedules

### Power BI Reports

Add to `config/dev.json`:

```json
{
  "artifacts_to_create": {
    "reports": [
      {
        "name": "SalesDashboard",
        "description": "Executive sales dashboard",
        "semantic_model": "SalesAnalyticsModel",
        "create_if_not_exists": true
      },
      {
        "name": "RegionalSalesReport",
        "description": "Regional sales performance",
        "semantic_model": "SalesAnalyticsModel",
        "create_if_not_exists": true
      }
    ]
  }
}
```

**Note:** The `semantic_model` field references an existing semantic model. Ensure the semantic model exists before deploying the report.

### Paginated Reports

Add to `config/dev.json`:

```json
{
  "artifacts_to_create": {
    "paginated_reports": [
      {
        "name": "MonthlySalesReport",
        "description": "Detailed monthly sales report for printing",
        "create_if_not_exists": true
      },
      {
        "name": "InvoiceTemplate",
        "description": "Customer invoice template",
        "create_if_not_exists": true
      }
    ]
  }
}
```

Paginated reports are ideal for:
- Formatted documents (invoices, statements)
- Multi-page operational reports
- Print-ready layouts
- PDF exports

## File-Based Deployment

Place report definition files in these folders:

```
fabcicd/
├── semanticmodels/
│   ├── SalesAnalyticsModel.json
│   └── InventoryModel.json
├── reports/
│   ├── SalesDashboard.json
│   └── RegionalSalesReport.json
└── paginatedreports/
    ├── MonthlySalesReport.json
    └── InvoiceTemplate.json
```

### Semantic Model Definition Format

```json
{
  "displayName": "SalesAnalyticsModel",
  "description": "Sales analytics semantic model",
  "dataModel": {
    "tables": [
      {
        "name": "Sales",
        "source": {
          "type": "lakehouse",
          "lakehouseId": "lakehouse-guid",
          "table": "FactSales"
        }
      }
    ],
    "relationships": [
      {
        "name": "SalesDate",
        "fromTable": "Sales",
        "fromColumn": "DateKey",
        "toTable": "Date",
        "toColumn": "DateKey"
      }
    ],
    "measures": [
      {
        "name": "TotalSales",
        "expression": "SUM(Sales[Amount])"
      }
    ]
  }
}
```

### Power BI Report Definition Format

```json
{
  "displayName": "SalesDashboard",
  "description": "Executive sales dashboard",
  "datasetId": "semantic-model-guid",
  "pages": [
    {
      "name": "Overview",
      "visuals": []
    }
  ]
}
```

### Paginated Report Definition Format

```json
{
  "displayName": "MonthlySalesReport",
  "description": "Monthly sales report",
  "reportDefinition": {
    "dataSource": "SalesAnalyticsModel",
    "parameters": [
      {
        "name": "Month",
        "type": "String"
      }
    ]
  }
}
```

## Update Behavior

All reporting artifacts support updates:

| Artifact Type | Create | Update | Delete |
|--------------|--------|--------|--------|
| Semantic Models | ✅ | ✅ | ❌ |
| Power BI Reports | ✅ | ✅ | ❌ |
| Paginated Reports | ✅ | ✅ | ❌ |

**Update Process:**
1. System checks if artifact exists (by name)
2. If exists: Updates definition using `updateDefinition` API
3. If not exists: Creates new artifact

## Deployment Examples

### Create All Reporting Artifacts

```bash
# Deploy with config-driven creation
python scripts/deploy_artifacts.py dev --create-artifacts

# Dry run first
python scripts/deploy_artifacts.py dev --create-artifacts --dry-run
```

### Deploy Only Semantic Models

```bash
# Create only semantic models from config
python scripts/deploy_artifacts.py dev --create-artifacts
# (Then manually filter or use selective deployment)
```

### Update Existing Reports

```bash
# Update reports from files
python scripts/deploy_artifacts.py dev

# This will:
# 1. Discover report definitions in reports/ folder
# 2. Check if reports exist in workspace
# 3. Update existing reports OR create new ones
```

## Best Practices

### 1. Semantic Model First

Always create semantic models before reports:

```json
{
  "artifacts_to_create": {
    "semantic_models": [
      {"name": "SalesModel", ...}
    ],
    "reports": [
      {"name": "SalesDashboard", "semantic_model": "SalesModel", ...}
    ]
  }
}
```

### 2. Development Workflow

1. **Dev Environment:**
   - Create initial semantic model from config
   - Design model in Power BI Desktop or Fabric portal
   - Export definition to `semanticmodels/` folder
   - Commit to development branch

2. **UAT Environment:**
   - Deploy via CI/CD
   - Validate data connections work
   - Test refresh schedules

3. **Production:**
   - Deploy via CI/CD with approval
   - Monitor refresh success

### 3. Parameter Substitution

Use environment-specific values:

**dev.json:**
```json
{
  "semantic_models": [
    {
      "name": "SalesModel",
      "connection": {
        "lakehouse": "SalesDataLakehouse",
        "workspace": "${workspace_id}"
      }
    }
  ]
}
```

The `${workspace_id}` will be substituted per environment.

### 4. Version Control

**Commit these files:**
- ✅ `semanticmodels/*.json` - Model definitions
- ✅ `reports/*.json` - Report definitions
- ✅ `paginatedreports/*.json` - Paginated report definitions
- ✅ `config/*.json` - Configuration files

**Don't commit:**
- ❌ `.pbix` files (use definition files instead)
- ❌ Cached data or temporary files

### 5. Testing

```bash
# Validate semantic model
python scripts/deploy_artifacts.py dev --dry-run

# Check logs for:
# - Model creation/update
# - Relationship validation
# - Measure syntax
```

## API Methods

The deployment system uses these Fabric APIs:

### Semantic Models
- `GET /workspaces/{workspaceId}/semanticModels` - List models
- `POST /workspaces/{workspaceId}/semanticModels` - Create model
- `POST /workspaces/{workspaceId}/semanticModels/{modelId}/updateDefinition` - Update model

### Power BI Reports
- `GET /workspaces/{workspaceId}/reports` - List reports
- `POST /workspaces/{workspaceId}/reports` - Create report
- `POST /workspaces/{workspaceId}/reports/{reportId}/updateDefinition` - Update report

### Paginated Reports
- `GET /workspaces/{workspaceId}/paginatedReports` - List paginated reports
- `POST /workspaces/{workspaceId}/paginatedReports` - Create paginated report
- `POST /workspaces/{workspaceId}/paginatedReports/{reportId}/updateDefinition` - Update paginated report

## Troubleshooting

### Issue: Report Creation Fails

**Symptom:** `HTTP 400: Dataset not found`

**Solution:** Ensure semantic model exists first:

```bash
# Check semantic models
python scripts/fabric_client.py list-semantic-models dev

# Create semantic model first
python scripts/deploy_artifacts.py dev --create-artifacts
```

### Issue: Update Not Applying

**Symptom:** Changes in JSON file not reflected in workspace

**Solution:**
1. Verify file is in correct folder (`reports/`, `semanticmodels/`, etc.)
2. Check file name matches artifact name
3. Run deployment:
   ```bash
   python scripts/deploy_artifacts.py dev
   ```

### Issue: Permission Denied

**Symptom:** `HTTP 403: Forbidden`

**Solution:** Grant service principal permissions:
1. Workspace Admin role
2. Power BI API permissions (if using Power BI-specific features)

### Issue: Semantic Model Refresh Fails

**Symptom:** Model created but data refresh fails

**Solution:**
1. Verify lakehouse/data source credentials
2. Check connection strings in model definition
3. Ensure service principal has read access to data sources

## Complete Example

Here's a complete configuration for a sales analytics solution:

**config/dev.json:**
```json
{
  "environment": "dev",
  "service_principal": {
    "client_id": "your-dev-client-id",
    "tenant_id": "your-tenant-id",
    "secret_env_var": "AZURE_CLIENT_SECRET_DEV"
  },
  "workspace": {
    "id": "dev-workspace-id",
    "name": "DataEng-Dev"
  },
  "artifacts_to_create": {
    "lakehouses": [
      {
        "name": "SalesDataLakehouse",
        "description": "Sales data storage",
        "create_if_not_exists": true
      }
    ],
    "semantic_models": [
      {
        "name": "SalesAnalyticsModel",
        "description": "Sales semantic model",
        "create_if_not_exists": true
      }
    ],
    "reports": [
      {
        "name": "SalesExecutiveDashboard",
        "description": "Executive dashboard",
        "semantic_model": "SalesAnalyticsModel",
        "create_if_not_exists": true
      },
      {
        "name": "RegionalPerformance",
        "description": "Regional sales performance",
        "semantic_model": "SalesAnalyticsModel",
        "create_if_not_exists": true
      }
    ],
    "paginated_reports": [
      {
        "name": "MonthlySalesDetailReport",
        "description": "Detailed monthly report",
        "create_if_not_exists": true
      }
    ]
  }
}
```

**Deployment:**
```bash
# 1. Create artifacts from config
python scripts/deploy_artifacts.py dev --create-artifacts --dry-run

# 2. Deploy for real
python scripts/deploy_artifacts.py dev --create-artifacts

# 3. Update semantic model definition (after designing in portal)
# ... export model definition to semanticmodels/SalesAnalyticsModel.json ...

# 4. Deploy updates
python scripts/deploy_artifacts.py dev
```

## See Also

- **[DEPLOYMENT-BEHAVIOR.md](DEPLOYMENT-BEHAVIOR.md)** - Update behavior details
- **[QUICK-REFERENCE.md](QUICK-REFERENCE.md)** - Quick command reference
- **[PER-ENVIRONMENT-SP-GUIDE.md](PER-ENVIRONMENT-SP-GUIDE.md)** - Service principal setup
- **[README.md](README.md)** - Main documentation
