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
        self.ws_reqs, self.ws_topics = self.public_ws.multi_stream_request(
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
        # Keep references for explicit dispatch and one-time debug
        self._bba_handler = HyperliquidBBAHandler(self.ss)
        self._ticker_handler = HyperliquidTickerHandler(self.ss)
        self._log_once_l2 = False
        self._log_once_ticker = False

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
        try:
            meta_resp = await HyperliquidPublicClient(self.ss).instrument_info()

            # Normalize meta structure
            meta = meta_resp.get("data", meta_resp)

            # Prefer SDK mapping for asset ids and decimals to match server expectations
            try:
                from hyperliquid.info import Info  # type: ignore
                from src.exchanges.hyperliquid.endpoints import BaseEndpoints
                info_sdk = Info(BaseEndpoints.MAINNET, True, meta, None, None, None)

                symbol = getattr(self.ss, 'hyperliquid_symbol', '').upper()
                asset_id = None

                # name_to_asset may be a method or mapping depending on SDK version
                try:
                    asset_id = info_sdk.name_to_asset(symbol)  # callable style
                except Exception:
                    try:
                        asset_id = info_sdk.name_to_asset[symbol]  # mapping style
                    except Exception:
                        asset_id = None

                if isinstance(asset_id, int):
                    self.ss.hyperliquid_asset_id = asset_id
                    # Store SDK coin key for consistent REST/WS usage
                    try:
                        coin_key = None
                        try:
                            coin_key = info_sdk.name_to_coin[symbol]  # mapping style
                        except Exception:
                            coin_key = info_sdk.name_to_coin(symbol)  # callable style
                        if coin_key:
                            self.ss.hyperliquid_coin_key = coin_key
                    except Exception:
                        pass
                    # szDecimals lookup
                    try:
                        sz_decimals = int(info_sdk.asset_to_sz_decimals[asset_id])
                        self.ss.hyperliquid_lot_size = 10 ** (-sz_decimals)
                    except Exception:
                        self.ss.hyperliquid_lot_size = 1.0

                    # Price tick size: try to infer from meta (pxDecimals) if present; fallback conservative
                    try:
                        px_decimals = None
                        # meta may be dict with "universe" list aligned with asset ids (with offset handled by SDK)
                        if isinstance(meta, dict) and "universe" in meta:
                            # SDK may offset indices; try to find matching by name
                            for a in meta["universe"]:
                                if a.get("name", "").upper() == symbol:
                                    px_decimals = int(a.get("pxDecimals", a.get("pxDecimal", 4)))
                                    break
                        if px_decimals is not None:
                            self.ss.hyperliquid_tick_size = 10 ** (-px_decimals)
                    except Exception:
                        pass
                    if not getattr(self.ss, 'hyperliquid_tick_size', 0):
                        self.ss.hyperliquid_tick_size = 0.0001

                    print(f"{symbol}: asset_id={asset_id}, tick_size={self.ss.hyperliquid_tick_size}, lot_size={self.ss.hyperliquid_lot_size}")
                    return
            except Exception:
                pass

            # Fallback: derive from universe inline
            if isinstance(meta, dict) and "universe" in meta:
                for idx, asset in enumerate(meta["universe"]):
                    if asset.get("name", "").upper() == getattr(self.ss, 'hyperliquid_symbol', '').upper():
                        self.ss.hyperliquid_asset_id = idx
                        sz_decimals = int(asset.get("szDecimals", 2))
                        self.ss.hyperliquid_lot_size = 10 ** (-sz_decimals)
                        # Price tick from pxDecimals if present
                        try:
                            px_decimals = int(asset.get("pxDecimals", asset.get("pxDecimal", 4)))
                            self.ss.hyperliquid_tick_size = 10 ** (-px_decimals)
                        except Exception:
                            if not getattr(self.ss, 'hyperliquid_tick_size', 0):
                                self.ss.hyperliquid_tick_size = 0.0001
                        print(f"{self.ss.hyperliquid_symbol}: asset_id={idx}, tick_size={self.ss.hyperliquid_tick_size}, lot_size={self.ss.hyperliquid_lot_size}")
                        return

            # Fallback to defaults
            print("Warning: Could not map asset id; using defaults")
            if not getattr(self.ss, 'hyperliquid_tick_size', 0):
                self.ss.hyperliquid_tick_size = 0.0001
            if not getattr(self.ss, 'hyperliquid_lot_size', 0):
                self.ss.hyperliquid_lot_size = 1.0

        except Exception as e:
            print(f"Error fetching precision: {e}")
            # Set defaults to allow system to run
            if not getattr(self.ss, 'hyperliquid_tick_size', 0):
                self.ss.hyperliquid_tick_size = 0.0001
            if not getattr(self.ss, 'hyperliquid_lot_size', 0):
                self.ss.hyperliquid_lot_size = 1.0

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
                # Send each subscription message individually
                for req in self.ws_reqs:
                    await websocket.send(req)

                raw_logged = 0

                while True:
                    recv = orjson.loads(await websocket.recv())

                    if "success" in recv or "error" in recv:
                        continue

                    # Unconditional one-time raw message logging (first 3 messages)
                    if raw_logged < 3:
                        try:
                            print(f"{dt_now()}: DEBUG raw ws msg: {orjson.dumps(recv)[:400].decode()}")
                        except Exception:
                            pass
                        raw_logged += 1

                    # Hyperliquid WebSocket message format may differ
                    # Adjust based on actual message structure
                    handler = None
                    if "channel" in recv:
                        channel = str(recv["channel"]).lower()
                        # One-time sample log for channel-based messages
                        if not self._log_once_l2 and "l2book" in channel:
                            try:
                                print(f"{dt_now()}: DEBUG first l2Book (channel) msg: {orjson.dumps(recv)[:350].decode()}")
                            except Exception:
                                pass
                            self._log_once_l2 = True
                        if not self._log_once_ticker and "ticker" in channel:
                            try:
                                print(f"{dt_now()}: DEBUG first ticker (channel) msg: {orjson.dumps(recv)[:350].decode()}")
                            except Exception:
                                pass
                            self._log_once_ticker = True

                        # Direct routing by channel name
                        if "l2book" in channel:
                            try:
                                self.ss.hyperliquid_book.process(recv)
                            except Exception:
                                pass
                            try:
                                self._bba_handler.process(recv)
                            except Exception:
                                pass
                            continue
                        if "ticker" in channel:
                            try:
                                self._ticker_handler.process(recv)
                            except Exception:
                                pass
                            continue
                        if "trades" in channel:
                            try:
                                HyperliquidTradesHandler(self.ss).process(recv)
                            except Exception:
                                pass
                            continue
                        if "candle" in channel or "kline" in channel:
                            try:
                                HyperliquidKlineHandler(self.ss).process(recv)
                            except Exception:
                                pass
                            continue
                        # Fallback to topic map using exact channel
                        handler = self.topic_handler_map.get(recv["channel"])
                    elif "type" in recv:
                        handler_type = str(recv["type"]).lower()
                        # One-time sample logs
                        if not self._log_once_l2 and "l2book" in handler_type:
                            try:
                                print(f"{dt_now()}: DEBUG first l2Book msg: {orjson.dumps(recv)[:350].decode()}")
                            except Exception:
                                pass
                            self._log_once_l2 = True
                        if not self._log_once_ticker and "ticker" in handler_type:
                            try:
                                print(f"{dt_now()}: DEBUG first ticker msg: {orjson.dumps(recv)[:350].decode()}")
                            except Exception:
                                pass
                            self._log_once_ticker = True

                        # Explicit dual dispatch for l2Book: update full book and BBA
                        if "l2book" in handler_type:
                            try:
                                self.ss.hyperliquid_book.process(recv)
                            except Exception:
                                pass
                            try:
                                self._bba_handler.process(recv)
                            except Exception:
                                pass
                            continue
                        # Direct dispatch for ticker
                        if "ticker" in handler_type:
                            try:
                                self._ticker_handler.process(recv)
                            except Exception:
                                pass
                            continue

                        # Fallback: map by substring
                        for topic, h in self.topic_handler_map.items():
                            if handler_type in topic.lower():
                                handler = h
                                break

                    if handler:
                        try:
                            handler(recv)
                        except Exception:
                            pass

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

