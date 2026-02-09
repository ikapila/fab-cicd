# Fabric Git Format Implementation

## Overview

This implementation adds full support for **Fabric Git format** artifacts (semantic models, reports, and paginated reports) to the CI/CD deployment pipeline. The solution implements **Option 4 (Hybrid Approach)**:

- **Dev Environment**: Developers work in Fabric workspace with **Fabric Git integration enabled** (Microsoft handles commits automatically)
- **CI/CD Pipeline**: Reads Fabric Git format from Azure repo and deploys to UAT/Prod using **REST APIs**
- **Environment-Specific Rebinding**: Automatically applies environment-specific connections after deployment

## Problem Solved

Previously, reports created in Power BI Desktop contained hardcoded workspace connection strings. Manual replacement with config tokens (e.g., `{{lakehouse_connection}}`) broke Power BI Desktop compatibility - developers couldn't reopen reports after tokenization.

**Solution**: Keep actual connection strings in Dev workspace. CI/CD reads Fabric Git format and applies rebinding rules during deployment to UAT/Prod.

## Implementation Details

### 1. Discovery Phase

Updated discovery methods to scan for both **JSON files** (legacy) and **Fabric Git format folders**:

#### Semantic Models
- **JSON**: `wsartifacts/Semanticmodels/<name>.json`
- **Fabric Git**: `wsartifacts/Semanticmodels/<name>.SemanticModel/` folder with:
  - `.platform` - metadata (displayName, logicalId, type)
  - `model.tmdl` - top-level model definition
  - `tables/*.tmdl` - table definitions (can be 30+ files)
  - `relationships/*.tmdl` - relationship definitions

#### Reports
- **JSON**: `wsartifacts/Reports/<name>.json`
- **Fabric Git**: `wsartifacts/Reports/<name>.Report/` folder with:
  - `.platform` - metadata
  - `definition.pbir` - dataset reference
  - `report.json` - visual definitions

#### Paginated Reports
- **JSON**: `wsartifacts/Paginatedreports/<name>.json`
- **Fabric Git**: `wsartifacts/Reports/<name>.PaginatedReport/` or `wsartifacts/Paginatedreports/<name>.PaginatedReport/` folder with:
  - `.platform` - metadata
  - `<name>.rdl` - report definition (XML)

### 2. Reading Fabric Git Format

Added helper methods to read Fabric Git format artifacts:

#### `_read_semantic_model_git_format(folder_path)`
- Recursively scans folder for all files
- Base64 encodes each file's content
- Returns definition dict with `parts` array:
  ```json
  {
    "parts": [
      {
        "path": "model.tmdl",
        "payload": "<base64_content>",
        "payloadType": "InlineBase64"
      },
      {
        "path": "tables/invoices.tmdl",
        "payload": "<base64_content>",
        "payloadType": "InlineBase64"
      }
    ]
  }
  ```

#### `_read_report_git_format(folder_path)`
- Same pattern as semantic models
- Includes `.platform`, `definition.pbir`, `report.json`

#### `_transform_rdl_connection_strings(rdl_content, replacements)`
- Parses RDL (XML) content
- Uses regex to replace connection strings:
  ```xml
  <ConnectString>Server=dev-workspace.datawarehouse.fabric.microsoft.com;...</ConnectString>
  ```
- Returns transformed RDL with environment-specific connection string

#### `_encode_paginated_report_parts(folder_path, connection_replacements)`
- Finds `.rdl` file in folder
- Calls `_transform_rdl_connection_strings()` if replacements provided
- Base64 encodes transformed RDL and other files
- Returns definition dict with `parts` array

### 3. Deployment Logic

Updated deployment methods to support both formats:

#### `_deploy_semantic_model(name)`
1. Try reading JSON file first (legacy format)
2. If not found, scan `.SemanticModel` folders by `displayName` from `.platform`
3. For Fabric Git format, call `_read_semantic_model_git_format()` to get all TMDL files
4. Deploy using `create_semantic_model()` or `update_semantic_model()`
5. Apply rebinding rules using `_apply_semantic_model_rebinding()`

#### `_deploy_report(name)`
1. Try reading JSON file first
2. If not found, scan `.Report` folders (excluding `.PaginatedReport`)
3. For Fabric Git format, call `_read_report_git_format()`
4. Deploy using `create_report()` or `update_report()`
5. Apply rebinding rules using `_apply_report_rebinding()`

#### `_deploy_paginated_report(name)`
1. Try reading JSON file first in `Paginatedreports/` folder
2. If not found, scan `.PaginatedReport` folders in both `Reports/` and `Paginatedreports/`
3. For Fabric Git format:
   - Get rebind rules for connection string replacements
   - Call `_encode_paginated_report_parts()` with transformation rules
   - RDL is transformed before encoding (no rebind API for paginated reports)
4. Deploy using `create_paginated_report()` or `update_paginated_report()`

### 4. Rebinding Configuration

Environment-specific rebinding is configured in `config/<env>.json`:

#### Semantic Model Rebinding (Lakehouse Tables)
```json
{
  "rebind_rules": {
    "semantic_models": [
      {
        "artifact_name": "Finance Summary",
        "table_rebindings": [
          {
            "table_name": "invoices",
            "source_lakehouse": "reporting_gold",
            "source_workspace_id": "{{workspace_id}}"
          },
          {
            "table_name": "contracts",
            "source_lakehouse": "reporting_gold",
            "source_workspace_id": "{{workspace_id}}"
          }
        ]
      }
    ]
  }
}
```

