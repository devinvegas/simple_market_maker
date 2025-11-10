import json
import hmac
import hashlib
from typing import List, Tuple
from src.utils.misc import time_ms


class HyperliquidPrivateWs:
    """
    Manages the WebSocket connection for Hyperliquid's private streams, including authentication.

    Attributes
    ----------
    wallet_address : str
        The wallet address for authentication.
    private_key : str
        The private key for signing authentication messages.

    Methods
    -------
    authentication() -> str:
        Generates an authentication payload for a private WebSocket connection.
    multi_stream_request(topics: List[str]) -> Tuple[str, List[str]]:
        Creates a WebSocket request for subscribing to multiple topics.
    """

    def __init__(self, wallet_address: str, private_key: str) -> None:
        """
        Initializes the HyperliquidPrivateWs with wallet credentials.

        Parameters
        ----------
        wallet_address : str
            The wallet address for Hyperliquid.
        private_key : str
            The private key for signing.
        """
        self.wallet_address = wallet_address
        self.private_key = private_key

    def authentication(self) -> str:
        """
        Constructs the authentication payload for establishing a private WebSocket connection.

        Note: Hyperliquid may use different authentication - this is a placeholder
        that may need adjustment based on actual API requirements.

        Returns
        -------
        str
            The authentication payload as a JSON string.
        """
        # Hyperliquid authentication format may differ
        # This is a placeholder - actual implementation depends on Hyperliquid's WebSocket auth
        timestamp = str(time_ms())
        
        # Create signature (format may need adjustment)
        message = f"{self.wallet_address}{timestamp}"
        signature = hmac.new(
            key=bytes(self.private_key, "utf-8"),
            msg=bytes(message, "utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        return json.dumps({
            "method": "auth",
            "wallet": self.wallet_address,
            "timestamp": timestamp,
            "signature": signature
        })

    def multi_stream_request(self, topics: List[str]) -> Tuple[str, List[str]]:
        """
        Generates a request for subscribing to multiple private topics.

        Parameters
        ----------
        topics : List[str]
            A list of topics to subscribe to, such as "Position", "Execution", and "Order".

        Returns
        -------
        Tuple[str, List[str]]
            A tuple containing the subscription request as a JSON string and a list of topics.
        """
        subscriptions = []
        topic_list = []
        
        for topic in topics:
            if topic == "Position":
                subscriptions.append({
                    "type": "userUpdates",
                    "user": self.wallet_address
                })
                topic_list.append("position")
            elif topic == "Execution":
                subscriptions.append({
                    "type": "userUpdates",
                    "user": self.wallet_address
                })
                topic_list.append("execution")
            elif topic == "Order":
                subscriptions.append({
                    "type": "userUpdates",
                    "user": self.wallet_address
                })
                topic_list.append("order")

        req = json.dumps({
            "method": "subscribe",
            "subscription": subscriptions[0] if len(subscriptions) == 1 else subscriptions
        })
        
        return req, topic_list

