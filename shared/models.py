"""Shared data models for the Golden Config AI system."""

from datetime import datetime
from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field
from enum import Enum


class ValidationStatus(str, Enum):
    """Status of a configuration validation request."""
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ValidationResult(str, Enum):
    """Result of a configuration validation."""
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    UNKNOWN = "unknown"


class SeverityLevel(str, Enum):
    """Severity levels for issues and notifications."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Request/Response Models
class ConfigValidationRequest(BaseModel):
    """Request model for configuration validation."""
    request_id: str = Field(..., description="Unique identifier for the request")
    repo_url: str = Field(..., description="Repository URL to validate")
    branch: str = Field(..., description="Branch name to validate")
    target_folder: Optional[str] = Field(None, description="Specific folder to scan")
    file_patterns: List[str] = Field(default_factory=lambda: ["*.yml", "*.yaml", "*.json"], 
                                   description="File patterns to include")
    callback_url: Optional[str] = Field(None, description="Webhook URL for result notification")
    requester: Optional[str] = Field(None, description="Who initiated the request")
    ci_cd_context: Optional[Dict[str, Any]] = Field(None, description="CI/CD pipeline context")


class ConfigValidationResponse(BaseModel):
    """Response model for configuration validation."""
    validation_id: str = Field(..., description="Unique validation identifier")
    status: ValidationStatus = Field(..., description="Current validation status")
    result: Optional[ValidationResult] = Field(None, description="Validation result")
    summary: Optional[str] = Field(None, description="Human-readable summary")
    details: Optional[Dict[str, Any]] = Field(None, description="Detailed validation results")
    errors: List[str] = Field(default_factory=list, description="Any errors encountered")
    warnings: List[str] = Field(default_factory=list, description="Any warnings")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")
    processing_time_seconds: Optional[float] = Field(None, description="Total processing time")


# Agent Communication Models
class AgentMessage(BaseModel):
    """Base model for inter-agent communication."""
    message_id: str = Field(..., description="Unique message identifier")
    from_agent: str = Field(..., description="Sending agent identifier")
    to_agent: str = Field(..., description="Target agent identifier")
    message_type: str = Field(..., description="Type of message")
    payload: Dict[str, Any] = Field(..., description="Message payload")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Message timestamp")
    correlation_id: Optional[str] = Field(None, description="Request correlation ID")


class TaskRequest(BaseModel):
    """Request model for agent tasks."""
    task_id: str = Field(..., description="Unique task identifier")
    task_type: str = Field(..., description="Type of task to perform")
    parameters: Dict[str, Any] = Field(..., description="Task parameters")
    priority: int = Field(default=5, description="Task priority (1-10)")
    timeout_seconds: Optional[int] = Field(300, description="Task timeout")


class TaskResponse(BaseModel):
    """Response model for agent tasks."""
    task_id: str = Field(..., description="Task identifier")
    status: Literal["success", "failure", "partial"] = Field(..., description="Task status")
    result: Optional[Dict[str, Any]] = Field(None, description="Task result data")
    error: Optional[str] = Field(None, description="Error message if failed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    processing_time_seconds: float = Field(..., description="Task processing time")


# Domain-Specific Models
class ConfigFile(BaseModel):
    """Model for configuration file information."""
    path: str = Field(..., description="File path in repository")
    content: str = Field(..., description="File content")
    size_bytes: int = Field(..., description="File size in bytes")
    last_modified: Optional[datetime] = Field(None, description="Last modification time")
    file_type: str = Field(..., description="File type/extension")
    encoding: str = Field(default="utf-8", description="File encoding")


class SecurityIssue(BaseModel):
    """Model for security issues found during scanning."""
    issue_id: str = Field(..., description="Unique issue identifier")
    severity: SeverityLevel = Field(..., description="Issue severity")
    issue_type: str = Field(..., description="Type of security issue")
    file_path: str = Field(..., description="File where issue was found")
    line_number: Optional[int] = Field(None, description="Line number of issue")
    description: str = Field(..., description="Issue description")
    recommendation: Optional[str] = Field(None, description="Recommended fix")
    confidence: float = Field(..., description="Confidence score (0-1)")


class ConfigDrift(BaseModel):
    """Model for configuration drift detection."""
    file_path: str = Field(..., description="Path of the drifted file")
    drift_type: Literal["added", "removed", "modified"] = Field(..., description="Type of drift")
    golden_content: Optional[str] = Field(None, description="Golden configuration content")
    current_content: Optional[str] = Field(None, description="Current configuration content")
    diff_summary: str = Field(..., description="Human-readable diff summary")
    impact_level: SeverityLevel = Field(..., description="Impact level of the drift")
    policy_violations: List[str] = Field(default_factory=list, description="Policy violations")


class TeamAssignment(BaseModel):
    """Model for team routing and assignment."""
    team_name: str = Field(..., description="Name of the responsible team")
    team_contact: str = Field(..., description="Team contact information")
    escalation_level: int = Field(default=1, description="Escalation level")
    notification_channels: List[str] = Field(default_factory=list, description="Notification channels")
    estimated_response_time: Optional[str] = Field(None, description="Expected response time")


class LearningRecommendation(BaseModel):
    """Model for AI learning recommendations."""
    recommendation_id: str = Field(..., description="Unique recommendation identifier")
    recommendation_type: Literal["auto_approve", "policy_update", "team_routing"] = Field(
        ..., description="Type of recommendation"
    )
    confidence_score: float = Field(..., description="Confidence score (0-1)")
    reasoning: str = Field(..., description="AI reasoning for the recommendation")
    historical_context: Dict[str, Any] = Field(default_factory=dict, description="Historical context")
    suggested_action: str = Field(..., description="Suggested action to take")
