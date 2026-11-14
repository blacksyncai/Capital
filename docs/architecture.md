# System Architecture

## Overview

The Cross-Broker AI Trading & Strategy Research System is designed to manage opposing CFD positions across Vantage Markets and JustMarkets brokers, with comprehensive risk management, strategy testing, and AI-assisted analysis.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CROSS-BROKER TRADING SYSTEM                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        WEB DASHBOARD                                 │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────┐  │   │
│  │  │   FastAPI    │  │   Jinja2    │  │   Static Files              │  │   │
│  │  │   Server     │  │   Templates │  │   (CSS, JS, Images)         │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                       │
│                                    ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      EXECUTION LAYER                                │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │                    Execution Worker                           │   │   │
│  │  │  - Task queue management                                       │   │   │
│  │  │  - Background processing                                        │   │   │
│  │  │  - Async task execution                                         │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  │                                                                     │   │
│  │  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐  │   │
│  │  │   Order         │    │   Trade State   │    │   Risk Engine   │  │   │
│  │  │   Manager       │    │   Manager       │    │                 │  │   │
│  │  │  - Order exec   │    │  - Cycle mgmt   │    │  - Risk checks  │  │   │
│  │  │  - Broker conn  │    │  - Reconciliation│   │  - Violations   │  │   │
│  │  │  - Idempotency  │    │  - State tracking│   │  - Emergency stop│  │   │
│  │  └─────────────────┘    └─────────────────┘    └─────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                       │
│                                    ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      BROKER LAYER                                   │   │
│  │  ┌─────────────────┐              ┌─────────────────┐                 │   │
│  │  │   Vantage       │              │   JustMarkets   │                 │   │
│  │  │   MT5 Terminal  │              │   MT5 Terminal  │                 │   │
│  │  │  - MetaTrader5  │              │  - MetaTrader5  │                 │   │
│  │  │  - Demo/Real    │              │  - Demo/Real    │                 │   │
│  │  └─────────────────┘              └─────────────────┘                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                       │
│                                    ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      DATA LAYER                                    │   │
│  │  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐  │   │
│  │  │   PostgreSQL    │    │   Market Data   │    │   Trade Data    │  │   │
│  │  │   Database      │    │   Recorder      │    │   Storage       │  │   │
│  │  │  - Tables       │    │  - Tick data    │    │  - Cycles       │  │   │
│  │  │  - Indexes      │    │  - Bar data     │    │  - Trades       │  │   │
│  │  │  - Queries      │    │  - Spreads      │    │  - Positions    │  │   │
│  │  └─────────────────┘    └─────────────────┘    └─────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      STRATEGY LAYER                                 │   │
│  │  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐  │   │
│  │  │   Strategy A    │    │   Strategy B    │    │   Strategy C    │  │   │
│  │  │   Paired Exit   │    │   Protected     │    │   Market Cond.  │  │   │
│  │  │                 │    │   Runner        │    │   Exits         │  │   │
│  │  └─────────────────┘    └─────────────────┘    └─────────────────┘  │   │
│  │                                                                     │   │
│  │  ┌─────────────────┐    ┌─────────────────┐                          │   │
│  │  │   Strategy D    │    │   Strategy E    │                          │   │
│  │  │   Adaptive      │    │   Entry Opt.    │                          │   │
│  │  │   Holding       │    │                 │                          │   │
│  │  └─────────────────┘    └─────────────────┘                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                       │
│                                    ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      AI RESEARCH LAYER                             │   │
│  │  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐  │   │
│  │  │   Data Analyzer │    │   Pattern       │    │   Report        │  │   │
│  │  │                 │    │   Detector      │    │   Generator     │  │   │
│  │  │  - Metrics      │    │  - Streaks      │    │  - Text/HTML    │  │   │
│  │  │  - Insights     │    │  - Time patterns │    │  - JSON         │  │   │
│  │  │  - Comparisons  │    │  - P&L patterns  │    │  - Markdown     │  │   │
│  │  └─────────────────┘    └─────────────────┘    └─────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Web Dashboard

**Technologies:** FastAPI, Jinja2, HTML/CSS/JavaScript

**Responsibilities:**
- REST API endpoints for system monitoring
- Real-time web interface
- Connection status display
- Account balances and equity
- Open paired positions
- Combined live P&L
- Trade history
- Risk metrics
- Strategy comparisons
- Execution errors
- Emergency stop controls

**Endpoints:**
- `/api/v1/status` - System status
- `/api/v1/brokers` - Broker status
- `/api/v1/cycles` - Trade cycles
- `/api/v1/pnl` - Profit and loss
- `/api/v1/risk` - Risk status
- `/api/v1/strategies` - Strategy status
- `/api/v1/analysis` - Analysis endpoints
- `/api/v1/market` - Market data

### 2. Execution Layer

#### Order Manager
- Manages order execution across both brokers
- Provides idempotent order handling
- Implements retry logic
- Handles order timeouts
- Tracks order status
- Manages paired orders (opposing positions)

#### Trade State Manager
- Tracks the state of paired trades
- Manages trade cycle lifecycle
- Provides position reconciliation
- Ensures consistency across brokers
- Handles error recovery
- Persists trade state

