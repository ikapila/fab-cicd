# Configurable Artifacts Root Folder

## Overview

The artifacts root folder name is now configurable, allowing flexibility in organizing your Microsoft Fabric artifacts. By default, the system uses `wsartifacts` to align with Fabric's Git integration conventions.

## Configuration

### Environment Config Files

Add the `artifacts_root_folder` property to your environment configuration files:

**config/dev.json, config/uat.json, config/prod.json:**
```json
{
  "artifacts_root_folder": "wsartifacts",
  "service_principal": {
    ...
  },
  "workspace": {
    ...
  }
}
```

**Default Value:** If not specified, defaults to `"wsartifacts"`

## Usage

### Deployment Script

The `deploy_artifacts.py` script automatically reads the `artifacts_root_folder` from the environment config:

```bash
# Uses artifacts_root_folder from config/dev.json
python scripts/deploy_artifacts.py --environment dev

# Uses artifacts_root_folder from config/prod.json
python scripts/deploy_artifacts.py --environment prod
```

The script will log the folder being used:
```
INFO - Using artifacts root folder: wsartifacts
```

### Validation Script

The `validate_artifacts.py` script supports a command-line argument:

```bash
# Use default (wsartifacts)
python scripts/validate_artifacts.py

# Use custom folder name
python scripts/validate_artifacts.py --artifacts-root myartifacts

# Show help
python scripts/validate_artifacts.py --help
```

## Folder Structure

The artifacts root folder should contain capitalized subfolder names for each artifact type:

```
{artifacts_root_folder}/
├── Lakehouses/
│   └── *.json
├── Environments/
│   └── *.json
├── Notebooks/
│   └── *.ipynb
├── Sparkjobdefinitions/
│   └── *.json
├── Datapipelines/
│   └── *.json
├── Reports/
│   └── *.json
├── Semanticmodels/
│   └── *.json
├── Paginatedreports/
│   └── *.json
├── Variablelibraries/
│   └── *.json
└── Views/
    └── {LakehouseName}/
        ├── *.sql
        └── metadata.json
```

## Common Scenarios

### Fabric Git Integration

When using Fabric's Git integration, your workspace folder is typically named `wsartifacts`:

```json
{
  "artifacts_root_folder": "wsartifacts"
}
```

### Custom Organization

For custom folder organization:

```json
{
  "artifacts_root_folder": "fabric-artifacts"
}
```

### Multiple Workspaces

Different environments can use different folder names:

**config/dev.json:**
```json
{
  "artifacts_root_folder": "dev-artifacts"
}
```

**config/prod.json:**
```json
{
  "artifacts_root_folder": "wsartifacts"
}
```

## Implementation Details

### ConfigManager

The `ConfigManager` class provides the `get_artifacts_root_folder()` method:

```python
from config_manager import ConfigManager

config = ConfigManager("dev")
root_folder = config.get_artifacts_root_folder()  # Returns "wsartifacts" by default
```

### FabricDeployer

The `FabricDeployer` class automatically uses the configured folder:

```python
# Stored as instance variable
self.artifacts_root_folder = self.config.get_artifacts_root_folder()

# Used in all discovery and deployment methods
lakehouse_dir = self.artifacts_dir / self.artifacts_root_folder / "Lakehouses"
```

## Migration Guide

### From Flat Structure

If you're migrating from a flat structure (lakehouses/, notebooks/, etc.):

1. Update your config files to add `artifacts_root_folder`:
   ```json
   {
     "artifacts_root_folder": "wsartifacts"
   }
   ```

2. Create the new folder structure:
   ```bash
   mkdir -p wsartifacts/{Lakehouses,Notebooks,Environments,Sparkjobdefinitions,Datapipelines,Reports,Semanticmodels,Paginatedreports,Variablelibraries,Views}
   ```

3. Move your artifact files:
   ```bash
   mv lakehouses/*.json wsartifacts/Lakehouses/
   mv notebooks/*.ipynb wsartifacts/Notebooks/
   # ... repeat for other artifact types
   ```

4. Test the deployment:
   ```bash
   python scripts/validate_artifacts.py
   python scripts/deploy_artifacts.py --environment dev --dry-run
   ```

### From Different Folder Name

If you're currently using a different folder name:

1. Update your config file to match your current structure:
   ```json
   {
     "artifacts_root_folder": "your-current-folder-name"
   }
   ```

2. Or rename your folder to match Fabric conventions:
   ```bash
   mv your-current-folder-name wsartifacts
   ```

## Best Practices

1. **Use `wsartifacts` for Fabric Git Integration**: This matches the folder name created by Fabric's Git sync feature

2. **Capitalize Subfolder Names**: Follow Microsoft Fabric conventions (Lakehouses, not lakehouses)

3. **Keep Config Consistent**: Use the same folder name across dev/uat/prod unless you have a specific reason not to

4. **Validate After Changes**: Always run `validate_artifacts.py` after changing folder structure

5. **Document Custom Names**: If using a non-standard folder name, document the reason in your README

## Troubleshooting

### "Artifacts root folder not found" Error

**Problem:** Validation script can't find the artifacts folder

**Solution:** 
- Check that the folder exists in your repository root
- Verify the folder name matches your config or command-line argument
- Use `--artifacts-root` flag if using a custom name

### "No artifacts discovered" During Deployment

**Problem:** Deployment finds 0 artifacts

**Solution:**
- Verify `artifacts_root_folder` in your environment config file
- Check that subfolder names are capitalized correctly
- Ensure artifact files are in the correct subfolders

### Wrong Folder Used in Deployment

**Problem:** Deployment uses wrong folder name

**Solution:**
- Check the `artifacts_root_folder` value in your environment config
- Look for the log message: "Using artifacts root folder: {name}"
- Verify you're targeting the correct environment (--environment flag)

## Related Documentation

- [README.md](README.md) - Main project documentation
- [VARIABLE-LIBRARY-INTEGRATION.md](VARIABLE-LIBRARY-INTEGRATION.md) - Variable library configuration
- [SQL-VIEWS-IMPLEMENTATION.md](SQL-VIEWS-IMPLEMENTATION.md) - SQL views setup
- [QUICK-REFERENCE.md](QUICK-REFERENCE.md) - Command reference

## Changes Log

**2025-12-15**: Initial implementation of configurable artifacts root folder
- Added `artifacts_root_folder` to environment config files
- Added `get_artifacts_root_folder()` method to ConfigManager
- Updated FabricDeployer to use configurable folder
- Added `--artifacts-root` argument to validate_artifacts.py
- Default value: `"wsartifacts"`
