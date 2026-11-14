# Setup Guide

## Prerequisites

Before you begin, ensure you have the following:

### System Requirements
- **Operating System**: Windows 10/11 (for MT5 terminals) or Linux/macOS (with Wine for MT5)
- **Python**: Python 3.10 or higher
- **Memory**: 4GB RAM minimum (8GB recommended)
- **Disk Space**: 10GB free disk space
- **Network**: Stable internet connection

### Software Requirements
- **MetaTrader 5**: Two separate MT5 terminals installed (one for each broker)
- **PostgreSQL**: PostgreSQL 12 or higher
- **Git**: For version control
- **pip**: Python package manager

---

## Step 1: Clone the Repository

```bash
# Clone the repository
git clone <repository-url> cross_broker_trading
cd cross_broker_trading

# Or if you have the files already
cd /path/to/cross_broker_trading
```

---

## Step 2: Install Python Dependencies

### Create Virtual Environment (Recommended)

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### Install Required Packages

```bash
# Install core dependencies
pip install -r requirements.txt
```

### Install MetaTrader5 Package

The MetaTrader5 Python package is **not** available on PyPI. You must download and install it manually:

1. **Download from MetaQuotes website**:
   - Go to: https://www.mql5.com/en/docs/integration/python_metatrader5
   - Download the appropriate package for your Python version

2. **Install the package**:
   ```bash
   # Example for Python 3.10 on Windows
   pip install MetaTrader5-5.0.43-cp310-cp310-win_amd64.whl
   
   # Or for Python 3.11
   pip install MetaTrader5-5.0.43-cp311-cp311-win_amd64.whl
   ```

3. **Verify installation**:
   ```python
   import MetaTrader5 as mt5
   print(mt5.__version__)
   ```

---

## Step 3: Setup PostgreSQL Database

### Option A: Local PostgreSQL Installation

#### Install PostgreSQL

**Windows**:
- Download from: https://www.postgresql.org/download/windows/
- Run installer and follow prompts
- Remember the password you set

**macOS**:
```bash
brew install postgresql
brew services start postgresql
```

**Linux (Ubuntu/Debian)**:
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
```

#### Create Database and User

```bash
# Connect to PostgreSQL
sudo -u postgres psql

-- Create user
CREATE USER cross_broker_user WITH PASSWORD 'your_secure_password';

-- Create database
CREATE DATABASE cross_broker_trading WITH OWNER cross_broker_user;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE cross_broker_trading TO cross_broker_user;

-- Exit
\q
```

### Option B: Railway PostgreSQL (Cloud)

1. **Sign up for Railway**: https://railway.app
2. **Create a new project**
3. **Add PostgreSQL service**
4. **Copy connection details** (host, port, username, password)
5. **Note**: Railway uses `postgres` as the default username

### Option C: Other Cloud Providers

- **AWS RDS**: Create a PostgreSQL instance
- **Google Cloud SQL**: Create a PostgreSQL instance
- **Azure Database**: Create a PostgreSQL instance
- **ElephantSQL**: https://www.elephantsql.com
- **Supabase**: https://supabase.com

### Setup Database Tables

```bash
# Run the database setup script
python scripts/setup_database.py
```

This will create all necessary tables in your database.

---

## Step 4: Configure MT5 Terminals

### Install MetaTrader 5

1. **Download MT5**:
   - Vantage Markets: https://www.vantagemarkets.com/platforms/metatrader-5/
   - JustMarkets: https://justmarkets.com/platforms/metatrader-5

2. **Install both terminals**:
   - Install Vantage MT5 terminal
   - Install JustMarkets MT5 terminal
   - Keep both installed in separate directories

### Open Demo Accounts

1. **Vantage Markets**:
   - Open the Vantage MT5 terminal
   - Click "File" > "Open an Account"
   - Select "Demo Account"
   - Fill in your details
   - Note down: Login, Password, Server

2. **JustMarkets**:
   - Open the JustMarkets MT5 terminal
   - Click "File" > "Open an Account"
   - Select "Demo Account"
   - Fill in your details
   - Note down: Login, Password, Server

### Verify Server Addresses

Check the server addresses in your MT5 terminals:
- In MT5, click "File" > "Login to Trade Account"
- The server address is displayed in the login window

Common server addresses:
- Vantage Demo: `Vantage-Demo` or `54.254.150.105:443`
- JustMarkets Demo: `JustMarkets-Demo` or `185.141.63.241:443`

---

## Step 5: Configure the System

### Create Environment File

Copy the example environment file and fill in your credentials:

```bash
# Copy example file
cp .env.example .env

