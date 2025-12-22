# Fabric Git Format Support Status

**⚠️ IMPORTANT**: This document reflects the current implementation status versus Microsoft's official Git integration format.

Based on [Microsoft Fabric Git Integration Documentation](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/source-code-format) (Last updated: 12/15/2025)

## Summary

| Artifact Type | Folder Name | Our Support | Official Git Format | Notes |
|---------------|-------------|-------------|---------------------|-------|
| ✅ Notebooks | `Notebooks/` | ✅ Full | Folder: `.platform` + `notebook-content.py` | Correctly implemented |
| ⚠️ Lakehouses | `Lakehouses/` | ⚠️ Partial | Folder: `.platform` (no shortcuts file documented) | **Needs review** - We read `shortcuts.metadata.json` but not documented in official spec |
| ❌ Variable Libraries | `Variablelibraries/` | ❌ Custom | **Not documented in official Git format** | We use custom `valueSets/` format |
| ❌ Environments | `Environments/` | ❌ JSON only | Folder format supported but structure not documented | Needs implementation |
| ❌ Spark Job Definitions | `Sparkjobdefinitions/` | ❌ JSON only | Folder format supported | Needs implementation |
| ❌ Data Pipelines | `Datapipelines/` | ❌ JSON only | Folder: `.platform` + `pipeline-content.json` | Needs implementation |
| ⚠️ Semantic Models | `Semanticmodels/` | ❌ JSON only | Folder: `definition.pbism` + TMDL files | Official format exists |
| ⚠️ Reports | `Reports/` | ❌ JSON only | Folder: `definition.pbir` + `report.json` | Official format exists |
| ⚠️ Paginated Reports | `Paginatedreports/` | ❌ JSON only | Folder: `.rdl` file | Official format exists |
| ✅ SQL Views | `Views/` | ✅ Custom | N/A - Not a Git-synced item type | Custom implementation |

## Official Microsoft Fabric Git Format Details

### Key Concepts from Official Documentation

#### Directory Naming Convention
Official pattern: `{displayName}.{type}`

Examples:
- `SalesReport.Report`
- `CustomerData.SemanticModel`
- `ETL Pipeline.DataPipeline`

#### System Files (Version 2)

The `.platform` file replaces the older `item.metadata.json` and `item.config.json` files:

```json
{
  "version": "2.0",
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/platform/platformProperties.json",
  "config": {
    "logicalId": "e553e3b0-0260-4141-a42a-70a24872f88d"
  },
  "metadata": {
    "type": "Report",
    "displayName": "Sales Report",
    "description": "Monthly sales analysis"
  }
}
```

**Important**:
- `logicalId`: Cross-workspace identifier (GUID) - **DO NOT CHANGE**
- `type`: Case-sensitive item type
- Directory can have `.platform` OR `item.metadata.json`/`item.config.json`, not both

---

## Currently Supported (1 artifact type)

### 1. Notebooks ✅ **CORRECTLY IMPLEMENTED**

**Official Git Format** (per Microsoft docs):
- Folder naming: `{NotebookName}.Notebook`
- Contains: `.platform` file
- Contains: `notebook-content.py` file

**Our Implementation**:
- ✅ Correctly reads `.platform` file
- ✅ Correctly reads `notebook-content.py`
- ✅ Falls back to `.ipynb` for backward compatibility
- ✅ Handles `displayName` from `.platform` metadata

**Structure**:
```
Notebooks/
  ProcessData.Notebook/
    .platform              # System file with metadata
    notebook-content.py    # Python code content
```

### 2. Lakehouses ⚠️ **PARTIALLY CORRECT - NEEDS VERIFICATION**

**Official Git Format** (per Microsoft docs):
- Folder naming: `{LakehouseName}.Lakehouse`
- Contains: `.platform` file
- **Shortcuts handling**: NOT DOCUMENTED in official Git format specification
- Lakehouse Git integration is in **PREVIEW**

**Our Implementation**:
- ⚠️ Reads `item.metadata.json` instead of `.platform`
- ⚠️ Reads `shortcuts.metadata.json` (custom format, not in official docs)
- ⚠️ Should be updated to use `.platform` file
- ✅ Falls back to simple JSON for backward compatibility

