# Variable Library Integration Plan

## Overview

This document outlines the integration of **Microsoft Fabric Variable Library** into the CI/CD deployment system to enable centralized, environment-specific variable management.

## What is Variable Library?

Variable Library is a Fabric artifact type that:
- Stores environment-specific variables (strings, secrets, connections)
- Can be referenced by notebooks, pipelines, and other artifacts at runtime
- Provides centralized variable management within Fabric workspaces
- Supports Git integration for version control

## Current vs. Proposed Architecture

### Current Architecture
```
┌─────────────────────┐
│  config/dev.json    │──┐
├─────────────────────┤  │
│ parameters:         │  │ Deployment-time
│   storage_account   │  │ substitution
│   api_endpoint      │  │
│   batch_size        │  │
└─────────────────────┘  │
                         ↓
┌─────────────────────────────────┐
│  Notebook (deployed)            │
│  storage = "devstorageaccount"  │ ← Hard-coded after deployment
│  api = "https://dev-api..."     │
└─────────────────────────────────┘
```

**Issues:**
- Variables hard-coded into artifacts after deployment
- No runtime flexibility
- Hard to change without redeployment

### Proposed Architecture

```
┌─────────────────────┐
│  config/dev.json    │──┐
├─────────────────────┤  │
│ variable_library:   │  │ Deployment-time
│   name: DevVars     │  │ - Create/Update Variable Library
│   variables:        │  │ - Keep config for build-time needs
│     - storage_acct  │  │
│     - api_endpoint  │  │
└─────────────────────┘  │
                         ↓
┌─────────────────────────────────┐
│  Fabric Workspace (Dev)         │
│  ┌───────────────────────────┐  │
│  │  Variable Library: DevVars│  │ ← Deployed artifact
│  │  - storage_account        │  │
│  │  - api_endpoint           │  │
│  │  - batch_size             │  │
│  └───────────────────────────┘  │
│                ↓ Reference       │
│  ┌───────────────────────────┐  │
│  │  Notebook (deployed)      │  │
│  │  storage = mssparkutils   │  │ ← Runtime reference
│  │    .env.getVariables()    │  │
│  └───────────────────────────┘  │
└─────────────────────────────────┘
```

**Benefits:**
- Variables managed centrally in Fabric
- Runtime flexibility (change variables without redeployment)
- Cleaner separation: config files for deployment, Variable Library for runtime
- Support for secrets (encrypted in Fabric)

## Implementation Plan

### Phase 1: Add Variable Library Support to Deployment System

#### 1.1 Update Dependency Resolver
Add `VARIABLE_LIBRARY` to artifact types with priority 4 (after shortcuts, before semantic models).

**File:** `scripts/dependency_resolver.py`
```python
class ArtifactType(Enum):
    LAKEHOUSE = "lakehouse"
    ENVIRONMENT = "environment"
    KQL_DATABASE = "kqlDatabase"
    SHORTCUT = "shortcut"
    VARIABLE_LIBRARY = "variableLibrary"  # NEW
    SEMANTIC_MODEL = "semanticModel"
    # ... rest
```

#### 1.2 Add Variable Library API Methods
Add CRUD operations for Variable Library.

**File:** `scripts/fabric_client.py`
```python
# Variable Library operations
def list_variable_libraries(self, workspace_id: str) -> List[Dict]:
    """List Variable Libraries in workspace"""
    
def create_variable_library(self, workspace_id: str, name: str, description: str = "") -> Dict:
    """Create a Variable Library"""
    
def get_variable_library(self, workspace_id: str, library_id: str) -> Dict:
    """Get Variable Library details"""
    
def get_variable_library_definition(self, workspace_id: str, library_id: str) -> Dict:
    """Get Variable Library definition (variables)"""
    
def update_variable_library_definition(self, workspace_id: str, library_id: str, definition: Dict) -> Dict:
    """Update Variable Library definition (variables)"""
```

#### 1.3 Add Deployment Logic
Add Variable Library deployment with update support.

