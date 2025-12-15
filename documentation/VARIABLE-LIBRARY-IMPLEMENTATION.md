# Variable Library Implementation Guide

## Overview

This implementation adds full support for Fabric Variable Libraries, enabling runtime environment-specific variable management for notebooks, pipelines, and other artifacts.

## What's New

### Core Changes

1. **Dependency Resolver** (`scripts/dependency_resolver.py`)
   - Added `VARIABLE_LIBRARY = "VariableLibrary"` to `ArtifactType` enum
   - Set priority level 4 (same as shortcuts - no dependencies)

2. **Fabric Client** (`scripts/fabric_client.py`)
   - `list_variable_libraries(workspace_id)` - List all Variable Libraries
   - `create_variable_library(workspace_id, name, description)` - Create new library
   - `get_variable_library(workspace_id, library_id)` - Get library details
   - `get_variable_library_definition(workspace_id, library_id)` - Get variables
   - `update_variable_library_definition(workspace_id, library_id, definition)` - Update variables

3. **Configuration Manager** (`scripts/config_manager.py`)
   - `get_parameters()` - Get environment parameters
   - `get_variable_library_config()` - Get Variable Library configuration

4. **Deployment Orchestrator** (`scripts/deploy_artifacts.py`)
   - `_discover_variable_libraries()` - Discover Variable Library JSON files
   - `_deploy_variable_library(name)` - Deploy or update Variable Library
   - `_create_variable_library_template(config)` - Create from config
   - Config-driven creation support in `deploy_config_artifacts()`

### New Directories and Files

```
variablelibraries/
├── DevVariables.json       # Development environment variables
├── UatVariables.json       # UAT environment variables
└── ProdVariables.json      # Production environment variables
```

### Configuration Updates

All environment configs (`config/dev.json`, `config/uat.json`, `config/prod.json`) now include:

```json
{
  "artifacts_to_create": {
    "variable_libraries": [
      {
        "name": "DevVariables",
        "description": "Development environment runtime variables",
        "create_if_not_exists": true,
        "variables": [
          {
            "name": "storage_account",
            "value": "devstorageaccount",
            "type": "String",
            "description": "Azure Storage Account name"
          },
          {
            "name": "batch_size",
            "value": "1000",
            "type": "Int",
            "description": "Batch size for processing"
          }
        ]
      }
    ]
  }
}
```

## Variable Types

Variable Libraries support four data types:

1. **String** - Text values (connection strings, URLs, paths)
2. **Int** - Integer numbers (batch sizes, retry counts, timeouts)
3. **Bool** - Boolean flags (enable/disable features)
4. **Secret** - Encrypted sensitive values (passwords, keys) - *Coming in future API update*

## Usage Examples

### 1. Accessing Variables in Notebooks

```python
# Import mssparkutils
from notebookutils import mssparkutils

# Get variable from active Variable Library
storage_account = mssparkutils.env.getVariable("storage_account")
batch_size = int(mssparkutils.env.getVariable("batch_size"))
enable_caching = mssparkutils.env.getVariable("enable_caching") == "true"

# Use in your code
data_path = f"abfss://data@{storage_account}.dfs.core.windows.net/raw/"
df = spark.read.parquet(data_path).limit(batch_size)

print(f"Processing {df.count()} rows from {storage_account}")
```

### 2. Accessing Variables in Data Pipelines

In Data Pipeline JSON definition:

```json
{
  "activities": [
    {
      "name": "CopyData",
      "type": "Copy",
      "inputs": [
        {
          "referenceName": "SourceDataset",
          "type": "DatasetReference",
          "parameters": {
            "storageAccount": "@variableLibrary('storage_account')",
            "path": "@variableLibrary('data_lake_path')"
          }
        }
      ]
    }
  ]
}
```

### 3. Creating Variable Library Definition

Create `variablelibraries/MyVariables.json`:

```json
{
  "name": "MyVariables",
  "description": "Custom environment variables",
  "variables": [
    {
      "name": "connection_string",
      "value": "Server=myserver;Database=mydb",
      "type": "String",
      "description": "Database connection string"
    },
    {
      "name": "max_workers",
      "value": "8",
      "type": "Int",
      "description": "Maximum parallel workers"
    },
    {
      "name": "enable_debug",
      "value": "false",
      "type": "Bool",
      "description": "Enable debug logging"
    }
  ]
}
```

### 4. Config-Driven Creation

Add to `config/dev.json`:

```json
{
  "artifacts_to_create": {
    "variable_libraries": [
      {
        "name": "DevVariables",
        "description": "Development variables",
        "create_if_not_exists": true,
        "variables": [
          {"name": "env_name", "value": "development", "type": "String"},
          {"name": "timeout", "value": "300", "type": "Int"}
        ]
      }
    ]
  }
}
```

## Deployment Behavior

### Discovery Phase
- Scans `variablelibraries/*.json` files
- Extracts variable definitions with name, value, type, description
- Adds to deployment queue at priority level 4

### Deployment Phase

**If Variable Library doesn't exist:**
1. Create Variable Library with name and description
2. Update definition to set initial variables
3. Log creation with variable count

**If Variable Library already exists:**
1. Get existing library ID
2. Update definition with new variables
3. Variables are merged/overwritten based on name
4. Log update with variable count

### Parameter Substitution

Variables support parameter substitution from config file:

