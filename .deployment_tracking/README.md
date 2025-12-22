# Deployment Tracking

This directory contains deployment state for change detection.

## Files

- `dev_last_commit.txt` - Last successful deployment commit for development environment
- `uat_last_commit.txt` - Last successful deployment commit for UAT environment  
- `prod_last_commit.txt` - Last successful deployment commit for production environment

## Format

Each file contains:
- Line 1: Git commit hash (SHA-1)
- Line 2+: Comment lines with deployment timestamp and environment

## Usage

These files are automatically created and updated by the deployment system.
The commit hashes are used for incremental deployment - only artifacts that 
changed since the last deployment are redeployed.

To force a full redeployment, use the `--force-all` flag:

```bash
python scripts/deploy_artifacts.py dev --force-all
```

Or delete the corresponding file to trigger a first-time deployment.
