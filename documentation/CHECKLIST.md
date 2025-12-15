# Quick Start Checklist

Use this checklist to track your implementation progress.

## ☐ Phase 1: Prerequisites (Week 1)

### Azure Setup
- [ ] Microsoft Fabric subscription with Premium/Fabric capacity
- [ ] Access to Azure Portal with permissions to create Service Principals
- [ ] Access to Microsoft Fabric portal

### Create Workspaces
- [ ] Create `DataEng-Dev` workspace in Fabric
- [ ] Create `DataEng-UAT` workspace in Fabric
- [ ] Create `DataEng-Prod` workspace in Fabric
- [ ] Note down all three workspace IDs

### Service Principal Setup (Per Environment)
**Development Service Principal:**
- [ ] Navigate to Azure Portal → Azure Entra ID → App registrations
- [ ] Create app registration: `fabric-cicd-dev-sp`
- [ ] Copy Dev Application (client) ID: ________________
- [ ] Copy Tenant ID: ________________
- [ ] Create client secret for Dev SP
- [ ] Copy Dev secret value: ________________ (store securely!)
- [ ] Add Dev SP to Dev workspace as Admin

**UAT Service Principal:**
- [ ] Create app registration: `fabric-cicd-uat-sp`
- [ ] Copy UAT Application (client) ID: ________________
- [ ] Create client secret for UAT SP
- [ ] Copy UAT secret value: ________________ (store securely!)
- [ ] Add UAT SP to UAT workspace as Admin

**Production Service Principal:**
- [ ] Create app registration: `fabric-cicd-prod-sp`
- [ ] Copy Prod Application (client) ID: ________________
- [ ] Create client secret for Prod SP
- [ ] Copy Prod secret value: ________________ (store securely!)
- [ ] Add Prod SP to Prod workspace as Admin

## ☐ Phase 2: Repository Setup (Week 1)

### Git Repository
- [ ] Clone this repository locally
- [ ] Create `development` branch: `git checkout -b development`
- [ ] Create `uat` branch: `git checkout -b uat`
- [ ] Create `main` branch: `git checkout -b main`
- [ ] Push all branches to remote

### Configuration Files
- [ ] Edit `config/dev.json`
  - [ ] Update service_principal.client_id (Dev SP)
  - [ ] Update service_principal.tenant_id
  - [ ] Verify service_principal.secret_env_var = "AZURE_CLIENT_SECRET_DEV"
  - [ ] Update workspace ID
  - [ ] Update workspace name
  - [ ] Update storage account name
  - [ ] Update Key Vault URL
  - [ ] Update data lake path
  - [ ] Adjust parameters as needed
  - [ ] Add artifacts to create in artifacts_to_create section (optional)

- [ ] Edit `config/uat.json`
  - [ ] Update service_principal.client_id (UAT SP)
  - [ ] Update service_principal.tenant_id
  - [ ] Verify service_principal.secret_env_var = "AZURE_CLIENT_SECRET_UAT"
  - [ ] Update workspace ID
  - [ ] Update workspace name
  - [ ] Update storage account name
  - [ ] Update Key Vault URL
  - [ ] Update data lake path
  - [ ] Adjust parameters as needed
  - [ ] Add artifacts to create in artifacts_to_create section (optional)

- [ ] Edit `config/prod.json`
  - [ ] Update service_principal.client_id (Prod SP)
  - [ ] Update service_principal.tenant_id
  - [ ] Verify service_principal.secret_env_var = "AZURE_CLIENT_SECRET_PROD"
  - [ ] Update workspace ID
  - [ ] Update workspace name
  - [ ] Update storage account name
  - [ ] Update Key Vault URL
  - [ ] Update data lake path
  - [ ] Adjust parameters as needed
  - [ ] Add artifacts to create in artifacts_to_create section (optional)

## ☐ Phase 3: Local Testing (Week 1)

### Python Environment
- [ ] Install Python 3.11 or higher
- [ ] Navigate to scripts directory: `cd scripts`
- [ ] Install dependencies: `pip install -r requirements.txt`

### Test Authentication
- [ ] Set environment variables:
  ```bash
  export AZURE_CLIENT_ID="your-client-id"
  export AZURE_CLIENT_SECRET="your-client-secret"
  export AZURE_TENANT_ID="your-tenant-id"
  ```
- [ ] Test authentication: `python fabric_auth.py`
- [ ] Should see "✅ Authentication successful!"

### Test Configuration
- [ ] Test Dev config: `python config_manager.py dev`
- [ ] Test UAT config: `python config_manager.py uat`
- [ ] Test Prod config: `python config_manager.py prod`
- [ ] Verify all configurations load without errors

### Test Deployment (Dry Run)
- [ ] Run dry-run deployment: `python deploy_artifacts.py dev --dry-run`
- [ ] Verify no errors in deployment plan
- [ ] Review deployment order

## ☐ Phase 4: Git Integration (Week 1-2)

### Connect Dev Workspace
- [ ] Open `DataEng-Dev` workspace in Fabric portal
- [ ] Go to Workspace settings → Git integration
- [ ] Select Git provider (Azure DevOps or GitHub)
- [ ] Authenticate with Git provider
- [ ] Configure connection:
  - [ ] Organization: ________________
  - [ ] Repository: fabric-data-engineering
  - [ ] Branch: development
  - [ ] Folder: / (root)
- [ ] Click Connect
- [ ] Verify "Connected to Git" status appears

### Initial Commit
- [ ] Click "Source control" in workspace
- [ ] Review uncommitted changes
- [ ] Add commit message: "Initial commit of Data Engineering artifacts"
- [ ] Click Commit
- [ ] Verify artifacts appear in Git repository

## ☐ Phase 5: CI/CD Pipeline Setup (Week 2)

