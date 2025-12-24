# SQL Views Deployment - ODBC Driver Requirements

## Issue

SQL view deployment fails with error:
```
ERROR: Can't open lib 'ODBC Driver 18 for SQL Server' : file not found
```

## Root Cause

SQL views are deployed using `pyodbc` which requires the **Microsoft ODBC Driver 18 for SQL Server** to be installed on the system. Azure DevOps build agents do not have this driver pre-installed.

## Solution: Install ODBC Driver in Pipeline

Add this step to your `azure-pipelines.yml` **BEFORE** the deployment step:

```yaml
- task: Bash@3
  displayName: 'Install ODBC Driver 18 for SQL Server'
  inputs:
    targetType: 'inline'
    script: |
      # Add Microsoft repository
      curl https://packages.microsoft.com/keys/microsoft.asc | sudo tee /etc/apt/trusted.gpg.d/microsoft.asc
      
      # Add repository for Ubuntu 22.04 (adjust version as needed)
      curl https://packages.microsoft.com/config/ubuntu/22.04/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
      
      # Update package list
      sudo apt-get update
      
      # Install ODBC Driver 18
      sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18
      
      # Install unixODBC development headers (optional, for development)
      sudo apt-get install -y unixodbc-dev
      
      # Verify installation
      odbcinst -j
      odbcinst -q -d
```

### For Different OS

**Ubuntu 20.04:**
```bash
curl https://packages.microsoft.com/config/ubuntu/20.04/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
```

**Ubuntu 24.04:**
```bash
curl https://packages.microsoft.com/config/ubuntu/24.04/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
```

**Red Hat/CentOS:**
```bash
sudo curl -o /etc/yum.repos.d/mssql-release.repo https://packages.microsoft.com/config/rhel/8/prod.repo
sudo yum remove unixODBC-utf16 unixODBC-utf16-devel
sudo ACCEPT_EULA=Y yum install -y msodbcsql18
```

## Complete Pipeline Example

```yaml
stages:
  - stage: Deploy
    displayName: 'Deploy to Dev'
    jobs:
      - job: DeployJob
        displayName: 'Deploy Artifacts'
        pool:
          vmImage: 'ubuntu-latest'
        
        steps:
          - checkout: self
            fetchDepth: 0
            
          # Install ODBC Driver
          - task: Bash@3
            displayName: 'Install ODBC Driver 18 for SQL Server'
            inputs:
              targetType: 'inline'
              script: |
                curl https://packages.microsoft.com/keys/microsoft.asc | sudo tee /etc/apt/trusted.gpg.d/microsoft.asc
                curl https://packages.microsoft.com/config/ubuntu/22.04/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
                sudo apt-get update
                sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18
                odbcinst -q -d
          
          # Install Python dependencies
          - task: UsePythonVersion@0
            inputs:
              versionSpec: '3.11'
          
          - task: Bash@3
            displayName: 'Install Python Dependencies'
            inputs:
              targetType: 'inline'
              script: |
                python -m pip install --upgrade pip
                pip install -r scripts/requirements.txt
          
          # Deploy artifacts
          - task: Bash@3
            displayName: 'Deploy to Dev Workspace'
            env:
              AZURE_CLIENT_SECRET_DEV: $(AZURE_CLIENT_SECRET_DEV)
            inputs:
              targetType: 'inline'
              script: |
                cd $(Build.SourcesDirectory)
                python scripts/deploy_artifacts.py dev
```

## Alternative: Skip ODBC Driver Installation

If you don't want to install ODBC driver, you have these options:

### Option 1: Deploy Views Manually
Comment out view deployment in the pipeline and deploy SQL views manually through Fabric UI or SQL endpoint.

### Option 2: Use Pre-installed Agent
Use a self-hosted agent with ODBC driver pre-installed.

### Option 3: Use Docker Container
Use a container with ODBC driver already installed:

```yaml
pool:
  vmImage: 'ubuntu-latest'

container:
  image: mcr.microsoft.com/mssql/server:2022-latest
  options: --add-host host.docker.internal:host-gateway
```

## Verification

After installing, verify the driver is available:

```bash
odbcinst -q -d
```

Should show:
```
[ODBC Driver 18 for SQL Server]
```

## Troubleshooting

### Driver not found after installation
```bash
# Check if driver file exists
ls -la /opt/microsoft/msodbcsql18/lib64/libmsodbcsql-18.*.so.*

# Check odbcinst configuration
cat /etc/odbcinst.ini
```

### Permission issues
Ensure the build agent has sudo access for installation.

### Network issues
If Microsoft repository is unreachable, check firewall/proxy settings.

## Technical Details

### Why ODBC is Required

SQL views are deployed using the following flow:
1. Get lakehouse SQL endpoint from Fabric API
2. Connect using `pyodbc` library
3. Execute `CREATE VIEW` or `ALTER VIEW` SQL statements
4. Views are created directly in the lakehouse SQL endpoint

### Connection String Format
```
DRIVER={ODBC Driver 18 for SQL Server};
SERVER={endpoint-guid}.datawarehouse.fabric.microsoft.com;
DATABASE={lakehouse_name};
Encrypt=yes;
TrustServerCertificate=no;
```

### Authentication
Uses Azure AD token from service principal (retrieved via `fabric_auth.py`).

## Related Files

- `scripts/fabric_client.py` - Contains `execute_sql_command()` and `get_lakehouse_sql_endpoint()`
- `scripts/deploy_artifacts.py` - Contains `_deploy_sql_view()` method
- `azure-pipelines.yml` - Pipeline configuration

## See Also

- [Microsoft ODBC Driver Documentation](https://learn.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server)
- [SQL Views Implementation](SQL-VIEWS-IMPLEMENTATION.md)
- [Azure DevOps Pipeline Setup](GITHUB-PUSH-INSTRUCTIONS.md)
