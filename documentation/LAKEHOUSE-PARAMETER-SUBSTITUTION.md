# Lakehouse Shortcuts Parameter Substitution

## Overview

Lakehouse shortcuts can use parameters from the config file to enable environment-specific configurations. This allows you to use the same `shortcuts.metadata.json` file across DEV, UAT, and PROD environments with different values.

## How It Works

When deploying a lakehouse with shortcuts, the deployment script will:
1. Read the `shortcuts.metadata.json` file
2. Find all `${parameter_name}` placeholders
3. Replace them with values from the config file's `parameters` section
4. Deploy the processed shortcuts to Fabric

## Parameter Syntax

Use `${parameter_name}` syntax in your `shortcuts.metadata.json` file:

```json
{
  "name": "ExternalData",
  "target": {
    "adlsGen2": {
      "connectionId": "${connection_id}",
      "location": "https://${storage_account}.dfs.core.windows.net/${container_name}/data"
    }
  }
}
```

## Config File Setup

Define parameters in your environment config file (e.g., `config/dev.json`):

```json
{
  "parameters": {
    "storage_account": "devstorageaccount",
    "container_name": "data-container",
    "connection_id": "dev-connection-guid-123",
    "source_workspace_id": "dev-workspace-guid-456",
    "source_lakehouse_id": "dev-lakehouse-guid-789"
  }
}
```

## Common Use Cases

### 1. ADLS Gen2 Shortcuts with Environment-Specific Storage Accounts

**shortcuts.metadata.json:**
```json
[
  {
    "name": "ExternalData",
    "path": "Tables",
    "target": {
      "adlsGen2": {
        "connectionId": "${connection_id}",
        "location": "https://${storage_account}.dfs.core.windows.net/rawdata/sales"
      }
    }
  }
]
```

**config/dev.json:**
```json
{
  "parameters": {
    "storage_account": "devdatalake",
    "connection_id": "dev-connection-guid"
  }
}
```

**config/prod.json:**
```json
{
  "parameters": {
    "storage_account": "proddatalake",
    "connection_id": "prod-connection-guid"
  }
}
```

### 2. OneLake Shortcuts with Environment-Specific Workspaces

**shortcuts.metadata.json:**
```json
[
  {
    "name": "SourceLakehouse",
    "path": "Tables",
    "target": {
      "oneLake": {
        "workspaceId": "${source_workspace_id}",
        "itemId": "${source_lakehouse_id}",
        "path": "Tables/DimProduct"
      }
    }
  }
]
```

**config/dev.json:**
```json
{
  "parameters": {
    "source_workspace_id": "dev-workspace-123",
    "source_lakehouse_id": "dev-lakehouse-456"
  }
}
```

### 3. Multiple Shortcuts with Shared Parameters

```json
[
  {
    "name": "RawData",
    "path": "Files",
    "target": {
      "adlsGen2": {
        "connectionId": "${connection_id}",
        "location": "https://${storage_account}.dfs.core.windows.net/raw"
      }
    }
  },
  {
    "name": "ProcessedData",
    "path": "Files",
    "target": {
      "adlsGen2": {
        "connectionId": "${connection_id}",
        "location": "https://${storage_account}.dfs.core.windows.net/processed"
      }
    }
  },
  {
    "name": "ArchivedData",
    "path": "Files",
    "target": {
      "adlsGen2": {
        "connectionId": "${connection_id}",
        "location": "https://${storage_account}.dfs.core.windows.net/archive"
      }
    }
  }
]
```

This allows all three shortcuts to use the same `storage_account` and `connection_id`, which change per environment.

## Parameter Resolution

### Available Parameters

Parameters must be defined in the `parameters` section of your environment config file. Common parameters include:

- `storage_account` - Azure Storage account name
- `connection_id` - Fabric connection GUID
- `container_name` - Storage container name
- `key_vault_url` - Azure Key Vault URL
- `source_workspace_id` - Source workspace GUID for OneLake shortcuts
- `source_lakehouse_id` - Source lakehouse GUID for OneLake shortcuts

### Missing Parameters

If a parameter is referenced in `shortcuts.metadata.json` but not found in the config file:
- A warning will be logged
- The placeholder will be left unchanged (e.g., `${missing_param}`)
- Deployment will continue but may fail if Fabric requires a valid value

**Example warning:**
```
WARNING - Parameter ${unknown_param} not found in config, leaving unchanged
```

