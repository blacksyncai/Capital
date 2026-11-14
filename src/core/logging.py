"""
Logging Module

Structured logging system with multiple output channels.
Supports file logging, console output, and structured logging.
"""

import logging
import logging.config
import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from datetime import datetime
from enum import Enum
import json

from .config import get_config


class LogLevel(Enum):
    """Log levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogChannel(Enum):
    """Log output channels."""
    CONSOLE = "console"
    FILE = "file"
    BOTH = "both"


class Logger:
    """
    Custom logger with structured logging support.
    
    Provides colored output, JSON formatting, and multiple output channels.
    """
    
    def __init__(
        self,
        name: str,
        log_level: Optional[Union[str, LogLevel]] = None,
        log_file: Optional[Union[str, Path]] = None,
        channel: LogChannel = LogChannel.BOTH,
        structured: bool = False,
        color: bool = True
    ):
        """
        Initialize the logger.
        
        Args:
            name: Logger name
            log_level: Minimum log level
            log_file: Path to log file
            channel: Output channel (console, file, both)
            structured: Use JSON structured logging
            color: Use colored output (console only)
        """
        self.name = name
        self.structured = structured
        self.color = color
        
        # Set log level
        if log_level is None:
            config = get_config()
            level_str = config.get("broker", "settings.log_level", "INFO")
            self.level = getattr(logging, level_str.upper(), logging.INFO)
        elif isinstance(log_level, LogLevel):
            self.level = getattr(logging, log_level.value, logging.INFO)
        else:
            self.level = getattr(logging, log_level.upper(), logging.INFO)
        
        # Create logger
        self._logger = logging.getLogger(name)
        self._logger.setLevel(self.level)
        self._logger.propagate = False
        
        # Remove existing handlers
        for handler in self._logger.handlers[:]:
            self._logger.removeHandler(handler)
        
        # Create formatters
        if structured:
            formatter = logging.Formatter('%(message)s')
        else:
            if color:
                formatter = ColorFormatter()
            else:
                formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                )
        
        # Add handlers based on channel
        if channel in [LogChannel.CONSOLE, LogChannel.BOTH]:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(self.level)
            console_handler.setFormatter(formatter)
            self._logger.addHandler(console_handler)
        
        if channel in [LogChannel.FILE, LogChannel.BOTH] and log_file:
            # Ensure directory exists
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(self.level)
            file_handler.setFormatter(formatter)
            self._logger.addHandler(file_handler)
    
    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message."""
        if self.structured:
            self._logger.debug(self._format_structured("DEBUG", message, kwargs))
        else:
            self._logger.debug(message, **kwargs)
    
    def info(self, message: str, **kwargs: Any) -> None:
        """Log info message."""
        if self.structured:
            self._logger.info(self._format_structured("INFO", message, kwargs))
        else:
            self._logger.info(message, **kwargs)
    
    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning message."""
        if self.structured:
            self._logger.warning(self._format_structured("WARNING", message, kwargs))
        else:
            self._logger.warning(message, **kwargs)
    
    def error(self, message: str, **kwargs: Any) -> None:
        """Log error message."""
        if self.structured:
            self._logger.error(self._format_structured("ERROR", message, kwargs))
        else:
            self._logger.error(message, **kwargs)
    
    def critical(self, message: str, **kwargs: Any) -> None:
        """Log critical message."""
        if self.structured:
            self._logger.critical(self._format_structured("CRITICAL", message, kwargs))
        else:
            self._logger.critical(message, **kwargs)
    
    def exception(self, message: str, exc_info: bool = True, **kwargs: Any) -> None:
        """Log exception with traceback."""
        if self.structured:
            log_data = self._format_structured("ERROR", message, kwargs)
            log_data["exception"] = True
            self._logger.error(log_data, exc_info=exc_info)
        else:
            self._logger.error(message, exc_info=exc_info, **kwargs)
    
    def _format_structured(self, level: str, message: str, kwargs: Dict[str, Any]) -> str:
        """Format structured log message as JSON."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "logger": self.name,
            "message": message,
            **kwargs
        }
        return json.dumps(log_data)
    
    @property
    def logger(self) -> logging.Logger:
        """Get the underlying logging.Logger instance."""
        return self._logger