### Choose Your Platform
Select ONE:
- [ ] Option A: Azure DevOps
- [ ] Option B: GitHub Actions

### Azure DevOps Setup (if chosen)
- [ ] Navigate to Azure DevOps project
- [ ] Create new pipeline
- [ ] Point to `azure-pipelines.yml`
- [ ] Create variable group: `fabric-secrets`
- [ ] Add secrets to variable group (per-environment):
  - [ ] AZURE_CLIENT_SECRET_DEV (Dev SP secret)
  - [ ] AZURE_CLIENT_SECRET_UAT (UAT SP secret)
  - [ ] AZURE_CLIENT_SECRET_PROD (Prod SP secret)
- [ ] Mark all secrets as "secret" (hidden values)
- [ ] Create environments:
  - [ ] fabric-dev (no approvals)
  - [ ] fabric-uat (1 approval required)
  - [ ] fabric-prod (2 approvals required)
- [ ] Save pipeline

### GitHub Actions Setup (if chosen)
- [ ] Navigate to repository Settings
- [ ] Go to Secrets and variables → Actions
- [ ] Add repository secrets (per-environment):
  - [ ] AZURE_CLIENT_SECRET_DEV
  - [ ] AZURE_CLIENT_SECRET_UAT
  - [ ] AZURE_CLIENT_SECRET_PROD
- [ ] Go to Environments
- [ ] Create environment: fabric-dev (no protection rules)
- [ ] Create environment: fabric-uat (1 required reviewer)
- [ ] Create environment: fabric-prod (2 required reviewers)
- [ ] Workflow file already exists at `.github/workflows/deploy.yml`

## ☐ Phase 6: Testing Deployments (Week 2-3)

### Test Dev Deployment
- [ ] Make a small change in Dev workspace
- [ ] Commit to `development` branch
- [ ] Push to remote
- [ ] Watch pipeline/workflow execute
- [ ] Verify deployment succeeds
- [ ] Check deployment logs

### Test UAT Promotion
- [ ] Create Pull Request: `development` → `uat`
- [ ] Review changes in PR
- [ ] Approve and merge PR
- [ ] Receive approval notification
- [ ] Approve deployment
- [ ] Watch pipeline/workflow execute
- [ ] Verify deployment to UAT workspace succeeds
- [ ] Run validation tests in UAT

### Test Production Promotion
- [ ] Create Pull Request: `uat` → `main`
- [ ] Review changes in PR
- [ ] Get two approvals on PR
- [ ] Merge PR
- [ ] Receive approval notification (Approval 1)
- [ ] First approver approves deployment
- [ ] Receive approval notification (Approval 2)
- [ ] Second approver approves deployment
- [ ] Watch pipeline/workflow execute
- [ ] Verify backup is created
- [ ] Verify deployment to Production workspace succeeds
- [ ] Run production validation tests

### Test Rollback
- [ ] Note current production commit SHA: ________________
- [ ] Trigger rollback workflow/pipeline
- [ ] Specify rollback environment: prod
- [ ] Specify target commit: (previous commit SHA)
- [ ] Approve rollback
- [ ] Verify artifacts reverted successfully

## ☐ Phase 7: Documentation & Training (Week 3-4)

### Documentation
- [ ] Document your workspace IDs and configurations
- [ ] Document approval process and approvers
- [ ] Document rollback procedures
- [ ] Create troubleshooting guide for your team
- [ ] Document monitoring and alerting setup

### Team Training
- [ ] Schedule training session
- [ ] Walk through Git workflow
- [ ] Demonstrate making changes in Dev
- [ ] Show how to create Pull Requests
- [ ] Explain approval process
- [ ] Demonstrate rollback procedure
- [ ] Q&A session

### Operational Procedures
- [ ] Define who can approve UAT deployments
- [ ] Define who can approve Production deployments
- [ ] Set up deployment notification channels
- [ ] Create on-call procedures for deployment issues
- [ ] Schedule regular sync meetings

## ☐ Phase 8: Go Live! (Week 4)

### Pre-Launch Checks
- [ ] All three environments operational
- [ ] Git sync working correctly
- [ ] Pipelines/workflows executing successfully
- [ ] Approval gates functioning
- [ ] Rollback tested and working
- [ ] Team trained and confident
- [ ] Monitoring and alerts configured
- [ ] Documentation complete

### Launch Day
- [ ] Announce go-live to team
- [ ] Monitor first production deployment closely
- [ ] Be available for questions and support
- [ ] Collect feedback from team

### Post-Launch
- [ ] Review first week of deployments
- [ ] Address any issues or concerns
- [ ] Gather team feedback
- [ ] Make adjustments as needed
- [ ] Celebrate success! 🎉

## ☐ Ongoing Maintenance

### Weekly
- [ ] Review deployment logs
- [ ] Check for failed deployments
- [ ] Monitor pipeline performance
- [ ] Address any issues

### Monthly
- [ ] Review service principal expiry dates
- [ ] Update Python dependencies if needed
- [ ] Review and update documentation
- [ ] Collect team feedback

### Quarterly
- [ ] Rotate service principal secrets
- [ ] Review and update approval list
- [ ] Audit workspace access
- [ ] Test disaster recovery procedures

---

## 📝 Notes & Issues

Use this section to track any issues or notes during implementation:

```
Date: ____________
Issue: 
Resolution:

Date: ____________
Issue:
Resolution:

Date: ____________
Issue:
Resolution:
```

---

## ✅ Completion

- [ ] All phases completed
- [ ] Team is comfortable with new workflow
- [ ] Production deployments running smoothly
- [ ] Documentation is complete and accessible

**Completion Date:** ____________

**Sign-off:** ____________

---

**Congratulations! Your Fabric CI/CD implementation is complete!** 🚀
