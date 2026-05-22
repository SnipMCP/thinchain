from abc import ABC, abstractmethod
from typing import Optional


class ConnectorError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class BaseConnector(ABC):
    name: str = "base"

    @abstractmethod
    async def get_chain(self, symbol: str, expiration: str) -> list[dict]:
        """Return a list of raw option contract dicts (broker-native field names)."""
        ...

    @abstractmethod
    async def get_underlying_price(self, symbol: str) -> float:
        """Return last/underlying price as float. Raise ConnectorError if missing."""
        ...
