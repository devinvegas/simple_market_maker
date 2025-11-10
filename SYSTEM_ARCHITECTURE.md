# Simple Market Maker - Complete System Architecture

## Overview

This document provides a comprehensive, verbose explanation of how all files in the `simple_market_maker` directory work together to make markets. The system is a sophisticated algorithmic trading bot that places limit orders on Bybit (and optionally uses Binance data) to provide liquidity and capture bid-ask spreads.

---

## System Entry Point

### `main.py`

The application starts here. It:
1. Loads environment variables (API keys) from `.env`
2. Creates a `SharedState` instance to centralize all market data and configuration
3. Runs two concurrent tasks:
   - `sharedstate.refresh_parameters()`: Periodically reloads trading parameters from `parameters.yaml` every 10 seconds
   - `Strategy(sharedstate).run()`: Executes the main trading strategy loop

The system uses `uvloop` for high-performance async I/O.

---

## Core Architecture: SharedState

### `src/sharedstate.py`

**Purpose**: Central data repository that all components read from and write to. This is the single source of truth for market data, configuration, and trading state.

**Key Data Structures**:

1. **Market Data (Bybit)**:
   - `bybit_bba`: NumPy array `[[bid_price, bid_qty], [ask_price, ask_qty]]` - Best bid/ask
   - `bybit_book`: `BaseOrderBook` instance - Full order book (up to 500 levels)
   - `bybit_trades`: RingBuffer of last 1000 trades `[timestamp, side, price, size]`
   - `bybit_klines`: RingBuffer of last 500 1-minute candles `[time, open, high, low, close, volume, turnover]`
   - `bybit_mark_price`: Mark price from ticker feed
   - `bybit_tick_size`, `bybit_lot_size`: Price and quantity precision

2. **Market Data (Binance - Optional)**:
   - Similar structures: `binance_bba`, `binance_book`, `binance_trades`, etc.
   - Only populated if `primary_data_feed == "BINANCE"`

3. **Trading State**:
   - `current_orders`: Dictionary mapping order IDs to `{side, price, qty}` - Tracks all open orders
   - `execution_feed`: Deque of last 100 executions
   - `inventory_delta`: Normalized position size (-1 to 1) relative to max account capacity
   - `volatility_value`: Current Bollinger Band Width (BBW) volatility measure

4. **Configuration Parameters** (loaded from `parameters.yaml`):
   - `account_size`: Account size in USD
   - `base_spread`: Minimum spread to quote
   - `min_order_size`, `max_order_size`: Order size bounds
   - `inventory_extreme`: Threshold (0-1) for extreme inventory handling
   - `bollinger_band_length`, `bollinger_band_std`: Volatility calculation parameters
   - `price_offset`, `size_offset`, `volatility_offset`: Master offsets for fine-tuning

**Key Methods**:
- `calculate_mid(bba)`: Simple average of best bid and ask
- `calculate_wmid(bba)`: Volume-weighted mid-price (considers bid/ask quantities)
- `calculate_vamp(book, depth=10)`: Volume-weighted average mid-price over order book depth

---

## Data Flow: WebSocket Feeds

The system continuously streams market data via WebSockets. There are three main feed classes:

### 1. `src/strategy/ws_feeds/bybitmarketdata.py` - Bybit Market Data

**Purpose**: Streams public market data from Bybit.

**Subscriptions**:
- **Orderbook**: Full depth order book updates (500 levels)
- **BBA**: Best bid/ask updates
- **Trades**: Real-time trade stream
- **Ticker**: Mark price updates
- **Kline**: 1-minute candlestick updates

**Initialization Flow**:
1. Fetches last 500 klines via REST API to initialize volatility calculation
2. Fetches last 1000 trades to initialize trade history
3. Retrieves symbol precision (tick size, lot size) from instrument info
4. Establishes WebSocket connection
5. Subscribes to all topics
6. Routes incoming messages to appropriate handlers

