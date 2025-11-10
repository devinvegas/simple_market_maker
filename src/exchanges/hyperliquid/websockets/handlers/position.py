from typing import Dict, List, Union
from src.strategy.inventory import Inventory
from src.sharedstate import SharedState


class HyperliquidPositionHandler:
    """
    Handler for processing position updates from Hyperliquid.
    """
    
    def __init__(self, ss: SharedState) -> None:
        self.ss = ss
        self.inventory = Inventory(self.ss)
    
    def sync(self, recv: Dict) -> None:
        """
        Synchronizes position from REST API response.

        Parameters
        ----------
        recv : Dict
            Response from position API call.
        """
        if recv is not None and "data" in recv:
            positions = recv["data"].get("assetPositions", recv["data"].get("positions", []))
            if positions:
                self.process(positions[0] if isinstance(positions, list) else positions)

    def process(self, data: Union[Dict, List]) -> None:
        """
        Processes position updates and updates inventory delta.

        Parameters
        ----------
        data : Union[Dict, List]
            Position data from WebSocket or REST API.
        """
        if isinstance(data, list):
            data = data[0] if data else {}

        if not data:
            return

        # Extract position information
        # Hyperliquid format may differ - adjust based on actual API
        side = data.get("side", data.get("position", {}).get("side", ""))
        value = float(data.get("positionValue", data.get("value", data.get("notional", 0))))
        leverage = float(data.get("leverage", data.get("leverage", 1)))

        if side:
            self.inventory.position_delta(side, value, leverage)

