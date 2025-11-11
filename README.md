# Hyperliquid-only Market Maker — Build Plan, Milestones, and Rationale

This document outlines a pragmatic sequence to build a Hyperliquid-only, symbol-agnostic market-making system using a hybrid SDK/custom approach. It defines milestones, scope, rationale (including microstructure concepts), acceptance criteria, and key risks.

## Objectives
- Production-grade connectivity to Hyperliquid (REST + WebSocket) with SDK-aligned signing.
- Robust, safe, two-sided quoting centered near live price.
- Inventory and exposure controls with low OMS churn.
- Clear observability and tunable parameters.

---

## Project Layout (suggested)

- `parameters.yaml` — runtime configuration (symbol, wallet, risk, tuning).
- `src/sharedstate.py` — centralized runtime state and computed properties.
- `src/exchanges/hyperliquid/`
  - `endpoints.py` — REST/WS endpoints.
  - `get/public.py` — public REST client (meta/klines/trades/orderbook).
  - `post/client.py` — private POST/signing (SDK-compatible).
  - `post/types.py` — order action formatters (limit/amend/cancel).
  - `websockets/public.py` — public WS client.
  - `websockets/handlers/*.py` — message handlers (book/mark/trades/positions).
- `src/strategy/`
  - `core.py` — data feed orchestration, gating, main loop.
  - `marketmaker.py` — quote generation (pricing, sizing, controls).
  - `oms.py` — order management (diff/amend/cancel/create).
  - `features/*.py` — feature engineering for skew and spread logic.
  - `ws_feeds/*.py` — feed bootstrap (precision, meta).
- `src/utils/`
  - `rounding.py` — tick/lot rounding.
  - `logging.py`, `time.py` — helpers.

---

## Milestones

### M1. Configuration and Skeleton
- [ ] Scope: `parameters.yaml`, repo layout, logging bootstrap.
- Goals: Centralize configuration; clarify module boundaries.
- Rationale: Decoupling improves reliability and speed of iteration.
- Acceptance:
  - App boots and loads `parameters.yaml` with defaults.
- Risks/Notes:
  - Keep secrets out of source control; use env overrides if needed.

### M2. Endpoints and SDK Wiring
- [ ] Scope: `src/exchanges/hyperliquid/endpoints.py`, SDK imports in `post/client.py`.
- Goals: Establish correct mainnet/testnet URLs; wire SDK utilities (`Account`, `get_timestamp_ms`, `Info`).
- Rationale: Small endpoint typos cause total outages; SDK alignment prevents signing drift.
- Acceptance:
  - Simple GET to a public endpoint succeeds in both environments.
- Risks/Notes:
  - Windows: avoid `uvloop`; keep optional.

### M3. Precision and IDs via Meta (Public REST)
- [ ] Scope: `src/exchanges/hyperliquid/get/public.py`, `src/sharedstate.py`.
- Goals: Resolve `asset_id`, `coin_key`, `tick_size`, `lot_size` for `symbol`.
- Rationale:
  - On-grid orders require correct tick/lot.
  - Correct IDs prevent orders from going to the wrong instrument.
- Acceptance:
  - State shows non-zero `tick/lot` and valid `asset_id`/`coin_key`.
- Risks/Notes:
  - Fail fast if symbol not in universe.

### M4. Public WebSocket Streaming and Derived Mids
- [ ] Scope: `websockets/public.py`, handlers, `features/generate.py`.
- Goals: Subscribe to orderbook/mark/trades; compute `mid`, `wmid`, `vamp` robustly.
- Rationale (microstructure):
  - Mid = (best bid + best ask) / 2; a proxy for current fair price.
  - Mark price is a reference; use as an anchor if book is invalid at startup.
  - Early streams may be empty or stale; guard against zeros.
- Acceptance:
  - Live updates for book/mark/trades; `mid > 0`, `mark > 0`.
