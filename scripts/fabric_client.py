"""
Microsoft Fabric REST API Client
Provides wrapper functions for common Fabric API operations
"""

import requests
import logging
import json
import struct
from typing import Dict, List, Optional, Any
from fabric_auth import FabricAuthenticator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Attempt to import pyodbc for SQL endpoint connections
try:
    import pyodbc
    PYODBC_AVAILABLE = True
except ImportError:
    PYODBC_AVAILABLE = False
    logger.warning("pyodbc not available - SQL view operations will not be supported")


class FabricClient:
    """Client for Microsoft Fabric REST API operations"""
    
    BASE_URL = "https://api.fabric.microsoft.com/v1"
    
    def __init__(self, authenticator: FabricAuthenticator):
        """
        Initialize Fabric client
        
        Args:
            authenticator: FabricAuthenticator instance
        """
        self.auth = authenticator
        
    def _make_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict:
        """
        Make HTTP request to Fabric API
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE, PATCH)
            endpoint: API endpoint (without base URL)
            json_data: JSON payload for POST/PUT/PATCH requests
            params: Query parameters
            
        Returns:
            Response JSON as dictionary
        """
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        headers = self.auth.get_auth_headers()
        
        # Debug logging for notebook operations
        if "notebooks" in endpoint and method == "POST":
            if json_data:
                import json
                # Log structure without exposing full base64 payload
                debug_data = json_data.copy()
                if "definition" in debug_data:
                    definition = debug_data["definition"]
                    if "parts" in definition:
                        parts_summary = []
                        for part in definition["parts"]:
                            part_info = {
                                "path": part.get("path"),
                                "payloadType": part.get("payloadType"),
                                "payload_length": len(part.get("payload", ""))
                            }
                            parts_summary.append(part_info)
                        debug_copy = debug_data.copy()
                        debug_definition = {"parts": parts_summary}
                        # Only include format if it exists in the definition
                        if "format" in definition:
                            debug_definition["format"] = definition["format"]
                        debug_copy["definition"] = debug_definition
                        if "updateDefinition" in endpoint:
                            logger.info(f"Updating notebook - URL: {url}")
                        else:
                            logger.info(f"Creating notebook - URL: {url}")
                        logger.info(f"Payload structure: {json.dumps(debug_copy, indent=2)}")

        # Debug logging for variable library operations
        if "updateDefinition" in endpoint and json_data:
            import json
            debug_data = json_data.copy()
            if "definition" in debug_data:
                definition = debug_data["definition"]
                if "parts" in definition:
                    parts_summary = []
                    for part in definition["parts"]:
                        part_info = {
                            "path": part.get("path"),
                            "payloadType": part.get("payloadType"),
                            "payload_length": len(part.get("payload", ""))
                        }
                        parts_summary.append(part_info)
                    debug_copy = debug_data.copy()
                    debug_definition = {"parts": parts_summary}
                    if "format" in definition:
                        debug_definition["format"] = definition["format"]
                    debug_copy["definition"] = debug_definition
                    logger.info(f"Variable Library Update - URL: {url}")
                    logger.info(f"Payload structure: {json.dumps(debug_copy, indent=2)}")

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=json_data,
                params=params,
                timeout=60
            )
            
            response.raise_for_status()
            
            # Some endpoints return 202 Accepted or 204 No Content
            if response.status_code in [202, 204]:
                result = {"status": "success", "status_code": response.status_code}
                
                # For 202 responses, capture LRO headers
                if response.status_code == 202:
                    if "Location" in response.headers:
                        result["location"] = response.headers["Location"]
                        logger.info(f"  LRO Location header: {response.headers['Location']}")
                    
                    if "x-ms-operation-id" in response.headers:
                        result["operation_id"] = response.headers["x-ms-operation-id"]
                        logger.info(f"  LRO Operation ID: {response.headers['x-ms-operation-id']}")
                    
                    if "Retry-After" in response.headers:
                        result["retry_after"] = int(response.headers["Retry-After"])
                        logger.info(f"  Retry-After: {response.headers['Retry-After']} seconds")
                
                # Try to parse response body if present
                if response.text:
                    try:
                        body = response.json()
                        result.update(body)
                    except:
                        pass
                
                return result
            
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP Error: {e.response.status_code} - {e.response.text}")
            # Try to parse error response for more details
            try:
                error_detail = e.response.json()
                logger.error(f"Error details: {json.dumps(error_detail, indent=2)}")
            except:
                pass
            raise
        except Exception as e:
            logger.error(f"Request failed: {str(e)}")
            raise
    
    def poll_operation_state(self, operation_id: str) -> Dict:
        """
        Poll the state of a long running operation
        
        Args:
            operation_id: The operation ID from x-ms-operation-id header
            
        Returns:
            Operation state dictionary with status, percentComplete, etc.
        """
        return self._make_request("GET", f"/operations/{operation_id}")
    
    def get_operation_result(self, operation_id: str) -> Dict:
        """
        Get the result of a completed long running operation
        
        Args:
            operation_id: The operation ID from x-ms-operation-id header
            
        Returns:
            The created resource details
        """
        return self._make_request("GET", f"/operations/{operation_id}/result")
    
    def wait_for_operation_completion(self, operation_id: str, retry_after: int = 5, max_attempts: int = 10) -> Dict:
        """
        Wait for a long running operation to complete and return the result
        
        Args:
            operation_id: The operation ID to poll
            retry_after: Seconds to wait between polls (default from Retry-After header)
            max_attempts: Maximum number of polling attempts
            
        Returns:
            The created resource details
            
        Raises:
            RuntimeError: If operation fails or times out
        """
        import time
        
        logger.info(f"  Polling operation {operation_id} (retry every {retry_after}s, max {max_attempts} attempts)")
        
        for attempt in range(1, max_attempts + 1):
            time.sleep(retry_after)
            
            state = self.poll_operation_state(operation_id)
            status = state.get("status")
            percent = state.get("percentComplete", 0)
            
            logger.info(f"    Attempt {attempt}/{max_attempts}: {status} ({percent}% complete)")
            
            # Log full state response for debugging
            if status == "Failed":
                logger.info(f"    Full LRO state response: {json.dumps(state, indent=2)}")
            
            if status == "Succeeded":
                logger.info(f"  ✓ Operation completed successfully")
                # Get the actual result
                result = self.get_operation_result(operation_id)
                return result
            elif status == "Failed":
                error = state.get("error", {})
                error_msg = error.get("message", "Unknown error")
                error_code = error.get("errorCode", "")
                more_details = error.get("moreDetails", [])
                
                logger.error(f"  ✗ Operation failed: {error_msg}")
                logger.error(f"    Error code: {error_code}")
                logger.error(f"    Full error object: {json.dumps(error, indent=2)}")
                
                if more_details:
                    logger.error(f"    Additional details:")
                    for detail in more_details:
                        logger.error(f"      - {detail.get('errorCode', '')}: {detail.get('message', '')}")
                
                raise RuntimeError(f"Operation {operation_id} failed: {error_msg}")
            elif status not in ["NotStarted", "Running"]:
                logger.warning(f"  Unexpected operation status: {status}")
        
        raise RuntimeError(f"Operation {operation_id} timed out after {max_attempts} attempts")
    
    # ==================== Workspace Operations ====================
    
    def list_workspaces(self) -> List[Dict]:
        """
        List all workspaces the service principal has access to
        
        Returns:
            List of workspace dictionaries
        """
        logger.info("Listing workspaces")
        response = self._make_request("GET", "/workspaces")
        return response.get("value", [])
    
    def get_workspace(self, workspace_id: str) -> Dict:
        """
        Get workspace details
        
        Args:
            workspace_id: Workspace GUID
            
        Returns:
            Workspace details dictionary
        """
        logger.info(f"Getting workspace: {workspace_id}")
        return self._make_request("GET", f"/workspaces/{workspace_id}")
    
    def create_workspace(self, workspace_name: str, capacity_id: Optional[str] = None) -> Dict:
        """
        Create a new workspace
        
        Args:
            workspace_name: Name for the new workspace
            capacity_id: Optional capacity ID to assign
            
        Returns:
            Created workspace details
        """
        logger.info(f"Creating workspace: {workspace_name}")
        payload = {"displayName": workspace_name}
        if capacity_id:
            payload["capacityId"] = capacity_id
        
        return self._make_request("POST", "/workspaces", json_data=payload)
    
    # ==================== Workspace Folder Operations ====================
    
    def list_workspace_folders(self, workspace_id: str) -> List[Dict]:
        """
        List all folders in a workspace
        
        Args:
            workspace_id: Workspace GUID
            
        Returns:
            List of folder dictionaries
        """
        logger.info(f"Listing folders in workspace: {workspace_id}")
        response = self._make_request("GET", f"/workspaces/{workspace_id}/folders")
        return response.get("value", [])
    
    def create_workspace_folder(self, workspace_id: str, folder_name: str) -> Dict:
        """
        Create a folder in workspace
        
        Args:
            workspace_id: Workspace GUID
            folder_name: Name for the folder
            
        Returns:
            Created folder details
        """
        logger.info(f"Creating workspace folder: {folder_name}")
        payload = {"displayName": folder_name}
        return self._make_request("POST", f"/workspaces/{workspace_id}/folders", json_data=payload)
    
    def get_or_create_workspace_folder(self, workspace_id: str, folder_name: str) -> str:
        """
        Get existing folder or create if it doesn't exist
        
        Args:
            workspace_id: Workspace GUID
            folder_name: Name of the folder
            
        Returns:
            Folder ID (GUID)
        """
        existing_folders = self.list_workspace_folders(workspace_id)
        existing_folder = next((f for f in existing_folders if f.get("displayName") == folder_name), None)
        
        if existing_folder:
            logger.debug(f"  Using existing folder '{folder_name}' (ID: {existing_folder['id']})")
            return existing_folder['id']
        else:
            result = self.create_workspace_folder(workspace_id, folder_name)
            logger.info(f"  ✓ Created workspace folder '{folder_name}' (ID: {result['id']})")
            return result['id']
    
    def move_item_to_folder(self, workspace_id: str, item_id: str, folder_id: str) -> None:
        """
        Move an item to a workspace folder
        
        Args:
            workspace_id: Workspace GUID
            item_id: Item GUID to move
            folder_id: Target folder GUID
        """
        logger.debug(f"  Moving item {item_id} to folder {folder_id}")
        payload = {"workspaceId": workspace_id, "folderId": folder_id}
        self._make_request("POST", f"/workspaces/{workspace_id}/items/{item_id}/move", json_data=payload)
    
    # ==================== Lakehouse Operations ====================
    
    def list_lakehouses(self, workspace_id: str) -> List[Dict]:
        """
        List all lakehouses in a workspace
        
        Args:
            workspace_id: Workspace GUID
            
        Returns:
            List of lakehouse dictionaries
        """
        logger.info(f"Listing lakehouses in workspace: {workspace_id}")
        response = self._make_request("GET", f"/workspaces/{workspace_id}/lakehouses")
        return response.get("value", [])
    
    def get_lakehouse(self, workspace_id: str, lakehouse_id: str) -> Dict:
        """
        Get lakehouse details
        
        Args:
            workspace_id: Workspace GUID
            lakehouse_id: Lakehouse GUID
            
        Returns:
            Lakehouse details dictionary
        """
        logger.info(f"Getting lakehouse: {lakehouse_id}")
        return self._make_request("GET", f"/workspaces/{workspace_id}/lakehouses/{lakehouse_id}")
    
    def create_lakehouse(self, workspace_id: str, lakehouse_name: str, description: str = "", folder_id: str = None, enable_schemas: bool = None) -> Dict:
        """
        Create a new lakehouse
        
        Args:
            workspace_id: Workspace GUID
            lakehouse_name: Name for the new lakehouse
            description: Optional description
            folder_id: Optional workspace folder ID to place lakehouse in
            enable_schemas: Optional - Enable schemas (multi-level namespace) for the lakehouse
            
        Returns:
            Created lakehouse details
        """
        logger.info(f"Creating lakehouse: {lakehouse_name}")
        payload = {
            "displayName": lakehouse_name,
            "description": description
        }
        if folder_id:
            payload["folderId"] = folder_id
            logger.info(f"  Including folderId in payload: {folder_id}")
        if enable_schemas is not None:
            payload["creationPayload"] = {
                "enableSchemas": enable_schemas
            }
            logger.info(f"  Including creationPayload with enableSchemas: {enable_schemas}")
        return self._make_request("POST", f"/workspaces/{workspace_id}/lakehouses", json_data=payload)
    
    def update_lakehouse(self, workspace_id: str, lakehouse_id: str, description: str) -> Dict:
        """
        Update lakehouse properties
        
        Args:
            workspace_id: Workspace GUID
            lakehouse_id: Lakehouse GUID
            description: New description
            
        Returns:
            Update response
        """
        logger.info(f"Updating lakehouse: {lakehouse_id}")
        payload = {
            "description": description
        }
        return self._make_request("PATCH", f"/workspaces/{workspace_id}/lakehouses/{lakehouse_id}", json_data=payload)
    
    # ==================== Notebook Operations ====================
    
    def list_notebooks(self, workspace_id: str) -> List[Dict]:
        """
        List all notebooks in a workspace
        
        Args:
            workspace_id: Workspace GUID
            
        Returns:
            List of notebook dictionaries
        """
        logger.info(f"Listing notebooks in workspace: {workspace_id}")
        response = self._make_request("GET", f"/workspaces/{workspace_id}/notebooks")
        return response.get("value", [])
    
    def get_notebook(self, workspace_id: str, notebook_id: str) -> Dict:
        """
        Get notebook details
        
        Args:
            workspace_id: Workspace GUID
            notebook_id: Notebook GUID
            
        Returns:
            Notebook details dictionary
        """
        logger.info(f"Getting notebook: {notebook_id}")
        return self._make_request("GET", f"/workspaces/{workspace_id}/notebooks/{notebook_id}")
    
    def create_notebook(self, workspace_id: str, notebook_name: str, definition: Dict, description: str = None, folder_id: str = None, wait_for_completion: bool = True) -> Dict:
        """
        Create a notebook (handles long running operations)
        
        Args:
            workspace_id: Workspace GUID
            notebook_name: Name for the notebook
            definition: Notebook definition (content)
            description: Optional notebook description
            folder_id: Optional workspace folder ID to place notebook in
            wait_for_completion: If True, wait for LRO to complete and return notebook details
            
        Returns:
            Created notebook details (if wait_for_completion=True) or LRO response
        """
        logger.info(f"Creating notebook: {notebook_name}")
        payload = {
            "displayName": notebook_name,
            "definition": definition
        }
        if description:
            payload["description"] = description
        if folder_id:
            payload["folderId"] = folder_id
            logger.info(f"  Including folderId in payload: {folder_id}")
        else:
            logger.warning(f"  No folderId provided - notebook will be created at workspace root")
        
        result = self._make_request("POST", f"/workspaces/{workspace_id}/notebooks", json_data=payload)
        
        # Handle long running operation (202 Accepted)
        if result.get("status_code") == 202 and wait_for_completion:
            operation_id = result.get("operation_id")
            retry_after = result.get("retry_after", 5)
            
            if operation_id:
                logger.info(f"  Notebook creation is a long running operation")
                notebook_result = self.wait_for_operation_completion(operation_id, retry_after)
                return notebook_result
            else:
                logger.warning(f"  202 response but no operation_id - cannot poll for completion")
                return result
        
        return result
    
    def update_notebook_definition(self, workspace_id: str, notebook_id: str, definition: Dict) -> Dict:
        """
        Update notebook definition
        
        Args:
            workspace_id: Workspace GUID
            notebook_id: Notebook GUID
            definition: New notebook definition
            
        Returns:
            Update response
        """
        logger.info(f"Updating notebook: {notebook_id}")
        payload = {"definition": definition}
        return self._make_request("POST", f"/workspaces/{workspace_id}/notebooks/{notebook_id}/updateDefinition", json_data=payload)
    
    # ==================== Spark Job Definition Operations ====================
    
    def list_spark_job_definitions(self, workspace_id: str) -> List[Dict]:
        """
        List all Spark job definitions in a workspace
        
        Args:
            workspace_id: Workspace GUID
            
        Returns:
            List of Spark job definition dictionaries
        """
        logger.info(f"Listing Spark job definitions in workspace: {workspace_id}")
        response = self._make_request("GET", f"/workspaces/{workspace_id}/sparkJobDefinitions")
        return response.get("value", [])
    
    def create_spark_job_definition(self, workspace_id: str, job_name: str, definition: Dict, folder_id: str = None, wait_for_completion: bool = True) -> Dict:
        """
        Create a Spark job definition (handles long running operations)
        
        Args:
            workspace_id: Workspace GUID
            job_name: Name for the Spark job
            definition: Job definition
            folder_id: Optional workspace folder ID to place job in
            wait_for_completion: If True, wait for LRO to complete
            
        Returns:
            Created job details
        """
        logger.info(f"Creating Spark job definition: {job_name}")
        payload = {
            "displayName": job_name,
            "definition": definition
        }
        if folder_id:
            payload["folderId"] = folder_id
        
        result = self._make_request("POST", f"/workspaces/{workspace_id}/sparkJobDefinitions", json_data=payload)
        
        # Handle long running operation (202 Accepted)
        if result.get("status_code") == 202 and wait_for_completion:
            operation_id = result.get("operation_id")
            retry_after = result.get("retry_after", 5)
            
            if operation_id:
                logger.info(f"  Spark job creation is a long running operation")
                job_result = self.wait_for_operation_completion(operation_id, retry_after)
                return job_result
            else:
                logger.warning(f"  202 response but no operation_id - cannot poll for completion")
                return result
        
        return result
    
    def update_spark_job_definition(self, workspace_id: str, job_id: str, definition: Dict) -> Dict:
        """
        Update Spark job definition
        
        Args:
            workspace_id: Workspace GUID
            job_id: Spark job GUID
            definition: New job definition
            
        Returns:
            Update response
        """
        logger.info(f"Updating Spark job definition: {job_id}")
        payload = {"definition": definition}
        return self._make_request("POST", f"/workspaces/{workspace_id}/sparkJobDefinitions/{job_id}/updateDefinition", json_data=payload)
    
    # ==================== Data Pipeline Operations ====================
    
    def list_data_pipelines(self, workspace_id: str) -> List[Dict]:
        """
        List all data pipelines in a workspace
        
        Args:
            workspace_id: Workspace GUID
            
        Returns:
            List of data pipeline dictionaries
        """
        logger.info(f"Listing data pipelines in workspace: {workspace_id}")
        response = self._make_request("GET", f"/workspaces/{workspace_id}/dataPipelines")
        return response.get("value", [])
    
    def create_data_pipeline(self, workspace_id: str, pipeline_name: str, definition: Dict, folder_id: str = None) -> Dict:
        """
        Create a data pipeline
        
        Args:
            workspace_id: Workspace GUID
            pipeline_name: Name for the pipeline
            definition: Pipeline definition
            folder_id: Optional workspace folder ID to place pipeline in
            
        Returns:
            Created pipeline details
        """
        logger.info(f"Creating data pipeline: {pipeline_name}")
        payload = {
            "displayName": pipeline_name,
            "definition": definition
        }
        if folder_id:
            payload["folderId"] = folder_id
        return self._make_request("POST", f"/workspaces/{workspace_id}/dataPipelines", json_data=payload)
    
    def update_data_pipeline(self, workspace_id: str, pipeline_id: str, definition: Dict) -> Dict:
        """
        Update data pipeline definition
        
        Args:
            workspace_id: Workspace GUID
            pipeline_id: Pipeline GUID
            definition: New pipeline definition
            
        Returns:
            Update response
        """
        logger.info(f"Updating data pipeline: {pipeline_id}")
        payload = {"definition": definition}
        return self._make_request("POST", f"/workspaces/{workspace_id}/dataPipelines/{pipeline_id}/updateDefinition", json_data=payload)
    
    # ==================== Environment Operations ====================
    
    def list_environments(self, workspace_id: str) -> List[Dict]:
        """
        List all environments in a workspace
        
        Args:
            workspace_id: Workspace GUID
            
        Returns:
            List of environment dictionaries
        """
        logger.info(f"Listing environments in workspace: {workspace_id}")
        response = self._make_request("GET", f"/workspaces/{workspace_id}/environments")
        return response.get("value", [])
    
    def create_environment(self, workspace_id: str, environment_name: str, description: str = "", folder_id: str = None) -> Dict:
        """
        Create an environment
        
        Args:
            workspace_id: Workspace GUID
            environment_name: Name for the environment
            description: Optional description
            folder_id: Optional workspace folder ID to place environment in
            
        Returns:
            Created environment details
        """
        logger.info(f"Creating environment: {environment_name}")
        payload = {
            "displayName": environment_name,
            "description": description
        }
        if folder_id:
            payload["folderId"] = folder_id
            logger.info(f"  Including folderId in payload: {folder_id}")
        return self._make_request("POST", f"/workspaces/{workspace_id}/environments", json_data=payload)
    
    def update_environment(self, workspace_id: str, environment_id: str, description: str) -> Dict:
        """
        Update environment properties
        
        Args:
            workspace_id: Workspace GUID
            environment_id: Environment GUID
            description: New description
            
        Returns:
            Update response
        """
        logger.info(f"Updating environment: {environment_id}")
        payload = {
            "description": description
        }
        return self._make_request("PATCH", f"/workspaces/{workspace_id}/environments/{environment_id}", json_data=payload)
    
    # ==================== Item Operations (Generic) ====================
    
    def list_items(self, workspace_id: str, item_type: Optional[str] = None) -> List[Dict]:
        """
        List all items in a workspace, optionally filtered by type
        
        Args:
            workspace_id: Workspace GUID
            item_type: Optional item type filter (e.g., 'Notebook', 'Lakehouse')
            
        Returns:
            List of item dictionaries
        """
        logger.info(f"Listing items in workspace: {workspace_id}")
        params = {"type": item_type} if item_type else None
        response = self._make_request("GET", f"/workspaces/{workspace_id}/items", params=params)
        return response.get("value", [])
    
    def delete_item(self, workspace_id: str, item_id: str) -> Dict:
        """
        Delete an item from a workspace
        
        Args:
            workspace_id: Workspace GUID
            item_id: Item GUID
            
        Returns:
            Deletion response
        """
        logger.info(f"Deleting item: {item_id}")
        return self._make_request("DELETE", f"/workspaces/{workspace_id}/items/{item_id}")
    
    # ==================== Semantic Model Operations ====================
    
    def list_semantic_models(self, workspace_id: str) -> List[Dict]:
        """
        List all semantic models (datasets) in a workspace
        
        Args:
            workspace_id: Workspace GUID
            
        Returns:
            List of semantic model dictionaries
        """
        logger.info(f"Listing semantic models in workspace: {workspace_id}")
        response = self._make_request("GET", f"/workspaces/{workspace_id}/semanticModels")
        return response.get("value", [])
    
    def create_semantic_model(self, workspace_id: str, model_name: str, definition: Dict, folder_id: str = None) -> Dict:
        """
        Create a semantic model
        
        Args:
            workspace_id: Workspace GUID
            model_name: Name for the semantic model
            definition: Model definition
            folder_id: Optional workspace folder ID to place model in
            
        Returns:
            Created model details
        """
        logger.info(f"Creating semantic model: {model_name}")
        payload = {
            "displayName": model_name,
            "definition": definition
        }
        if folder_id:
            payload["folderId"] = folder_id
        return self._make_request("POST", f"/workspaces/{workspace_id}/semanticModels", json_data=payload)
    
    def update_semantic_model(self, workspace_id: str, model_id: str, definition: Dict) -> Dict:
        """
        Update semantic model definition
        
        Args:
            workspace_id: Workspace GUID
            model_id: Semantic model GUID
            definition: New model definition
            
        Returns:
            Update response
        """
        logger.info(f"Updating semantic model: {model_id}")
        payload = {"definition": definition}
        return self._make_request("POST", f"/workspaces/{workspace_id}/semanticModels/{model_id}/updateDefinition", json_data=payload)
    
    def get_semantic_model_tables(self, workspace_id: str, model_id: str) -> List[Dict]:
        """
        Get all tables from a semantic model
        
        Args:
            workspace_id: Workspace GUID
            model_id: Semantic model GUID
        
        Returns:
            List of tables with name, source, etc.
        """
        endpoint = f"/workspaces/{workspace_id}/semanticModels/{model_id}/tables"
        response = self._make_request("GET", endpoint)
        return response.get("value", [])
    
    def rebind_semantic_model_sources(self, workspace_id: str, model_id: str, table_sources: List[Dict]) -> Dict:
        """
        Rebind semantic model table sources after deployment
        
        This allows changing data sources without redeploying the entire model,
        similar to Fabric deployment pipeline rules.
        
        Args:
            workspace_id: Workspace GUID
            model_id: Semantic model GUID
            table_sources: List of table rebinding configs:
              [
                {
                  "tableName": "FactSales",
                  "sourceLakehouseId": "lakehouse-guid",
                  "sourceWorkspaceId": "workspace-guid"
                }
              ]
        
        Returns:
            Rebinding response
        """
        logger.info(f"Rebinding data sources for semantic model: {model_id}")
        endpoint = f"/workspaces/{workspace_id}/semanticModels/{model_id}/rebindSources"
        payload = {"tableSources": table_sources}
        return self._make_request("POST", endpoint, json_data=payload)
    
    def update_semantic_model_parameters(self, workspace_id: str, model_id: str, parameters: List[Dict]) -> Dict:
        """
        Update semantic model parameters (for parameterized queries)
        
        Args:
            workspace_id: Workspace GUID
            model_id: Semantic model GUID
            parameters: List of parameter updates:
              [
                {"name": "ServerName", "newValue": "prod-sql.database.windows.net"},
                {"name": "DatabaseName", "newValue": "ProdDB"}
              ]
        
        Returns:
            Update response
        """
        logger.info(f"Updating parameters for semantic model: {model_id}")
        endpoint = f"/workspaces/{workspace_id}/semanticModels/{model_id}/updateParameters"
        payload = {"updateDetails": parameters}
        return self._make_request("POST", endpoint, json_data=payload)
    
    def refresh_semantic_model(self, workspace_id: str, model_id: str, refresh_type: str = "full") -> Dict:
        """
        Trigger a refresh of a semantic model
        
        Args:
            workspace_id: Workspace GUID
            model_id: Semantic model GUID
            refresh_type: Type of refresh - "full" (default), "automatic", "dataOnly", "calculate", "clearValues"
            
        Returns:
            Refresh response with request ID
        """
        logger.info(f"Triggering {refresh_type} refresh for semantic model: {model_id}")
        endpoint = f"/workspaces/{workspace_id}/semanticModels/{model_id}/refreshes"
        payload = {"type": refresh_type}
        return self._make_request("POST", endpoint, json_data=payload)
    
    def get_semantic_model_datasources(self, workspace_id: str, model_id: str) -> List[Dict]:
        """
        Get data sources for a semantic model
        
        Args:
            workspace_id: Workspace GUID
            model_id: Semantic model GUID
            
        Returns:
            List of data source dictionaries
        """
        logger.info(f"Getting data sources for semantic model: {model_id}")
        endpoint = f"/workspaces/{workspace_id}/semanticModels/{model_id}/datasources"
        response = self._make_request("GET", endpoint)
        return response.get("value", [])
    
    def update_semantic_model_datasource(self, workspace_id: str, model_id: str, datasource_updates: List[Dict]) -> Dict:
        """
        Update data source credentials for a semantic model
        
        This uses the Power BI REST API to configure authentication for data sources.
        The semantic model must already exist before updating credentials.
        
        Args:
            workspace_id: Workspace GUID
            model_id: Semantic model GUID
            datasource_updates: List of update details with credentialDetails
            
        Returns:
            Update response
        """
        logger.info(f"Updating data source credentials for semantic model: {model_id}")
        endpoint = f"/workspaces/{workspace_id}/semanticModels/{model_id}/Default.UpdateDatasources"
        payload = {"updateDetails": datasource_updates}
        return self._make_request("POST", endpoint, json_data=payload)
    
    # ==================== Power BI Report Operations ====================
    
    def list_reports(self, workspace_id: str) -> List[Dict]:
        """
        List all Power BI reports in a workspace
        
        Args:
            workspace_id: Workspace GUID
            
        Returns:
            List of report dictionaries
        """
        logger.info(f"Listing reports in workspace: {workspace_id}")
        response = self._make_request("GET", f"/workspaces/{workspace_id}/reports")
        return response.get("value", [])
    
    def create_report(self, workspace_id: str, report_name: str, definition: Dict, folder_id: str = None) -> Dict:
        """
        Create a Power BI report
        
        Args:
            workspace_id: Workspace GUID
            report_name: Name for the report
            definition: Report definition
            folder_id: Optional workspace folder ID to place report in
            
        Returns:
            Created report details
        """
        logger.info(f"Creating Power BI report: {report_name}")
        payload = {
            "displayName": report_name,
            "definition": definition
        }
        if folder_id:
            payload["folderId"] = folder_id
        return self._make_request("POST", f"/workspaces/{workspace_id}/reports", json_data=payload)
    
    def update_report(self, workspace_id: str, report_id: str, definition: Dict) -> Dict:
        """
        Update Power BI report definition
        
        Args:
            workspace_id: Workspace GUID
            report_id: Report GUID
            definition: New report definition
            
        Returns:
            Update response
        """
        logger.info(f"Updating Power BI report: {report_id}")
        payload = {"definition": definition}
        return self._make_request("POST", f"/workspaces/{workspace_id}/reports/{report_id}/updateDefinition", json_data=payload)
    
    def rebind_report_dataset(self, workspace_id: str, report_id: str, dataset_id: str) -> Dict:
        """
        Rebind report to different dataset/semantic model
        
        This allows changing the data source of a report after deployment,
        similar to Fabric deployment pipeline rules.
        
        Args:
            workspace_id: Workspace GUID
            report_id: Report GUID
            dataset_id: New dataset/semantic model GUID
        
        Returns:
            Rebinding response
        """
        logger.info(f"Rebinding report {report_id} to dataset {dataset_id}")
        endpoint = f"/workspaces/{workspace_id}/reports/{report_id}/rebind"
        payload = {"datasetId": dataset_id}
        return self._make_request("POST", endpoint, json_data=payload)
    
    # ==================== Paginated Report Operations ====================
    
    def list_paginated_reports(self, workspace_id: str) -> List[Dict]:
        """
        List all paginated reports in a workspace
        
        
        Args:
            workspace_id: Workspace GUID
            
        Returns:
            List of paginated report dictionaries
        """
        logger.info(f"Listing paginated reports in workspace: {workspace_id}")
        response = self._make_request("GET", f"/workspaces/{workspace_id}/paginatedReports")
        return response.get("value", [])
    
    def create_paginated_report(self, workspace_id: str, report_name: str, definition: Dict, folder_id: str = None) -> Dict:
        """
        Create a paginated report using the Fabric Items API.
        
        According to Fabric documentation, paginated reports must be created in two steps:
        1. Create the item without definition (just displayName and type)
        2. Update the definition using updateDefinition API
        
        Args:
            workspace_id: Workspace GUID
            report_name: Name for the report
            definition: Report definition (.rdl file with parts structure)
            folder_id: Optional workspace folder ID
            
        Returns:
            Created report details
        """
        logger.info(f"Creating paginated report: {report_name}")
        
        # Step 1: Create the paginated report item without definition
        payload = {
            "displayName": report_name
        }
        
        # Include folder if specified
        if folder_id:
            payload["folderId"] = folder_id
            logger.info(f"  Creating in folder: {folder_id}")
        
        # Create the report item using Reports API
        response = self._make_request("POST", f"/workspaces/{workspace_id}/reports", json_data=payload)
        
        # Check if it's an LRO
        if response and 'operation_id' in response and response.get('status_code') == 202:
            operation_id = response['operation_id']
            retry_after = response.get('retry_after', 5)
            logger.info(f"  Paginated report creation initiated (LRO), waiting for completion...")
            
            # Poll the operation until it completes
            operation_result = self.wait_for_operation_completion(
                operation_id,
                retry_after=retry_after,
                max_attempts=10
            )
            
            # Get the report ID from the operation result
            if operation_result and 'id' in operation_result:
                report_id = operation_result['id']
                logger.info(f"  ✓ Created paginated report (ID: {report_id})")
            else:
                logger.warning(f"  ⚠ Paginated report created but ID not in operation result")
                report_id = 'unknown'
        elif response and 'id' in response:
            # Immediate response with ID
            report_id = response['id']
            logger.info(f"  ✓ Created paginated report (ID: {report_id})")
        else:
            raise Exception("Failed to get paginated report ID after creation")
        
        # Step 2: Update the definition if provided
        if definition and report_id != 'unknown':
            logger.info(f"  Updating paginated report definition...")
            try:
                self.update_paginated_report_definition(workspace_id, report_id, definition)
                logger.info(f"  ✓ Paginated report definition updated")
            except Exception as e:
                logger.warning(f"  ⚠ Failed to update definition: {e}")
        
        return {"id": report_id}
    
    def update_paginated_report_definition(self, workspace_id: str, report_id: str, definition: Dict) -> Dict:
        """
        Update paginated report definition using Items API
        
        Args:
            workspace_id: Workspace GUID
            report_id: Paginated report GUID
            definition: Report definition with parts structure
            
        Returns:
            Update response
        """
        logger.debug(f"Updating paginated report definition: {report_id}")
        payload = {"definition": definition}
        return self._make_request("POST", f"/workspaces/{workspace_id}/items/{report_id}/updateDefinition", json_data=payload)
    
    def update_paginated_report(self, workspace_id: str, report_id: str, definition: Dict) -> Dict:
        """
        Update paginated report definition
        
        Args:
            workspace_id: Workspace GUID
            report_id: Paginated report GUID
            definition: New report definition
            
        Returns:
            Update response
        """
        logger.info(f"Updating paginated report: {report_id}")
        payload = {"definition": definition}
        return self._make_request("POST", f"/workspaces/{workspace_id}/paginatedReports/{report_id}/updateDefinition", json_data=payload)
    
    def rebind_paginated_report_datasource(self, workspace_id: str, report_id: str, connection_details: Dict) -> Dict:
        """
        Rebind paginated report data source connection
        
        This allows updating connection strings or data source references after deployment,
        similar to Fabric deployment pipeline rules.
        
        Args:
            workspace_id: Workspace GUID
            report_id: Paginated report GUID
            connection_details: Connection configuration:
              {
                "connectionString": "Server=prod-sql.database.windows.net;...",
                "datasourceType": "sql"
              }
              or
              {
                "datasetId": "semantic-model-guid"
              }
        
        Returns:
            Rebinding response
        """
        logger.info(f"Rebinding data source for paginated report: {report_id}")
        endpoint = f"/workspaces/{workspace_id}/paginatedReports/{report_id}/rebindDatasource"
        return self._make_request("POST", endpoint, json_data=connection_details)
    
    def delete_paginated_report(self, workspace_id: str, report_id: str) -> Dict:
        """
        Delete a paginated report
        
        Args:
            workspace_id: Workspace GUID
            report_id: Paginated report GUID
            
        Returns:
            Delete response
        """
        logger.info(f"Deleting paginated report: {report_id}")
        endpoint = f"/workspaces/{workspace_id}/paginatedReports/{report_id}"
        return self._make_request("DELETE", endpoint)
    
    # ==================== Variable Library Operations ===================
    
    def list_variable_libraries(self, workspace_id: str) -> List[Dict]:
        """
        List Variable Libraries in workspace
        
        Args:
            workspace_id: Workspace GUID
            
        Returns:
            List of Variable Libraries
        """
        logger.info(f"Listing Variable Libraries in workspace: {workspace_id}")
        response = self._make_request("GET", f"/workspaces/{workspace_id}/items", params={"type": "VariableLibrary"})
        return response.get("value", [])
    
    def create_variable_library(self, workspace_id: str, name: str, description: str = "", folder_id: str = None, definition: Dict = None) -> Dict:
        """
        Create a Variable Library
        
        Args:
            workspace_id: Workspace GUID
            name: Variable Library name
            description: Variable Library description
            folder_id: Optional workspace folder ID to place library in
            definition: Optional public definition with initial variables
            
        Returns:
            Created Variable Library
        """
        logger.info(f"Creating Variable Library: {name}")
        payload = {
            "displayName": name,
            "type": "VariableLibrary",
            "description": description
        }
        if folder_id:
            payload["folderId"] = folder_id
            logger.info(f"  Including folderId in payload: {folder_id}")
        if definition:
            payload["definition"] = definition
            logger.info(f"  Including definition in payload (creating with initial variables)")
        return self._make_request("POST", f"/workspaces/{workspace_id}/items", json_data=payload)
    
    def get_variable_library(self, workspace_id: str, library_id: str) -> Dict:
        """
        Get Variable Library details
        
        Args:
            workspace_id: Workspace GUID
            library_id: Variable Library GUID
            
        Returns:
            Variable Library details
        """
        logger.info(f"Getting Variable Library: {library_id}")
        return self._make_request("GET", f"/workspaces/{workspace_id}/items/{library_id}")
    
    def get_variable_library_definition(self, workspace_id: str, library_id: str) -> Dict:
        """
        Get Variable Library definition (variables)
        Per Microsoft docs: POST /workspaces/{workspaceId}/VariableLibraries/{variableLibraryId}/getDefinition
        https://learn.microsoft.com/en-us/rest/api/fabric/variablelibrary/items/get-variable-library-definition
        
        Args:
            workspace_id: Workspace GUID
            library_id: Variable Library GUID
            
        Returns:
            Variable Library definition with variables
        """
        logger.info(f"Getting Variable Library definition: {library_id}")
        return self._make_request("POST", f"/workspaces/{workspace_id}/VariableLibraries/{library_id}/getDefinition")
    
    def update_variable_library_definition(self, workspace_id: str, library_id: str, definition: Dict) -> Dict:
        """
        Update Variable Library definition (variables)
        Per Microsoft docs: POST /workspaces/{workspaceId}/VariableLibraries/{variableLibraryId}/updateDefinition
        https://learn.microsoft.com/en-us/rest/api/fabric/variablelibrary/items/update-variable-library-definition
        
        Args:
            workspace_id: Workspace GUID
            library_id: Variable Library GUID
            definition: Variable Library definition with variables
            
        Returns:
            Update response
        """
        logger.info(f"Updating Variable Library definition: {library_id}")
        payload = {"definition": definition}
        return self._make_request("POST", f"/workspaces/{workspace_id}/VariableLibraries/{library_id}/updateDefinition", json_data=payload)
    
    def delete_variable_library(self, workspace_id: str, library_id: str) -> Dict:
        """
        Delete a Variable Library from a workspace
        Uses the specific Variable Library delete endpoint per Microsoft docs:
        https://learn.microsoft.com/en-us/rest/api/fabric/variablelibrary/items/delete-variable-library
        
        Args:
            workspace_id: Workspace GUID
            library_id: Variable Library GUID
            
        Returns:
            Deletion response
        """
        logger.info(f"Deleting Variable Library: {library_id}")
        return self._make_request("DELETE", f"/workspaces/{workspace_id}/VariableLibraries/{library_id}")
    
    def set_active_value_set(self, workspace_id: str, library_id: str, value_set_name: str) -> Dict:
        """
        Set the active value set for a Variable Library
        
        Args:
            workspace_id: Workspace GUID
            library_id: Variable Library GUID
            value_set_name: Name of the value set to activate (e.g., 'dev', 'uat', 'prod')
            
        Returns:
            Update response
        """
        logger.info(f"Setting active value set to '{value_set_name}' for Variable Library: {library_id}")
        payload = {
            "properties": {
                "activeValueSetName": value_set_name
            }
        }
        return self._make_request("PATCH", f"/workspaces/{workspace_id}/VariableLibraries/{library_id}", json_data=payload)
    
    # ==================== Lakehouse Definition Operations ====================
    
    def update_lakehouse_definition(self, workspace_id: str, lakehouse_id: str, parts: list, update_metadata: bool = True) -> dict:
        """Update lakehouse definition (includes shortcuts and other configuration)
        
        Args:
            workspace_id: The workspace ID
            lakehouse_id: The lakehouse ID
            parts: List of definition parts, each with path, payload (base64), and payloadType
            update_metadata: Whether to update metadata from .platform file
        
        Returns:
            Operation result or status
        """
        endpoint = f"/workspaces/{workspace_id}/lakehouses/{lakehouse_id}/updateDefinition"
        params = {"updateMetadata": "true" if update_metadata else "false"}
        
        payload = {
            "definition": {
                "format": "LakehouseDefinitionV1",
                "parts": parts
            }
        }
        
        logger.info(f"Updating lakehouse definition - workspace: {workspace_id}, lakehouse: {lakehouse_id}")
        logger.info(f"  Including {len(parts)} definition part(s)")
        
        result = self._make_request('POST', endpoint, json_data=payload, params=params)
        
        # _make_request returns a dict with status info for 202/204, or parsed JSON for 200
        if result.get('status_code') == 202:
            logger.info("Lakehouse definition update accepted (202) - LRO started")
            # The result already contains location, operation_id, retry_after from _make_request
            operation_id = result.get('operation_id')
            retry_after = result.get('retry_after', 30)
            
            if operation_id:
                logger.info(f"  Polling operation: {operation_id}")
                return self.wait_for_operation_completion(operation_id, retry_after, max_attempts=12)
        
        logger.info("Lakehouse definition updated successfully")
        return result
    
    def get_lakehouse_definition(self, workspace_id: str, lakehouse_id: str, format: str = "LakehouseDefinitionV1") -> dict:
        """Get lakehouse definition
        
        Args:
            workspace_id: The workspace ID
            lakehouse_id: The lakehouse ID
            format: Definition format (default: LakehouseDefinitionV1)
        
        Returns:
            Definition data with parts
        """
        endpoint = f"/workspaces/{workspace_id}/lakehouses/{lakehouse_id}/getDefinition"
        params = {"format": format}
        
        result = self._make_request('POST', endpoint, params=params)
        
        if result.get('status_code') == 202:
            logger.info("Get lakehouse definition - LRO started")
            operation_id = result.get('operation_id')
            retry_after = result.get('retry_after', 30)
            if operation_id:
                return self.wait_for_operation_completion(operation_id, retry_after, max_attempts=12)
        
        logger.info(f"Retrieved lakehouse definition: format={result.get('definition', {}).get('format')}")
        return result
    
    # ==================== Shortcut Operations ====================
    
    def list_shortcuts(self, workspace_id: str, lakehouse_id: str, path: str = "Tables") -> List[Dict]:
        """
        List shortcuts in a lakehouse path
        
        Args:
            workspace_id: Workspace GUID
            lakehouse_id: Lakehouse GUID
            path: Path within lakehouse (Tables or Files)
            
        Returns:
            List of shortcuts
        """
        logger.info(f"Listing shortcuts in lakehouse: {lakehouse_id}, path: {path}")
        response = self._make_request(
            "GET", 
            f"/workspaces/{workspace_id}/lakehouses/{lakehouse_id}/shortcuts",
            params={"path": path}
        )
        return response.get("value", [])
    
    def create_shortcut(self, workspace_id: str, lakehouse_id: str, shortcut_name: str, 
                       path: str, target: Dict) -> Dict:
        """
        Create a shortcut in a lakehouse
        
        Args:
            workspace_id: Workspace GUID
            lakehouse_id: Lakehouse GUID
            shortcut_name: Name for the shortcut
            path: Path within lakehouse (e.g., "Tables" or "Files")
            target: Target configuration with connection details
            
        Returns:
            Created shortcut details
            
        Example target for ADLS Gen2:
            {
                "adlsGen2": {
                    "location": "https://storageaccount.dfs.core.windows.net/container/path",
                    "connectionId": "connection-guid"
                }
            }
            
        Example target for OneLake:
            {
                "oneLake": {
                    "workspaceId": "source-workspace-guid",
                    "itemId": "source-lakehouse-guid",
                    "path": "Tables/SourceTable"
                }
            }
        """
        logger.info(f"Creating shortcut '{shortcut_name}' in lakehouse: {lakehouse_id}")
        payload = {
            "name": shortcut_name,
            "path": path,
            "target": target
        }
        return self._make_request(
            "POST",
            f"/workspaces/{workspace_id}/lakehouses/{lakehouse_id}/shortcuts",
            json_data=payload
        )
    
    def get_shortcut(self, workspace_id: str, lakehouse_id: str, path: str, 
                    shortcut_name: str) -> Dict:
        """
        Get shortcut details
        
        Args:
            workspace_id: Workspace GUID
            lakehouse_id: Lakehouse GUID
            path: Path within lakehouse
            shortcut_name: Name of the shortcut
            
        Returns:
            Shortcut details
        """
        logger.info(f"Getting shortcut: {shortcut_name}")
        return self._make_request(
            "GET",
            f"/workspaces/{workspace_id}/lakehouses/{lakehouse_id}/shortcuts/{path}/{shortcut_name}"
        )
    
    def delete_shortcut(self, workspace_id: str, lakehouse_id: str, path: str, 
                       shortcut_name: str) -> Dict:
        """
        Delete a shortcut
        
        Args:
            workspace_id: Workspace GUID
            lakehouse_id: Lakehouse GUID
            path: Path within lakehouse
            shortcut_name: Name of the shortcut
            
        Returns:
            Deletion response
        """
        logger.info(f"Deleting shortcut: {shortcut_name}")
        return self._make_request(
            "DELETE",
            f"/workspaces/{workspace_id}/lakehouses/{lakehouse_id}/shortcuts/{path}/{shortcut_name}"
        )
    
    # ==================== SQL Endpoint Operations ====================
    
    def get_lakehouse_sql_endpoint(self, workspace_id: str, lakehouse_id: str) -> str:
        """
        Get the SQL analytics endpoint connection string for a lakehouse
        
        Args:
            workspace_id: Workspace GUID
            lakehouse_id: Lakehouse GUID
            
        Returns:
            SQL endpoint connection string (server address)
        """
        logger.info(f"Getting SQL endpoint for lakehouse: {lakehouse_id}")
        lakehouse = self.get_lakehouse(workspace_id, lakehouse_id)
        
        # Extract properties for SQL endpoint
        properties = lakehouse.get("properties", {})
        sql_endpoint_props = properties.get("sqlEndpointProperties", {})
        
        if not sql_endpoint_props:
            logger.warning(f"Lakehouse {lakehouse_id} does not have sqlEndpointProperties, trying alternate method")
        
        # Try to get connection string from properties
        connection_string = sql_endpoint_props.get("connectionString")
        
        if connection_string:
            logger.info(f"Found SQL endpoint from properties: {connection_string}")
            return connection_string
        
        # Fallback: Use standard Fabric SQL endpoint format
        # Format: <guid>.datawarehouse.fabric.microsoft.com
        # The SQL endpoint ID is typically different from lakehouse ID
        sql_endpoint_id = sql_endpoint_props.get("id") if sql_endpoint_props else None
        
        if sql_endpoint_id:
            connection_string = f"{sql_endpoint_id}.datawarehouse.fabric.microsoft.com"
            logger.info(f"Constructed SQL endpoint from ID: {connection_string}")
            return connection_string
        
        # Last resort: Try to get SQL endpoint via list_items
        items = self.list_items(workspace_id, item_type="SQLEndpoint")
        lakehouse_name = lakehouse.get("displayName", "")
        
        # SQL endpoints are named same as lakehouse
        sql_endpoint = next((item for item in items if item.get("displayName") == lakehouse_name), None)
        
        if sql_endpoint:
            endpoint_id = sql_endpoint.get("id")
            connection_string = f"{endpoint_id}.datawarehouse.fabric.microsoft.com"
            logger.info(f"Found SQL endpoint via list: {connection_string}")
            return connection_string
        
        raise ValueError(f"Could not determine SQL endpoint for lakehouse {lakehouse_id} ({lakehouse_name})")
    
    def execute_sql_command(self, connection_string: str, database: str, sql_command: str) -> Optional[List[Dict]]:
        """
        Execute SQL command against lakehouse SQL endpoint
        Supports multiple statements separated by GO batch separator
        
        Args:
            connection_string: SQL endpoint connection string
            database: Database name (lakehouse name)
            sql_command: SQL command to execute (can contain multiple batches separated by GO)
            
        Returns:
            Query results as list of dictionaries (for SELECT), None for DDL commands
        """
        if not PYODBC_AVAILABLE:
            raise ImportError("pyodbc is required for SQL operations. Install with: pip install pyodbc")
        
        logger.info(f"Executing SQL command on {database}")
        
        # Get access token for Azure SQL Database (not Fabric API token)
        # SQL endpoints require https://database.windows.net/.default scope
        token = self.auth.get_sql_access_token()
        
        # Convert token to bytes for pyodbc
        token_bytes = token.encode('utf-16-le')
        token_struct = struct.pack(f'<I{len(token_bytes)}s', len(token_bytes), token_bytes)
        
        # Build connection string with AAD token
        conn_str = (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={connection_string};"
            f"DATABASE={database};"
            f"Encrypt=yes;"
            f"TrustServerCertificate=no;"
        )
        
        # Split by GO batch separator (case-insensitive, must be on its own line)
        import re
        batches = re.split(r'^\s*GO\s*$', sql_command, flags=re.MULTILINE | re.IGNORECASE)
        
        # Clean up batches - remove comments and empty lines
        cleaned_batches = []
        for batch in batches:
            # Remove single-line comments
            lines = []
            for line in batch.split('\n'):
                # Keep line if it's not a comment-only line
                stripped = line.strip()
                if stripped and not stripped.startswith('--'):
                    lines.append(line)
            cleaned = '\n'.join(lines).strip()
            if cleaned:
                cleaned_batches.append(cleaned)
        
        if not cleaned_batches:
            logger.warning("No SQL statements to execute after parsing")
            return None
        
        connection = None
        cursor = None
        results = None
        
        try:
            # Connect using AAD token
            connection = pyodbc.connect(conn_str, attrs_before={1256: token_struct})
            cursor = connection.cursor()
            
            # Execute each batch separately
            for i, batch in enumerate(cleaned_batches, 1):
                if len(cleaned_batches) > 1:
                    logger.info(f"  Executing batch {i}/{len(cleaned_batches)}")
                
                cursor.execute(batch)
                
                # Check if this is a SELECT query
                if batch.strip().upper().startswith("SELECT"):
                    columns = [column[0] for column in cursor.description]
                    batch_results = []
                    for row in cursor.fetchall():
                        batch_results.append(dict(zip(columns, row)))
                    results = batch_results  # Return last SELECT result
                else:
                    # DDL command (CREATE, ALTER, DROP)
                    connection.commit()
            
            return results
                
        except pyodbc.Error as e:
            logger.error(f"SQL execution error: {str(e)}")
            raise
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def check_view_exists(self, connection_string: str, database: str, schema: str, view_name: str) -> bool:
        """
        Check if a SQL view exists
        
        Args:
            connection_string: SQL endpoint connection string
            database: Database name
            schema: Schema name (typically 'dbo')
            view_name: View name
            
        Returns:
            True if view exists, False otherwise
        """
        query = f"""
        SELECT COUNT(*) as count
        FROM sys.views v
        JOIN sys.schemas s ON v.schema_id = s.schema_id
        WHERE s.name = '{schema}' AND v.name = '{view_name}'
        """
        
        result = self.execute_sql_command(connection_string, database, query)
        return result[0]['count'] > 0 if result else False
    
    def get_view_definition(self, connection_string: str, database: str, schema: str, view_name: str) -> Optional[str]:
        """
        Get the definition of an existing SQL view
        
        Args:
            connection_string: SQL endpoint connection string
            database: Database name
            schema: Schema name
            view_name: View name
            
        Returns:
            View definition SQL or None if not found
        """
        query = f"""
        SELECT m.definition
        FROM sys.views v
        JOIN sys.schemas s ON v.schema_id = s.schema_id
        JOIN sys.sql_modules m ON v.object_id = m.object_id
        WHERE s.name = '{schema}' AND v.name = '{view_name}'
        """
        
        result = self.execute_sql_command(connection_string, database, query)
        return result[0]['definition'] if result else None


def main():
    """Test Fabric client"""
    print("Testing Fabric Client...")
    
    # Authenticate
    auth = FabricAuthenticator()
    client = FabricClient(auth)
    
    # List workspaces
    workspaces = client.list_workspaces()
    print(f"\n✅ Found {len(workspaces)} workspaces:")
    for ws in workspaces:
        print(f"  - {ws.get('displayName')} (ID: {ws.get('id')})")


if __name__ == "__main__":
    main()
