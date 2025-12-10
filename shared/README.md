# Shared Utilities

This directory contains shared utilities, models, and configuration used across all agents in the multi-agent system.

---

## 📁 Contents

```
shared/
├── __init__.py
├── agent_communication.py    # Inter-agent messaging bus
├── config.py                 # Configuration management
├── logging_config.py         # Logging setup
├── models.py                 # Pydantic data models
└── README.md                 # This file
```

---

## 🔧 Core Modules

### 1. `config.py` - Configuration Management

Centralizes all configuration settings using Pydantic for validation.

**Usage:**
```python
from shared.config import Config

config = Config()

print(config.aws_region)           # us-east-1
print(config.bedrock_model_id)     # Claude model ID
print(config.gitlab_url)           # https://gitlab.com
```

**Configuration Sources:**
1. Environment variables (`.env` file)
2. Default values (fallback)

**Key Settings:**

**AWS:**
- `aws_region` - AWS region for Bedrock
- `aws_access_key_id` - AWS access key
- `aws_secret_access_key` - AWS secret key
- `bedrock_model_id` - Supervisor model (Claude 3.5 Sonnet)
- `bedrock_worker_model_id` - Worker model (Claude 3 Haiku)

**GitLab:**
- `gitlab_url` - GitLab instance URL
- `gitlab_private_token` - Access token for private repos
- `git_user_name` - Git username
- `git_user_email` - Git email

**Repository:**
- `default_repo_url` - Default repository for validation
- `default_golden_branch` - Default golden branch (gold)
- `default_drift_branch` - Default drift branch (drift)

**Logging:**
- `log_level` - Logging verbosity (DEBUG, INFO, WARNING, ERROR)
- `agent_runtime_mode` - Runtime mode (development, production)

---

### 2. `models.py` - Data Models

Pydantic models for type-safe data handling across agents.

**Key Models:**

#### `TaskRequest`
Request structure for agent tasks.

```python
from shared.models import TaskRequest

task = TaskRequest(
    task_id="unique_task_id",
    task_type="collect_diffs",  # or "analyze_drift"
    parameters={
        "repo_url": "https://gitlab.verizon.com/saja9l7/golden_config.git",
        "golden_branch": "gold",
        "drift_branch": "drift"
    },
    timeout_seconds=300
)
```

**Fields:**
- `task_id` (str) - Unique identifier
- `task_type` (str) - Type of task to perform
- `parameters` (Dict) - Task-specific parameters
- `timeout_seconds` (int) - Maximum execution time
- `metadata` (Dict, optional) - Additional context

#### `TaskResponse`
Response structure from agent tasks.

```python
from shared.models import TaskResponse

response = TaskResponse(
    task_id="unique_task_id",
    status="success",  # or "failed", "timeout"
    result={
        "drift_analysis_file": "path/to/file.json",
        "summary": {
            "files_with_drift": 3,
            "total_files": 10
        }
    },
    error=None,
    processing_time_seconds=45.2,
    metadata={
        "agent": "config_collector"
    }
)
```

**Fields:**
- `task_id` (str) - Matches request ID
- `status` (str) - Execution status
- `result` (Dict) - Task output data
- `error` (str, optional) - Error message if failed
- `processing_time_seconds` (float, optional) - Execution time
- `metadata` (Dict, optional) - Additional response info

#### `AgentMessage`
Inter-agent communication message.

```python
from shared.models import AgentMessage

message = AgentMessage(
    from_agent="config_collector",
    to_agent="diff_policy_engine",
    message_type="drift_analysis_complete",
    payload={
        "drift_analysis_file": "path/to/drift_analysis.json",
        "files_with_drift": 3
    },
    correlation_id="run_20251004_165130"
)
```

**Fields:**
- `from_agent` (str) - Sender agent
- `to_agent` (str) - Recipient agent
- `message_type` (str) - Message category
- `payload` (Dict) - Message content
- `correlation_id` (str, optional) - Request tracking ID
- `timestamp` (datetime) - When sent

---

### 3. `agent_communication.py` - Communication Bus

Facilitates inter-agent messaging with topic-based pub/sub.

**Usage:**

**Initialize Bus:**
```python
from shared.agent_communication import AgentCommunicationBus

bus = AgentCommunicationBus()
```

**Subscribe to Topic:**
```python
def handle_drift_complete(message: AgentMessage):
    print(f"Received: {message.message_type}")
    print(f"File: {message.payload['drift_analysis_file']}")

bus.subscribe("drift_analysis_complete", handle_drift_complete)
```

