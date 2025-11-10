import numpy as np
from typing import List, Dict
from src.indicators.bbw import bbw
from src.sharedstate import SharedState


class HyperliquidKlineHandler:
    """
    Handler for processing candlestick (kline) data from Hyperliquid and updating volatility.
    """
    
    def __init__(self, ss: SharedState) -> None:
        self.ss = ss

    def _update_volatility_(self) -> None:
        """Updates volatility value using Bollinger Band Width."""
        self.ss.volatility_value = bbw(
            klines=self.ss.hyperliquid_klines._unwrap(), 
            length=self.ss.bb_length, 
            multiplier=self.ss.bb_std
        )
        self.ss.volatility_value += self.ss.volatility_offset

    def initialize(self, data: List) -> None:
        """
        Initialize the klines array and update volatility value.

        Parameters
        ----------
        data : List
            List of candlestick data.
        """
        for candle in data:
            # Hyperliquid format: [time, open, high, low, close, volume, turnover]
            arr = np.array([
                float(candle.get("time", candle.get("timestamp", 0))),
                float(candle.get("open", candle[1] if isinstance(candle, list) else 0)),
                float(candle.get("high", candle[2] if isinstance(candle, list) else 0)),
                float(candle.get("low", candle[3] if isinstance(candle, list) else 0)),
                float(candle.get("close", candle[4] if isinstance(candle, list) else 0)),
                float(candle.get("volume", candle.get("vol", candle[5] if isinstance(candle, list) else 0))),
                float(candle.get("turnover", candle.get("value", candle[6] if isinstance(candle, list) else 0)))
            ], dtype=np.float64)
            self.ss.hyperliquid_klines.appendleft(arr)

        self._update_volatility_()

    def process(self, recv: Dict) -> None:
        """
        Processes candlestick updates and recalculates volatility.

        Parameters
        ----------
        recv : Dict
            A dictionary containing candlestick data.
        """
        if "data" in recv:
            candles = recv["data"] if isinstance(recv["data"], list) else [recv["data"]]
            for candle in candles:
                new = np.array([
                    float(candle.get("time", candle.get("timestamp", 0))),
                    float(candle.get("open", 0)),
                    float(candle.get("high", 0)),
                    float(candle.get("low", 0)),
                    float(candle.get("close", 0)),
                    float(candle.get("volume", candle.get("vol", 0))),
                    float(candle.get("turnover", candle.get("value", 0)))
                ], dtype=np.float64)

                # If previous time same, then overwrite, else append
                if len(self.ss.hyperliquid_klines) > 0 and self.ss.hyperliquid_klines[-1][0] != new[0]:
                    self.ss.hyperliquid_klines.append(new)
                else:
                    if len(self.ss.hyperliquid_klines) > 0:
                        self.ss.hyperliquid_klines.pop()
                    self.ss.hyperliquid_klines.append(new)

                self._update_volatility_()

