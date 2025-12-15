#!/usr/bin/env python3
"""
Validate Jupyter Notebook Syntax
Checks that all .ipynb files in the repository are valid JSON and properly formatted
"""

import json
import sys
import argparse
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def validate_notebook(notebook_path: Path) -> bool:
    """
    Validate a single notebook file
    
    Args:
        notebook_path: Path to the notebook file
        
    Returns:
        True if valid, False otherwise
    """
    try:
        with open(notebook_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)
        
        # Check required top-level fields
        required_fields = ['cells', 'metadata', 'nbformat', 'nbformat_minor']
        for field in required_fields:
            if field not in notebook:
                logger.error(f"{notebook_path}: Missing required field '{field}'")
                return False
        
        # Validate cells
        if not isinstance(notebook['cells'], list):
            logger.error(f"{notebook_path}: 'cells' must be a list")
            return False
        
        for i, cell in enumerate(notebook['cells']):
            # Check required cell fields
            if 'cell_type' not in cell:
                logger.error(f"{notebook_path}: Cell {i} missing 'cell_type'")
                return False
            
            if 'source' not in cell:
                logger.error(f"{notebook_path}: Cell {i} missing 'source'")
                return False
            
            # Validate cell_type
            valid_types = ['code', 'markdown', 'raw']
            if cell['cell_type'] not in valid_types:
                logger.error(f"{notebook_path}: Cell {i} has invalid cell_type '{cell['cell_type']}'")
                return False
        
        logger.info(f"✓ {notebook_path.name} is valid ({len(notebook['cells'])} cells)")
        return True
        
    except json.JSONDecodeError as e:
        logger.error(f"{notebook_path}: Invalid JSON - {str(e)}")
        return False
    except Exception as e:
        logger.error(f"{notebook_path}: Validation error - {str(e)}")
        return False


def main():
    """Main validation function"""
    parser = argparse.ArgumentParser(description='Validate Jupyter notebook files')
    parser.add_argument(
        '--artifacts-root',
        default='wsartifacts',
        help='Root folder name for artifacts (default: wsartifacts)'
    )
    args = parser.parse_args()
    
    # Find all notebook files
    repo_root = Path(__file__).parent.parent
    notebooks_dir = repo_root / args.artifacts_root / "Notebooks"
    
    if not notebooks_dir.exists():
        logger.warning(f"Notebooks directory not found: {notebooks_dir}")
        logger.info("No notebooks to validate")
        return 0
    
    notebook_files = list(notebooks_dir.glob("*.ipynb"))
    
    if not notebook_files:
        logger.info("No notebook files found to validate")
        return 0
    
    logger.info(f"Validating {len(notebook_files)} notebook(s)...")
    
    failed = []
    for notebook_path in sorted(notebook_files):
        if not validate_notebook(notebook_path):
            failed.append(notebook_path)
    
    # Summary
    print("\n" + "=" * 60)
    if failed:
        logger.error(f"Validation FAILED: {len(failed)} notebook(s) have errors")
        for path in failed:
            logger.error(f"  ✗ {path.name}")
        return 1
    else:
        logger.info(f"Validation PASSED: All {len(notebook_files)} notebook(s) are valid")
        return 0


if __name__ == "__main__":
    sys.exit(main())
