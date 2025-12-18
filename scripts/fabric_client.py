"""
Microsoft Fabric REST API Client
Provides wrapper functions for common Fabric API operations
"""

import requests
import logging
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
            
            if status == "Succeeded":
                logger.info(f"  ✓ Operation completed successfully")
                # Get the actual result
                result = self.get_operation_result(operation_id)
                return result
            elif status == "Failed":
                error = state.get("error", {})
                error_msg = error.get("message", "Unknown error")
                logger.error(f"  ✗ Operation failed: {error_msg}")
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
    
    def create_lakehouse(self, workspace_id: str, lakehouse_name: str, description: str = "", folder_id: str = None) -> Dict:
        """
        Create a new lakehouse
        
        Args:
            workspace_id: Workspace GUID
            lakehouse_name: Name for the new lakehouse
            description: Optional description
            folder_id: Optional workspace folder ID to place lakehouse in
            
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
        return self._make_request("POST", f"/workspaces/{workspace_id}/lakehouses", json_data=payload)
    
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
        Create a paginated report
        
        Args:
            workspace_id: Workspace GUID
            report_name: Name for the report
            definition: Report definition (.rdl file)
            folder_id: Optional workspace folder ID to place report in
            
        Returns:
            Created report details
        """
        logger.info(f"Creating paginated report: {report_name}")
        payload = {
            "displayName": report_name,
            "definition": definition
        }
        if folder_id:
            payload["folderId"] = folder_id
            logger.info(f"  Including folderId in payload: {folder_id}")
        return self._make_request("POST", f"/workspaces/{workspace_id}/paginatedReports", json_data=payload)
    
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
    
    def create_variable_library(self, workspace_id: str, name: str, description: str = "", folder_id: str = None) -> Dict:
        """
        Create a Variable Library
        
        Args:
            workspace_id: Workspace GUID
            name: Variable Library name
            description: Variable Library description
            folder_id: Optional workspace folder ID to place library in
            
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
        
        Args:
            workspace_id: Workspace GUID
            library_id: Variable Library GUID
            
        Returns:
            Variable Library definition with variables
        """
        logger.info(f"Getting Variable Library definition: {library_id}")
        return self._make_request("POST", f"/workspaces/{workspace_id}/items/{library_id}/getDefinition")
    
    def update_variable_library_definition(self, workspace_id: str, library_id: str, definition: Dict) -> Dict:
        """
        Update Variable Library definition (variables)
        
        Args:
            workspace_id: Workspace GUID
            library_id: Variable Library GUID
            definition: Variable Library definition with variables
            
        Returns:
            Update response
        """
        logger.info(f"Updating Variable Library definition: {library_id}")
        payload = {"definition": definition}
        return self._make_request("POST", f"/workspaces/{workspace_id}/items/{library_id}/updateDefinition", json_data=payload)
    
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
            SQL endpoint connection string
        """
        logger.info(f"Getting SQL endpoint for lakehouse: {lakehouse_id}")
        lakehouse = self.get_item(workspace_id, lakehouse_id)
        
        # Extract properties for SQL endpoint
        properties = lakehouse.get("properties", {})
        sql_endpoint_props = properties.get("sqlEndpointProperties", {})
        
        if not sql_endpoint_props:
            raise ValueError(f"Lakehouse {lakehouse_id} does not have SQL endpoint enabled")
        
        # Build connection string using workspace and lakehouse info
        # Format: <workspace-name>.datawarehouse.fabric.microsoft.com
        connection_string = sql_endpoint_props.get("connectionString")
        
        if not connection_string:
            # Fallback: construct from workspace info
            workspace = self.get_workspace(workspace_id)
            workspace_name = workspace.get("displayName", "").replace(" ", "")
            lakehouse_name = lakehouse.get("displayName", "")
            connection_string = f"{workspace_name}.datawarehouse.fabric.microsoft.com"
            
        return connection_string
    
    def execute_sql_command(self, connection_string: str, database: str, sql_command: str) -> Optional[List[Dict]]:
        """
        Execute SQL command against lakehouse SQL endpoint
        
        Args:
            connection_string: SQL endpoint connection string
            database: Database name (lakehouse name)
            sql_command: SQL command to execute
            
        Returns:
            Query results as list of dictionaries (for SELECT), None for DDL commands
        """
        if not PYODBC_AVAILABLE:
            raise ImportError("pyodbc is required for SQL operations. Install with: pip install pyodbc")
        
        logger.info(f"Executing SQL command on {database}")
        
        # Get access token for Azure SQL
        token = self.auth.get_access_token()
        
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
        
        connection = None
        cursor = None
        
        try:
            # Connect using AAD token
            connection = pyodbc.connect(conn_str, attrs_before={1256: token_struct})
            cursor = connection.cursor()
            
            # Execute command
            cursor.execute(sql_command)
            
            # Check if this is a SELECT query
            if sql_command.strip().upper().startswith("SELECT"):
                columns = [column[0] for column in cursor.description]
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
            else:
                # DDL command (CREATE, ALTER, DROP)
                connection.commit()
                return None
                
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
    from fabric_auth import FabricAuthenticator
    
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