#### Execution Worker
- Background worker for trade execution
- Processes tasks from a queue
- Monitors positions
- Reconciles state periodically
- Handles errors and retries

#### Risk Engine
- Central risk management
- Coordinates all risk checks
- Preflight checks before trading
- Runtime risk monitoring
- Emergency stop functionality
- Risk violation tracking

### 3. Broker Layer

**Technologies:** MetaTrader5 Python Package

**Responsibilities:**
- Connect to MT5 terminals
- Retrieve account information
- Get market data (ticks, bars)
- Send orders (market, limit, stop)
- Manage positions
- Modify and cancel orders
- Handle connection errors

**Brokers:**
- Vantage Markets (Demo/Real)
- JustMarkets (Demo/Real)

### 4. Data Layer

**Technologies:** PostgreSQL, SQLAlchemy

**Database Schema:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           POSTGRESQL DATABASE                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐               │
│  │   trades     │    │  market_data │    │   accounts   │               │
│  │              │    │              │    │              │               │
│  │ - trade_id   │    │ - broker_id  │    │ - broker_id  │               │
│  │ - broker_id  │    │ - instrument │    │ - account_id │               │
│  │ - instrument │    │ - bid/ask    │    │ - balance    │               │
│  │ - side       │    │ - timestamp  │    │ - equity     │               │
│  │ - volume     │    │ - volume     │    │ - margin     │               │
│  │ - prices     │    │              │    │              │               │
│  │ - status     │    └──────────────┘    └──────────────┘               │
│  │ - timestamps │                                                          │
│  └──────────────┘                                                          │
│                                                                           │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐               │
│  │  positions   │    │   orders     │    │  trade_cycles│               │
│  │              │    │              │    │              │               │
│  │ - position_id│    │ - order_id   │    │ - cycle_id   │               │
│  │ - broker_id  │    │ - broker_id  │    │ - strategy_id│               │
│  │ - instrument │    │ - instrument │    │ - instrument │               │
│  │ - side       │    │ - type       │    │ - lot_size   │               │
│  │ - volume     │    │ - side       │    │ - direction  │               │
│  │ - prices     │    │ - volume     │    │ - status     │               │
│  │ - timestamps │    │ - prices     │    │ - timestamps │               │
│  └──────────────┘    └──────────────┘    └──────────────┘               │
│                                                                           │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐               │
│  │   rebates    │    │ risk_violations│   │execution_errors│            │
│  │              │    │              │    │              │               │
│  │ - rebate_id  │    │ - violation_id│   │ - error_id   │               │
│  │ - trade_id   │    │ - check_name │   │ - error_type │               │
│  │ - amount     │    │ - severity   │   │ - message    │               │
│  │ - status     │    │ - message    │   │ - context    │               │
│  │ - timestamps │    │ - timestamp  │   │ - timestamp  │               │
│  └──────────────┘    └──────────────┘    └──────────────┘               │
│                                                                           │
│  ┌──────────────┐    ┌──────────────┐                                 │
│  │ system_logs  │    │ strategy_perf│                                 │
│  │              │    │              │                                 │
│  │ - log_id     │    │ - strategy_id│                                 │
│  │ - timestamp  │    │ - metrics    │                                 │
│  │ - level      │    │ - timestamp  │                                 │
│  │ - message    │    └──────────────┘                                 │
│  └──────────────┘                                                          │
│                                                                           │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5. Strategy Layer

**Strategy A: Paired Exit**
- Opens opposing positions on both brokers
- Closes both when combined P&L reaches target
- Time-based exit after maximum holding period
- Stop loss exit

**Strategy B: Protected Runner**
- Opens opposing positions
- Closes one position under predefined conditions
- Allows remaining position to run with protective stop
- Trailing stop support

**Strategy C: Market Condition Exits**
- Exits based on volatility
- Exits based on momentum
- Exits based on spread conditions
- Exits based on market sessions
- Exits based on short-term price behavior

**Strategy D: Adaptive Holding Periods**
- Tests different holding periods
- Adapts to best performing period
- Optimizes P&L and costs
- Tracks performance metrics

**Strategy E: Entry Optimization**
- Delays entries until conditions improve
- Checks spread conditions
- Checks execution quality
- Checks market stability
- Queues orders for better conditions

### 6. AI Research Layer

**Data Analyzer**
- Analyzes historical trade data
- Calculates performance metrics
- Generates insights
- Compares strategies

**Pattern Detector**
- Detects winning/losing streaks
- Identifies time-based patterns
- Finds P&L patterns
- Detects holding time patterns

**Report Generator**
- Generates strategy performance reports
- Creates strategy comparison reports
- Produces pattern analysis reports
- Generates execution quality reports
- Creates comprehensive research reports
- Supports multiple formats (JSON, HTML, Markdown, text)

## Data Flow

### Trade Execution Flow

