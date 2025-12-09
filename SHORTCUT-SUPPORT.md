# Shortcut Support - Implementation Summary

## Overview

Extended the config-driven artifact creation to support **Lakehouse Shortcuts**, enabling creation of OneLake and ADLS Gen2 shortcuts through configuration files.

---

## What Was Added

### 1. Dependency Resolver Update

**scripts/dependency_resolver.py:**
- Added `SHORTCUT` to `ArtifactType` enum
- Added shortcuts to `DEPENDENCY_PRIORITY` (priority 4, after lakehouses/environments, before notebooks)
- Ensures shortcuts are created after their target lakehouses exist

### 2. Fabric Client Enhancement

**scripts/fabric_client.py:**

Added complete shortcut management API:

#### New Methods:
- `list_shortcuts(workspace_id, lakehouse_id, path)` - List existing shortcuts
- `create_shortcut(workspace_id, lakehouse_id, name, path, target)` - Create new shortcut
- `get_shortcut(workspace_id, lakehouse_id, path, name)` - Get shortcut details
- `delete_shortcut(workspace_id, lakehouse_id, path, name)` - Delete shortcut

#### Supported Shortcut Types:
- **OneLake** - Link to another Fabric lakehouse
- **ADLS Gen2** - Link to Azure Data Lake Storage Gen2
- **S3** - Link to Amazon S3 (requires connection setup)

### 3. Deployment Script Enhancement

**scripts/deploy_artifacts.py:**

Added shortcut creation logic in `create_artifacts_from_config()`:
- Processes `shortcuts` array from configuration
- Resolves lakehouse names to IDs
- Checks for existing shortcuts before creating
- Supports both OneLake and ADLS Gen2 targets
- Respects `create_if_not_exists` flag

### 4. Configuration Files Updated

All three environment configs now include shortcuts examples:

**config/dev.json, uat.json, prod.json:**
```json
{
  "artifacts_to_create": {
    "shortcuts": [
      {
        "name": "SharedData",
        "description": "OneLake shortcut to shared data",
        "lakehouse": "SalesDataLakehouse",
        "path": "Tables",
        "create_if_not_exists": true,
        "target": {
          "oneLake": {
            "workspaceId": "shared-workspace-id",
            "itemId": "shared-lakehouse-id",
            "path": "Tables/MasterData"
          }
        }
      }
    ]
  }
}
```

---

## Configuration Examples

### OneLake Shortcut

Link to another Fabric lakehouse (cross-workspace or same workspace):

```json
{
  "name": "SharedMasterData",
  "description": "Link to master data lakehouse",
  "lakehouse": "MyLakehouse",
  "path": "Tables",
  "create_if_not_exists": true,
  "target": {
    "oneLake": {
      "workspaceId": "source-workspace-guid",
      "itemId": "source-lakehouse-guid",
      "path": "Tables/MasterData"
    }
  }
}
```

**Use Cases:**
- Share reference/master data across workspaces
- Link to centralized data catalogs
- Cross-environment data access (dev accessing shared data)
- Data mesh architectures

### ADLS Gen2 Shortcut

Link to Azure Data Lake Storage Gen2:

```json
{
  "name": "ExternalStorage",
  "description": "Link to ADLS Gen2 storage",
  "lakehouse": "MyLakehouse",
  "path": "Files",
  "create_if_not_exists": true,
  "target": {
    "adlsGen2": {
      "location": "https://storageaccount.dfs.core.windows.net/container/path",
      "connectionId": "connection-guid"
    }
  }
}
```

**Use Cases:**
- Access external data sources
- Link to existing data lakes
- Hybrid cloud architectures
- Data migration scenarios

**Prerequisites:**
- Connection must be created in Fabric first
- Service principal needs access to ADLS
- Connection ID from Fabric connections settings

### S3 Shortcut

Link to Amazon S3 (requires connection configuration):

```json
{
  "name": "S3Data",
  "description": "Link to S3 bucket",
  "lakehouse": "MyLakehouse",
  "path": "Files",
  "create_if_not_exists": true,
  "target": {
    "s3": {
      "location": "s3://bucket-name/path",
      "connectionId": "s3-connection-guid"
    }
  }
}
```