**Current Structure** (our custom format):
```
Lakehouses/
  SalesDataLakehouse/
    item.metadata.json         # Should be .platform
    shortcuts.metadata.json    # Not in official spec
```

**What we should support**:
```
Lakehouses/
  SalesDataLakehouse.Lakehouse/
    .platform                  # Official system file
    # Shortcuts format TBD - not documented
```

**Action Required**:
- [ ] Update to read `.platform` instead of `item.metadata.json`
- [ ] Verify shortcuts storage format with actual Fabric Git export
- [ ] Test with real lakehouse from Fabric Git integration

### 3. Variable Libraries ❌ **CUSTOM FORMAT - NOT IN OFFICIAL DOCS**

**Official Git Format**: 
- **NOT DOCUMENTED** - Variable Libraries are not mentioned in the official Git integration format documentation
- May not be a Git-synced item type yet

**Our Custom Implementation**:
- Uses custom `valueSets/` folder structure
- Environment-specific JSON files (dev.json, uat.json, prod.json)
- Reads `item.metadata.json` (should be `.platform` if Git-synced)

**Our Custom Structure**:
```
Variablelibraries/
  AppVariables/
    item.metadata.json     # Should be .platform if Git-synced
    valueSets/            # Custom format
      dev.json           
      uat.json           
      prod.json          
```

**Status**:
- ⚠️ This is a custom format for our CI/CD system
- ⚠️ Not based on official Fabric Git integration
- ✅ Works well for environment-specific deployments
- ❓ Unknown if Variable Libraries will support Git integration

**Recommendation**:
- Keep custom format for now
- Monitor Microsoft docs for official Variable Library Git format
- Update when official format is released

## Not Yet Supported (6 artifact types)

### 1. Environments ❌

**Current Implementation**:
- **Discovery**: Lines 255-284 - Only scans `*.json` files
- **Deployment**: Lines 1722-1760 - Only reads JSON files

**Required Changes**:
- Add folder detection in discovery
- Add Fabric Git format reading in deployment

**Expected Fabric Git Structure**:
```
Environments/
  ProdEnvironment/
    item.metadata.json     # Environment metadata
```

### 2. Spark Job Definitions ❌

**Current Implementation**:
- **Discovery**: Lines 372-402 - Only scans `*.json` files
- **Deployment**: Lines 1924-1985 - Only reads JSON files

**Required Changes**:
- Add folder detection in discovery
- Add Fabric Git format reading in deployment
- Handle SparkJobDefinitionV1.json content file

**Expected Fabric Git Structure**:
```
Sparkjobdefinitions/
  DailySalesAggregation/
    item.metadata.json
    SparkJobDefinitionV1.json     # Job definition content
```

### 3. Data Pipelines ❌

**Current Implementation**:
- **Discovery**: Lines 403-426 - Only scans `*.json` files
- **Deployment**: Lines 1986-2036 - Only reads JSON files

**Required Changes**:
- Add folder detection in discovery
- Add Fabric Git format reading in deployment
- Handle pipeline-content.json

**Expected Fabric Git Structure**:
```
Datapipelines/
  SalesDailyOrchestration/
    item.metadata.json
    pipeline-content.json     # Pipeline definition
```

### 4. Semantic Models ❌

**Current Implementation**:
- **Discovery**: Not implemented (deployed via config or explicit list)
- **Deployment**: Lines 2037-2072 - Only reads JSON files

**Required Changes**:
- Add discovery method
- Add folder detection
- Add Fabric Git format reading in deployment

**Expected Fabric Git Structure**:
```
Semanticmodels/
  SalesAnalyticsModel/
    item.metadata.json
    model.bim              # Tabular model definition
```

### 5. Reports ❌

**Current Implementation**:
- **Discovery**: Not implemented (deployed via config or explicit list)
- **Deployment**: Lines 2073-2108 - Only reads JSON files

**Required Changes**:
- Add discovery method
- Add folder detection
- Add Fabric Git format reading in deployment

**Expected Fabric Git Structure**:
```
Reports/
  SalesDashboard/
    item.metadata.json
    definition.pbir        # Power BI report definition
```

### 6. Paginated Reports ❌

**Current Implementation**:
- **Discovery**: Not implemented (deployed via config or explicit list)
- **Deployment**: Lines 2109-2139 - Only reads JSON files

