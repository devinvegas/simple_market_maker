import numpy as np
from numpy.typing import NDArray
from typing import List, Tuple
from src.utils.rounding import round_step
from src.utils.jit_funcs import nblinspace, nbgeomspace, nbround, nbabs, nbclip
from src.strategy.features.generate import Features
from src.sharedstate import SharedState


class MarketMaker:
    """
    Implements market making strategies including quote generation based on skew,
    spread adjustment for volatility, and order size calculations.

    Attributes
    ----------
    ss : SharedState
        Shared application state containing configuration and market data.
    features : Features
        A class instance for calculating market features like skew.
    tick_size : float
        The minimum price movement of an asset.
    lot_size : float
        The minimum quantity movement of an asset.
    spread : float
        The adjusted spread based on market volatility.

    Methods
    -------
    _skew_() -> Tuple[float, float]:
        Calculates bid and ask skew based on inventory and market conditions.
    _adjusted_spread_() -> float:
        Adjusts the base spread according to market volatility.
    _prices_(bid_skew: float, ask_skew: float) -> Tuple[np.ndarray, np.ndarray]:
        Generates bid and ask prices based on market conditions and skew.
    _sizes_(bid_skew: float, ask_skew: float) -> Tuple[np.ndarray, np.ndarray]:
        Calculates the sizes for bid and ask orders based on skew.
    generate_quotes() -> List[Tuple[str, float, float]]:
        Generates a list of quotes to be submitted to the exchange.
    """

    max_orders = 8  # total across both sides (kept for backward compat)

    def __init__(self, ss: SharedState) -> None:
        self.ss = ss
        self.features = Features(self.ss)
        # Cap quotes per side (default 2)
        self.quotes_per_side = int(getattr(self.ss, "max_quotes_per_side", 2))
        # Keep max_orders consistent with per-side cap
        self.max_orders = max(2 * self.quotes_per_side, 2)
        # Support both Bybit and Hyperliquid
        if hasattr(ss, 'primary_exchange') and ss.primary_exchange == "HYPERLIQUID":
            self.tick_size = self.ss.hyperliquid_tick_size
            self.lot_size = self.ss.hyperliquid_lot_size
        else:
            self.tick_size = self.ss.bybit_tick_size
            self.lot_size = self.ss.bybit_lot_size
        self.spread = self._adjusted_spread_()

    def _skew_(self) -> Tuple[float, float]:
        """
        Calculates the skew for bid and ask orders based on the current inventory level and generated skew value.

        Steps:
        1. Generate a base skew value from market features.
        2. Adjust the skew based on the current inventory level to encourage balancing.
        3. Limit skew adjustment to prevent extreme order placement if inventory is beyond predefined thresholds.
        
        Returns
        -------
        Tuple[float, float]
            The absolute values of bid and ask skew, ensuring they are positive.
        """
        skew = self.features.generate_skew()
        skew = nbround(skew, 2) # NOTE: Temporary, prevents heavy OMS use

        # Set the initial values
        bid_skew = nbclip(skew, 0, 1)
        ask_skew = nbclip(skew, -1, 0)  

        # Adjust for current inventory delta 
        bid_skew += self.ss.inventory_delta if self.ss.inventory_delta < 0 else 0
        ask_skew -= self.ss.inventory_delta if self.ss.inventory_delta > 0 else 0

        # Clip values if inventory reaches extreme levels
        bid_skew = bid_skew if self.ss.inventory_delta > -self.ss.inventory_extreme else 1
        ask_skew = ask_skew if self.ss.inventory_delta < self.ss.inventory_extreme else 1
        
        # Edge case where skew is extreme for no apparent reason (0 delta is rare here)
        if (bid_skew == 1 or ask_skew == 1) and (self.ss.inventory_delta == 0):
            return 0, 0
        
        return nbabs(bid_skew), nbabs(ask_skew)

    def _adjusted_spread_(self) -> float:
        """
        Adjusts the base spread of orders based on current market volatility.

        Steps:
        1. Calculate a multiplier based on the current volatility and mid price.
        2. Adjust the base spread by this multiplier, within a clipped range to prevent extreme spreads.

        Returns
        -------
        float
            The adjusted spread value.
        """
        # Get mid price based on primary exchange
        if hasattr(self.ss, 'primary_exchange') and self.ss.primary_exchange == "HYPERLIQUID":
            mid_price = self.ss.hyperliquid_mid
        else:
            mid_price = self.ss.bybit_mid
        
        if mid_price == 0:
            return self.ss.base_spread  # Fallback to base spread
        
        multiplier = (self.ss.volatility_value * 100) / mid_price
        return self.ss.base_spread * nbclip(multiplier, 1, 10)

    def _prices_(self, bid_skew: float, ask_skew: float) -> Tuple[NDArray, NDArray]:
        """
        Generates a list of bid and ask prices based on market conditions and skew.

        Steps:
        1. Determine base bid and ask prices from the current BBA.
        2. Adjust the prices based on the skew to generate a range for orders.
        3. Create linearly or geometrically spaced prices within this range.

        Parameters
        ----------
        bid_skew : float
            The skew value for bid orders.
        ask_skew : float
            The skew value for ask orders.

        Returns
        -------
        Tuple[np.ndarray, np.ndarray]
            Arrays of bid and ask prices.
        """
        # Get BBA based on primary exchange
        if hasattr(self.ss, 'primary_exchange') and self.ss.primary_exchange == "HYPERLIQUID":
            best_bid, best_ask = self.ss.hyperliquid_bba[:, 0]
        else:
            best_bid, best_ask = self.ss.bybit_bba[:, 0]

        # Inventory is too short, dont quote asks
        if bid_skew >= 1:
            bid_lower = best_bid - (self.spread * self.max_orders)
            bid_prices = nblinspace(best_bid, bid_lower, self.max_orders)
            return bid_prices, None
        
        # Inventory is too long, dont quote bids
        elif ask_skew >= 1:
            ask_upper = best_ask + (self.spread * self.max_orders)
            ask_prices = nblinspace(best_ask, ask_upper, self.max_orders)
            return None, ask_prices

        # If skew is normal, quote both sides
        elif bid_skew >= ask_skew:
            best_bid = best_ask - self.spread * 0.33
            best_ask = best_bid + self.spread * 0.67       

        elif bid_skew < ask_skew:
            best_ask = best_bid + self.spread * 0.33
            best_bid = best_ask - self.spread * 0.67 
        
        base_range = self.ss.volatility_value/2
        bid_lower = best_bid - (base_range * (1 - bid_skew))
        ask_upper = best_ask + (base_range * (1 - ask_skew))
            
        bid_prices = nbgeomspace(best_bid, bid_lower, self.quotes_per_side) + self.ss.price_offset
        ask_prices = nbgeomspace(best_ask, ask_upper, self.quotes_per_side) + self.ss.price_offset

        # Ensure prices are positive and respect tick size
        if self.tick_size and self.tick_size > 0:
            bid_prices = np.maximum(bid_prices, self.tick_size)
            ask_prices = np.maximum(ask_prices, self.tick_size)
        else:
            bid_prices = np.maximum(bid_prices, 1e-12)
            ask_prices = np.maximum(ask_prices, 1e-12)

        return bid_prices, ask_prices

    def _sizes_(self, bid_skew: float, ask_skew: float) -> Tuple[NDArray, NDArray]:
        """
        Calculates order sizes for bid and ask orders, adjusting based on skew and inventory levels.

        Steps:
        1. Set increased sizes for orders closer to the current price to entice trades that balance inventory.
        2. Decrease sizes for orders further from the current price to manage risk.

        Parameters
        ----------
        bid_skew : float
            The skew value for bid orders.
        ask_skew : float
            The skew value for ask orders.

        Returns
        -------
        Tuple[np.ndarray, np.ndarray]
            Arrays of sizes for bid and ask orders.
        """
        # Inventory is too short, dont quote asks
        if bid_skew >= 1:
            bid_sizes = np.full(
                shape=self.max_orders, 
                fill_value=np.median([self.ss.min_order_size, self.ss.max_order_size / 2])
            )
            return bid_sizes, None
        
        # Inventory is too long, dont quote bids
        elif ask_skew >= 1:
            ask_sizes = np.full(
                shape=self.max_orders, 
                fill_value=np.median([self.ss.min_order_size, self.ss.max_order_size / 2])
            )
            return None, ask_sizes

        # Increased size near best bid, decreased size near furthest bid
        bid_min = self.ss.min_order_size * (1 + bid_skew**0.5)
        bid_upper = self.ss.max_order_size * (1 - bid_skew)

        # Increased size near best ask, decreased size near furthest ask
        ask_min = self.ss.min_order_size * (1 + ask_skew**0.5)
        ask_upper = self.ss.max_order_size * (1 - ask_skew)

        bid_sizes = nbgeomspace(
            start=bid_min if bid_skew >= ask_skew else self.ss.min_order_size, 
            end=bid_upper, 
            n=self.max_orders/2
        ) + self.ss.size_offset

        ask_sizes = nbgeomspace(
            start=ask_min if ask_skew >= bid_skew else self.ss.min_order_size, 
            end=ask_upper, 
            n=self.max_orders/2
        ) + self.ss.size_offset

        return bid_sizes, ask_sizes

    def generate_quotes(self, debug=False) -> List[Tuple[str, float, float]]:
        """
        Generates a list of market making quotes to be placed on the exchange.

        Steps:
        1. Calculate skew values to determine the direction of inventory adjustment.
        3. Generate prices and sizes for both bid and ask orders.
        4. Aggregate and return the quotes for submission.

        Returns
        -------
        List[Tuple[str, float, float]]
            A list of quotes, where each quote is a tuple containing the side, price, and size.
        """
        bid_skew, ask_skew = self._skew_()
        bid_prices, ask_prices = self._prices_(bid_skew, ask_skew)
        bid_sizes, ask_sizes = self._sizes_(bid_skew, ask_skew)

        # Hard inventory safety: strongly bias away from the heavy side
        inv = getattr(self.ss, "inventory_delta", 0.0)
        inv_ext = getattr(self.ss, "inventory_extreme", 0.5)
        # If long beyond half-threshold: suppress bids
        if inv > (inv_ext * 0.6):
            bid_prices, bid_sizes = None, None
        # If short beyond half-threshold: suppress asks
        if inv < -(inv_ext * 0.6):
            ask_prices, ask_sizes = None, None

        # If current position is long at all, prefer quoting asks only; if short, bids only
        pos_szi = float(getattr(self.ss, "position_szi", 0.0) or 0.0)
        if pos_szi > 0 and bid_prices is not None:
            bid_prices, bid_sizes = None, None
        elif pos_szi < 0 and ask_prices is not None:
            ask_prices, ask_sizes = None, None

        # Fallback: ensure we always quote both sides near mid when not suppressed
        if (bid_prices is None or ask_prices is None) and (inv <= (inv_ext * 0.6) and inv >= -(inv_ext * 0.6)):
            # symmetric fallback around current mid
            if hasattr(self.ss, 'primary_exchange') and self.ss.primary_exchange == "HYPERLIQUID":
                mid = float(self.ss.hyperliquid_mid)
            else:
                mid = float(self.ss.bybit_mid)
            if mid > 0:
                half = max(self.spread * 0.5, self.tick_size if self.tick_size else 0.0)
                # generate compact symmetric ladders
                n = self.quotes_per_side
                if bid_prices is None:
                    bid_prices = nblinspace(mid - half, mid - self.tick_size, n) if n > 0 else None
                if ask_prices is None:
                    ask_prices = nblinspace(mid + self.tick_size, mid + half, n) if n > 0 else None
                if bid_sizes is None and isinstance(ask_sizes, np.ndarray):
                    bid_sizes = ask_sizes.copy()
                if ask_sizes is None and isinstance(bid_sizes, np.ndarray):
                    ask_sizes = bid_sizes.copy()

        bids, asks = [], []

        if isinstance(bid_prices, np.ndarray):
            bids = []
            for price, size in zip(bid_prices, bid_sizes):
                px = round_step(price, self.tick_size)
                # Auto-guard: ensure USD notional >= min_order_notional_usd
                if px > 0:
                    min_qty_by_usd = self.ss.min_order_notional_usd / px
                    # Round up to lot size
                    lot = self.lot_size if self.lot_size > 0 else 1.0
                    # Ceil to nearest lot step
                    min_qty_steps = int(np.ceil(min_qty_by_usd / lot))
                    min_qty = max(self.ss.min_order_size, min_qty_steps * lot)
                else:
                    min_qty = self.ss.min_order_size
                qty = max(size, min_qty)
                qty = round_step(qty, lot)
                bids.append(["Buy", px, qty])
        
        if isinstance(ask_prices, np.ndarray):
            asks = []
            for price, size in zip(ask_prices, ask_sizes):
                px = round_step(price, self.tick_size)
                if px > 0:
                    min_qty_by_usd = self.ss.min_order_notional_usd / px
                    lot = self.lot_size if self.lot_size > 0 else 1.0
                    min_qty_steps = int(np.ceil(min_qty_by_usd / lot))
                    min_qty = max(self.ss.min_order_size, min_qty_steps * lot)
                else:
                    min_qty = self.ss.min_order_size
                qty = max(size, min_qty)
                qty = round_step(qty, lot)
                asks.append(["Sell", px, qty])

        # Clamp quotes to a reasonable band around mid to avoid exchange 422 on absurd prices
        try:
            if hasattr(self.ss, 'primary_exchange') and self.ss.primary_exchange == "HYPERLIQUID":
                mid = float(self.ss.hyperliquid_mid)
            else:
                mid = float(self.ss.bybit_mid)
        except Exception:
            mid = 0.0

        if mid and mid > 0:
            max_dev = 0.2  # 20% band
            lower = mid * (1 - max_dev)
            upper = mid * (1 + max_dev)
            bids = [b for b in bids if lower <= b[1] <= mid]
            asks = [a for a in asks if mid <= a[1] <= upper]

        if debug:
            print("-----------------------------")
            print(f"Skews: {bid_skew} |  {ask_skew}")
            print(f"Inventory: {self.ss.inventory_delta}")
            print(f"Bids: {bids}")
            print(f"Asks: {asks}")

        return bids + asks, self.spread