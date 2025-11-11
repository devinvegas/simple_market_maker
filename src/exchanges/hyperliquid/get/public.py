import aiohttp
import orjson
import time
from typing import Dict, Union, List
from src.exchanges.hyperliquid.endpoints import BaseEndpoints, ApiEndpoints
from src.sharedstate import SharedState


class HyperliquidPublicClient:
    """
    A client for fetching public trading data from Hyperliquid, such as candlestick data,
    recent trades, and instrument information.

    Attributes
    ----------
    ss : SharedState
        An instance of SharedState containing shared application data.
    base_url : str
        The base URL for Hyperliquid API.
    symbol : str
        The trading symbol to query data for, obtained from the shared state.

    Methods
    -------
    _request(method: str, endpoint: str, data: Dict = None) -> Dict:
        Makes an HTTP request to the Hyperliquid API.
    klines(interval: int, limit: int) -> Dict:
        Fetches candlestick data for the specified interval and limit.
    trades(limit: int) -> Dict:
        Retrieves the recent trades up to the specified limit.
    instrument_info() -> Dict:
        Gets the instrument information for the specified symbol.
    orderbook() -> Dict:
        Gets the current order book snapshot.
    """

    def __init__(self, ss: SharedState) -> None:
        """
        Initializes the HyperliquidPublicClient with shared state and trading symbol.

        Parameters
        ----------
        ss : SharedState
            An instance of SharedState containing shared application data.
        """
        self.ss = ss
        self.base_url = BaseEndpoints.MAINNET
        raw = getattr(ss, 'hyperliquid_symbol', None) or getattr(ss, 'bybit_symbol', None)
        self.coin = getattr(ss, 'hyperliquid_coin_key', None) or raw

    async def _request(self, method: str, endpoint: str, data: Dict = None) -> Dict:
        """
        Makes an HTTP request to the Hyperliquid API.

        Parameters
        ----------
        method : str
            HTTP method (GET or POST).
        endpoint : str
            API endpoint path.
        data : Dict, optional
            Request payload for POST requests.

        Returns
        -------
        Dict
            JSON response from the API.
        """
        url = f"{self.base_url}{endpoint}"
        async with aiohttp.ClientSession() as session:
            if method == "POST":
                async with session.post(url, json=data) as response:
                    # Check status code
                    if response.status != 200:
                        text = await response.text()
                        raise Exception(f"HTTP {response.status}: {text}")
                    text = await response.text()
                    if not text:
                        raise Exception("Empty response from API")
                    return orjson.loads(text)
            else:
                async with session.get(url) as response:
                    if response.status != 200:
                        text = await response.text()
                        raise Exception(f"HTTP {response.status}: {text}")
                    text = await response.text()
                    if not text:
                        raise Exception("Empty response from API")
                    return orjson.loads(text)

    async def klines(self, interval: int, limit: int) -> Dict:
        """
        Fetches candlestick data for the specified interval and limit.

        Parameters
        ----------
        interval : int
            The interval in milliseconds (e.g., 60000 for 1 minute).
        limit : int
            The number of candles to retrieve.

        Returns
        -------
        Dict
            A dictionary containing the candlestick data.
        """
        # Convert milliseconds to minutes for interval string
        interval_minutes = interval // 60000
        interval_str = f"{interval_minutes}m"
        
        # Calculate startTime and endTime (endTime = now, startTime = now - limit * interval)
        end_time = int(time.time() * 1000)  # Current time in milliseconds
        start_time = end_time - (limit * interval)  # Go back by limit * interval
        
        payload = {
            "type": "candleSnapshot",
            "req": {
                "coin": self.coin,
                "interval": interval_str,  # e.g., "1m", "5m"
                "startTime": start_time,
                "endTime": end_time
            }
        }
        return await self._request("POST", ApiEndpoints.INFO, payload)

    async def trades(self, limit: int) -> Dict:
        """
        Retrieves the recent trades up to the specified limit.

        Parameters
        ----------
        limit : int
            The maximum number of trades to retrieve.

        Returns
        -------
        Dict
            A dictionary containing the recent trades.
        """
        payload = {
            "type": "recentTrades",
            "coin": self.coin,
            "n": limit
        }
        return await self._request("POST", ApiEndpoints.INFO, payload)

    async def instrument_info(self) -> Dict:
        """
        Gets the instrument information for the specified symbol.

        Returns
        -------
        Dict
            A dictionary containing instrument information including tick size, lot size, etc.
        """
        payload = {
            "type": "meta"
        }
        return await self._request("POST", ApiEndpoints.INFO, payload)

    async def orderbook(self, limit: int = 500) -> Dict:
        """
        Gets the current order book snapshot.

        Parameters
        ----------
        limit : int
            Maximum number of levels to retrieve (default 500).

        Returns
        -------
        Dict
            A dictionary containing the order book snapshot.
        """
        payload = {
            "type": "l2Book",
            "coin": self.coin
        }
        return await self._request("POST", ApiEndpoints.INFO, payload)

