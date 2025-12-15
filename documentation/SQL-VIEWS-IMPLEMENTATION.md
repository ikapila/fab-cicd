# SQL Views Deployment - Implementation Guide

## Overview

This guide documents the SQL Views deployment capability for Microsoft Fabric Lakehouses. SQL views are deployed to lakehouse SQL analytics endpoints using T-SQL statements through secure AAD token authentication.

## Architecture

### Components

1. **View Definition Files** (`views/{lakehouse}/*.sql`)
   - T-SQL CREATE VIEW statements
   - Stored per lakehouse in dedicated directories
   - Support parameter substitution via config

2. **Metadata File** (`views/{lakehouse}/metadata.json`)
   - Declares view dependencies (tables and other views)
   - Enables proper deployment ordering
   - Supports view-to-view dependency chains

3. **SQL Connection Support** (fabric_client.py)
   - AAD token authentication via pyodbc
   - Connection string resolution from lakehouse properties
   - SQL command execution and result retrieval

4. **Dependency Resolution** (dependency_resolver.py)
   - SQL_VIEW artifact type with priority 5
   - Topological sort for correct deployment order
   - Circular dependency detection

## Directory Structure

```
views/
├── SalesDataLakehouse/
│   ├── metadata.json
│   ├── SalesSummary.sql
│   ├── ProductAnalysis.sql
│   └── RegionalPerformance.sql
└── CustomerDataLakehouse/
    ├── metadata.json
    ├── CustomerSegments.sql
    └── CustomerLifetimeValue.sql
```

## Metadata Format

The `metadata.json` file defines dependencies for each view:

```json
{
  "lakehouse": "SalesDataLakehouse",
  "description": "SQL views for sales analytics",
  "dependencies": {
    "SalesSummary": {
      "tables": ["dbo.FactSales"],
      "views": []
    },
    "ProductAnalysis": {
      "tables": ["dbo.DimProduct"],
      "views": ["dbo.SalesSummary"]
    },
    "RegionalPerformance": {
      "tables": [],
      "views": ["dbo.SalesSummary"]
    }
  }
}
```

### Dependency Types

- **tables**: Table references (e.g., `dbo.FactSales`) - ensures lakehouse exists
- **views**: View-to-view dependencies (e.g., `dbo.SalesSummary`) - controls deployment order

## View Definition Files

Create standard T-SQL view definitions:

```sql
-- SalesSummary.sql
CREATE VIEW dbo.SalesSummary
AS
SELECT 
    ProductID,
    Region,
    SaleDate,
    SUM(Quantity) AS TotalQuantity,
    SUM(Amount) AS TotalAmount,
    COUNT(*) AS TransactionCount,
    AVG(Amount) AS AvgTransactionAmount
FROM dbo.FactSales
WHERE SaleDate >= DATEADD(YEAR, -2, GETDATE())
GROUP BY ProductID, Region, SaleDate;
```

### Parameter Substitution

Views support parameter substitution from environment configs:

```sql
-- Example with parameter
CREATE VIEW dbo.ActiveCustomers
AS
SELECT *
FROM dbo.Customers
WHERE Status = '${customer_status}'
    AND CreatedDate >= '${cutoff_date}';
```

## Configuration

Add SQL views to environment config files:

```json
{
  "sql_views": [
    {
      "lakehouse": "SalesDataLakehouse",
      "views": ["SalesSummary", "ProductAnalysis", "RegionalPerformance"],
      "description": "Sales analytics views"
    }
  ]
}
```

## Deployment Flow

### Discovery Phase

1. Scan `views/{lakehouse}/` directories for `.sql` files
2. Read `metadata.json` to load dependencies
3. Register each view as artifact with dependency resolver
4. Build dependency graph including view-to-view relationships

### Deployment Phase

1. Resolve deployment order using topological sort
2. For each view in order:
   - Get lakehouse SQL endpoint connection string
   - Check if view exists
   - Compare existing definition with new definition
   - Execute CREATE VIEW (new) or ALTER VIEW (update)
   - Skip if definitions match (idempotent)

### Dependency Ordering Example

Given these dependencies:
- SalesSummary → depends on → FactSales table
- ProductAnalysis → depends on → SalesSummary view, DimProduct table
- RegionalPerformance → depends on → SalesSummary view

Deployment order will be:
1. SalesSummary (no view dependencies)
2. ProductAnalysis (depends on SalesSummary)
3. RegionalPerformance (depends on SalesSummary)

## Implementation Details

### SQL Connection Methods (fabric_client.py)

#### get_lakehouse_sql_endpoint()
- Retrieves SQL analytics endpoint connection string
- Extracts from lakehouse properties via REST API
- Returns: `{workspace}.datawarehouse.fabric.microsoft.com`

#### execute_sql_command()
- Executes T-SQL statements against SQL endpoint
- Uses pyodbc with AAD token authentication
- Returns query results (SELECT) or None (DDL)

#### check_view_exists()
- Queries `sys.views` catalog to check existence
- Filters by schema and view name
- Returns boolean

#### get_view_definition()
- Retrieves view DDL from `sys.sql_modules`
- Returns CREATE VIEW statement text
- Used for compare-and-skip logic

### Discovery Logic (deploy_artifacts.py)

