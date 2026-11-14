# Cross-Broker AI Trading & Strategy Research System

A comprehensive trading system that manages opposing CFD positions across Vantage Markets and JustMarkets brokers, with AI-assisted strategy research and IB rebate accounting.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Cross-Broker Trading System                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │  Vantage     │    │  JustMarkets │    │   PostgreSQL      │  │
│  │  MT5 Terminal │    │  MT5 Terminal │    │   Database        │  │
│  └──────┬───────┘    └──────┬───────┘    └──────────┬────────┘  │
│         │                   │                      │            │
│         ▼                   ▼                      ▼            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Execution Engine                       │   │
│  │  ┌──────────┐  ┌──────────┐  ┌─────────────────────────┐  │   │
│  │  │ Broker   │  │ Broker   │  │   Trade State           │  │   │
│  │  │ Worker A │  │ Worker B │  │   Manager               │  │   │
│  │  └────┬─────┘  └────┬─────┘  └───────────┬───────────┘  │   │
│  │       │              │                    │              │   │
│  └───────┼──────────────┼────────────────────┼──────────────┘   │
│          │              │                    │                  │
│          ▼              ▼                    ▼                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Risk Management                        │   │
│  │  ┌───────────────────────────────────────────────────┐  │   │
│  │  │  Deterministic Risk Engine                       │  │   │
│  │  │  - Max loss per cycle                           │  │   │
│  │  │  - Max daily loss                               │  │   │
│  │  │  - Max open exposure                            │  │   │
│  │  │  - Emergency stop                               │  │   │
│  │  └───────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Strategy Engine                       │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐              │   │
│  │  │ Strategy │  │ Strategy │  │ Strategy │              │   │
│  │  │    A     │  │    B     │  │    C     │              │   │
│  │  └──────────┘  └──────────┘  └──────────┘              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    AI Research Module                     │   │
│  │  - Pattern analysis                                   │   │
│  │  - Strategy comparison                                │   │
│  │  - Experiment reports                                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Web Dashboard                        │   │
│  │  - Connection status                                  │   │
│  │  - Live P&L                                          │   │
│  │  - Trade history                                     │   │
│  │  - Risk metrics                                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
cross_broker_trading/
├── config/
│   ├── broker_config.yaml
│   ├── risk_parameters.yaml
│   ├── strategy_config.yaml
│   └── database_config.yaml
├── src/
│   ├── brokers/
│   │   ├── __init__.py
│   │   ├── base_broker.py
│   │   ├── vantage_broker.py
│   │   └── justmarkets_broker.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── logging.py
│   │   └── database.py
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── order_manager.py
│   │   ├── trade_state.py
│   │   └── execution_worker.py
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── base_strategy.py
│   │   ├── strategy_a.py
│   │   ├── strategy_b.py
│   │   ├── strategy_c.py
│   │   ├── strategy_d.py
│   │   └── strategy_e.py
│   ├── risk/
│   │   ├── __init__.py
│   │   ├── risk_engine.py
│   │   └── risk_checks.py
│   ├── ai_research/
│   │   ├── __init__.py
│   │   ├── data_analyzer.py
│   │   ├── pattern_detector.py
│   │   └── report_generator.py
│   ├── dashboard/
│   │   ├── __init__.py
│   │   ├── app.py
│   │   ├── routes.py
│   │   └── templates/
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── trades.py
│   │   ├── market_data.py
│   │   ├── accounts.py
│   │   └── rebates.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── helpers.py
│   │   └── validators.py
│   └── tests/
│       ├── __init__.py
│       ├── test_brokers.py
│       ├── test_strategies.py
│       └── test_risk.py
├── data/
│   ├── market_data/
│   └── trade_history/
├── logs/
│   ├── execution.log
│   ├── risk.log
│   └── strategy.log
├── scripts/
│   ├── data_recorder.py
│   ├── backtest.py
│   ├── replay_engine.py
│   └── setup_database.py
├── docs/
│   ├── architecture.md
│   ├── setup_guide.md
│   ├── api_reference.md
│   └── deployment.md
├── requirements.txt
├── .env.example
└── README.md
```

## Development Phases

### Phase 1: Project Foundation ✅
- Repository structure
- Configuration system
- Database schema
- Core utilities

### Phase 2: Demo Broker Connectivity
- MT5 terminal connections
- Account information retrieval
- Market data collection
- Contract specification validation

### Phase 3: Execution Engine
- Paired order management
- Trade reconciliation
- Order monitoring
- Emergency exits

### Phase 4: Strategy Testing
- Replay engine
- Strategy implementations
- Performance comparison

### Phase 5: Dashboard
- Web interface
- Real-time monitoring
- Analytics

### Phase 6: Controlled Live Validation
- Small live accounts
- Execution quality measurement
- Rebate tracking

### Phase 7: Scaling
- Position size optimization
- Multi-instrument support
- Production deployment

## Quick Start

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Configure broker credentials (see `.env.example`)
4. Set up PostgreSQL database
5. Run setup: `python scripts/setup_database.py`
6. Start dashboard: `python -m src.dashboard.app`

## Important Notes

- **All live trading is disabled by default**
- **Explicit approval required before enabling live trading**
- **Do not hardcode credentials**
- **All secrets must be in environment variables**
- **MT5 terminals must be installed and running**

## License

Private - All rights reserved