```
1. Strategy generates trade signal
2. Risk engine checks pre-trade conditions
   - Max loss per cycle
   - Max daily loss
   - Max exposure
   - Min margin
   - Max spread
   - Emergency stop status
3. If all checks pass, create trade cycle
4. Order manager sends paired orders to both brokers
5. Trade state manager tracks cycle state
6. Strategy monitors cycle and decides when to close
7. Risk engine checks pre-close conditions
8. Order manager closes both positions
9. Trade state manager updates cycle status
10. Results saved to database
```

### Market Data Flow

```
1. Market data recorder polls brokers for ticks
2. Tick data saved to database
3. Data analyzer processes historical data
4. Pattern detector identifies patterns
5. Reports generated for analysis
```

### Risk Management Flow

```
1. Risk engine runs all checks periodically
2. Violations recorded in database
3. Blocking violations prevent new trades
4. Emergency stop can be triggered manually or automatically
5. All active positions closed on emergency stop
6. Violations can be acknowledged to clear warnings
```

## Technology Stack

### Core Technologies
- **Python 3.10+** - Primary programming language
- **MetaTrader5** - Broker connectivity
- **PostgreSQL** - Database
- **SQLAlchemy** - ORM
- **FastAPI** - Web framework
- **Uvicorn** - ASGI server
- **Pandas** - Data analysis
- **NumPy** - Numerical computations

### Optional Technologies
- **Pydantic** - Data validation
- **Jinja2** - HTML templates
- **asyncio** - Async programming
- **pytest** - Testing
- **Cerebras/Other AI** - AI inference (for research module)

## Deployment Architecture

### Development Environment
```
┌─────────────────────────────────────────────────────────┐
│                    Developer Machine                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │   VS Code   │  │   Python     │  │   PostgreSQL     │  │
│  │   IDE       │  │   Runtime    │  │   (Local)       │  │
│  └─────────────┘  └─────────────┘  └─────────────────┘  │
│  ┌─────────────────────────────────────────────────────┐│
│  │                    MT5 Terminals                       ││
│  │  ┌─────────────┐              ┌─────────────┐       ││
│  │  │  Vantage    │              │  JustMarkets │       ││
│  │  │  Terminal   │              │  Terminal   │       ││
│  │  └─────────────┘              └─────────────┘       ││
│  └─────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

### Production Environment (Recommended)
```
┌─────────────────────────────────────────────────────────┐
│                    Windows VPS                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │                    MT5 Terminals                       │  │
│  │  ┌─────────────┐              ┌─────────────┐       │  │
│  │  │  Vantage    │              │  JustMarkets │       │  │
│  │  │  Terminal   │              │  Terminal   │       │  │
│  │  └─────────────┘              └─────────────┘       │  │
│  └─────────────────────────────────────────────────────┘  │
│                                    │                         │
│                                    ▼                         │
│  ┌─────────────────────────────────────────────────────┐  │
│  │                    Application Server                  │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │  │
│  │  │   FastAPI    │  │   Python     │  │   PostgreSQL │  │  │
│  │  │   Dashboard  │  │   Runtime    │  │   (Remote)   │  │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### Cloud Deployment (Railway)
```
┌─────────────────────────────────────────────────────────┐
│                    Railway Cloud                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │                    Web Service                        │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │  │
│  │  │   FastAPI    │  │   Dashboard  │  │   Static    │  │  │
│  │  │   Server     │  │   Routes     │  │   Files     │  │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  │  │
│  └─────────────────────────────────────────────────────┘  │
│                                    │                         │
│                                    ▼                         │
│  ┌─────────────────────────────────────────────────────┐  │
│  │                    PostgreSQL                        │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │  │
│  │  │   Database  │  │   Tables     │  │   Queries    │  │  │
│  │  │   Instance  │  │   & Indexes  │  │   & Views    │  │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                    Windows VPS                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │                    MT5 Terminals                       │  │
│  │  (Connects to Railway via API)                         │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Configuration

### Environment Variables

See `.env.example` for all available configuration options.

### Configuration Files

- `config/broker_config.yaml` - Broker-specific settings
- `config/risk_parameters.yaml` - Risk management parameters
- `config/strategy_config.yaml` - Strategy configurations
- `config/database_config.yaml` - Database settings

## Security Considerations

1. **Credentials**: Never hardcode credentials. Use environment variables.
2. **Database**: Use SSL for remote connections.
3. **API**: Implement authentication for the dashboard.
4. **MT5**: Ensure MT5 terminals are properly secured.
5. **Network**: Use firewalls and restrict access to necessary ports only.
6. **Logging**: Avoid logging sensitive information.

## Scalability

The system is designed to be scalable:

1. **Database**: PostgreSQL can handle large datasets with proper indexing.
2. **Execution**: Async processing allows for concurrent operations.
3. **Strategies**: Multiple strategies can run simultaneously.
4. **Brokers**: Architecture supports adding more brokers.
5. **Horizontal**: Can be deployed across multiple servers.

## Fault Tolerance

1. **Reconnection**: Automatic reconnection to brokers.
2. **Retry Logic**: Retry failed operations with exponential backoff.
3. **State Persistence**: Trade state is persisted to database.
4. **Reconciliation**: Regular position reconciliation.
5. **Emergency Stop**: Manual and automatic emergency stop mechanisms.