**API Used**: `rebind_semantic_model_sources(workspace_id, dataset_id, table_name, lakehouse_id, lakehouse_workspace_id)`
- API automatically resolves lakehouse SQL endpoint from lakehouse ID
- No need to manage connection strings in config

#### Report Rebinding (Dataset Reference)
```json
{
  "rebind_rules": {
    "reports": [
      {
        "artifact_name": "Finance Summary",
        "dataset_rebinding": {
          "target_dataset": "Finance Summary",
          "target_workspace_id": "{{workspace_id}}"
        }
      }
    ]
  }
}
```

**API Used**: `rebind_report_dataset(workspace_id, report_id, dataset_id)`

#### Paginated Report Rebinding (Connection String Transformation)
```json
{
  "rebind_rules": {
    "paginated_reports": [
      {
        "report_name": "Aged Debtors",
        "connection_string_replacements": {
          "old_pattern": "Server=[^;]+\\.datawarehouse\\.fabric\\.microsoft\\.com",
          "new_connection_string": "Server=prod-reporting-gold.datawarehouse.fabric.microsoft.com"
        }
      }
    ]
  }
}
```

**Note**: Paginated reports don't have a rebind API. Connection string transformation happens before deployment using regex-based XML transformation in `_transform_rdl_connection_strings()`.

## Workflow

### Development Workflow

1. **Developer** creates/edits reports in Power BI Desktop
2. **Developer** publishes to Dev Fabric workspace
3. **Fabric Git Integration** automatically commits to Azure repo in Fabric Git format
4. **Developer** doesn't manually edit connection strings (keeps workspace connections)

### Deployment Workflow (CI/CD)

1. **Pipeline** pulls latest code from Azure repo
2. **Discovery Phase**:
   - Scans `wsartifacts/` folder for JSON and Fabric Git format folders
   - Reads `.platform` files to get `displayName` for matching
3. **Deployment Phase**:
   - For each artifact:
     - Reads definition (JSON or Fabric Git format with all files)
     - Creates/updates artifact via REST API
     - Applies environment-specific rebinding
4. **Rebinding Phase**:
   - **Semantic Models**: Rebinds tables to environment-specific lakehouses via API
   - **Reports**: Rebinds to environment-specific datasets via API
   - **Paginated Reports**: Already transformed during encoding (no rebind API)

## Key Benefits

1. **No Manual Editing**: Developers never manually edit connection strings or tokenize configs
2. **Power BI Desktop Compatible**: Reports remain editable in Power BI Desktop (no broken references)
3. **Environment Isolation**: Each environment has its own connection strings applied automatically
4. **Backward Compatible**: Still supports legacy JSON format for gradual migration
5. **Full Fidelity**: All TMDL files (30+ for complex models) included in deployment
6. **Automatic Resolution**: Lakehouse rebinding API resolves SQL endpoints automatically

## Testing Recommendations

1. **Test Discovery**: Verify both JSON and Fabric Git format artifacts are discovered
   ```bash
   python scripts/deploy_artifacts.py --config config/dev.json --dry-run
   ```

2. **Test Semantic Model Deployment**:
   - Deploy "Finance Summary" semantic model
   - Verify all TMDL files included in API payload
   - Verify table rebinding to "reporting_gold" lakehouse

3. **Test Report Deployment**:
   - Deploy "Finance Summary" report
   - Verify dataset rebinding to semantic model
   - Verify report opens in Power BI Service

4. **Test Paginated Report Deployment**:
   - Deploy "Aged Debtors" paginated report
   - Verify RDL connection string transformed before deployment
   - Verify report runs in Power BI Service

5. **Test Cross-Environment**:
   - Deploy to Dev (should use dev-reporting-gold endpoint)
   - Deploy to UAT (should use uat-reporting-gold endpoint)
   - Deploy to Prod (should use prod-reporting-gold endpoint)

## Files Modified

- `scripts/deploy_artifacts.py`:
  - `_discover_semantic_models()` - updated for Fabric Git format
  - `_discover_reports()` - updated for Fabric Git format
  - `_discover_paginated_reports()` - updated for Fabric Git format
  - Added `_read_semantic_model_git_format()`
  - Added `_read_report_git_format()`
  - Added `_transform_rdl_connection_strings()`
  - Added `_read_paginated_report_git_format()`
  - Added `_encode_paginated_report_parts()`
  - `_deploy_semantic_model()` - updated for both formats
  - `_deploy_report()` - updated for both formats
  - `_deploy_paginated_report()` - updated for both formats

- `config/dev.json`, `config/uat.json`, `config/prod.json`:
  - Added rebinding examples for "Finance Summary" semantic model
  - Added rebinding examples for "Finance Summary" report
  - Added rebinding examples for "Aged Debtors" paginated report

## Example Artifacts

Sample Fabric Git format artifacts in `wsartifacts/`:

- `wsartifacts/Semanticmodels/Finance Summary.SemanticModel/`
  - 36+ TMDL files (tables: invoices, contracts, aged_debtors, etc.)
  
- `wsartifacts/Reports/Finance Summary.Report/`
  - Visual definitions and dataset reference
  
- `wsartifacts/Reports/Aged Debtors.PaginatedReport/`
  - RDL file with lakehouse SQL connection

## Future Enhancements

1. **Validation**: Add validation for Fabric Git format structure (`.platform` required, TMDL syntax validation)
2. **Incremental Deployment**: Deploy only changed files (compare hashes)
3. **Rollback**: Store previous versions for rollback capability
4. **Monitoring**: Add telemetry for deployment success rates and rebinding failures
5. **Documentation**: Auto-generate lineage diagrams from TMDL relationships
