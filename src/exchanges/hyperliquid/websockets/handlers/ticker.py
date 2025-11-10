from typing import Dict
from src.sharedstate import SharedState


class HyperliquidTickerHandler:
    """
    Handler for processing ticker updates from Hyperliquid, including mark price.
    """
    
    def __init__(self, ss: SharedState) -> None:
        self.ss = ss

    def process(self, recv: Dict) -> None:
        """
        Processes ticker updates and extracts mark price if available.

        Parameters
        ----------
        recv : Dict
            A dictionary containing ticker data.
        """
        if "data" in recv:
            data = recv["data"]
            # Hyperliquid may use different field names
            if "markPrice" in data:
                self.ss.hyperliquid_mark_price = float(data["markPrice"])
            elif "mark" in data:
                self.ss.hyperliquid_mark_price = float(data["mark"])
            elif "markPrice" in recv:
                self.ss.hyperliquid_mark_price = float(recv["markPrice"])

