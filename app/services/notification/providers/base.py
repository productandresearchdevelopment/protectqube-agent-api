from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple


class BaseNotificationProvider(ABC):
    """
    Abstract interface for notification providers.
    """
    provider_key: str
    display_name: str
    description: str
    icon: str

    @abstractmethod
    def send(self, recipient: str, title: str, body: str, data: Dict[str, Any], config: Dict[str, Any]) -> Tuple[bool, str, Any]:
        """
        Sends the notification.
        Returns: (success: bool, error_message: str, response_payload: Any)
        """
        pass

    @abstractmethod
    def test_connection(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Verifies credentials / connection with a test message or ping.
        Returns: (success: bool, message: str)
        """
        pass

    @abstractmethod
    def get_config_schema(self) -> Dict[str, Any]:
        """
        Returns JSON schema describing configuration fields for UI form generation.
        """
        pass