**File:** `scripts/deploy_artifacts.py`
```python
def _deploy_variable_library(self, library_def: Dict, dry_run: bool = False) -> bool:
    """
    Deploy a Variable Library
    - Creates if doesn't exist
    - Updates variables if exists
    """
    
def _discover_variable_libraries(self) -> None:
    """Discover Variable Library definitions from variablelibraries/ folder"""
    
def _create_variable_library_template(self, config: Dict) -> Dict:
    """Create Variable Library definition from config"""
```

#### 1.4 Update Configuration Schema
Add `variable_libraries` section to config files.

**File:** `config/dev.json` (example)
```json
{
  "variable_library": {
    "name": "DevVariables",
    "description": "Development environment variables",
    "auto_deploy": true,
    "variables": [
      {
        "name": "storage_account",
        "value": "devstorageaccount",
        "type": "String"
      },
      {
        "name": "api_endpoint",
        "value": "https://dev-api.company.com",
        "type": "String"
      },
      {
        "name": "batch_size",
        "value": "100",
        "type": "Int"
      },
      {
        "name": "enable_monitoring",
        "value": "false",
        "type": "Bool"
      },
      {
        "name": "sql_connection_string",
        "value": "Server=dev-sql-server.database.windows.net;",
        "type": "Secret"
      }
    ]
  },
  "artifacts_to_create": {
    "variable_libraries": [
      {
        "name": "DevVariables",
        "description": "Development environment variables",
        "create_if_not_exists": true
      }
    ]
  }
}
```

### Phase 2: Create Variable Library Definition Format

#### 2.1 Variable Library Definition Structure
**File:** `variablelibraries/DevVariables.json`
```json
{
  "displayName": "DevVariables",
  "description": "Development environment variables",
  "definition": {
    "variables": [
      {
        "name": "storage_account",
        "value": "devstorageaccount",
        "type": "String",
        "description": "Azure Storage account name"
      },
      {
        "name": "api_endpoint",
        "value": "https://dev-api.company.com",
        "type": "String",
        "description": "API endpoint URL"
      },
      {
        "name": "data_lake_path",
        "value": "abfss://dev@devstorageaccount.dfs.core.windows.net/",
        "type": "String",
        "description": "Data Lake path"
      },
      {
        "name": "batch_size",
        "value": "100",
        "type": "Int",
        "description": "Processing batch size"
      },
      {
        "name": "max_retries",
        "value": "3",
        "type": "Int",
        "description": "Maximum retry attempts"
      },
      {
        "name": "enable_monitoring",
        "value": "false",
        "type": "Bool",
        "description": "Enable monitoring flag"
      },
      {
        "name": "sql_connection_string",
        "value": "Server=dev-sql-server.database.windows.net;Database=DevDB;",
        "type": "Secret",
        "description": "SQL Server connection string"
      },
      {
        "name": "storage_connection_string",
        "value": "DefaultEndpointsProtocol=https;AccountName=devstorageaccount;",
        "type": "Secret",
        "description": "Storage account connection string"
      }
    ]
  }
}
```

#### 2.2 Supported Variable Types
| Type | Description | Example |
|------|-------------|---------|
| String | Text values | "dev-storage" |
| Int | Integer numbers | 100 |
| Bool | Boolean values | true/false |
| Secret | Encrypted strings | Connection strings, API keys |

### Phase 3: Runtime Usage in Notebooks and Pipelines

#### 3.1 Notebook Usage (PySpark)
```python
# Import mssparkutils
from notebookutils import mssparkutils

# Get single variable
storage_account = mssparkutils.env.getVariable("storage_account", "DevVariables")
api_endpoint = mssparkutils.env.getVariable("api_endpoint", "DevVariables")

# Get all variables from library
all_vars = mssparkutils.env.getVariables("DevVariables")
storage_account = all_vars["storage_account"]
batch_size = int(all_vars["batch_size"])

# Use in code
df = spark.read.parquet(f"abfss://{storage_account}.dfs.core.windows.net/data/")
```

#### 3.2 Data Pipeline Usage
```json
{
  "activities": [
    {
      "name": "CopyData",
      "type": "Copy",
      "inputs": [
        {
          "referenceName": "SourceDataset",
          "parameters": {
            "storageAccount": "@variables('storage_account')"
          }
        }
      ],
      "userProperties": [],
      "typeProperties": {
        "source": {
          "type": "BinarySource",
          "storeSettings": {
            "type": "AzureBlobFSReadSettings"
          }
        }
      }
    }
  ],
  "variables": {
    "storage_account": {
      "type": "String",
      "defaultValue": "@variableLibrary('DevVariables', 'storage_account')"
    }
  }
}
```