- Risks/Notes:
  - Synthesize temporary BBA if startup data is malformed to avoid quoting at 1.0.

### M5. Rounding and Precision Utilities
- [ ] Scope: `src/utils/rounding.py`.
- Goals: Exact on-grid rounding for prices and sizes.
- Rationale:
  - Exchanges reject off-grid orders; rounding twice causes amend churn.
- Acceptance:
  - Unit tests: prices/sizes round correctly; `step == 0` guarded.
- Risks/Notes:
  - Round once at the end of computation.

### M6. Private Client and Centralized Signing
- [ ] Scope: `src/exchanges/hyperliquid/post/client.py`, `post/types.py`.
- Goals: Single signing path; `/exchange` payloads match SDK shape.
- Rationale:
  - Centralization avoids drift; consistent error handling.
- Acceptance:
  - Signed payloads validate server-side; HTTP/JSON errors produce actionable logs.
- Risks/Notes:
  - Time/nonce skew; handle retries with backoff.

### M7. Single-Order Acceptance (Place/Query/Cancel)
- [ ] Scope: simple driver script or function harness; `post/order.py`.
- Goals: Prove E2E order lifecycle before OMS complexity.
- Rationale:
  - Ensures plumbing correctness in isolation.
- Acceptance:
  - Place one limit near mark; appears in open orders; cancel by `oid`.
- Risks/Notes:
  - Respect `min_order_size` and lot size to avoid rejects.

### M8. Order Management System (OMS)
- [ ] Scope: `src/strategy/oms.py`, `post/order.py`.
- Goals: Diff desired vs live; batch amend/create/cancel; low churn.
- Rationale (microstructure):
  - Queue priority is price-time; amending can reset queue position depending on exchange semantics.
  - Prefer amend-in-place when price unchanged; avoid cancel-all/replace.
- Acceptance:
  - Minimal churn for small quote adjustments; stable under moderate volatility.
- Risks/Notes:
  - Handle partial fills; reconcile local intents with remote `oid`s.

### M9. Strategy Core Loop and Gating
- [ ] Scope: `src/strategy/core.py`, `ws_feeds/hyperliquidmarketdata.py`.
- Goals: Only run when ready: precision loaded, WS connected, `mark/mid > 0`; tick cadence.
- Rationale:
  - Prevents off-market quotes (e.g., 1.0) during startup.
- Acceptance:
  - No quotes until all gates pass; then steady cadence with heartbeats.
- Risks/Notes:
  - Add cancel-stale guard; graceful shutdown.

### M10. Market Maker (Pricing, Sizing, Controls)
- [ ] Scope: `src/strategy/marketmaker.py`, `features/*.py`.
- Goals:
  - Price centered at mid; anchor to mark if mid invalid or far.
  - Spread from `base_spread` plus adjustments.
  - Sizing ladder on depth; enforce `min_order_size` and lot rounding.
  - Controls: `max_quotes_per_side`, inventory suppression, price bands vs mark.
- Rationale (microstructure):
  - Adverse selection risk is highest at top-of-book; small top sizes reduce loss on toxic flow.
  - Depth sizes catch sweeps; wider quotes reduce pick-off risk.
- Acceptance:
  - Two-sided near mark when flat; one-sided when overexposed; prices > 0 and on-grid.
- Risks/Notes:
  - Clamp generated prices to positive, within reasonable bands.

### M11. Risk Limits and Failsafes
- [ ] Scope: `strategy/core.py`, `oms.py`.
- Goals: Inventory caps, side notional caps, kill-switches, cancel-all on disconnect/shutdown.
- Rationale:
  - Fail safe rather than accumulate hidden risk.
- Acceptance:
  - Breach triggers suppression or cancel-all; logs show cause.
- Risks/Notes:
  - Avoid flapping kill-switch; add cooldowns.

### M12. Observability (Logs, Metrics, Debug)
- [ ] Scope: `utils/logging.py`, structured logs in clients/OMS/strategy.
- Goals: Trace what was quoted, why, and with what exposure.
- Rationale:
  - Tuning requires visibility into inputs and decisions.
