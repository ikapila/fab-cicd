"""
Main Deployment Orchestrator for Microsoft Fabric Artifacts
Coordinates the deployment of artifacts to target environments
"""

import os
import sys
import json
import base64
import argparse
import logging
from typing import List, Dict, Optional
from pathlib import Path

from fabric_auth import FabricAuthenticator
from fabric_client import FabricClient
from config_manager import ConfigManager
from dependency_resolver import DependencyResolver, ArtifactType
from change_detector import ChangeDetector

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FabricDeployer:
    """Orchestrates deployment of Fabric artifacts"""
    
    def __init__(
        self,
        environment: str,
        config_dir: str = "config",
        artifacts_dir: str = "."
    ):
        """
        Initialize deployer
        
        Args:
            environment: Target environment (dev, uat, prod)
            config_dir: Directory containing configuration files
            artifacts_dir: Root directory containing artifact definitions
        """
        self.environment = environment
        self.config_dir = config_dir
        self.artifacts_dir = Path(artifacts_dir)
        
        # Initialize components
        logger.info(f"Initializing deployment to {environment} environment")
        self.config = ConfigManager(environment, config_dir)
        
        # Initialize authenticator with environment-specific service principal
        sp_config = self.config.get_service_principal_config()
        if sp_config:
            logger.info(f"Using environment-specific service principal for {environment}")
            self.auth = FabricAuthenticator(
                client_id=sp_config.get("client_id"),
                tenant_id=sp_config.get("tenant_id"),
                secret_env_var=sp_config.get("secret_env_var")
            )
        else:
            logger.info("Using default service principal configuration")
            self.auth = FabricAuthenticator()
        
        self.client = FabricClient(self.auth)
        self.resolver = DependencyResolver()
        
        # Get artifacts root folder from config
        self.artifacts_root_folder = self.config.get_artifacts_root_folder()
        logger.info(f"Using artifacts root folder: {self.artifacts_root_folder}")
        
        # Validate authentication
        if not self.auth.validate_authentication():
            raise RuntimeError("Authentication validation failed")
        
        self.workspace_id = self.config.get_workspace_id()
        logger.info(f"Target workspace: {self.config.get_workspace_name()} ({self.workspace_id})")
        
        # Cache for workspace folder IDs
        self._folder_cache = {}
        
        # Track artifacts created in this run to avoid immediate update attempts
        self._created_in_this_run = set()
        
        # Build set of config-managed artifact names (config is source of truth for these)
        self._config_managed_artifacts = self._get_config_managed_artifacts()
        
        # Initialize change detector
        self.change_detector = ChangeDetector(
            environment=environment,
            artifacts_dir=self.artifacts_dir,
            repo_root=self.artifacts_dir
        )
    
    def _get_config_managed_artifacts(self) -> dict:
        """
        Get set of artifact names that are managed by config file.
        These artifacts should NOT be deployed from wsartifacts folders.
        Config is the source of truth for these artifacts.
        
        Returns:
            Dictionary with artifact type as key and set of names as values
        """
        config_managed = {
            'notebooks': set(),
            'spark_job_definitions': set(),
            'lakehouses': set(),
            'environments': set()
        }
        
        artifacts_config = self.config.get_artifacts_to_create()
        if not artifacts_config:
            return config_managed
        
        # Collect notebook names from config
        for notebook_def in artifacts_config.get("notebooks", []):
            name = notebook_def.get("name")
            if name:
                config_managed['notebooks'].add(name)
        
        # Collect spark job names from config
        for job_def in artifacts_config.get("spark_job_definitions", []):
            name = job_def.get("name")
            if name:
                config_managed['spark_job_definitions'].add(name)
        
        # Collect lakehouse names from config
        for lh_def in artifacts_config.get("lakehouses", []):
            name = lh_def.get("name")
            if name:
                config_managed['lakehouses'].add(name)
        
        # Collect environment names from config
        for env_def in artifacts_config.get("environments", []):
            name = env_def.get("name")
            if name:
                config_managed['environments'].add(name)
        
        # Log what's being managed by config
        total_managed = sum(len(names) for names in config_managed.values())
        if total_managed > 0:
            logger.info(f"Config-managed artifacts (will not be deployed from wsartifacts folders):")
            for artifact_type, names in config_managed.items():
                if names:
                    logger.info(f"  {artifact_type}: {', '.join(sorted(names))}")
        
        return config_managed
    
    def _get_or_create_folder(self, folder_name: str) -> str:
        """
        Get or create a workspace folder and cache the ID
        
        Args:
            folder_name: Name of the folder
            
        Returns:
            Folder ID (GUID)
        """
        if folder_name not in self._folder_cache:
            self._folder_cache[folder_name] = self.client.get_or_create_workspace_folder(
                self.workspace_id, 
                folder_name
            )
        return self._folder_cache[folder_name]
    
    def _apply_change_detection(self) -> None:
        """
        Apply change detection to filter artifacts
        Only artifacts that have changed will be deployed
        """
        logger.info("\n" + "="*60)
        logger.info("CHANGE DETECTION")
        logger.info("="*60)
        
        # Get changed artifacts
        changed_artifacts = self.change_detector.get_changed_artifacts(force_all=False)
        
        if changed_artifacts is None:
            # Deploy all (first deployment, config changed, or git not available)
            logger.info("Deploying all discovered artifacts")
            return
        
        if not changed_artifacts:
            # No changes detected
            logger.info("No changes detected since last deployment")
            logger.info("Skipping deployment (use --force-all to override)")
            self.resolver.artifacts = []
            return
        
        # Get all discovered artifacts organized by type
        all_discovered = {}
        for artifact in self.resolver.artifacts:
            artifact_type = artifact["type"].value
            if artifact_type not in all_discovered:
                all_discovered[artifact_type] = set()
            all_discovered[artifact_type].add(artifact["name"])
        
        # Add dependent artifacts (e.g., SQL views when lakehouse changes)
        dependent_artifacts = self.change_detector.get_dependent_artifacts(
            changed_artifacts,
            all_discovered
        )
        
        # Merge changed and dependent artifacts
        for artifact_type, names in dependent_artifacts.items():
            if artifact_type in changed_artifacts:
                changed_artifacts[artifact_type].update(names)
            else:
                changed_artifacts[artifact_type] = names
        
        # Filter artifacts to only include changed ones
        filtered_artifacts = []
        skipped_count = 0
        
        for artifact in self.resolver.artifacts:
            artifact_type = artifact["type"].value
            artifact_name = artifact["name"]
            
            if artifact_type in changed_artifacts and artifact_name in changed_artifacts[artifact_type]:
                filtered_artifacts.append(artifact)
            else:
                skipped_count += 1
        
        # Update resolver with filtered artifacts
        self.resolver.artifacts = filtered_artifacts
        
        # Log summary
        total_changed = sum(len(names) for names in changed_artifacts.values())
        logger.info(f"Changed artifacts: {total_changed}")
        for artifact_type, names in sorted(changed_artifacts.items()):
            logger.info(f"  {artifact_type}: {', '.join(sorted(names))}")
        logger.info(f"Skipped (unchanged): {skipped_count}")
        logger.info("="*60)
    
    def _filter_specific_artifacts(self, specific_artifacts: List[str]) -> None:
        """
        Filter to only deploy specific named artifacts
        
        Args:
            specific_artifacts: List of artifact names to deploy
        """
        logger.info("\n" + "="*60)
        logger.info("SPECIFIC ARTIFACT DEPLOYMENT")
        logger.info("="*60)
        logger.info(f"Requested artifacts: {', '.join(specific_artifacts)}")
        
        specific_set = set(specific_artifacts)
        filtered_artifacts = []
        
        for artifact in self.resolver.artifacts:
            if artifact["name"] in specific_set:
                filtered_artifacts.append(artifact)
        
        # Check if all requested artifacts were found
        found_names = {a["name"] for a in filtered_artifacts}
        missing = specific_set - found_names
        
        if missing:
            logger.warning(f"Requested artifacts not found: {', '.join(missing)}")
        
        # Update resolver with filtered artifacts
        self.resolver.artifacts = filtered_artifacts
        
        logger.info(f"Found {len(filtered_artifacts)} artifact(s) to deploy")
        logger.info("="*60)
    
    def _save_deployment_state(self) -> None:
        """
        Save the current deployment state (commit hash)
        """
        current_commit = self.change_detector.get_current_commit()
        if current_commit:
            self.change_detector.save_deployment_commit(current_commit)
            logger.info(f"Saved deployment state: {current_commit[:8]}")
        else:
            logger.warning("Could not save deployment state (Git not available)")
    
    def discover_artifacts(self, force_all: bool = False, specific_artifacts: List[str] = None) -> None:
        """
        Discover artifacts from file system and config file, then build dependency graph
        
        Args:
            force_all: If True, skip change detection and deploy all artifacts
            specific_artifacts: List of specific artifact names to deploy (overrides change detection)
        """
        logger.info("="*60)
        logger.info("ARTIFACT DISCOVERY PHASE")
        logger.info("="*60)
        logger.info("Discovering artifacts from file system...")
        
        # Discover lakehouses
        self._discover_lakehouses()
        
        # Discover environments
        self._discover_environments()
        
        # Discover notebooks
        self._discover_notebooks()
        
        # Discover Spark job definitions
        self._discover_spark_jobs()
        
        # Discover data pipelines
        self._discover_pipelines()
        
        # Discover variable libraries
        self._discover_variable_libraries()
        
        # Discover SQL views
        self._discover_sql_views()
        
        logger.info("="*60)
        logger.info(f"DISCOVERY COMPLETE: Found {len(self.resolver.artifacts)} total artifacts")
        logger.info("="*60)
        
        # Apply change detection if enabled
        if not force_all and not specific_artifacts:
            self._apply_change_detection()
        elif specific_artifacts:
            self._filter_specific_artifacts(specific_artifacts)
    
    def _discover_lakehouses(self) -> None:
        """Discover lakehouse definitions"""
        lakehouse_dir = self.artifacts_dir / self.artifacts_root_folder / "Lakehouses"
        if not lakehouse_dir.exists():
            logger.debug("No lakehouses directory found")
            return
        
        discovered = []
        
        # Discover JSON files (simple format)
        for lakehouse_file in lakehouse_dir.glob("*.json"):
            with open(lakehouse_file, 'r') as f:
                definition = json.load(f)
            
            lakehouse_name = definition.get("name", lakehouse_file.stem)
            
            # Always discover - will check config-managed status during deployment
            discovered.append(lakehouse_name)
            lakehouse_id = definition.get("id", f"lakehouse-{lakehouse_name}")
            
            self.resolver.add_artifact(
                lakehouse_id,
                ArtifactType.LAKEHOUSE,
                lakehouse_name,
                dependencies=[]
            )
            
            logger.debug(f"Discovered lakehouse (JSON): {lakehouse_name}")
        
        # Discover Fabric Git format folders
        for item in lakehouse_dir.iterdir():
            if not item.is_dir():
                continue
            
            # Determine lakehouse name from folder name
            # Official format: {name}.Lakehouse or legacy: {name}
            folder_name = item.name
            if folder_name.endswith('.Lakehouse'):
                base_name = folder_name[:-10]  # Remove .Lakehouse suffix
                format_type = "Git v2"
            else:
                base_name = folder_name
                format_type = "Git v1/legacy"
            
            # Check for .platform file (Version 2 - official format)
            platform_file = item / ".platform"
            metadata_file = item / "item.metadata.json"
            
            if platform_file.exists():
                with open(platform_file, 'r') as f:
                    platform_data = json.load(f)
                
                lakehouse_name = platform_data["metadata"].get("displayName", base_name)
                lakehouse_id = platform_data["config"].get("logicalId", f"lakehouse-{lakehouse_name}")
                
                # Skip if already discovered from JSON file
                if lakehouse_name in discovered:
                    logger.debug(f"Skipping duplicate lakehouse folder: {lakehouse_name}")
                    continue
                
                discovered.append(lakehouse_name)
                
                self.resolver.add_artifact(
                    lakehouse_id,
                    ArtifactType.LAKEHOUSE,
                    lakehouse_name,
                    dependencies=[]
                )
                
                logger.debug(f"Discovered lakehouse ({format_type}): {lakehouse_name}")
                
            elif metadata_file.exists():
                # Fall back to Version 1 format (item.metadata.json)
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                
                lakehouse_name = metadata.get("displayName", base_name)
                
                # Skip if already discovered from JSON file
                if lakehouse_name in discovered:
                    logger.debug(f"Skipping duplicate lakehouse folder: {lakehouse_name}")
                    continue
                
                discovered.append(lakehouse_name)
                lakehouse_id = metadata.get("id", f"lakehouse-{lakehouse_name}")
                
                self.resolver.add_artifact(
                    lakehouse_id,
                    ArtifactType.LAKEHOUSE,
                    lakehouse_name,
                    dependencies=[]
                )
                
                logger.debug(f"Discovered lakehouse ({format_type}): {lakehouse_name}")
        
        if discovered:
            logger.info(f"Discovered {len(discovered)} lakehouse(s): {', '.join(sorted(discovered))}")
    
    def _discover_environments(self) -> None:
        """Discover environment definitions"""
        env_dir = self.artifacts_dir / self.artifacts_root_folder / "Environments"
        if not env_dir.exists():
            logger.debug("No environments directory found")
            return
        
        discovered = []
        for env_file in env_dir.glob("*.json"):
            with open(env_file, 'r') as f:
                definition = json.load(f)
            
            env_name = definition.get("name", env_file.stem)
            
            # Always discover - will check config-managed status during deployment
            discovered.append(env_name)
            env_id = definition.get("id", f"environment-{env_name}")
            
            self.resolver.add_artifact(
                env_id,
                ArtifactType.ENVIRONMENT,
                env_name,
                dependencies=[]
            )
            
            logger.debug(f"Discovered environment: {env_name}")
        
        if discovered:
            logger.info(f"Discovered {len(discovered)} environment(s): {', '.join(sorted(discovered))}")
    
    def _discover_notebooks(self) -> None:
        """Discover notebook definitions (both .ipynb files and Fabric Git folder format)"""
        notebook_dir = self.artifacts_dir / self.artifacts_root_folder / "Notebooks"
        if not notebook_dir.exists():
            logger.debug("No notebooks directory found")
            return
        
        logger.debug(f"Scanning for notebooks in: {notebook_dir}")
        discovered_notebooks = set()
        
        # Discover .ipynb files (legacy format)
        ipynb_files = list(notebook_dir.glob("*.ipynb"))
        logger.debug(f"Found {len(ipynb_files)} .ipynb files")
        
        for notebook_file in ipynb_files:
            try:
                notebook_name = notebook_file.stem
                
                # Always discover - will check config-managed status during deployment
                discovered_notebooks.add(notebook_name)
                notebook_id = f"notebook-{notebook_name}"
                
                # Try to read metadata for dependencies
                dependencies = self._extract_notebook_dependencies(notebook_file)
                
                self.resolver.add_artifact(
                    notebook_id,
                    ArtifactType.NOTEBOOK,
                    notebook_name,
                    dependencies=dependencies
                )
                
                logger.debug(f"Discovered notebook (ipynb): {notebook_name}")
            except Exception as e:
                logger.error(f"Failed to discover notebook {notebook_file.name}: {e}")
                import traceback
                logger.debug(traceback.format_exc())
        
        # Discover Fabric Git format (folders with .platform and notebook-content.py)
        fabric_folders = [item for item in notebook_dir.iterdir() if item.is_dir()]
        logger.debug(f"Found {len(fabric_folders)} folders to check for Fabric format")
        
        for item in fabric_folders:
            if item.is_dir():
                platform_file = item / ".platform"
                content_file = item / "notebook-content.py"
                
                # Check if it's a valid Fabric notebook folder
                if platform_file.exists() and content_file.exists():
                    try:
                        # Read displayName from .platform file
                        try:
                            with open(platform_file, 'r') as f:
                                platform_data = json.load(f)
                            notebook_name = platform_data.get("metadata", {}).get("displayName", item.name)
                        except Exception as e:
                            logger.warning(f"Could not read displayName from {platform_file}, using folder name: {e}")
                            notebook_name = item.name
                        
                        # Skip if already discovered as .ipynb
                        if notebook_name in discovered_notebooks:
                            logger.debug(f"Skipping duplicate notebook (already found as .ipynb): {notebook_name}")
                            continue
                        
                        # Always discover - will check config-managed status during deployment
                        discovered_notebooks.add(notebook_name)
                        notebook_id = f"notebook-{notebook_name}"
                        
                        # Try to read metadata for dependencies from .platform
                        dependencies = self._extract_notebook_dependencies_from_fabric_format(item)
                        
                        self.resolver.add_artifact(
                            notebook_id,
                            ArtifactType.NOTEBOOK,
                            notebook_name,
                            dependencies=dependencies
                        )
                        
                        logger.debug(f"Discovered notebook (Fabric): {notebook_name}")
                    except Exception as e:
                        logger.error(f"Failed to discover Fabric notebook {item.name}: {e}")
                        import traceback
                        logger.debug(traceback.format_exc())
        
        if discovered_notebooks:
            logger.info(f"Discovered {len(discovered_notebooks)} notebook(s): {', '.join(sorted(discovered_notebooks))}")
    
    def _discover_spark_jobs(self) -> None:
        """Discover Spark job definitions"""
        job_dir = self.artifacts_dir / self.artifacts_root_folder / "Sparkjobdefinitions"
        if not job_dir.exists():
            logger.debug("No Spark job definitions directory found")
            return
        
        discovered = []
        for job_file in job_dir.glob("*.json"):
            with open(job_file, 'r') as f:
                definition = json.load(f)
            
            job_name = definition.get("name", job_file.stem)
            
            # Always discover - will check config-managed status during deployment
            discovered.append(job_name)
            job_id = definition.get("id", f"sparkjob-{job_name}")
            dependencies = definition.get("dependencies", [])
            
            self.resolver.add_artifact(
                job_id,
                ArtifactType.SPARK_JOB_DEFINITION,
                job_name,
                dependencies=dependencies
            )
            
            logger.debug(f"Discovered Spark job: {job_name}")
        
        if discovered:
            logger.info(f"Discovered {len(discovered)} Spark job(s): {', '.join(sorted(discovered))}")
    
    def _discover_pipelines(self) -> None:
        """Discover data pipeline definitions"""
        pipeline_dir = self.artifacts_dir / self.artifacts_root_folder / "Datapipelines"
        if not pipeline_dir.exists():
            logger.debug("No data pipelines directory found")
            return
        
        for pipeline_file in pipeline_dir.glob("*.json"):
            with open(pipeline_file, 'r') as f:
                definition = json.load(f)
            
            pipeline_name = definition.get("name", pipeline_file.stem)
            pipeline_id = definition.get("id", f"pipeline-{pipeline_name}")
            dependencies = definition.get("dependencies", [])
            
            self.resolver.add_artifact(
                pipeline_id,
                ArtifactType.DATA_PIPELINE,
                pipeline_name,
                dependencies=dependencies
            )
            
            logger.debug(f"Discovered pipeline: {pipeline_name}")
    
    def _discover_variable_libraries(self) -> None:
        """Discover Variable Library definitions"""
        library_dir = self.artifacts_dir / self.artifacts_root_folder / "Variablelibraries"
        if not library_dir.exists():
            logger.debug("No variable libraries directory found")
            return
        
        discovered = []
        
        # Discover JSON files (simple format)
        for library_file in library_dir.glob("*.json"):
            with open(library_file, 'r') as f:
                definition = json.load(f)
            
            library_name = definition.get("name", library_file.stem)
            library_id = definition.get("id", f"varlib-{library_name}")
            dependencies = definition.get("dependencies", [])
            
            discovered.append(library_name)
            
            self.resolver.add_artifact(
                library_id,
                ArtifactType.VARIABLE_LIBRARY,
                library_name,
                dependencies=dependencies
            )
            
            logger.debug(f"Discovered Variable Library (JSON): {library_name}")
        
        # Discover Fabric Git format folders (custom format for variable libraries)
        for item in library_dir.iterdir():
            if not item.is_dir():
                continue
            
            # Determine library name from folder name
            folder_name = item.name
            if folder_name.endswith('.VariableLibrary'):
                base_name = folder_name[:-16]  # Remove .VariableLibrary suffix
                format_type = "Git v2"
            else:
                base_name = folder_name
                format_type = "Git v1/custom"
            
            # Check for .platform file, valueSets folder, or item.metadata.json
            platform_file = item / ".platform"
            value_sets_dir = item / "valueSets"
            metadata_file = item / "item.metadata.json"
            
            # Get name from .platform file if available
            if platform_file.exists():
                with open(platform_file, 'r') as f:
                    platform_data = json.load(f)
                library_name = platform_data["metadata"].get("displayName", base_name)
            elif metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                library_name = metadata.get("displayName", base_name)
            elif value_sets_dir.exists():
                # valueSets folder exists - assume it's a custom format library
                library_name = base_name
            else:
                # No recognizable files, skip
                continue
            
            # Skip if already discovered from JSON file
            if library_name in discovered:
                logger.debug(f"Skipping duplicate variable library folder: {library_name}")
                continue
            
            discovered.append(library_name)
            library_id = f"varlib-{library_name}"
            
            self.resolver.add_artifact(
                library_id,
                ArtifactType.VARIABLE_LIBRARY,
                library_name,
                dependencies=[]
            )
            
            logger.debug(f"Discovered Variable Library ({format_type}): {library_name}")
        
        if discovered:
            logger.info(f"Discovered {len(discovered)} Variable Librar{'y' if len(discovered) == 1 else 'ies'}: {', '.join(sorted(discovered))}")
    
    def _discover_sql_views(self) -> None:
        """Discover SQL view definitions from {artifacts_root_folder}/Views/{lakehouse}/ directories"""
        views_dir = self.artifacts_dir / self.artifacts_root_folder / "Views"
        if not views_dir.exists():
            logger.debug("No views directory found")
            return
        
        # Iterate through each lakehouse subdirectory
        for lakehouse_dir in views_dir.iterdir():
            if not lakehouse_dir.is_dir():
                continue
            
            lakehouse_name = lakehouse_dir.name
            logger.debug(f"Discovering views for lakehouse: {lakehouse_name}")
            
            # Read metadata.json for dependencies
            metadata_file = lakehouse_dir / "metadata.json"
            dependencies_map = {}
            
            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                        dependencies_map = metadata.get("dependencies", {})
                except Exception as e:
                    logger.warning(f"Could not read metadata from {metadata_file}: {str(e)}")
            
            # Discover all .sql files
            for view_file in lakehouse_dir.glob("*.sql"):
                view_name = view_file.stem
                view_id = f"view-{lakehouse_name}-{view_name}"
                
                # Get dependencies for this view from metadata
                view_dependencies_info = dependencies_map.get(view_name, {})
                artifact_dependencies = []
                
                # Add lakehouse dependency (views depend on their lakehouse)
                lakehouse_id = f"lakehouse-{lakehouse_name}"
                artifact_dependencies.append(lakehouse_id)
                
                # Add table dependencies
                table_deps = view_dependencies_info.get("tables", [])
                for table_ref in table_deps:
                    # Table references are just strings like "dbo.FactSales"
                    # We don't track table artifacts separately, just ensure lakehouse exists
                    pass
                
                # Add view-to-view dependencies
                view_deps = view_dependencies_info.get("views", [])
                for dep_view_ref in view_deps:
                    # Parse schema.viewname format
                    parts = dep_view_ref.split(".")
                    if len(parts) == 2:
                        dep_schema, dep_name = parts
                    else:
                        dep_name = dep_view_ref
                    
                    # Create dependency on the other view
                    dep_view_id = f"view-{lakehouse_name}-{dep_name}"
                    artifact_dependencies.append(dep_view_id)
                
                # Register with resolver
                self.resolver.add_artifact(
                    view_id,
                    ArtifactType.SQL_VIEW,
                    view_name,
                    dependencies=artifact_dependencies
                )
                
                logger.debug(f"Discovered SQL view: {view_name} with {len(artifact_dependencies)} dependencies")
    
    def _extract_notebook_dependencies(self, notebook_path: Path) -> List[str]:
        """
        Extract dependencies from notebook metadata (.ipynb format)
        
        Args:
            notebook_path: Path to notebook file
            
        Returns:
            List of dependency IDs
        """
        try:
            with open(notebook_path, 'r') as f:
                notebook = json.load(f)
            
            metadata = notebook.get("metadata", {})
            dependencies = metadata.get("dependencies", [])
            return dependencies
        except Exception as e:
            logger.warning(f"Could not extract dependencies from {notebook_path}: {str(e)}")
            return []
    
    def _extract_notebook_dependencies_from_fabric_format(self, notebook_folder: Path) -> List[str]:
        """
        Extract dependencies from Fabric Git format notebook (.platform file)
        
        Args:
            notebook_folder: Path to notebook folder containing .platform
            
        Returns:
            List of dependency IDs
        """
        try:
            platform_file = notebook_folder / ".platform"
            with open(platform_file, 'r') as f:
                platform_data = json.load(f)
            
            # Extract dependencies from platform metadata
            metadata = platform_data.get("metadata", {})
            dependencies = metadata.get("dependencies", [])
            return dependencies
        except Exception as e:
            logger.warning(f"Could not extract dependencies from {notebook_folder}: {str(e)}")
            return []
    
    def create_artifacts_from_config(self, dry_run: bool = False) -> bool:
        """
        Create artifacts defined in configuration file
        These artifacts will be owned by the service principal
        
        Args:
            dry_run: If True, only simulate creation without making changes
            
        Returns:
            True if creation successful, False otherwise
        """
        logger.info("="*60)
        logger.info(f"Creating artifacts from configuration for {self.environment}")
        if dry_run:
            logger.info("DRY RUN MODE - No changes will be made")
        logger.info("="*60)
        
        artifacts_config = self.config.get_artifacts_to_create()
        
        if not artifacts_config:
            logger.info("No artifacts configured for creation")
            return True
        
        success = True
        
        # Create lakehouses
        for lakehouse_def in artifacts_config.get("lakehouses", []):
            try:
                name = lakehouse_def["name"]
                description = lakehouse_def.get("description", "")
                create_if_not_exists = lakehouse_def.get("create_if_not_exists", True)
                
                logger.info(f"\nProcessing lakehouse: {name}")
                
                if not dry_run:
                    existing = self.client.list_lakehouses(self.workspace_id)
                    existing_lakehouse = next((lh for lh in existing if lh["displayName"] == name), None)
                    
                    if existing_lakehouse:
                        logger.info(f"  ✓ Lakehouse '{name}' already exists (ID: {existing_lakehouse['id']})")
                        
                        # Check if description changed and update if needed
                        existing_desc = existing_lakehouse.get("description", "")
                        if existing_desc != description:
                            logger.info(f"  Updating description for lakehouse '{name}'")
                            try:
                                self.client.update_lakehouse(self.workspace_id, existing_lakehouse['id'], description)
                                logger.info(f"  ✓ Updated lakehouse description")
                            except Exception as e:
                                logger.warning(f"  ⚠ Could not update description: {str(e)}")
                        
                        # Don't skip deployment - wsartifacts may have additional config
                        # self._created_in_this_run.add(('lakehouse', name))
                    elif create_if_not_exists:
                        # Get or create folder for lakehouses
                        folder_id = self._get_or_create_folder("Lakehouses")
                        
                        # Get enableSchemas setting - check both simple and native formats
                        enable_schemas = lakehouse_def.get("enable_schemas")
                        if enable_schemas is None and "creationPayload" in lakehouse_def:
                            enable_schemas = lakehouse_def["creationPayload"].get("enableSchemas")
                        
                        if enable_schemas is not None:
                            logger.info(f"  Creating lakehouse with enableSchemas: {enable_schemas}")
                        
                        result = self.client.create_lakehouse(
                            self.workspace_id, 
                            name, 
                            description, 
                            folder_id=folder_id, 
                            enable_schemas=enable_schemas
                        )
                        logger.info(f"  ✓ Created lakehouse '{name}' in 'Lakehouses' folder (ID: {result['id']})")
                        # Track as created to skip deployment
                        self._created_in_this_run.add(('lakehouse', name))
                        # Save to local file
                        lakehouse_definition = {
                            "name": name,
                            "id": result['id'],
                            "description": description
                        }
                        self._save_artifact_to_file("Lakehouses", name, lakehouse_definition)
                    else:
                        logger.warning(f"  ⚠ Lakehouse '{name}' does not exist and create_if_not_exists is false")
                else:
                    logger.info(f"  [DRY RUN] Would create lakehouse: {name}")
                    
            except Exception as e:
                logger.error(f"  ✗ Failed to create lakehouse '{name}': {str(e)}")
                success = False
        
        # Create environments
        for env_def in artifacts_config.get("environments", []):
            try:
                name = env_def["name"]
                description = env_def.get("description", "")
                create_if_not_exists = env_def.get("create_if_not_exists", True)
                
                logger.info(f"\nProcessing environment: {name}")
                
                if not dry_run:
                    existing = self.client.list_environments(self.workspace_id)
                    existing_env = next((env for env in existing if env["displayName"] == name), None)
                    
                    if existing_env:
                        logger.info(f"  ✓ Environment '{name}' already exists (ID: {existing_env['id']})")
                        
                        # Check if description changed and update if needed
                        existing_desc = existing_env.get("description", "")
                        if existing_desc != description:
                            logger.info(f"  Updating description for environment '{name}'")
                            try:
                                self.client.update_environment(self.workspace_id, existing_env['id'], description)
                                logger.info(f"  ✓ Updated environment description")
                            except Exception as e:
                                logger.warning(f"  ⚠ Could not update description: {str(e)}")
                        
                        # Don't skip deployment - wsartifacts may have additional config
                        # self._created_in_this_run.add(('environment', name))
                    elif create_if_not_exists:
                        # Get or create folder for environments
                        folder_id = self._get_or_create_folder("Environments")
                        
                        result = self.client.create_environment(self.workspace_id, name, description, folder_id=folder_id)
                        logger.info(f"  ✓ Created environment '{name}' in 'Environments' folder (ID: {result['id']})")
                        # Track as created to skip deployment
                        self._created_in_this_run.add(('environment', name))
                        # Save to local file
                        env_definition = {
                            "name": name,
                            "id": result['id'],
                            "description": description
                        }
                        if env_def.get("libraries"):
                            env_definition["libraries"] = env_def["libraries"]
                        self._save_artifact_to_file("Environments", name, env_definition)
                        # Note: Library installation would require additional API calls
                        if env_def.get("libraries"):
                            logger.info(f"  ℹ Libraries defined: {len(env_def['libraries'])} (install separately)")
                    else:
                        logger.warning(f"  ⚠ Environment '{name}' does not exist and create_if_not_exists is false")
                else:
                    logger.info(f"  [DRY RUN] Would create environment: {name}")
                    if env_def.get("libraries"):
                        logger.info(f"    with {len(env_def['libraries'])} libraries")
                    
            except Exception as e:
                logger.error(f"  ✗ Failed to create environment '{name}': {str(e)}")
                success = False
        
        # Create KQL databases
        for kql_def in artifacts_config.get("kql_databases", []):
            try:
                name = kql_def["name"]
                description = kql_def.get("description", "")
                create_if_not_exists = kql_def.get("create_if_not_exists", True)
                
                logger.info(f"\nProcessing KQL database: {name}")
                
                if not dry_run:
                    # Note: KQL database creation requires specific API endpoint
                    logger.info(f"  ℹ KQL database creation: {name}")
                    logger.info(f"    (requires KQL-specific API endpoint - implement as needed)")
                else:
                    logger.info(f"  [DRY RUN] Would create KQL database: {name}")
                    
            except Exception as e:
                logger.error(f"  ✗ Failed to create KQL database '{name}': {str(e)}")
                success = False
        
        # Create notebooks
        for notebook_def in artifacts_config.get("notebooks", []):
            name = None
            try:
                name = notebook_def["name"]
                description = notebook_def.get("description", "")
                create_if_not_exists = notebook_def.get("create_if_not_exists", True)
                template = notebook_def.get("template", "basic_spark")
                
                logger.info(f"\nProcessing notebook: {name}")
                logger.info(f"  Template: {template}")
                logger.info(f"  Description: {description}")
                
                if not dry_run:
                    # Check if notebook already exists
                    logger.info(f"  Checking if notebook '{name}' exists...")
                    existing = self.client.list_notebooks(self.workspace_id)
                    existing_notebook = next((nb for nb in existing if nb["displayName"] == name), None)
                    
                    if existing_notebook:
                        logger.info(f"  ✓ Notebook '{name}' already exists (ID: {existing_notebook['id']})")
                        
                        # Check if we should update the notebook
                        if notebook_def.get("update_if_exists", False):
                            logger.info(f"  Updating notebook '{name}'...")
                            try:
                                notebook_definition = self._create_notebook_template(name, description, template, notebook_def)
                                self.client.update_notebook_definition(
                                    self.workspace_id,
                                    existing_notebook['id'],
                                    notebook_definition
                                )
                                logger.info(f"  ✓ Updated notebook '{name}'")
                            except Exception as e:
                                logger.warning(f"  ⚠ Could not update notebook: {str(e)}")
                    elif create_if_not_exists:
                        try:
                            # Get or create folder for notebooks
                            logger.info(f"  Getting/creating 'Notebooks' folder...")
                            folder_id = self._get_or_create_folder("Notebooks")
                            logger.info(f"  Folder ID: {folder_id}")
                            
                            # Create basic notebook structure in Fabric Git format
                            logger.info(f"  Creating notebook definition from template '{template}'...")
                            notebook_definition = self._create_notebook_template(name, description, template, notebook_def)
                            
                            # Validate definition
                            if not notebook_definition:
                                raise ValueError("Notebook definition is empty")
                            if "parts" not in notebook_definition:
                                raise ValueError("Notebook definition missing 'parts'")
                            if not notebook_definition["parts"]:
                                raise ValueError("Notebook definition has empty 'parts' array")
                            
                            logger.info(f"  Definition created successfully with {len(notebook_definition['parts'])} part(s)")
                            
                            # Create notebook via API
                            logger.info(f"  Calling Fabric API to create notebook...")
                            result = self.client.create_notebook(
                                self.workspace_id, 
                                name, 
                                notebook_definition, 
                                description, 
                                folder_id=folder_id,
                                wait_for_completion=True  # Wait for LRO to complete
                            )
                            
                            # Result now contains the created notebook details
                            notebook_id = result.get('id') if result else None
                            
                            if notebook_id:
                                logger.info(f"  ✓ Notebook created successfully (ID: {notebook_id})")
                            else:
                                logger.warning(f"  ⚠ Notebook created but no ID returned")
                                logger.debug(f"  API Response: {result}")
                            
                            # Track this notebook as created in this run
                            self._created_in_this_run.add(('notebook', name))
                            
                            # Save to local file in Fabric Git format
                            logger.info(f"  Saving to local file system...")
                            save_data = {
                                "id": notebook_id or "",
                                "displayName": name,
                                "description": description,
                                "definition": notebook_definition
                            }
                            self._save_artifact_to_file("Notebooks", name, save_data, "fabric-notebook")
                            
                        except Exception as create_error:
                            logger.error(f"  ✗ Error during notebook creation:")
                            logger.error(f"     {str(create_error)}")
                            import traceback
                            logger.error(f"     Traceback:\n{traceback.format_exc()}")
                            raise
                    else:
                        logger.warning(f"  ⚠ Notebook '{name}' does not exist and create_if_not_exists is false")
                else:
                    logger.info(f"  [DRY RUN] Would create notebook: {name}")
                    logger.info(f"    Template: {template}")
                    
            except KeyError as ke:
                logger.error(f"  ✗ Missing required field in notebook configuration: {str(ke)}")
                logger.error(f"     Configuration: {notebook_def}")
                success = False
            except Exception as e:
                import traceback
                notebook_name = name if name else "Unknown"
                logger.error(f"  ✗ Failed to create notebook '{notebook_name}'")
                logger.error(f"     Error: {str(e)}")
                logger.error(f"     Type: {type(e).__name__}")
                logger.error(f"     Full traceback:\n{traceback.format_exc()}")
                success = False
        
        # Create Spark job definitions
        for job_def in artifacts_config.get("spark_job_definitions", []):
            try:
                name = job_def["name"]
                description = job_def.get("description", "")
                create_if_not_exists = job_def.get("create_if_not_exists", True)
                
                logger.info(f"\nProcessing Spark job definition: {name}")
                
                if not dry_run:
                    existing = self.client.list_spark_job_definitions(self.workspace_id)
                    existing_job = next((job for job in existing if job["displayName"] == name), None)
                    
                    if existing_job:
                        logger.info(f"  ✓ Spark job '{name}' already exists (ID: {existing_job['id']})")
                        
                        # Check if we should update the spark job
                        if job_def.get("update_if_exists", False):
                            logger.info(f"  Updating Spark job '{name}'...")
                            try:
                                job_definition = self._create_spark_job_template(name, description, job_def)
                                self.client.update_spark_job_definition(
                                    self.workspace_id,
                                    existing_job['id'],
                                    job_definition
                                )
                                logger.info(f"  ✓ Updated Spark job '{name}'")
                            except Exception as e:
                                logger.warning(f"  ⚠ Could not update Spark job: {str(e)}")
                    elif create_if_not_exists:
                        # Get or create folder for Spark jobs
                        folder_id = self._get_or_create_folder("Sparkjobdefinitions")
                        
                        # Create basic Spark job definition
                        job_definition = self._create_spark_job_template(name, description, job_def)
                        result = self.client.create_spark_job_definition(
                            self.workspace_id, 
                            name, 
                            job_definition, 
                            folder_id=folder_id,
                            wait_for_completion=True  # Wait for LRO to complete
                        )
                        
                        job_id = result.get('id') if result else None
                        if job_id:
                            logger.info(f"  ✓ Spark job created successfully (ID: {job_id})")
                        else:
                            logger.warning(f"  ⚠ Spark job created but no ID returned")
                        
                        # Track this Spark job as created in this run
                        self._created_in_this_run.add(('spark_job_definition', name))
                        
                        # Save to local file
                        self._save_artifact_to_file("Sparkjobdefinitions", name, job_definition)
                    else:
                        logger.warning(f"  ⚠ Spark job '{name}' does not exist and create_if_not_exists is false")
                else:
                    logger.info(f"  [DRY RUN] Would create Spark job: {name}")
                    if job_def.get("main_file"):
                        logger.info(f"    Main file: {job_def['main_file']}")
                    
            except Exception as e:
                logger.error(f"  ✗ Failed to create Spark job '{name}': {str(e)}")
                success = False
        
        # Create data pipelines
        for pipeline_def in artifacts_config.get("data_pipelines", []):
            try:
                name = pipeline_def["name"]
                description = pipeline_def.get("description", "")
                create_if_not_exists = pipeline_def.get("create_if_not_exists", True)
                
                logger.info(f"\nProcessing data pipeline: {name}")
                
                if not dry_run:
                    existing = self.client.list_data_pipelines(self.workspace_id)
                    existing_pipeline = next((pl for pl in existing if pl["displayName"] == name), None)
                    
                    if existing_pipeline:
                        logger.info(f"  ✓ Pipeline '{name}' already exists (ID: {existing_pipeline['id']})")
                        
                        # Check if we should update the pipeline
                        if pipeline_def.get("update_if_exists", False):
                            logger.info(f"  Updating pipeline '{name}'...")
                            try:
                                pipeline_definition = self._create_pipeline_template(name, description, pipeline_def)
                                self.client.update_data_pipeline(
                                    self.workspace_id,
                                    existing_pipeline['id'],
                                    pipeline_definition
                                )
                                logger.info(f"  ✓ Updated pipeline '{name}'")
                            except Exception as e:
                                logger.warning(f"  ⚠ Could not update pipeline: {str(e)}")
                    elif create_if_not_exists:
                        # Get or create folder for pipelines
                        folder_id = self._get_or_create_folder("Datapipelines")
                        
                        # Create basic pipeline definition
                        pipeline_definition = self._create_pipeline_template(name, description, pipeline_def)
                        result = self.client.create_data_pipeline(
                            self.workspace_id, 
                            name, 
                            pipeline_definition, 
                            folder_id=folder_id
                        )
                        
                        pipeline_id = result.get('id') if result else None
                        if pipeline_id:
                            logger.info(f"  ✓ Created pipeline '{name}' in 'Datapipelines' folder (ID: {pipeline_id})")
                        else:
                            logger.info(f"  ✓ Created pipeline '{name}' in 'Datapipelines' folder (async operation)")
                        # Save to local file
                        self._save_artifact_to_file("Datapipelines", name, pipeline_definition)
                    else:
                        logger.warning(f"  ⚠ Pipeline '{name}' does not exist and create_if_not_exists is false")
                else:
                    logger.info(f"  [DRY RUN] Would create pipeline: {name}")
                    if pipeline_def.get("activities"):
                        logger.info(f"    Activities: {len(pipeline_def['activities'])}")
                    
            except Exception as e:
                logger.error(f"  ✗ Failed to create pipeline '{name}': {str(e)}")
                success = False
        
        # Create semantic models
        for model_def in artifacts_config.get("semantic_models", []):
            try:
                name = model_def["name"]
                description = model_def.get("description", "")
                create_if_not_exists = model_def.get("create_if_not_exists", True)
                
                logger.info(f"\nProcessing semantic model: {name}")
                
                if not dry_run:
                    existing = self.client.list_semantic_models(self.workspace_id)
                    existing_model = next((m for m in existing if m["displayName"] == name), None)
                    
                    if existing_model:
                        logger.info(f"  ✓ Semantic model '{name}' already exists (ID: {existing_model['id']})")
                    elif create_if_not_exists:
                        model_definition = self._create_semantic_model_template(name, description, model_def)
                        result = self.client.create_semantic_model(self.workspace_id, name, model_definition)
                        logger.info(f"  ✓ Created semantic model '{name}' (ID: {result['id']})")
                        # Save to local file
                        self._save_artifact_to_file("Semanticmodels", name, model_definition)
                    else:
                        logger.warning(f"  ⚠ Semantic model '{name}' does not exist and create_if_not_exists is false")
                else:
                    logger.info(f"  [DRY RUN] Would create semantic model: {name}")
                    
            except Exception as e:
                logger.error(f"  ✗ Failed to create semantic model '{name}': {str(e)}")
                success = False
        
        # Create Power BI reports
        for report_def in artifacts_config.get("reports", []):
            try:
                name = report_def["name"]
                description = report_def.get("description", "")
                create_if_not_exists = report_def.get("create_if_not_exists", True)
                
                logger.info(f"\nProcessing Power BI report: {name}")
                
                if not dry_run:
                    existing = self.client.list_reports(self.workspace_id)
                    existing_report = next((r for r in existing if r["displayName"] == name), None)
                    
                    if existing_report:
                        logger.info(f"  ✓ Report '{name}' already exists (ID: {existing_report['id']})")
                    elif create_if_not_exists:
                        report_definition = self._create_report_template(name, description, report_def)
                        result = self.client.create_report(self.workspace_id, name, report_definition)
                        logger.info(f"  ✓ Created report '{name}' (ID: {result['id']})")
                        # Save to local file
                        self._save_artifact_to_file("Reports", name, report_definition)
                    else:
                        logger.warning(f"  ⚠ Report '{name}' does not exist and create_if_not_exists is false")
                else:
                    logger.info(f"  [DRY RUN] Would create report: {name}")
                    if report_def.get("semantic_model"):
                        logger.info(f"    Semantic model: {report_def['semantic_model']}")
                    
            except Exception as e:
                logger.error(f"  ✗ Failed to create report '{name}': {str(e)}")
                success = False
        
        # Create paginated reports
        for report_def in artifacts_config.get("paginated_reports", []):
            try:
                name = report_def["name"]
                description = report_def.get("description", "")
                create_if_not_exists = report_def.get("create_if_not_exists", True)
                
                logger.info(f"\nProcessing paginated report: {name}")
                
                if not dry_run:
                    existing = self.client.list_paginated_reports(self.workspace_id)
                    existing_report = next((r for r in existing if r["displayName"] == name), None)
                    
                    if existing_report:
                        logger.info(f"  ✓ Paginated report '{name}' already exists (ID: {existing_report['id']})")
                    elif create_if_not_exists:
                        report_definition = self._create_paginated_report_template(name, description, report_def)
                        result = self.client.create_paginated_report(self.workspace_id, name, report_definition)
                        logger.info(f"  ✓ Created paginated report '{name}' (ID: {result['id']})")
                        # Save to local file
                        self._save_artifact_to_file("Paginatedreports", name, report_definition)
                    else:
                        logger.warning(f"  ⚠ Paginated report '{name}' does not exist and create_if_not_exists is false")
                else:
                    logger.info(f"  [DRY RUN] Would create paginated report: {name}")
                    
            except Exception as e:
                logger.error(f"  ✗ Failed to create paginated report '{name}': {str(e)}")
                success = False
        
        # Create variable libraries
        for library_config in artifacts_config.get("variable_libraries", []):
            try:
                name = library_config["name"]
                create_if_not_exists = library_config.get("create_if_not_exists", True)
                
                logger.info(f"\nProcessing Variable Library: {name}")
                
                if not dry_run:
                    existing = self.client.list_variable_libraries(self.workspace_id)
                    existing_library = next((lib for lib in existing if lib["displayName"] == name), None)
                    
                    if existing_library:
                        logger.info(f"  ✓ Variable Library '{name}' already exists (ID: {existing_library['id']})")
                        
                        # Update variables if provided
                        variables = library_config.get("variables", [])
                        if variables:
                            # Wrap variables in proper parts structure
                            variables_json = json.dumps({"variables": variables})
                            variables_base64 = base64.b64encode(variables_json.encode('utf-8')).decode('utf-8')
                            
                            update_payload = {
                                "parts": [
                                    {
                                        "path": "variables.json",
                                        "payload": variables_base64,
                                        "payloadType": "InlineBase64"
                                    }
                                ]
                            }
                            
                            try:
                                self.client.update_variable_library_definition(
                                    self.workspace_id, existing_library["id"], update_payload
                                )
                                logger.info(f"  ✓ Updated {len(variables)} variables in '{name}'")
                            except Exception as e:
                                logger.error(f"  ✗ Failed to update variables: {str(e)}")
                                raise
                    elif create_if_not_exists:
                        # Get or create folder for Variable Libraries
                        folder_id = self._get_or_create_folder("Variablelibraries")
                        
                        library_def = self._create_variable_library_template(library_config)
                        variables = library_def.get("variables", [])
                        
                        # Prepare definition with variables for creation
                        definition = None
                        if variables:
                            variables_json = json.dumps({"variables": variables})
                            variables_base64 = base64.b64encode(variables_json.encode('utf-8')).decode('utf-8')
                            
                            definition = {
                                "format": "VariableLibraryV1",
                                "parts": [
                                    {
                                        "path": "variables.json",
                                        "payload": variables_base64,
                                        "payloadType": "InlineBase64"
                                    }
                                ]
                            }
                        
                        # Create variable library with initial variables
                        result = self.client.create_variable_library(
                            self.workspace_id, 
                            name, 
                            library_def.get("description", ""), 
                            folder_id=folder_id,
                            definition=definition
                        )
                        
                        logger.info(f"  ✓ Created Variable Library '{name}' in 'Variablelibraries' folder with {len(variables)} variables (ID: {result['id']})")
                        
                        # Save to local file
                        library_definition = {
                            "name": name,
                            "id": result["id"],
                            "description": library_def.get("description", ""),
                            "variables": variables
                        }
                        self._save_artifact_to_file("Variablelibraries", name, library_definition)
                    else:
                        logger.warning(f"  ⚠ Variable Library '{name}' does not exist and create_if_not_exists is false")
                else:
                    logger.info(f"  [DRY RUN] Would create Variable Library: {name}")
                    
            except Exception as e:
                logger.error(f"  ✗ Failed to create Variable Library '{name}': {str(e)}")
                success = False
        
        # Create shortcuts
        for shortcut_def in artifacts_config.get("shortcuts", []):
            try:
                name = shortcut_def["name"]
                lakehouse_name = shortcut_def["lakehouse"]
                path = shortcut_def.get("path", "Tables")
                target = shortcut_def["target"]
                create_if_not_exists = shortcut_def.get("create_if_not_exists", True)
                
                logger.info(f"\nProcessing shortcut: {name}")
                
                if not dry_run:
                    # Find lakehouse ID
                    lakehouses = self.client.list_lakehouses(self.workspace_id)
                    lakehouse = next((lh for lh in lakehouses if lh["displayName"] == lakehouse_name), None)
                    
                    if not lakehouse:
                        logger.error(f"  ✗ Lakehouse '{lakehouse_name}' not found")
                        success = False
                        continue
                    
                    lakehouse_id = lakehouse["id"]
                    
                    # Check if shortcut exists
                    try:
                        existing_shortcut = self.client.get_shortcut(
                            self.workspace_id, lakehouse_id, path, name
                        )
                        logger.info(f"  ✓ Shortcut '{name}' already exists in {lakehouse_name}/{path}")
                    except:
                        # Shortcut doesn't exist
                        if create_if_not_exists:
                            result = self.client.create_shortcut(
                                self.workspace_id, lakehouse_id, name, path, target
                            )
                            logger.info(f"  ✓ Created shortcut '{name}' in {lakehouse_name}/{path}")
                        else:
                            logger.warning(f"  ⚠ Shortcut '{name}' does not exist and create_if_not_exists is false")
                else:
                    logger.info(f"  [DRY RUN] Would create shortcut: {name}")
                    logger.info(f"    Lakehouse: {lakehouse_name}")
                    logger.info(f"    Path: {path}")
                    if target.get("oneLake"):
                        logger.info(f"    Type: OneLake shortcut")
                    elif target.get("adlsGen2"):
                        logger.info(f"    Type: ADLS Gen2 shortcut")
                    
            except Exception as e:
                logger.error(f"  ✗ Failed to create shortcut '{name}': {str(e)}")
                success = False
        
        logger.info("\n" + "="*60)
        if success:
            logger.info("✅ All artifacts created successfully")
        else:
            logger.error("❌ Some artifacts failed to create")
        logger.info("="*60)
        
        return success
    
    def _save_artifact_to_file(self, artifact_type: str, name: str, definition: Dict, extension: str = ".json") -> None:
        """
        Save artifact definition to local file in wsartifacts folder structure
        For notebooks, creates Fabric Git folder format (folder with .platform and notebook-content.py)
        
        Args:
            artifact_type: Type of artifact (Lakehouses, Notebooks, etc.) - capitalized
            name: Name of the artifact
            definition: Artifact definition dictionary
            extension: File extension (.json, .ipynb, or 'fabric-notebook' for Fabric format)
        """
        try:
            # Create directory structure
            artifact_dir = self.artifacts_dir / self.artifacts_root_folder / artifact_type
            artifact_dir.mkdir(parents=True, exist_ok=True)
            
            # Handle Fabric Git notebook format specially
            if extension == "fabric-notebook":
                # Create notebook folder
                notebook_folder = artifact_dir / name
                notebook_folder.mkdir(parents=True, exist_ok=True)
                
                # Save .platform file (metadata)
                platform_data = {
                    "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
                    "metadata": {
                        "type": "Notebook",
                        "displayName": name,
                        "description": definition.get("description", "")
                    },
                    "config": {
                        "version": "2.0",
                        "logicalId": definition.get("id", "")
                    }
                }
                
                platform_file = notebook_folder / ".platform"
                with open(platform_file, 'w', encoding='utf-8') as f:
                    json.dump(platform_data, f, indent=2, ensure_ascii=False)
                
                # Extract and save notebook-content.py
                # The definition should have the notebook content in parts
                notebook_content = ""
                if "definition" in definition and "parts" in definition["definition"]:
                    parts = definition["definition"]["parts"]
                    for part in parts:
                        if "notebook-content" in part.get("path", ""):
                            payload = part.get("payload", "")
                            # If base64 encoded, decode it
                            if part.get("payloadType") == "InlineBase64":
                                import base64
                                notebook_content = base64.b64decode(payload).decode('utf-8')
                            else:
                                notebook_content = payload
                            break
                
                # If no content found, create a basic Python notebook
                if not notebook_content:
                    notebook_content = f"# Fabric notebook source\n\n# METADATA ********************\n\n# META {{\n#   \"kernel_info\": {{\n#     \"name\": \"synapse_pyspark\"\n#   }}\n# }}\n\n# MARKDOWN ********************\n\n# # {name}\n# {definition.get('description', '')}\n\n# CELL ********************\n\n# This is a placeholder notebook\nprint('Notebook initialized')"
                
                content_file = notebook_folder / "notebook-content.py"
                with open(content_file, 'w', encoding='utf-8') as f:
                    f.write(notebook_content)
                
                logger.info(f"  📁 Saved to {notebook_folder.relative_to(self.artifacts_dir)}/ (Fabric format)")
            else:
                # Standard file save for other artifact types
                file_path = artifact_dir / f"{name}{extension}"
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(definition, f, indent=2, ensure_ascii=False)
                
                logger.info(f"  📁 Saved to {file_path.relative_to(self.artifacts_dir)}")
        except Exception as e:
            logger.warning(f"  ⚠ Failed to save artifact to file: {str(e)}")
    
    def _create_notebook_template(self, name, description, template, notebook_def):
        """Create notebook definition in Fabric Git format."""
        # Generate Fabric notebook content (Python format)
        notebook_content = self._get_fabric_notebook_content(template, notebook_def)
        
        # Encode as base64
        content_bytes = notebook_content.encode('utf-8')
        content_base64 = base64.b64encode(content_bytes).decode('utf-8')
        
        # Construct definition for Fabric Git format
        # Do not include format field - let API infer from the path
        definition = {
            "parts": [
                {
                    "path": "notebook-content.py",
                    "payload": content_base64,
                    "payloadType": "InlineBase64"
                }
            ]
        }
        
        # Add default lakehouse if specified
        if notebook_def.get("default_lakehouse"):
            definition["defaultLakehouse"] = {
                "name": notebook_def["default_lakehouse"],
                "workspaceId": self.workspace_id
            }
        
        return definition
    
    def _get_fabric_notebook_content(self, template, notebook_def):
        """Generate Fabric notebook content in Python format."""
        name = notebook_def.get('name', 'Untitled')
        description = notebook_def.get('description', '')
        
        if template == "basic_spark":
            # Create basic PySpark notebook in Fabric format
            # Use proper Fabric notebook format
            content = """# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# CELL ********************

# Welcome to your new notebook
# Type here in the cell editor to add code!

# METADATA ********************

# META {
# META   "language": "python",
# META   "azdata_cell_guid": "00000000-0000-0000-0000-000000000000"
# META }

# CELL ********************

print('Hello from Fabric notebook!')

# METADATA ********************

# META {
# META   "language": "python",
# META   "azdata_cell_guid": "00000000-0000-0000-0000-000000000001"
# META }
"""
        elif template == "sql":
            content = """# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC -- SQL query example
# MAGIC SELECT 1 as test

# METADATA ********************

# META {
# META   "language": "sql",
# META   "azdata_cell_guid": "00000000-0000-0000-0000-000000000000"
# META }
"""
        else:
            # Default notebook
            content = """# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# CELL ********************

print('Notebook initialized')

# METADATA ********************

# META {
# META   "language": "python",
# META   "azdata_cell_guid": "00000000-0000-0000-0000-000000000000"
# META }
"""
        
        return content
    
    def _create_spark_job_template(self, name, description, job_def):
        """Create Spark job definition."""
        job = {
            "displayName": name,
            "description": description or f"Spark job: {name}",
            "definition": {
                "executionData": {
                    "jobType": "SparkJob"
                }
            }
        }
        
        # Add main file reference
        if job_def.get("main_file"):
            if not job.get("definition"):
                job["definition"] = {}
            job["definition"]["mainFile"] = job_def["main_file"]
        
        # Add default lakehouse
        if job_def.get("default_lakehouse"):
            if not job.get("definition"):
                job["definition"] = {}
            job["definition"]["defaultLakehouse"] = {
                "name": job_def["default_lakehouse"],
                "workspaceId": self.workspace_id
            }
        
        # Add Spark configuration if provided
        if job_def.get("configuration"):
            if not job.get("definition"):
                job["definition"] = {}
            if not job["definition"].get("executionData"):
                job["definition"]["executionData"] = {}
            job["definition"]["executionData"]["configuration"] = job_def["configuration"]
        
        return job
    
    def _create_pipeline_template(self, name, description, pipeline_def):
        """Create data pipeline definition."""
        # Base pipeline structure
        pipeline = {
            "displayName": name,
            "description": description or f"Pipeline: {name}",
            "objectId": "",
            "properties": {
                "activities": pipeline_def.get("activities", [
                    {
                        "name": "PlaceholderActivity",
                        "type": "Script",
                        "typeProperties": {
                            "scripts": [
                                {
                                    "type": "Query",
                                    "text": "SELECT 1"
                                }
                            ]
                        }
                    }
                ]),
                "annotations": [],
                "variables": pipeline_def.get("variables", {})
            }
        }
        
        # Add parameters if specified
        if pipeline_def.get("parameters"):
            pipeline["properties"]["parameters"] = pipeline_def["parameters"]
        
        return pipeline
    
    def _create_semantic_model_template(self, name, description, model_def):
        """Create semantic model definition."""
        model = {
            "displayName": name,
            "description": description or f"Semantic model: {name}",
            "definition": {
                "parts": []
            }
        }
        
        # Add connection if specified
        if model_def.get("connection"):
            model["definition"]["connection"] = model_def["connection"]
        
        return model
    
    def _create_report_template(self, name, description, report_def):
        """Create Power BI report definition."""
        report = {
            "displayName": name,
            "description": description or f"Report: {name}",
            "definition": {
                "parts": []
            }
        }
        
        # Link to semantic model if specified
        if report_def.get("semantic_model"):
            report["datasetId"] = report_def["semantic_model"]
        
        return report
    
    def _create_paginated_report_template(self, name, description, report_def):
        """Create paginated report definition."""
        report = {
            "displayName": name,
            "description": description or f"Paginated report: {name}",
            "definition": {
                "parts": []
            }
        }
        
        return report
    
    def _create_variable_library_template(self, config: Dict) -> Dict:
        """Create Variable Library definition from config"""
        name = config["name"]
        description = config.get("description", f"Variable Library: {name}")
        variables = config.get("variables", [])
        
        # If no variables provided, create from environment parameters
        if not variables:
            params = self.config.get_parameters()
            variables = [
                {
                    "name": key,
                    "value": str(value),
                    "type": "String",
                    "description": f"Environment parameter: {key}"
                }
                for key, value in params.items()
            ]
        
        return {
            "name": name,
            "description": description,
            "variables": variables
        }
    
    def deploy_all(self, dry_run: bool = False) -> bool:
        """
        Deploy all discovered artifacts in dependency order
        
        Args:
            dry_run: If True, only simulate deployment without making changes
            
        Returns:
            True if deployment successful, False otherwise
        """
        logger.info("="*60)
        logger.info(f"Starting deployment to {self.environment} environment")
        if dry_run:
            logger.info("DRY RUN MODE - No changes will be made")
        logger.info("="*60)
        
        # Validate dependencies
        errors = self.resolver.validate_dependencies()
        if errors:
            logger.error("Dependency validation failed. Aborting deployment.")
            return False
        
        # Get deployment order
        deployment_order = self.resolver.get_deployment_order()
        
        if not deployment_order:
            logger.warning("No artifacts to deploy")
            return True
        
        # Deploy each artifact
        success_count = 0
        failure_count = 0
        
        for artifact in deployment_order:
            try:
                logger.info(f"\nDeploying: {artifact['name']} ({artifact['type'].value})")
                
                if not dry_run:
                    self._deploy_artifact(artifact)
                else:
                    logger.info(f"  [DRY RUN] Would deploy {artifact['name']}")
                
                success_count += 1
                logger.info(f"✅ Successfully deployed: {artifact['name']}")
                
            except Exception as e:
                failure_count += 1
                logger.error(f"❌ Failed to deploy {artifact['name']}: {str(e)}")
        
        # Summary
        logger.info("\n" + "="*60)
        logger.info("DEPLOYMENT SUMMARY")
        logger.info("="*60)
        logger.info(f"Total artifacts: {len(deployment_order)}")
        logger.info(f"Successful: {success_count}")
        logger.info(f"Failed: {failure_count}")
        logger.info("="*60)
        
        # Save deployment commit if successful
        if failure_count == 0:
            self._save_deployment_state()
        
        return failure_count == 0
    
    def _deploy_artifact(self, artifact: Dict) -> None:
        """
        Deploy a single artifact
        
        Args:
            artifact: Artifact dictionary
        """
        artifact_type = artifact["type"]
        artifact_name = artifact["name"]
        
        if artifact_type == ArtifactType.LAKEHOUSE:
            self._deploy_lakehouse(artifact_name)
        elif artifact_type == ArtifactType.ENVIRONMENT:
            self._deploy_environment(artifact_name)
        elif artifact_type == ArtifactType.SEMANTIC_MODEL:
            self._deploy_semantic_model(artifact_name)
        elif artifact_type == ArtifactType.NOTEBOOK:
            self._deploy_notebook(artifact_name)
        elif artifact_type == ArtifactType.SPARK_JOB_DEFINITION:
            self._deploy_spark_job(artifact_name)
        elif artifact_type == ArtifactType.DATA_PIPELINE:
            self._deploy_pipeline(artifact_name)
        elif artifact_type == ArtifactType.VARIABLE_LIBRARY:
            self._deploy_variable_library(artifact_name)
        elif artifact_type == ArtifactType.SQL_VIEW:
            self._deploy_sql_view(artifact_name)
        elif artifact_type == ArtifactType.POWER_BI_REPORT:
            self._deploy_report(artifact_name)
        elif artifact_type == ArtifactType.PAGINATED_REPORT:
            self._deploy_paginated_report(artifact_name)
        else:
            logger.warning(f"Unsupported artifact type: {artifact_type}")
    
    def _deploy_lakehouse(self, name: str) -> None:
        """Deploy a lakehouse"""
        lakehouse_dir = self.artifacts_dir / self.artifacts_root_folder / "Lakehouses"
        lakehouse_file = lakehouse_dir / f"{name}.json"
        # Check both official Git format and legacy folder names
        lakehouse_folder_v2 = lakehouse_dir / f"{name}.Lakehouse"  # Official Git format
        lakehouse_folder_v1 = lakehouse_dir / name  # Legacy format
        
        # Skip if this lakehouse was just created in the current run AND no local file exists
        if ('lakehouse', name) in self._created_in_this_run and not lakehouse_file.exists() and not lakehouse_folder_v2.exists() and not lakehouse_folder_v1.exists():
            logger.info(f"  ⏭ Skipping lakehouse '{name}' - created in this run with no file to deploy")
            return
        
        # Try to read from JSON file first, then Fabric Git folder format
        definition = None
        shortcuts = []
        
        if lakehouse_file.exists():
            logger.info(f"  Reading lakehouse definition from: {lakehouse_file.name}")
            with open(lakehouse_file, 'r') as f:
                definition = json.load(f)
            # Shortcuts might be in the JSON file directly
            shortcuts = definition.get("shortcuts", [])
        elif lakehouse_folder_v2.exists():
            logger.info(f"  Reading lakehouse definition from Fabric Git folder (v2): {name}.Lakehouse/")
            # Try .platform file first (Version 2 - official format)
            platform_file = lakehouse_folder_v2 / ".platform"
            if platform_file.exists():
                with open(platform_file, 'r') as f:
                    platform_data = json.load(f)
                definition = {
                    "name": platform_data["metadata"].get("displayName", name),
                    "description": platform_data["metadata"].get("description", "")
                }
                logger.info(f"  Using .platform file (Git format v2)")
            else:
                # Fall back to item.metadata.json
                item_metadata_file = lakehouse_folder_v2 / "item.metadata.json"
                if item_metadata_file.exists():
                    with open(item_metadata_file, 'r') as f:
                        definition = json.load(f)
                else:
                    definition = {"name": name, "description": ""}
            
            # Read shortcuts from shortcuts.metadata.json
            shortcuts_file = lakehouse_folder_v2 / "shortcuts.metadata.json"
            if shortcuts_file.exists():
                logger.info(f"  Reading shortcuts from: shortcuts.metadata.json")
                with open(shortcuts_file, 'r') as f:
                    shortcuts_data = json.load(f)
                    # Handle both direct array and object with 'shortcuts' key
                    if isinstance(shortcuts_data, list):
                        shortcuts = shortcuts_data
                    elif isinstance(shortcuts_data, dict):
                        shortcuts = shortcuts_data.get("shortcuts", [])
                    else:
                        shortcuts = []
                    logger.info(f"  Found {len(shortcuts)} shortcut(s) in metadata file")
        elif lakehouse_folder_v1.exists():
            logger.info(f"  Reading lakehouse definition from Fabric Git folder (v1): {name}/")
            # Try .platform file first
            platform_file = lakehouse_folder_v1 / ".platform"
            if platform_file.exists():
                with open(platform_file, 'r') as f:
                    platform_data = json.load(f)
                definition = {
                    "name": platform_data["metadata"].get("displayName", name),
                    "description": platform_data["metadata"].get("description", "")
                }
                logger.info(f"  Using .platform file (Git format v2)")
            else:
                # Fall back to item.metadata.json
                item_metadata_file = lakehouse_folder_v1 / "item.metadata.json"
                if item_metadata_file.exists():
                    with open(item_metadata_file, 'r') as f:
                        definition = json.load(f)
                else:
                    definition = {"name": name, "description": ""}
            
            # Read shortcuts from shortcuts.metadata.json
            shortcuts_file = lakehouse_folder_v1 / "shortcuts.metadata.json"
            if shortcuts_file.exists():
                logger.info(f"  Reading shortcuts from: shortcuts.metadata.json")
                with open(shortcuts_file, 'r') as f:
                    shortcuts_data = json.load(f)
                    # Handle both direct array and object with 'shortcuts' key
                    if isinstance(shortcuts_data, list):
                        shortcuts = shortcuts_data
                    elif isinstance(shortcuts_data, dict):
                        shortcuts = shortcuts_data.get("shortcuts", [])
                    else:
                        shortcuts = []
                    logger.info(f"  Found {len(shortcuts)} shortcut(s) in metadata file")
        else:
            logger.error(f"  ❌ Lakehouse file or folder not found: {lakehouse_file}, {lakehouse_folder_v2}, or {lakehouse_folder_v1}")
            raise FileNotFoundError(f"Lakehouse file or folder not found: {lakehouse_file} or {lakehouse_folder_v2} or {lakehouse_folder_v1}")
        
        description = definition.get("description", "")
        
        # Check if lakehouse exists
        existing = self.client.list_lakehouses(self.workspace_id)
        existing_lakehouse = next((lh for lh in existing if lh["displayName"] == name), None)
        
        if existing_lakehouse:
            lakehouse_id = existing_lakehouse['id']
            logger.info(f"  Lakehouse '{name}' already exists (ID: {lakehouse_id})")
            
            # Check if description changed
            existing_desc = existing_lakehouse.get("description", "")
            if existing_desc != description:
                logger.info(f"  Description differs - consider manual update")
                logger.info(f"    Current: {existing_desc}")
                logger.info(f"    New: {description}")
            
            # Handle shortcuts if defined
            if shortcuts:
                logger.info(f"  Processing {len(shortcuts)} shortcut(s) for lakehouse '{name}'...")
                for shortcut_def in shortcuts:
                    try:
                        shortcut_name = shortcut_def["name"]
                        target = shortcut_def["target"]
                        path = shortcut_def.get("path", "Tables")
                        
                        # Check if shortcut already exists
                        existing_shortcuts = self.client.list_shortcuts(self.workspace_id, lakehouse_id, path)
                        shortcut_exists = any(sc.get("name") == shortcut_name for sc in existing_shortcuts)
                        
                        if shortcut_exists:
                            logger.info(f"    ⏭ Shortcut '{shortcut_name}' already exists in {path}")
                        else:
                            self.client.create_shortcut(
                                self.workspace_id,
                                lakehouse_id,
                                shortcut_name,
                                path,
                                target
                            )
                            logger.info(f"    ✓ Created shortcut '{shortcut_name}' in {path}")
                    except Exception as e:
                        logger.error(f"    ❌ Failed to create shortcut '{shortcut_def.get('name', 'unknown')}': {str(e)}")
        else:
            logger.info(f"  Lakehouse '{name}' not found, creating...")
            
            # Get or create folder for lakehouses
            folder_id = self._get_or_create_folder("Lakehouses")
            
            # Get enableSchemas setting - check both simple and native formats
            enable_schemas = definition.get("enable_schemas")
            if enable_schemas is None and "creationPayload" in definition:
                enable_schemas = definition["creationPayload"].get("enableSchemas")
            
            if enable_schemas is not None:
                logger.info(f"  Creating lakehouse with enableSchemas: {enable_schemas}")
            
            result = self.client.create_lakehouse(
                self.workspace_id, 
                name, 
                description, 
                folder_id=folder_id, 
                enable_schemas=enable_schemas
            )
            lakehouse_id = result.get('id') if result else 'unknown'
            logger.info(f"  ✓ Created lakehouse '{name}' in 'Lakehouses' folder (ID: {lakehouse_id})")
            
            # Handle shortcuts after creation
            if shortcuts and lakehouse_id and lakehouse_id != 'unknown':
                logger.info(f"  Processing {len(shortcuts)} shortcut(s) for new lakehouse...")
                for shortcut_def in shortcuts:
                    try:
                        shortcut_name = shortcut_def["name"]
                        target = shortcut_def["target"]
                        path = shortcut_def.get("path", "Tables")
                        
                        self.client.create_shortcut(
                            self.workspace_id,
                            lakehouse_id,
                            shortcut_name,
                            path,
                            target
                        )
                        logger.info(f"    ✓ Created shortcut '{shortcut_name}' in {path}")
                    except Exception as e:
                        logger.error(f"    ❌ Failed to create shortcut '{shortcut_def.get('name', 'unknown')}': {str(e)}")
    
    def _deploy_environment(self, name: str) -> None:
        """Deploy an environment"""
        # Note: We no longer skip config-created environments to allow wsartifacts updates
        env_file = self.artifacts_dir / self.artifacts_root_folder / "Environments" / f"{name}.json"
        
        # Check if environment definition exists
        if not env_file.exists():
            if ('environment', name) in self._created_in_this_run:
                logger.info(f"  ⏭ Skipping environment '{name}' - created from config, no wsartifacts definition")
                return
            else:
                logger.error(f"  ❌ Environment file not found: {env_file}")
                raise FileNotFoundError(f"Environment definition not found: {name}")
        
        with open(env_file, 'r') as f:
            definition = json.load(f)
        
        description = definition.get("description", "")
        
        # Check if environment exists
        existing = self.client.list_environments(self.workspace_id)
        existing_env = next((env for env in existing if env["displayName"] == name), None)
        
        if existing_env:
            # Check if description changed and update
            existing_desc = existing_env.get("description", "")
            if existing_desc != description:
                logger.info(f"  Updating description for environment '{name}'")
                logger.info(f"    Current: {existing_desc}")
                logger.info(f"    New: {description}")
                try:
                    self.client.update_environment(self.workspace_id, existing_env['id'], description)
                    logger.info(f"  ✓ Updated environment description")
                except Exception as e:
                    logger.warning(f"  ⚠ Could not update description: {str(e)}")
            else:
                logger.info(f"  Environment '{name}' already exists, no changes detected (ID: {existing_env['id']})")
        else:
            # Get or create folder for environments
            folder_id = self._get_or_create_folder("Environments")
            
            result = self.client.create_environment(
                self.workspace_id, 
                name, 
                description, 
                folder_id=folder_id
            )
            env_id = result.get('id') if result else 'unknown'
            logger.info(f"  ✓ Created environment '{name}' in 'Environments' folder (ID: {env_id})")
    
    def _deploy_notebook(self, name: str) -> None:
        """Deploy a notebook (supports both .ipynb and Fabric Git folder format)"""
        # Note: We no longer skip config-created notebooks to allow wsartifacts updates
        notebooks_dir = self.artifacts_dir / self.artifacts_root_folder / "Notebooks"
        
        notebook_content = None
        notebook_format = None
        notebook_folder_path = None
        
        # Try .ipynb file first (legacy format)
        notebook_file = notebooks_dir / f"{name}.ipynb"
        if notebook_file.exists():
            logger.debug(f"  Found notebook as .ipynb file: {name}")
            with open(notebook_file, 'r') as f:
                notebook_content = f.read()
            notebook_format = "ipynb"
        else:
            # Try Fabric Git folder format - need to search by displayName in .platform files
            found = False
            if notebooks_dir.exists():
                for item in notebooks_dir.iterdir():
                    if item.is_dir():
                        platform_file = item / ".platform"
                        content_file = item / "notebook-content.py"
                        
                        if platform_file.exists() and content_file.exists():
                            try:
                                with open(platform_file, 'r') as f:
                                    platform_data = json.load(f)
                                display_name = platform_data.get("metadata", {}).get("displayName", item.name)
                                
                                if display_name == name:
                                    logger.debug(f"  Found notebook as Fabric Git folder: {item.name} (displayName: {name})")
                                    # Read the notebook content from notebook-content.py
                                    with open(content_file, 'r', encoding='utf-8') as f:
                                        notebook_content = f.read()
                                    notebook_format = "fabric"
                                    notebook_folder_path = item
                                    found = True
                                    break
                            except Exception as e:
                                logger.debug(f"  Skipping folder {item.name}: {e}")
                                continue
            
            if not found:
                # Fallback: try using name as folder name directly
                notebook_folder = notebooks_dir / name
                if notebook_folder.exists() and notebook_folder.is_dir():
                    platform_file = notebook_folder / ".platform"
                    content_file = notebook_folder / "notebook-content.py"
                    
                    if platform_file.exists() and content_file.exists():
                        logger.debug(f"  Found notebook as Fabric Git folder (by folder name): {name}")
                        with open(content_file, 'r', encoding='utf-8') as f:
                            notebook_content = f.read()
                        notebook_format = "fabric"
                        notebook_folder_path = notebook_folder
                        found = True
            
            if not found:
                # No local files found - this shouldn't happen since we discovered it
                raise FileNotFoundError(f"Notebook '{name}' was discovered but local files not found")
        
        # Substitute environment-specific parameters
        notebook_content = self.config.substitute_parameters(notebook_content)
        
        # Read description from .platform file if Fabric format
        description = None
        if notebook_format == "fabric" and notebook_folder_path:
            platform_file = notebook_folder_path / ".platform"
            try:
                with open(platform_file, 'r') as f:
                    platform_data = json.load(f)
                description = platform_data.get("metadata", {}).get("description", "")
                logger.debug(f"  Read description from .platform: {description[:50] if description else 'None'}...")
            except Exception as e:
                logger.debug(f"  Could not read description from .platform: {e}")
        
        # Parse based on format and construct API payload
        if notebook_format == "ipynb":
            # For .ipynb files, encode the JSON notebook content as base64
            import base64
            content_bytes = notebook_content.encode('utf-8')
            content_base64 = base64.b64encode(content_bytes).decode('utf-8')
            
            # Construct definition for ipynb format
            notebook_definition = {
                "format": "ipynb",
                "parts": [
                    {
                        "path": "notebook-content.ipynb",
                        "payload": content_base64,
                        "payloadType": "InlineBase64"
                    }
                ]
            }
        else:  # fabric format (notebook-content.py)
            # For Fabric format, encode the notebook-content.py as base64
            import base64
            
            # Validate content is not empty
            if not notebook_content or not notebook_content.strip():
                raise ValueError(f"Notebook content is empty for '{name}'")
            
            content_bytes = notebook_content.encode('utf-8')
            content_base64 = base64.b64encode(content_bytes).decode('utf-8')
            
            # Validate base64 encoding succeeded
            if not content_base64:
                raise ValueError(f"Failed to encode notebook content for '{name}'")
            
            # Construct the definition that matches Fabric API expectations
            # Format field omitted = fabricGitSource (default)
            notebook_definition = {
                "parts": [
                    {
                        "path": "notebook-content.py",
                        "payload": content_base64,
                        "payloadType": "InlineBase64"
                    }
                ]
            }
            
            logger.debug(f"  Notebook definition created with {len(content_base64)} byte payload")
        
        # Check if notebook exists
        existing = self.client.list_notebooks(self.workspace_id)
        logger.debug(f"  Found {len(existing)} existing notebooks in workspace")
        
        existing_notebook = next((nb for nb in existing if nb["displayName"] == name), None)
        
        if existing_notebook:
            logger.info(f"  Notebook '{name}' already exists, updating...")
            logger.debug(f"  Existing notebook ID: {existing_notebook['id']}")
            # For updates, send only the definition part
            self.client.update_notebook_definition(
                self.workspace_id,
                existing_notebook['id'],
                notebook_definition
            )
            logger.info(f"  ✓ Updated notebook '{name}' (ID: {existing_notebook['id']})")
        else:
            logger.info(f"  Notebook '{name}' not found, creating new...")
            logger.debug(f"  Existing notebook names: {[nb.get('displayName') for nb in existing]}")
            
            # Get or create folder for notebooks
            folder_id = self._get_or_create_folder("Notebooks")
            
            # For creation, we need the full structure with displayName and optional description
            result = self.client.create_notebook(
                self.workspace_id, 
                name, 
                notebook_definition, 
                description=description,
                folder_id=folder_id
            )
            notebook_id = result.get('id') if result else 'unknown'
            logger.info(f"  ✓ Created notebook '{name}' in 'Notebooks' folder (ID: {notebook_id})")
    
    def _deploy_spark_job(self, name: str) -> None:
        """Deploy a Spark job definition"""
        # Note: We no longer skip config-created spark jobs to allow wsartifacts updates
        job_file = self.artifacts_dir / self.artifacts_root_folder / "Sparkjobdefinitions" / f"{name}.json"
        
        # Check if file exists locally
        if not job_file.exists():
            if ('spark_job_definition', name) in self._created_in_this_run:
                logger.info(f"  ⏭ Skipping Spark job '{name}' - created from config, no wsartifacts definition")
                return
            else:
                raise FileNotFoundError(f"Spark job '{name}' definition not found: {job_file}")
        
        with open(job_file, 'r') as f:
            job_content = f.read()
        
        # Substitute parameters
        job_content = self.config.substitute_parameters(job_content)
        
        # Encode as base64 for API
        import base64
        content_bytes = job_content.encode('utf-8')
        content_base64 = base64.b64encode(content_bytes).decode('utf-8')
        
        # Construct definition according to Fabric API spec
        # Format can be SparkJobDefinitionV1 or SparkJobDefinitionV2
        definition = {
            "parts": [
                {
                    "path": "SparkJobDefinitionV1.json",
                    "payload": content_base64,
                    "payloadType": "InlineBase64"
                }
            ]
        }
        
        # Check if job exists
        existing = self.client.list_spark_job_definitions(self.workspace_id)
        existing_job = next((job for job in existing if job["displayName"] == name), None)
        
        if existing_job:
            logger.info(f"  Spark job '{name}' already exists, updating...")
            self.client.update_spark_job_definition(
                self.workspace_id,
                existing_job['id'],
                definition
            )
            logger.info(f"  ✓ Updated Spark job '{name}' (ID: {existing_job['id']})")
        else:
            # Get or create folder for Spark jobs
            folder_id = self._get_or_create_folder("Sparkjobdefinitions")
            
            # For creation, client.create_spark_job_definition handles displayName + definition wrapping
            result = self.client.create_spark_job_definition(
                self.workspace_id, 
                name, 
                definition, 
                folder_id=folder_id
            )
            job_id = result.get('id') if result else 'unknown'
            logger.info(f"  ✓ Created Spark job '{name}' in 'Sparkjobdefinitions' folder (ID: {job_id})")
    
    def _deploy_pipeline(self, name: str) -> None:
        """Deploy a data pipeline"""
        pipeline_file = self.artifacts_dir / self.artifacts_root_folder / "Datapipelines" / f"{name}.json"
        with open(pipeline_file, 'r') as f:
            pipeline_content = f.read()
        
        # Substitute parameters
        pipeline_content = self.config.substitute_parameters(pipeline_content)
        
        # Encode as base64 for API
        import base64
        content_bytes = pipeline_content.encode('utf-8')
        content_base64 = base64.b64encode(content_bytes).decode('utf-8')
        
        # Construct definition according to Fabric API spec
        definition = {
            "parts": [
                {
                    "path": "pipeline-content.json",
                    "payload": content_base64,
                    "payloadType": "InlineBase64"
                }
            ]
        }
        
        # Check if pipeline exists
        existing = self.client.list_data_pipelines(self.workspace_id)
        existing_pipeline = next((pl for pl in existing if pl["displayName"] == name), None)
        
        if existing_pipeline:
            logger.info(f"  Pipeline '{name}' already exists, updating...")
            self.client.update_data_pipeline(
                self.workspace_id,
                existing_pipeline['id'],
                definition
            )
            logger.info(f"  ✓ Updated pipeline '{name}' (ID: {existing_pipeline['id']})")
        else:
            # Get or create folder for pipelines
            folder_id = self._get_or_create_folder("Datapipelines")
            
            # For creation, client.create_data_pipeline handles displayName + definition wrapping
            result = self.client.create_data_pipeline(
                self.workspace_id, 
                name, 
                definition, 
                folder_id=folder_id
            )
            pipeline_id = result.get('id') if result else 'unknown'
            logger.info(f"  ✓ Created data pipeline '{name}' in 'Datapipelines' folder (ID: {pipeline_id})")
    
    def _deploy_semantic_model(self, name: str) -> None:
        """Deploy a semantic model"""
        model_file = self.artifacts_dir / self.artifacts_root_folder / "Semanticmodels" / f"{name}.json"
        with open(model_file, 'r') as f:
            definition = json.load(f)
        
        # Substitute parameters
        definition_str = json.dumps(definition)
        definition_str = self.config.substitute_parameters(definition_str)
        definition = json.loads(definition_str)
        
        # Check if model exists
        existing = self.client.list_semantic_models(self.workspace_id)
        existing_model = next((m for m in existing if m["displayName"] == name), None)
        
        if existing_model:
            logger.info(f"  Semantic model '{name}' already exists, updating...")
            self.client.update_semantic_model(
                self.workspace_id,
                existing_model['id'],
                definition
            )
            logger.info(f"  Updated semantic model (ID: {existing_model['id']})")
        else:
            # Get or create folder for semantic models
            folder_id = self._get_or_create_folder("Semanticmodels")
            
            result = self.client.create_semantic_model(
                self.workspace_id, 
                name, 
                definition, 
                folder_id=folder_id
            )
            model_id = result.get('id') if result else 'unknown'
            logger.info(f"  ✓ Created semantic model '{name}' in 'Semanticmodels' folder (ID: {model_id})")
    
    def _deploy_report(self, name: str) -> None:
        """Deploy a Power BI report"""
        report_file = self.artifacts_dir / self.artifacts_root_folder / "Reports" / f"{name}.json"
        with open(report_file, 'r') as f:
            definition = json.load(f)
        
        # Substitute parameters
        definition_str = json.dumps(definition)
        definition_str = self.config.substitute_parameters(definition_str)
        definition = json.loads(definition_str)
        
        # Check if report exists
        existing = self.client.list_reports(self.workspace_id)
        existing_report = next((r for r in existing if r["displayName"] == name), None)
        
        if existing_report:
            logger.info(f"  Power BI report '{name}' already exists, updating...")
            self.client.update_report(
                self.workspace_id,
                existing_report['id'],
                definition
            )
            logger.info(f"  Updated report (ID: {existing_report['id']})")
        else:
            # Get or create folder for reports
            folder_id = self._get_or_create_folder("Reports")
            
            result = self.client.create_report(
                self.workspace_id, 
                name, 
                definition, 
                folder_id=folder_id
            )
            report_id = result.get('id') if result else 'unknown'
            logger.info(f"  ✓ Created report '{name}' in 'Reports' folder (ID: {report_id})")
    
    def _deploy_paginated_report(self, name: str) -> None:
        """Deploy a paginated report"""
        report_file = self.artifacts_dir / self.artifacts_root_folder / "Paginatedreports" / f"{name}.json"
        with open(report_file, 'r') as f:
            definition = json.load(f)
        
        # Substitute parameters
        definition_str = json.dumps(definition)
        definition_str = self.config.substitute_parameters(definition_str)
        definition = json.loads(definition_str)
        
        # Check if report exists
        existing = self.client.list_paginated_reports(self.workspace_id)
        existing_report = next((r for r in existing if r["displayName"] == name), None)
        
        if existing_report:
            logger.info(f"  Paginated report '{name}' already exists, updating...")
            self.client.update_paginated_report(
                self.workspace_id,
                existing_report['id'],
                definition
            )
            logger.info(f"  Updated paginated report (ID: {existing_report['id']})")
        else:
            # Get or create folder for paginated reports
            folder_id = self._get_or_create_folder("Paginatedreports")
            
            result = self.client.create_paginated_report(self.workspace_id, name, definition, folder_id=folder_id)
            report_id = result.get('id') if result else 'unknown'
            logger.info(f"  ✓ Created paginated report '{name}' in 'Paginatedreports' folder (ID: {report_id})")
    
    def _deploy_variable_library(self, name: str) -> None:
        """Deploy a Variable Library"""
        library_dir = self.artifacts_dir / self.artifacts_root_folder / "Variablelibraries"
        library_file = library_dir / f"{name}.json"
        library_folder_v2 = library_dir / f"{name}.VariableLibrary"  # Potential Git format
        library_folder_v1 = library_dir / name  # Legacy/custom format
        
        # Try to read from JSON file first, then Fabric Git folder format
        definition = None
        variables = []
        
        if library_file.exists():
            logger.info(f"  Reading variable library definition from: {library_file.name}")
            with open(library_file, 'r') as f:
                definition = json.load(f)
            
            # Substitute parameters in variable values
            definition_str = json.dumps(definition)
            definition_str = self.config.substitute_parameters(definition_str)
            definition = json.loads(definition_str)
            
            # Get variables from definition
            variables = definition.get("variables", [])
            
            # Check if using environment-specific sets
            sets = definition.get("sets")
            active_set = definition.get("active_set")
            
            if sets:
                # Multiple value sets defined - select based on environment or active_set
                env_set_name = active_set or self.environment
                logger.info(f"  Found {len(sets)} variable set(s): {', '.join(sets.keys())}")
                logger.info(f"  Selecting set: '{env_set_name}' (active_set={active_set}, environment={self.environment})")
                
                if env_set_name in sets:
                    variables = sets[env_set_name]
                    logger.info(f"  ✓ Using variable set '{env_set_name}' with {len(variables)} variable(s)")
                else:
                    logger.warning(f"  ⚠ No set found for '{env_set_name}', using 'variables' if present")
                    logger.warning(f"  Available sets: {', '.join(sets.keys())}")
        
        elif library_folder_v2.exists() or library_folder_v1.exists():
            # Use whichever folder exists
            library_folder = library_folder_v2 if library_folder_v2.exists() else library_folder_v1
            folder_suffix = ".VariableLibrary" if library_folder_v2.exists() else ""
            logger.info(f"  Reading variable library definition from folder: {name}{folder_suffix}/")
            
            # Try .platform file first (Version 2 - official format)
            platform_file = library_folder / ".platform"
            if platform_file.exists():
                with open(platform_file, 'r') as f:
                    platform_data = json.load(f)
                definition = {
                    "name": platform_data["metadata"].get("displayName", name),
                    "description": platform_data["metadata"].get("description", "")
                }
                logger.info(f"  Using .platform file (Git format v2)")
            else:
                # Fall back to item.metadata.json
                item_metadata_file = library_folder / "item.metadata.json"
                if item_metadata_file.exists():
                    with open(item_metadata_file, 'r') as f:
                        definition = json.load(f)
                else:
                    # Create minimal definition
                    definition = {"name": name, "description": ""}
            
            # Read variables from valueSets folder - deploy ALL value sets
            value_sets_dir = library_folder / "valueSets"
            if value_sets_dir.exists():
                logger.info(f"  Found valueSets folder - deploying all value sets")
                
                # Show available files in valueSets
                available_files = list(value_sets_dir.glob("*.json"))
                logger.info(f"  Available value sets: {', '.join([f.name for f in available_files])}")
                
                # Read ALL value sets and build the complete structure
                value_sets = {}
                for set_file in available_files:
                    set_name = set_file.stem  # e.g., 'dev', 'uat', 'prod'
                    logger.info(f"  Reading value set: {set_file.name}")
                    
                    with open(set_file, 'r') as f:
                        set_data = json.load(f)
                        # Handle both direct array and object with 'variableOverrides' key
                        if isinstance(set_data, list):
                            value_sets[set_name] = set_data
                        elif isinstance(set_data, dict):
                            # Fabric Git format uses 'variableOverrides', fallback to 'variables'
                            value_sets[set_name] = set_data.get("variableOverrides", set_data.get("variables", []))
                        else:
                            value_sets[set_name] = []
                    
                    # Substitute parameters in this value set
                    set_str = json.dumps(value_sets[set_name])
                    set_str = self.config.substitute_parameters(set_str)
                    value_sets[set_name] = json.loads(set_str)
                    
                    logger.info(f"    ✓ Loaded {len(value_sets[set_name])} variable(s) from '{set_name}' set")
                
                if not value_sets:
                    logger.error(f"  ❌ No valid value sets found in valueSets folder")
                    raise ValueError(f"No value sets found in {value_sets_dir}")
                
                logger.info(f"  Total value sets to deploy: {len(value_sets)}")
                logger.info(f"  NOTE: All value sets will be deployed. You can switch between them in the Fabric UI.")
                
                # Deploy ALL value sets - this is the proper Fabric Git format behavior
                variables = value_sets
            else:
                logger.error(f"  ❌ No valueSets folder found in {library_folder.name}/")
                raise FileNotFoundError(f"No valueSets folder found in variable library: {library_folder}")
        
        else:
            logger.error(f"  ❌ Variable library file or folder not found: {library_file} or {library_folder}")
            raise FileNotFoundError(f"Variable library file or folder not found: {library_file} or {library_folder}")
        
        description = definition.get("description", "")
        
        # Check if Variable Library exists
        existing = self.client.list_variable_libraries(self.workspace_id)
        existing_library = next((lib for lib in existing if lib["displayName"] == name), None)
        
        if existing_library:
            logger.info(f"  Variable Library '{name}' already exists, updating...")
            library_id = existing_library["id"]
            
            # Check if we have value sets (dict) or just variables (list)
            is_value_sets = isinstance(variables, dict) and len(variables) > 0
            
            if variables:
                if is_value_sets:
                    # Git format: deploy base variables + all value sets
                    logger.info(f"  Deploying base variables + {len(variables)} value sets...")
                    
                    parts = []
                    
                    # Add base variables.json (required) - use first value set as base
                    first_set = next(iter(variables.values()))
                    base_vars = [
                        {
                            "name": var["name"],
                            "type": var.get("type", "String"),
                            "value": var["value"],
                            "description": var.get("description", "")
                        }
                        for var in first_set
                    ]
                    base_json = json.dumps({"variables": base_vars}, indent=2)
                    logger.debug(f"  Base variables structure sample:\n{base_json[:300]}...")
                    base_base64 = base64.b64encode(base_json.encode('utf-8')).decode('utf-8')
                    parts.append({
                        "path": "variables.json",
                        "payload": base_base64,
                        "payloadType": "InlineBase64"
                    })
                    
                    # Add each value set as valueSets/{name}.json
                    for set_name, set_vars in variables.items():
                        set_data = {
                            "variableOverrides": [
                                {"name": var["name"], "value": var["value"]} 
                                for var in set_vars
                            ]
                        }
                        set_json = json.dumps(set_data, indent=2)
                        logger.debug(f"  Value set '{set_name}' structure sample:\n{set_json[:300]}...")
                        
                        set_base64 = base64.b64encode(set_json.encode('utf-8')).decode('utf-8')
                        parts.append({
                            "path": f"valueSets/{set_name}.json",
                            "payload": set_base64,
                            "payloadType": "InlineBase64"
                        })
                    
                    update_payload = {
                        "parts": parts,
                        "format": "VariableLibraryV1"
                    }
                else:
                    # Simple list of variables (non-Git format)
                    logger.info(f"  Updating with {len(variables)} variables...")
                    
                    variables_data = {"variables": variables}
                    variables_json = json.dumps(variables_data)
                    variables_base64 = base64.b64encode(variables_json.encode('utf-8')).decode('utf-8')
                    
                    update_payload = {
                        "parts": [
                            {
                                "path": "variables.json",
                                "payload": variables_base64,
                                "payloadType": "InlineBase64"
                            }
                        ],
                        "format": "VariableLibraryV1"
                    }
                
                logger.info(f"  DEBUG: Payload has {len(update_payload['parts'])} part(s)")
                
                try:
                    # First API call: Update the definition with all parts
                    result = self.client.update_variable_library_definition(
                        self.workspace_id,
                        library_id,
                        update_payload
                    )
                    logger.info(f"  DEBUG: API response: {json.dumps(result, indent=2) if result else 'No response'}")
                    logger.info(f"  ✓ Updated Variable Library definition for '{name}'")
                    
                    # Second API call: Set the active value set for this environment (only for value sets)
                    if is_value_sets and self.environment in variables:
                        logger.info(f"  Setting active value set to '{self.environment}'...")
                        self.client.set_active_value_set(
                            self.workspace_id,
                            library_id,
                            self.environment
                        )
                        logger.info(f"  ✓ Set active value set to '{self.environment}' for Variable Library '{name}'")
                except Exception as e:
                    logger.error(f"  ❌ Failed to update Variable Library '{name}': {str(e)}")
                    raise
            else:
                logger.error(f"  ❌ No variables found to update for '{name}'")
                raise ValueError(f"No variables found for Variable Library '{name}'")
        else:
            logger.info(f"  Creating Variable Library: {name}")
            
            # Get or create folder for variable libraries
            folder_id = self._get_or_create_folder("Variablelibraries")
            
            try:
                result = self.client.create_variable_library(
                    self.workspace_id,
                    name,
                    description,
                    folder_id=folder_id
                )
                library_id = result.get('id') if result else None
                
                if not library_id:
                    logger.error(f"  ❌ Failed to create Variable Library '{name}': No ID returned")
                    raise ValueError(f"Failed to create Variable Library '{name}': No ID in response")
                
                logger.info(f"  ✓ Created Variable Library '{name}' in 'Variablelibraries' folder (ID: {library_id})")
                
                if variables:
                    # Check if we have value sets (dict) or just a list of variables
                    is_value_sets = isinstance(variables, dict) and len(variables) > 0
                    
                    if is_value_sets:
                        # Git format: deploy base variables + all value sets
                        logger.info(f"  Setting base variables + {len(variables)} value sets...")
                        
                        parts = []
                        
                        # Add base variables.json (required) - use first value set as base
                        first_set = next(iter(variables.values()))
                        base_vars = [
                            {
                                "name": var["name"],
                                "type": var.get("type", "String"),
                                "value": var["value"],
                                "description": var.get("description", "")
                            }
                            for var in first_set
                        ]
                        base_json = json.dumps({"variables": base_vars}, indent=2)
                        logger.debug(f"  Base variables structure sample:\n{base_json[:300]}...")
                        base_base64 = base64.b64encode(base_json.encode('utf-8')).decode('utf-8')
                        parts.append({
                            "path": "variables.json",
                            "payload": base_base64,
                            "payloadType": "InlineBase64"
                        })
                        
                        # Add each value set as valueSets/{name}.json
                        for set_name, set_vars in variables.items():
                            set_data = {
                                "variableOverrides": [
                                    {"name": var["name"], "value": var["value"]} 
                                    for var in set_vars
                                ]
                            }
                            set_json = json.dumps(set_data, indent=2)
                            logger.debug(f"  Value set '{set_name}' structure sample:\n{set_json[:300]}...")
                            
                            set_base64 = base64.b64encode(set_json.encode('utf-8')).decode('utf-8')
                            parts.append({
                                "path": f"valueSets/{set_name}.json",
                                "payload": set_base64,
                                "payloadType": "InlineBase64"
                            })
                        
                        update_payload = {
                            "parts": parts,
                            "format": "VariableLibraryV1"
                        }
                    else:
                        # Simple list of variables (non-Git format)
                        logger.info(f"  Setting {len(variables)} initial variables...")
                        
                        variables_data = {"variables": variables}
                        variables_json = json.dumps(variables_data)
                        variables_base64 = base64.b64encode(variables_json.encode('utf-8')).decode('utf-8')
                        
                        update_payload = {
                            "parts": [
                                {
                                    "path": "variables.json",
                                    "payload": variables_base64,
                                    "payloadType": "InlineBase64"
                                }
                            ],
                            "format": "VariableLibraryV1"
                        }
                    
                    # First API call: Update the definition with all parts
                    self.client.update_variable_library_definition(
                        self.workspace_id,
                        library_id,
                        update_payload
                    )
                    logger.info(f"  ✓ Initialized variable definition for '{name}'")
                    
                    # Second API call: Set the active value set for this environment (only for value sets)
                    if is_value_sets and self.environment in variables:
                        logger.info(f"  Setting active value set to '{self.environment}'...")
                        self.client.set_active_value_set(
                            self.workspace_id,
                            library_id,
                            self.environment
                        )
                        logger.info(f"  ✓ Set active value set to '{self.environment}' for Variable Library '{name}'")
            except Exception as e:
                logger.error(f"  ❌ Failed to deploy Variable Library '{name}': {str(e)}")
                raise
    
    def _deploy_sql_view(self, name: str) -> None:
        """Deploy a SQL view to lakehouse SQL endpoint"""
        # Find the view file in {artifacts_root_folder}/Views directories
        views_dir = self.artifacts_dir / self.artifacts_root_folder / "Views"
        view_file = None
        lakehouse_name = None
        
        for lakehouse_dir in views_dir.iterdir():
            if not lakehouse_dir.is_dir():
                continue
            
            candidate = lakehouse_dir / f"{name}.sql"
            if candidate.exists():
                view_file = candidate
                lakehouse_name = lakehouse_dir.name
                break
        
        if not view_file:
            raise FileNotFoundError(f"View file not found for: {name}")
        
        # Read the view SQL definition
        with open(view_file, 'r') as f:
            view_sql = f.read()
        
        # Substitute parameters
        view_sql = self.config.substitute_parameters(view_sql)
        
        # Get the lakehouse
        lakehouses = self.client.list_items(self.workspace_id, type_filter="Lakehouse")
        lakehouse = next((lh for lh in lakehouses if lh["displayName"] == lakehouse_name), None)
        
        if not lakehouse:
            raise ValueError(f"Lakehouse '{lakehouse_name}' not found")
        
        lakehouse_id = lakehouse["id"]
        
        # Get SQL endpoint connection string
        logger.info(f"  Connecting to SQL endpoint for lakehouse: {lakehouse_name}")
        connection_string = self.client.get_lakehouse_sql_endpoint(self.workspace_id, lakehouse_id)
        
        # Parse schema and view name from SQL (assuming dbo schema)
        schema = "dbo"
        view_name = name
        
        # Check if SQL contains CREATE VIEW with schema
        import re
        create_match = re.search(r'CREATE\s+VIEW\s+(\[?(\w+)\]?\.)?(\[?(\w+)\]?)', view_sql, re.IGNORECASE)
        if create_match:
            if create_match.group(2):
                schema = create_match.group(2)
            view_name = create_match.group(4)
        
        # Check if view exists
        view_exists = self.client.check_view_exists(connection_string, lakehouse_name, schema, view_name)
        
        if view_exists:
            logger.info(f"  View '{schema}.{view_name}' exists, checking if update needed...")
            
            # Get existing definition
            existing_def = self.client.get_view_definition(connection_string, lakehouse_name, schema, view_name)
            
            # Normalize both definitions for comparison (remove whitespace, comments)
            def normalize_sql(sql):
                # Remove comments
                sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
                sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
                # Remove extra whitespace
                sql = ' '.join(sql.split())
                return sql.strip().upper()
            
            new_sql_normalized = normalize_sql(view_sql)
            existing_sql_normalized = normalize_sql(existing_def) if existing_def else ""
            
            if new_sql_normalized == existing_sql_normalized:
                logger.info(f"  View '{schema}.{view_name}' is up to date, skipping")
                return
            
            logger.info(f"  View definition changed, updating...")
            # Convert CREATE to ALTER
            alter_sql = re.sub(r'CREATE\s+VIEW', 'ALTER VIEW', view_sql, count=1, flags=re.IGNORECASE)
            self.client.execute_sql_command(connection_string, lakehouse_name, alter_sql)
            logger.info(f"  Updated view '{schema}.{view_name}'")
        else:
            logger.info(f"  Creating view '{schema}.{view_name}'...")
            self.client.execute_sql_command(connection_string, lakehouse_name, view_sql)
            logger.info(f"  Created view '{schema}.{view_name}'")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Deploy Microsoft Fabric Data Engineering artifacts"
    )
    parser.add_argument(
        "environment",
        choices=["dev", "uat", "prod"],
        help="Target environment"
    )
    parser.add_argument(
        "--config-dir",
        default="config",
        help="Configuration directory (default: config)"
    )
    parser.add_argument(
        "--artifacts-dir",
        default=".",
        help="Artifacts root directory (default: current directory)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate deployment without making changes"
    )
    parser.add_argument(
        "--create-artifacts",
        action="store_true",
        help="Create artifacts defined in config file (with service principal ownership)"
    )
    parser.add_argument(
        "--skip-discovery",
        action="store_true",
        help="Skip artifact discovery (useful with --create-artifacts)"
    )
    parser.add_argument(
        "--force-all",
        action="store_true",
        help="Deploy all artifacts, ignoring change detection"
    )
    parser.add_argument(
        "--artifacts",
        help="Comma-separated list of specific artifacts to deploy (e.g., 'Notebook1,Lakehouse2')"
    )
    
    args = parser.parse_args()
    
    try:
        deployer = FabricDeployer(
            args.environment,
            args.config_dir,
            args.artifacts_dir
        )
        
        # Create artifacts from config if requested
        if args.create_artifacts:
            logger.info("Running in artifact creation mode")
            success = deployer.create_artifacts_from_config(dry_run=args.dry_run)
            if not success:
                logger.error("Artifact creation failed")
                sys.exit(1)
            logger.info("Artifact creation completed successfully")
            
            # If not deploying, exit here
            if args.skip_discovery:
                sys.exit(0)
        
        # Discover and deploy artifacts
        if not args.skip_discovery:
            # Parse specific artifacts if provided
            specific_artifacts = None
            if args.artifacts:
                specific_artifacts = [a.strip() for a in args.artifacts.split(',')]
                logger.info(f"Deploying specific artifacts: {', '.join(specific_artifacts)}")
            
            deployer.discover_artifacts(
                force_all=args.force_all,
                specific_artifacts=specific_artifacts
            )
            success = deployer.deploy_all(dry_run=args.dry_run)
            sys.exit(0 if success else 1)
        else:
            sys.exit(0)
        
    except Exception as e:
        logger.error(f"Deployment failed: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
