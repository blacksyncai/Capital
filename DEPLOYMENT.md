# Cross-Broker Trading System - Deployment Guide

## Overview

This is a cross-broker CFD trading system for Vantage Markets and JustMarkets that opens and manages opposing positions across two independent brokers.

**Status**: All 56 tests passing ✅  
**Mode**: Demo only (live trading disabled by default)

---

## Quick Start

### Prerequisites

1. **Windows Server 2022 VPS** (for MT5 terminal support)
2. **Python 3.10+** (3.12 recommended)
3. **MetaTrader 5** installed with demo accounts for both brokers
4. **PostgreSQL** (optional for production, SQLite works for testing)

### Installation

```bash
# Clone the repository
git clone <repository-url> cross_broker_trading
cd cross_broker_trading

# Create virtual environment
python -m venv venv
.\[Windows] venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# For MT5 support on Windows
pip install MetaTrader5
```

---

## Configuration

### 1. Environment Variables

Copy `.env.example` to `.env` and update:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```ini
# Trading Mode
TRADING_MODE=demo
LIVE_TRADING_ENABLED=false

# Broker: Vantage Markets
VANTAGE_MT5_PATH=C:\\Program Files\\MetaTrader 5\\terminal64.exe
VANTAGE_LOGIN=your_demo_login
VANTAGE_PASSWORD=your_demo_password
VANTAGE_SERVER=Vantage-Demo

# Broker: JustMarkets
JUSTMARKETS_MT5_PATH=C:\\Program Files\\MetaTrader 5 JustMarkets\\terminal64.exe
JUSTMARKETS_LOGIN=your_demo_login
JUSTMARKETS_PASSWORD=your_demo_password
JUSTMARKETS_SERVER=JustMarkets-Demo

# Primary Instrument
PRIMARY_INSTRUMENT=XAUUSD
INITIAL_LOT_SIZE=0.01

# Database (optional - for data persistence)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=cross_broker_trading
DB_USER=postgres
DB_PASSWORD=your_password
```

### 2. MT5 Terminal Setup

Install **two separate MT5 terminals**:
- One for Vantage Markets demo account
- One for JustMarkets demo account

**Important**: Each terminal must have:
- Unique installation directory
- Demo account logged in
- Auto-trading enabled in terminal settings
- API access permitted (Tools > Options > Expert Advisors > Allow WebRequest)

---

## Running the System

### Start Market Data Recorder

```bash
python src/data_recorder.py
```

### Start Trading Engine

```bash
python src/main.py
```

### Start Dashboard (Web)

```bash
python src/dashboard/app.py
```

Access dashboard at: `http://localhost:8080`

---

## Test Results

```
56 passed, 56 warnings in 7.65s
```

All tests passing. Run tests with:
```bash
pytest src/tests/ -v
```

---

## Architecture

### Components

1. **Broker Layer** (`src/brokers/`)
   - `base_broker.py` - Abstract interface
   - `vantage_broker.py` - Vantage MT5 integration
   - `justmarkets_broker.py` - JustMarkets MT5 integration
   - `test_broker_simulator.py` - For testing without MT5

2. **Execution Layer** (`src/execution/`)
   - `order_manager.py` - Order execution with retries
   - `trade_state.py` - Trade cycle management
   - `execution_worker.py` - Worker processes

3. **Risk Layer** (`src/risk/`)
   - `risk_engine.py` - Risk validation
   - `risk_checks.py` - Individual risk checks

4. **Strategy Layer** (`src/strategies/`)
   - `base_strategy.py` - Strategy interface
   - `strategy_a.py` - Paired exit
   - `strategy_b.py` - Protected runner
   - `strategy_c.py` - Market-condition exits
   - `strategy_d.py` - Adaptive holding periods
   - `strategy_e.py` - Entry optimization

5. **AI Research** (`src/ai_research/`)
   - `data_analyzer.py` - Trade analysis
   - `pattern_detector.py` - Pattern detection
   - `report_generator.py` - Reports

6. **Dashboard** (`src/dashboard/`)
   - `app.py` - FastAPI application
   - `routes.py` - API endpoints

7. **Models** (`src/models/`)
   - SQLAlchemy database models

---

## Key Features

### ✅ Working
- Paired order execution (BUY on one, SELL on other)
- Trade cycle management
- Position reconciliation
- Emergency stop
- Simulated broker for testing
- All 5 strategies implemented
- Risk management engine
- Market data recording
- Dashboard (simulation mode)