**Handlers** (in `src/exchanges/bybit/websockets/handlers/`):
- `orderbook.py`: Updates `bybit_book` with incremental order book changes
- `bba.py`: Updates `bybit_bba` array with best bid/ask
- `trades.py`: Appends new trades to `bybit_trades` RingBuffer
- `ticker.py`: Updates `bybit_mark_price`
- `kline.py`: Updates `bybit_klines` and recalculates volatility (BBW)

**Key Behavior**: Every kline update triggers volatility recalculation, which affects spread adjustment.

---

### 2. `src/strategy/ws_feeds/bybitprivatedata.py` - Bybit Private Data

**Purpose**: Streams authenticated private data (positions, orders).

**Subscriptions**:
- **Position**: Real-time position updates
- **Order**: Real-time order status updates (New, PartiallyFilled, Filled, Cancelled, Rejected)
- **Execution**: (Available but not currently subscribed) - Would provide detailed execution data for filled orders

**Dual Update Mechanism**:
1. **WebSocket Stream**: Real-time updates as trades execute and orders change
2. **Periodic Sync** (every 10 seconds): REST API calls to fetch current open orders and position to prevent drift

**Handlers**:
- `position.py`: 
  - Receives position updates
  - Calls `Inventory.position_delta()` to calculate normalized inventory
  - Updates `sharedstate.inventory_delta` (ranges from -1 to 1)
  
- `order.py`:
  - Maintains `sharedstate.current_orders` dictionary
  - Adds new/partially filled orders
  - Removes filled/cancelled/rejected orders
  - This is critical for the OMS to know what orders exist

- `execution.py` (not currently used):
  - Would append execution details to `sharedstate.execution_feed`
  - Provides granular execution data (price, quantity, order ID) for each fill
  - Currently execution feed is populated but handler is not subscribed

**Key Behavior**: Position updates immediately affect inventory delta, which influences quote generation.

---

### 3. `src/strategy/ws_feeds/binancemarketdata.py` - Binance Market Data (Optional)

**Purpose**: Streams market data from Binance when `primary_data_feed == "BINANCE"`.

**Subscriptions**:
- **Orderbook**: Full depth order book
- **BBA**: Best bid/ask
- **Trades**: Trade stream

**Why Binance?**: Provides additional pricing signals. The strategy compares Binance prices to Bybit prices to detect mispricings and predict price movements.

**Initialization**: Similar to Bybit - fetches snapshot, then streams updates.

---

## Order Book Management

### `src/exchanges/common/localorderbook.py`

**Purpose**: Maintains a local copy of the exchange order book.

**Data Structure**:
- `bids`: NumPy array of `[price, quantity]` pairs, sorted descending
- `asks`: NumPy array of `[price, quantity]` pairs, sorted ascending
- Keeps top 500 levels

**Update Mechanism**:
- Receives incremental updates from WebSocket
- For each update: removes old price level, adds new level if quantity > 0
- Sorts after each update

**Usage**: Used to calculate VAMP (Volume-Weighted Average Mid-Price) for feature generation.

---

## Feature Generation: Market Signals

### `src/strategy/features/generate.py`

**Purpose**: Calculates a composite "skew" value that predicts price direction. This skew drives quote placement.

**Feature Categories**:

#### 1. **Price Spread Features** (40-50% weight):
- `bybit_mark_wmid_spread()`: Log difference between mark price and weighted mid
- `binance_bybit_wmid_spread()`: Log difference between Binance and Bybit weighted mids
- `bybit_wmid_vamp_spread()`: Log difference between weighted mid and VAMP
- `binance_wmid_vamp_spread()`: Same for Binance

**Logic**: These detect when different price measures diverge, indicating potential price movement.

#### 2. **BBA Imbalance** (2.5-10% weight):
- `bba_imbalance()`: Normalized imbalance between best bid and ask quantities
- Formula: `((bid_qty / (bid_qty + ask_qty)) - 0.5) * 2`
- Range: -1 (ask heavy) to +1 (bid heavy)

