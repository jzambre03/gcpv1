"""Logging configuration for the Golden Config AI system."""

import logging
import os
import sys
from typing import Dict, Any, Optional


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
