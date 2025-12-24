"""
Microsoft Fabric Authentication Module
Handles authentication using Azure Service Principal for automated deployments
"""

import os
from typing import Optional
from azure.identity import ClientSecretCredential, DefaultAzureCredential
import requests
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FabricAuthenticator:
    """Handles authentication for Microsoft Fabric REST API calls"""
    
    FABRIC_API_SCOPE = "https://api.fabric.microsoft.com/.default"
    SQL_DATABASE_SCOPE = "https://database.windows.net/.default"  # For SQL endpoint authentication
    
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        tenant_id: Optional[str] = None,
        use_default_credential: bool = False,
        secret_env_var: Optional[str] = None
    ):
        """
        Initialize authenticator with service principal credentials
        
        Args:
            client_id: Azure AD Application (Client) ID
            client_secret: Azure AD Application Secret
            tenant_id: Azure AD Tenant ID
            use_default_credential: Use DefaultAzureCredential (for local development)
            secret_env_var: Environment variable name containing the secret (for per-env SPs)
        """
        self.client_id = client_id or os.getenv("AZURE_CLIENT_ID")
        
        # Support environment-specific secret variables
        if secret_env_var:
            self.client_secret = os.getenv(secret_env_var)
            logger.info(f"Using environment-specific secret from: {secret_env_var}")
        else:
            self.client_secret = client_secret or os.getenv("AZURE_CLIENT_SECRET")
        
        self.tenant_id = tenant_id or os.getenv("AZURE_TENANT_ID")
        self.use_default_credential = use_default_credential
        
        self._credential = None
        self._access_token = None
        self._sql_access_token = None  # Separate token for SQL database authentication
        
    def _get_credential(self):
        """Get Azure credential object"""
        if self._credential is None:
            if self.use_default_credential:
                logger.info("Using DefaultAzureCredential for authentication")
                self._credential = DefaultAzureCredential()
            else:
                if not all([self.client_id, self.client_secret, self.tenant_id]):
                    raise ValueError(
                        "Service Principal credentials not provided. "
                        "Set AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, and AZURE_TENANT_ID "
                        "environment variables or pass them to the constructor."
                    )
                logger.info(f"Using Service Principal authentication (Client ID: {self.client_id})")
                self._credential = ClientSecretCredential(
                    tenant_id=self.tenant_id,
                    client_id=self.client_id,
                    client_secret=self.client_secret
                )
        return self._credential
    
    def get_access_token(self, force_refresh: bool = False) -> str:
        """
        Get access token for Fabric REST API
        
        Args:
            force_refresh: Force token refresh even if cached token exists
            
        Returns:
            Access token string
        """
        if self._access_token is None or force_refresh:
            credential = self._get_credential()
            token = credential.get_token(self.FABRIC_API_SCOPE)
            self._access_token = token.token
            logger.info("Successfully obtained access token")
        
        return self._access_token
    
    def get_sql_access_token(self, force_refresh: bool = False) -> str:
        """
        Get access token for SQL Database (for lakehouse SQL endpoints)
        
        Args:
            force_refresh: Force token refresh even if cached token exists
            
        Returns:
            Access token string for SQL Database scope
        """
        if self._sql_access_token is None or force_refresh:
            credential = self._get_credential()
            token = credential.get_token(self.SQL_DATABASE_SCOPE)
            self._sql_access_token = token.token
            logger.info("Successfully obtained SQL Database access token")
        
        return self._sql_access_token
    
    def get_auth_headers(self, force_refresh: bool = False) -> dict:
        """
        Get authorization headers for API requests
        
        Args:
            force_refresh: Force token refresh
            
        Returns:
            Dictionary with authorization header
        """
        token = self.get_access_token(force_refresh=force_refresh)
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    
    def validate_authentication(self) -> bool:
        """
        Validate that authentication is working by making a test API call
        
        Returns:
            True if authentication successful, False otherwise
        """
        try:
            headers = self.get_auth_headers()
            # Test by listing workspaces
            response = requests.get(
                "https://api.fabric.microsoft.com/v1/workspaces",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info("Authentication validation successful")
                return True
            else:
                logger.error(f"Authentication validation failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Authentication validation error: {str(e)}")
            return False


def main():
    """Test authentication"""
    print("Testing Fabric Authentication...")
    
    # Try to authenticate
    auth = FabricAuthenticator()
    
    if auth.validate_authentication():
        print("✅ Authentication successful!")
        token = auth.get_access_token()
        print(f"Access token obtained (length: {len(token)})")
    else:
        print("❌ Authentication failed!")
        print("Please check your credentials and try again.")


if __name__ == "__main__":
    main()
