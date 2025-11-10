import json
from src.sharedstate import SharedState


class HyperliquidPublicWs:
    """
    Manages the WebSocket connection for Hyperliquid's public streams, handling subscription requests.

    Attributes
    ----------
    ss : SharedState
        An instance of SharedState for managing shared application data.
    symbol : str
        The trading symbol in uppercase, extracted from SharedState.

    Methods
    -------
    multi_stream_request(topics: list, **kwargs) -> tuple:
        Generates a WebSocket subscription request for a list of topics.
    """

    def __init__(self, ss: SharedState) -> None:
        """
        Initializes the HyperliquidPublicWs with a reference to SharedState and sets the trading symbol.

        Parameters
        ----------
        ss : SharedState
            The shared state instance for managing application data.
        """
        self.ss = ss
        self.symbol = (getattr(ss, 'hyperliquid_symbol', None) or getattr(ss, 'bybit_symbol', None) or "").upper()

    def multi_stream_request(self, topics: list, **kwargs) -> tuple:
        """
        Constructs and returns a WebSocket request for subscribing to specified public topics.

        Hyperliquid WebSocket uses a different format than Bybit - it subscribes via messages.

        Parameters
        ----------
        topics : list
            A list of topics to subscribe to.
        **kwargs : dict
            Additional keyword arguments for specific topics, such as 'depth' for Orderbook.

        Returns
        -------
        tuple
            A tuple containing the subscription request as a JSON string and a list of topics.
        """
        # Hyperliquid WebSocket subscription format
        # Format: {"method": "subscribe", "subscription": {...}}
        subscriptions = []
        topic_list = []
        
        for topic in topics:
            if topic == "Orderbook":
                depth = kwargs.get("depth", 500)
                subscriptions.append({
                    "type": "l2Book",
                    "coin": self.symbol
                })
                topic_list.append(f"l2Book-{self.symbol}")
            elif topic == "BBA":
                subscriptions.append({
                    "type": "l2Book",
                    "coin": self.symbol
                })
                topic_list.append(f"bba-{self.symbol}")
            elif topic == "Trades":
                subscriptions.append({
                    "type": "trades",
                    "coin": self.symbol
                })
                topic_list.append(f"trades-{self.symbol}")
            elif topic == "Ticker":
                subscriptions.append({
                    "type": "ticker",
                    "coin": self.symbol
                })
                topic_list.append(f"ticker-{self.symbol}")
            elif topic == "Kline":
                interval = kwargs.get("interval", 1)
                subscriptions.append({
                    "type": "candle",
                    "coin": self.symbol,
                    "interval": f"{interval}m"
                })
                topic_list.append(f"candle-{self.symbol}-{interval}m")
        
        # Hyperliquid uses a single subscription message
        req = json.dumps({
            "method": "subscribe",
            "subscription": subscriptions[0] if len(subscriptions) == 1 else subscriptions
        })
        
        return req, topic_list