**Required Changes**:
- Add discovery method
- Add folder detection
- Add Fabric Git format reading in deployment

**Expected Fabric Git Structure**:
```
Paginatedreports/
  MonthlySalesReport/
    item.metadata.json
    report.rdl             # Report definition
```

## Implementation Priority

Based on usage patterns, here's the recommended order for adding Fabric Git format support:

### High Priority
1. **Data Pipelines** - Very commonly used, complex definitions benefit from Git format
2. **Spark Job Definitions** - Commonly used, benefit from version control
3. **Environments** - Simple to implement, provides consistency

### Medium Priority
4. **Semantic Models** - Large files benefit from Git format
5. **Reports** - Benefit from Git format for version control

### Low Priority
6. **Paginated Reports** - Less commonly used, simple structure

## Implementation Pattern

For each unsupported artifact type, follow this pattern (based on the working implementations):

### 1. Update Discovery Method

```python
def _discover_artifact_type(self) -> None:
    """Discover artifact definitions"""
    artifact_dir = self.artifacts_dir / self.artifacts_root_folder / "ArtifactFolder"
    if not artifact_dir.exists():
        logger.debug("No artifacts directory found")
        return
    
    discovered = []
    
    # Discover JSON files (simple format)
    for artifact_file in artifact_dir.glob("*.json"):
        with open(artifact_file, 'r') as f:
            definition = json.load(f)
        
        artifact_name = definition.get("name", artifact_file.stem)
        discovered.append(artifact_name)
        
        # Add to resolver...
        logger.debug(f"Discovered artifact (JSON): {artifact_name}")
    
    # Discover Fabric Git format folders
    for item in artifact_dir.iterdir():
        if not item.is_dir():
            continue
        
        metadata_file = item / "item.metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            artifact_name = metadata.get("displayName", item.name)
            
            # Skip if already discovered from JSON
            if artifact_name in discovered:
                continue
            
            discovered.append(artifact_name)
            
            # Add to resolver...
            logger.debug(f"Discovered artifact (Fabric Git): {artifact_name}")
    
    if discovered:
        logger.info(f"Discovered {len(discovered)} artifact(s)")
```

### 2. Update Deployment Method

```python
def _deploy_artifact_type(self, name: str) -> None:
    """Deploy an artifact"""
    artifact_dir = self.artifacts_dir / self.artifacts_root_folder / "ArtifactFolder"
    artifact_file = artifact_dir / f"{name}.json"
    artifact_folder = artifact_dir / name
    
    definition = None
    
    # Try JSON file first
    if artifact_file.exists():
        logger.info(f"  Reading artifact from: {artifact_file.name}")
        with open(artifact_file, 'r') as f:
            definition = json.load(f)
    
    # Try Fabric Git folder
    elif artifact_folder.exists():
        logger.info(f"  Reading artifact from Fabric Git folder: {name}/")
        
        metadata_file = artifact_folder / "item.metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                definition = json.load(f)
        
        # Read content from specific file (e.g., pipeline-content.json)
        content_file = artifact_folder / "artifact-content.json"
        if content_file.exists():
            with open(content_file, 'r') as f:
                content = json.load(f)
            # Merge or use content as needed
    
    else:
        logger.error(f"  ❌ Artifact not found: {artifact_file} or {artifact_folder}")
        raise FileNotFoundError(f"Artifact not found")
    
    # Continue with deployment logic...
```

## Testing Checklist

When adding Fabric Git format support to a new artifact type:

- [ ] Discovery finds JSON files
- [ ] Discovery finds Fabric Git folders
- [ ] Discovery avoids duplicates
- [ ] Discovery logs format type
- [ ] Deployment reads from JSON files
- [ ] Deployment reads from Fabric Git folders
- [ ] Deployment handles missing files gracefully
- [ ] Parameter substitution works for both formats
- [ ] Created artifacts are placed in correct folders
- [ ] Environment-specific logic works (if applicable)
- [ ] Update this status document

## Notes

- **SQL Views** don't need Fabric Git format - they already use `.sql` files
- All artifact types already support folder organization in workspace
- Parameter substitution works for both JSON and Fabric Git formats
- Fabric Git format provides better Git diffs and merge conflict resolution
