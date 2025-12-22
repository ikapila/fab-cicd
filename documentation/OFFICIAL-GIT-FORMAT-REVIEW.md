# Official Fabric Git Format Review

**Date**: December 22, 2025  
**Source**: [Microsoft Fabric Git Integration Documentation](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/source-code-format)

## \u26a0\ufe0f Critical Findings

After reviewing the official Microsoft Fabric Git integration documentation, several discrepancies were found between our implementation and the official format:

### 1. Directory Naming Convention

**Official Format**: `{displayName}.{type}`

Examples from Microsoft docs:
- `Sales Report.Report`
- `Customer Data.SemanticModel`
- `ETL Pipeline.DataPipeline`
- `ProcessData.Notebook`

**Our Implementation**: Uses simple names without type suffix
- `SalesDataLakehouse/` instead of `SalesDataLakehouse.Lakehouse/`
- `ProcessData/` instead of `ProcessData.Notebook/`

**Impact**: \u26a0\ufe0f **MEDIUM** - Our folders won't match Git-exported structure

---

### 2. System Files - Version 2 Format

**Official Format**: `.platform` file (Version 2)

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
    "description": "This is a report"
  }
}
```

**Old Format (Version 1)**: `item.metadata.json` + `item.config.json`
- **Note**: Version 1 files are automatically upgraded to Version 2 when committing to Git

**Our Implementation**: Reads `item.metadata.json` 

**Impact**: \u26a0\ufe0f **HIGH** - Should read `.platform` file, not `item.metadata.json`

---

### 3. Lakehouse Git Format

**Official Documentation**:
- Folder naming: `{LakehouseName}.Lakehouse`
- Contains: `.platform` file
- **Shortcuts**: \u274c NOT DOCUMENTED in official Git format spec
- Status: **PREVIEW** - Lakehouse Git integration is in preview

**Our Implementation**:
- Reads `item.metadata.json` (old format)
- Reads `shortcuts.metadata.json` (custom, not in official docs)

**Impact**: \u26a0\ufe0f **MEDIUM** - Need to verify shortcuts format from actual Git export

**Action Required**:
1. Test with actual lakehouse from Fabric Git export
2. Verify how shortcuts are stored (if at all)
3. Update to read `.platform` file
4. Consider shortcuts may not be Git-synced yet

---

### 4. Variable Libraries

**Official Documentation**: \u274c **NOT MENTIONED**

Variable Libraries do not appear in the list of Git-supported items or in the source code format documentation.

**Our Implementation**: 
- Custom `valueSets/` folder structure
- Environment-specific JSON files (dev.json, uat.json, prod.json)

**Impact**: \u2705 **LOW** - Our custom format is valid for CI/CD, just not Git-synced

**Status**: Variable Libraries may not support Git integration yet, so our custom format is appropriate for deployment scenarios.

---

## Officially Documented Item Types

Per [Git integration supported items](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/intro-to-git-integration#supported-items), the following have Git support:

### Fully Documented Formats

| Item Type | Folder Pattern | Files | Documentation Link |
|-----------|---------------|-------|-------------------|
| **Notebook** | `{name}.Notebook` | `.platform` + `notebook-content.py` | [Notebook Git integration](https://learn.microsoft.com/en-us/fabric/data-engineering/notebook-source-control-deployment) |
| **Report** | `{name}.Report` | `.platform` + `definition.pbir` + `report.json` | [Power BI project report folder](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report) |
| **Semantic Model** | `{name}.SemanticModel` | `.platform` + `definition.pbism` + `definition/` (TMDL) | [Power BI project dataset folder](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-dataset) |
| **Paginated Report** | `{name}.PaginatedReport` | `.platform` + `.rdl` file | [Paginated reports Git integration](https://learn.microsoft.com/en-us/power-bi/paginated-reports/paginated-github-integration) |
| **Mirrored Database** | `{name}.MirroredDatabase` | `.platform` + `.json` file | [Mirrored database Git](https://learn.microsoft.com/en-us/fabric/mirroring/mirrored-database-cicd) |

### Git Supported but Format Not Fully Documented

| Item Type | Git Support | Our Implementation |
|-----------|-------------|-------------------|
| **Environment** | \u2705 Listed | \u274c JSON only |
| **Lakehouse** | \u2705 Listed (PREVIEW) | \u26a0\ufe0f Partial - custom shortcuts |
| **Spark Job Definition** | \u2705 Listed | \u274c JSON only |
| **Data Pipeline** | \u2705 Listed | \u274c JSON only |
| **Dataflow Gen2** | \u2705 Listed | \u274c Not implemented |
| **KQL Database** | \u2705 Listed | \u274c Not implemented |
| **Warehouse** | \u2705 Listed (PREVIEW) | \u274c Not implemented |
| **EventStream** | \u2705 Listed | \u274c Not implemented |

### Not Git-Synced (Custom CI/CD Format OK)

| Item Type | Status |
|-----------|--------|
| **Variable Libraries** | \u274c Not in Git integration docs - custom format is appropriate |
| **SQL Views** | \u274c Not a Git item type - custom `.sql` format is appropriate |

---

## Comparison: Our Implementation vs Official Format

### \u2705 Correctly Implemented

**Notebooks**:
- \u2705 Reads `.platform` file
- \u2705 Reads `notebook-content.py`
- \u2705 Falls back to `.ipynb`
- \u2705 Handles both formats correctly

### \u26a0\ufe0f Needs Updates

**Lakehouses**:
- \u274c Should read `.platform` instead of `item.metadata.json`
- \u274c Directory naming should be `{name}.Lakehouse`
- \u2753 Shortcuts format needs verification from actual Git export

**All Other Artifact Types**:
- \u274c Should support `.platform` file when reading Git format
- \u274c Should support `{name}.{Type}` directory naming
- \u274c Currently only read simple JSON files

### \u2705 Custom Format (Not Git-Synced)

**Variable Libraries**:
- \u2705 Custom `valueSets/` format is fine - not a Git-synced item type
- \u2705 Environment-specific deployment works well

**SQL Views**:
- \u2705 Custom `.sql` files are fine - not a Git item type
- \u2705 Lakehouse-specific organization works well

---

## Recommended Actions

### Priority 1: Fix Core System File Reading

**All artifact types should**:
1. Check for `.platform` file first (Version 2)
2. Fall back to `item.metadata.json` + `item.config.json` (Version 1)
3. Fall back to simple JSON (our legacy format)

**Example pattern**:
```python
# Try .platform file (Version 2)
platform_file = artifact_folder / ".platform"
if platform_file.exists():
    with open(platform_file, 'r') as f:
        platform_data = json.load(f)
    display_name = platform_data["metadata"]["displayName"]
    description = platform_data["metadata"].get("description", "")
    logical_id = platform_data["config"]["logicalId"]

