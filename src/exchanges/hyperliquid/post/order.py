import asyncio
import aiohttp
from typing import List, Dict, Tuple, Union
from src.exchanges.hyperliquid.post.client import HyperliquidPrivatePostClient
from src.exchanges.hyperliquid.endpoints import ApiEndpoints
from src.exchanges.hyperliquid.post.types import HyperliquidFormats
from src.sharedstate import SharedState


class Order:
    """
    Facilitates creating, amending, and canceling orders on Hyperliquid through asynchronous HTTP requests.
    
    Attributes
    ----------
    ss : SharedState
        An instance of SharedState containing shared application data.
    wallet_address : str
        Wallet address for authenticated requests.
    private_key : str
        Private key for signing requests.
    formats : HyperliquidFormats
        A helper object for formatting order payloads according to Hyperliquid's API requirements.
    endpoints : ApiEndpoints
        Container for Hyperliquid's API endpoint URLs.
    client : HyperliquidPrivatePostClient
        A client configured for executing signed POST requests to Hyperliquid.
    session : aiohttp.ClientSession
        A session for making HTTP requests.
    """

    def __init__(self, ss: SharedState) -> None:
        """
        Initializes the Order object with shared state and API credentials.
        """
        self.ss = ss
        self.wallet_address = getattr(ss, 'hyperliquid_wallet_address', None) or ss.api_key
        self.private_key = getattr(ss, 'hyperliquid_private_key', None) or ss.api_secret
        symbol = getattr(ss, 'hyperliquid_symbol', None) or getattr(ss, 'bybit_symbol', None)
        self.formats = HyperliquidFormats(symbol, self.wallet_address, self.private_key)
        self.endpoints = ApiEndpoints
        self.client = HyperliquidPrivatePostClient(self.ss)
        self.session = aiohttp.ClientSession()

    def _order_to_str_(self, order: List) -> List[str]:
        """
        Converts order elements to strings for API submission.

        Parameters
        ----------
        order : List
            The order details as a list.

        Returns
        -------
        List[str]
            The order details with all elements converted to strings.
        """
        return list(map(str, order))

    async def _submit_(self, endpoint: str, payload: Dict) -> Union[Dict, None]:
        """
        Submits an order to a specified endpoint with the given payload.

        Parameters
        ----------
        endpoint : str
            The API endpoint to submit the order to.
        payload : Dict
            The payload of the order.

        Returns
        -------
        Union[Dict, None]
            The response from the API if successful; otherwise, None.
        """
        async with self.session:
            return await self.client.submit(self.session, endpoint, payload)

    async def _sessionless_submit_(self, endpoint: str, payload: Dict) -> Union[Dict, None]:
        """
        Submits an order without managing the session lifecycle, assuming the session is already active.

        Parameters
        ----------
        endpoint : str
            The API endpoint to submit the order to.
        payload : Dict
            The payload of the order.

        Returns
        -------
        Union[Dict, None]
            The response from the API if successful; otherwise, None.
        """
        return await self.client.submit(self.session, endpoint, payload)

    async def order_market(self, order: Tuple[str, float]) -> Union[Dict, None]:
        """
        Asynchronously places a market order on Hyperliquid.

        Parameters
        ----------
        order : Tuple[str, float]
            The order details, including side ('Buy' or 'Sell') and quantity.

        Returns
        -------
        Union[Dict, None]
            The response from Hyperliquid's API if the order is successfully placed; otherwise, None.
        """
        endpoint = self.endpoints.EXCHANGE
        side, qty = self._order_to_str_(order)
        payload = self.formats.create_market(side, qty)
        return await self._submit_(endpoint, payload)

    async def order_limit(self, order: Tuple[str, float, float]) -> Union[Dict, None]:
        """
        Asynchronously places a limit order on Hyperliquid.

        Parameters
        ----------
        order : Tuple[str, float, float]
            The order details, including side ('Buy' or 'Sell'), price, and quantity.

        Returns
        -------
        Union[Dict, None]
            The response from Hyperliquid's API if the order is successfully placed; otherwise, None.
        """
        endpoint = self.endpoints.EXCHANGE
        side, price, qty = self._order_to_str_(order)
        payload = self.formats.create_limit(side, price, qty)
        return await self._submit_(endpoint, payload)

    async def order_limit_batch(self, orders: List[Tuple[str, float, float]]) -> Union[Dict, None]:
        """
        Asynchronously places a batch of limit orders on Hyperliquid.

        Parameters
        ----------
        orders : List[Tuple[str, float, float]]
            A list of orders, each including side ('Buy' or 'Sell'), price, and quantity.

        Returns
        -------
        Union[Dict, None]
            The response from Hyperliquid's API if the orders are successfully placed; otherwise, None.
        """
        endpoint = self.endpoints.EXCHANGE
        
        # Hyperliquid supports batch orders in a single action
        batch_orders = []
        for order in orders:
            side, price, qty = self._order_to_str_(order)
            batch_orders.append({
                "a": int(float(qty) * 1e6),
                "b": int(float(price) * 1e6),
                "s": self.formats._convert_side(side),
                "r": False,
                "t": {"limit": {"tif": "Gtc"}}
            })
        
        action = {
            "type": "order",
            "orders": batch_orders,
            "grouping": "na"
        }
        
        # Sign if SDK available
        try:
            from hyperliquid.utils.signing import sign_l1_action
            signed = sign_l1_action(
                self.wallet_address,
                self.private_key,
                action,
                None,
                None
            )
            payload = {"action": signed}
        except Exception:
            payload = {"action": action}
        
        result = await self._sessionless_submit_(endpoint, payload)
        await self.close_session()
        return result
         
    async def amend(self, order: Tuple[str, float, float]) -> Union[Dict, None]:
        """
        Asynchronously amends an existing order on Hyperliquid.
        Note: Hyperliquid may require cancel+replace instead of direct amend.

        Parameters
        ----------
        order : Tuple[str, float, float]
            The order details to be amended, including the order ID, new price, and new quantity.

        Returns
        -------
        Union[Dict, None]
            The response from Hyperliquid's API if the order is successfully amended; otherwise, None.
        """
        endpoint = self.endpoints.EXCHANGE
        order_id, price, qty = self._order_to_str_(order)
        payload = self.formats.create_amend(order_id, price, qty)
        return await self._submit_(endpoint, payload)

    async def amend_batch(self, orders: List[Tuple[str, float, float]]) -> Union[Dict, None]:
        """
        Asynchronously amends a batch of existing orders on Hyperliquid.

        Parameters
        ----------
        orders : List[Tuple[str, float, float]]
            A list of orders to be amended, each including the order ID, new price, and new quantity.

        Returns
        -------
        Union[Dict, None]
            The response from Hyperliquid's API if the orders are successfully amended; otherwise, None.
        """
        endpoint = self.endpoints.EXCHANGE
        # Similar to batch place, but with order IDs
        batch_orders = []
        for order in orders:
            order_id, price, qty = self._order_to_str_(order)
            batch_orders.append({
                "oid": int(order_id),
                "a": int(float(qty) * 1e6),
                "b": int(float(price) * 1e6),
            })
        
        action = {
            "type": "order",
            "orders": batch_orders,
            "grouping": "na"
        }
        
        try:
            from hyperliquid.utils.signing import sign_l1_action
            signed = sign_l1_action(
                self.wallet_address,
                self.private_key,
                action,
                None,
                None
            )
            payload = {"action": signed}
        except Exception:
            payload = {"action": action}
        
        result = await self._sessionless_submit_(endpoint, payload)
        await self.close_session()
        return result

    async def cancel(self, order_id: str) -> Union[Dict, None]:
        """
        Asynchronously cancels an existing order on Hyperliquid by order ID.

        Parameters
        ----------
        order_id : str
            The ID of the order to cancel.

        Returns
        -------
        Union[Dict, None]
            The response from Hyperliquid's API if the order is successfully canceled; otherwise, None.
        """
        endpoint = self.endpoints.EXCHANGE
        payload = self.formats.create_cancel(order_id)
        return await self._submit_(endpoint, payload)

    async def cancel_batch(self, order_ids: List[str]) -> Union[Dict, None]:
        """
        Asynchronously cancels a batch of existing orders on Hyperliquid by their order IDs.

        Parameters
        ----------
        order_ids : List[str]
            A list of order IDs to cancel.

        Returns
        -------
        Union[Dict, None]
            The response from Hyperliquid's API if the orders are successfully canceled; otherwise, None.
        """
        endpoint = self.endpoints.EXCHANGE
        symbol = getattr(self.ss, 'hyperliquid_symbol', None) or getattr(self.ss, 'bybit_symbol', None)
        
        cancels = [{"a": symbol, "o": int(oid)} for oid in order_ids]
        action = {
            "type": "cancel",
            "cancels": cancels
        }
        
        try:
            from hyperliquid.utils.signing import sign_cancel_action
            signed = sign_cancel_action(
                self.wallet_address,
                self.private_key,
                action,
                None
            )
            payload = {"action": signed}
        except Exception:
            payload = {"action": action}
        
        result = await self._sessionless_submit_(endpoint, payload)
        await self.close_session()
        return result

    async def cancel_all(self) -> Union[Dict, None]:
        """
        Asynchronously cancels all orders for the trading symbol on Hyperliquid.

        Returns
        -------
        Union[Dict, None]
            The response from Hyperliquid's API if all orders are successfully canceled; otherwise, None.
        """
        endpoint = self.endpoints.EXCHANGE
        payload = self.formats.create_cancel_all()
        return await self._submit_(endpoint, payload)
    
    async def close_session(self) -> None:
        """
        Asynchronously close the current session
        """
        await self.session.close()

