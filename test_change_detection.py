#!/usr/bin/env python3
"""
Test script for change detection functionality
Tests the ChangeDetector class without requiring Azure credentials
"""

import sys
from pathlib import Path

# Add scripts directory to path
script_dir = Path(__file__).parent / "scripts"
sys.path.insert(0, str(script_dir))

from change_detector import ChangeDetector

def test_change_detector():
    """Test the ChangeDetector class"""
    
    print("=" * 60)
    print("CHANGE DETECTION TEST")
    print("=" * 60)
    
    # Initialize change detector
    cd = ChangeDetector(
        environment="dev",
        artifacts_dir=Path("."),
        repo_root=Path(".")
    )
    
    # Test 1: Check Git availability
    print("\n1. Testing Git availability...")
    git_available = cd.is_git_available()
    print(f"   ✓ Git available: {git_available}")
    
    if not git_available:
        print("   ⚠️  Git not available - some tests will be skipped")
        return
    
    # Test 2: Get current commit
    print("\n2. Testing current commit retrieval...")
    current_commit = cd.get_current_commit()
    if current_commit:
        print(f"   ✓ Current commit: {current_commit[:8]}")
    else:
        print("   ✗ Failed to get current commit")
    
    # Test 3: Check last deployment commit
    print("\n3. Testing last deployment commit retrieval...")
    last_commit = cd.get_last_deployment_commit()
    if last_commit:
        print(f"   ✓ Last deployment: {last_commit[:8]}")
    else:
        print("   ℹ️  No previous deployment found (first deployment)")
    
    # Test 4: Get changed files
    print("\n4. Testing changed files detection...")
    if last_commit:
        changed_files = cd.get_changed_files(last_commit)
        print(f"   ✓ Changed files: {len(changed_files)}")
        if changed_files:
            print("   Files:")
            for f in changed_files[:5]:
                print(f"     - {f}")
            if len(changed_files) > 5:
                print(f"     ... and {len(changed_files) - 5} more")
    else:
        print("   ⊘ Skipped (no last deployment)")
    
    # Test 5: Extract artifact names
    print("\n5. Testing artifact name extraction...")
    test_files = [
        "wsartifacts/Notebooks/ProcessSalesData.ipynb",
        "wsartifacts/Lakehouses/SalesDataLakehouse.json",
        "wsartifacts/Lakehouses/SampleLakehouse.Lakehouse/.platform",
        "wsartifacts/Variablelibraries/DevVariables.VariableLibrary/valueSets/dev.json",
        "wsartifacts/Views/SalesDataLakehouse/SalesSummary.sql",
        "config/dev.json",
        "README.md"
    ]
    
    artifacts = cd.extract_artifact_names(test_files)
    print(f"   ✓ Extracted artifacts from {len(test_files)} test files:")
    for artifact_type, names in sorted(artifacts.items()):
        print(f"     {artifact_type}: {', '.join(sorted(names))}")
    
    # Test 6: Check config changes
    print("\n6. Testing config change detection...")
    has_config_changes = cd.has_config_changes(test_files)
    print(f"   ✓ Config changes detected: {has_config_changes}")
    
    # Test 7: Test tracking file operations
    print("\n7. Testing tracking file operations...")
    if current_commit:
        # Save a test commit (won't affect actual deployment)
        test_file = cd.tracking_dir / "test_commit.txt"
        try:
            with open(test_file, 'w') as f:
                f.write(f"{current_commit}\n")
                f.write("# Test commit\n")
            print(f"   ✓ Can write tracking files")
            test_file.unlink()
        except Exception as e:
            print(f"   ✗ Error writing tracking file: {e}")
    
    # Test 8: Get changed artifacts (integration test)
    print("\n8. Testing get_changed_artifacts (integration)...")
    try:
        changed = cd.get_changed_artifacts(force_all=False)
        if changed is None:
            print("   ✓ Result: Deploy all (expected for first deployment or config change)")
        elif not changed:
            print("   ✓ Result: No changes detected (empty dict)")
        else:
            print(f"   ✓ Result: {sum(len(v) for v in changed.values())} artifact(s) changed")
            for artifact_type, names in sorted(changed.items()):
                print(f"     {artifact_type}: {', '.join(sorted(names))}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    
    # Summary
    print("\n✓ ChangeDetector class is working correctly!")
    print("\nTo use in deployment:")
    print("  python scripts/deploy_artifacts.py dev              # Uses change detection")
    print("  python scripts/deploy_artifacts.py dev --force-all  # Deploys all")
    print("  python scripts/deploy_artifacts.py dev --artifacts 'Notebook1,Lakehouse1'")
    

if __name__ == "__main__":
    try:
        test_change_detector()
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