**Publish Message:**
```python
bus.publish(
    topic="drift_analysis_complete",
    from_agent="config_collector",
    to_agent="diff_policy_engine",
    payload={
        "drift_analysis_file": "path/to/file.json",
        "files_with_drift": 3
    }
)
```

**Get Agent Messages:**
```python
messages = bus.get_messages_for_agent("diff_policy_engine")
for message in messages:
    print(f"From: {message.from_agent}")
    print(f"Type: {message.message_type}")
```

**Clear Messages:**
```python
bus.clear_messages()
```

**Features:**
- ✅ Topic-based routing
- ✅ Agent-specific message queues
- ✅ Correlation ID tracking
- ✅ Timestamp tracking
- ✅ Message persistence

---

### 4. `logging_config.py` - Logging Setup

Configures colored logging with custom formatting.

**Features:**
- ✅ **Colored output** - Different colors for log levels
- ✅ **Structured format** - Level | Logger | Message
- ✅ **Configurable verbosity** - Set via `LOG_LEVEL` env var
- ✅ **Agent-specific loggers** - Separate logger per agent

**Usage:**

**Setup Logging:**
```python
from shared.logging_config import setup_logging

setup_logging()  # Uses LOG_LEVEL from .env
```

**Get Logger:**
```python
import logging

logger = logging.getLogger(__name__)

logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
logger.critical("Critical message")
```

**Custom Log Level:**
```python
setup_logging(log_level="DEBUG")
```

**Log Levels:**
- **DEBUG** - Detailed diagnostic info
- **INFO** - General informational messages
- **WARNING** - Warning messages
- **ERROR** - Error messages
- **CRITICAL** - Critical failures

**Output Format:**
```
INFO | config_collector | Cloning repository...
DEBUG | diff_engine | Analyzing file: config/app.yml
WARNING | supervisor | High risk detected
ERROR | config_collector | Git clone failed: authentication error
```

---

## 🎯 Common Patterns

### Agent Initialization

```python
from shared.config import Config
from shared.logging_config import setup_logging
import logging

# Setup
setup_logging()
logger = logging.getLogger(__name__)
config = Config()

# Use in agent
logger.info(f"Initializing agent with model: {config.bedrock_worker_model_id}")
```

### Task Processing

```python
from shared.models import TaskRequest, TaskResponse

def process_task(self, task: TaskRequest) -> TaskResponse:
    try:
        # Process task
        result = self.do_work(task.parameters)
        
        return TaskResponse(
            task_id=task.task_id,
            status="success",
            result=result
        )
    except Exception as e:
        return TaskResponse(
            task_id=task.task_id,
            status="failed",
            result={},
            error=str(e)
        )
```

### Inter-Agent Communication

```python
from shared.agent_communication import AgentCommunicationBus
from shared.models import AgentMessage

# Sender agent
bus = AgentCommunicationBus()
bus.publish(
    topic="analysis_complete",
    from_agent="config_collector",
    to_agent="diff_policy_engine",
    payload={"file": "path/to/output.json"}
)

# Receiver agent
messages = bus.get_messages_for_agent("diff_policy_engine")
for message in messages:
    process_message(message)
```

---

## 🔧 Configuration via .env

Create `.env` file in project root:

```bash
# AWS Configuration
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
BEDROCK_WORKER_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0

# GitLab Configuration
GITLAB_URL=https://gitlab.verizon.com
GITLAB_PRIVATE_TOKEN=your_token

# Git User
GIT_USER_NAME=Your Name
GIT_USER_EMAIL=your@email.com

# Repository Defaults
DEFAULT_REPO_URL=https://gitlab.verizon.com/saja9l7/golden_config.git
DEFAULT_GOLDEN_BRANCH=gold
DEFAULT_DRIFT_BRANCH=drift

# Logging
LOG_LEVEL=INFO
AGENT_RUNTIME_MODE=development
```

---

## 🐛 Troubleshooting

### "Config validation error"
**Check:**
1. `.env` file exists in project root
2. Required variables are set
3. Variable names match exactly
4. No extra spaces in values

### "Logger not colored"
**Check:**
1. Terminal supports ANSI colors
2. `colorlog` package installed
3. Logging setup called before use

### "Agent messages not delivered"
**Check:**
1. Communication bus initialized
2. Topic names match exactly
3. Agent names are correct
4. Subscriber registered before publish

---

## 📚 Related

- **Agents:** `../Agents/`
- **API:** `../api/`
- **Main README:** `../README.md`

---

## 🔗 Dependencies

- **pydantic** - Data validation
- **python-dotenv** - Environment variable loading
- **colorlog** - Colored logging output
- **typing** - Type hints

---

**The foundation of your multi-agent system!** 🏗️

