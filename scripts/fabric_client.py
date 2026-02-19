"""
Microsoft Fabric REST API Client
Provides wrapper functions for common Fabric API operations
"""

import requests
import logging
import json
import re
import struct
import time
from typing import Dict, List, Optional, Any
from fabric_auth import FabricAuthenticator

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
        
        # Summarise updateDefinition payloads at DEBUG level (avoids dumping full base64)
        if "updateDefinition" in endpoint and json_data and method == "POST":
            definition = json_data.get("definition", {})
            parts = definition.get("parts", [])
            part_paths = [p.get("path", "?") for p in parts]
            logger.debug(f"updateDefinition {len(parts)} part(s): {part_paths} → {url}")

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
                        logger.debug(f"  LRO Location: {response.headers['Location']}")
                    
                    if "x-ms-operation-id" in response.headers:
                        result["operation_id"] = response.headers["x-ms-operation-id"]
                        logger.debug(f"  LRO Operation ID: {response.headers['x-ms-operation-id']}")
                    
                    if "Retry-After" in response.headers:
                        result["retry_after"] = int(response.headers["Retry-After"])
                        logger.debug(f"  Retry-After: {response.headers['Retry-After']}s")
                
                # Try to parse response body if present
                if response.text:
                    try:
                        body = response.json()
                        result.update(body)
                    except:
                        pass
                
                return result
            
            # Handle 200 with empty body (e.g. bindConnection returns 200 with no content)
            if not response.text or not response.text.strip():
                return {"status": "success", "status_code": response.status_code}
            
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
        logger.debug(f"  Polling operation {operation_id} (retry every {retry_after}s, max {max_attempts} attempts)")
        
        for attempt in range(1, max_attempts + 1):
            time.sleep(retry_after)
            
            state = self.poll_operation_state(operation_id)
            status = state.get("status")
            percent = state.get("percentComplete", 0)
            
            logger.info(f"    Attempt {attempt}/{max_attempts}: {status} ({percent}% complete)")
            
            # Log full state response for debugging
            if status == "Failed":
                logger.debug(f"    Full LRO state: {json.dumps(state, indent=2)}")
            
            if status == "Succeeded":
                logger.info(f"  ✓ Operation completed successfully")
                # Try to get the actual result.
                # Note: updateDefinition operations do NOT produce a result resource —
                # only create operations do. The API returns 400 OperationHasNoResult
                # for updates. We handle this gracefully since the operation itself succeeded.
                try:
                    result = self.get_operation_result(operation_id)
                    return result
                except requests.exceptions.HTTPError as e:
                    if e.response is not None and e.response.status_code == 400:
                        resp_body = {}
                        try:
                            resp_body = e.response.json()
                        except Exception:
                            pass
                        error_code = resp_body.get("errorCode", "")
                        if error_code == "OperationHasNoResult":
                            logger.info(f"  ℹ Operation has no result (expected for update operations)")
                            return {}
                    # Re-raise if it's a different 400 error or non-400
                    raise
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
        
        Uses Fabric REST API: POST /v1/workspaces/{workspaceId}/items/{itemId}/move
        See: https://learn.microsoft.com/en-us/rest/api/fabric/core/items/move-item
        
        Args:
            workspace_id: Workspace GUID
            item_id: Item GUID to move
            folder_id: Target folder GUID
        """
        logger.debug(f"  Moving item {item_id} to folder {folder_id}")
        payload = {"targetFolderId": folder_id}
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
        Trigger a refresh of a semantic model.

        Uses the Power BI REST API — NOT the Fabric v1 API — because the
        refresh endpoint only exists on the Power BI side:
            POST https://api.powerbi.com/v1.0/myorg/groups/{groupId}/datasets/{datasetId}/refreshes

        Args:
            workspace_id: Workspace GUID (used as the Power BI group ID)
            model_id: Semantic model GUID
            refresh_type: Type of refresh — "Full" (default), "Automatic",
                          "DataOnly", "Calculate", "ClearValues"

        Returns:
            Dict with status_code 202 on success, or raises on HTTP error
        """
        logger.info(f"Triggering {refresh_type} refresh for semantic model: {model_id}")
        url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/datasets/{model_id}/refreshes"
        headers = self.auth.get_auth_headers()
        payload = {
            "type": refresh_type.capitalize(),
            "notifyOption": "NoNotification"
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            if response.status_code == 202:
                logger.info(f"  ✓ Refresh queued (202 Accepted)")
                return {"status": "success", "status_code": 202}
            else:
                response.raise_for_status()
                return {"status": "success", "status_code": response.status_code}
        except requests.exceptions.HTTPError as e:
            logger.error(f"  HTTP Error triggering refresh: {e.response.status_code} - {e.response.text}")
            raise
    
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
    
    def take_over_dataset(self, workspace_id: str, dataset_id: str) -> bool:
        """
        Take over ownership of a semantic model (dataset) so the service principal
        can manage its connections and credentials.
        
        Uses Power BI REST API: POST /groups/{groupId}/datasets/{datasetId}/Default.TakeOver
        
        This is required before the SP can bind connections or update data source
        credentials on a semantic model it didn't originally create.
        
        Args:
            workspace_id: Workspace GUID
            dataset_id: Semantic model / dataset GUID
            
        Returns:
            True if take-over succeeded, False otherwise
        """
        logger.info(f"Taking over ownership of semantic model {dataset_id}")
        
        url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/datasets/{dataset_id}/Default.TakeOver"
        headers = self.auth.get_auth_headers()
        
        try:
            response = requests.post(url, headers=headers, timeout=60)
            if response.status_code == 200:
                logger.info(f"  ✓ Successfully took over ownership of semantic model {dataset_id}")
                return True
            else:
                logger.warning(f"  ⚠ TakeOver returned {response.status_code}: {response.text}")
                return False
        except Exception as e:
            logger.warning(f"  ⚠ TakeOver failed: {e}")
            return False
    
    def list_item_connections(self, workspace_id: str, item_id: str) -> List[Dict]:
        """
        List the connections that a workspace item is connected to.
        
        Uses Fabric REST API: GET /v1/workspaces/{workspaceId}/items/{itemId}/connections
        
        See: https://learn.microsoft.com/en-us/rest/api/fabric/core/items/list-item-connections
        
        Args:
            workspace_id: Workspace GUID
            item_id: Item GUID (semantic model, report, etc.)
            
        Returns:
            List of connection dicts with connectivityType, connectionDetails, id, etc.
        """
        logger.info(f"  Listing connections for item {item_id}")
        response = self._make_request("GET", f"/workspaces/{workspace_id}/items/{item_id}/connections")
        return response.get("value", [])
    
    def bind_semantic_model_to_connection(self, workspace_id: str, semantic_model_id: str, connection_id: str) -> Dict:
        """
        Bind a semantic model to a Fabric shareable cloud connection using the
        official Fabric Semantic Model bindConnection API.
        
        Endpoint: POST /v1/workspaces/{workspaceId}/semanticModels/{semanticModelId}/bindConnection
        
        See: https://learn.microsoft.com/en-us/rest/api/fabric/semanticmodel/items/bind-semantic-model-connection
        
        Prerequisite: The caller must be the owner of the semantic model.
        Use take_over_dataset() first to transfer ownership to the SP.
        
        This API does not support bulk operations — to bind multiple data source
        references, submit multiple bindConnection requests (one per data source).
        
        Args:
            workspace_id: Workspace GUID
            semantic_model_id: Semantic model GUID
            connection_id: Fabric connection GUID (from GET /v1/connections)
            
        Returns:
            Dict with status "bound" and details on success, empty dict on failure
        """
        logger.info(f"Binding semantic model to Fabric connection")
        
        # Step 1: Take over ownership so the SP can manage connections
        self.take_over_dataset(workspace_id, semantic_model_id)
        
        # Step 2: List current item connections to get the connectionDetails (type + path)
        # that need to be matched in the bindConnection request
        try:
            item_connections = self.list_item_connections(workspace_id, semantic_model_id)
            logger.info(f"  Found {len(item_connections)} existing connection reference(s) on semantic model")
            for idx, conn in enumerate(item_connections):
                conn_type = conn.get("connectivityType", "unknown")
                conn_details = conn.get("connectionDetails", {})
                logger.debug(f"    [{idx+1}] type={conn_type}, path={conn_details.get('path', 'N/A')}, connType={conn_details.get('type', 'N/A')}, id={conn.get('id', 'none')}")
        except Exception as e:
            logger.warning(f"  ⚠ Could not list item connections: {e}")
            item_connections = []
        
        # Step 3: Bind each data source reference to the target ShareableCloud connection
        # using the Fabric Semantic Model bindConnection API
        bound_count = 0
        bind_endpoint = f"/workspaces/{workspace_id}/semanticModels/{semantic_model_id}/bindConnection"
        
        if item_connections:
            for conn in item_connections:
                conn_details = conn.get("connectionDetails", {})
                conn_type_detail = conn_details.get("type", "")
                conn_path = conn_details.get("path", "")
                current_connectivity = conn.get("connectivityType", "")
                
                # Skip if already bound to the target ShareableCloud connection
                if current_connectivity == "ShareableCloud" and conn.get("id") == connection_id:
                    logger.info(f"  ✓ Already bound to target connection (path={conn_path})")
                    bound_count += 1
                    continue
                
                # Build the bindConnection payload
                payload = {
                    "connectionBinding": {
                        "id": connection_id,
                        "connectivityType": "ShareableCloud",
                        "connectionDetails": {
                            "type": conn_type_detail,
                            "path": conn_path
                        }
                    }
                }
                
                logger.debug(f"  Binding data source (type={conn_type_detail}, path={conn_path})")
                try:
                    result = self._make_request("POST", bind_endpoint, json_data=payload)
                    logger.info(f"  ✓ Successfully bound data source to ShareableCloud connection")
                    bound_count += 1
                except Exception as bind_err:
                    logger.warning(f"  ⚠ bindConnection failed: {bind_err}")
                    logger.debug(f"    Payload: {json.dumps(payload, indent=2)}")
        else:
            # No existing connections found — the semantic model may not have been
            # refreshed yet. Try binding with the connection details from config.
            logger.info(f"  No existing connections on semantic model — attempting direct bind")
            logger.info(f"  The semantic model may need a refresh first to establish data source references")
        
        if bound_count > 0:
            logger.info(f"  ✓ Bound {bound_count} data source(s) to Fabric connection")
            return {"status": "bound", "bound_count": bound_count}
        
        return {}
    
    def bind_paginated_report_to_connection(self, workspace_id: str, report_id: str, connection_id: str) -> Dict:
        """
        Bind a paginated report to a Fabric ShareableCloud connection.
        
        Unlike semantic models, there is no dedicated ``bindConnection`` API for
        paginated reports.  The approach here is:
        
        1. TakeOver — SP becomes the data-source owner.
        2. Get Datasources — retrieve the gatewayId + datasourceId that Fabric
           created when the report was imported.
        3. Update Datasource (via the Gateways API) — set OAuth2 credentials
           with ``useCallerAADIdentity=true`` so the SP's identity flows through
           the target ShareableCloud connection.
        
        If a ``paginated_report_connection`` is configured, the method also
        updates the connection details (server/database) via UpdateDatasources
        so the paginated report points to the same endpoint as the shareable
        connection.
        
        Prerequisite: The target ShareableCloud connection must already exist
        in Fabric (created manually in the portal).  The SP must have access
        to the connection.
        
        Args:
            workspace_id: Workspace GUID
            report_id: Paginated report GUID (Power BI report ID)
            connection_id: Fabric connection GUID (from GET /v1/connections)
            
        Returns:
            Dict with status info on success, empty dict on failure
        """
        logger.info(f"Binding paginated report to Fabric connection")
        
        # Step 1: List item connections via Fabric Items API (generic, works for any item)
        try:
            item_connections = self.list_item_connections(workspace_id, report_id)
            logger.info(f"  Found {len(item_connections)} connection reference(s) on paginated report")
            for idx, conn in enumerate(item_connections):
                conn_type = conn.get("connectivityType", "unknown")
                conn_details = conn.get("connectionDetails", {})
                logger.debug(f"    [{idx+1}] type={conn_type}, path={conn_details.get('path', 'N/A')}, connType={conn_details.get('type', 'N/A')}, id={conn.get('id', 'none')}")
            
            # Check if already bound to the target ShareableCloud connection
            already_bound = any(
                c.get("connectivityType") == "ShareableCloud" and c.get("id") == connection_id
                for c in item_connections
            )
            if already_bound:
                logger.info(f"  ✓ Paginated report already bound to target ShareableCloud connection")
                return {"status": "already_bound"}
        except Exception as e:
            logger.warning(f"  ⚠ Could not list item connections: {e}")
            item_connections = []
        
        # Step 2: TakeOver — SP becomes data-source owner
        self.take_over_paginated_report(workspace_id, report_id)
        
        # Step 3: Get datasources via Power BI API to obtain gatewayId + datasourceId
        try:
            datasources = self.get_paginated_report_datasources(workspace_id, report_id)
            logger.info(f"  Found {len(datasources)} data source(s) on paginated report")
            for idx, ds in enumerate(datasources):
                ds_type = ds.get("datasourceType", "unknown")
                ds_conn = ds.get("connectionDetails", {})
                logger.debug(f"    [{idx+1}] type={ds_type}, server={ds_conn.get('server', 'N/A')}, database={ds_conn.get('database', 'N/A')}, gatewayId={ds.get('gatewayId', 'none')}, datasourceId={ds.get('datasourceId', 'none')}")
        except Exception as e:
            logger.warning(f"  ⚠ Could not get paginated report datasources: {e}")
            return {}
        
        # Step 4: For each datasource with a gatewayId, update credentials using
        # the Gateways Update Datasource API with useCallerAADIdentity=true.
        # This makes the SP's OAuth token flow through so the ShareableCloud
        # connection can authenticate.
        bound_count = 0
        for ds in datasources:
            gw_id = ds.get("gatewayId")
            ds_id = ds.get("datasourceId")
            if not gw_id or not ds_id:
                logger.info(f"  ℹ Datasource has no gatewayId/datasourceId — skipping credential update")
                continue
            
            logger.debug(f"  Updating datasource credentials (gatewayId={gw_id}, datasourceId={ds_id}) with OAuth2 + CallerAADIdentity...")
            success = self.update_gateway_datasource_credentials(gw_id, ds_id, use_caller_identity=True)
            if success:
                bound_count += 1
        
        if bound_count > 0:
            return {"status": "bound", "bound_count": bound_count}
        
        return {}
    
    # ==================== Connection Operations ====================
    
    def list_connections(self) -> List[Dict]:
        """
        List all connections (tenant-scoped Fabric Connections API).
        Endpoint: GET /v1/connections
        
        Handles pagination via continuationToken/continuationUri.
        
        Returns:
            List of connection dictionaries
        """
        logger.info(f"Listing connections via Fabric Connections API")
        all_connections = []
        endpoint = "/connections"
        
        while endpoint:
            response = self._make_request("GET", endpoint)
            connections = response.get("value", [])
            all_connections.extend(connections)
            
            # Handle pagination
            continuation_uri = response.get("continuationUri")
            continuation_token = response.get("continuationToken")
            
            if continuation_uri:
                # continuationUri is a full URL — extract the path after base URL
                if continuation_uri.startswith(self.BASE_URL):
                    endpoint = continuation_uri[len(self.BASE_URL):]
                else:
                    endpoint = continuation_uri
            elif continuation_token:
                endpoint = f"/connections?continuationToken={continuation_token}"
            else:
                endpoint = None
        
        logger.info(f"  Retrieved {len(all_connections)} connections total")
        return all_connections
    
    def get_connection(self, connection_id: str) -> Dict:
        """
        Get connection details (tenant-scoped Fabric Connections API).
        Endpoint: GET /v1/connections/{connectionId}
        
        Args:
            connection_id: Connection GUID
            
        Returns:
            Connection details dictionary
        """
        logger.info(f"Getting connection: {connection_id}")
        return self._make_request("GET", f"/connections/{connection_id}")
    
    def create_connection(self, connection_payload: Dict) -> Dict:
        """
        Create a new connection using Fabric Connections API (tenant-scoped).
        Endpoint: POST /v1/connections
        
        See: https://learn.microsoft.com/en-us/rest/api/fabric/core/connections/create-connection
        
        Args:
            connection_payload: Connection configuration with:
                - connectivityType: "ShareableCloud" for cloud connections
                - displayName: Connection name
                - connectionDetails: {type, parameters: {server, database}}
                - privacyLevel: "Organizational", "Private", "Public", or "None"
                - credentialDetails: {singleSignOnType, connectionEncryption, skipTestConnection, credentials}
                
        Returns:
            Created connection details with connection ID
        """
        connection_name = connection_payload.get('displayName', 'Unknown')
        logger.info(f"Creating Fabric connection: {connection_name}")
        return self._make_request("POST", "/connections", json_data=connection_payload)
    
    # ==================== Git Integration Operations ====================

    def get_git_connection(self, workspace_id: str) -> Dict:
        """
        Get the Git connection details for a workspace.
        
        Endpoint: GET /v1/workspaces/{workspaceId}/git/connection
        
        Returns the Git provider details (org, project, repo, branch),
        sync details, and connection state.
        
        See: https://learn.microsoft.com/en-us/rest/api/fabric/core/git/get-connection
        """
        logger.info(f"Getting Git connection for workspace {workspace_id}")
        return self._make_request("GET", f"/workspaces/{workspace_id}/git/connection")

    def create_ado_git_connection(self, repo_url: str, display_name: str,
                                  client_id: str, tenant_id: str, client_secret: str) -> Dict:
        """
        Create an Azure DevOps Source Control connection for Git integration.
        
        This creates a ShareableCloud connection of type AzureDevOpsSourceControl
        using the SP's credentials, which can then be used with Update My Git
        Credentials to enable Git operations for the SP.
        
        Endpoint: POST /v1/connections
        
        See: https://learn.microsoft.com/en-us/fabric/cicd/git-integration/git-automation#create-a-new-connection-that-stores-your-git-credentials
        
        Args:
            repo_url: Azure DevOps repo URL (e.g., https://dev.azure.com/org/project/_git/repo)
            display_name: Display name for the connection
            client_id: Service principal application (client) ID
            tenant_id: Service principal tenant (directory) ID
            client_secret: Service principal secret
            
        Returns:
            Created connection with 'id'
        """
        logger.info(f"Creating Azure DevOps Git connection: '{display_name}'")
        
        payload = {
            "connectivityType": "ShareableCloud",
            "displayName": display_name,
            "connectionDetails": {
                "type": "AzureDevOpsSourceControl",
                "creationMethod": "AzureDevOpsSourceControl.Contents",
                "parameters": [
                    {
                        "dataType": "Text",
                        "name": "url",
                        "value": repo_url
                    }
                ]
            },
            "credentialDetails": {
                "credentials": {
                    "credentialType": "ServicePrincipal",
                    "tenantId": tenant_id,
                    "servicePrincipalClientId": client_id,
                    "servicePrincipalSecret": client_secret
                }
            }
        }
        
        return self.create_connection(payload)

    def update_paginated_report_datasources(self, workspace_id: str, report_id: str,
                                             update_details: List[Dict]) -> bool:
        """
        Update data sources of a paginated report (RDL).
        
        Endpoint: POST /v1.0/myorg/groups/{groupId}/reports/{reportId}/Default.UpdateDatasources
        
        Changes the server/database for named data sources in the paginated report.
        The caller must be the data source owner (call TakeOver first).
        
        Limitations:
          - Only supports paginated reports
          - Cannot change data source type
          - ODBC sources not supported
          - Both original and new data source must have the same schema
        
        See: https://learn.microsoft.com/en-us/rest/api/power-bi/reports/update-datasources-in-group
        
        Args:
            workspace_id: Workspace GUID
            report_id: Paginated report GUID
            update_details: List of dicts with:
                - datasourceName: Name of the data source in the RDL
                - connectionDetails: {server, database}
            
        Returns:
            True on success, False on failure
        """
        logger.info(f"Updating data sources for paginated report: {report_id}")
        
        url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/reports/{report_id}/Default.UpdateDatasources"
        headers = self.auth.get_auth_headers()
        
        payload = {"updateDetails": update_details}
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            logger.info(f"  ✓ Updated {len(update_details)} data source(s) via UpdateDatasources API")
            return True
        except requests.exceptions.HTTPError as e:
            logger.warning(f"  ⚠ UpdateDatasources failed: {e.response.status_code} - {e.response.text}")
            return False
        except Exception as e:
            logger.warning(f"  ⚠ UpdateDatasources error: {e}")
            return False

    def get_git_credentials(self, workspace_id: str) -> Dict:
        """
        Get the current user's (or SP's) Git credentials configuration.
        
        Endpoint: GET /v1/workspaces/{workspaceId}/git/myGitCredentials
        
        Returns the credential source: "Automatic", "ConfiguredConnection", or "None".
        
        See: https://learn.microsoft.com/en-us/rest/api/fabric/core/git/get-my-git-credentials
        """
        logger.info(f"Getting Git credentials for workspace {workspace_id}")
        return self._make_request("GET", f"/workspaces/{workspace_id}/git/myGitCredentials")

    def update_git_credentials(self, workspace_id: str, source: str, connection_id: str = None) -> Dict:
        """
        Update the user's (or SP's) Git credentials configuration.
        
        Endpoint: PATCH /v1/workspaces/{workspaceId}/git/myGitCredentials
        
        For Service Principals, only "ConfiguredConnection" or "None" are supported.
        "Automatic" is blocked for SPs.
        
        See: https://learn.microsoft.com/en-us/rest/api/fabric/core/git/update-my-git-credentials
        
        Args:
            workspace_id: Workspace GUID
            source: "Automatic", "ConfiguredConnection", or "None"
            connection_id: Required when source is "ConfiguredConnection"
            
        Returns:
            Updated credentials configuration
        """
        logger.info(f"Updating Git credentials for workspace {workspace_id} (source: {source})")
        
        payload = {"source": source}
        if source == "ConfiguredConnection" and connection_id:
            payload["connectionId"] = connection_id
        
        url = f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/git/myGitCredentials"
        headers = self.auth.get_auth_headers()
        
        try:
            response = requests.patch(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()
            logger.info(f"  ✓ Git credentials updated: source={result.get('source')}")
            return result
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP Error updating Git credentials: {e.response.status_code} - {e.response.text}")
            raise

    def get_git_status(self, workspace_id: str) -> Dict:
        """
        Get the Git sync status of a workspace.
        Endpoint: GET /v1/workspaces/{workspaceId}/git/status
        
        Returns the current workspace head, remote commit hash, and a list
        of changes between the workspace and the connected Git branch.
        
        This may be a long-running operation (LRO) returning 202.
        
        See: https://learn.microsoft.com/en-us/rest/api/fabric/core/git/get-status
        
        Args:
            workspace_id: Workspace GUID
            
        Returns:
            GitStatusResponse with workspaceHead, remoteCommitHash, and changes[]
        """
        logger.info(f"Getting Git status for workspace {workspace_id}")
        response = self._make_request("GET", f"/workspaces/{workspace_id}/git/status")
        
        # If it's an LRO (202), poll for completion
        if response.get("status_code") == 202 and response.get("operation_id"):
            operation_id = response["operation_id"]
            retry_after = response.get("retry_after", 5)
            logger.info(f"  Git status is a long-running operation, polling...")
            result = self.wait_for_operation_completion(operation_id, retry_after=retry_after, max_attempts=12)
            return result
        
        return response
    
    def update_from_git(self, workspace_id: str, remote_commit_hash: str, 
                        workspace_head: str = None, 
                        conflict_resolution_policy: str = "PreferRemote",
                        allow_override_items: bool = True) -> Dict:
        """
        Update the workspace with commits pushed to the connected Git branch.
        Endpoint: POST /v1/workspaces/{workspaceId}/git/updateFromGit
        
        This is a long-running operation (LRO).
        
        See: https://learn.microsoft.com/en-us/rest/api/fabric/core/git/update-from-git
        
        Args:
            workspace_id: Workspace GUID
            remote_commit_hash: Full SHA of the remote commit to update to
            workspace_head: Full SHA the workspace is currently synced to (optional)
            conflict_resolution_policy: "PreferRemote" or "PreferWorkspace"
            allow_override_items: Whether to allow overriding incoming items
            
        Returns:
            Operation result or success status
        """
        logger.info(f"Updating workspace {workspace_id} from Git (commit: {remote_commit_hash[:12]}...)")
        
        payload = {
            "remoteCommitHash": remote_commit_hash,
            "conflictResolution": {
                "conflictResolutionType": "Workspace",
                "conflictResolutionPolicy": conflict_resolution_policy
            },
            "options": {
                "allowOverrideItems": allow_override_items
            }
        }
        
        if workspace_head:
            payload["workspaceHead"] = workspace_head
        
        response = self._make_request("POST", f"/workspaces/{workspace_id}/git/updateFromGit", json_data=payload)
        
        # Handle LRO (202 Accepted)
        if response.get("status_code") == 202 and response.get("operation_id"):
            operation_id = response["operation_id"]
            retry_after = response.get("retry_after", 30)
            logger.info(f"  Update from Git in progress (operation: {operation_id}), polling...")
            
            # Poll until completion — updateFromGit has no result body, just status
            for attempt in range(1, 25):  # Up to ~12 minutes with 30s intervals
                time.sleep(retry_after)
                state = self.poll_operation_state(operation_id)
                status = state.get("status")
                percent = state.get("percentComplete", 0)
                logger.info(f"    Poll {attempt}: {status} ({percent}% complete)")
                
                if status == "Succeeded":
                    logger.info(f"  ✓ Update from Git completed successfully")
                    return {"status": "success", "operation_id": operation_id}
                elif status == "Failed":
                    error = state.get("error", {})
                    error_msg = error.get("message", "Unknown error")
                    logger.error(f"  ✗ Update from Git failed: {error_msg}")
                    raise RuntimeError(f"Update from Git failed: {error_msg}")
            
            raise RuntimeError(f"Update from Git timed out after polling")
        
        # 200 = completed immediately
        logger.info(f"  ✓ Update from Git completed")
        return response
    
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
    
    def update_paginated_report(self, workspace_id: str, report_id: str, definition: Dict) -> Dict:
        """
        Update paginated report definition via Fabric Items API.
        
        Uses POST /workspaces/{id}/paginatedReports/{id}/updateDefinition.
        
        NOTE: As of 2026-02, this endpoint returns OperationNotSupportedForItem
        for paginated reports. Use import_paginated_report() with overwrite=True
        instead to update existing paginated reports.
        
        Args:
            workspace_id: Workspace GUID
            report_id: Paginated report GUID
            definition: Definition dict with 'parts' list
            
        Returns:
            Update response
        """
        logger.info(f"Updating paginated report: {report_id}")
        payload = {"definition": definition}
        return self._make_request("POST", f"/workspaces/{workspace_id}/paginatedReports/{report_id}/updateDefinition", json_data=payload)

    def create_paginated_report(self, workspace_id: str, report_name: str, definition: Dict = None, folder_id: str = None) -> Dict:
        """
        Create a paginated report via the Fabric Items API.
        
        Uses POST /workspaces/{id}/items with type=PaginatedReport (the generic
        Items endpoint). The dedicated /paginatedReports endpoint does not exist
        and returns UnsupportedItemType.
        
        If definition is provided, creates the report with the RDL definition
        included. Otherwise creates a shell item — use update_paginated_report()
        afterwards to upload the RDL definition.
        
        Args:
            workspace_id: Workspace GUID
            report_name: Display name for the paginated report
            definition: Optional definition dict with base64-encoded parts
            folder_id: Optional workspace folder ID
            
        Returns:
            Created item details (may include operation_id for LRO)
        """
        logger.info(f"Creating paginated report: {report_name}")
        payload = {
            "displayName": report_name,
            "type": "PaginatedReport",
        }
        if definition:
            payload["definition"] = definition
        if folder_id:
            payload["folderId"] = folder_id
        return self._make_request("POST", f"/workspaces/{workspace_id}/items", json_data=payload)

    def import_paginated_report(self, workspace_id: str, report_name: str, rdl_content: str, max_retries: int = 3, overwrite: bool = False) -> Dict:
        """
        Import a paginated report using the Power BI Imports API.
        
        This is the primary method for deploying paginated reports because the
        Fabric Items API does not support create or updateDefinition for
        PaginatedReport items (returns UnsupportedItemType / OperationNotSupportedForItem).
        
        For RDL files the supported nameConflict values are:
          - Abort: Fail if a report with the same name exists (use for new reports)
          - Overwrite: Overwrite existing report (use when report already exists)
        CreateOrOverwrite is NOT supported for RDL.
        
        The datasetDisplayName MUST include the .rdl extension so the API
        recognises the upload as a paginated report. Without it, the API
        treats it as a .pbix and returns RequestedFileIsEncryptedOrCorrupted.
        
        When used after delete_paginated_report(), includes retry logic to
        handle the case where the deletion hasn't fully propagated yet.
        
        Args:
            workspace_id: Workspace GUID
            report_name: Name for the report (without .rdl extension)
            rdl_content: The RDL XML content as a string
            max_retries: Maximum retries if import fails due to conflict (default 3)
            overwrite: If True use nameConflict=Overwrite, else Abort (default False)
            
        Returns:
            Dict with 'id' and 'name' of the imported report
        """
        
        logger.info(f"Importing paginated report: {report_name}")
        
        # The Power BI Imports API requires the .rdl extension in BOTH the
        # datasetDisplayName parameter AND the multipart file name.
        # Without .rdl in datasetDisplayName, the API doesn't recognise the
        # upload as a paginated report and returns RequestedFileIsEncryptedOrCorrupted.
        # See: https://learn.microsoft.com/en-us/rest/api/power-bi/imports/post-import-in-group
        file_name = f"{report_name}.rdl"
        display_name = f"{report_name}.rdl"
        
        # Build the URL using Power BI API  
        url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/imports"
        # For RDL files: Abort = fail if exists, Overwrite = replace existing
        # Using Overwrite on a report that doesn't exist causes DuplicatePackageNotFoundError
        conflict_mode = "Overwrite" if overwrite else "Abort"
        params = {
            "datasetDisplayName": display_name,
            "nameConflict": conflict_mode
        }
        
        # Strip UTF-8 BOM if present - the BOM (\ufeff) causes the Power BI
        # Imports API to return RequestedFileIsEncryptedOrCorrupted
        if rdl_content.startswith('\ufeff'):
            rdl_content = rdl_content[1:]
            logger.info(f"  Stripped UTF-8 BOM from RDL content")
        
        rdl_bytes = rdl_content.encode('utf-8')
        
        logger.info(f"  Uploading RDL file ({len(rdl_bytes)} bytes) as '{file_name}'")
        logger.info(f"  datasetDisplayName='{display_name}', nameConflict={conflict_mode}")
        
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                headers = self.auth.get_auth_headers()
                # Remove Content-Type - requests will set it with the boundary for multipart
                headers.pop("Content-Type", None)
                
                files = {
                    'file': (file_name, rdl_bytes, 'application/xml')
                }
                
                response = requests.post(
                    url, headers=headers, params=params,
                    files=files, timeout=120
                )
                response.raise_for_status()
                
                result = response.json()
                import_id = result.get("id")
                import_state = result.get("importState", "Unknown")
                
                logger.info(f"  Import initiated (ID: {import_id}, State: {import_state})")
                
                # If import is not yet complete, poll for completion
                if response.status_code == 202 or import_state not in ["Succeeded", "Failed"]:
                    result = self._poll_import_completion(workspace_id, import_id)
                
                # Extract report ID from the import result
                reports = result.get("reports", [])
                if reports:
                    report_id = reports[0].get("id", "unknown")
                    report_name_result = reports[0].get("name", report_name)
                    logger.info(f"  ✓ Paginated report imported successfully (ID: {report_id}, Name: {report_name_result})")
                    return {"id": report_id, "name": report_name_result}
                else:
                    logger.warning(f"  ⚠ Import completed but no reports in result: {json.dumps(result, indent=2)}")
                    return {"id": "unknown"}
                    
            except requests.exceptions.HTTPError as e:
                last_error = e
                status_code = e.response.status_code if e.response is not None else 0
                error_text = e.response.text if e.response is not None else str(e)
                
                logger.warning(f"  ⚠ Import attempt {attempt}/{max_retries} failed: {status_code} - {error_text}")
                try:
                    error_detail = e.response.json()
                    logger.warning(f"  Error details: {json.dumps(error_detail, indent=2)}")
                except:
                    pass
                
                # Retry on 409 Conflict (name still in use after delete),
                # 404 (delete not yet propagated), or 429 (rate limit)
                if status_code in [404, 409, 429] and attempt < max_retries:
                    wait_time = 5 * attempt  # Progressive backoff: 5s, 10s, 15s
                    logger.info(f"  Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                
                # Non-retryable error or max retries exceeded
                logger.error(f"HTTP Error importing paginated report: {status_code} - {error_text}")
                raise
            except Exception as e:
                logger.error(f"Failed to import paginated report: {str(e)}")
                raise
        
        # Should not reach here, but just in case
        raise last_error or RuntimeError(f"Failed to import paginated report '{report_name}' after {max_retries} attempts")
    
    def _poll_import_completion(self, workspace_id: str, import_id: str, max_attempts: int = 30, retry_after: int = 5) -> Dict:
        """
        Poll the Power BI Imports API for import completion.
        
        Args:
            workspace_id: Workspace GUID
            import_id: The import ID to poll
            max_attempts: Maximum number of polling attempts
            retry_after: Seconds to wait between polls
            
        Returns:
            The completed import result
        """
        
        url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/imports/{import_id}"
        headers = self.auth.get_auth_headers()
        
        logger.info(f"  Polling import {import_id} (retry every {retry_after}s, max {max_attempts} attempts)")
        
        for attempt in range(1, max_attempts + 1):
            time.sleep(retry_after)
            
            response = requests.get(url, headers=headers, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            state = result.get("importState", "Unknown")
            
            logger.info(f"    Attempt {attempt}/{max_attempts}: {state}")
            
            if state == "Succeeded":
                logger.info(f"  ✓ Import completed successfully")
                return result
            elif state == "Failed":
                error = result.get("error", {})
                error_msg = error.get("code", "Unknown error")
                error_details = error.get("details", [])
                logger.error(f"  ✗ Import failed: {error_msg}")
                if error_details:
                    for detail in error_details:
                        logger.error(f"    - {detail.get('message', '')}")
                raise RuntimeError(f"Import {import_id} failed: {error_msg}")
        
        raise RuntimeError(f"Import {import_id} timed out after {max_attempts} attempts")
    
    def take_over_paginated_report(self, workspace_id: str, report_id: str) -> bool:
        """
        Take over ownership of a paginated report's data sources so the service
        principal can manage credentials.
        
        Uses Power BI REST API: POST /groups/{groupId}/reports/{reportId}/Default.TakeOver
        
        This is the paginated report equivalent of take_over_dataset() for semantic
        models. After TakeOver, the SP becomes the data source owner and can update
        credentials via the Gateway Datasource API.
        
        See: https://learn.microsoft.com/en-us/rest/api/power-bi/reports/take-over-in-group
        
        Args:
            workspace_id: Workspace GUID
            report_id: Paginated report GUID
            
        Returns:
            True if take-over succeeded, False otherwise
        """
        logger.info(f"Taking over ownership of paginated report {report_id}")
        
        url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/reports/{report_id}/Default.TakeOver"
        headers = self.auth.get_auth_headers()
        
        try:
            response = requests.post(url, headers=headers, timeout=60)
            if response.status_code == 200:
                logger.info(f"  ✓ Successfully took over ownership of paginated report {report_id}")
                return True
            else:
                logger.warning(f"  ⚠ TakeOver returned {response.status_code}: {response.text}")
                return False
        except Exception as e:
            logger.warning(f"  ⚠ TakeOver failed: {e}")
            return False
    
    def get_paginated_report_datasources(self, workspace_id: str, report_id: str) -> List[Dict]:
        """
        Get data sources for a paginated report (RDL).
        
        Uses Power BI REST API: GET /groups/{groupId}/reports/{reportId}/datasources
        
        Returns data source info including gatewayId and datasourceId, which are
        needed to update credentials via the Gateway Datasource API.
        
        See: https://learn.microsoft.com/en-us/rest/api/power-bi/reports/get-datasources-in-group
        
        Args:
            workspace_id: Workspace GUID
            report_id: Paginated report GUID
            
        Returns:
            List of data source dicts with gatewayId, datasourceId, connectionDetails, etc.
        """
        logger.info(f"Getting data sources for paginated report: {report_id}")
        
        url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/reports/{report_id}/datasources"
        headers = self.auth.get_auth_headers()
        
        try:
            response = requests.get(url, headers=headers, timeout=60)
            response.raise_for_status()
            data = response.json()
            datasources = data.get("value", [])
            logger.info(f"  Found {len(datasources)} data source(s) on paginated report")
            for idx, ds in enumerate(datasources):
                ds_type = ds.get("datasourceType", "unknown")
                gw_id = ds.get("gatewayId", "none")
                ds_id = ds.get("datasourceId", "none")
                conn = ds.get("connectionDetails", {})
                logger.info(f"    [{idx+1}] type={ds_type}, gateway={gw_id}, datasource={ds_id}, server={conn.get('server', 'N/A')}, database={conn.get('database', 'N/A')}")
            return datasources
        except Exception as e:
            logger.warning(f"  ⚠ Could not get paginated report datasources: {e}")
            return []
    
    def update_gateway_datasource_credentials(self, gateway_id: str, datasource_id: str, use_caller_identity: bool = True) -> bool:
        """
        Update credentials for a gateway data source.
        
        Uses Power BI REST API: PATCH /gateways/{gatewayId}/datasources/{datasourceId}
        
        For cloud data sources (e.g. Fabric Lakehouse SQL endpoints), sets
        useCallerAADIdentity=True so the SP's Entra ID identity is used for
        authentication. This creates a PersonalCloud connection bound to the SP.
        
        Prerequisites:
        - The caller must be the data source owner (use TakeOver first)
        - For paginated reports: use take_over_paginated_report()
        - For semantic models: use take_over_dataset()
        
        See: https://learn.microsoft.com/en-us/rest/api/power-bi/gateways/update-datasource
        
        Args:
            gateway_id: Gateway GUID (from get_paginated_report_datasources)
            datasource_id: Data source GUID (from get_paginated_report_datasources)
            use_caller_identity: If True, use the SP's Entra ID identity (default)
            
        Returns:
            True on success, False on failure
        """
        logger.info(f"Updating credentials for gateway datasource (gateway={gateway_id}, datasource={datasource_id})")
        
        url = f"https://api.powerbi.com/v1.0/myorg/gateways/{gateway_id}/datasources/{datasource_id}"
        headers = self.auth.get_auth_headers()
        
        payload = {
            "credentialDetails": {
                "credentialType": "OAuth2",
                "credentials": '{"credentialData":""}',
                "encryptedConnection": "Encrypted",
                "encryptionAlgorithm": "None",
                "privacyLevel": "Organizational",
                "useCallerAADIdentity": use_caller_identity
            }
        }
        
        try:
            response = requests.patch(url, headers=headers, json=payload, timeout=60)
            if response.status_code == 200:
                logger.info(f"  ✓ Successfully updated data source credentials (using SP identity)")
                return True
            else:
                logger.warning(f"  ⚠ Update credentials returned {response.status_code}: {response.text}")
                return False
        except Exception as e:
            logger.warning(f"  ⚠ Failed to update credentials: {e}")
            return False
    
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
    
    def delete_paginated_report(self, workspace_id: str, report_id: str, wait_for_completion: bool = True) -> Dict:
        """
        Delete a paginated report using the Power BI Reports API.
        
        Neither the Fabric PaginatedReport endpoint (DELETE /paginatedReports/{id})
        nor the generic Items API (DELETE /items/{id}) support deleting paginated
        reports — both return OperationNotSupportedForItem.
        
        The Power BI Reports API (DELETE /groups/{id}/reports/{id}) works for
        all report types including paginated reports.
        
        Args:
            workspace_id: Workspace GUID
            report_id: Paginated report GUID
            wait_for_completion: Pause briefly after delete to allow propagation
            
        Returns:
            Delete response dict
        """
        logger.info(f"Deleting paginated report: {report_id}")
        
        # Use Power BI Reports API - both Fabric endpoints fail for paginated reports:
        #   DELETE /paginatedReports/{id} → OperationNotSupportedForItem
        #   DELETE /items/{id}            → OperationNotSupportedForItem
        url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/reports/{report_id}"
        headers = self.auth.get_auth_headers()
        
        try:
            response = requests.delete(url, headers=headers, timeout=60)
            response.raise_for_status()
            logger.info(f"  ✓ Deleted paginated report via Power BI API")
            
            # Brief pause to allow deletion to propagate before re-import
            if wait_for_completion:
                time.sleep(3)
            
            return {"status": "success", "status_code": response.status_code}
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP Error deleting paginated report: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Failed to delete paginated report: {str(e)}")
            raise
    
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


    # ==================== Deployment Pipeline Operations ====================

    def list_deployment_pipelines(self) -> List[Dict]:
        """
        List all deployment pipelines the service principal has access to.
        
        Returns:
            List of deployment pipeline objects with id, displayName, description
        """
        result = self._make_request("GET", "/deploymentPipelines")
        return result.get("value", [])

    def get_deployment_pipeline(self, pipeline_id: str) -> Dict:
        """
        Get deployment pipeline metadata.
        
        Args:
            pipeline_id: The deployment pipeline ID
            
        Returns:
            Pipeline metadata dict
        """
        return self._make_request("GET", f"/deploymentPipelines/{pipeline_id}")

    def list_deployment_pipeline_stages(self, pipeline_id: str) -> List[Dict]:
        """
        List stages of a deployment pipeline.
        
        Each stage has: id, order, displayName, description, workspaceId, workspaceName, isPublic
        
        Args:
            pipeline_id: The deployment pipeline ID
            
        Returns:
            List of stage objects
        """
        result = self._make_request("GET", f"/deploymentPipelines/{pipeline_id}/stages")
        return result.get("value", [])

    def list_deployment_pipeline_stage_items(self, pipeline_id: str, stage_id: str) -> List[Dict]:
        """
        List supported items in a deployment pipeline stage.
        
        Args:
            pipeline_id: The deployment pipeline ID
            stage_id: The stage ID
            
        Returns:
            List of item objects with itemId, itemDisplayName, itemType, etc.
        """
        result = self._make_request(
            "GET",
            f"/deploymentPipelines/{pipeline_id}/stages/{stage_id}/items"
        )
        return result.get("value", [])

    def deploy_stage_content(
        self,
        pipeline_id: str,
        source_stage_id: str,
        target_stage_id: str,
        items: Optional[List[Dict]] = None,
        note: str = "",
        options: Optional[Dict] = None
    ) -> Dict:
        """
        Deploy items from one pipeline stage to another.
        
        This is an LRO (long-running operation). Returns operation details
        that can be polled for completion.
        
        Args:
            pipeline_id: The deployment pipeline ID
            source_stage_id: Source stage ID
            target_stage_id: Target stage ID
            items: Optional list of specific items to deploy. Each item has:
                   - sourceItemId: The item ID in the source stage
                   - itemType: The Fabric item type (e.g. "PaginatedReport", "Report")
                   If not provided, ALL supported items are deployed.
            note: Optional deployment note (max 1024 chars)
            options: Optional deployment options (e.g. allowCrossRegionDeployment)
            
        Returns:
            Dict with operation_id, deployment_id, status, etc.
        """
        payload = {
            "sourceStageId": source_stage_id,
            "targetStageId": target_stage_id
        }
        
        if items:
            payload["items"] = items
        
        if note:
            payload["note"] = note[:1024]
        
        if options:
            payload["options"] = options
        
        logger.info(f"Deploying from stage {source_stage_id} to {target_stage_id}")
        if items:
            logger.info(f"  Deploying {len(items)} specific item(s)")
            for item in items:
                logger.info(f"    - {item.get('itemType')}: {item.get('sourceItemId')}")
        else:
            logger.info(f"  Deploying all supported items")
        
        result = self._make_request(
            "POST",
            f"/deploymentPipelines/{pipeline_id}/deploy",
            json_data=payload
        )
        
        # Capture deployment-id header if present in LRO response
        if "deployment_id" not in result and result.get("status_code") == 202:
            logger.info("  Deployment initiated (LRO)")
        
        return result

    def get_deployment_pipeline_operation(self, pipeline_id: str, operation_id: str) -> Dict:
        """
        Get the details of a specific deployment operation, including execution plan.
        
        Args:
            pipeline_id: The deployment pipeline ID
            operation_id: The operation ID from the deploy response
            
        Returns:
            Operation details with status, executionPlan, etc.
        """
        return self._make_request(
            "GET",
            f"/deploymentPipelines/{pipeline_id}/operations/{operation_id}"
        )

    def wait_for_deployment_completion(
        self,
        pipeline_id: str,
        operation_id: str,
        retry_after: int = 30,
        max_attempts: int = 40
    ) -> Dict:
        """
        Poll a deployment pipeline operation until it completes.
        
        Args:
            pipeline_id: The deployment pipeline ID
            operation_id: The operation ID to poll
            retry_after: Seconds between polls (default 30)
            max_attempts: Maximum poll attempts (default 40 = ~20 min)
            
        Returns:
            Final operation result
            
        Raises:
            RuntimeError: If deployment fails or times out
        """
        
        logger.info(f"  Waiting for deployment to complete (polling every {retry_after}s, max {max_attempts} attempts)")
        
        for attempt in range(1, max_attempts + 1):
            time.sleep(retry_after)
            
            operation = self.get_deployment_pipeline_operation(pipeline_id, operation_id)
            status = operation.get("status", "Unknown")
            
            logger.info(f"    Attempt {attempt}/{max_attempts}: {status}")
            
            if status == "Succeeded":
                logger.info(f"  ✓ Deployment completed successfully")
                
                # Log execution plan summary
                exec_plan = operation.get("executionPlan", {})
                steps = exec_plan.get("steps", [])
                for step in steps:
                    src_target = step.get("sourceAndTarget", {})
                    src_name = src_target.get("sourceItemDisplayName", "Unknown")
                    item_type = src_target.get("itemType", "Unknown")
                    step_status = step.get("status", "Unknown")
                    diff_state = step.get("preDeploymentDiffState", "Unknown")
                    logger.info(f"    ✓ {src_name} ({item_type}): {step_status} [was: {diff_state}]")
                
                return operation
                
            elif status == "Failed":
                exec_plan = operation.get("executionPlan", {})
                steps = exec_plan.get("steps", [])
                
                error_details = []
                for step in steps:
                    step_status = step.get("status", "Unknown")
                    if step_status == "Failed":
                        error = step.get("error", {})
                        src_target = step.get("sourceAndTarget", {})
                        src_name = src_target.get("sourceItemDisplayName", "Unknown")
                        error_msg = error.get("message", "Unknown error")
                        error_details.append(f"{src_name}: {error_msg}")
                        logger.error(f"    ✗ {src_name}: {error_msg}")
                
                raise RuntimeError(
                    f"Deployment failed: {'; '.join(error_details) if error_details else 'Unknown error'}"
                )
            
            elif status not in ["NotStarted", "Running"]:
                logger.warning(f"  Unexpected deployment status: {status}")
        
        raise RuntimeError(
            f"Deployment timed out after {max_attempts * retry_after}s"
        )

    def find_deployment_pipeline_by_name(self, pipeline_name: str) -> Optional[Dict]:
        """
        Find a deployment pipeline by its display name.
        
        Args:
            pipeline_name: The display name of the pipeline
            
        Returns:
            Pipeline dict if found, None otherwise
        """
        pipelines = self.list_deployment_pipelines()
        for pipeline in pipelines:
            if pipeline.get("displayName") == pipeline_name:
                return pipeline
        return None

    def find_stage_by_workspace_id(
        self,
        pipeline_id: str,
        workspace_id: str
    ) -> Optional[Dict]:
        """
        Find a pipeline stage by the workspace ID assigned to it.
        
        Args:
            pipeline_id: The deployment pipeline ID
            workspace_id: The workspace ID to search for
            
        Returns:
            Stage dict if found, None otherwise
        """
        stages = self.list_deployment_pipeline_stages(pipeline_id)
        for stage in stages:
            if stage.get("workspaceId") == workspace_id:
                return stage
        return None

    def find_stage_by_order(self, pipeline_id: str, order: int) -> Optional[Dict]:
        """
        Find a pipeline stage by its order (0=Development, 1=Test, 2=Production, etc.).
        
        Args:
            pipeline_id: The deployment pipeline ID
            order: The stage order (0-based)
            
        Returns:
            Stage dict if found, None otherwise
        """
        stages = self.list_deployment_pipeline_stages(pipeline_id)
        for stage in stages:
            if stage.get("order") == order:
                return stage
        return None


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