- Acceptance:
  - Logs for quote gen, OMS diffs, responses, exposure; optional metrics sink.
- Risks/Notes:
  - Balance verbosity to avoid noise.

### M13. Tuning and Validation
- [ ] Scope: `parameters.yaml`, `marketmaker.py`, `features/generate.py`.
- Goals: Tune spreads, sizing, skew, and thresholds for stability and PnL.
- Rationale:
  - “Correctness” first, then “profitability”.
- Acceptance:
  - Stable inventory around target; realized spread > costs; low reject/amend rates.
- Risks/Notes:
  - Tune conservatively first; increase aggressiveness incrementally.

---

## Parameter Tuning Guide

- base_spread (absolute price):
  - Why: Exchanges quote in absolute price units (ticks). If ALGO ≈ 0.18, `base_spread=0.005` ≈ 2.8%. Using “0.5%” directly as `0.005` unintentionally sets 2.8%. Always think in absolute, convert percent→absolute when desired.
  - How: Start 0.002–0.006 for 0.18 assets; widen with volatility, narrow with liquidity.

- tick precision handling:
  - Why: Off-grid orders are rejected; double rounding triggers churn.
  - How: Compute price once, then `round_step(price, tick_size)`; add amend thresholds (e.g., ≥ 1 tick change).

- size ladder:
  - Why: Reduce adverse selection at top-of-book; provide depth to catch sweeps.
  - How: Small top size; geometric increase deeper (e.g., ×1.3, ×1.7), cap per-side notional; respect `min_order_size`.

- inventory skew coefficients:
  - Why: Mean-revert inventory; reduce risk.
  - How: Skew ∝ inventory delta (notional or contracts); bound skew to avoid shutoff unless risk caps require it.

- max_quotes_per_side:
  - Why: Bound exposure velocity.
  - How: 1–2 per side initially; pause adding more if two buys fill until inventory normalizes.

- price anchoring and bands:
  - Why: Startup BBA may be invalid (e.g., 1.0). Anchoring prevents absurd quotes.
  - How: If `mid ≤ 0` or `|mid−mark|/mark > 0.5`, anchor to `mark`; enforce bands around mark.

- volatility_offset:
  - Why: Additive guard to widen quotes during turbulence.
  - How: Derive from recent `wmid` volatility; clamp maxima to control churn.

---

## Key Microstructure Concepts (Practical)

- Price-time priority and queue position:
  - Amending price can forfeit queue; favor amends only when meaningful to preserve time priority.

- Adverse selection:
  - Fast informed flow hits your best quotes. Reduce top size, widen spread, and adjust skew when signals indicate toxicity.

- Mid vs mark:
  - Mid uses BBA; mark is a reference price (e.g., index-based). When the book is thin/stale, mark is a better anchor.

- Tick size and lot size:
  - The market is discrete. Small errors in rounding can flip orders between valid/invalid or cause re-amend loops.

- Sweep risk and depth:
  - Sudden moves sweep multiple price levels. Larger sizes deeper help monetize spread while limiting top-of-book risk.

- Inventory mean reversion:
  - Quoting more aggressively on the side that reduces your exposure stabilizes PnL and reduces tail risk.

---

## Acceptance Matrix (Abbreviated)

- M3: `tick/lot > 0`, valid `asset_id/coin_key`.
- M4: Book/mark/trades streaming; `mid > 0`, `mark > 0`.
- M7: Place/cancel single limit works.
- M8: OMS diffing with low churn.
- M10: Two-sided near mark; suppression when overexposed; on-grid prices/sizes.
- M11: Risk caps/kill-switch verified.
- M12: Logs show quotes, OMS actions, responses, exposure.
- M13: Stable inventory; realized spread > fees + slippage.

---

## Quick Checklist

