#!/usr/bin/env python3
"""
Database Setup Script

Creates all database tables and performs initial setup.
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.database import get_database, create_all_tables
from src.core.config import get_config
from src.core.logging import setup_logging, get_logger


def main():
    """Main setup function."""
    print("=" * 60)
    print("Cross-Broker Trading System - Database Setup")
    print("=" * 60)
    
    # Setup logging
    log_dir = project_root / "logs"
    loggers = setup_logging(log_dir=log_dir)
    logger = get_logger("setup")
    
    try:
        # Initialize database
        logger.info("Initializing database...")
        db = get_database()
        
        # Create tables
        logger.info("Creating database tables...")
        db.initialize()
        db.create_tables()
        
        logger.info("Database setup completed successfully!")
        print("\n✓ Database setup completed successfully!")
        print(f"\nDatabase connection:")
        print(f"  Host: {get_config().database_config.get('database', {}).get('host', 'localhost')}")
        print(f"  Port: {get_config().database_config.get('database', {}).get('port', 5432)}")
        print(f"  Name: {get_config().database_config.get('database', {}).get('name', 'cross_broker_trading')}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Database setup failed: {e}")
        print(f"\n✗ Database setup failed: {e}")
        print("\nPlease check the error and try again.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
