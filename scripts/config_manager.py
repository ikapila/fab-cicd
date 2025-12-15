"""
Configuration Manager for Microsoft Fabric Deployments
Handles loading and managing environment-specific configurations
"""

import json
import os
from typing import Dict, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages environment-specific configuration for Fabric deployments"""
    
    VALID_ENVIRONMENTS = ["dev", "uat", "prod"]
    
    def __init__(self, environment: str, config_dir: str = "config"):
        """
        Initialize configuration manager
        
        Args:
            environment: Environment name (dev, uat, prod)
            config_dir: Directory containing configuration files
        """
        if environment.lower() not in self.VALID_ENVIRONMENTS:
            raise ValueError(
                f"Invalid environment: {environment}. "
                f"Must be one of {self.VALID_ENVIRONMENTS}"
            )
        
        self.environment = environment.lower()
        self.config_dir = config_dir
        self.config = self._load_config()
        
    def _load_config(self) -> Dict:
        """
        Load configuration from JSON file
        
        Returns:
            Configuration dictionary
        """
        config_file = os.path.join(self.config_dir, f"{self.environment}.json")
        
        if not os.path.exists(config_file):
            raise FileNotFoundError(
                f"Configuration file not found: {config_file}"
            )
        
        logger.info(f"Loading configuration from: {config_file}")
        
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        # Validate required fields
        self._validate_config(config)
        
        return config
    
    def _validate_config(self, config: Dict) -> None:
        """
        Validate that required configuration fields are present
        
        Args:
            config: Configuration dictionary to validate
            
        Raises:
            ValueError: If required fields are missing
        """
        required_fields = ["workspace"]
        
        for field in required_fields:
            if field not in config:
                raise ValueError(
                    f"Missing required field in configuration: {field}"
                )
        
        # Validate workspace configuration
        workspace = config.get("workspace", {})
        if not workspace.get("id") or not workspace.get("name"):
            raise ValueError(
                "Workspace configuration must include 'id' and 'name'"
            )
    
    def get_workspace_id(self) -> str:
        """Get workspace ID for this environment"""
        return self.config["workspace"]["id"]
    
    def get_workspace_name(self) -> str:
        """Get workspace name for this environment"""
        return self.config["workspace"]["name"]
    
    def get_capacity_id(self) -> Optional[str]:
        """Get capacity ID for this environment"""
        return self.config["workspace"].get("capacity_id")
    
    def get_artifacts_root_folder(self) -> str:
        """Get artifacts root folder name (defaults to 'wsartifacts')"""
        return self.config.get("artifacts_root_folder", "wsartifacts")
    
    def get_lakehouse_config(self, lakehouse_name: str) -> Optional[Dict]:
        """
        Get configuration for a specific lakehouse
        
        Args:
            lakehouse_name: Name of the lakehouse
            
        Returns:
            Lakehouse configuration dictionary or None
        """
        lakehouses = self.config.get("lakehouses", {})
        return lakehouses.get(lakehouse_name)
    
    def get_lakehouse_id(self, lakehouse_name: str) -> Optional[str]:
        """
        Get lakehouse ID by name
        
        Args:
            lakehouse_name: Name of the lakehouse
            
        Returns:
            Lakehouse ID or None
        """
        lakehouse_config = self.get_lakehouse_config(lakehouse_name)
        if lakehouse_config:
            return lakehouse_config.get("id")
        return None
    
    def get_connection(self, connection_name: str) -> Optional[str]:
        """
        Get connection string by name
        
        Args:
            connection_name: Name of the connection
            
        Returns:
            Connection string or None
        """
        connections = self.config.get("connections", {})
        return connections.get(connection_name)
    
    def get_parameter(self, parameter_name: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get environment-specific parameter
        
        Args:
            parameter_name: Name of the parameter
            default: Default value if parameter not found
            
        Returns:
            Parameter value or default
        """
        parameters = self.config.get("parameters", {})
        return parameters.get(parameter_name, default)
    
    def get_all_parameters(self) -> Dict:
        """
        Get all environment parameters
        
        Returns:
            Dictionary of all parameters
        """
        return self.config.get("parameters", {})
    
    def substitute_parameters(self, text: str) -> str:
        """
        Replace parameter placeholders in text with actual values
        
        Args:
            text: Text containing placeholders like {{parameter_name}}
            
        Returns:
            Text with substituted values
        """
        parameters = self.get_all_parameters()
        
        for param_name, param_value in parameters.items():
            placeholder = f"{{{{{param_name}}}}}"
            text = text.replace(placeholder, str(param_value))
        
        return text
    
    def get_service_principal_config(self) -> Optional[Dict]:
        """
        Get service principal configuration for this environment
        
        Returns:
            Service principal configuration dictionary or None
        """
        return self.config.get("service_principal")
    
    def get_sp_client_id(self) -> Optional[str]:
        """Get service principal client ID"""
        sp_config = self.get_service_principal_config()
        return sp_config.get("client_id") if sp_config else None
    
    def get_sp_tenant_id(self) -> Optional[str]:
        """Get service principal tenant ID"""
        sp_config = self.get_service_principal_config()
        return sp_config.get("tenant_id") if sp_config else None
    
    def get_sp_secret_env_var(self) -> Optional[str]:
        """Get environment variable name for service principal secret"""
        sp_config = self.get_service_principal_config()
        return sp_config.get("secret_env_var") if sp_config else None
    
    def get_artifacts_to_create(self) -> Dict:
        """
        Get artifacts that should be created in this environment
        
        Returns:
            Dictionary of artifacts to create, keyed by artifact type
        """
        return self.config.get("artifacts_to_create", {})
    
    def get_parameters(self) -> Dict:
        """
        Get environment parameters
        
        Returns:
            Dictionary of parameters
        """
        return self.config.get("parameters", {})
    
    def get_variable_library_config(self) -> Optional[Dict]:
        """
        Get Variable Library configuration
        
        Returns:
            Variable Library configuration or None
        """
        return self.config.get("variable_library")
    
    def get_config(self) -> Dict:
        """Get entire configuration dictionary"""
        return self.config


def main():
    """Test configuration manager"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python config_manager.py <environment>")
        print("Example: python config_manager.py dev")
        sys.exit(1)
    
    env = sys.argv[1]
    
    try:
        config_mgr = ConfigManager(env)
        print(f"\n✅ Configuration loaded for environment: {env}")
        print(f"\nWorkspace: {config_mgr.get_workspace_name()}")
        print(f"Workspace ID: {config_mgr.get_workspace_id()}")
        
        parameters = config_mgr.get_all_parameters()
        if parameters:
            print(f"\nParameters:")
            for key, value in parameters.items():
                print(f"  - {key}: {value}")
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
