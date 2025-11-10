import aiohttp
import orjson
import asyncio
from typing import Dict, Union
from src.utils.misc import datetime_now as dt_now
from src.exchanges.hyperliquid.endpoints import BaseEndpoints, ApiEndpoints
from src.sharedstate import SharedState


class HyperliquidPrivateGetClient:
    """
    Handles the private GET requests to Hyperliquid's API.

    Attributes
    ----------
    ss : SharedState
        An instance of SharedState containing shared application data.
    max_retries : int
        Maximum number of retries for a request before giving up.
    base_url : str
        The base URL for Hyperliquid API.

    Methods
    -------
    submit(session: aiohttp.ClientSession, endpoint: str, payload: dict) -> Union[Dict, None]:
        Submits a POST request to a specific Hyperliquid API endpoint and returns the response.
    """

    max_retries = 3

    def __init__(self, ss: SharedState) -> None:
        """
        Initializes the HyperliquidPrivateGetClient with API credentials and base endpoint.

        Parameters
        ----------
        ss : SharedState
            An instance of SharedState containing shared application data.
        """
        self.ss = ss
        self.base_url = BaseEndpoints.MAINNET
        self.wallet_address = getattr(ss, 'hyperliquid_wallet_address', None) or ss.api_key

    async def submit(self, session: aiohttp.ClientSession, endpoint: str, payload: dict) -> Union[Dict, None]:
        """
        Asynchronously submits a POST request to Hyperliquid.

        Parameters
        ----------
        session : aiohttp.ClientSession
            The session used to send the request.
        endpoint : str
            The API endpoint to which the request is sent.
        payload : dict
            The request payload.

        Returns
        -------
        Union[Dict, None]
            The JSON response from the API or None if an error occurs.
        """
        full_endpoint = self.base_url + endpoint
        max_retries = self.max_retries
    
        for attempt in range(max_retries):
            try:
                async with session.post(full_endpoint, json=payload) as req:
                    response = orjson.loads(await req.text())
                    
                    if isinstance(response, dict):
                        status = response.get("status", "").lower()
                        if status == "ok" or "data" in response:
                            return response
                        else:
                            print(f"{dt_now()}: Error: {response} | Endpoint: {endpoint}")
                            break
                    else:
                        return response
                        
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(attempt + 1)
                else:
                    raise e
        
        return None


class HyperliquidPrivateGet:
    """
    Handles the retrieval of private data from Hyperliquid's API, such as open orders and current positions.

    Attributes
    ----------
    ss : SharedState
        An instance of SharedState containing shared application data.
    symbol : str
        The trading symbol to query data for, obtained from the shared state.
    endpoints : ApiEndpoints
        Container for API endpoint URLs specific to Hyperliquid's private data retrieval.
    client : HyperliquidPrivateGetClient
        A client configured to interact with Hyperliquid's private API endpoints.
    session : aiohttp.ClientSession
        An active session for making HTTP requests asynchronously.

    Methods
    -------
    open_orders() -> Union[Dict, None]:
        Fetches the current open orders for the specified trading symbol.
    current_position() -> Union[Dict, None]:
        Retrieves the current position for the specified trading symbol.
    _close_() -> None:
        Closes the active aiohttp session gracefully.
    """

    def __init__(self, ss: SharedState) -> None:
        """
        Initializes the HyperliquidPrivateGet class with shared state, API endpoints, and a session for HTTP requests.

        Parameters
        ----------
        ss : SharedState
            An instance of SharedState containing shared application data.
        """
        self.ss = ss
        self.symbol = getattr(ss, 'hyperliquid_symbol', None) or getattr(ss, 'bybit_symbol', None)
        self.endpoints = ApiEndpoints
        self.client = HyperliquidPrivateGetClient(self.ss)
        self.session = aiohttp.ClientSession()
        self.wallet_address = getattr(ss, 'hyperliquid_wallet_address', None) or ss.api_key

    async def open_orders(self) -> Union[Dict, None]:
        """
        Asynchronously retrieves the list of open orders for the trading symbol from Hyperliquid.

        Returns
        -------
        Union[Dict, None]
            A dictionary containing the open orders if successful, otherwise None.
        """
        payload = {
            "type": "openOrders",
            "user": self.wallet_address
        }
        endpoint = self.endpoints.INFO
        return await self.client.submit(self.session, endpoint, payload)

    async def current_position(self) -> Union[Dict, None]:
        """
        Asynchronously fetches the current position for the trading symbol from Hyperliquid.

        Returns
        -------
        Union[Dict, None]
            A dictionary containing the current position if successful, otherwise None.
        """
        payload = {
            "type": "clearinghouseState",
            "user": self.wallet_address
        }
        endpoint = self.endpoints.INFO
        return await self.client.submit(self.session, endpoint, payload)
 
    async def _close_(self) -> None:
        """
        Closes the aiohttp session associated with this instance.

        This method should be called to release resources before the instance is discarded.
        """
        await self.session.close()

