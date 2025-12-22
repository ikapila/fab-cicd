# Variable Library Configuration Guide

This guide shows how to configure variable libraries in your Microsoft Fabric CI/CD deployment.

## Overview

Variable libraries can be configured in **two locations**:

1. **Config files** (`config/dev.json`, `config/uat.json`, `config/prod.json`) - For creation via `--create-artifacts`
2. **Artifacts folder** (`wsartifacts/Variablelibraries/`) - For deployment

---

## Method 1: Config File (artifacts_to_create)

### Location
`config/dev.json` (or uat.json, prod.json)

### Usage
Used with `--create-artifacts` flag to create variable libraries owned by service principal.

### Sample Configuration

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
            "name": "api_endpoint",
            "value": "https://dev-api.contoso.com",
            "type": "String",
            "description": "API endpoint URL"
          },
          {
            "name": "batch_size",
            "value": "1000",
            "type": "Int",
            "description": "Batch size for processing"
          },
          {
            "name": "enable_logging",
            "value": "true",
            "type": "Bool",
            "description": "Enable debug logging"
          }
        ]
      },
      {
        "name": "ConnectionStrings",
        "description": "Database and service connection strings",
        "create_if_not_exists": true,
        "variables": [
          {
            "name": "sql_connection",
            "value": "Server=dev-sql.database.windows.net;Database=DevDB;",
            "type": "String",
            "description": "SQL Server connection string"
          },
          {
            "name": "cosmos_connection",
            "value": "AccountEndpoint=https://dev-cosmos.documents.azure.com:443/;",
            "type": "String",
            "description": "Cosmos DB connection string"
          }
        ]
      }
    ]
  }
}
```

### Variable Types
- `String` - Text values
- `Int` - Integer numbers
- `Bool` - Boolean (true/false)

### Deployment Command
```bash
python scripts/deploy_artifacts.py dev --create-artifacts --artifacts-dir .
```

---

## Method 2: Simple JSON Format (wsartifacts folder)

### Location
`wsartifacts/Variablelibraries/MyVariableLibrary.json`

### Structure
Single JSON file with all variables inline.

### Sample File: `wsartifacts/Variablelibraries/DevVariables.json`

```json
{
  "name": "DevVariables",
  "description": "Development environment variables",
  "variables": [
    {
      "name": "storage_account",
      "value": "devstorageaccount",
      "type": "String",
      "description": "Azure Storage Account name"
    },
    {
      "name": "api_endpoint",
      "value": "https://dev-api.contoso.com",
      "type": "String",
      "description": "API endpoint URL"
    },
    {
      "name": "batch_size",
      "value": "1000",
      "type": "Int",
      "description": "Batch size for processing"
    },
    {
      "name": "enable_logging",
      "value": "true",
      "type": "Bool",
      "description": "Enable debug logging"
    }
  ]
}
```

### Deployment Command
```bash
python scripts/deploy_artifacts.py dev --artifacts-dir .
```

---

## Method 3: Fabric Git Format (wsartifacts folder)

### Location
`wsartifacts/Variablelibraries/MyVariableLibrary.VariableLibrary/`

### Structure
Official Microsoft Fabric Git format with environment-specific value sets.

### Folder Structure
```
wsartifacts/
└── Variablelibraries/
    └── MyVariableLibrary.VariableLibrary/
        ├── .platform                    # Metadata (required)
        └── valueSets/                   # Environment-specific variables
            ├── dev.json
            ├── uat.json
            └── prod.json
```

### Sample Files

#### `.platform` file
```json
{
  "version": "2.0",
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/platform/platformProperties.json",
  "config": {
    "logicalId": "00000000-0000-0000-0000-000000000000"
  },
  "metadata": {
    "type": "VariableLibrary",
    "displayName": "MyVariableLibrary",
    "description": "Environment-specific runtime variables"
  }
}
```

#### `valueSets/dev.json`
```json
[
  {
    "name": "storage_account",
    "value": "devstorageaccount",
    "type": "String",
    "description": "DEV: Azure Storage Account"
  },
  {
    "name": "api_endpoint",
    "value": "https://dev-api.contoso.com",
    "type": "String",
    "description": "DEV: API endpoint URL"
  },
  {
    "name": "batch_size",
    "value": "500",
    "type": "Int",
    "description": "DEV: Batch size (smaller for testing)"
  },
  {
    "name": "enable_logging",
    "value": "true",
    "type": "Bool",
    "description": "DEV: Debug logging enabled"
  }
]
```

#### `valueSets/uat.json`
```json
[
  {
    "name": "storage_account",
    "value": "uatstorageaccount",
    "type": "String",
    "description": "UAT: Azure Storage Account"
  },
  {
    "name": "api_endpoint",
    "value": "https://uat-api.contoso.com",
    "type": "String",
    "description": "UAT: API endpoint URL"
  },
  {
    "name": "batch_size",
    "value": "1000",
    "type": "Int",
    "description": "UAT: Batch size"
  },
  {
    "name": "enable_logging",
    "value": "true",
    "type": "Bool",
    "description": "UAT: Debug logging enabled"
  }
]
```

#### `valueSets/prod.json`
```json
[
  {
    "name": "storage_account",
    "value": "prodstorageaccount",
    "type": "String",
    "description": "PROD: Azure Storage Account"
  },
  {
    "name": "api_endpoint",
    "value": "https://api.contoso.com",
    "type": "String",
    "description": "PROD: API endpoint URL"
  },
  {
    "name": "batch_size",
    "value": "5000",
    "type": "Int",
    "description": "PROD: Batch size (optimized)"
  },
  {
    "name": "enable_logging",
    "value": "false",
    "type": "Bool",
    "description": "PROD: Debug logging disabled"
  }
]
```

### Deployment Command
```bash
# Deploys dev-specific variables
python scripts/deploy_artifacts.py dev --artifacts-dir .

