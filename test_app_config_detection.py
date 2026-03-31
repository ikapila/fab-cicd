"""Tests for content-aware config change detection and deploy_all app update flow."""
import json
import subprocess
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from scripts.change_detector import ChangeDetector


def test_has_config_changes_unchanged():
    """has_config_changes still works as before."""
    cd = ChangeDetector("uat", Path("."), Path("."))
    assert cd.has_config_changes(["config/uat.json"]) is True
    assert cd.has_config_changes(["wsartifacts/Notebooks/test.ipynb"]) is False
    print("PASSED: has_config_changes() unchanged")


def test_deployment_config_no_last_commit():
    """Without a previous commit, has_deployment_config_changes returns True."""
    cd = ChangeDetector("uat", Path("."), Path("."))
    cd.app_config_changed = False
    result = cd.has_deployment_config_changes(["config/uat.json"])
    assert result is True, f"Expected True, got {result}"
    assert cd.app_config_changed is False
    print("PASSED: falls back to True when no previous commit")


def test_deployment_config_non_config_file():
    """Non-config files return False."""
    cd = ChangeDetector("uat", Path("."), Path("."))
    cd.app_config_changed = False
    result = cd.has_deployment_config_changes(["wsartifacts/Notebooks/test.ipynb"])
    assert result is False
    assert cd.app_config_changed is False
    print("PASSED: non-config files return False")


def test_only_app_config_changed():
    """When only workspace_app differs, deployment is NOT triggered and app_config_changed is set."""
    cd = ChangeDetector("uat", Path("."), Path("."))
    cd.app_config_changed = False

    old_config = {
        "parameters": {"batch_size": "500"},
        "workspace_app": {"enabled": True, "audiences": [{"name": "Old"}]},
    }
    current_config = {
        "parameters": {"batch_size": "500"},
        "workspace_app": {"enabled": True, "audiences": [{"name": "New Audience"}]},
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        # Write current config
        config_dir = Path(tmpdir) / "config"
        config_dir.mkdir()
        with open(config_dir / "uat.json", "w") as f:
            json.dump(current_config, f)

        cd_test = ChangeDetector("uat", Path(tmpdir), Path(tmpdir))
        cd_test.app_config_changed = False

        # Mock get_last_deployment_commit to return a fake commit
        with patch.object(cd_test, "get_last_deployment_commit", return_value="abc123"):
            # Mock subprocess to return old config from git show
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(old_config)

            with patch("scripts.change_detector.subprocess.run", return_value=mock_result):
                result = cd_test.has_deployment_config_changes(["config/uat.json"])

        assert result is False, f"Expected False (app-only change), got {result}"
        assert cd_test.app_config_changed is True
        print("PASSED: only workspace_app changed — no full deploy, flag set")


def test_deployment_relevant_config_changed():
    """When parameters differ, full deployment IS triggered."""
    old_config = {
        "parameters": {"batch_size": "500"},
        "workspace_app": {"enabled": True, "audiences": []},
    }
    current_config = {
        "parameters": {"batch_size": "1000"},  # Changed!
        "workspace_app": {"enabled": True, "audiences": []},
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / "config"
        config_dir.mkdir()
        with open(config_dir / "uat.json", "w") as f:
            json.dump(current_config, f)

        cd_test = ChangeDetector("uat", Path(tmpdir), Path(tmpdir))
        cd_test.app_config_changed = False

        with patch.object(cd_test, "get_last_deployment_commit", return_value="abc123"):
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(old_config)

            with patch("scripts.change_detector.subprocess.run", return_value=mock_result):
                result = cd_test.has_deployment_config_changes(["config/uat.json"])

        assert result is True, f"Expected True (deployment config changed), got {result}"
        assert cd_test.app_config_changed is False
        print("PASSED: deployment-relevant config changed — full deploy triggered")


def test_both_config_sections_changed():
    """When both workspace_app AND parameters differ, full deploy IS triggered."""
    old_config = {
        "parameters": {"batch_size": "500"},
        "workspace_app": {"enabled": True, "audiences": [{"name": "Old"}]},
    }
    current_config = {
        "parameters": {"batch_size": "1000"},  # Changed
        "workspace_app": {"enabled": True, "audiences": [{"name": "New"}]},  # Also changed
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / "config"
        config_dir.mkdir()
        with open(config_dir / "uat.json", "w") as f:
            json.dump(current_config, f)

        cd_test = ChangeDetector("uat", Path(tmpdir), Path(tmpdir))
        cd_test.app_config_changed = False

        with patch.object(cd_test, "get_last_deployment_commit", return_value="abc123"):
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(old_config)

            with patch("scripts.change_detector.subprocess.run", return_value=mock_result):
                result = cd_test.has_deployment_config_changes(["config/uat.json"])

        assert result is True, f"Expected True (both changed), got {result}"
        assert cd_test.app_config_changed is False
        print("PASSED: both app + deployment config changed — full deploy triggered")


if __name__ == "__main__":
    test_has_config_changes_unchanged()
    test_deployment_config_no_last_commit()
    test_deployment_config_non_config_file()
    test_only_app_config_changed()
    test_deployment_relevant_config_changed()
    test_both_config_sections_changed()
    print("\n✅ All tests passed!")