class ColorFormatter(logging.Formatter):
    """
    Custom formatter with colored output.
    """
    
    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",    # Cyan
        "INFO": "\033[32m",     # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",    # Red
        "CRITICAL": "\033[1;31m", # Bold Red
        "RESET": "\033[0m",
    }
    
    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with colors."""
        levelname = record.levelname
        color = self.COLORS.get(levelname, self.COLORS["RESET"])
        reset = self.COLORS["RESET"]
        
        # Format the message
        message = super().format(record)
        
        # Add color to level
        colored_level = f"{color}{levelname}{reset}"
        
        # Replace levelname in the message
        return message.replace(levelname, colored_level)


# Global loggers
_loggers: Dict[str, Logger] = {}


def get_logger(
    name: str,
    log_level: Optional[Union[str, LogLevel]] = None,
    log_file: Optional[Union[str, Path]] = None,
    channel: LogChannel = LogChannel.BOTH,
    structured: bool = False,
    color: bool = True
) -> Logger:
    """
    Get or create a logger with the specified configuration.
    
    Args:
        name: Logger name
        log_level: Minimum log level
        log_file: Path to log file
        channel: Output channel
        structured: Use JSON structured logging
        color: Use colored output
        
    Returns:
        Logger instance
    """
    key = f"{name}_{log_level}_{log_file}_{channel.value}_{structured}_{color}"
    
    if key not in _loggers:
        _loggers[key] = Logger(
            name=name,
            log_level=log_level,
            log_file=log_file,
            channel=channel,
            structured=structured,
            color=color
        )
    
    return _loggers[key]


def setup_logging(
    log_level: Optional[str] = None,
    log_dir: Optional[Union[str, Path]] = None,
    structured: bool = False,
    color: bool = True
) -> Dict[str, Logger]:
    """
    Set up logging for all system components.
    
    Args:
        log_level: Default log level
        log_dir: Directory for log files
        structured: Use JSON structured logging
        color: Use colored output
        
    Returns:
        Dictionary of configured loggers
    """
    if log_dir is None:
        config = get_config()
        log_dir = Path(__file__).parent.parent.parent.parent / "logs"
    else:
        log_dir = Path(log_dir)
    
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Create loggers for different components
    loggers = {
        "execution": get_logger(
            name="execution",
            log_level=log_level,
            log_file=log_dir / "execution.log",
            channel=LogChannel.BOTH,
            structured=structured,
            color=color
        ),
        "risk": get_logger(
            name="risk",
            log_level=log_level,
            log_file=log_dir / "risk.log",
            channel=LogChannel.BOTH,
            structured=structured,
            color=color
        ),
        "strategy": get_logger(
            name="strategy",
            log_level=log_level,
            log_file=log_dir / "strategy.log",
            channel=LogChannel.BOTH,
            structured=structured,
            color=color
        ),
        "market_data": get_logger(
            name="market_data",
            log_level=log_level,
            log_file=log_dir / "market_data.log",
            channel=LogChannel.BOTH,
            structured=structured,
            color=color
        ),
        "broker": get_logger(
            name="broker",
            log_level=log_level,
            log_file=log_dir / "broker.log",
            channel=LogChannel.BOTH,
            structured=structured,
            color=color
        ),
        "system": get_logger(
            name="system",
            log_level=log_level,
            log_file=log_dir / "system.log",
            channel=LogChannel.BOTH,
            structured=structured,
            color=color
        ),
    }
    
    return loggers


def reset_logging() -> None:
    """Reset all loggers."""
    global _loggers
    _loggers.clear()
    
    # Clear logging handlers
    for logger_name in list(logging.Logger.manager.loggerDict.keys()):
        logger = logging.getLogger(logger_name)
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