#### 3. **Order Book Imbalance** (10-25% weight):
- `orderbook_imbalance()`: Calculates log ratio of bid/ask volumes at multiple depths (10, 25, 50, 100, 200, 500 BPS)
- Uses EMA-weighted aggregation across depths
- More weight on closer depths
- Positive = bid heavy (price likely to go up)

#### 4. **Trades Imbalance** (10-25% weight):
- `trades_imbalance()`: Analyzes last 1000 trades
- Calculates weighted buy vs sell volume using EMA weights (recent trades weighted more)
- Formula: `(weighted_buys - weighted_sells) / (weighted_buys + weighted_sells)`

**Skew Generation**:
- Combines all features with weighted sum
- **If Binance enabled**: 40% price spreads, 60% orderbook/trades
- **If Bybit only**: 50% price spreads, 50% orderbook/trades
- Returns a single float: positive = bullish (price up), negative = bearish (price down)

---

## Inventory Management

### `src/strategy/inventory.py`

**Purpose**: Tracks and normalizes position size relative to account capacity.

**Calculation**:
1. Receives position updates from `BybitPositionHandler`
2. Calculates max account value: `(account_size * leverage) / 2.05`
3. Normalizes position value: `inventory_delta = position_value / max_account_value`
4. Sign convention: Positive for long positions, negative for short

**Key Behavior**: 
- `inventory_delta` ranges from -1 (max short) to +1 (max long)
- This value is used by `MarketMaker` to adjust quotes to reduce inventory risk

---

## Quote Generation: The Market Maker

### `src/strategy/marketmaker.py`

**Purpose**: Generates optimal bid/ask quotes based on market conditions, skew, and inventory.

**Process Flow**:

#### 1. **Calculate Skew** (`_skew_()`):
   - Gets base skew from `Features.generate_skew()` (market prediction)
   - Rounds to 2 decimals to reduce OMS churn
   - Splits into `bid_skew` (0 to 1) and `ask_skew` (0 to 1)
   - **Inventory Adjustment**:
     - If inventory is long (positive delta): increases ask_skew (quote more asks to reduce)
     - If inventory is short (negative delta): increases bid_skew (quote more bids to reduce)
   - **Extreme Inventory Handling**:
     - If `inventory_delta < -inventory_extreme`: `bid_skew = 1` (only quote bids, no asks)
     - If `inventory_delta > inventory_extreme`: `ask_skew = 1` (only quote asks, no bids)
     - This prevents taking on more risk when already at extremes

#### 2. **Adjust Spread** (`_adjusted_spread_()`):
   - Calculates volatility multiplier: `(volatility_value * 100) / mid_price`
   - Multiplies `base_spread` by this multiplier
   - Clipped between 1x and 10x base spread
   - **Result**: Spread widens during volatile periods, narrows during calm

#### 3. **Generate Prices** (`_prices_()`):
   - **Extreme Cases**:
     - If `bid_skew >= 1`: Only generate bid prices (inventory too short)
     - If `ask_skew >= 1`: Only generate ask prices (inventory too long)
   - **Normal Case**:
     - Adjusts best bid/ask based on skew:
       - If `bid_skew >= ask_skew`: Bid closer to mid, ask further
       - If `ask_skew > bid_skew`: Ask closer to mid, bid further
     - Calculates price range: `volatility_value / 2`
     - Generates geometrically spaced prices:
       - Bids: From best_bid down to `best_bid - (range * (1 - bid_skew))`
       - Asks: From best_ask up to `best_ask + (range * (1 - ask_skew))`
     - Creates 4 bids and 4 asks (total 8 orders max)
   - Applies `price_offset` to all prices

