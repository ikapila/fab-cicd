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
        
        # Validate authentication
        if not self.auth.validate_authentication():
            raise RuntimeError("Authentication validation failed")
        
        self.workspace_id = self.config.get_workspace_id()
        logger.info(f"Target workspace: {self.config.get_workspace_name()} ({self.workspace_id})")
    
    def discover_artifacts(self) -> None:
        """
        Discover artifacts from file system and build dependency graph
        """
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
        
        logger.info(f"Discovered {len(self.resolver.artifacts)} artifacts")
    
    def _discover_lakehouses(self) -> None:
        """Discover lakehouse definitions"""
        lakehouse_dir = self.artifacts_dir / "lakehouses"
        if not lakehouse_dir.exists():
            logger.debug("No lakehouses directory found")
            return
        
        for lakehouse_file in lakehouse_dir.glob("*.json"):
            with open(lakehouse_file, 'r') as f:
                definition = json.load(f)
            
            lakehouse_name = definition.get("name", lakehouse_file.stem)
            lakehouse_id = definition.get("id", f"lakehouse-{lakehouse_name}")
            
            self.resolver.add_artifact(
                lakehouse_id,
                ArtifactType.LAKEHOUSE,
                lakehouse_name,
                dependencies=[]
            )
            
            logger.debug(f"Discovered lakehouse: {lakehouse_name}")
    
    def _discover_environments(self) -> None:
        """Discover environment definitions"""
        env_dir = self.artifacts_dir / "environments"
        if not env_dir.exists():
            logger.debug("No environments directory found")
            return
        
        for env_file in env_dir.glob("*.json"):
            with open(env_file, 'r') as f:
                definition = json.load(f)
            
            env_name = definition.get("name", env_file.stem)
            env_id = definition.get("id", f"environment-{env_name}")
            
            self.resolver.add_artifact(
                env_id,
                ArtifactType.ENVIRONMENT,
                env_name,
                dependencies=[]
            )
            
            logger.debug(f"Discovered environment: {env_name}")
    
    def _discover_notebooks(self) -> None:
        """Discover notebook definitions"""
        notebook_dir = self.artifacts_dir / "notebooks"
        if not notebook_dir.exists():
            logger.debug("No notebooks directory found")
            return
        
        for notebook_file in notebook_dir.glob("*.ipynb"):
            notebook_name = notebook_file.stem
            notebook_id = f"notebook-{notebook_name}"
            
            # Try to read metadata for dependencies
            dependencies = self._extract_notebook_dependencies(notebook_file)
            
            self.resolver.add_artifact(
                notebook_id,
                ArtifactType.NOTEBOOK,
                notebook_name,
                dependencies=dependencies
            )
            
            logger.debug(f"Discovered notebook: {notebook_name}")
    
    def _discover_spark_jobs(self) -> None:
        """Discover Spark job definitions"""
        job_dir = self.artifacts_dir / "sparkjobdefinitions"
        if not job_dir.exists():
            logger.debug("No Spark job definitions directory found")
            return
        
        for job_file in job_dir.glob("*.json"):
            with open(job_file, 'r') as f:
                definition = json.load(f)
            
            job_name = definition.get("name", job_file.stem)
            job_id = definition.get("id", f"sparkjob-{job_name}")
            dependencies = definition.get("dependencies", [])
            
            self.resolver.add_artifact(
                job_id,
                ArtifactType.SPARK_JOB_DEFINITION,
                job_name,
                dependencies=dependencies
            )
            
            logger.debug(f"Discovered Spark job: {job_name}")
    
    def _discover_pipelines(self) -> None:
        """Discover data pipeline definitions"""
        pipeline_dir = self.artifacts_dir / "datapipelines"
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
    
    def _extract_notebook_dependencies(self, notebook_path: Path) -> List[str]:
        """
        Extract dependencies from notebook metadata
        
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
                    elif create_if_not_exists:
                        result = self.client.create_lakehouse(self.workspace_id, name, description)
                        logger.info(f"  ✓ Created lakehouse '{name}' (ID: {result['id']})")
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
                    elif create_if_not_exists:
                        result = self.client.create_environment(self.workspace_id, name, description)
                        logger.info(f"  ✓ Created environment '{name}' (ID: {result['id']})")
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
            try:
                name = notebook_def["name"]
                description = notebook_def.get("description", "")
                create_if_not_exists = notebook_def.get("create_if_not_exists", True)
                template = notebook_def.get("template", "basic_spark")
                
                logger.info(f"\nProcessing notebook: {name}")
                
                if not dry_run:
                    existing = self.client.list_notebooks(self.workspace_id)
                    existing_notebook = next((nb for nb in existing if nb["displayName"] == name), None)
                    
                    if existing_notebook:
                        logger.info(f"  ✓ Notebook '{name}' already exists (ID: {existing_notebook['id']})")
                    elif create_if_not_exists:
                        # Create basic notebook structure
                        notebook_definition = self._create_notebook_template(name, description, template, notebook_def)
                        result = self.client.create_notebook(self.workspace_id, name, notebook_definition)
                        logger.info(f"  ✓ Created notebook '{name}' (ID: {result['id']})")
                    else:
                        logger.warning(f"  ⚠ Notebook '{name}' does not exist and create_if_not_exists is false")
                else:
                    logger.info(f"  [DRY RUN] Would create notebook: {name}")
                    logger.info(f"    Template: {template}")
                    
            except Exception as e:
                logger.error(f"  ✗ Failed to create notebook '{name}': {str(e)}")
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
                    elif create_if_not_exists:
                        # Create basic Spark job definition
                        job_definition = self._create_spark_job_template(name, description, job_def)
                        result = self.client.create_spark_job_definition(self.workspace_id, name, job_definition)
                        logger.info(f"  ✓ Created Spark job '{name}' (ID: {result['id']})")
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
                    elif create_if_not_exists:
                        # Create basic pipeline definition
                        pipeline_definition = self._create_pipeline_template(name, description, pipeline_def)
                        result = self.client.create_data_pipeline(self.workspace_id, name, pipeline_definition)
                        logger.info(f"  ✓ Created pipeline '{name}' (ID: {result['id']})")
                    else:
                        logger.warning(f"  ⚠ Pipeline '{name}' does not exist and create_if_not_exists is false")
                else:
                    logger.info(f"  [DRY RUN] Would create pipeline: {name}")
                    if pipeline_def.get("activities"):
                        logger.info(f"    Activities: {len(pipeline_def['activities'])}")
                    
            except Exception as e:
                logger.error(f"  ✗ Failed to create pipeline '{name}': {str(e)}")
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
    
    def _create_notebook_template(self, name, description, template, notebook_def):
        """Create notebook definition from template."""
        # Base notebook structure
        notebook = {
            "displayName": name,
            "description": description or f"Notebook: {name}",
            "definition": {
                "format": "ipynb",
                "parts": [
                    {
                        "path": "notebook-content.py",
                        "payload": self._get_notebook_content(template, notebook_def),
                        "payloadType": "InlineBase64"
                    }
                ]
            }
        }
        
        # Add default lakehouse if specified
        if notebook_def.get("default_lakehouse"):
            notebook["definition"]["defaultLakehouse"] = {
                "name": notebook_def["default_lakehouse"],
                "workspaceId": self.workspace_id
            }
        
        return notebook
    
    def _get_notebook_content(self, template, notebook_def):
        """Generate notebook content based on template."""
        if template == "basic_spark":
            # Create basic PySpark notebook
            notebook_content = {
                "cells": [
                    {
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": [f"# {notebook_def['name']}\n", f"\n{notebook_def.get('description', '')}"]
                    },
                    {
                        "cell_type": "code",
                        "execution_count": None,
                        "metadata": {},
                        "outputs": [],
                        "source": [
                            "# Import required libraries\n",
                            "from pyspark.sql import SparkSession\n",
                            "from pyspark.sql.functions import *\n",
                            "\n",
                            "print('Notebook initialized successfully')"
                        ]
                    },
                    {
                        "cell_type": "code",
                        "execution_count": None,
                        "metadata": {},
                        "outputs": [],
                        "source": [
                            "# Your code here\n",
                            "# This is a placeholder notebook\n"
                        ]
                    }
                ],
                "metadata": {
                    "language_info": {
                        "name": "python"
                    },
                    "kernelspec": {
                        "display_name": "Synapse PySpark",
                        "name": "synapse_pyspark"
                    }
                },
                "nbformat": 4,
                "nbformat_minor": 2
            }
        elif template == "sql":
            # Create SQL notebook
            notebook_content = {
                "cells": [
                    {
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": [f"# {notebook_def['name']}\n", f"\n{notebook_def.get('description', '')}"]
                    },
                    {
                        "cell_type": "code",
                        "execution_count": None,
                        "metadata": {"language": "sql"},
                        "outputs": [],
                        "source": [
                            "-- SQL query example\n",
                            "-- SELECT * FROM table_name LIMIT 10;\n"
                        ]
                    }
                ],
                "metadata": {
                    "language_info": {
                        "name": "sql"
                    }
                },
                "nbformat": 4,
                "nbformat_minor": 2
            }
        else:
            # Default empty notebook
            notebook_content = {
                "cells": [],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 2
            }
        
        # Convert to base64
        content_str = json.dumps(notebook_content)
        content_bytes = content_str.encode('utf-8')
        content_base64 = base64.b64encode(content_bytes).decode('utf-8')
        
        return content_base64
    
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
        elif artifact_type == ArtifactType.NOTEBOOK:
            self._deploy_notebook(artifact_name)
        elif artifact_type == ArtifactType.SPARK_JOB_DEFINITION:
            self._deploy_spark_job(artifact_name)
        elif artifact_type == ArtifactType.DATA_PIPELINE:
            self._deploy_pipeline(artifact_name)
        else:
            logger.warning(f"Unsupported artifact type: {artifact_type}")
    
    def _deploy_lakehouse(self, name: str) -> None:
        """Deploy a lakehouse"""
        lakehouse_file = self.artifacts_dir / "lakehouses" / f"{name}.json"
        with open(lakehouse_file, 'r') as f:
            definition = json.load(f)
        
        description = definition.get("description", "")
        
        # Check if lakehouse exists
        existing = self.client.list_lakehouses(self.workspace_id)
        existing_lakehouse = next((lh for lh in existing if lh["displayName"] == name), None)
        
        if existing_lakehouse:
            logger.info(f"  Lakehouse '{name}' already exists (ID: {existing_lakehouse['id']})")
        else:
            result = self.client.create_lakehouse(self.workspace_id, name, description)
            logger.info(f"  Created lakehouse (ID: {result['id']})")
    
    def _deploy_environment(self, name: str) -> None:
        """Deploy an environment"""
        env_file = self.artifacts_dir / "environments" / f"{name}.json"
        with open(env_file, 'r') as f:
            definition = json.load(f)
        
        description = definition.get("description", "")
        
        # Check if environment exists
        existing = self.client.list_environments(self.workspace_id)
        existing_env = next((env for env in existing if env["displayName"] == name), None)
        
        if existing_env:
            logger.info(f"  Environment '{name}' already exists (ID: {existing_env['id']})")
        else:
            result = self.client.create_environment(self.workspace_id, name, description)
            logger.info(f"  Created environment (ID: {result['id']})")
    
    def _deploy_notebook(self, name: str) -> None:
        """Deploy a notebook"""
        notebook_file = self.artifacts_dir / "notebooks" / f"{name}.ipynb"
        
        with open(notebook_file, 'r') as f:
            notebook_content = f.read()
        
        # Substitute environment-specific parameters
        notebook_content = self.config.substitute_parameters(notebook_content)
        notebook_definition = json.loads(notebook_content)
        
        # Check if notebook exists
        existing = self.client.list_notebooks(self.workspace_id)
        existing_notebook = next((nb for nb in existing if nb["displayName"] == name), None)
        
        if existing_notebook:
            logger.info(f"  Notebook '{name}' already exists, updating...")
            self.client.update_notebook_definition(
                self.workspace_id,
                existing_notebook['id'],
                notebook_definition
            )
        else:
            result = self.client.create_notebook(self.workspace_id, name, notebook_definition)
            logger.info(f"  Created notebook (ID: {result['id']})")
    
    def _deploy_spark_job(self, name: str) -> None:
        """Deploy a Spark job definition"""
        job_file = self.artifacts_dir / "sparkjobdefinitions" / f"{name}.json"
        with open(job_file, 'r') as f:
            definition = json.load(f)
        
        # Substitute parameters
        definition_str = json.dumps(definition)
        definition_str = self.config.substitute_parameters(definition_str)
        definition = json.loads(definition_str)
        
        # Check if job exists
        existing = self.client.list_spark_job_definitions(self.workspace_id)
        existing_job = next((job for job in existing if job["displayName"] == name), None)
        
        if existing_job:
            logger.info(f"  Spark job '{name}' already exists (ID: {existing_job['id']})")
            # Update would go here
        else:
            result = self.client.create_spark_job_definition(self.workspace_id, name, definition)
            logger.info(f"  Created Spark job (ID: {result['id']})")
    
    def _deploy_pipeline(self, name: str) -> None:
        """Deploy a data pipeline"""
        pipeline_file = self.artifacts_dir / "datapipelines" / f"{name}.json"
        with open(pipeline_file, 'r') as f:
            definition = json.load(f)
        
        # Substitute parameters
        definition_str = json.dumps(definition)
        definition_str = self.config.substitute_parameters(definition_str)
        definition = json.loads(definition_str)
        
        # Check if pipeline exists
        existing = self.client.list_data_pipelines(self.workspace_id)
        existing_pipeline = next((pl for pl in existing if pl["displayName"] == name), None)
        
        if existing_pipeline:
            logger.info(f"  Pipeline '{name}' already exists (ID: {existing_pipeline['id']})")
            # Update would go here
        else:
            result = self.client.create_data_pipeline(self.workspace_id, name, definition)
            logger.info(f"  Created pipeline (ID: {result['id']})")


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
            deployer.discover_artifacts()
            success = deployer.deploy_all(dry_run=args.dry_run)
            sys.exit(0 if success else 1)
        else:
            sys.exit(0)
        
    except Exception as e:
        logger.error(f"Deployment failed: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
