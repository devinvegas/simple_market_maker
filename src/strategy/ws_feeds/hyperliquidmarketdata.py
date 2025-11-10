import orjson
import websockets
from typing import Coroutine, Union

from src.utils.misc import datetime_now as dt_now
from src.exchanges.hyperliquid.get.public import HyperliquidPublicClient
from src.exchanges.hyperliquid.endpoints import WsStreamLinks
from src.exchanges.hyperliquid.websockets.handlers.kline import HyperliquidKlineHandler
from src.exchanges.hyperliquid.websockets.handlers.orderbook import HyperliquidBBAHandler
from src.exchanges.hyperliquid.websockets.handlers.ticker import HyperliquidTickerHandler
from src.exchanges.hyperliquid.websockets.handlers.trades import HyperliquidTradesHandler
from src.exchanges.hyperliquid.websockets.public import HyperliquidPublicWs
from src.sharedstate import SharedState


class HyperliquidMarketData:
    """
    Manages market data streams from Hyperliquid, including order book, BBA, trades, ticker, and kline.
    """

    _topics_ = ["Orderbook", "BBA", "Trades", "Ticker", "Kline"]

    def __init__(self, ss: SharedState) -> None:
        """
        Initializes the HyperliquidMarketData with a SharedState instance and sets up WebSocket connections.

        Parameters
        ----------
        ss : SharedState
            The shared state instance for managing application data.
        """
        self.ss = ss
        self.public_ws = HyperliquidPublicWs(self.ss)
        self.ws_req, self.ws_topics = self.public_ws.multi_stream_request(
            topics=self._topics_, 
            depth=500, 
            interval=1
        )

        self.topic_handler_map = {
            self.ws_topics[0]: self.ss.hyperliquid_book.process,
            self.ws_topics[1]: HyperliquidBBAHandler(self.ss).process,
            self.ws_topics[2]: HyperliquidTradesHandler(self.ss).process,
            self.ws_topics[3]: HyperliquidTickerHandler(self.ss).process,
            self.ws_topics[4]: HyperliquidKlineHandler(self.ss).process,
        }

    async def _initialize_(self) -> None:
        """
        Fetches the latest klines and trades data to initialize the market data before streaming.
        """
        klines = await HyperliquidPublicClient(self.ss).klines(60000, 500)  # 1 minute candles
        trades = await HyperliquidPublicClient(self.ss).trades(1000)
        
        if "data" in klines:
            HyperliquidKlineHandler(self.ss).initialize(klines["data"])
        if "data" in trades:
            HyperliquidTradesHandler(self.ss).initialize(trades["data"])

    async def _get_precision_(self) -> None:
        """
        Fetches and assigns the symbol's tick & lot size to the shared market data before streaming.
        """
        info = await HyperliquidPublicClient(self.ss).instrument_info()
        if "data" in info:
            meta = info["data"]
            # Extract tick and lot size from metadata
            # Format may need adjustment based on actual Hyperliquid API
            self.ss.hyperliquid_tick_size = float(meta.get("tickSize", meta.get("szDecimals", 0.01)))
            self.ss.hyperliquid_lot_size = float(meta.get("lotSize", meta.get("szDecimals", 0.01)))

    async def _stream_(self) -> Union[Coroutine, None]:
        """
        Asynchronously listens for messages on the WebSocket and dispatches them to the appropriate handlers.
        """
        await self._initialize_()
        await self._get_precision_()

        async for websocket in websockets.connect(WsStreamLinks.PUBLIC_STREAM):
            print(f"{dt_now()}: Connected to {self.ws_topics} hyperliquid feeds...")
            self.ss.hyperliquid_ws_connected = True

            try:
                await websocket.send(self.ws_req)

                while True:
                    recv = orjson.loads(await websocket.recv())

                    if "success" in recv or "error" in recv:
                        continue

                    # Hyperliquid WebSocket message format may differ
                    # Adjust based on actual message structure
                    handler = None
                    if "channel" in recv:
                        channel = recv["channel"]
                        handler = self.topic_handler_map.get(channel)
                    elif "type" in recv:
                        handler_type = recv["type"]
                        # Map handler type to topic
                        for topic, h in self.topic_handler_map.items():
                            if handler_type in topic.lower():
                                handler = h
                                break

                    if handler:
                        handler(recv)

            except websockets.ConnectionClosed:
                continue

            except Exception as e:
                print(f"{dt_now()}: Error with hyperliquid public feed: {e}")
                raise e

    async def start_feed(self) -> Coroutine:
        """
        Starts the WebSocket stream to continuously receive and handle live market data from Hyperliquid.
        """
        await self._stream_()

