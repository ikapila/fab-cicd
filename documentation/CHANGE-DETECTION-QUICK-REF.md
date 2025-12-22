# Change Detection Quick Reference

## Basic Usage

```bash
# Default - deploy only changed artifacts
python scripts/deploy_artifacts.py dev

# Force deploy all artifacts
python scripts/deploy_artifacts.py dev --force-all

# Deploy specific artifacts only
python scripts/deploy_artifacts.py dev --artifacts "ProcessSalesData,SalesDataLakehouse"

# Dry run to preview changes
python scripts/deploy_artifacts.py dev --dry-run
```

## What Triggers Full Deployment

- ✅ First deployment (no tracking file exists)
- ✅ Config file changed (`config/dev.json`)
- ✅ `--force-all` flag used
- ✅ Git not available
- ✅ Cannot determine current commit

## What Triggers Incremental Deployment

- ✅ Only specific files in `wsartifacts/` changed
- ✅ Git repository available
- ✅ Previous deployment commit exists

## Dependency Handling

When deploying changed artifacts, automatically includes:

- 📊 **Lakehouse changes** → All SQL views for that lakehouse
- 🔗 **Variable library changes** → (Currently: no automatic dependents)

## Skipped Deployment

If no changes detected since last deployment:
- ⚡ Deployment is **skipped entirely**
- ⏱️ Completes in <10 seconds
- 💡 Use `--force-all` to override

## Tracking Files

Location: `.deployment_tracking/`

```
.deployment_tracking/
├── dev_last_commit.txt       # Last deployment commit for dev
├── uat_last_commit.txt       # Last deployment commit for uat
└── prod_last_commit.txt      # Last deployment commit for prod
```

## Reset Change Tracking

```bash
# Delete tracking file to force full deployment
rm .deployment_tracking/dev_last_commit.txt

# Next deployment will be treated as first deployment
python scripts/deploy_artifacts.py dev
```

## Common Scenarios

### Scenario 1: Update Single Notebook
```bash
git add wsartifacts/Notebooks/ProcessSalesData.ipynb
git commit -m "Update notebook"
python scripts/deploy_artifacts.py dev
# → Deploys only ProcessSalesData notebook
```

### Scenario 2: Update Lakehouse
```bash
git add wsartifacts/Lakehouses/SalesDataLakehouse.Lakehouse/
git commit -m "Update lakehouse"
python scripts/deploy_artifacts.py dev
# → Deploys lakehouse + all its SQL views
```

### Scenario 3: Update Config
```bash
git add config/dev.json
git commit -m "Update API endpoint"
python scripts/deploy_artifacts.py dev
# → Deploys ALL artifacts (config affects everything)
```

### Scenario 4: No Changes
```bash
python scripts/deploy_artifacts.py dev
# → Skips deployment (nothing changed)
```

### Scenario 5: Force Full Deployment
```bash
python scripts/deploy_artifacts.py dev --force-all
# → Deploys ALL artifacts (ignores change detection)
```

## Troubleshooting

### "Git not available, deploying all artifacts"
**Problem**: Git not installed or not a git repository  
**Solution**: Install Git or accept full deployment

### "All artifacts deploying despite no changes"
**Problem**: Config file changed or tracking file missing  
**Solution**: This is expected behavior

### "Artifact not deploying when it should"
**Problem**: File not committed to Git  
**Solution**: `git add` and `git commit` before deploying

## Performance Metrics

| Scenario | Before | After | Improvement |
|----------|--------|-------|-------------|
| No changes | 5-10 min | <10 sec | **95% faster** |
| Single file | 5-10 min | 1-2 min | **80% faster** |
| Full deploy | 5-10 min | 5-10 min | Same |

## CI/CD Integration

### Azure DevOps
```yaml
- script: python scripts/deploy_artifacts.py $(Environment)
  displayName: 'Deploy Changed Artifacts'
```

### GitHub Actions
```yaml
- run: python scripts/deploy_artifacts.py ${{ matrix.environment }}
```

No special configuration needed - change detection works automatically!
