#!/usr/bin/env python3
"""
Validate All Artifact Definitions
Comprehensive validation for all Fabric artifact types
"""

import json
import sys
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def validate_json_file(file_path: Path, artifact_type: str) -> bool:
    """
    Validate a single JSON artifact file
    
    Args:
        file_path: Path to the JSON file
        artifact_type: Type of artifact (for logging)
        
    Returns:
        True if valid, False otherwise
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Notebooks have different structure - just validate JSON
        if artifact_type == "Notebook":
            if 'cells' not in data or 'metadata' not in data:
                logger.error(f"{artifact_type} {file_path.name}: Invalid notebook structure")
                return False
            logger.debug(f"✓ {artifact_type} {file_path.name} is valid")
            return True
        
        # Check for name or displayName field (common across most artifacts)
        if 'name' not in data and 'displayName' not in data:
            logger.error(f"{artifact_type} {file_path.name}: Missing 'name' or 'displayName' field")
            return False
        
        logger.debug(f"✓ {artifact_type} {file_path.name} is valid")
        return True
        
    except json.JSONDecodeError as e:
        logger.error(f"{artifact_type} {file_path.name}: Invalid JSON - {str(e)}")
        return False
    except Exception as e:
        logger.error(f"{artifact_type} {file_path.name}: Validation error - {str(e)}")
        return False


def validate_sql_file(file_path: Path) -> bool:
    """
    Validate a SQL view file
    
    Args:
        file_path: Path to the SQL file
        
    Returns:
        True if valid, False otherwise
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        
        if not content:
            logger.error(f"SQL View {file_path.name}: File is empty")
            return False
        
        # Check for CREATE VIEW statement
        if 'CREATE VIEW' not in content.upper():
            logger.warning(f"SQL View {file_path.name}: No CREATE VIEW statement found")
        
        logger.debug(f"✓ SQL View {file_path.name} is valid")
        return True
        
    except Exception as e:
        logger.error(f"SQL View {file_path.name}: Validation error - {str(e)}")
        return False


def validate_artifact_directory(dir_path: Path, artifact_type: str, extension: str = "*.json") -> tuple:
    """
    Validate all artifacts in a directory
    
    Args:
        dir_path: Path to directory
        artifact_type: Type of artifact
        extension: File extension pattern
        
    Returns:
        Tuple of (total_count, failed_files)
    """
    if not dir_path.exists():
        logger.debug(f"Directory not found: {dir_path}")
        return 0, []
    
    files = list(dir_path.glob(extension))
    if not files:
        return 0, []
    
    failed = []
    for file_path in sorted(files):
        # Skip metadata files
        if file_path.name == "metadata.json":
            continue
            
        if extension == "*.sql":
            if not validate_sql_file(file_path):
                failed.append(file_path)
        else:
            if not validate_json_file(file_path, artifact_type):
                failed.append(file_path)
    
    return len(files), failed


def main():
    """Main validation function"""
    repo_root = Path(__file__).parent.parent
    
    # Define artifact types to validate
    artifacts = [
        ("lakehouses", "Lakehouse", "*.json"),
        ("environments", "Environment", "*.json"),
        ("notebooks", "Notebook", "*.ipynb"),
        ("sparkjobdefinitions", "Spark Job", "*.json"),
        ("datapipelines", "Pipeline", "*.json"),
        ("reports", "Report", "*.json"),
        ("semanticmodels", "Semantic Model", "*.json"),
        ("paginatedreports", "Paginated Report", "*.json"),
        ("variablelibraries", "Variable Library", "*.json"),
    ]
    
    total_artifacts = 0
    total_failed = []
    
    logger.info("Validating all artifact definitions...\n")
    
    # Validate each artifact type
    for dir_name, artifact_type, extension in artifacts:
        dir_path = repo_root / dir_name
        count, failed = validate_artifact_directory(dir_path, artifact_type, extension)
        
        if count > 0:
            status = "✓" if not failed else "✗"
            logger.info(f"{status} {artifact_type}: {count - len(failed)}/{count} valid")
            total_artifacts += count
            total_failed.extend(failed)
    
    # Validate SQL views separately (nested structure)
    views_dir = repo_root / "views"
    if views_dir.exists():
        sql_count = 0
        sql_failed = []
        
        for lakehouse_dir in views_dir.iterdir():
            if lakehouse_dir.is_dir():
                count, failed = validate_artifact_directory(lakehouse_dir, "SQL View", "*.sql")
                sql_count += count
                sql_failed.extend(failed)
        
        if sql_count > 0:
            status = "✓" if not sql_failed else "✗"
            logger.info(f"{status} SQL Views: {sql_count - len(sql_failed)}/{sql_count} valid")
            total_artifacts += sql_count
            total_failed.extend(sql_failed)
    
    # Summary
    print("\n" + "=" * 60)
    if total_artifacts == 0:
        logger.info("No artifacts found to validate")
        return 0
    
    if total_failed:
        logger.error(f"Validation FAILED: {len(total_failed)}/{total_artifacts} artifact(s) have errors")
        for path in total_failed:
            logger.error(f"  ✗ {path.relative_to(repo_root)}")
        return 1
    else:
        logger.info(f"Validation PASSED: All {total_artifacts} artifact(s) are valid")
        return 0


if __name__ == "__main__":
    sys.exit(main())