#### 4. **Generate Sizes** (`_sizes_()`):
   - **Extreme Cases**: Fixed size (median of min and half max)
   - **Normal Case**:
     - Sizes increase near best price when skew favors that side
     - Sizes decrease further from mid
     - Formula: `min_size * (1 + skew^0.5)` for closest orders
     - Formula: `max_size * (1 - skew)` for furthest orders
     - Geometrically spaced between min and max
     - Applies `size_offset` to all sizes

#### 5. **Format Quotes** (`generate_quotes()`):
   - Rounds prices to tick size
   - Rounds sizes to lot size
   - Returns list of `[side, price, size]` tuples
   - Returns current spread value

**Key Behavior**: 
- Generates up to 8 orders (4 bids, 4 asks) per iteration
- Orders are geometrically spaced to provide liquidity at multiple price levels
- Skew determines which side gets more aggressive pricing and larger sizes

---

## Order Management System (OMS)

### `src/strategy/oms.py`

**Purpose**: Efficiently transitions from current orders to new orders while minimizing API calls and respecting rate limits.

**Current Implementation**: 
- **SIMPLIFIED**: Currently cancels all orders and places all new orders every iteration
- This is the active code path (lines 123-128)

**Intended Logic** (currently disabled, lines 130-183):
The OMS was designed with sophisticated logic but is currently bypassed:

1. **Segregation**: Separates current and new orders into buys and sells, sorted by price
2. **Categorization**: 
   - "Best" orders: Closest 2 to mid-price
   - "Outer" orders: Remaining orders
3. **Update Strategy**:
   - **Case 1**: No current orders → Cancel all, send all new
   - **Case 2**: All one side (extreme inventory) → Cancel missing prices, send new prices
   - **Case 3**: Side mismatch (switching extremes) → Cancel all, send all new
   - **Case 4**: Best orders changed → Amend in place (most efficient)
   - **Case 5**: Outer orders changed > buffer → Cancel and replace as batch

**Why Simplified?**: Likely for reliability - cancel-all and replace ensures no stale orders remain.

**Key Methods**:
- `segregate_current_orders()`: Groups existing orders by side
- `segregate_new_orders()`: Groups new orders by side
- `amend_orders()`: Amends orders if price change > buffer
- `replace_orders()`: Cancels old, sends new as batch
- `run()`: Main orchestration logic

---

## Order Execution: Exchange Interface

### `src/exchanges/bybit/post/order.py`

**Purpose**: Handles all order operations via Bybit REST API.

**Key Methods**:

1. **`order_limit_batch(orders)`**:
   - Splits orders into batches of 10 (Bybit limit)
   - Creates batch payload with multiple orders
   - Submits asynchronously
   - Returns API response

2. **`cancel_all()`**:
   - Cancels all orders for the symbol
   - Used every iteration in current implementation

3. **`amend(order)`** / **`amend_batch(orders)`**:
   - Amends existing orders (currently unused)
   - More efficient than cancel+replace

**Authentication**: Uses API key/secret to sign requests via `BybitPrivatePostClient`.

**Rate Limiting**: Batches orders to respect exchange limits (10 orders per batch).

---

## Strategy Orchestration

### `src/strategy/core.py`

**Purpose**: Coordinates all components and runs the main trading loop.

**Classes**:

#### `DataFeeds`:
- Initializes and starts all WebSocket feeds concurrently
- Always starts: `BybitMarketData`, `BybitPrivateData`
- Conditionally starts: `BinanceMarketData` (if `primary_data_feed == "BINANCE"`)

#### `Strategy`:
- **`_wait_for_ws_confirmation_()`**: Blocks until all required WebSocket connections are established
- **`primary_loop()`**:
  1. Waits for WebSocket confirmation
  2. Enters infinite loop:
     - Sleeps 1 second
     - Creates `MarketMaker` instance
     - Generates new quotes
     - Passes quotes to `OMS.run()`
     - OMS cancels all and places new orders
  3. Repeats every second