```json
{
  "parameters": {
    "storage_account": "devstorageaccount"
  },
  "artifacts_to_create": {
    "variable_libraries": [
      {
        "variables": [
          {
            "name": "storage_path",
            "value": "abfss://data@{{storage_account}}.dfs.core.windows.net/"
          }
        ]
      }
    ]
  }
}
```

The `{{storage_account}}` will be replaced with `devstorageaccount` during deployment.

## Best Practices

### 1. Variable Naming
- Use snake_case for consistency
- Make names descriptive and self-documenting
- Prefix related variables: `storage_account`, `storage_path`, `storage_key`

### 2. Environment Strategy
- **Development**: DEBUG logging, small batch sizes, test endpoints
- **UAT**: INFO logging, medium batches, UAT endpoints
- **Production**: WARNING logging, large batches, production endpoints

### 3. Variable Organization
- Group related variables (storage, API, processing)
- Use consistent variable names across environments
- Only change values between environments, keep names identical

### 4. Security
- Avoid storing secrets directly in Variable Libraries for now
- Use Azure Key Vault references in variable values
- Example: `"key_vault_url": "https://mykv.vault.azure.net/secrets/mysecret"`

### 5. Type Usage
- **String**: URLs, paths, connection strings, log levels
- **Int**: Batch sizes, timeouts, retry counts, worker counts
- **Bool**: Feature flags (enable_caching, enable_monitoring)

## Migration Path

### Current State (Deployment-Time)
Variables in `config/dev.json` → Hard-coded into artifacts at deployment

### Future State (Runtime)
Variables in Variable Library → Accessed at runtime via `mssparkutils.env.getVariable()`

### Hybrid Approach (Recommended)

**Keep in Config Files:**
- Workspace IDs (deployment metadata)
- Service principal credentials (CI/CD secrets)
- Lakehouse/artifact names (infrastructure naming)
- Artifact creation flags

**Move to Variable Libraries:**
- Storage account names (runtime connection details)
- API endpoints (runtime service URLs)
- Batch sizes (runtime processing parameters)
- Log levels (runtime configuration)
- Feature flags (runtime behavior control)
- Timeout values (runtime operation limits)

### Migration Steps

1. **Identify runtime variables** in your notebooks and pipelines
2. **Create Variable Library JSON** with these variables per environment
3. **Deploy Variable Library** to each environment
4. **Update notebooks** to use `mssparkutils.env.getVariable()` instead of hard-coded values
5. **Update pipelines** to use `@variableLibrary()` function
6. **Test in Dev** - verify variables are accessible
7. **Promote to UAT/Prod** - deploy updated artifacts

## Testing

### Test Variable Library Creation

```bash
# Deploy to development
python scripts/deploy_artifacts.py --environment dev --create-from-config

# Verify Variable Library exists
# Check Fabric portal: Workspace → Variable Libraries → DevVariables
```

### Test Variable Access in Notebook

Create test notebook:

```python
from notebookutils import mssparkutils

# Test all variables
variables = ["storage_account", "api_endpoint", "log_level", "batch_size"]

for var_name in variables:
    try:
        value = mssparkutils.env.getVariable(var_name)
        print(f"✓ {var_name}: {value}")
    except Exception as e:
        print(f"✗ {var_name}: Error - {e}")
```

### Test Variable Updates

1. Modify `variablelibraries/DevVariables.json`
2. Change a variable value (e.g., `batch_size: 1000 → 2000`)
3. Deploy: `python scripts/deploy_artifacts.py --environment dev`
4. Run test notebook - verify new value is returned

## Troubleshooting

### Variable Library Not Found
- Check `variablelibraries/*.json` files exist
- Verify JSON syntax is valid
- Ensure `_discover_variable_libraries()` is called in deployment

### Variables Not Accessible in Notebook
- Verify Variable Library is deployed to workspace
- Check variable names match exactly (case-sensitive)
- Ensure notebook kernel is running in same workspace

### Update Not Taking Effect
- Variables are cached - restart notebook kernel
- Verify deployment completed successfully
- Check logs for update confirmation

### Variable Type Mismatch
- Fabric may return all variables as strings
- Convert explicitly in code: `int()`, `bool()`
- Example: `batch_size = int(mssparkutils.env.getVariable("batch_size"))`

## API Reference

### Fabric REST API Endpoints

```http
# List Variable Libraries
GET https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/items?type=VariableLibrary

# Create Variable Library
POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/items
{
  "displayName": "MyVariables",
  "type": "VariableLibrary",
  "description": "My variables"
}

# Get Variable Library Definition
POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/items/{libraryId}/getDefinition

# Update Variable Library Definition
POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/items/{libraryId}/updateDefinition
{
  "definition": {
    "variables": [
      {"name": "var1", "value": "value1", "type": "String"}
    ]
  }
}
```

## Next Steps

1. ✅ Core implementation complete
2. ✅ Variable Library files created for all environments
3. ✅ Configuration files updated
4. ⏳ Test deployment in development environment
5. ⏳ Update existing notebooks to use Variable Library
6. ⏳ Update pipelines to reference Variable Library
7. ⏳ Document team usage guidelines
8. ⏳ Deploy to UAT for testing
9. ⏳ Production rollout

## Support

For questions or issues:
- Review VARIABLE-LIBRARY-INTEGRATION.md for detailed architecture
- Check Fabric API documentation: https://learn.microsoft.com/fabric/
- Test manually in Fabric portal before automation
