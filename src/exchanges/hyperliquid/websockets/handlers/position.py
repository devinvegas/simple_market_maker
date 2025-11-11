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
        if recv is None or "data" not in recv:
            return

        data = recv["data"]
        positions = data.get("assetPositions", data.get("positions", []))
        if not positions:
            return

        # Try to select the matching coin for our symbol
        target_name = getattr(self.ss, "hyperliquid_symbol", "").upper()
        target_key = getattr(self.ss, "hyperliquid_coin_key", None)

        chosen = None
        for pos in positions if isinstance(positions, list) else [positions]:
            coin_name = pos.get("position", {}).get("coin", pos.get("coin", ""))
            if coin_name and (
                coin_name.upper() == target_name or (target_key and coin_name == target_key)
            ):
                chosen = pos
                break

        if chosen is None:
            # Fallback to the first position entry
            chosen = positions[0] if isinstance(positions, list) else positions

        self.process(chosen)

    def process(self, data: Union[Dict, List]) -> None:
        """
        Processes position updates and updates inventory delta.

        Parameters
        ----------
        data : Union[Dict, List]
            Position data from WebSocket or REST API.
        """
        # Normalize into dict
        if isinstance(data, list):
            data = data[0] if data else {}
        if not data:
            return

        # Hyperliquid position schema: data or data["position"]
        pos = data.get("position", data)

        # Signed size (contracts)
        try:
            szi = float(pos.get("szi", pos.get("size", 0)) or 0)
        except Exception:
            szi = 0.0
        # Persist signed size for strategy-level decisions
        try:
            self.ss.position_szi = szi
        except Exception:
            pass

        # Use current mid; fallback to markPx/entryPx from position
        mid = float(getattr(self.ss, "hyperliquid_mid", 0) or 0)
        if mid <= 0:
            try:
                mid = float(pos.get("markPx", pos.get("entryPx", 0)) or 0)
            except Exception:
                mid = 0.0

        if mid <= 0:
            return

        # Notional and leverage
        notional = abs(szi) * mid
        lev_obj = pos.get("leverage", {})
        try:
            leverage = float(lev_obj.get("value", lev_obj.get("leverage", 1)) or 1)
        except Exception:
            leverage = 1.0

        # Side from signed size
        side = "Buy" if szi > 0 else ("Sell" if szi < 0 else "")
        if side:
            self.inventory.position_delta(side, notional, leverage)

