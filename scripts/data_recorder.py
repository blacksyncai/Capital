#!/usr/bin/env python3
"""
Market Data Recorder

Records market data from both brokers for historical analysis.
"""

import sys
import time
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.database import get_database
from src.core.config import get_config
from src.core.logging import setup_logging, get_logger
from src.execution.order_manager import get_order_manager


def main():
    """Main recording function."""
    print("=" * 60)
    print("Cross-Broker Trading System - Market Data Recorder")
    print("=" * 60)
    
    # Setup logging
    log_dir = project_root / "logs"
    loggers = setup_logging(log_dir=log_dir)
    logger = get_logger("data_recorder")
    
    # Configuration
    config = get_config()
    instrument = config.get_primary_instrument()
    interval_seconds = 1  # Record every second
    max_records = 10000  # Max records per run
    
    try:
        # Initialize components
        logger.info("Initializing components...")
        db = get_database()
        db.initialize()
        
        order_manager = get_order_manager()
        order_manager.initialize()
        order_manager.connect_all()
        
        logger.info(f"Starting data recording for {instrument}")
        print(f"\nRecording market data for {instrument}...")
        print(f"Interval: {interval_seconds} second(s)")
        print(f"Press Ctrl+C to stop\n")
        
        # Main recording loop
        record_count = 0
        try:
            while True:
                timestamp = datetime.utcnow()
                
                # Get ticks from both brokers
                for broker_id in ["vantage", "justmarkets"]:
                    try:
                        tick = order_manager.get_tick(broker_id, instrument)
                        if tick:
                            # Save to database
                            # (Implementation would go here)
                            # For now, just log
                            logger.info(
                                f"{broker_id} - {instrument}: "
                                f"Bid={tick.bid:.4f}, Ask={tick.ask:.4f}, "
                                f"Spread={tick.spread:.4f}"
                            )
                            record_count += 1
                    except Exception as e:
                        logger.error(f"Error getting tick from {broker_id}: {e}")
                
                # Check if we've reached max records
                if max_records > 0 and record_count >= max_records:
                    logger.info(f"Reached maximum records: {record_count}")
                    break
                
                # Sleep
                time.sleep(interval_seconds)
                
        except KeyboardInterrupt:
            logger.info("Data recording stopped by user")
            print("\n\nData recording stopped by user")
            
        finally:
            # Cleanup
            order_manager.disconnect_all()
            
        print(f"\nTotal records: {record_count}")
        logger.info(f"Data recording completed. Total records: {record_count}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Data recording failed: {e}")
        print(f"\n✗ Data recording failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
