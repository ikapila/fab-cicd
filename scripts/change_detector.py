"""
Change Detection for Microsoft Fabric Artifacts
Uses Git to track which artifacts have changed since last deployment
"""

import os
import subprocess
import logging
from typing import List, Dict, Set, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class ChangeDetector:
    """Detects changed artifacts using Git diff between deployments"""
    
    def __init__(self, environment: str, artifacts_dir: Path, repo_root: Path = None):
        """
        Initialize change detector
        
        Args:
            environment: Target environment (dev, uat, prod)
            artifacts_dir: Path to artifacts directory
            repo_root: Path to git repository root (defaults to artifacts_dir parent)
        """
        self.environment = environment
        self.artifacts_dir = Path(artifacts_dir)
        self.repo_root = Path(repo_root) if repo_root else self.artifacts_dir.parent
        self.tracking_dir = self.repo_root / ".deployment_tracking"
        self.commit_file = self.tracking_dir / f"{environment}_last_commit.txt"
        
        # Ensure tracking directory exists
        self.tracking_dir.mkdir(exist_ok=True)
        
        # Artifact type to folder mapping
        self.artifact_folders = {
            "Lakehouse": "Lakehouses",
            "Notebook": "Notebooks",
            "VariableLibrary": "Variablelibraries",
            "DataPipeline": "Datapipelines",
            "Environment": "Environments",
            "SparkJobDefinition": "Sparkjobdefinitions",
            "SqlView": "Views",
            "Report": "Reports",
            "PaginatedReport": "Paginatedreports",
            "SemanticModel": "Semanticmodels"
        }
    
    def is_git_available(self) -> bool:
        """
        Check if Git is available and this is a Git repository
        
        Returns:
            True if Git is available, False otherwise
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
    
    def get_current_commit(self) -> Optional[str]:
        """
        Get current Git commit hash
        
        Returns:
            Current commit hash or None if not available
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )
            return result.stdout.strip()
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            logger.warning(f"Failed to get current commit: {e}")
            return None
    
    def get_last_deployment_commit(self) -> Optional[str]:
        """
        Get the commit hash of the last successful deployment
        
        Returns:
            Last deployment commit hash or None if not found
        """
        if not self.commit_file.exists():
            logger.info(f"No previous deployment found for {self.environment}")
            return None
        
        try:
            with open(self.commit_file, 'r') as f:
                lines = f.readlines()
                if lines:
                    # First line is the commit hash
                    return lines[0].strip()
        except Exception as e:
            logger.warning(f"Failed to read last deployment commit: {e}")
        
        return None
    
    def save_deployment_commit(self, commit_hash: str) -> None:
        """
        Save the current deployment commit hash
        
        Args:
            commit_hash: Git commit hash to save
        """
        try:
            with open(self.commit_file, 'w') as f:
                f.write(f"{commit_hash}\n")
                f.write(f"# Last deployment: {datetime.now().isoformat()}\n")
                f.write(f"# Environment: {self.environment}\n")
            logger.info(f"Saved deployment commit: {commit_hash[:8]}")
        except Exception as e:
            logger.warning(f"Failed to save deployment commit: {e}")
    
    def get_changed_files(self, since_commit: str = None) -> List[str]:
        """
        Get list of changed files since a specific commit
        
        Args:
            since_commit: Commit hash to compare against (defaults to last deployment)
            
        Returns:
            List of changed file paths relative to repo root
        """
        if not since_commit:
            since_commit = self.get_last_deployment_commit()
        
        if not since_commit:
            logger.info("No previous commit found, treating all files as changed")
            return []
        
        try:
            # Get changed files between commits
            result = subprocess.run(
                ["git", "diff", "--name-only", since_commit, "HEAD"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
                timeout=10
            )
            
            changed_files = [f.strip() for f in result.stdout.split('\n') if f.strip()]
            logger.info(f"Found {len(changed_files)} changed file(s) since {since_commit[:8]}")
            
            return changed_files
            
        except subprocess.SubprocessError as e:
            logger.warning(f"Failed to get changed files: {e}")
            return []
    
    def extract_artifact_names(self, changed_files: List[str]) -> Dict[str, Set[str]]:
        """
        Extract artifact names from list of changed files
        
        Args:
            changed_files: List of file paths
            
        Returns:
            Dictionary mapping artifact type to set of artifact names
        """
        artifacts_by_type = {}
        
        for file_path in changed_files:
            path = Path(file_path)
            parts = path.parts
            
            # Skip if not in wsartifacts folder
            if len(parts) < 2 or parts[0] != "wsartifacts":
                continue
            
            folder_name = parts[1]  # e.g., "Notebooks", "Lakehouses"
            
            # Map folder to artifact type
            artifact_type = None
            for atype, afolder in self.artifact_folders.items():
                if folder_name == afolder:
                    artifact_type = atype
                    break
            
            if not artifact_type:
                continue
            
            # Extract artifact name based on type
            artifact_name = None
            
            if artifact_type == "SqlView":
                # Views: wsartifacts/Views/{lakehouse_name}/{view_name}.sql
                if len(parts) >= 4 and parts[-1].endswith('.sql'):
                    artifact_name = parts[-1][:-4]  # Remove .sql extension
            
            elif len(parts) >= 3:
                # Check for Git format folder (e.g., MyArtifact.Lakehouse/)
                if parts[2].endswith(f".{artifact_type}"):
                    # Extract name without suffix
                    artifact_name = parts[2][:-(len(artifact_type) + 1)]
                
                # Check for Git format folder for Variable Library
                elif artifact_type == "VariableLibrary" and parts[2].endswith(".VariableLibrary"):
                    artifact_name = parts[2][:-16]  # Remove .VariableLibrary
                
                # Check for simple JSON file
                elif parts[2].endswith('.json'):
                    artifact_name = parts[2][:-5]  # Remove .json extension
                
                # Check for notebook file
                elif parts[2].endswith('.ipynb'):
                    artifact_name = parts[2][:-6]  # Remove .ipynb extension
                
                # Check for folder-based artifact (legacy format)
                else:
                    artifact_name = parts[2]
            
            if artifact_name:
                if artifact_type not in artifacts_by_type:
                    artifacts_by_type[artifact_type] = set()
                artifacts_by_type[artifact_type].add(artifact_name)
                logger.debug(f"Detected change: {artifact_type} - {artifact_name}")
        
        return artifacts_by_type
    
    def has_config_changes(self, changed_files: List[str]) -> bool:
        """
        Check if configuration files have changed
        
        Args:
            changed_files: List of changed file paths
            
        Returns:
            True if config files changed, False otherwise
        """
        config_files = [
            f"config/{self.environment}.json",
            "config/common.json"
        ]
        
        for file_path in changed_files:
            if any(file_path == cf or file_path.endswith(cf) for cf in config_files):
                logger.info(f"Configuration file changed: {file_path}")
                return True
        
        return False
    
    def get_changed_artifacts(self, force_all: bool = False) -> Optional[Dict[str, Set[str]]]:
        """
        Get artifacts that have changed since last deployment
        
        Args:
            force_all: If True, return None (deploy all artifacts)
            
        Returns:
            Dictionary of changed artifacts by type, or None if should deploy all
        """
        if force_all:
            logger.info("Force deployment requested, skipping change detection")
            return None
        
        # Check if Git is available
        if not self.is_git_available():
            logger.warning("Git not available, deploying all artifacts")
            return None
        
        # Get last deployment commit
        last_commit = self.get_last_deployment_commit()
        
        if not last_commit:
            logger.info("First deployment detected, deploying all artifacts")
            return None
        
        # Get current commit
        current_commit = self.get_current_commit()
        
        if not current_commit:
            logger.warning("Cannot determine current commit, deploying all artifacts")
            return None
        
        # Check if commits are the same
        if last_commit == current_commit:
            logger.info(f"No changes since last deployment ({last_commit[:8]})")
            return {}  # Empty dict means no changes
        
        # Get changed files
        changed_files = self.get_changed_files(last_commit)
        
        if not changed_files:
            logger.info("No file changes detected")
            return {}
        
        # Check for config changes - if config changed, deploy all
        if self.has_config_changes(changed_files):
            logger.info("Configuration files changed, deploying all artifacts")
            return None
        
        # Extract artifact names from changed files
        changed_artifacts = self.extract_artifact_names(changed_files)
        
        # Log summary
        total_artifacts = sum(len(names) for names in changed_artifacts.values())
        logger.info(f"Change detection: {total_artifacts} artifact(s) changed")
        
        for artifact_type, names in changed_artifacts.items():
            logger.info(f"  {artifact_type}: {', '.join(sorted(names))}")
        
        return changed_artifacts
    
    def get_dependent_artifacts(
        self,
        changed_artifacts: Dict[str, Set[str]],
        all_discovered: Dict[str, Set[str]]
    ) -> Dict[str, Set[str]]:
        """
        Get artifacts that depend on changed artifacts
        
        Args:
            changed_artifacts: Dictionary of changed artifacts by type
            all_discovered: Dictionary of all discovered artifacts by type
            
        Returns:
            Dictionary of dependent artifacts to include in deployment
        """
        dependent = {}
        
        # If lakehouse changed, include its SQL views
        if "Lakehouse" in changed_artifacts and "SqlView" in all_discovered:
            changed_lakehouses = changed_artifacts["Lakehouse"]
            
            # We need to map views to their lakehouses
            # For now, include all views if any lakehouse changed
            # TODO: More precise mapping based on view metadata
            if changed_lakehouses:
                dependent["SqlView"] = all_discovered["SqlView"].copy()
                logger.info(f"Including {len(dependent['SqlView'])} SQL view(s) due to lakehouse changes")
        
        return dependent
