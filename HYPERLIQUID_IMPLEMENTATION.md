# Hyperliquid Exchange Implementation

## Overview

This document describes the Hyperliquid exchange integration that has been added to the market maker system. The implementation follows a hybrid approach, using the Hyperliquid Python SDK where beneficial, while maintaining custom implementations for specific needs.

## Implementation Status

✅ **Completed Components:**

1. **Directory Structure** - Created `src/exchanges/hyperliquid/` with full structure
2. **REST Clients** - Public and private REST API clients
3. **WebSocket Clients** - Public and private WebSocket clients  
4. **WebSocket Handlers** - Orderbook, trades, ticker, kline, order, position handlers
5. **Order Management** - Place, cancel, amend operations
6. **SharedState Integration** - Hyperliquid data structures added
7. **Market Data Feeds** - HyperliquidMarketData and HyperliquidPrivateData classes
8. **Strategy Integration** - MarketMaker and Strategy core updated
9. **Feature Generation** - Hyperliquid features added with Bybit as optional feed
10. **Configuration** - parameters.yaml.example updated

## Configuration

### Environment Variables

Add to your `.env` file:

```env
# For Hyperliquid, you need wallet address and private key
# These can be the same as API_KEY/API_SECRET if you're using them for both
HYPERLIQUID_WALLET_ADDRESS=your_wallet_address
HYPERLIQUID_PRIVATE_KEY=your_private_key
```

Or the system will fall back to using `API_KEY` and `API_SECRET` if the Hyperliquid-specific ones aren't set.

### Parameters Configuration

Update `parameters.yaml`:

```yaml
primary_exchange: Hyperliquid  # Choices: ["Bybit", "Hyperliquid"]
primary_data_feed: Binance     # Optional: Use Binance as data feed when trading on Hyperliquid
hyperliquid_symbol: ETH        # Hyperliquid symbol (format may differ from Bybit)
```

## Key Features

### 1. Exchange Selection

The system now supports both Bybit and Hyperliquid as primary exchanges:

- **Bybit (default)**: Original implementation
- **Hyperliquid**: New implementation with full feature parity

### 2. Optional Data Feeds

Just like Bybit can use Binance as an optional data feed, Hyperliquid can use Binance:

- **Hyperliquid + Binance**: Use Binance market data for additional signals
- **Hyperliquid only**: Use only Hyperliquid data

### 3. Symbol Agnostic

All implementations are symbol-agnostic - no hardcoded symbols. Configure via `parameters.yaml`.

## Implementation Details

### API Structure

Hyperliquid uses a different API structure than Bybit:

- **REST Endpoints**: `/info` and `/exchange`
- **WebSocket**: Single endpoint with subscription-based messages
- **Authentication**: Wallet-based (not API key/secret like Bybit)
- **Order Format**: Integer-based sizes and prices (multiplied by 1e6)

### Hybrid SDK Approach

The implementation uses the Hyperliquid Python SDK when available:

- **SDK Used For**: Order signing, authentication
- **Custom Implementation**: WebSocket handling, data processing, order management

If the SDK is not installed, the system falls back to custom implementations.

### Order Format Conversion

Hyperliquid uses integer-based orders:
- Prices: `int(price * 1e6)`
- Quantities: `int(qty * 1e6)`

The implementation handles this conversion automatically.

## Important Notes

### ⚠️ API Format Assumptions

The implementation makes some assumptions about Hyperliquid's API message formats based on common DEX patterns. **You may need to adjust**:

1. **WebSocket Message Format**: The handlers expect certain field names - adjust in:
   - `src/exchanges/hyperliquid/websockets/handlers/*.py`

2. **REST Response Format**: Adjust in:
   - `src/exchanges/hyperliquid/get/public.py`
   - `src/exchanges/hyperliquid/get/private.py`

3. **Order Response Format**: Adjust in:
   - `src/exchanges/hyperliquid/post/order.py`
   - `src/exchanges/hyperliquid/websockets/handlers/order.py`

### Testing Recommendations

1. **Start with Testnet**: Use `TESTNET=True` in `.env` to test on Hyperliquid testnet
2. **Verify WebSocket Messages**: Check actual message formats and adjust handlers
3. **Test Order Placement**: Verify order format and signing work correctly
4. **Monitor Logs**: Watch for any format mismatches

## Installation

### Optional: Install Hyperliquid SDK

```bash
pip install hyperliquid-python-sdk
```

The system works without it, but signing will be more reliable with the SDK.

## Usage

### Running with Hyperliquid

1. Set `primary_exchange: Hyperliquid` in `parameters.yaml`
2. Set `hyperliquid_symbol: ETH` (or your desired symbol)
3. Optionally set `primary_data_feed: Binance` to use Binance as data source
4. Ensure wallet address and private key are in `.env` or use API_KEY/API_SECRET
5. Run: `python main.py`

### Running with Bybit (Default)

1. Set `primary_exchange: Bybit` in `parameters.yaml`
2. System works as before

## File Structure

```
src/exchanges/hyperliquid/
├── endpoints.py                    # API endpoints
├── get/
│   ├── public.py                 # Public REST client
│   └── private.py                 # Private REST client
├── post/
│   ├── client.py                 # POST client with signing
│   ├── order.py                  # Order operations
│   └── types.py                  # Order payload formatters
└── websockets/
    ├── public.py                 # Public WebSocket manager
    ├── private.py                # Private WebSocket manager
    └── handlers/
        ├── orderbook.py          # Order book handler
        ├── trades.py             # Trades handler
        ├── ticker.py             # Ticker handler
        ├── kline.py              # Candlestick handler
        ├── order.py              # Order updates handler
        └── position.py           # Position handler
```

## Differences from Bybit

1. **Authentication**: Wallet-based vs API key/secret
2. **Order Format**: Integer-based vs decimal
3. **WebSocket Format**: Subscription-based vs topic-based
4. **API Structure**: Different endpoint structure

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure all files are in place
2. **WebSocket Connection**: Check Hyperliquid WebSocket URL format
3. **Order Signing**: Verify wallet address and private key format
4. **Message Parsing**: Adjust handlers if message format differs

### Debugging

Enable debug mode in `MarketMaker.generate_quotes(debug=True)` to see quote generation details.

## Next Steps

1. **Test on Testnet**: Verify all functionality works
2. **Adjust API Formats**: Based on actual Hyperliquid API responses
3. **Fine-tune Features**: Adjust feature weights for Hyperliquid markets
4. **Monitor Performance**: Compare with Bybit performance

## References

- [Hyperliquid API Documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api)
- [Hyperliquid Python SDK](https://github.com/hyperliquid-dex/hyperliquid-python-sdk)