# Deploys uat-specific variables
python scripts/deploy_artifacts.py uat --artifacts-dir .

# Deploys prod-specific variables
python scripts/deploy_artifacts.py prod --artifacts-dir .
```

---

## Complete Example: Both Methods Together

### Step 1: Create via Config (Service Principal owned)
**File:** `config/dev.json`
```json
{
  "artifacts_to_create": {
    "variable_libraries": [
      {
        "name": "CommonVariables",
        "description": "Shared variables across all environments",
        "create_if_not_exists": true,
        "variables": [
          {
            "name": "company_name",
            "value": "Contoso Ltd",
            "type": "String"
          },
          {
            "name": "max_retries",
            "value": "3",
            "type": "Int"
          }
        ]
      }
    ]
  }
}
```

**Command:**
```bash
python scripts/deploy_artifacts.py dev --create-artifacts
```

### Step 2: Deploy Environment-Specific Variables
**Folder:** `wsartifacts/Variablelibraries/EnvVariables.VariableLibrary/`

**Command:**
```bash
python scripts/deploy_artifacts.py dev --artifacts-dir .
```

---

## Variable Update Behavior

### Config Files (artifacts_to_create)
- **If library exists:** Variables are **automatically updated**
- **If library doesn't exist:** Library is created with variables
- No special flag needed

### wsartifacts Folder
- **If library exists:** Variables are updated
- **If library doesn't exist:** Library is created with variables
- Always processes on deployment

---

## Best Practices

### 1. Environment-Specific Values
Use Git format with `valueSets/` for different environment values:
- `dev.json` - Development settings (verbose logging, smaller batches)
- `uat.json` - Testing settings (moderate logging, test endpoints)
- `prod.json` - Production settings (minimal logging, optimized values)

### 2. Sensitive Data
**DO NOT** store secrets directly in variable libraries:
```json
❌ BAD:
{
  "name": "database_password",
  "value": "MyP@ssw0rd123!",
  "type": "String"
}

✅ GOOD:
{
  "name": "key_vault_url",
  "value": "https://my-keyvault.vault.azure.net/",
  "type": "String"
}
```

### 3. Naming Conventions
- Use snake_case: `storage_account`, `api_endpoint`
- Be descriptive: `max_retry_attempts` not `max_retry`
- Group related variables: `sql_connection_string`, `sql_timeout`, `sql_pool_size`

### 4. Documentation
Always include descriptions:
```json
{
  "name": "batch_size",
  "value": "1000",
  "type": "Int",
  "description": "Number of records to process per batch - optimized for memory usage"
}
```

---

## Troubleshooting

### Variables not visible after creation
✅ **Fixed in latest version** - Now uses correct Microsoft API format with `variables.json` path.

### Variables not updating
- Config method: Variables automatically update when library exists
- Artifacts method: Ensure variable library is discovered (check logs)

### Wrong environment values deployed
- Check you're running with correct environment: `dev`, `uat`, or `prod`
- Verify `valueSets/{environment}.json` exists
- Check logs for which file is being loaded

---

## Summary

| Method | Location | When to Use | Variables Update |
|--------|----------|-------------|------------------|
| **Config** | `config/{env}.json` | Service principal owned items | Automatic |
| **Simple JSON** | `wsartifacts/Variablelibraries/{Name}.json` | Single environment | Yes |
| **Git Format** | `wsartifacts/Variablelibraries/{Name}.VariableLibrary/` | Multi-environment | Yes (env-specific) |

**Recommended:** Use Git format with `valueSets/` for environment-specific deployments.
