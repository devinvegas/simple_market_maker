import asyncio
import orjson
import websockets
from typing import Coroutine, Union

from src.utils.misc import datetime_now as dt_now
from src.exchanges.hyperliquid.get.private import HyperliquidPrivateGet
from src.exchanges.hyperliquid.endpoints import WsStreamLinks
from src.exchanges.hyperliquid.websockets.handlers.order import HyperliquidOrderHandler
from src.exchanges.hyperliquid.websockets.handlers.position import HyperliquidPositionHandler
from src.exchanges.hyperliquid.websockets.private import HyperliquidPrivateWs
from src.sharedstate import SharedState


class HyperliquidPrivateData:
    """
    Manages private data streams from Hyperliquid, including position, execution, and order updates.
    """

    _topics_ = ["Position", "Order"]

    def __init__(self, ss: SharedState) -> None:
        """
        Initializes the HyperliquidPrivateData with a SharedState instance and sets up WebSocket connections.

        Parameters
        ----------
        ss : SharedState
            The shared state instance for managing application data.
        """
        self.ss = ss
        wallet_address = getattr(ss, 'hyperliquid_wallet_address', None) or ss.api_key
        private_key = getattr(ss, 'hyperliquid_private_key', None) or ss.api_secret
        self.private_ws = HyperliquidPrivateWs(wallet_address, private_key)
        self.private_client = HyperliquidPrivateGet(self.ss)
        
        self.ws_req, self.ws_topics = self.private_ws.multi_stream_request(
            topics=self._topics_
        )

        self.order_handler = HyperliquidOrderHandler(self.ss)
        self.position_handler = HyperliquidPositionHandler(self.ss)

        self.topic_handler_map = {
            self.ws_topics[0]: self.position_handler.process,
            self.ws_topics[1]: self.order_handler.process,
        }

    async def _sync_(self) -> Coroutine:
        """
        Synchronizes open orders and current positions at regular intervals.
        """
        while True:
            open_orders = await self.private_client.open_orders()
            current_position = await self.private_client.current_position()
            self.order_handler.sync(open_orders)
            self.position_handler.sync(current_position)
            await asyncio.sleep(10)

    async def _stream_(self) -> Union[Coroutine, None]:
        """
        Connects to Hyperliquid's private WebSocket stream and handles incoming updates.
        """
        print(f"{dt_now()}: Connected to {self.ws_topics} hyperliquid feeds...")

        async for websocket in websockets.connect(WsStreamLinks.PRIVATE_STREAM):
            try:
                await websocket.send(self.private_ws.authentication())
                await websocket.send(self.ws_req)

                while True:
                    recv = orjson.loads(await websocket.recv())

                    if "success" in recv or "error" in recv:
                        continue

                    # Hyperliquid WebSocket message format may differ
                    handler = None
                    if "channel" in recv:
                        channel = recv["channel"]
                        handler = self.topic_handler_map.get(channel)
                    elif "type" in recv:
                        handler_type = recv["type"]
                        for topic, h in self.topic_handler_map.items():
                            if handler_type in topic.lower():
                                handler = h
                                break

                    if handler:
                        handler(recv.get("data", recv))

            except websockets.ConnectionClosed:
                continue

            except Exception as e:
                print(f"{dt_now()}: Error with hyperliquid private feed: {e}")
                raise e

    async def start_feed(self) -> Coroutine:
        """
        Initiates the streaming and synchronization of live private market data from Hyperliquid.
        """
        await asyncio.gather(
            asyncio.create_task(self._sync_()),
            asyncio.create_task(self._stream_())
        )