### Parameter Naming

- Use descriptive names: `${storage_account}` not `${sa}`
- Use lowercase with underscores: `${source_lakehouse_id}` not `${SourceLakehouseId}`
- Avoid special characters except underscores

## Deployment Behavior

### When Parameters are Substituted

Parameters are substituted:
- When deploying NEW lakehouses (CREATE path)
- When updating EXISTING lakehouses (UPDATE path)
- For Git format lakehouses only (folder structure with `.Lakehouse` suffix)

### Logging

The deployment script logs parameter substitution:

```
INFO - Including shortcuts.metadata.json in definition
DEBUG - Substituting ${storage_account} with devstorageaccount
DEBUG - Substituting ${connection_id} with dev-connection-guid-123
```

## Example: Complete Environment Setup

### Directory Structure

```
wsartifacts/
  Lakehouses/
    ReportingLakehouse.Lakehouse/
      lakehouse.metadata.json
      shortcuts.metadata.json   ← Uses parameters
      alm.settings.json
      .platform

config/
  dev.json       ← DEV parameters
  uat.json       ← UAT parameters
  prod.json      ← PROD parameters
```

### shortcuts.metadata.json (same for all environments)

```json
[
  {
    "name": "ExternalData",
    "path": "Tables",
    "target": {
      "adlsGen2": {
        "connectionId": "${connection_id}",
        "location": "https://${storage_account}.dfs.core.windows.net/data"
      }
    }
  }
]
```

### config/dev.json

```json
{
  "workspace_name": "DEV Workspace",
  "workspace_id": "dev-workspace-guid",
  "parameters": {
    "storage_account": "devdatalake",
    "connection_id": "dev-connection-guid"
  }
}
```

### config/prod.json

```json
{
  "workspace_name": "PROD Workspace",
  "workspace_id": "prod-workspace-guid",
  "parameters": {
    "storage_account": "proddatalake",
    "connection_id": "prod-connection-guid"
  }
}
```

### Deployment

```bash
# Deploy to DEV - uses devdatalake storage account
python scripts/deploy_artifacts.py dev

# Deploy to PROD - uses proddatalake storage account
python scripts/deploy_artifacts.py prod
```

## Benefits

1. **Single Source of Truth**: One `shortcuts.metadata.json` works across all environments
2. **Environment Isolation**: Different storage accounts, connections, and workspaces per environment
3. **Version Control**: Track parameter changes in config files
4. **Reduced Errors**: No manual editing of shortcuts per environment
5. **Consistency**: Same structure deployed to all environments

## Limitations

1. Only works with Git format lakehouses (folder structure)
2. Parameters must be defined in config file's `parameters` section
3. No support for nested parameter references (e.g., `${${env}_storage}`)
4. Parameter names are case-sensitive
5. No default values - missing parameters are left unchanged

## Best Practices

1. **Define All Parameters**: Ensure all environments have the same parameter names
2. **Use Descriptive Names**: Make parameter purpose clear
3. **Document Parameters**: Add comments in config files explaining parameter usage
4. **Test in DEV**: Verify parameter substitution works before promoting to UAT/PROD
5. **Validate GUIDs**: Ensure connection IDs and workspace IDs are valid for each environment
6. **Check Logs**: Review deployment logs to confirm parameters were substituted correctly

## Troubleshooting

### Shortcuts Not Working After Deployment

- Verify parameter values in config file are correct
- Check that GUIDs (connection_id, workspace_id, etc.) are valid for the target environment
- Review deployment logs for "Parameter not found" warnings
- Test connection to storage account or OneLake source

### Parameter Not Substituted

- Ensure parameter is defined in config file's `parameters` section
- Check spelling and case of parameter name (case-sensitive)
- Verify `${parameter_name}` syntax is correct (no spaces)
- Check deployment logs for warnings

### Deployment Fails with "Invalid Connection"

- Connection ID parameter may be incorrect for the environment
- Verify connection exists in target workspace
- Check that service principal has access to the connection

## Related Documentation

- [Lakehouse Git Format](FABRIC-GIT-FORMAT.md)
- [Change Detection](CHANGE-DETECTION.md)
- [Per-Environment Service Principal Guide](PER-ENVIRONMENT-SP-GUIDE.md)
- [Variable Library Integration](VARIABLE-LIBRARY-INTEGRATION.md)
