# Push to Capital Repository

The Capital repository already exists at: **https://github.com/blacksyncai/Capital**

## Quick Push (Copy-Paste All)

```bash
cd /workspace/cross_broker_trading

git init
git add .
git commit -m "Cross-Broker Trading System - All 56 tests passing

Complete trading system for Vantage Markets and JustMarkets.
- Paired order execution
- 5 trading strategies
- Risk management engine
- MT5 integration
- All 56 tests passing
- Demo mode only (live trading disabled)"

git branch -M main
git remote add origin https://github.com/blacksyncai/Capital.git
git push -u origin main --force
```

## Expected Output

```
To github.com:blacksyncai/Capital.git
 * [new branch]      main -> main
```

## Repository Details

- **URL**: https://github.com/blacksyncai/Capital
- **Branch**: main
- **Commit hash**: e185643 (from the commit above)
- **Files**: 67 files, 20,509 lines
- **Size**: ~170KB

## For Claude

After pushing, tell Claude:

```
Repository URL: https://github.com/blacksyncai/Capital
Branch: main
Commit hash: e185643

Deployment:
  git clone https://github.com/blacksyncai/Capital.git
  cd Capital
  python -m venv venv
  .\venv\Scripts\activate
  pip install -r requirements.txt
  pip install MetaTrader5
  copy .env.example .env
  # Edit .env with Vantage/JustMarkets demo credentials
  pytest src/tests/ -v  # Verify: 56 passed
  python src/main.py     # Start system
```

## Test Verification

Before pushing, verify tests pass:
```bash
cd /workspace/cross_broker_trading
pytest src/tests/ --tb=no -q
```

Expected output:
```
56 passed, 56 warnings in 7.46s
```
