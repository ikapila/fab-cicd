# Fabric Deployment Pipeline Integration

## Overview

This document describes the Fabric Deployment Pipeline integration for promoting artifacts (currently paginated reports) across environments. Instead of deploying paginated reports directly via the Power BI Imports API (which is incompatible with Fabric-format RDL files), we use the **Fabric Deployment Pipeline API** to promote items from one stage to another.

### Why Deployment Pipelines?

The Power BI Imports API returns `RequestedFileIsEncryptedOrCorrupted` for Fabric-format RDL files that use the `2016/01/reportdefinition` schema with `MustUnderstand="df"` extensions. This is a fundamental incompatibility — Fabric-native RDL files cannot be deployed via the legacy Power BI API.

The Fabric Deployment Pipeline approach provides:
- ✅ Native support for Fabric-format paginated reports
- ✅ Automatic data source remapping via deployment rules
- ✅ Service principal support for CI/CD automation
- ✅ Autobinding (automatic connection to dependencies in target stage)
- ✅ Deployment history and audit trail in Fabric portal

## Architecture

```
┌──────────────┐     Git Sync      ┌──────────────┐   Pipeline    ┌──────────────┐
│   Git Repo   │ ──────────────►   │  Dev Stage   │ ──────────►   │  UAT Stage   │
│  (Source)     │                   │  (Order: 0)  │   (API)       │  (Order: 1)  │
└──────────────┘                   └──────────────┘               └──────┬───────┘
                                                                         │
                                                                    Pipeline
                                                                     (API)
                                                                         │
                                                                         ▼
                                                                  ┌──────────────┐
                                                                  │  Prod Stage  │
                                                                  │  (Order: 2)  │
                                                                  └──────────────┘
```

### Deployment Flow Per Environment

| Environment | Git Connected | Paginated Report Strategy | Other Artifacts |
|-------------|:------------:|--------------------------|-----------------|
| **Dev**     | ✅ Yes       | Git sync (`updateFromGit`) | Fabric Items API (`updateDefinition`) |
| **UAT**     | ❌ No        | Pipeline promotion (Dev → UAT) | Fabric Items API (`updateDefinition`) |
| **Prod**    | ❌ No        | Pipeline promotion (UAT → Prod) | Fabric Items API (`updateDefinition`) |

### How `deploy_all()` Works

The deployment is now split into three phases:

1. **Phase 1 — Source Control Sync** (Dev only): Runs `updateFromGit` to sync paginated reports (and any other Git-managed items) into the Dev workspace before anything else.

2. **Phase 2 — API Deployment**: Deploys all non-pipeline artifacts (semantic models, notebooks, reports, etc.) via the Fabric Items API in dependency order. These artifacts continue to use `updateDefinition` with environment-specific transforms.

3. **Phase 3 — Pipeline Promotion**: Promotes pipeline-configured artifact types (e.g., `PaginatedReport`) from the source stage to the target stage via the Deployment Pipeline API. Data source rules configured in the Fabric portal apply automatically.

## Configuration

### Config Structure

Each environment config (`config/dev.json`, `config/uat.json`, `config/prod.json`) includes a `deployment_pipeline` section:

```json
{
  "deployment_pipeline": {
    "enabled": true,
    "pipeline_name": "DataEng-Pipeline",
    "source_stage_order": 0,
    "target_stage_order": 1,
    "artifact_types": ["PaginatedReport"],
    "allow_create_artifact": true,
    "allow_overwrite_artifact": true,
    "allow_overwrite_target_artifact_label": true,
    "allow_skip_tiles_with_missing_prerequisites": true,
    "data_source_mapping": {
      "description": "Data source rules applied automatically when deploying to this environment.",
      "sql_server": "uat-reporting-gold.datawarehouse.fabric.microsoft.com",
      "sql_database": "reporting_gold"
    }
  }
}
```