- [ ] Correct endpoints + SDK wired
- [ ] Precision/IDs resolved for symbol
- [ ] WS streaming healthy; derived mids sane
- [ ] Private client signing centralized
- [ ] Single order E2E proven
- [ ] OMS diff/amend/cancel stable
- [ ] Strategy gating prevents early bad quotes
- [ ] Market maker pricing/sizing/controls active
- [ ] Risk caps and kill-switches enforced
- [ ] Observability useful
- [ ] Tuning passes completed

---

## Appendix: IDs, Precision, and Wire Formats

- Asset identity:
  - Use `Info.name_to_asset[symbol]` → `asset_id`
  - Use `Info.name_to_coin[symbol]` → `coin_key`
- Precision:
  - `pxDecimals` → `tick_size = 10^(-pxDecimals)`
  - Lot decimals → `lot_size`
- Order payloads:
  - Include `asset_id` and on-grid `px/size`
  - Sign with SDK (centralized in `post/client.py`)

Bybit Simple Market Maker
===================

This is a simple market making bot for [Bybit](https://www.bybit.com/en/).

***DISCLAIMER: Nothing in this repository constitutes financial advice (and therefore, please use at your own risk). It is tailored primarily for learning purposes, and is highly unlikely you will make profits trading this strategy. If you are not ready to risk your own capital, but want to try it out, you can sign up for Bybit's [Testnet](https://testnet.bybit.com/en/). [BeatzXBT](https://twitter.com/BeatzXBT) will not accept liability for any loss or damage including, without limitation to, any loss of profit which may arise directly or indirectly from use of or reliance on this software.***


# Getting Started


### Clone the repository

In the terminal run the following commands:
```console
# Change directories to your workspace
$ cd /path/to/your/workspace

# Clone the repository
$ git clone git@github.com:beatzxbt/bybit-smm.git

# Change directories into the project
$ cd bybit-smm
```

__Note: Each terminal command going forward will be run within the main project directory.__

### Set Up the environment

Copy `.env.exmaple` to `.env`. This is where we are going to store our API keys:
```console 
$ cp .env.example .env
```

Next, you will need to create a Bybit account. __If you are not ready to trade real money, you can create a testnet account with no KYC required by signing up at [testnet.bybit.com](https://testnet.bybit.com/en/).__


Once you have created your Bybit account, generate API key and secret following [this guide](https://learn.bybit.com/bybit-guide/how-to-create-a-bybit-api-key/). Once you have your API keys, edit the `.env` file that you generated earlier, filling in your credentials:
```
API_KEY=YOUR_API_KEY_HERE
API_SECRET=YOUR_API_SECRET_HERE
```

The account **must** be a Unified Trading Account (UTA).

_Optional: If you are using the testnet to trade, set the `TESTNET` flag to True within the `.env` file:_
```
TESTNET=True
```

### Install the requirements
_Optional: If you are familiar with virtual environments, create one now and activate it. If not, this step is not necessary:_

```console
$ virtualenv venv
$ source venv/bin/activate
```

Install the package requirements:
```console
$ pip install -r requirements.txt
```

### Configure the trading parameters

Next, we are going to configure the parameters that actually determine which market we are making, and how the trader should behave. 

Sensible defaults are set in `parameters.yaml.example`. Copy it over to your `parameter.yaml` file to get started:
```console
$ cp parameters.yaml.example parameters.yaml
```

The `parameters.yaml` file is gitignored, and can be configured for each environment that you are trading in separately.

Each of the configurable parameters are explained below in more detail

- `account_size` - Your account size in USD.
- `primary_data_feed` - Either Binance or Bybit. While most of the features are based on Bybit's own price, selecting Binance will start additional websocket streams to enable additional pricing features. Only possible if the symbol is trading on Binance USD-M.

- `binance_symbol`: - The derivatives symbol on Binance USD-M, unused if primary_data_feed is set to Bybit.
- `bybit_symbol`: - The derivatives symbol on Bybit Futures.

#### Master offsets 
- `price_offset` - Offset the generates quote prices ± some value. Positive number increases the quote price (and vice versa), however keep in mind that the API will return errors if the offset causes the minimum quote price to be less than 0, or the prices to be outside the exchange defined min/max range.
- `size_offset` - Offset the generates quote sizes ± some value. Positive number increases the quote size (and vice versa), however keep in mind that the API will return errors if the offset causes the minimum quote size to be less than minimum trading size.
- `volatility_offset` - Offset the total quote range ± some value (Positive number increases the distance between the lowest bid and the highest ask, and vice versa)


#### Market Maker Settings
Settings regarding the functionality of the core market making script
- `base_spread` - Lowest spread you're willing to quote at any given volatility. This may be scaled depending on the short-term volatility, up to 10x it's value.
- `min_order_size` - The minimum order size of the closest order to mid-price. 
- `max_order_size` - The maximum order size of the further order from mid-price. 
-  `inventory_extreme` - A value between 0 <-> 1, defining the maximum limit at which the system quotes normally. If inventory delta exceeds this value, it will stop quoting the opposite side and go into a reduce-only mode.

#### Volatility settings
The volatility indicator used to define the trading range is Bollinger Band Width.
- `bollinger_band_length` - Lookback of 1 minute candlestick close data used to calculate band width. 
- `bollinger_band_std` - Multipler of standard deviations generated over the lookback period above.


#### Running the bot

To run the the bot, once your `.env` and `parameters.yaml` file are configured, simply run:
```console
(venv) $ python3 -m main
```

__NOTE: If you are using MacOS, you may run into the following error__:
```
ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1006)
```

The fix is [simple](https://stackoverflow.com/questions/52805115/certificate-verify-failed-unable-to-get-local-issuer-certificate).


# Strategy Design/Overview

1. Prices from Bybit (and optionally Binance) are streamed using websockets into a common shared class.
2. Features are calculated from the updated market data, and a market maker class generates optimal quotes
  * Multiple features work on comparing different mid-prices to each other (trying to predict where price is likely to go).
  * Both bid/ask skew is then calculated, based on the feature values but corrected for the current inventory (filled position).
  * Prices & sizes are generated based on the skew, with edge cases for extreme inventory cases.
  * Spread is adjusted for volatility (as a multiple of the base spread), widening when short term movements increase.
  * Quotes are generated using all the above, formatted for the local client and returned.
3. Orders are sent via a Order Management System (currently disabled), which transitions between current and new states, and tries to do so in the most ratelimit-efficient way possible.
  


# Contributions

- None planned for this repository in its current state, although i'm working on a major upgrade in [this branch](https://github.com/beatzxbt/bybit-smm/tree/v.2.0-alpha). It has a faster, exchange-agnostic framework and intends to support multi-symbol execution. However, this is still very much WIP and will not work out of the box, so explore it only for learning purposes (or to take bits and pieces for your own system)!

Please create [issues](https://github.com/beatzxbt/bybit-smm/issues) to flag bugs or suggest new features and feel free to create a [pull request](https://github.com/beatzxbt/bybit-smm/pulls) with any improvements.


If you have any questions or suggestions regarding the repo, or just want to have a chat, my handles are below 👇🏼

Twitter: [@beatzXBT](https://twitter.com/BeatzXBT) | Discord: gamingbeatz


## Donations
If you want to buy me a coffee (much appreciated :D), my addresses are below:

-USDC: 0x84a16e23c38f84709395720b08348d86883acf81 (Arbitrum)

-USDC: 9mJw3Wyifr19vqHJp6SLK86sDXrE6Ayk96U7F4Wano2H (Solana)

-ETH: 0x84a16e23c38f84709395720b08348d86883acf81 (ERC20)

If you are feeling generous but cant send over any of the above chains for whatever reason, feel free to DM on Twitter/Discord and we can sort something out :)