# Edit the file
nano .env  # or use your preferred editor
```

### Edit `.env` File

```ini
# DATABASE CONFIGURATION
DB_HOST=localhost
DB_PORT=5432
DB_NAME=cross_broker_trading
DB_USER=cross_broker_user
DB_PASSWORD=your_secure_password_here

# BROKER CONFIGURATION - Vantage Markets
VANTAGE_LOGIN=12345678
VANTAGE_PASSWORD=your_vantage_demo_password
VANTAGE_SERVER=Vantage-Demo
VANTAGE_SERVER_ADDRESS=54.254.150.105:443
VANTAGE_ACCOUNT_TYPE=DEMO
VANTAGE_MT5_PATH=C:/Program Files/Vantage MT5/terminal64.exe

# BROKER CONFIGURATION - JustMarkets
JUSTMARKETS_LOGIN=87654321
JUSTMARKETS_PASSWORD=your_justmarkets_demo_password
JUSTMARKETS_SERVER=JustMarkets-Demo
JUSTMARKETS_SERVER_ADDRESS=185.141.63.241:443
JUSTMARKETS_ACCOUNT_TYPE=DEMO
JUSTMARKETS_MT5_PATH=C:/Program Files/JustMarkets MT5/terminal64.exe

# TRADING CONFIGURATION
PRIMARY_INSTRUMENT=XAUUSD
INITIAL_LOT_SIZE=0.01
TRADING_MODE=DEMO
LIVE_TRADING_ENABLED=false

# RISK PARAMETERS (Use conservative defaults)
MAX_LOSS_PER_CYCLE=10.0
MAX_DAILY_LOSS=50.0
MAX_OPEN_EXPOSURE=100.0
MAX_HOLDING_TIME_HOURS=24
MIN_FREE_MARGIN_PERCENT=50.0
MAX_SPREAD_POINTS=10
MAX_EXECUTION_DELAY_SECONDS=5
MAX_SLIPPAGE_POINTS=5

# IB REBATE CONFIGURATION
VANTAGE_REBATE_PER_LOT=10.0
VANTAGE_MIN_HOLDING_TIME_MINUTES=5
VANTAGE_ELIGIBLE_INSTRUMENTS=XAUUSD,XAGUSD,BTCUSD,ETHUSD

JUSTMARKETS_REBATE_PER_LOT=8.0
JUSTMARKETS_MIN_HOLDING_TIME_MINUTES=5
JUSTMARKETS_ELIGIBLE_INSTRUMENTS=XAUUSD,XAGUSD,BTCUSD,ETHUSD

# DASHBOARD CONFIGURATION
DASHBOARD_HOST=localhost
DASHBOARD_PORT=8000
DASHBOARD_AUTH_ENABLED=false
```

### Configure Broker YAML Files

Edit the configuration files in the `config/` directory if needed:

- `config/broker_config.yaml` - Broker-specific settings
- `config/risk_parameters.yaml` - Risk management parameters
- `config/strategy_config.yaml` - Strategy configurations
- `config/database_config.yaml` - Database settings

---

## Step 6: Test the Setup

### Test Database Connection

```bash
# Run a quick test
python -c "from src.core.database import get_database; db = get_database(); db.initialize(); print('Database connection successful!')"
```

### Test Broker Connections

```bash
# Test Vantage connection
python -c "
from src.brokers.vantage_broker import VantageBroker
from src.core.config import get_config
config = get_config()
broker = VantageBroker()
try:
    broker.connect()
    print('Vantage connection successful!')
    print(f'Account: {broker.account_info.account_id}')
    print(f'Balance: {broker.account_info.balance}')
    broker.disconnect()
except Exception as e:
    print(f'Vantage connection failed: {e}')
"

# Test JustMarkets connection
python -c "
from src.brokers.justmarkets_broker import JustMarketsBroker
from src.core.config import get_config
config = get_config()
broker = JustMarketsBroker()
try:
    broker.connect()
    print('JustMarkets connection successful!')
    print(f'Account: {broker.account_info.account_id}')
    print(f'Balance: {broker.account_info.balance}')
    broker.disconnect()
except Exception as e:
    print(f'JustMarkets connection failed: {e}')