---

## Shortcut Paths

Shortcuts can be created in two locations:

| Path | Description | Typical Use |
|------|-------------|-------------|
| `Tables` | Delta Lake tables | Structured data, queryable tables |
| `Files` | Raw files | Parquet, CSV, JSON, unstructured data |

---

## Usage

### Create Shortcuts from Configuration

```bash
# Dry run to preview
python scripts/deploy_artifacts.py dev --create-artifacts --dry-run

# Create all configured artifacts including shortcuts
python scripts/deploy_artifacts.py dev --create-artifacts

# Create and deploy
python scripts/deploy_artifacts.py dev --create-artifacts
```

### Output Example

```
Processing shortcut: SharedData
  Lakehouse: SalesDataLakehouse found (ID: abc-123)
  ✓ Created shortcut 'SharedData' in SalesDataLakehouse/Tables

Processing shortcut: ExternalFiles
  Lakehouse: SalesDataLakehouse found (ID: abc-123)
  ✓ Created shortcut 'ExternalFiles' in SalesDataLakehouse/Files
```

---

## Benefits

### 1. Declarative Shortcuts
Define shortcuts in version-controlled config files

### 2. Environment-Specific Targets
Different source workspaces/storage accounts per environment:
- Dev shortcuts → Dev shared workspace
- UAT shortcuts → UAT shared workspace
- Prod shortcuts → Prod shared workspace

### 3. Automated Setup
No manual shortcut creation through UI

### 4. Idempotent Operations
`create_if_not_exists` prevents errors on redeployment

### 5. Dependency Management
Shortcuts created after lakehouses, ensuring targets exist

---

## Best Practices

### 1. Use Environment-Specific IDs
```json
// dev.json
"workspaceId": "dev-shared-workspace-id"

// prod.json
"workspaceId": "prod-shared-workspace-id"
```

### 2. Document Connection IDs
Keep connection IDs in configuration for traceability

### 3. Organize by Path
- Use `Tables` for structured, queryable data
- Use `Files` for raw, unstructured data

### 4. Naming Conventions
Use descriptive names indicating source:
- `SharedMasterData`
- `ExternalRawFiles`
- `CentralizedCatalog`

### 5. Security Considerations
- Ensure service principal has access to source lakehouses
- For ADLS, configure proper RBAC on storage accounts
- Use managed identities where possible

---

## Common Scenarios

### Scenario 1: Shared Master Data

**Problem:** Multiple projects need access to centralized master data

**Solution:**
```json
{
  "name": "MasterDataCatalog",
  "lakehouse": "MyLakehouse",
  "path": "Tables",
  "target": {
    "oneLake": {
      "workspaceId": "master-data-workspace-id",
      "itemId": "master-data-lakehouse-id",
      "path": "Tables"
    }
  }
}
```

### Scenario 2: External Data Integration

**Problem:** Need to access data from existing ADLS Gen2 storage

**Solution:**
```json
{
  "name": "LegacyData",
  "lakehouse": "MyLakehouse",
  "path": "Files",
  "target": {
    "adlsGen2": {
      "location": "https://legacy.dfs.core.windows.net/data/archive",
      "connectionId": "adls-connection-id"
    }
  }
}
```

### Scenario 3: Cross-Environment Access

**Problem:** Dev environment needs read-only access to UAT data

**Solution:**
```json
// config/dev.json
{
  "name": "UATReference",
  "lakehouse": "DevLakehouse",
  "path": "Tables",
  "target": {
    "oneLake": {
      "workspaceId": "uat-workspace-id",
      "itemId": "uat-lakehouse-id",
      "path": "Tables/ProcessedData"
    }
  }
}
```

---

## Troubleshooting

### Issue: Lakehouse Not Found

**Error:** `Lakehouse 'MyLakehouse' not found`

**Solution:**
- Ensure lakehouse is created first (lakehouses have priority 1)
- Check lakehouse name matches exactly
- Verify lakehouse exists in target workspace

### Issue: Permission Denied