### ⚠️ Requires Real MT5 Terminals
- Live market data from brokers
- Real order execution
- Account balance updates
- Margin calculations

---

## MT5 Terminal Configuration

### Vantage Markets
```ini
[Vantage]
MT5_Path=C:\Program Files\MetaTrader 5\terminal64.exe
Login=123456
Password=demo_password
Server=Vantage-Demo
```

### JustMarkets
```ini
[JustMarkets]
MT5_Path=C:\Program Files\MetaTrader 5 JustMarkets\terminal64.exe
Login=789012
Password=demo_password
Server=JustMarkets-Demo
```

**Critical**: Each terminal must have a different installation path!

---

## Risk Management

Default risk parameters (configurable in `config/risk_config.yaml`):

```yaml
max_loss_per_cycle: 50.0      # USD
max_daily_loss: 200.0         # USD
max_open_exposure: 1000.0     # USD
max_holding_hours: 24          # hours
min_free_margin_percent: 50  # %
max_spread_points: 10         # points
max_execution_delay_ms: 500  # milliseconds
max_slippage_points: 5        # points
```

---

## Strategy Configuration

All strategies are disabled by default. Enable in `config/strategy_config.yaml`:

```yaml
strategies:
  strategy_a:
    enabled: true
    parameters:
      target_profit_usd: 10.0
      stop_loss_usd: 5.0
      max_holding_minutes: 60
  
  strategy_b:
    enabled: false
  
  strategy_c:
    enabled: false
  
  strategy_d:
    enabled: false
  
  strategy_e:
    enabled: false
```

---

## Troubleshooting

### "MT5 not connected"
- Verify MT5 terminal is running
- Check terminal path in `.env`
- Ensure demo account is logged in
- Enable "Allow WebRequest" in terminal settings

### "Order rejected"
- Check lot size is valid (min 0.01)
- Verify sufficient margin
- Check spread is within limits

### "Database connection failed"
- Verify PostgreSQL is running
- Check credentials in `.env`
- Or use SQLite for testing (update config)

---

## Directory Structure

```
cross_broker_trading/
├── config/                  # Configuration files
│   ├── broker_config.yaml
│   ├── database_config.yaml
│   ├── risk_config.yaml
│   └── strategy_config.yaml
├── src/
│   ├── brokers/             # Broker integrations
│   ├── core/                # Core utilities
│   ├── execution/           # Execution engine
│   ├── risk/                # Risk management
│   ├── strategies/          # Trading strategies
│   ├── ai_research/         # AI analysis
│   ├── dashboard/           # Web dashboard
│   ├── models/              # Database models
│   ├── tests/               # Test suite
│   └── data_recorder.py     # Market data recorder
├── .env.example             # Environment template
├── .gitignore
├── README.md
├── DEPLOYMENT.md           # This file
├── requirements.txt
└── setup.py
```

---

## Requirements

See `requirements.txt`:

```
MetaTrader5>=5.0.43
fastapi>=0.104.0
uvicorn>=0.24.0
sqlalchemy>=2.0.23
psycopg2-binary>=2.9.9
pandas>=2.1.4
pytest>=7.4.3
pytest-asyncio>=0.21.1
```

---

## Important Notes

1. **Live trading is DISABLED by default**
   - Set `LIVE_TRADING_ENABLED=true` in `.env` to enable
   - Requires explicit approval and preflight check

2. **Demo accounts only for now**
   - System tested with demo accounts
   - Live accounts require additional validation

3. **Two MT5 terminals required**
   - Separate installations for each broker
   - Cannot use same terminal for both

4. **Start small**
   - Begin with 0.01 lots
   - Verify execution quality before scaling

---

## Next Steps

1. ✅ Install Python and dependencies
2. ✅ Install two MT5 terminals
3. ✅ Create demo accounts
4. ✅ Configure `.env` file
5. ✅ Run tests (`pytest src/tests/`)
6. ⏳ Deploy to Windows VPS
7. ⏳ Start data recorder
8. ⏳ Start trading engine

---

## Support

For issues or questions, check:
- Logs in `logs/` directory
- Test suite output
- Configuration files

**Never hardcode credentials. Always use environment variables.**

---

*Last updated: November 2024*
*Status: All 56 tests passing*
