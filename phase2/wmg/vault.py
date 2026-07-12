import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("WMG.Vault")

class AccessDeniedError(Exception):
    """Raised when access to credentials is requested from an unauthorized context or caller class."""
    pass

class CredentialVault:
    def __init__(self, secrets: Optional[Dict[str, Any]] = None):
        self._secrets = secrets or {}
        self._allowed_classes = set()

    def register_allowed_class(self, cls: type):
        """Registers a Python class authorized to retrieve secrets from the vault."""
        self._allowed_classes.add(cls)
        logger.info(f"Registered authorized class: {cls.__name__}")

    def get_credentials(self, caller: Any, platform: str) -> Dict[str, str]:
        """
        Retrieves credentials for a given platform.
        Strict verification: the caller object must be an instance of an allowed adapter class.
        This prevents raw agents or unauthorized tasks from inspecting the vault.
        """
        caller_type = type(caller)
        # Check if caller type or any of its parent classes (except object) is in allowed classes
        is_allowed = False
        for allowed_cls in self._allowed_classes:
            if issubclass(caller_type, allowed_cls):
                is_allowed = True
                break
                
        if not is_allowed:
            raise AccessDeniedError(
                f"Security Violation: Access to credentials for platform '{platform}' "
                f"was requested by unauthorized type '{caller_type.__name__}'."
            )
            
        creds = self._secrets.get(platform)
        if not creds:
            raise ValueError(f"No credentials configured for platform: {platform}")
            
        return creds