"
```

### Test Market Data

```bash
# Test getting tick data
python -c "
from src.execution.order_manager import get_order_manager
om = get_order_manager()
om.initialize()
om.connect_all()
tick = om.get_tick('vantage', 'XAUUSD')
print(f'Vantage XAUUSD: Bid={tick.bid:.2f}, Ask={tick.ask:.2f}, Spread={tick.spread:.2f}')
tick = om.get_tick('justmarkets', 'XAUUSD')
print(f'JustMarkets XAUUSD: Bid={tick.bid:.2f}, Ask={tick.ask:.2f}, Spread={tick.spread:.2f}')
om.disconnect_all()
"
```

---

## Step 7: Run the Dashboard

### Start the Dashboard

```bash
# Start the FastAPI dashboard
uvicorn src.dashboard.app:create_app --reload
```

Or use the convenience script:

```bash
python -m src.dashboard.app
```

### Access the Dashboard

Open your web browser and navigate to:
- **Main Dashboard**: http://localhost:8000/dashboard
- **API Documentation**: http://localhost:8000/api/docs
- **Health Check**: http://localhost:8000/health

### Dashboard Features

- **Connection Status**: Check if both brokers are connected
- **Account Information**: View account balances and equity
- **Open Positions**: See all open positions across both brokers
- **Trade Cycles**: View active and completed trade cycles
- **P&L**: Monitor combined profit and loss
- **Risk Status**: View current risk violations
- **Execution**: Open and close trades
- **Emergency Stop**: Trigger emergency stop

---

## Step 8: Run the Execution Worker

### Start the Execution Worker

```bash
# In a separate terminal
python -c "
from src.execution.execution_worker import start_execution_worker
worker = start_execution_worker()
# Keep this running
"
```

Or create a script:

```python
# scripts/start_worker.py
from src.execution.execution_worker import start_execution_worker

if __name__ == '__main__':
    worker = start_execution_worker()
    print('Execution worker started. Press Ctrl+C to stop.')
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        worker.stop()
        print('Execution worker stopped.')
```

---

## Step 9: Test Trading (Demo Mode)

### Open a Trade Cycle

```bash
# Open a paired trade
python -c "
from src.execution.execution_worker import start_execution_worker
worker = start_execution_worker()
cycle_id = worker.open_cycle(
    instrument='XAUUSD',
    lot_size=0.01,
    direction='BUY_SELL',
    strategy_id='paired_exit'
)
print(f'Cycle opened: {cycle_id}')
"
```

### Check Cycle Status

```bash
# Check cycle status
python -c "
from src.execution.trade_state import get_trade_state_manager
tsm = get_trade_state_manager()
state = tsm.get_cycle_state('your-cycle-id')
print(f'Cycle state: {state}')
"
```

### Close a Trade Cycle

```bash
# Close a cycle
python -c "
from src.execution.execution_worker import get_execution_worker
worker = get_execution_worker()
worker.close_cycle('your-cycle-id', reason='manual_test')
"
```

---

## Step 10: Run Analysis

### Analyze Strategy Performance

```bash
# Analyze a strategy
python -c "
from src.ai_research import get_data_analyzer
analyzer = get_data_analyzer()
result = analyzer.analyze_strategy_performance('paired_exit')
print(result.to_dict())
"
```

### Detect Patterns

```bash
# Detect patterns
python -c "
from src.ai_research import get_pattern_detector
detector = get_pattern_detector()
result = detector.detect_all_patterns()
print(f'Detected {len(result.patterns)} patterns')
for pattern in result.patterns:
    print(f'  - {pattern.description}: {pattern.occurrences} occurrences')
