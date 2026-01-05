"""Logging configuration for the Golden Config AI system."""

import logging
import os
import sys
from typing import Dict, Any, Optional
from pathlib import Path


def setup_logging(log_level: Optional[str] = None) -> None:
    """Setup centralized logging configuration for all agents."""
    
    if log_level is None:
        log_level = os.getenv("LOG_LEVEL", "INFO")
    
    # Create custom formatter
    class ColoredFormatter(logging.Formatter):
        """Custom formatter with colors for different log levels."""
        
        COLORS = {
            'DEBUG': '\033[36m',    # Cyan
            'INFO': '\033[32m',     # Green
            'WARNING': '\033[33m',  # Yellow
            'ERROR': '\033[31m',    # Red
            'CRITICAL': '\033[35m', # Magenta
        }
        RESET = '\033[0m'
        
        def format(self, record):
            if sys.stdout.isatty():  # Only use colors for terminal output
                log_color = self.COLORS.get(record.levelname, '')
                record.levelname = f"{log_color}{record.levelname}{self.RESET}"
                record.name = f"\033[34m{record.name}{self.RESET}"  # Blue for logger name
            
            return super().format(record)
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Apply colored formatter
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setFormatter(ColoredFormatter(
                '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            ))
    
    # Configure specific loggers
    configure_agent_loggers()
    configure_external_loggers()


def configure_agent_loggers() -> None:
    """Configure logging for agent modules."""
    agent_loggers = [
        'agents.supervisor',
        'agents.workers.config_collector',
        'agents.workers.guardrails',
        'agents.workers.diff_policy_engine',
        'agents.workers.triage_routing',
        'agents.workers.learning_ai',
        'api.sqs_bridge',
        'shared',
        'tools',
    ]
    
    for logger_name in agent_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)


def configure_external_loggers() -> None:
    """Configure logging levels for external libraries."""
    external_loggers = {
        'boto3': logging.WARNING,
        'botocore': logging.WARNING,
        'urllib3': logging.WARNING,
        'git': logging.WARNING,
        'asyncio': logging.WARNING,
        'redis': logging.INFO,
        'strands': logging.INFO,
    }
    
    for logger_name, level in external_loggers.items():
        logging.getLogger(logger_name).setLevel(level)


def get_agent_logger(agent_name: str) -> logging.Logger:
    """Get a properly configured logger for an agent."""
    return logging.getLogger(f"agents.{agent_name}")


def get_tool_logger(tool_name: str) -> logging.Logger:
    """Get a properly configured logger for a tool."""
    return logging.getLogger(f"tools.{tool_name}")


class DatabaseLogHandler(logging.Handler):
    """
    Custom logging handler that saves logs to the database.
    
    This handler saves all log records to the database for persistent storage,
    querying, and analysis.
    """
    
    def __init__(self, log_type: str = 'system', **context):
        """
        Initialize the database log handler.
        
        Args:
            log_type: Type of logs (system, vsat_sync, analysis, git, etc.)
            **context: Additional context (run_id, service_name, environment, vsat)
        """
        super().__init__()
        self.log_type = log_type
        self.context = context
        
        # Import here to avoid circular imports
        from .db import save_log
        self.save_log = save_log
    
    def emit(self, record: logging.LogRecord):
        """
        Emit a log record to the database.
        
        Args:
            record: LogRecord to save
        """
        try:
            # Extract context from record if available
            run_id = getattr(record, 'run_id', self.context.get('run_id'))
            service_name = getattr(record, 'service_name', self.context.get('service_name'))
            environment = getattr(record, 'environment', self.context.get('environment'))
            vsat = getattr(record, 'vsat', self.context.get('vsat'))
            
            # Build metadata
            metadata = {
                'thread': record.thread,
                'thread_name': record.threadName,
                'process': record.process,
                'process_name': record.processName,
            }
            
            # Add exception info if present
            if record.exc_info:
                metadata['exception'] = self.format(record)
            
            # Save to database
            self.save_log(
                log_level=record.levelname,
                logger_name=record.name,
                message=record.getMessage(),
                module=record.module,
                function_name=record.funcName,
                line_number=record.lineno,
                log_type=self.log_type,
                run_id=run_id,
                service_name=service_name,
                environment=environment,
                vsat=vsat,
                metadata=metadata
            )
        except Exception as e:
            # Don't let logging failures break the application
            # Use handleError to report the error
            self.handleError(record)


def add_database_logging(
    log_type: str = 'system',
    log_level: int = logging.INFO,
    **context
) -> DatabaseLogHandler:
    """
    Add database logging handler to the root logger.
    
    Args:
        log_type: Type of logs (system, vsat_sync, analysis, git, etc.)
        log_level: Minimum log level to save to database
        **context: Additional context (run_id, service_name, environment, vsat)
        
    Returns:
        The database handler instance
    """
    handler = DatabaseLogHandler(log_type=log_type, **context)
    handler.setLevel(log_level)
    
    # Add to root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    
    return handler


def remove_database_logging(handler: DatabaseLogHandler):
    """
    Remove database logging handler from the root logger.
    
    Args:
        handler: The database handler to remove
    """
    root_logger = logging.getLogger()
    root_logger.removeHandler(handler)
