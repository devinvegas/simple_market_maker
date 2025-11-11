from typing import Dict, List

# Try to use Hyperliquid SDK for signing if available
try:
    from hyperliquid.utils.signing import sign_l1_action
    HYPERLIQUID_SDK_AVAILABLE = True
except ImportError:
    HYPERLIQUID_SDK_AVAILABLE = False


class HyperliquidFormats:
    """
    Provides methods to format order payloads according to Hyperliquid's API requirements.

    Attributes
    ----------
    symbol : str
        The trading symbol the orders will be created for.

    Methods
    -------
    create_limit(side: str, price: str, qty: str, reduce_only: bool = False) -> Dict:
        Formats a limit order payload.
    create_market(side: str, qty: str, reduce_only: bool = False) -> Dict:
        Formats a market order payload.
    create_amend(orderId: str, price: str, qty: str) -> Dict:
        Formats a payload for amending an existing order.
    create_cancel(orderId: str) -> Dict:
        Formats a payload for canceling a specific order.
    create_cancel_all() -> Dict:
        Formats a payload for canceling all orders for the symbol.
    """

    def __init__(self, symbol: str, wallet_address: str = None, private_key: str = None, asset_id: int = None) -> None:
        """
        Initializes the HyperliquidFormats class with the trading symbol.

        Parameters
        ----------
        symbol : str
            The trading symbol orders are associated with.
        wallet_address : str, optional
            Wallet address for signing (if using SDK).
        private_key : str, optional
            Private key for signing (if using SDK).
        asset_id : int, optional
            The asset ID (index in universe) for this symbol.
        """
        self.symbol = symbol
        self.wallet_address = wallet_address
        self.private_key = private_key
        self.asset_id = asset_id

    def _is_buy(self, side: str) -> bool:
        """Convert 'Buy'/'Sell' to boolean isBuy as required by wire format"""
        return True if side == "Buy" else False

    def create_limit(self, side: str, price: str, qty: str, reduce_only: bool = False) -> Dict:
        """
        Creates a dictionary payload for a limit order.

        Parameters
        ----------
        side : str
            The side of the order, either "Buy" or "Sell".
        price : str
            The price at which to place the order.
        qty : str
            The quantity of the order.
        reduce_only : bool
            Whether this is a reduce-only order.

        Returns
        -------
        Dict
            A dictionary formatted for a limit order request.
        """
        # Build order wire per SDK: a=assetId, b=isBuy(bool), p=price(str), s=size(str)
        try:
            # Prefer SDK's float_to_wire for safe normalization if available
            from hyperliquid.utils.signing import float_to_wire  # type: ignore
            p_str = float_to_wire(float(price))
            s_str = float_to_wire(float(qty))
        except Exception:
            # Fallback to plain string format
            p_str = f"{float(price):.8f}".rstrip('0').rstrip('.') if '.' in f"{float(price):.8f}" else f"{float(price):.8f}"
            s_str = f"{float(qty):.8f}".rstrip('0').rstrip('.') if '.' in f"{float(qty):.8f}" else f"{float(qty):.8f}"

        action = {
            "type": "order",
            "orders": [{
                "a": int(self.asset_id) if self.asset_id is not None else 0,
                "b": self._is_buy(side),
                "p": p_str,
                "s": s_str,
                "r": reduce_only,
                "t": {"limit": {"tif": "Gtc"}}  # Good till cancel
            }],
            "grouping": "na"
        }
        return {
            "action": action
        }

    def create_market(self, side: str, qty: str, reduce_only: bool = False) -> Dict:
        """
        Creates a dictionary payload for a market order.

        Parameters
        ----------
        side : str
            The side of the order, either "Buy" or "Sell".
        qty : str
            The quantity of the order.
        reduce_only : bool
            Whether this is a reduce-only order.

        Returns
        -------
        Dict
            A dictionary formatted for a market order request.
        """
        # For market, SDK uses aggressive IOC limit; keep "market" type if supported; fallback to IOC
        try:
            from hyperliquid.utils.signing import float_to_wire  # type: ignore
            s_str = float_to_wire(float(qty))
        except Exception:
            s_str = f"{float(qty):.8f}".rstrip('0').rstrip('.') if '.' in f"{float(qty):.8f}" else f"{float(qty):.8f}"

        action = {
            "type": "order",
            "orders": [{
                "a": int(self.asset_id) if self.asset_id is not None else 0,
                "b": self._is_buy(side),
                # Without slippage logic here, use IOC limit semantics with no price -> leave 'p' out
                "s": s_str,
                "r": reduce_only,
                "t": {"limit": {"tif": "Ioc"}}
            }],
            "grouping": "na"
        }
        return {
            "action": action
        }

    def create_amend(self, orderId: str, price: str, qty: str) -> Dict:
        """
        Creates a dictionary payload for amending an existing order.

        Parameters
        ----------
        orderId : str
            The ID of the order to amend.
        price : str
            The new price for the order.
        qty : str
            The new quantity for the order.

        Returns
        -------
        Dict
            A dictionary formatted for an amend order request.
        """
        # Hyperliquid doesn't have direct amend - need to cancel and replace
        # But we'll structure it for batch operations
        return {
            "action": {
                "type": "order",
                "orders": [{
                    "oid": int(orderId),
                    "a": int(float(qty) * 1e6),
                    "b": int(float(price) * 1e6),
                }],
                "grouping": "na"
            }
        }

    def create_cancel(self, orderId: str) -> Dict:
        """
        Creates a dictionary payload for canceling a specific order.

        Parameters
        ----------
        orderId : str
            The ID of the order to cancel.

        Returns
        -------
        Dict
            A dictionary formatted for a cancel order request.
        """
        # Wire format uses asset ID (int) not coin name (str)
        action = {
            "type": "cancel",
            "cancels": [{
                "a": self.asset_id if self.asset_id is not None else 0,
                "o": int(orderId)
            }]
        }
        
        return {
            "action": action
        }

    def create_cancel_all(self) -> Dict:
        """
        Creates a dictionary payload for canceling all orders for the symbol.

        Returns
        -------
        Dict
            A dictionary formatted for a cancel all orders request.
        """
        # Cancel all orders for this asset - wire format uses asset ID
        # Omitting 'o' (order ID) cancels all orders for this asset
        action = {
            "type": "cancel",
            "cancels": [{
                "a": self.asset_id if self.asset_id is not None else 0
            }]
        }
        
        return {
            "action": action
        }

