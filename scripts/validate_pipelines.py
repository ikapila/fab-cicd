#!/usr/bin/env python3
"""
Validate Data Pipeline Definitions
Checks that all pipeline JSON files are valid and properly formatted
"""

import json
import sys
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def validate_pipeline(pipeline_path: Path) -> bool:
    """
    Validate a single pipeline definition file
    
    Args:
        pipeline_path: Path to the pipeline JSON file
        
    Returns:
        True if valid, False otherwise
    """
    try:
        with open(pipeline_path, 'r', encoding='utf-8') as f:
            pipeline = json.load(f)
        
        # Check required top-level fields
        if 'name' not in pipeline:
            logger.error(f"{pipeline_path}: Missing required field 'name'")
            return False
        
        # Check properties if present
        if 'properties' in pipeline:
            properties = pipeline['properties']
            
            # Validate activities if present
            if 'activities' in properties:
                activities = properties['activities']
                if not isinstance(activities, list):
                    logger.error(f"{pipeline_path}: 'activities' must be a list")
                    return False
                
                for i, activity in enumerate(activities):
                    if 'name' not in activity:
                        logger.error(f"{pipeline_path}: Activity {i} missing 'name'")
                        return False
                    if 'type' not in activity:
                        logger.error(f"{pipeline_path}: Activity {i} missing 'type'")
                        return False
        
        logger.info(f"✓ {pipeline_path.name} is valid")
        return True
        
    except json.JSONDecodeError as e:
        logger.error(f"{pipeline_path}: Invalid JSON - {str(e)}")
        return False
    except Exception as e:
        logger.error(f"{pipeline_path}: Validation error - {str(e)}")
        return False


def main():
    """Main validation function"""
    # Find all pipeline files
    repo_root = Path(__file__).parent.parent
    pipelines_dir = repo_root / "datapipelines"
    
    if not pipelines_dir.exists():
        logger.warning(f"Pipelines directory not found: {pipelines_dir}")
        logger.info("No pipelines to validate")
        return 0
    
    pipeline_files = list(pipelines_dir.glob("*.json"))
    
    if not pipeline_files:
        logger.info("No pipeline files found to validate")
        return 0
    
    logger.info(f"Validating {len(pipeline_files)} pipeline(s)...")
    
    failed = []
    for pipeline_path in sorted(pipeline_files):
        if not validate_pipeline(pipeline_path):
            failed.append(pipeline_path)
    
    # Summary
    print("\n" + "=" * 60)
    if failed:
        logger.error(f"Validation FAILED: {len(failed)} pipeline(s) have errors")
        for path in failed:
            logger.error(f"  ✗ {path.name}")
        return 1
    else:
        logger.info(f"Validation PASSED: All {len(pipeline_files)} pipeline(s) are valid")
        return 0


if __name__ == "__main__":
    sys.exit(main())