### Config Fields

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | boolean | Whether to use deployment pipeline for this environment. `false` for Dev. |
| `pipeline_name` | string | Display name of the Fabric Deployment Pipeline. Must match exactly. |
| `source_stage_order` | int | Order of the source stage (0 = Development, 1 = Test, 2 = Production). |
| `target_stage_order` | int | Order of the target stage to deploy to. |
| `artifact_types` | string[] | List of Fabric item types to deploy via pipeline. E.g., `["PaginatedReport"]`. |
| `allow_create_artifact` | boolean | Allow creating new items in the target stage. Default: `true`. |
| `allow_overwrite_artifact` | boolean | Allow overwriting existing items in the target stage. Default: `true`. |
| `allow_overwrite_target_artifact_label` | boolean | Allow overwriting target item labels. Default: `true`. |
| `allow_skip_tiles_with_missing_prerequisites` | boolean | Allow skipping tiles with missing prerequisites. Default: `true`. |
| `data_source_mapping` | object | Source of truth for data source connection details. Used for documentation and validation. Actual rules are set in the Fabric portal. |

### Environment-Specific Configuration

**Dev (`config/dev.json`)**:
```json
{
  "deployment_pipeline": {
    "enabled": false,
    "pipeline_name": "DataEng-Pipeline",
    "artifact_types": ["PaginatedReport"],
    "data_source_mapping": {
      "sql_server": "dev-reporting-gold.datawarehouse.fabric.microsoft.com",
      "sql_database": "reporting_gold"
    }
  }
}
```
- `enabled: false` — Dev workspace gets paginated reports via Git sync
- `data_source_mapping` documents the Dev data source (used as the source when promoting)

**UAT (`config/uat.json`)**:
```json
{
  "deployment_pipeline": {
    "enabled": true,
    "pipeline_name": "DataEng-Pipeline",
    "source_stage_order": 0,
    "target_stage_order": 1,
    "artifact_types": ["PaginatedReport"],
    "data_source_mapping": {
      "sql_server": "uat-reporting-gold.datawarehouse.fabric.microsoft.com",
      "sql_database": "reporting_gold"
    }
  }
}
```
- Promotes from Dev (stage 0) to UAT (stage 1)
- Data source rules in the Fabric portal should map Dev server → UAT server

**Prod (`config/prod.json`)**:
```json
{
  "deployment_pipeline": {
    "enabled": true,
    "pipeline_name": "DataEng-Pipeline",
    "source_stage_order": 1,
    "target_stage_order": 2,
    "artifact_types": ["PaginatedReport"],
    "data_source_mapping": {
      "sql_server": "prod-reporting-gold.datawarehouse.fabric.microsoft.com",
      "sql_database": "reporting_gold"
    }
  }
}
```
- Promotes from UAT (stage 1) to Prod (stage 2)
- Data source rules in the Fabric portal should map UAT server → Prod server

### Adding New Artifact Types

To add another artifact type (e.g., `Report`) to pipeline deployment:

1. Add the type to `artifact_types` in the environment config:
   ```json
   "artifact_types": ["PaginatedReport", "Report"]
   ```

2. Set up deployment rules in the Fabric portal for the new type (if needed).

3. The `deploy_all()` method will automatically route artifacts of that type to the pipeline instead of API deployment.

> **Note**: PBIR reports are NOT supported by deployment pipelines (Fabric limitation). Standard Power BI reports in PBIP format are supported.

## One-Time Fabric Portal Setup

The following steps must be done once in the Fabric portal before CI/CD automation works:

### 1. Create the Deployment Pipeline

