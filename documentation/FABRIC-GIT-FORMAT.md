# Fabric Git Format Support

This document explains how the deployment system supports both simple JSON format and Microsoft Fabric's native Git format for artifacts.

## Overview

The deployment system now supports two formats for storing artifacts:

1. **Simple JSON Format**: Single JSON file containing all artifact metadata
2. **Fabric Git Format**: Folder structure with separate metadata files (native to Fabric Git integration)

## Supported Formats by Artifact Type

### Lakehouses

#### Simple JSON Format
```
wsartifacts/
  Lakehouses/
    SalesDataLakehouse.json
```

**File structure:**
```json
{
  "name": "SalesDataLakehouse",
  "description": "Lakehouse for sales data",
  "enable_schemas": true,
  "shortcuts": [
    {
      "name": "ExternalData",
      "path": "Tables",
      "target": {
        "location": "abfss://container@account.dfs.core.windows.net/path",
        "type": "AzureDataLakeStorage"
      }
    }
  ]
}
```

#### Fabric Git Format
```
wsartifacts/
  Lakehouses/
    SalesDataLakehouse/
      item.metadata.json
      shortcuts.metadata.json
```

**item.metadata.json:**
```json
{
  "displayName": "SalesDataLakehouse",
  "description": "Lakehouse for sales data",
  "id": "lakehouse-sales-001"
}
```

**shortcuts.metadata.json:**
```json
{
  "shortcuts": [
    {
      "name": "ExternalData",
      "path": "Tables",
      "target": {
        "location": "abfss://container@account.dfs.core.windows.net/path",
        "type": "AzureDataLakeStorage"
      }
    }
  ]
}
```

### Variable Libraries

#### Simple JSON Format
```
wsartifacts/
  Variablelibraries/
    AppVariables.json
```

**File structure (inline sets):**
```json
{
  "name": "AppVariables",
  "description": "Application configuration variables",
  "sets": {
    "dev": [
      {
        "name": "API_URL",
        "value": "https://dev-api.example.com",
        "type": "String"
      }
    ],
    "uat": [
      {
        "name": "API_URL",
        "value": "https://uat-api.example.com",
        "type": "String"
      }
    ],
    "prod": [
      {
        "name": "API_URL",
        "value": "https://api.example.com",
        "type": "String"
      }
    ]
  }
}
```

#### Fabric Git Format
```
wsartifacts/
  Variablelibraries/
    AppVariables/
      item.metadata.json
      valueSets/
        dev.json
        uat.json
        prod.json
```

**item.metadata.json:**
```json
{
  "displayName": "AppVariables",
  "description": "Application configuration variables",
  "id": "varlib-app-001"
}
```

**valueSets/prod.json:**
```json
{
  "variables": [
    {
      "name": "API_URL",
      "value": "https://api.example.com",
      "type": "String"
    },
    {
      "name": "DATABASE_NAME",
      "value": "production_db",
      "type": "String"
    }
  ]
}
```

### Notebooks

Both formats already supported (existing functionality):

#### Simple Format
```
wsartifacts/
  Notebooks/
    ProcessData.ipynb
```

#### Fabric Git Format
```
wsartifacts/
  Notebooks/
    ProcessData/
      .platform
      notebook-content.py
```

## How It Works

### Discovery Phase

The deployment system scans for both formats during discovery:

1. **Checks for JSON files first** - Traditional format
2. **Then checks for folders** - Fabric Git format
3. **Avoids duplicates** - If the same artifact exists in both formats, the JSON file takes precedence

**Lakehouse Discovery:**
- Looks for `*.json` files in `Lakehouses/` folder
- Looks for folders with `item.metadata.json` in `Lakehouses/` folder
- Logs format type: `(JSON)` or `(Fabric Git)`

**Variable Library Discovery:**
- Looks for `*.json` files in `Variablelibraries/` folder
- Looks for folders with `valueSets/` subdirectory or `item.metadata.json`
- Logs format type: `(JSON)` or `(Fabric Git)`

### Deployment Phase

#### Lakehouses

**For JSON format:**
1. Reads lakehouse definition from `.json` file
2. Reads `shortcuts` array from same file
3. Reads `enable_schemas` from either direct property or `creationPayload.enableSchemas`

**For Fabric Git format:**
1. Reads lakehouse metadata from `item.metadata.json`
2. Reads shortcuts from `shortcuts.metadata.json`
3. Creates lakehouse with folder support
4. Creates all shortcuts defined in metadata

**Logging output:**
```
  Reading lakehouse definition from Fabric Git folder: SalesDataLakehouse/
  Reading shortcuts from: shortcuts.metadata.json
  Found 3 shortcut(s) in metadata file
```

#### Variable Libraries

**For JSON format:**
1. Reads library definition from `.json` file
2. Checks for environment-specific `sets` object
3. Selects appropriate set based on deployment environment
4. Falls back to `active_set` property if specified

**For Fabric Git format:**
1. Reads library metadata from `item.metadata.json`
2. Checks for `valueSets/` folder
3. Maps deployment environment to file:
   - `dev` → `valueSets/dev.json`
   - `uat` → `valueSets/uat.json`
   - `prod` → `valueSets/prod.json`