**Key Behavior**: 
- Strategy runs at 1 Hz (once per second)
- Each iteration generates fresh quotes based on latest market data
- Orders are completely replaced each iteration

---

## Volatility Calculation

### `src/indicators/bbw.py` & `src/exchanges/bybit/websockets/handlers/kline.py`

**Purpose**: Calculates Bollinger Band Width (BBW) as a volatility measure.

**Process**:
1. `BybitKlineHandler` receives kline updates
2. Updates `bybit_klines` RingBuffer
3. Calls `bbw()` function:
   - Extracts close prices from last N klines (where N = `bollinger_band_length`)
   - Calculates standard deviation of closes
   - Multiplies by `bollinger_band_std`
   - Returns `2 * std_dev` (band width)
4. Adds `volatility_offset` to result
5. Stores in `sharedstate.volatility_value`

**Usage**: 
- Used by `MarketMaker._adjusted_spread_()` to widen/narrow spreads
- Used by `MarketMaker._prices_()` to determine quote range

---

## Feature Calculation Details

### `src/strategy/features/bba_imbalance.py`
- Simple bid/ask quantity imbalance at best prices
- Formula: `((bid_qty / (bid_qty + ask_qty)) - 0.5) * 2`

### `src/strategy/features/ob_imbalance.py`
- Calculates imbalance at multiple depths (10, 25, 50, 100, 200, 500 BPS)
- For each depth: `log(total_bid_size / total_ask_size)`
- Aggregates with EMA weights (closer depths weighted more)
- Returns weighted sum

### `src/strategy/features/trades_imbalance.py`
- Analyzes last N trades (default 1000)
- Applies EMA weights (recent trades weighted more)
- Calculates: `(weighted_buys - weighted_sells) / (weighted_buys + weighted_sells)`

### `src/strategy/features/mark_spread.py`
- Calculates log price difference: `log(base / follow) * 100`
- Used to compare different price measures (mark vs mid, Binance vs Bybit, etc.)

---

## Complete Data Flow

### Initialization Phase:
1. `main.py` creates `SharedState`
2. `SharedState` loads parameters from `parameters.yaml`
3. `Strategy` starts `DataFeeds`
4. WebSocket connections established:
   - Bybit public stream → Orderbook, BBA, Trades, Ticker, Kline
   - Bybit private stream → Position, Order
   - (Optional) Binance stream → Orderbook, BBA, Trades
5. Initial data fetched via REST:
   - Last 500 klines → Initialize volatility
   - Last 1000 trades → Initialize trade history
   - Symbol info → Tick/lot sizes
   - Current position → Initialize inventory
   - Open orders → Initialize `current_orders`

### Runtime Loop (Every 1 Second):

1. **Market Data Updates** (Continuous, async):
   - Order book updates → `bybit_book` updated
   - BBA updates → `bybit_bba` updated
   - Trade updates → `bybit_trades` appended
   - Kline updates → `bybit_klines` updated → Volatility recalculated
   - Position updates → `inventory_delta` recalculated
   - Order updates → `current_orders` updated

2. **Quote Generation**:
   - `MarketMaker.generate_quotes()` called
   - `Features.generate_skew()` calculates market skew
   - Skew adjusted for inventory
   - Spread adjusted for volatility
   - Prices and sizes generated
   - Quotes formatted and returned

3. **Order Management**:
   - `OMS.run()` receives new quotes
   - Cancels all existing orders
   - Places all new orders as batch
   - `current_orders` updated via WebSocket

4. **Repeat**: Loop continues every second

---

## Key Interactions Summary

### How Orders Are Updated:
- **Trigger**: Every 1 second by the strategy loop
- **Process**: 
  1. New quotes generated based on latest market data
  2. All existing orders cancelled
  3. All new orders placed
- **Response To**:
  - Market price movements (via BBA updates)
  - Volatility changes (via kline updates)
  - Inventory changes (via position updates)
  - Order book changes (via orderbook updates)
  - Trade flow changes (via trades updates)

