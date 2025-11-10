import numpy as np
from typing import Dict, List
from src.exchanges.common.localorderbook import BaseOrderBook


class OrderBookHyperliquid(BaseOrderBook):
    """
    Order book class for Hyperliquid, extending the BaseOrderBook for handling Hyperliquid-specific order book data.

    Methods
    -------
    process_snapshot(asks: List[List[float]], bids: List[List[float]]) -> None:
        Processes the initial snapshot of the order book.
    process(recv: Dict) -> None:
        Processes incoming messages from Hyperliquid to update the order book.
    """

    def process_snapshot(self, asks: List[List[float]], bids: List[List[float]]) -> None:
        """
        Processes and initializes the order book with a snapshot of asks and bids.

        Parameters
        ----------
        asks : List[List[float]]
            A list of ask orders, each represented as [price, quantity].
        bids : List[List[float]]
            A list of bid orders, each represented as [price, quantity].
        """
        self.asks = np.array(asks, dtype=float)
        self.bids = np.array(bids, dtype=float)
        self.sort_book()

    def process(self, recv: Dict) -> None:
        """
        Handles incoming WebSocket messages to update the order book.

        Parameters
        ----------
        recv : Dict
            The incoming message containing order book data.
        """
        # Hyperliquid format may differ - adjust based on actual API
        if "data" in recv:
            data = recv["data"]
            if "asks" in data and "bids" in data:
                asks = np.array([[float(a[0]), float(a[1])] for a in data["asks"]], dtype=float)
                bids = np.array([[float(b[0]), float(b[1])] for b in data["bids"]], dtype=float)
                
                if recv.get("type") == "snapshot" or "snapshot" in str(recv).lower():
                    self.process_snapshot(asks, bids)
                else:
                    # Delta update
                    self.asks = self.update_book(self.asks, asks)
                    self.bids = self.update_book(self.bids, bids)
                    self.sort_book()


class HyperliquidBBAHandler:
    """
    Handler for processing Best Bid and Ask (BBA) updates from Hyperliquid.

    Parameters
    ----------
    ss : SharedState
        An instance of SharedState for managing shared application data.

    Methods
    -------
    process(recv: Dict) -> None:
        Processes real-time BBA updates.
    """

    def __init__(self, ss) -> None:
        """
        Initializes the HyperliquidBBAHandler with a reference to SharedState.

        Parameters
        ----------
        ss : SharedState
            The shared state instance for managing application data.
        """
        self.ss = ss

    def process(self, recv: Dict) -> None:
        """
        Processes real-time updates to the best bid and ask prices and quantities.

        Parameters
        ----------
        recv : Dict
            A dictionary containing the latest BBA prices and quantities.
        """
        # Extract from orderbook or dedicated BBA message
        if "data" in recv:
            data = recv["data"]
            if "bids" in data and len(data["bids"]) > 0:
                best_bid = data["bids"][0]
                price, qty = float(best_bid[0]), float(best_bid[1])
                if qty > 0:
                    self.ss.hyperliquid_bba[0, 0] = price
                    self.ss.hyperliquid_bba[0, 1] = qty

            if "asks" in data and len(data["asks"]) > 0:
                best_ask = data["asks"][0]
                price, qty = float(best_ask[0]), float(best_ask[1])
                if qty > 0:
                    self.ss.hyperliquid_bba[1, 0] = price
                    self.ss.hyperliquid_bba[1, 1] = qty

