from dataclasses import dataclass
import os

if_testnet = "-testnet" if os.getenv("TESTNET") == "True" else ""

@dataclass
class BaseEndpoints:
    """Base REST API endpoints for Hyperliquid"""
    MAINNET = f"https://api.{'hyperliquid-testnet' if if_testnet else 'hyperliquid'}.xyz"

@dataclass
class WsStreamLinks:
    """WebSocket stream URLs for Hyperliquid"""
    domain = f"api.{'hyperliquid-testnet' if if_testnet else 'hyperliquid'}.xyz"
    PUBLIC_STREAM = f"wss://{domain}/ws"
    PRIVATE_STREAM = f"wss://{domain}/ws"  # Same URL, authenticated via message

@dataclass
class ApiEndpoints:
    """REST API endpoint paths"""
    INFO = "/info"
    EXCHANGE = "/exchange"

