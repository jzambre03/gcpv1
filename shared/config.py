"""Configuration management for the Golden Config AI system."""

import os
import tempfile
import logging
from typing import Optional
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Configuration file patterns for sparse checkout
CONFIG_FILE_PATTERNS = [
    "*.yml", "*.yaml", "*.properties", "*.toml", "*.ini",
    "*.cfg", "*.conf", "*.config",
    "Dockerfile", "docker-compose.yml",
    "pom.xml", "build.gradle", "requirements.txt"
]

# Project root and temp directory configuration
PROJECT_ROOT = Path(__file__).parent.parent
PROJECT_TEMP_DIR = PROJECT_ROOT / "temp"


def get_temp_base_dir() -> Path:
    """
    Get the base temporary directory for all operations.
    
    This function provides intelligent temp directory selection with 3-tier priority:
    1. GCP_TEMP_DIR environment variable (if set by user)
    2. Project temp directory (./temp in project root) - DEFAULT
    3. System temp directory (fallback if project dir not writable)
    
    This ensures temp files are created in the same filesystem as the application,
    which is critical for EC2 instances where /tmp might have limited space.
    
    Returns:
        Path object pointing to the temp base directory
    
    Examples:
        >>> # On EC2: /app/saja9l7/gcpv1/temp/
        >>> # On Local: /Users/user/project/temp/
        >>> temp_dir = get_temp_base_dir()
    """
    # Priority 1: Check environment variable
    env_temp = os.getenv('GCP_TEMP_DIR')
    if env_temp:
        temp_base = Path(env_temp)
        logger.info(f"Using temp directory from GCP_TEMP_DIR: {temp_base}")
        temp_base.mkdir(parents=True, exist_ok=True)
        return temp_base
    
    # Priority 2: Use project temp directory
    try:
        PROJECT_TEMP_DIR.mkdir(parents=True, exist_ok=True)
        # Test if we can write to it
        test_file = PROJECT_TEMP_DIR / ".write_test"
        test_file.touch()
        test_file.unlink()
        logger.debug(f"Using project temp directory: {PROJECT_TEMP_DIR}")
        return PROJECT_TEMP_DIR
    except (PermissionError, OSError) as e:
        logger.warning(f"Cannot use project temp directory: {e}")
    
    # Priority 3: Fallback to system temp directory
    system_temp = Path(tempfile.gettempdir())
    logger.info(f"Using system temp directory (fallback): {system_temp}")
    return system_temp


@dataclass
class Config:
    """Central configuration for all agents and components."""
    
    # AWS Configuration
    aws_region: str = os.getenv("AWS_REGION", "us-east-1")
    aws_access_key_id: Optional[str] = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = os.getenv("AWS_SECRET_ACCESS_KEY")
    
    # Bedrock Configuration (Exclusive LLM Access via Strands SDK)
    bedrock_model_id: str = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")
    bedrock_worker_model_id: str = os.getenv("BEDROCK_WORKER_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
    bedrock_guardrails_id: Optional[str] = os.getenv("BEDROCK_GUARDRAILS_ID")
    bedrock_guardrails_version: str = os.getenv("BEDROCK_GUARDRAILS_VERSION", "DRAFT")
    
    # Agent Configuration
    supervisor_agent_id: str = os.getenv("SUPERVISOR_AGENT_ID", "supervisor-agent")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    agent_runtime_mode: str = os.getenv("AGENT_RUNTIME_MODE", "development")
    
    # Redis Configuration
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_db: int = int(os.getenv("REDIS_DB", "0"))
    redis_password: Optional[str] = os.getenv("REDIS_PASSWORD")
    
    # SQS Configuration
    request_queue_url: Optional[str] = os.getenv("REQUEST_QUEUE_URL")
    response_queue_url: Optional[str] = os.getenv("RESPONSE_QUEUE_URL")
    status_queue_url: Optional[str] = os.getenv("STATUS_QUEUE_URL")
    
    # Repository Configuration
    gitlab_token: Optional[str] = os.getenv("GITLAB_TOKEN")
    github_token: Optional[str] = os.getenv("GITHUB_TOKEN")
    
    # Golden Config Storage
    golden_config_bucket: Optional[str] = os.getenv("GOLDEN_CONFIG_BUCKET")
    golden_config_prefix: str = os.getenv("GOLDEN_CONFIG_PREFIX", "golden-configs/")
    
    # Notification Configuration
    slack_webhook_url: Optional[str] = os.getenv("SLACK_WEBHOOK_URL")
    teams_webhook_url: Optional[str] = os.getenv("TEAMS_WEBHOOK_URL")
    
    # Security Configuration
    secret_detection_enabled: bool = os.getenv("SECRET_DETECTION_ENABLED", "true").lower() == "true"
    compliance_scanning_enabled: bool = os.getenv("COMPLIANCE_SCANNING_ENABLED", "true").lower() == "true"
    
    # Learning AI Configuration
    learning_ai_enabled: bool = os.getenv("LEARNING_AI_ENABLED", "true").lower() == "true"
    auto_approval_threshold: float = float(os.getenv("AUTO_APPROVAL_THRESHOLD", "0.9"))
    learning_model_bucket: Optional[str] = os.getenv("LEARNING_MODEL_BUCKET")
    
    def validate(self) -> None:
        """Validate configuration and raise errors for missing required values."""
        required_fields = [
            ("aws_region", self.aws_region),
            ("bedrock_model_id", self.bedrock_model_id),
        ]
        
        missing = [field for field, value in required_fields if not value]
        if missing:
            raise ValueError(f"Missing required configuration fields: {missing}")
    
    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.agent_runtime_mode.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.agent_runtime_mode.lower() == "development"
