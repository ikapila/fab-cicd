"""
Dependency Resolver for Microsoft Fabric Artifacts
Determines deployment order based on artifact dependencies
"""

from typing import List, Dict, Set
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ArtifactType(Enum):
    """Supported Fabric artifact types"""
    LAKEHOUSE = "Lakehouse"
    ENVIRONMENT = "Environment"
    SEMANTIC_MODEL = "SemanticModel"
    NOTEBOOK = "Notebook"
    SPARK_JOB_DEFINITION = "SparkJobDefinition"
    DATA_PIPELINE = "DataPipeline"
    KQL_DATABASE = "KQLDatabase"
    KQL_QUERYSET = "KQLQueryset"
    EVENTSTREAM = "Eventstream"
    SHORTCUT = "Shortcut"
    VARIABLE_LIBRARY = "VariableLibrary"
    SQL_VIEW = "SqlView"
    POWER_BI_REPORT = "Report"
    PAGINATED_REPORT = "PaginatedReport"


class DependencyResolver:
    """Resolves dependencies and determines deployment order for Fabric artifacts"""
    
    # Define dependency hierarchy (artifacts that should be deployed first)
    DEPENDENCY_PRIORITY = {
        ArtifactType.VARIABLE_LIBRARY: 1,    # Variable libraries FIRST (config values used by other artifacts)
        ArtifactType.ENVIRONMENT: 2,         # Environments second (runtime configs)
        ArtifactType.LAKEHOUSE: 3,           # Lakehouses third (data storage, may reference variables)
        ArtifactType.KQL_DATABASE: 4,        # KQL Databases fourth
        ArtifactType.SHORTCUT: 5,            # Shortcuts fifth (after lakehouses, may reference variables)
        ArtifactType.SQL_VIEW: 6,            # SQL views sixth (after lakehouses, may depend on other views)
        ArtifactType.SEMANTIC_MODEL: 7,      # Semantic models seventh (data models)
        ArtifactType.NOTEBOOK: 8,            # Notebooks eighth
        ArtifactType.SPARK_JOB_DEFINITION: 9,  # Spark jobs ninth
        ArtifactType.KQL_QUERYSET: 10,       # KQL Querysets tenth
        ArtifactType.POWER_BI_REPORT: 11,    # Power BI reports eleventh (depend on semantic models)
        ArtifactType.PAGINATED_REPORT: 12,   # Paginated reports twelfth
        ArtifactType.EVENTSTREAM: 13,        # Eventstreams thirteenth
        ArtifactType.DATA_PIPELINE: 14,      # Pipelines last (orchestration)
    }
    
    def __init__(self):
        """Initialize dependency resolver"""
        self.artifacts: List[Dict] = []
        self.dependency_graph: Dict[str, Set[str]] = {}
    
    def add_artifact(
        self,
        artifact_id: str,
        artifact_type: ArtifactType,
        artifact_name: str,
        dependencies: List[str] = None
    ) -> None:
        """
        Add an artifact to the resolver
        
        Args:
            artifact_id: Unique identifier for the artifact
            artifact_type: Type of artifact
            artifact_name: Display name of the artifact
            dependencies: List of artifact IDs this artifact depends on
        """
        artifact = {
            "id": artifact_id,
            "type": artifact_type,
            "name": artifact_name,
            "dependencies": dependencies or []
        }
        
        self.artifacts.append(artifact)
        self.dependency_graph[artifact_id] = set(dependencies or [])
        
        logger.debug(f"Added artifact: {artifact_name} ({artifact_type.value})")
    
    def _get_priority(self, artifact: Dict) -> int:
        """
        Get deployment priority for an artifact
        
        Args:
            artifact: Artifact dictionary
            
        Returns:
            Priority value (lower = deploy first)
        """
        artifact_type = artifact["type"]
        return self.DEPENDENCY_PRIORITY.get(artifact_type, 999)
    
    def _topological_sort(self) -> List[str]:
        """
        Perform topological sort on dependency graph
        
        Returns:
            Sorted list of artifact IDs
            
        Raises:
            ValueError: If circular dependency detected
        """
        # Create copy of dependency graph
        graph = {k: set(v) for k, v in self.dependency_graph.items()}
        result = []
        no_deps = [node for node, deps in graph.items() if not deps]
        
        while no_deps:
            # Sort by priority within the same dependency level
            no_deps.sort(key=lambda x: self._get_priority(
                next(a for a in self.artifacts if a["id"] == x)
            ))
            
            node = no_deps.pop(0)
            result.append(node)
            
            # Remove this node from dependencies of other nodes
            for deps in graph.values():
                deps.discard(node)
            
            # Find new nodes with no dependencies
            no_deps.extend([
                node for node, deps in graph.items()
                if not deps and node not in result and node not in no_deps
            ])
        
        # Check for circular dependencies
        if len(result) != len(graph):
            remaining = set(graph.keys()) - set(result)
            raise ValueError(
                f"Circular dependency detected involving artifacts: {remaining}"
            )
        
        return result
    
    def get_deployment_order(self) -> List[Dict]:
        """
        Get artifacts in deployment order (respecting dependencies)
        
        Returns:
            List of artifacts in deployment order
        """
        if not self.artifacts:
            logger.warning("No artifacts to deploy")
            return []
        
        # First, try topological sort based on explicit dependencies
        try:
            sorted_ids = self._topological_sort()
            deployment_order = [
                next(a for a in self.artifacts if a["id"] == aid)
                for aid in sorted_ids
            ]
        except ValueError as e:
            logger.error(f"Dependency resolution failed: {str(e)}")
            # Fallback to priority-based sorting
            deployment_order = sorted(self.artifacts, key=self._get_priority)
        
        logger.info("Deployment order determined:")
        for idx, artifact in enumerate(deployment_order, 1):
            logger.info(
                f"  {idx}. {artifact['name']} "
                f"({artifact['type'].value})"
            )
        
        return deployment_order
    
    def get_artifacts_by_type(self, artifact_type: ArtifactType) -> List[Dict]:
        """
        Get all artifacts of a specific type
        
        Args:
            artifact_type: Type of artifact to filter
            
        Returns:
            List of artifacts matching the type
        """
        return [a for a in self.artifacts if a["type"] == artifact_type]
    
    def validate_dependencies(self) -> List[str]:
        """
        Validate that all dependencies exist
        
        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        all_ids = {a["id"] for a in self.artifacts}
        
        for artifact in self.artifacts:
            for dep_id in artifact["dependencies"]:
                if dep_id not in all_ids:
                    errors.append(
                        f"Artifact '{artifact['name']}' depends on "
                        f"non-existent artifact ID: {dep_id}"
                    )
        
        if errors:
            logger.error("Dependency validation failed:")
            for error in errors:
                logger.error(f"  - {error}")
        else:
            logger.info("✅ All dependencies are valid")
        
        return errors


def main():
    """Test dependency resolver"""
    print("Testing Dependency Resolver...\n")
    
    resolver = DependencyResolver()
    
    # Add sample artifacts
    lakehouse_id = "lakehouse-001"
    env_id = "env-001"
    notebook_id = "notebook-001"
    job_id = "job-001"
    pipeline_id = "pipeline-001"
    
    resolver.add_artifact(
        lakehouse_id,
        ArtifactType.LAKEHOUSE,
        "SalesDataLakehouse",
        dependencies=[]
    )
    
    resolver.add_artifact(
        env_id,
        ArtifactType.ENVIRONMENT,
        "ProdEnvironment",
        dependencies=[]
    )
    
    resolver.add_artifact(
        notebook_id,
        ArtifactType.NOTEBOOK,
        "ProcessSalesData",
        dependencies=[lakehouse_id, env_id]
    )
    
    resolver.add_artifact(
        job_id,
        ArtifactType.SPARK_JOB_DEFINITION,
        "DailySalesAggregation",
        dependencies=[lakehouse_id, notebook_id]
    )
    
    resolver.add_artifact(
        pipeline_id,
        ArtifactType.DATA_PIPELINE,
        "SalesDailyOrchestration",
        dependencies=[notebook_id, job_id]
    )
    
    # Validate dependencies
    print("Validating dependencies...")
    errors = resolver.validate_dependencies()
    
    if not errors:
        # Get deployment order
        print("\n✅ Getting deployment order...")
        deployment_order = resolver.get_deployment_order()
        
        print("\nDeployment Order:")
        for idx, artifact in enumerate(deployment_order, 1):
            deps = ", ".join(artifact["dependencies"]) if artifact["dependencies"] else "None"
            print(f"{idx}. {artifact['name']} ({artifact['type'].value})")
            print(f"   Dependencies: {deps}")
    else:
        print("\n❌ Dependency validation failed!")


if __name__ == "__main__":
    main()
