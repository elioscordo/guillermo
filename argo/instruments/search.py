import asyncio
import os
from abc import ABC, abstractmethod
from typing import Iterable, List, Optional

from nautilus_trader.adapters.interactive_brokers.client import InteractiveBrokersClient
from nautilus_trader.adapters.interactive_brokers.common import IBContract
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.model.identifiers import TraderId

from argo.models import AssetClass


ASSET_CLASS_TO_SEC_TYPE: dict[str, str] = {
    AssetClass.EQUITY: "STK",
    AssetClass.FUTURE: "FUT",
    AssetClass.OPTION: "OPT",
    AssetClass.FX: "CASH",
    AssetClass.CRYPTO: "CRYPTO",
    AssetClass.INDEX: "IND",
    AssetClass.COMMODITY: "CMDTY",
}


class SymbolSearchStrategy(ABC):
    """Abstract Strategy interface for symbol discovery."""

    @abstractmethod
    async def search_async(
        self,
        query: str,
        sec_type: Optional[str] = None,
        currency: Optional[str] = None,
    ) -> List[str]:
        """Asynchronously searches and returns matched ticker symbols."""
        pass

    def search(
        self,
        query: str,
        sec_type: Optional[str] = None,
        currency: Optional[str] = None,
    ) -> List[str]:
        """Synchronous wrapper for searching symbols."""
        return asyncio.run(self.search_async(query, sec_type=sec_type, currency=currency))


class NautilusIBSymbolSearchStrategy(SymbolSearchStrategy):
    """
    Concrete Strategy searching Interactive Brokers contracts via Nautilus Trader client.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        client_id: int = 98,
        timeout: int = 15,
        client: Optional[InteractiveBrokersClient] = None,
    ):
        self.host = host or os.getenv("IB_HOST", "127.0.0.1")
        self.port = port or int(os.getenv("IB_PORT", "7497"))
        self.client_id = client_id
        self.timeout = timeout
        self.client = client

    def _create_temp_client(self, loop: asyncio.AbstractEventLoop) -> InteractiveBrokersClient:
        """Factory method for initializing a dedicated Nautilus IB client."""
        clock = LiveClock()
        return InteractiveBrokersClient(
            loop=loop,
            msgbus=MessageBus(trader_id=TraderId(f"SEARCH-{self.client_id}"), clock=clock),
            cache=Cache(database=None),
            clock=clock,
            host=self.host,
            port=self.port,
            client_id=self.client_id,
            request_timeout_secs=self.timeout,
        )

    def _filter_contracts(
        self,
        contracts: Iterable[IBContract],
        sec_type: Optional[str] = None,
        currency: Optional[str] = None,
    ) -> List[str]:
        """Filters matching contracts and extracts deduplicated symbols."""
        matched: set[str] = set()
        for contract in contracts:
            if sec_type and contract.secType != sec_type:
                continue
            if currency and contract.currency != currency:
                continue
            if contract.symbol:
                matched.add(contract.symbol.upper())
        return sorted(matched)

    async def _query_client(
        self,
        client: InteractiveBrokersClient,
        query: str,
        sec_type: Optional[str] = None,
        currency: Optional[str] = None,
    ) -> List[str]:
        """Executes pattern matching request through the Nautilus client."""
        results = await client.get_matching_contracts(pattern=query)
        return self._filter_contracts(results or [], sec_type=sec_type, currency=currency)

    async def search_async(
        self,
        query: str,
        sec_type: Optional[str] = None,
        currency: Optional[str] = None,
    ) -> List[str]:
        """Searches contracts using active or temporary Nautilus IB client."""
        if self.client and self.client.is_connected:
            return await self._query_client(self.client, query, sec_type, currency)

        loop = asyncio.get_running_loop()
        temp_client = self._create_temp_client(loop)
        await temp_client._start_async()
        try:
            return await self._query_client(temp_client, query, sec_type, currency)
        finally:
            await temp_client._stop_async()


class SymbolSearchService:
    """
    Service facade orchestrating symbol discovery and InstrumentGroup population.
    """

    def __init__(self, strategy: Optional[SymbolSearchStrategy] = None):
        self.strategy = strategy or NautilusIBSymbolSearchStrategy()

    def search_for_group(self, group, query: str) -> List[str]:
        """Searches symbols matching the group's asset class and currency."""
        sec_type = ASSET_CLASS_TO_SEC_TYPE.get(group.asset_class, "STK")
        return self.strategy.search(query=query, sec_type=sec_type, currency=group.currency)

    async def search_for_group_async(self, group, query: str) -> List[str]:
        """Asynchronously searches symbols matching the group's asset class and currency."""
        sec_type = ASSET_CLASS_TO_SEC_TYPE.get(group.asset_class, "STK")
        return await self.strategy.search_async(query=query, sec_type=sec_type, currency=group.currency)

    def populate_group_symbols(self, group, query: str, append: bool = False) -> List[str]:
        """Searches symbols and saves them to the InstrumentGroup instance."""
        symbols = self.search_for_group(group, query)
        if not symbols:
            return []

        existing = set(group.get_codes()) if append else set()
        combined = sorted(existing.union(symbols))
        group.symbols = ", ".join(combined)
        group.save(update_fields=["symbols", "updated_at"])
        return symbols