```python
def _discover_sql_views(self) -> None:
    """Discover SQL view definitions from views/{lakehouse}/ directories"""
    views_dir = self.artifacts_dir / "views"
    
    for lakehouse_dir in views_dir.iterdir():
        lakehouse_name = lakehouse_dir.name
        metadata_file = lakehouse_dir / "metadata.json"
        
        # Read metadata for dependencies
        with open(metadata_file) as f:
            metadata = json.load(f)
            dependencies_map = metadata.get("dependencies", {})
        
        # Discover .sql files
        for view_file in lakehouse_dir.glob("*.sql"):
            view_name = view_file.stem
            view_id = f"view-{lakehouse_name}-{view_name}"
            
            # Build dependency list
            artifact_dependencies = [f"lakehouse-{lakehouse_name}"]
            
            # Add view-to-view dependencies
            view_deps = dependencies_map.get(view_name, {}).get("views", [])
            for dep_view in view_deps:
                dep_view_id = f"view-{lakehouse_name}-{dep_view.split('.')[-1]}"
                artifact_dependencies.append(dep_view_id)
            
            # Register with resolver
            self.resolver.add_artifact(
                view_id,
                ArtifactType.SQL_VIEW,
                view_name,
                dependencies=artifact_dependencies
            )
```

### Deployment Logic (deploy_artifacts.py)

```python
def _deploy_sql_view(self, name: str) -> None:
    """Deploy a SQL view to lakehouse SQL endpoint"""
    # Find view file
    view_file = self._find_view_file(name)
    
    # Read and substitute parameters
    with open(view_file) as f:
        view_sql = f.read()
    view_sql = self.config.substitute_parameters(view_sql)
    
    # Get SQL endpoint
    connection_string = self.client.get_lakehouse_sql_endpoint(
        workspace_id, lakehouse_id
    )
    
    # Check if view exists
    if self.client.check_view_exists(connection_string, lakehouse_name, schema, view_name):
        # Get existing definition
        existing_def = self.client.get_view_definition(...)
        
        # Compare normalized definitions
        if normalize_sql(view_sql) == normalize_sql(existing_def):
            logger.info("View is up to date, skipping")
            return
        
        # Update view
        alter_sql = view_sql.replace("CREATE VIEW", "ALTER VIEW", 1)
        self.client.execute_sql_command(connection_string, lakehouse_name, alter_sql)
    else:
        # Create new view
        self.client.execute_sql_command(connection_string, lakehouse_name, view_sql)
```

## Security and Permissions

### Service Principal Requirements

The service principal needs these permissions:

1. **Workspace Access**: Admin or Contributor role
2. **Lakehouse Access**: Read/Write permissions
3. **SQL Endpoint Access**: `db_ddladmin` role for CREATE/ALTER VIEW

### Setting SQL Permissions

```sql
-- Grant permissions to service principal
-- Run as lakehouse owner in SQL endpoint
EXEC sp_addrolemember 'db_ddladmin', '<service-principal-app-id>';
```

## Error Handling

### Common Issues

1. **"pyodbc not available"**
   - Install: `pip install pyodbc>=5.0.0`
   - Requires ODBC Driver 18 for SQL Server

2. **"Lakehouse does not have SQL endpoint enabled"**
   - Ensure lakehouse has SQL analytics endpoint
   - Wait for endpoint provisioning to complete

3. **"Permission denied on CREATE VIEW"**
   - Grant `db_ddladmin` role to service principal
   - Check workspace permissions

4. **Circular dependency detected**
   - Review metadata.json dependencies
   - Views cannot reference each other circularly

## Testing

### Manual Testing

```bash
# Install dependencies
cd scripts
pip install -r requirements.txt

# Run deployment
python deploy_artifacts.py --environment dev --workspace-id <workspace-id>
```

### Validation

After deployment, verify views in SQL endpoint:

```sql
-- List all views
SELECT 
    s.name AS SchemaName,
    v.name AS ViewName,
    v.create_date,
    v.modify_date
FROM sys.views v
JOIN sys.schemas s ON v.schema_id = s.schema_id
ORDER BY s.name, v.name;

-- Query a deployed view
SELECT TOP 10 * FROM dbo.SalesSummary;
```

## Limitations

1. **Single Lakehouse Scope**: Views in one lakehouse cannot reference tables/views in another lakehouse
2. **No Cross-Database Queries**: Each lakehouse is a separate database
3. **SQL Endpoint Only**: Views are not visible in lakehouse explorer (Files/Tables), only via SQL endpoint
4. **Read-Only Tables**: Base tables in lakehouse are read-only from SQL endpoint perspective

## Best Practices

1. **Use Descriptive Names**: Name views clearly (e.g., `SalesSummary`, `ProductAnalysis`)
2. **Document Dependencies**: Always maintain accurate `metadata.json`
3. **Test Locally First**: Validate SQL syntax before committing
4. **Schema Qualification**: Always use schema prefix (e.g., `dbo.TableName`)
5. **Incremental Complexity**: Build simple views first, then compose complex views
6. **Monitor Performance**: Views execute on-demand, consider materialization for heavy queries

## Example: Multi-Level Dependency Chain

```
SalesSummary (base view)
    ↓
ProductAnalysis (depends on SalesSummary)
    ↓
ProductRanking (depends on ProductAnalysis)
    ↓
ExecutiveDashboard (depends on ProductRanking, SalesSummary)
```

Deployment order: SalesSummary → ProductAnalysis → ProductRanking → ExecutiveDashboard

## References

- [Microsoft Fabric SQL Analytics Endpoint](https://learn.microsoft.com/fabric/data-engineering/lakehouse-sql-analytics-endpoint)
- [T-SQL CREATE VIEW](https://learn.microsoft.com/sql/t-sql/statements/create-view-transact-sql)
- [pyodbc Documentation](https://github.com/mkleehammer/pyodbc/wiki)
- [Azure SQL Authentication with AAD Token](https://learn.microsoft.com/azure/azure-sql/database/authentication-aad-overview)

## Changelog

- **2024-12-14**: Initial implementation with view-to-view dependency support
- Added SQL_VIEW artifact type to dependency resolver
- Implemented SQL connection support via pyodbc
- Created discovery and deployment logic
- Added example views for SalesDataLakehouse