### Quote Placement Logic:
- **Based On**:
  1. **Market Skew**: Composite signal from multiple features predicting price direction
  2. **Inventory Delta**: Current position size (normalized -1 to 1)
  3. **Volatility**: Bollinger Band Width (affects spread width)
  4. **Best Prices**: Current best bid/ask from exchange
  5. **Configuration**: Offsets, min/max sizes, base spread, etc.

- **Skew Calculation**:
  - Combines price spreads, BBA imbalance, order book imbalance, trades imbalance
  - Weighted sum produces single skew value
  - Adjusted by inventory to encourage rebalancing

- **Price Generation**:
  - Geometrically spaced orders
  - Range determined by volatility
  - Skew determines which side is more aggressive
  - Extreme inventory stops quoting opposite side

- **Size Generation**:
  - Larger sizes near best price when skew favors that side
  - Smaller sizes further from mid
  - Geometrically spaced between min and max

### Inventory Management:
- **Tracking**: 
  - Position updates received via WebSocket
  - `Inventory.position_delta()` calculates normalized position
  - Formula: `position_value / ((account_size * leverage) / 2.05)`
  - Range: -1 (max short) to +1 (max long)

- **Impact on Quotes**:
  - Long inventory (positive delta) → Increases ask skew → More aggressive asks
  - Short inventory (negative delta) → Increases bid skew → More aggressive bids
  - Extreme inventory (beyond `inventory_extreme`) → Stops quoting opposite side
  - This creates natural mean reversion in position

### Volatility Management:
- **Calculation**: 
  - Bollinger Band Width from last N klines
  - Updated every kline (1 minute)
  - Formula: `2 * std_dev * multiplier`

- **Impact**:
  - Higher volatility → Wider spreads (up to 10x base spread)
  - Lower volatility → Narrower spreads (minimum 1x base spread)
  - Also affects quote range (distance from best prices)

---

## Configuration Parameters

### `parameters.yaml`:

- **`account_size`**: Account size in USD (affects inventory normalization)
- **`primary_data_feed`**: "Binance" or "Bybit" (determines if Binance feeds start)
- **`binance_symbol`**, **`bybit_symbol`**: Trading symbols
- **`price_offset`**: Global offset applied to all quote prices
- **`size_offset`**: Global offset applied to all quote sizes
- **`volatility_offset`**: Added to volatility value
- **`base_spread`**: Minimum spread (scaled by volatility)
- **`min_order_size`**, **`max_order_size`**: Order size bounds
- **`inventory_extreme`**: Threshold (0-1) for extreme inventory handling
- **`bollinger_band_length`**: Lookback period for volatility (default 20)
- **`bollinger_band_std`**: Standard deviation multiplier (default 2.5)

---

## Error Handling & Resilience

- **WebSocket Reconnection**: All WebSocket loops have `except websockets.ConnectionClosed` that reconnects automatically
- **Parameter Reloading**: Parameters reloaded every 10 seconds without restart
- **Order Sync**: Private data feed syncs orders every 10 seconds via REST to prevent drift
- **Rate Limiting**: Orders batched in groups of 10 to respect exchange limits

---

## Performance Characteristics

- **Update Frequency**: 
  - Strategy loop: 1 Hz
  - Market data: Real-time (WebSocket)
  - Parameter reload: 0.1 Hz (every 10 seconds)
  - Order sync: 0.1 Hz (every 10 seconds)

- **Order Count**: Maximum 8 orders (4 bids, 4 asks)

- **Data Structures**:
  - RingBuffers for trades/klines (fixed size, efficient)
  - NumPy arrays for order books (fast operations)
  - Dictionary for current orders (O(1) lookups)

---

This architecture enables the system to continuously monitor market conditions, calculate optimal quotes based on multiple signals, manage inventory risk, and efficiently update orders on the exchange.

