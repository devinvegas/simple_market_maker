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
                def to_level(e):
                    try:
                        if isinstance(e, (list, tuple)) and len(e) >= 2:
                            return float(e[0]), float(e[1])
                        if isinstance(e, dict):
                            px = e.get("px", e.get("price", e.get("p", 0)))
                            sz = e.get("sz", e.get("size", e.get("q", 0)))
                            return float(px), float(sz)
                    except Exception:
                        return None
                    return None

                asks_lvls = [to_level(a) for a in data["asks"]]
                bids_lvls = [to_level(b) for b in data["bids"]]
                asks = np.array([[p, q] for p, q in asks_lvls if p and q and p > 0 and q > 0], dtype=float)
                bids = np.array([[p, q] for p, q in bids_lvls if p and q and p > 0 and q > 0], dtype=float)
                
                if recv.get("type", "").lower() == "snapshot" or "snapshot" in str(recv).lower():
                    self.process_snapshot(asks, bids)
                else:
                    # Delta update
                    if asks.size > 0:
                        self.asks = self.update_book(self.asks, asks)
                    if bids.size > 0:
                        self.bids = self.update_book(self.bids, bids)
                    self.sort_book()
            # Alternate HL shape: levels as [asks[], bids[]] OR flat list with side flags
            elif "levels" in data:
                levels = data.get("levels", [])
                # Case 1: nested two lists [asks[], bids[]]
                if isinstance(levels, list) and len(levels) >= 1 and isinstance(levels[0], list):
                    asks_in = levels[0] if len(levels) >= 1 else []
                    bids_in = levels[1] if len(levels) >= 2 else []
                    def to_pq(obj):
                        try:
                            if isinstance(obj, dict):
                                px = float(obj.get("px", obj.get("price", obj.get("p", 0))))
                                sz = float(obj.get("sz", obj.get("size", obj.get("q", 0))))
                                return px, sz
                            if isinstance(obj, (list, tuple)) and len(obj) >= 2:
                                return float(obj[0]), float(obj[1])
                        except Exception:
                            return None
                        return None
                    asks_arr = [to_pq(o) for o in asks_in]
                    bids_arr = [to_pq(o) for o in bids_in]
                    asks = np.array([[p, q] for pq in asks_arr if pq for p, q in [pq] if p > 0 and q > 0], dtype=float)
                    bids = np.array([[p, q] for pq in bids_arr if pq for p, q in [pq] if p > 0 and q > 0], dtype=float)
                    if asks.size or bids.size:
                        # Treat as snapshot on first population
                        if self.asks.size == 0 and self.bids.size == 0:
                            self.process_snapshot(asks if asks.size else self.asks, bids if bids.size else self.bids)
                        else:
                            if asks.size > 0:
                                self.asks = self.update_book(self.asks, asks)
                            if bids.size > 0:
                                self.bids = self.update_book(self.bids, bids)
                            self.sort_book()
                    return
                # Case 2: flat "levels" with side flags
                levels = data.get("levels", [])
                bids_list, asks_list = [], []
                for lv in levels:
                    try:
                        if isinstance(lv, (list, tuple)):
                            # Possible shapes: [px, sz, isBid] or [px, sz, "bid"/"ask"]
                            px = float(lv[0]); sz = float(lv[1])
                            side_flag = lv[2] if len(lv) > 2 else True
                            is_bid = (str(side_flag).lower() in ("1", "true", "bid"))
                        elif isinstance(lv, dict):
                            px = float(lv.get("px", lv.get("price", lv.get("p", 0))))
                            sz = float(lv.get("sz", lv.get("size", lv.get("q", 0))))
                            sf = lv.get("isBid", lv.get("side", True))
                            is_bid = (str(sf).lower() in ("1", "true", "bid"))
                        else:
                            continue
                        if px > 0 and sz > 0:
                            if is_bid:
                                bids_list.append([px, sz])
                            else:
                                asks_list.append([px, sz])
                    except Exception:
                        continue
                bids = np.array(bids_list, dtype=float) if bids_list else np.empty((0, 2))
                asks = np.array(asks_list, dtype=float) if asks_list else np.empty((0, 2))
                if bids.size or asks.size:
                    # Treat absence on one side as no updates for that side; update accordingly
                    if self.asks.size == 0 and asks.size > 0:
                        self.asks = asks
                    elif asks.size > 0:
                        self.asks = self.update_book(self.asks, asks)
                    if self.bids.size == 0 and bids.size > 0:
                        self.bids = bids
                    elif bids.size > 0:
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
            def parse_level(e):
                try:
                    if isinstance(e, (list, tuple)) and len(e) >= 2:
                        return float(e[0]), float(e[1])
                    if isinstance(e, dict):
                        px = e.get("px", e.get("price", e.get("p", 0)))
                        sz = e.get("sz", e.get("size", e.get("q", 0)))
                        return float(px), float(sz)
                except Exception:
                    return None
                return None

            if "bids" in data and len(data["bids"]) > 0:
                lvl = parse_level(data["bids"][0])
                if lvl:
                    price, qty = lvl
                    if qty > 0 and price > 0:
                        self.ss.hyperliquid_bba[0, 0] = price
                        self.ss.hyperliquid_bba[0, 1] = qty
                        try:
                            from src.utils.misc import datetime_now as dt_now
                            print(f"{dt_now()}: BBA update | best_bid={price} qty={qty}")
                        except Exception:
                            pass

            if "asks" in data and len(data["asks"]) > 0:
                lvl = parse_level(data["asks"][0])
                if lvl:
                    price, qty = lvl
                    if qty > 0 and price > 0:
                        self.ss.hyperliquid_bba[1, 0] = price
                        self.ss.hyperliquid_bba[1, 1] = qty
                        try:
                            from src.utils.misc import datetime_now as dt_now
                            print(f"{dt_now()}: BBA update | best_ask={price} qty={qty}")
                        except Exception:
                            pass

            # Alternate "levels" structure: [asks[], bids[]]
            if "levels" in data and isinstance(data["levels"], list) and len(data["levels"]) >= 1 and isinstance(data["levels"][0], list):
                asks_in = data["levels"][0] if len(data["levels"]) >= 1 else []
                bids_in = data["levels"][1] if len(data["levels"]) >= 2 else []
                def best_from(arr, choose_max=False):
                    best_px, best_qty = (0.0, 0.0)
                    for e in arr:
                        lvl = parse_level(e)
                        if not lvl:
                            continue
                        px, qty = lvl
                        if qty <= 0 or px <= 0:
                            continue
                        if best_px == 0.0:
                            best_px, best_qty = px, qty
                        else:
                            if choose_max and px > best_px:
                                best_px, best_qty = px, qty
                            if not choose_max and px < best_px:
                                best_px, best_qty = px, qty
                    return best_px, best_qty
                # For bids, choose max px; for asks, choose min px
                bid_px, bid_qty = best_from(bids_in, choose_max=True)
                ask_px, ask_qty = best_from(asks_in, choose_max=False)
                if bid_px > 0:
                    self.ss.hyperliquid_bba[0, 0] = bid_px
                    self.ss.hyperliquid_bba[0, 1] = bid_qty
                if ask_px > 0:
                    self.ss.hyperliquid_bba[1, 0] = ask_px
                    self.ss.hyperliquid_bba[1, 1] = ask_qty

