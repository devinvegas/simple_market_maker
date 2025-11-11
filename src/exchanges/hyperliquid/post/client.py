import aiohttp
import orjson
import asyncio
from typing import Dict
from src.utils.misc import datetime_now as dt_now
from src.exchanges.hyperliquid.endpoints import BaseEndpoints, ApiEndpoints
from src.sharedstate import SharedState

# Try to use Hyperliquid SDK for signing if available, otherwise use custom implementation
try:
    from hyperliquid.utils.signing import sign_l1_action, get_timestamp_ms
    from hyperliquid.utils.constants import MAINNET_API_URL
    from eth_account import Account
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
        if endpoint == ApiEndpoints.EXCHANGE and not HYPERLIQUID_SDK_AVAILABLE:
            raise Exception("hyperliquid-python-sdk is required for /exchange actions (signing).")

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
                    # Debug: show payload when hitting /exchange (without leaking full signature)
                    if endpoint == ApiEndpoints.EXCHANGE:
                        try:
                            dbg = dict(signed_payload)
                            sig = dbg.get("signature", {})
                            if isinstance(sig, dict):
                                dbg["signature"] = {k: (v[:10] + "..." if isinstance(v, str) else v) for k, v in sig.items()}
                            print(f"{dt_now()}: DEBUG exchange payload: {orjson.dumps(dbg)[:512].decode()}")
                        except Exception:
                            pass

                    # Check status code first
                    if req.status != 200:
                        text = await req.text()
                        print(f"{dt_now()}: HTTP {req.status}: {text} | Endpoint: {endpoint}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(attempt + 1)
                            continue
                        return {"status": "error", "message": text}
                    
                    text = await req.text()
                    if not text:
                        print(f"{dt_now()}: Empty response | Endpoint: {endpoint}")
                        return {}
                    
                    response = orjson.loads(text)
                    
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
                        
            except orjson.JSONDecodeError as json_err:
                print(f"{dt_now()}: JSON decode error: {json_err} | Response: {text[:200] if text else 'empty'}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(attempt + 1)
                else:
                    return {}
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

        # Expect either {"action": {...}} or a raw action dict
        action = payload.get("action", payload)

        # Build wallet from private key
        private_key = getattr(self, "private_key", None)
        if not private_key:
            raise Exception("Hyperliquid private key missing for signing.")
        if not str(private_key).startswith("0x"):
            private_key = "0x" + str(private_key)
        wallet = Account.from_key(private_key)

        # Prepare signing inputs
        nonce = get_timestamp_ms()
        is_mainnet = (self.base_url == MAINNET_API_URL)

        signature = sign_l1_action(
            wallet,
            action,
            None,   # active pool / vault address (None for user wallet)
            nonce,
            None,   # expiresAfter
            is_mainnet
        )

        # Construct full /exchange payload as per SDK
        return {
            "action": action,
            "nonce": nonce,
            "signature": signature,
            "vaultAddress": None,
            "expiresAfter": None,
        }

