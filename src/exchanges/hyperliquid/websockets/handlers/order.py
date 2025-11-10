from typing import Dict
from src.sharedstate import SharedState


class HyperliquidOrderHandler:
    """
    Handler for processing order updates from Hyperliquid.
    """
    
    _opened_ = ["open", "new", "partiallyFilled"]
    _closed_ = ["filled", "cancelled", "rejected", "closed"]

    def __init__(self, ss: SharedState) -> None:
        self.ss = ss

    def sync(self, recv: Dict) -> None:
        """
        Synchronizes open orders from REST API response.

        Parameters
        ----------
        recv : Dict
            Response from open orders API call.
        """
        if recv is not None and "data" in recv:
            orders = recv["data"].get("orders", [])
            self.ss.current_orders = {
                str(order.get("oid", order.get("orderId", ""))): {
                    "side": "Buy" if order.get("side", order.get("s", "")) in ["B", "Buy"] else "Sell",
                    "price": float(order.get("price", order.get("px", 0))),
                    "qty": float(order.get("sz", order.get("size", order.get("qty", 0))))
                }
                for order in orders
                if order.get("status", "").lower() in self._opened_
            }

    def process(self, data: Dict) -> None:
        """
        Processes real-time order updates from WebSocket.

        Parameters
        ----------
        data : Dict
            Order update data from WebSocket.
        """
        if isinstance(data, list):
            orders = data
        elif "orders" in data:
            orders = data["orders"]
        else:
            orders = [data]

        new_orders = {}
        filled_orders = set()

        for order in orders:
            order_id = str(order.get("oid", order.get("orderId", "")))
            status = order.get("status", "").lower()
            
            if status in self._opened_:
                new_orders[order_id] = {
                    "side": "Buy" if order.get("side", order.get("s", "")) in ["B", "Buy"] else "Sell",
                    "price": float(order.get("price", order.get("px", 0))),
                    "qty": float(order.get("sz", order.get("size", order.get("qty", 0))))
                }
            elif status in self._closed_:
                filled_orders.add(order_id)

        # Update the orders
        self.ss.current_orders.update(new_orders)

        # Remove filled orders
        for order_id in filled_orders:
            self.ss.current_orders.pop(order_id, None)