4. Reads variables from environment-specific file
5. Falls back to any available file if environment file not found

**Logging output:**
```
  Reading variable library definition from Fabric Git folder: AppVariables/
  Found valueSets folder for environment-specific variables
  Deployment environment: 'prod'
  Reading variables from: valueSets/prod.json
  Found 5 variable(s) for environment 'prod'
```

## Environment-Specific Variable Selection

The system automatically selects the correct variable set based on the deployment environment:

| Deployment Environment | JSON Sets Key | Fabric Git File |
|------------------------|---------------|-----------------|
| `dev`, `development`   | `sets.dev`    | `valueSets/dev.json` |
| `uat`, `staging`, `test` | `sets.uat`  | `valueSets/uat.json` |
| `prod`, `production`   | `sets.prod`   | `valueSets/prod.json` |

### Override with active_set

For JSON format, you can override the environment selection:

```json
{
  "name": "AppVariables",
  "active_set": "uat",
  "sets": {
    "dev": [...],
    "uat": [...],
    "prod": [...]
  }
}
```

This will use the `uat` set regardless of deployment environment.

## Parameter Substitution

Both formats support parameter substitution from `config/*.json` files:

**Lakehouse shortcuts:**
- Target locations can use `{{PARAMETER_NAME}}`
- Substituted during deployment

**Variable library values:**
- Variable values can use `{{PARAMETER_NAME}}`
- Substituted before updating in Fabric

Example:
```json
{
  "name": "STORAGE_ACCOUNT",
  "value": "{{AZURE_STORAGE_ACCOUNT}}",
  "type": "String"
}
```

## Migration from JSON to Fabric Git Format

To migrate from simple JSON format to Fabric Git format:

### Lakehouses

1. Create folder with lakehouse name
2. Move basic metadata to `item.metadata.json`
3. Move shortcuts to `shortcuts.metadata.json`
4. Delete original `.json` file

**Before:**
```json
// SalesDataLakehouse.json
{
  "name": "SalesDataLakehouse",
  "description": "Sales data",
  "shortcuts": [...]
}
```

**After:**
```
SalesDataLakehouse/
  item.metadata.json → {"displayName": "SalesDataLakehouse", "description": "Sales data"}
  shortcuts.metadata.json → {"shortcuts": [...]}
```

### Variable Libraries

1. Create folder with library name
2. Move basic metadata to `item.metadata.json`
3. Create `valueSets/` folder
4. Split sets into separate environment files
5. Delete original `.json` file

**Before:**
```json
// AppVariables.json
{
  "name": "AppVariables",
  "sets": {
    "dev": [...],
    "uat": [...],
    "prod": [...]
  }
}
```

**After:**
```
AppVariables/
  item.metadata.json → {"displayName": "AppVariables"}
  valueSets/
    dev.json → {"variables": [...]}
    uat.json → {"variables": [...]}
    prod.json → {"variables": [...]}
```

## Benefits of Fabric Git Format

1. **Native Integration**: Matches format used by Fabric Git sync
2. **Cleaner Diffs**: Separate files make version control clearer
3. **Environment Separation**: Variable sets in separate files reduce merge conflicts
4. **Better Organization**: Metadata separated from content
5. **Scalability**: Easier to manage large numbers of shortcuts or variables

## Backward Compatibility

The deployment system maintains full backward compatibility:

- Existing JSON files continue to work without changes
- Can mix formats in same repository
- JSON format takes precedence if both exist
- All existing features work with both formats

## Best Practices

1. **Choose one format per repository**: Mixing formats works but can be confusing
2. **Use Fabric Git format for new projects**: Better long-term maintainability
3. **Use JSON format for simple artifacts**: Less overhead for artifacts with few shortcuts/variables
4. **Document format choice**: Add note to README about which format is used
5. **Version control**: Both formats work well with Git, but Fabric Git format has cleaner diffs

## Troubleshooting

### Artifacts not discovered

**Check:**
- Folder structure matches expected format
- `item.metadata.json` exists for Fabric Git format
- File names match environment names (`dev.json`, `uat.json`, `prod.json`)

**View discovery logs:**
```bash
# Look for discovery messages
python scripts/deploy_artifacts.py --environment dev | grep "Discovered"
```

### Wrong variables deployed

**Check:**
- Deployment environment matches file name
- `valueSets/` folder exists and contains environment files
- Variables structure in environment files is correct

**View selection logs:**
```bash
# Look for selection messages
python scripts/deploy_artifacts.py --environment prod | grep "valueSets"
```

### Shortcuts not created

**Check:**
- `shortcuts.metadata.json` exists in lakehouse folder
- Shortcuts array structure is correct
- Target locations are valid

**View shortcuts logs:**
```bash
# Look for shortcut creation messages
python scripts/deploy_artifacts.py --environment prod | grep "shortcut"
```

## Examples

See the following files for format examples:

- **Simple JSON**: Current `wsartifacts/` folder contents
- **Fabric Git**: Documentation examples above

For a complete working example with Fabric Git format, see the test fixtures in future test directories.