"
```

### Generate Report

```bash
# Generate a report
python -c "
from src.ai_research import get_report_generator
generator = get_report_generator()
report = generator.generate_strategy_report('paired_exit')
print(generator.format_report(report, 'text'))
"
```

---

## Step 11: Enable Live Trading (Optional)

### ⚠️ WARNING ⚠️

**Live trading involves real money and significant risk.**

- **All live trading is disabled by default**
- **You must explicitly enable it**
- **Start with small amounts**
- **Test thoroughly in demo mode first**

### Steps to Enable Live Trading

1. **Open live accounts** with both brokers
2. **Update `.env` file**:
   ```ini
   TRADING_MODE=LIVE
   LIVE_TRADING_ENABLED=true
   
   # Update broker credentials
   VANTAGE_LOGIN=your_live_login
   VANTAGE_PASSWORD=your_live_password
   VANTAGE_SERVER=Vantage-Live
   VANTAGE_ACCOUNT_TYPE=REAL
   
   JUSTMARKETS_LOGIN=your_live_login
   JUSTMARKETS_PASSWORD=your_live_password
   JUSTMARKETS_SERVER=JustMarkets-Live
   JUSTMARKETS_ACCOUNT_TYPE=REAL
   ```

3. **Review risk parameters** in `config/risk_parameters.yaml`
4. **Run preflight checks**:
   ```bash
   python -c "
   from src.risk.risk_engine import get_risk_engine
   engine = get_risk_engine()
   engine.initialize()
   result = engine.run_preflight_checks()
   if result.all_passed:
       print('✓ All preflight checks passed!')
   else:
       print('✗ Preflight checks failed:')
       for v in result.violations:
           print(f'  - {v.message}')
   "
   ```

5. **Start with small lot sizes** (0.01 or less)
6. **Monitor closely**

---

## Troubleshooting

### Common Issues

#### 1. MetaTrader5 Package Not Found

**Error**: `ModuleNotFoundError: No module named 'MetaTrader5'`

**Solution**: Download and install from https://www.mql5.com/en/docs/integration/python_metatrader5

#### 2. MT5 Terminal Not Running

**Error**: `MT5 not initialized` or connection errors

**Solution**: 
- Ensure MT5 terminal is installed
- Ensure MT5 terminal is running
- Check the path in `.env` file
- Verify login credentials

#### 3. Database Connection Failed

**Error**: `Database connection failed`

**Solution**:
- Check database is running
- Verify connection details in `.env`
- Test connection manually:
  ```bash
  psql -h localhost -p 5432 -U cross_broker_user -d cross_broker_trading
  ```

#### 4. Broker Connection Failed

**Error**: `Connection failed` or `Invalid login`

**Solution**:
- Verify demo account credentials
- Check if demo account is still valid (expires after 30 days)
- Verify server address
- Try reconnecting

#### 5. Spread Too Wide

**Error**: `Spread too wide` or `Max spread exceeded`

**Solution**:
- Increase `MAX_SPREAD_POINTS` in risk parameters
- Wait for better market conditions
- Check if instrument is tradable

### Debug Mode

Enable debug logging:

```bash
# In .env file
LOG_LEVEL=DEBUG

# Or in code
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Log Files

Check log files in the `logs/` directory:
- `execution.log` - Execution-related logs
- `risk.log` - Risk management logs
- `strategy.log` - Strategy logs
- `market_data.log` - Market data logs
- `system.log` - System logs

---

## Next Steps

1. **Test thoroughly in demo mode**
2. **Review all strategies** and their configurations
3. **Adjust risk parameters** based on your risk tolerance
4. **Run backtests** using historical data
5. **Monitor performance** in demo mode
6. **Start with small live amounts** when ready
7. **Scale up gradually** as you gain confidence

---

## Support

For issues or questions:

1. **Check the documentation** in the `docs/` directory
2. **Review the logs** in the `logs/` directory
3. **Check the API documentation** at http://localhost:8000/api/docs
4. **Review the architecture** in `docs/architecture.md`

---

## Security Checklist

Before going live:

- [ ] All credentials are in environment variables (not in code)
- [ ] `.env` file is not committed to version control
- [ ] Database has proper authentication
- [ ] MT5 terminals are secured
- [ ] Network access is restricted
- [ ] Emergency stop is tested
- [ ] Risk parameters are conservative
- [ ] All preflight checks pass
- [ ] Live trading is explicitly enabled
- [ ] Starting with small lot sizes

---

## Maintenance

### Regular Tasks

1. **Monitor database size** - Clean up old data periodically
2. **Check logs** - Review logs for errors and warnings
3. **Update dependencies** - Keep Python packages up to date
4. **Test connections** - Verify broker connections daily
5. **Review performance** - Analyze strategy performance weekly

### Cleanup Scripts

```bash
# Clean up old logs (keep last 30 days)
find logs/ -name "*.log" -mtime +30 -delete

# Clean up old data (keep last 90 days)
# (Implement in your database maintenance)
```

---

## Updating the System

### Pull Latest Changes

```bash
cd /path/to/cross_broker_trading
git pull origin main
```

### Update Dependencies

```bash
pip install -r requirements.txt --upgrade
```

### Run Database Migrations

If there are database changes:

```bash
# Run setup script to update tables
python scripts/setup_database.py
```

---

## Conclusion

You now have a fully functional cross-broker trading system set up! The system is designed to be:

- **Safe**: All live trading disabled by default
- **Reliable**: Comprehensive error handling and recovery
- **Flexible**: Configurable strategies and risk parameters
- **Transparent**: Detailed logging and monitoring
- **Scalable**: Can grow with your needs

Start with demo trading, test thoroughly, and only enable live trading when you're completely comfortable with the system.