### Phase 4: Deployment Workflow

#### 4.1 Standard Deployment Flow
```bash
# 1. Deploy Variable Library first (priority 4)
python scripts/deploy_artifacts.py dev --create-artifacts

# Deployment order:
# Priority 1: Lakehouses
# Priority 2: Environments
# Priority 3: KQL Databases
# Priority 4: Shortcuts
# Priority 4: Variable Libraries ← NEW
# Priority 5: Semantic Models
# ... rest
```

#### 4.2 Update Variables Only
```bash
# Update only Variable Library (fast operation)
python scripts/deploy_artifacts.py dev --artifacts variable_libraries

# This will:
# 1. Read variablelibraries/DevVariables.json
# 2. Update variables in existing Variable Library
# 3. No need to redeploy notebooks/pipelines
```

#### 4.3 CI/CD Integration
```yaml
# GitHub Actions example
- name: Deploy Variable Library
  run: |
    python scripts/deploy_artifacts.py ${{ matrix.environment }} \\
      --artifacts variable_libraries

- name: Deploy All Artifacts
  run: |
    python scripts/deploy_artifacts.py ${{ matrix.environment }} \\
      --create-artifacts
```

## Migration Path

### Option 1: Hybrid Approach (Recommended)
Keep both config files AND Variable Library:
- **Config files**: For deployment-time substitution (workspace IDs, resource names)
- **Variable Library**: For runtime variables (connection strings, batch sizes)

```
Deployment Time (config/dev.json):
  ✓ Workspace IDs
  ✓ Service Principal details
  ✓ Lakehouse names
  ✓ Artifact creation flags

Runtime (Variable Library in Fabric):
  ✓ Connection strings
  ✓ API endpoints
  ✓ Batch sizes
  ✓ Feature flags
  ✓ Processing parameters
```

### Option 2: Full Migration
Move all runtime-accessible variables to Variable Library:
1. Create Variable Library per environment
2. Migrate variables from `parameters` section in config
3. Update notebooks/pipelines to use mssparkutils.env.getVariable()
4. Keep only deployment metadata in config files

## Benefits

### 1. Centralized Variable Management
- All environment variables in one place (Fabric portal)
- Easy to view and modify
- No need to redeploy artifacts to change variables

### 2. Runtime Flexibility
```python
# Before (hard-coded after deployment):
storage_account = "devstorageaccount"  # Fixed

# After (runtime lookup):
storage_account = mssparkutils.env.getVariable("storage_account", "DevVariables")
# Can be changed in Fabric portal without redeployment
```

### 3. Security
- Secrets encrypted in Fabric
- Access controlled via workspace permissions
- Audit trail for variable changes

### 4. Environment Parity
```
Dev:     DevVariables     → storage_account = "devstorageaccount"
UAT:     UATVariables     → storage_account = "uatstorageaccount"
Prod:    ProdVariables    → storage_account = "prodstorageaccount"

Same code in all environments, different variables
```

### 5. Git Integration
- Variable Library definitions can be stored in Git
- Version controlled
- Deployed via CI/CD

## Implementation Checklist

### Phase 1: Core Implementation
- [ ] Add VARIABLE_LIBRARY to ArtifactType enum
- [ ] Add Variable Library priority to DEPENDENCY_PRIORITY
- [ ] Implement list_variable_libraries() in fabric_client.py
- [ ] Implement create_variable_library() in fabric_client.py
- [ ] Implement get_variable_library_definition() in fabric_client.py
- [ ] Implement update_variable_library_definition() in fabric_client.py
- [ ] Add _deploy_variable_library() to deploy_artifacts.py
- [ ] Add _discover_variable_libraries() to deploy_artifacts.py
- [ ] Add _create_variable_library_template() to deploy_artifacts.py

### Phase 2: Configuration
- [ ] Create variablelibraries/ folder
- [ ] Add variable_library section to config/dev.json
- [ ] Add variable_library section to config/uat.json
- [ ] Add variable_library section to config/prod.json
- [ ] Add variable_libraries to artifacts_to_create
- [ ] Create example Variable Library definitions