**Error:** `403 Forbidden when creating shortcut`

**Solution:**
- Verify service principal has Admin or Contributor role on workspace
- For OneLake shortcuts, SP needs read access to source workspace
- For ADLS shortcuts, SP needs appropriate RBAC on storage account

### Issue: Connection Not Found

**Error:** `Connection with ID 'xxx' not found`

**Solution:**
- Create connection in Fabric first (Settings → Manage connections)
- Copy correct connection ID to configuration
- Ensure connection is in the same workspace

### Issue: Shortcut Already Exists

**Behavior:** Logs "Shortcut already exists" and continues

**Expected:** This is normal with `create_if_not_exists: true`

**Action:** No action needed, idempotent operation working correctly

---

## API Reference

### Fabric REST API Endpoints Used

```
GET    /workspaces/{workspaceId}/lakehouses/{lakehouseId}/shortcuts
POST   /workspaces/{workspaceId}/lakehouses/{lakehouseId}/shortcuts
GET    /workspaces/{workspaceId}/lakehouses/{lakehouseId}/shortcuts/{path}/{name}
DELETE /workspaces/{workspaceId}/lakehouses/{lakehouseId}/shortcuts/{path}/{name}
```

### Request Payload Structure

```json
{
  "name": "shortcut-name",
  "path": "Tables",
  "target": {
    "oneLake": {
      "workspaceId": "guid",
      "itemId": "guid",
      "path": "Tables/TableName"
    }
  }
}
```

---

## Complete Configuration Example

```json
{
  "service_principal": {
    "client_id": "your-sp-client-id",
    "tenant_id": "your-tenant-id",
    "secret_env_var": "AZURE_CLIENT_SECRET_DEV"
  },
  "workspace": {
    "id": "workspace-id",
    "name": "workspace-name"
  },
  "artifacts_to_create": {
    "lakehouses": [
      {
        "name": "SalesDataLakehouse",
        "description": "Sales data storage",
        "create_if_not_exists": true
      }
    ],
    "shortcuts": [
      {
        "name": "SharedMasterData",
        "description": "OneLake shortcut to master data",
        "lakehouse": "SalesDataLakehouse",
        "path": "Tables",
        "create_if_not_exists": true,
        "target": {
          "oneLake": {
            "workspaceId": "master-workspace-id",
            "itemId": "master-lakehouse-id",
            "path": "Tables/Customers"
          }
        }
      },
      {
        "name": "ExternalRawData",
        "description": "ADLS shortcut to raw files",
        "lakehouse": "SalesDataLakehouse",
        "path": "Files",
        "create_if_not_exists": true,
        "target": {
          "adlsGen2": {
            "location": "https://storage.dfs.core.windows.net/raw/sales",
            "connectionId": "adls-connection-id"
          }
        }
      }
    ]
  }
}
```

---

## Summary

Shortcut support completes the infrastructure-as-code capability for Fabric:

### Supported Artifacts (Complete):
- ✅ Lakehouses
- ✅ Environments (with libraries)
- ✅ KQL Databases
- ✅ Notebooks (with templates)
- ✅ Spark Job Definitions
- ✅ Data Pipelines
- ✅ **Shortcuts** (OneLake, ADLS Gen2, S3)

### Key Features:
- Declarative shortcut configuration
- Environment-specific targets
- Automatic lakehouse resolution
- Idempotent operations
- OneLake and ADLS Gen2 support
- Proper dependency ordering

### Files Modified:
1. scripts/dependency_resolver.py - Added SHORTCUT artifact type
2. scripts/fabric_client.py - Added shortcut API methods
3. scripts/deploy_artifacts.py - Added shortcut creation logic
4. config/dev.json - Added shortcuts configuration
5. config/uat.json - Added shortcuts configuration
6. config/prod.json - Added shortcuts configuration
7. README.md - Updated supported artifacts list
8. QUICK-REFERENCE.md - Added shortcut examples
9. PER-ENVIRONMENT-SP-GUIDE.md - Added shortcut documentation

The system now provides **complete data platform automation** including external data integration via shortcuts! 🎉
