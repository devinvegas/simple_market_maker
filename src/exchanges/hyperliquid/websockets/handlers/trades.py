import numpy as np
from typing import Dict, List
from src.sharedstate import SharedState


class HyperliquidTradesHandler:
    """
    Handler for processing trades data from Hyperliquid and updating the shared state.

    Attributes
    ----------
    ss : SharedState
        An instance of SharedState for storing and managing trades data.

    Methods
    -------
    initialize(data: List[Dict]) -> None:
        Initializes the handler with historical trades data.
    process(recv: Dict) -> None:
        Processes real-time trades data received from Hyperliquid.
    """

    def __init__(self, ss: SharedState) -> None:
        """
        Initializes the HyperliquidTradesHandler with a reference to SharedState.

        Parameters
        ----------
        ss : SharedState
            The shared state instance for managing trades data.
        """
        self.ss = ss

    def initialize(self, data: List[Dict]) -> None:
        """
        Initializes the shared state with historical trades data.

        Parameters
        ----------
        data : List[Dict]
            A list of dictionaries, each representing a trade with time, price, size, and side information.
        """
        for row in data:
            time = float(row.get("time", row.get("timestamp", 0)))
            price = float(row.get("price", row.get("px", 0)))
            qty = float(row.get("size", row.get("sz", 0)))
            # Hyperliquid may use different side format
            side_str = row.get("side", row.get("S", "Buy"))
            side = 0.0 if side_str == "Buy" or side_str == "B" else 1.0
            new_trade = np.array([[time, side, price, qty]])
            self.ss.hyperliquid_trades.append(new_trade)

    def process(self, recv: Dict) -> None:
        """
        Processes and updates the shared state with real-time trades data received from Hyperliquid.

        Parameters
        ----------
        recv : Dict
            A dictionary containing trade data.
        """
        # Hyperliquid format may differ - adjust based on actual API
        if "data" in recv:
            trades = recv["data"] if isinstance(recv["data"], list) else [recv["data"]]
            for trade in trades:
                time = float(trade.get("time", trade.get("timestamp", 0)))
                price = float(trade.get("price", trade.get("px", 0)))
                qty = float(trade.get("size", trade.get("sz", 0)))
                side_str = trade.get("side", trade.get("S", "Buy"))
                side = 0.0 if side_str == "Buy" or side_str == "B" else 1.0
                new_trade = np.array([[time, side, price, qty]])
                self.ss.hyperliquid_trades.append(new_trade)