# Fall back to Version 1
elif (artifact_folder / "item.metadata.json").exists():
    # Read item.metadata.json and item.config.json
    ...

# Fall back to simple JSON
else:
    artifact_file = artifact_dir / f"{name}.json"
    ...
```

### Priority 2: Update Directory Naming Detection

**Discovery methods should detect**:
- `{name}.{Type}/` folders (official Git format)
- `{name}/` folders (our legacy format)
- `{name}.json` files (simple format)

**Example**:
```python
for item in artifact_dir.iterdir():
    if item.is_dir():
        # Check for Git format: ends with .Lakehouse, .Notebook, etc.
        if item.name.endswith('.Lakehouse'):
            name = item.name.replace('.Lakehouse', '')
            # Process as Git format
        else:
            # Process as our legacy folder format
            name = item.name
```

### Priority 3: Verify Lakehouse Shortcuts Format

**Action steps**:
1. Create a lakehouse in Fabric with shortcuts
2. Connect workspace to Git
3. Commit lakehouse to Git
4. Examine actual Git structure
5. Update our code to match

### Priority 4: Add Support for Official Git Formats

**In order of usefulness**:
1. **Reports** - `.platform` + `definition.pbir` + `report.json`
2. **Semantic Models** - `.platform` + `definition.pbism` + TMDL files
3. **Data Pipelines** - `.platform` + `pipeline-content.json` (likely)
4. **Spark Jobs** - `.platform` + `SparkJobDefinitionV1.json` (likely)
5. **Environments** - `.platform` + TBD files
6. **Paginated Reports** - `.platform` + `.rdl` file

---

## Testing Strategy

### Step 1: Export Real Git Format

For each artifact type:
1. Create item in Fabric workspace
2. Connect workspace to Git repo
3. Commit item to Git
4. Examine actual folder structure
5. Document findings

### Step 2: Update Implementation

1. Update system file reading (`.platform` support)
2. Update directory naming detection
3. Add content file reading (`.pbir`, `.pbism`, `.rdl`, etc.)
4. Test with both Git format and legacy JSON format

### Step 3: Validate

1. Test discovery finds both formats
2. Test deployment works with both formats
3. Test parameter substitution works
4. Test environment-specific logic works

---

## Key Takeaways

1. **`.platform` file is the new standard** - We should support it everywhere
2. **Directory naming includes type suffix** - `{name}.{Type}`
3. **Notebooks are correctly implemented** - Good reference for other types
4. **Lakehouse shortcuts format is unclear** - Needs verification
5. **Variable Libraries not Git-synced** - Our custom format is appropriate
6. **Many item types need full format documentation** - Only 5 types fully documented

---

## References

- [Git integration source code format](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/source-code-format)
- [Git integration supported items](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/intro-to-git-integration#supported-items)
- [Power BI Desktop project format](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-overview)
- [Notebook Git integration](https://learn.microsoft.com/en-us/fabric/data-engineering/notebook-source-control-deployment)
- [Lakehouse Git integration](https://learn.microsoft.com/en-us/fabric/data-engineering/lakehouse-git-deployment-pipelines)