### Phase 3: Documentation
- [ ] Create VARIABLE-LIBRARY-GUIDE.md
- [ ] Update README.md with Variable Library support
- [ ] Update DEPLOYMENT-BEHAVIOR.md
- [ ] Update QUICK-REFERENCE.md
- [ ] Add runtime usage examples

### Phase 4: Testing
- [ ] Test Variable Library creation
- [ ] Test Variable Library updates
- [ ] Test variable retrieval in notebooks
- [ ] Test variable usage in pipelines
- [ ] Test CI/CD deployment

### Phase 5: Migration
- [ ] Identify runtime variables in current config
- [ ] Move runtime variables to Variable Library
- [ ] Update notebooks to use mssparkutils.env.getVariable()
- [ ] Update pipelines to reference Variable Library
- [ ] Test in Dev environment
- [ ] Deploy to UAT
- [ ] Deploy to Prod

## API Reference

### Fabric REST API Endpoints (Expected)
```
# List Variable Libraries
GET /v1/workspaces/{workspaceId}/items?type=VariableLibrary

# Create Variable Library
POST /v1/workspaces/{workspaceId}/items
Body: {"type": "VariableLibrary", "displayName": "DevVariables"}

# Get Variable Library Definition
POST /v1/workspaces/{workspaceId}/items/{libraryId}/getDefinition

# Update Variable Library Definition
POST /v1/workspaces/{workspaceId}/items/{libraryId}/updateDefinition
Body: {"definition": {"variables": [...]}}
```

## Example: Complete Workflow

### Step 1: Create Variable Library Definition
**File:** `variablelibraries/DevVariables.json`
```json
{
  "displayName": "DevVariables",
  "description": "Development environment variables",
  "definition": {
    "variables": [
      {"name": "storage_account", "value": "devstorageaccount", "type": "String"},
      {"name": "batch_size", "value": "100", "type": "Int"}
    ]
  }
}
```

### Step 2: Add to Config
**File:** `config/dev.json`
```json
{
  "artifacts_to_create": {
    "variable_libraries": [
      {
        "name": "DevVariables",
        "description": "Development environment variables",
        "create_if_not_exists": true
      }
    ]
  }
}
```

### Step 3: Deploy
```bash
python scripts/deploy_artifacts.py dev --create-artifacts
```

### Step 4: Use in Notebook
```python
from notebookutils import mssparkutils

# Get variables
storage = mssparkutils.env.getVariable("storage_account", "DevVariables")
batch_size = int(mssparkutils.env.getVariable("batch_size", "DevVariables"))

# Use in processing
df = spark.read.parquet(f"abfss://{storage}.dfs.core.windows.net/data/")
df.write.mode("overwrite").option("maxRecordsPerFile", batch_size).parquet("output/")
```

### Step 5: Update Variables (No Redeployment)
```bash
# Edit variablelibraries/DevVariables.json
# Change batch_size from 100 to 200

# Deploy update
python scripts/deploy_artifacts.py dev --artifacts variable_libraries

# Notebook automatically uses new value on next run
```

## Next Steps

1. **Review this plan** and provide feedback
2. **Prioritize phases** - which phase to implement first?
3. **API verification** - Test Variable Library APIs in Fabric
4. **Proof of concept** - Create one Variable Library manually to understand format
5. **Implementation** - Start with Phase 1 (core implementation)

## Questions for Consideration

1. **Variable Naming**: Should we use naming conventions (e.g., `DEV_STORAGE_ACCOUNT` vs `storage_account`)?
2. **Secret Management**: Should secrets stay in Azure Key Vault or move to Variable Library?
3. **Backward Compatibility**: Keep existing parameter substitution for transition period?
4. **Environment Mapping**: One Variable Library per environment or one with environment prefixes?
5. **Deployment Strategy**: Deploy Variable Library with artifacts or separately?

## References

- [Fabric Items API - List Items](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/list-items)
- [Fabric Items API - Create Item](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/create-item)
- [Fabric Items API - Get Item Definition](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/get-item-definition)
- [Fabric Deployment Pipelines](https://learn.microsoft.com/en-us/fabric/cicd/deployment-pipelines/understand-the-deployment-process)
