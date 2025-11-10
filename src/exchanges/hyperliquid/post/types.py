from typing import Dict, List

# Try to use Hyperliquid SDK for signing if available
try:
    from hyperliquid.utils.signing import sign_l1_action, sign_l2_action, sign_cancel_action
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

    def __init__(self, symbol: str, wallet_address: str = None, private_key: str = None) -> None:
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
        """
        self.symbol = symbol
        self.wallet_address = wallet_address
        self.private_key = private_key

    def _convert_side(self, side: str) -> str:
        """Convert 'Buy'/'Sell' to Hyperliquid format ('B'/'A' or 'A'/'B')"""
        # Hyperliquid uses 'A' for ask (sell) and 'B' for bid (buy)
        return "B" if side == "Buy" else "A"

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
        action = {
            "type": "order",
            "orders": [{
                "a": int(float(qty) * 1e6),  # Hyperliquid uses integer sizes (in base units * 1e6)
                "b": int(float(price) * 1e6),  # Prices also in integer format
                "s": self._convert_side(side),
                "r": reduce_only,
                "t": {"limit": {"tif": "Gtc"}}  # Good till cancel
            }],
            "grouping": "na"
        }
        
        # If SDK is available, sign the action
        if HYPERLIQUID_SDK_AVAILABLE and self.wallet_address and self.private_key:
            try:
                from hyperliquid.utils.signing import sign_l1_action
                signed = sign_l1_action(
                    self.wallet_address,
                    self.private_key,
                    action,
                    None,  # nonce - SDK will generate
                    None   # vault_address - optional
                )
                return {
                    "action": signed
                }
            except Exception:
                pass
        
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
        action = {
            "type": "order",
            "orders": [{
                "a": int(float(qty) * 1e6),
                "b": 0,  # Market order - no price
                "s": self._convert_side(side),
                "r": reduce_only,
                "t": {"market": {}}
            }],
            "grouping": "na"
        }
        
        if HYPERLIQUID_SDK_AVAILABLE and self.wallet_address and self.private_key:
            try:
                from hyperliquid.utils.signing import sign_l1_action
                signed = sign_l1_action(
                    self.wallet_address,
                    self.private_key,
                    action,
                    None,
                    None
                )
                return {
                    "action": signed
                }
            except Exception:
                pass
        
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
        action = {
            "type": "cancel",
            "cancels": [{
                "a": self.symbol,
                "o": int(orderId)
            }]
        }
        
        if HYPERLIQUID_SDK_AVAILABLE and self.wallet_address and self.private_key:
            try:
                from hyperliquid.utils.signing import sign_cancel_action
                signed = sign_cancel_action(
                    self.wallet_address,
                    self.private_key,
                    action,
                    None
                )
                return {
                    "action": signed
                }
            except Exception:
                pass
        
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
        action = {
            "type": "cancel",
            "cancels": [{
                "a": self.symbol
            }]
        }
        
        if HYPERLIQUID_SDK_AVAILABLE and self.wallet_address and self.private_key:
            try:
                from hyperliquid.utils.signing import sign_cancel_action
                signed = sign_cancel_action(
                    self.wallet_address,
                    self.private_key,
                    action,
                    None
                )
                return {
                    "action": signed
                }
            except Exception:
                pass
        
        return {
            "action": action
        }