1. Open [Fabric Portal](https://app.fabric.microsoft.com)
2. Go to **Workspaces** → select any workspace → **Deployment pipelines**
3. Click **Create pipeline**
4. Name it exactly as configured in `pipeline_name` (e.g., `DataEng-Pipeline`)
5. Add three stages: **Development**, **Test**, **Production**

### 2. Assign Workspaces to Stages

| Stage | Order | Workspace |
|-------|:-----:|-----------|
| Development | 0 | DataEng-Dev |
| Test | 1 | DataEng-UAT |
| Production | 2 | DataEng-Prod |

### 3. Configure Data Source Rules

Data source rules must be set on the **target stage** (UAT and Prod):

**For UAT stage (order 1)**:
1. Click on the UAT stage → **Deployment rules**
2. Find each paginated report
3. Add a **Data source rule**:
   - Source: `dev-reporting-gold.datawarehouse.fabric.microsoft.com`
   - Target: `uat-reporting-gold.datawarehouse.fabric.microsoft.com`
4. Save

**For Prod stage (order 2)**:
1. Click on the Prod stage → **Deployment rules**
2. Find each paginated report
3. Add a **Data source rule**:
   - Source: `uat-reporting-gold.datawarehouse.fabric.microsoft.com`
   - Target: `prod-reporting-gold.datawarehouse.fabric.microsoft.com`
4. Save

> **Important**: Data source rules can only map to the **same type** of data source. The rules persist across deployments and only need to be set once per item.

### 4. Grant Service Principal Access

The service principal needs:
- **Pipeline.Deploy** and **Pipeline.Read.All** API permissions
- **Admin** or **Member** role on the deployment pipeline
- **Contributor** role on all workspaces assigned to pipeline stages

To add the service principal to the pipeline:
1. Open the deployment pipeline in Fabric portal
2. Click **Manage access** (gear icon)
3. Add the service principal with **Admin** role

### 5. New Paginated Reports

When adding a new paginated report to the repository:

1. **Add to Git**: Place the `.PaginatedReport` folder under `wsartifacts/Paginatedreports/` or `wsartifacts/Reports/`
2. **Git sync to Dev**: The CI/CD pipeline runs `updateFromGit` which syncs the report to the Dev workspace
3. **Set deployment rules**: In the Fabric portal, add data source rules for the new report on UAT and Prod stages
4. **Deploy**: The next CI/CD run for UAT/Prod will automatically pick up the new report and promote it via the deployment pipeline

The `data_source_mapping` in the config serves as the single source of truth for what the rules should be configured to, eliminating guesswork.

## API Endpoints Used

| Operation | API | Endpoint |
|-----------|-----|----------|
| List pipelines | Fabric REST API | `GET /v1/deploymentPipelines` |
| Get pipeline | Fabric REST API | `GET /v1/deploymentPipelines/{id}` |
| List stages | Fabric REST API | `GET /v1/deploymentPipelines/{id}/stages` |
| List stage items | Fabric REST API | `GET /v1/deploymentPipelines/{id}/stages/{stageId}/items` |
| Deploy | Fabric REST API | `POST /v1/deploymentPipelines/{id}/deploy` |
| Poll operation | Fabric REST API | `GET /v1/deploymentPipelines/{id}/operations/{opId}` |

## Known Limitations

1. **Data source rules are UI-only**: There is no REST API to create or update deployment rules programmatically. They must be set once in the Fabric portal.

2. **Parameter rules not supported for paginated reports**: Only data source rules work for paginated reports. Semantic models support both.

3. **PBIR reports not supported**: Power BI reports in PBIR format cannot be deployed via deployment pipelines. They should continue using the Fabric Items API (`updateDefinition`).

4. **Max 300 items per deployment**: The API limits a single deploy call to 300 items.

5. **Report Builder incompatibility**: After deploying a paginated report with a data source rule, it cannot be opened in Power BI Report Builder.

6. **Owner requirement for rules**: You must be the owner of the item to create deployment rules for it.

7. **Same-type data source only**: Data source rules can only change to a data source of the same type (e.g., SQL Server → SQL Server).

## Troubleshooting

### Pipeline not found
```
❌ Deployment pipeline 'DataEng-Pipeline' not found
```
- Verify the `pipeline_name` in config matches exactly (case-sensitive)
- Ensure the service principal has been granted access to the pipeline

### Item not found in source stage
```
⚠ Not found in source stage: MonthlySalesReport (PaginatedReport)
```
- The item must exist in the source workspace first
- For Dev → UAT: ensure Git sync has run and the report exists in the Dev workspace
- For UAT → Prod: ensure the previous deployment to UAT succeeded

### Deployment fails with permission error
- The service principal needs **Pipeline.Deploy** scope
- The SP needs **Admin** or **Member** role on the pipeline
- The SP needs **Contributor** role on both source and target workspaces

### Data source not remapped
- Verify deployment rules are set on the **target** stage in the Fabric portal
- Check that the rule source matches the actual data source in the source stage
- Rules only apply to same-type data sources

## Files Changed

| File | Changes |
|------|---------|
| `scripts/fabric_client.py` | Added 10 Deployment Pipeline API methods |
| `scripts/deploy_artifacts.py` | Added `_deploy_via_pipeline()`, `_get_pipeline_artifact_types()`, `_is_pipeline_artifact()`. Modified `deploy_all()` to split into 3 phases. Updated `_deploy_paginated_report()` to skip when pipeline is enabled. |
| `config/dev.json` | Added `deployment_pipeline` section (disabled) |
| `config/uat.json` | Added `deployment_pipeline` section (enabled, Dev→UAT) |
| `config/prod.json` | Added `deployment_pipeline` section (enabled, UAT→Prod) |
