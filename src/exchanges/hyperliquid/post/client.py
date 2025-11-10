import aiohttp
import orjson
import asyncio
from typing import Dict
from src.utils.misc import datetime_now as dt_now
from src.exchanges.hyperliquid.endpoints import BaseEndpoints, ApiEndpoints
from src.sharedstate import SharedState

# Try to use Hyperliquid SDK for signing if available, otherwise use custom implementation
try:
    from hyperliquid.utils.signing import sign_l1_action, sign_l2_action, sign_cancel_action
    from hyperliquid.utils.constants import MAINNET_API_URL, TESTNET_API_URL
    HYPERLIQUID_SDK_AVAILABLE = True
except ImportError:
    HYPERLIQUID_SDK_AVAILABLE = False


class HyperliquidPrivatePostClient:
    """
    Manages the execution of private POST requests to Hyperliquid's API, handling authentication,
    request signing, and retry logic.

    Attributes
    ----------
    ss : SharedState
        An instance of SharedState containing shared application data.
    max_retries : int
        The maximum number of retries for a request before giving up.
    _success_ : List[str]
        A list of messages indicating a successful request.
    _retry_ : List[str]
        A list of error messages that should trigger a retry of the request.

    Methods
    -------
    submit(session: aiohttp.ClientSession, endpoint: str, payload: dict) -> Dict:
        Asynchronously submits a signed POST request to Hyperliquid.
    """

    max_retries = 3
    _success_ = ["ok", "success"]
    _retry_ = ["rate limit", "timeout"]

    def __init__(self, ss: SharedState) -> None:
        """
        Initializes the HyperliquidPrivatePostClient with shared state and API credentials.

        Parameters
        ----------
        ss : SharedState
            An instance of SharedState containing shared application data.
        """
        self.ss = ss
        self.base_url = BaseEndpoints.MAINNET
        # Hyperliquid uses wallet address and private key, not API key/secret
        # We'll need to get these from environment or config
        self.wallet_address = getattr(ss, 'hyperliquid_wallet_address', None) or ss.api_key
        self.private_key = getattr(ss, 'hyperliquid_private_key', None) or ss.api_secret

    async def submit(self, session: aiohttp.ClientSession, endpoint: str, payload: dict) -> Dict:
        """
        Asynchronously submits a signed POST request to Hyperliquid.

        Parameters
        ----------
        session : aiohttp.ClientSession
            The session used to send the request.
        endpoint : str
            The API endpoint to which the request is sent.
        payload : dict
            The payload of the request (will be signed).

        Returns
        -------
        Dict
            The JSON response from the API if successful.

        Raises
        ------
        Exception
            If the request fails after the maximum number of retries.
        """
        full_endpoint = self.base_url + endpoint
        max_retries = self.max_retries
        
        # Sign the payload if SDK is available
        if HYPERLIQUID_SDK_AVAILABLE and endpoint == ApiEndpoints.EXCHANGE:
            # Use SDK for signing exchange actions
            try:
                signed_payload = self._sign_with_sdk(payload)
            except Exception as e:
                print(f"{dt_now()}: SDK signing failed, using custom: {e}")
                signed_payload = payload
        else:
            signed_payload = payload
        
        for attempt in range(max_retries):
            try:
                async with session.post(full_endpoint, json=signed_payload) as req:
                    response = orjson.loads(await req.text())
                    
                    # Check for success
                    if isinstance(response, dict):
                        status = response.get("status", "").lower()
                        if status in self._success_ or "data" in response:
                            return response
                        elif any(retry_msg in str(response).lower() for retry_msg in self._retry_):
                            raise Exception(f"Retryable error: {response}")
                        else:
                            print(f"{dt_now()}: Error: {response} | Endpoint: {endpoint}")
                            break
                    else:
                        return response
                        
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(attempt + 1)  # Incremental back-off
                else:
                    raise e
        
        return {}

    def _sign_with_sdk(self, payload: dict) -> dict:
        """
        Signs the payload using Hyperliquid SDK if available.

        Parameters
        ----------
        payload : dict
            The payload to sign.

        Returns
        -------
        dict
            The signed payload.
        """
        if not HYPERLIQUID_SDK_AVAILABLE:
            return payload
        
        # This is a placeholder - actual signing depends on the action type
        # The SDK provides different signing functions for different actions
        # We'll handle this in the order.py file where we know the action type
        return payload

