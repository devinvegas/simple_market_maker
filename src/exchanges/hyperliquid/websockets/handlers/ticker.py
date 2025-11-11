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
        # Robust extraction of mark/reference price from multiple possible fields
        def _to_float(v):
            try:
                return float(v)
            except Exception:
                return 0.0

        candidates = []
        data = recv.get("data", {})
        top = recv

        # Common fields seen across versions
        keys = [
            "markPx", "markPrice", "mark",
            "midPx", "fairPx", "indexPx",
            "lastPx", "last"
        ]
        for k in keys:
            if k in data:
                candidates.append(_to_float(data.get(k)))
            if k in top:
                candidates.append(_to_float(top.get(k)))

        # Nested price object fallback (e.g., {"price": {"markPx": ...}} )
        price_obj = data.get("price", {}) if isinstance(data.get("price", {}), dict) else {}
        for k in keys:
            if k in price_obj:
                candidates.append(_to_float(price_obj.get(k)))

        # Choose first positive candidate
        for v in candidates:
            if v and v > 0:
                self.ss.hyperliquid_mark_price = v
                try:
                    from src.utils.misc import datetime_now as dt_now
                    print(f"{dt_now()}: TICKER mark update | mark={v}")
                except Exception:
                    pass
                break

