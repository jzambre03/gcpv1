"""
Config Collector Agent - Extract Config Files & Create Snapshots

This agent ONLY:
1. Extracts configuration files from GitLab repositories
2. Creates snapshot branches (golden and drift)
3. Performs basic Git operations

NO diff detection - that's done by Drift Detector Agent.
"""

from datetime import datetime
import asyncio
import logging
import os
import sys
import json
import tempfile
import shutil
import time
from typing import Any, Dict, List, Optional
from pathlib import Path

import git
from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.tools import tool
from dotenv import load_dotenv
from shared.models import TaskResponse, TaskRequest
from shared.config import Config

# Import Git operations from shared
from shared.git_operations import (
    setup_git_auth,
    generate_unique_branch_name,
    create_config_only_branch,
    create_env_specific_config_branch
)

# Import golden branch tracker
from shared.golden_branch_tracker import (
    get_active_golden_branch,
    add_golden_branch,
    add_drift_branch
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def configure_git_user():
    """Configures Git user settings from environment variables."""
    git_user_name = os.getenv('GIT_USER_NAME')
    git_user_email = os.getenv('GIT_USER_EMAIL')
    
    if git_user_name and git_user_email:
        try:
            os.system(f'git config --global user.name "{git_user_name}"')
            os.system(f'git config --global user.email "{git_user_email}"')
            logger.info(f"✅ Git user configured as: {git_user_name} <{git_user_email}>")
        except Exception as e:
            logger.warning(f"Could not configure git user: {e}")


def ensure_repo_ready(repo_url: str, repo_path: Path) -> Optional[git.Repo]:
    """Clone or fetch repository in temporary location."""
    try:
        if repo_path.exists():
            logger.info(f"Repository already exists at: {repo_path}")
            repo = git.Repo(repo_path)
            logger.info("Fetching latest updates from remote...")
            repo.remotes.origin.fetch()
            return repo
        else:
            logger.info(f"Cloning repository into temporary location: {repo_path}")
            repo_path.parent.mkdir(parents=True, exist_ok=True)
            authenticated_url = setup_git_auth(repo_url, os.getenv('GITLAB_TOKEN'))
            repo = git.Repo.clone_from(authenticated_url, repo_path)
            logger.info("Fetching origin after clone...")
            repo.remotes.origin.fetch()
            logger.info("✅ Repository is ready.")
            return repo
    except Exception as e:
        logger.error(f"Failed to clone or access repository: {e}")
        return None


def switch_to_branch(repo: git.Repo, branch_name: str) -> Optional[str]:
    """Switch branches."""
    try:
        original_branch = repo.active_branch.name
        logger.info(f"Current branch is '{original_branch}'.")
        if original_branch != branch_name:
            logger.info(f"Attempting to switch to branch '{branch_name}'...")
            repo.git.checkout(branch_name)
            logger.info(f"✅ Switched to branch '{branch_name}'.")
        else:
            logger.info(f"Already on branch '{branch_name}'. No switch needed.")
        return original_branch
    except git.exc.GitCommandError as e:
        logger.error(f"Could not checkout branch '{branch_name}': {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error switching branch: {e}")
        return None


def is_config_file(file_path: str) -> bool:
    """Check if file is a configuration file."""
    config_extensions = {
        '.yml', '.yaml', '.json', '.env', '.ini', '.cfg', '.conf',
        '.toml', '.xml', '.properties', '.config'
    }
    config_filenames = {
        'dockerfile', 'docker-compose', 'makefile', 'requirements.txt',
        'package.json', 'package-lock.json', 'poetry.lock', 'pipfile',
        'setup.py', 'setup.cfg', 'pyproject.toml', '.gitignore',
        '.dockerignore', 'webpack.config.js', 'babel.config.js',
        'pom.xml', 'build.gradle', 'build.gradle.kts',
        'settings.gradle', 'settings.gradle.kts', 'go.mod'
    }
    file_name = Path(file_path).name.lower()
    file_suffix = Path(file_path).suffix.lower()
    return (
        file_suffix in config_extensions or
        file_name in config_filenames or
        (not file_suffix and file_name in {'dockerfile', 'makefile', 'jenkinsfile'})
    )


def get_config_file_paths(repo: git.Repo, target_folder: str = None) -> List[str]:
    """Get list of configuration files in the repository."""
    config_extensions = {
        '.yml', '.yaml', '.json', '.env', '.ini', '.cfg', '.conf',
        '.toml', '.xml', '.properties', '.config'
    }
    
    config_filenames = {
        'dockerfile', 'docker-compose', 'makefile', 'requirements.txt',
        'package.json', 'package-lock.json', 'poetry.lock', 'pipfile',
        'setup.py', 'setup.cfg', 'pyproject.toml', '.gitignore',
        '.dockerignore', 'webpack.config.js', 'babel.config.js',
        'pom.xml', 'build.gradle', 'build.gradle.kts',
        'settings.gradle', 'settings.gradle.kts', 'go.mod'
    }
    
    relative_paths = []

    try:
        repo_root = Path(repo.working_tree_dir)
        search_root = repo_root / target_folder if target_folder else repo_root
        
        if not search_root.exists():
            logger.warning(f"Target folder '{target_folder}' does not exist in the repository.")
            return []
        
        logger.info(f"🔍 Searching for configuration files in: {search_root}")
        logger.info(f"📁 Repository root: {repo_root}")
        
        # Walk through the directory tree
        for file_path in search_root.rglob("*"):
            if file_path.is_file():
                # Get relative path from repository root
                relative_path = file_path.relative_to(repo_root)
                relative_path_str = str(relative_path).replace("\\", "/")
                
                # Check if it's a config file by extension
                if file_path.suffix.lower() in config_extensions:
                    relative_paths.append(relative_path_str)
                # Check if it's a config file by name
                elif file_path.name.lower() in config_filenames:
                    relative_paths.append(relative_path_str)
                # Special case for files without extensions
                elif not file_path.suffix and file_path.name.lower() in {'dockerfile', 'makefile', 'jenkinsfile'}:
                    relative_paths.append(relative_path_str)
        
        logger.info(f"✅ Found {len(relative_paths)} configuration files")
    except Exception as e:
        logger.error(f"Error scanning repository: {e}")
        return []
    
    return sorted(relative_paths)


class ConfigCollectorAgent(Agent):
    """
    Config Collector Agent - Extract Config Files & Create Snapshots
    
    Responsibilities:
    1. Extract configuration files from GitLab repositories
    2. Create snapshot branches (golden and drift)
    3. Perform basic Git operations (clone, checkout, branch creation)
    
    NO diff detection - that's handled by Drift Detector Agent.
    """

    def __init__(self, config: Optional[Config] = None):
        if config is None:
            config = Config()
        
        system_prompt = self._get_config_collector_prompt()
        
        super().__init__(
            model=BedrockModel(model_id=config.bedrock_worker_model_id),
            system_prompt=system_prompt,
            tools=[
                self.setup_repository_access,
                self.clone_repository,
                self.extract_config_files,
                self.create_golden_snapshot,
                self.create_drift_snapshot,
                self.prepare_repository_snapshots,
                self.certify_drift_as_golden
            ]
        )
        self.config = config
    
    def _get_config_collector_prompt(self) -> str:
        return """You are the Config Collector Agent in the Golden Config AI system.

**Your Role:**
Extract configuration files from GitLab repositories and create snapshot branches for drift analysis.

**Your Responsibilities:**
1. Extract configuration files from GitLab repositories
2. Manage snapshot branches:
   - Golden branch: Use existing certified baseline (from database)
   - Drift branch: Always create new snapshot of current state
3. Perform basic Git operations (clone, checkout, branch management)
4. Handle errors gracefully with intelligent fallbacks
5. Certify drift branches as golden when configurations are approved

**Standard Workflow (99% of cases):**
For normal cases, use the `prepare_repository_snapshots` convenience tool which handles:
- Get existing golden branch from database (or create if none exists)
- Create new drift snapshot branch from main branch
- Clone both branches to temporary locations
- Extract all configuration files
- Return paths and file lists

**Golden Branch Logic:**
- Golden branch = Certified baseline configuration (immutable)
- Check database first for existing golden branch for the environment
- Use existing golden branch if found (don't create new one)
- Only create new golden branch if none exists
- Golden branches are updated via certification process (not on every run)

**Drift Branch Logic:**
- Drift branch = Current state snapshot (created every time)
- Always create a new drift branch from main branch
- Each drift branch represents a point-in-time snapshot
- Used to compare against golden branch to detect drift

**Tool Choice:**
- **Convenience Tool**: Use `prepare_repository_snapshots` for standard cases (fast, predictable)
- **Individual Tools**: Use individual tools (`create_golden_snapshot`, `create_drift_snapshot`, etc.) for:
  - Custom workflows
  - Error recovery
  - Step-by-step debugging
  - Partial operations

**Edge Case Handling (1% of cases):**
If the convenience tool fails, use individual tools with your judgment:
- Target folder not found? → Use `extract_config_files` with parent directory or empty target_folder
- Branch doesn't exist? → Use `create_golden_snapshot` with 'main' or 'master' as fallback
- No configs found? → Try `extract_config_files` with broader search
- Authentication issues? → Use `setup_repository_access` first, then retry

**Available Tools:**
- `prepare_repository_snapshots`: Convenience tool for complete workflow (use for standard cases)
  - Gets existing golden branch OR creates new one if none exists
  - Always creates new drift branch
  - Clones both and extracts config files
- `create_golden_snapshot`: Create golden branch only (use for custom workflows)
- `create_drift_snapshot`: Create drift branch only (use for custom workflows)
- `clone_repository`: Clone a specific branch (use for custom workflows)
- `extract_config_files`: List config files in a repo (use for custom workflows)
- `setup_repository_access`: Setup Git authentication (use if auth issues)
- `certify_drift_as_golden`: Promote a drift branch to golden (use when configs are approved)

**Configuration File Types You Should Find:**
- YAML: .yml, .yaml
- JSON: .json
- Properties: .properties, .ini, .cfg, .conf, .config
- TOML: .toml
- XML: .xml
- Build: pom.xml, build.gradle, requirements.txt, package.json
- Container: Dockerfile, docker-compose.yml
- CI/CD: Jenkinsfile, Makefile

**Important:**
- You do NOT perform diff detection - that's handled by Drift Detector Agent
- Your job is to PREPARE the data, not analyze it
- Always return structured data in the expected format
- Log clear messages about what you're doing

**Output Format:**
Always structure your response as:
```json
{
  "repository_snapshots": {
    "golden_branch": "golden_prod_20251201_...",
    "drift_branch": "drift_prod_20251201_...",
    "golden_path": "/tmp/...",
    "drift_path": "/tmp/..."
  },
  "config_files": ["file1.yml", "file2.json", ...],
  "summary": {
    "total_config_files": 15,
    "environment": "prod",
    "service_id": "gcp"
  }
}
```

Be efficient, reliable, and handle edge cases intelligently.
"""

    def process_task(self, task: TaskRequest) -> TaskResponse:
        """
        Process a config collection task.
        
        HYBRID APPROACH: LLM receives task and decides how to execute.
        For 99% of cases, LLM follows standard workflow.
        For edge cases, LLM can adapt and make intelligent decisions.
        
        Args:
            task: TaskRequest with parameters:
                - repo_url: Repository URL
                - main_branch: Main branch name (source of current configs)
                - environment: Environment name (prod, dev, qa, staging)
                - service_id: Service identifier
                - target_folder: Optional subfolder to analyze
                
        Returns:
            TaskResponse with repository snapshots and config file lists
        """
        start_time = time.time()
        
        try:
            logger.info(f"📦 Config Collector processing task: {task.task_id}")
            
            params = task.parameters
            
            # Extract parameters
            repo_url = params.get('repo_url')
            main_branch = params.get('main_branch', 'main')
            environment = params.get('environment', 'prod')
            service_id = params.get('service_id', 'default')
            target_folder = params.get('target_folder', '')
            
            if not repo_url:
                return TaskResponse(
                    task_id=task.task_id,
                    status="failure",
                    result={},
                    error="Missing required parameter: repo_url",
                    processing_time_seconds=time.time() - start_time,
                    metadata={"agent": "config_collector"}
                )
            
            # Build task description for the LLM agent
            task_description = f"""
You need to collect configuration files and create repository snapshots.

**Task Parameters:**
- Repository URL: {repo_url}
- Main Branch: {main_branch}
- Environment: {environment}
- Service ID: {service_id}
- Target Folder: {target_folder if target_folder else "entire repository"}

**Standard Workflow (follow this for normal cases):**
Use the `prepare_repository_snapshots` convenience tool with the provided parameters.
This single tool call will handle everything:
1. Create golden and drift snapshot branches
2. Clone both branches to temporary locations
3. Extract configuration files from both branches
4. Return complete results

**If you encounter errors with the convenience tool:**
Switch to individual tools for more control:
- Target folder not found → Use `extract_config_files` with parent directory or empty target_folder
- Branch doesn't exist → Use `create_golden_snapshot`/`create_drift_snapshot` with 'main' or 'master' as fallback
- Authentication issues → Use `setup_repository_access` first, then retry
- No config files found → Use `extract_config_files` with broader search (empty target_folder)

**Expected Output:**
Return a JSON object with:
- repository_snapshots: {{golden_branch, drift_branch, golden_path, drift_path}}
- config_files: [list of config file paths]
- summary: {{total_config_files, environment, service_id}}

Execute the workflow now.
"""
            
            logger.info("🤖 Invoking LLM agent to execute task...")
            
            # Let the LLM agent handle the task
            # The agent will decide which tools to call and in what order
            # Strands Agent is callable directly: agent(instruction)
            agent_response = self(task_description)
            
            logger.info(f"✅ Agent completed execution")
            
            # DEBUG: Log response structure
            logger.info(f"🔍 DEBUG: Agent response type: {type(agent_response)}")
            if hasattr(agent_response, '__dict__'):
                logger.info(f"🔍 DEBUG: Agent response attributes: {list(agent_response.__dict__.keys())}")
            if hasattr(agent_response, 'tool_results'):
                logger.info(f"🔍 DEBUG: Tool results count: {len(agent_response.tool_results) if agent_response.tool_results else 0}")
                if agent_response.tool_results:
                    logger.info(f"🔍 DEBUG: Last tool result type: {type(agent_response.tool_results[-1])}")
                    logger.info(f"🔍 DEBUG: Last tool result: {str(agent_response.tool_results[-1])[:500]}")
            
            # Parse the agent's response
            # Strands Agent returns the final tool result or a response object
            result_data = self._parse_agent_response(agent_response)
            
            logger.info(f"🔍 DEBUG: Parsed result_data type: {type(result_data)}")
            logger.info(f"🔍 DEBUG: Parsed result_data keys: {list(result_data.keys()) if isinstance(result_data, dict) else 'not a dict'}")
            
            # FALLBACK: If parsing failed but we know the tool was called, check for cached tool results
            if not isinstance(result_data, dict) or not result_data:
                logger.warning("⚠️ Parser returned empty/invalid data, checking for cached tool results...")
                # Check if we have a _last_tool_result or similar attribute
                if hasattr(self, '_last_tool_result'):
                    logger.info("Found _last_tool_result attribute")
                    result_data = self._last_tool_result
                # Check agent_response for any dict-like data
                elif hasattr(agent_response, '__dict__'):
                    logger.info("Searching agent_response.__dict__ for data")
                    for attr_name, attr_value in agent_response.__dict__.items():
                        if isinstance(attr_value, dict) and ('golden_branch' in attr_value or 'repository_snapshots' in attr_value):
                            logger.info(f"Found data in attribute: {attr_name}")
                            result_data = attr_value
                            break
            
            # Validate we got the expected output
            # The tool should return data with repository_snapshots or the data directly
            if not isinstance(result_data, dict):
                logger.error(f"Invalid agent response format: {type(result_data)}")
                return TaskResponse(
                    task_id=task.task_id,
                    status="failure",
                    result={},
                    error=f"Agent did not return expected data format: {str(result_data)[:200]}",
                    processing_time_seconds=time.time() - start_time,
                    metadata={"agent": "config_collector"}
                )
            
            # Check if we have an error in the response
            if result_data.get('status') == 'error' or 'error' in result_data:
                error_msg = result_data.get('error', 'Unknown error from agent')
                logger.error(f"Agent returned error: {error_msg}")
                return TaskResponse(
                    task_id=task.task_id,
                    status="failure",
                    result={},
                    error=error_msg,
                    processing_time_seconds=time.time() - start_time,
                    metadata={"agent": "config_collector"}
                )
            
            # Extract results - handle both formats:
            # Format 1: Direct format from prepare_repository_snapshots
            # Format 2: Nested format with repository_snapshots key
            if 'repository_snapshots' in result_data:
                repo_snapshots = result_data['repository_snapshots']
                config_files = result_data.get('config_files', [])
                # Reformat to match expected structure
                result_data = {
                    "repository_snapshots": repo_snapshots,
                    "config_files": config_files,
                    "summary": result_data.get('summary', {
                        "total_config_files": len(config_files),
                        "environment": params.get('environment', 'prod'),
                        "service_id": params.get('service_id', 'default')
                    })
                }
            elif 'golden_branch' in result_data and 'drift_branch' in result_data:
                # Format from prepare_repository_snapshots tool (direct format)
                repo_snapshots = {
                    "golden_branch": result_data.get('golden_branch'),
                    "drift_branch": result_data.get('drift_branch'),
                    "golden_path": result_data.get('golden_path'),
                    "drift_path": result_data.get('drift_path')
                }
                config_files = result_data.get('config_files', [])
                result_data = {
                    "repository_snapshots": repo_snapshots,
                    "config_files": config_files,
                    "summary": {
                        "total_config_files": len(config_files),
                        "environment": params.get('environment', 'prod'),
                        "service_id": params.get('service_id', 'default')
                    }
                }
            else:
                logger.error(f"Missing required fields in agent response: {list(result_data.keys())}")
                return TaskResponse(
                    task_id=task.task_id,
                    status="failure",
                    result={},
                    error="Agent response missing required fields (golden_branch, drift_branch, or repository_snapshots)",
                    processing_time_seconds=time.time() - start_time,
                    metadata={"agent": "config_collector"}
                )
            
            # Extract for logging
            repo_snapshots = result_data.get('repository_snapshots', {})
            config_files = result_data.get('config_files', [])
            
            logger.info(f"✅ Config Collector completed")
            logger.info(f"   Golden branch: {repo_snapshots.get('golden_branch')}")
            logger.info(f"   Drift branch: {repo_snapshots.get('drift_branch')}")
            logger.info(f"   Config files found: {len(config_files)}")
            
            return TaskResponse(
                task_id=task.task_id,
                status="success",
                result=result_data,
                error=None,
                processing_time_seconds=time.time() - start_time,
                metadata={
                    "agent": "config_collector",
                    "golden_branch": repo_snapshots.get('golden_branch'),
                    "drift_branch": repo_snapshots.get('drift_branch')
                }
            )
            
        except Exception as e:
            logger.exception(f"❌ Config Collector task processing failed: {e}")
            return TaskResponse(
                task_id=task.task_id,
                status="failure",
                result={},
                error=str(e),
                processing_time_seconds=time.time() - start_time,
                metadata={"agent": "config_collector"}
            )
        
    def _parse_agent_response(self, agent_response) -> Dict[str, Any]:
        """
        Parse the agent's response to extract structured data.
        
        Strands Agent returns the result of the last tool call or a response object.
        This method extracts the structured data from various possible formats.
        
        Priority order:
        1. tool_results (most reliable - actual tool return values)
        2. Direct dict response
        3. JSON in content/messages
        4. JSON extracted from markdown code blocks
        5. JSON extracted from mixed text
        """
        try:
            # CASE 1: Response has tool_results attribute (HIGHEST PRIORITY)
            # This is the most reliable - it's the actual return value from the tool
            if hasattr(agent_response, 'tool_results') and agent_response.tool_results:
                logger.debug(f"Found tool_results with {len(agent_response.tool_results)} results")
                # Get the last tool result (should be prepare_repository_snapshots or other tool)
                last_result = agent_response.tool_results[-1]
                
                # Tool results can be wrapped in different formats
                if isinstance(last_result, dict):
                    logger.debug("Tool result is already a dict")
                    return last_result
                
                # Sometimes tool_results contain objects with 'result' or 'output' attributes
                if hasattr(last_result, 'result'):
                    if isinstance(last_result.result, dict):
                        logger.debug("Extracted dict from tool_result.result")
                        return last_result.result
                
                if hasattr(last_result, 'output'):
                    if isinstance(last_result.output, dict):
                        logger.debug("Extracted dict from tool_result.output")
                        return last_result.output
                    # Try parsing output as JSON string
                    if isinstance(last_result.output, str):
                        try:
                            parsed = json.loads(last_result.output)
                            if isinstance(parsed, dict):
                                logger.debug("Parsed JSON from tool_result.output string")
                                return parsed
                        except json.JSONDecodeError:
                            pass
            
            # CASE 2: Response is already a dict (tool returned dict directly)
            if isinstance(agent_response, dict):
                logger.debug("Agent response is already a dict")
                # Check if it's the expected format
                if 'repository_snapshots' in agent_response or 'status' in agent_response:
                    return agent_response
                # Might be wrapped, try to extract
                if 'result' in agent_response:
                    return agent_response['result']
                return agent_response
            
            # CASE 3: Response has content attribute (Strands response object)
            if hasattr(agent_response, 'content'):
                content = agent_response.content
                logger.debug(f"Found content attribute, type: {type(content)}")
                
                # Content is already structured
                if isinstance(content, dict):
                    logger.debug("Content is already a dict")
                    return content
                
                # Try to parse as JSON string
                if isinstance(content, str):
                    # First try direct JSON parse
                    try:
                        parsed = json.loads(content)
                        if isinstance(parsed, dict):
                            logger.debug("Parsed JSON from content string")
                            return parsed
                    except json.JSONDecodeError:
                        pass
                    
                    # Try to extract JSON from markdown code blocks
                    json_from_markdown = self._extract_json_from_markdown(content)
                    if json_from_markdown:
                        logger.debug("Extracted JSON from markdown code block in content")
                        return json_from_markdown
                    
                    # Try to extract JSON from mixed text
                    json_from_text = self._extract_json_from_text(content)
                    if json_from_text:
                        logger.debug("Extracted JSON from mixed text in content")
                        return json_from_text
            
            # CASE 4: Response has messages attribute (conversation history)
            if hasattr(agent_response, 'messages') and agent_response.messages:
                logger.debug(f"Found {len(agent_response.messages)} messages")
                # Get the last message which should contain tool result
                last_message = agent_response.messages[-1]
                if hasattr(last_message, 'content'):
                    if isinstance(last_message.content, dict):
                        logger.debug("Last message content is a dict")
                        return last_message.content
                    if isinstance(last_message.content, str):
                        # Try direct JSON parse
                        try:
                            parsed = json.loads(last_message.content)
                            logger.debug("Parsed JSON from last message content")
                            return parsed
                        except json.JSONDecodeError:
                            pass
                        
                        # Try to extract JSON from markdown
                        json_from_markdown = self._extract_json_from_markdown(last_message.content)
                        if json_from_markdown:
                            logger.debug("Extracted JSON from markdown in last message")
                            return json_from_markdown
                        
                        # Try to extract JSON from mixed text
                        json_from_text = self._extract_json_from_text(last_message.content)
                        if json_from_text:
                            logger.debug("Extracted JSON from mixed text in last message")
                            return json_from_text
            
            # CASE 5: Try to extract from string representation
            response_str = str(agent_response)
            logger.debug(f"Trying string representation parse, length: {len(response_str)}")
            
            # Direct JSON parse if it looks like JSON
            if response_str.strip().startswith('{'):
                try:
                    parsed = json.loads(response_str)
                    logger.debug("Parsed JSON from string representation")
                    return parsed
                except json.JSONDecodeError:
                    pass
            
            # Try extracting JSON from markdown or mixed text
            json_from_markdown = self._extract_json_from_markdown(response_str)
            if json_from_markdown:
                logger.debug("Extracted JSON from markdown in string representation")
                return json_from_markdown
            
            json_from_text = self._extract_json_from_text(response_str)
            if json_from_text:
                logger.debug("Extracted JSON from mixed text in string representation")
                return json_from_text
            
            # FAILED TO PARSE
            logger.warning(f"Could not parse agent response format: {type(agent_response)}")
            logger.warning(f"Response attributes: {dir(agent_response) if hasattr(agent_response, '__dict__') else 'N/A'}")
            logger.warning(f"Response preview: {str(agent_response)[:200]}")
            
            # Return error dict so caller knows parsing failed
            return {
                "error": "Failed to parse agent response",
                "raw_response_type": str(type(agent_response)),
                "raw_response": str(agent_response)[:500]  # Limit length
            }
            
        except Exception as e:
            logger.error(f"Error parsing agent response: {e}", exc_info=True)
            return {
                "error": f"Failed to parse response: {e}",
                "raw_response": str(agent_response)[:500] if agent_response else "None"
            }
    
    def _extract_json_from_markdown(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extract JSON from markdown code blocks like:
        ```json
        {"key": "value"}
        ```
        or just
        ```
        {"key": "value"}
        ```
        """
        import re
        
        # Pattern for markdown code blocks with optional language tag
        patterns = [
            r'```json\s*\n(.*?)\n```',  # ```json ... ```
            r'```\s*\n(\{.*?\})\s*\n```',  # ``` {...} ```
            r'```\s*\n(\[.*?\])\s*\n```',  # ``` [...] ```
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                try:
                    parsed = json.loads(match)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    continue
        
        return None
    
    def _extract_json_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extract JSON object from mixed text.
        Looks for the first valid JSON object in the text.
        """
        import re
        
        # Find all potential JSON objects (starting with { and ending with })
        # This is a simple heuristic - find balanced braces
        start_idx = text.find('{')
        if start_idx == -1:
            return None
        
        brace_count = 0
        in_string = False
        escape_next = False
        
        for i in range(start_idx, len(text)):
            char = text[i]
            
            if escape_next:
                escape_next = False
                continue
            
            if char == '\\':
                escape_next = True
                continue
            
            if char == '"':
                in_string = not in_string
                continue
            
            if in_string:
                continue
            
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                
                if brace_count == 0:
                    # Found a complete JSON object
                    potential_json = text[start_idx:i+1]
                    try:
                        parsed = json.loads(potential_json)
                        if isinstance(parsed, dict):
                            return parsed
                    except json.JSONDecodeError:
                        # Try to find another JSON object
                        start_idx = text.find('{', i+1)
                        if start_idx == -1:
                            return None
                        brace_count = 0
                        continue
        
        return None

    @tool
    async def setup_repository_access(self, repo_url: str) -> Dict[str, Any]:
        """
        Setup repository access with authentication.
        
        Args:
            repo_url: Repository URL to setup access for
            
        Returns:
            Setup status and authenticated URL
        """
        logger.info(f"Setting up repository access for: {repo_url}")
        
        try:
            configure_git_user()
            authenticated_url = setup_git_auth(repo_url, os.getenv('GITLAB_TOKEN'))
            
            return {
                "status": "success",
                "authenticated_url": authenticated_url,
                "has_auth": authenticated_url != repo_url,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Repository access setup failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    @tool
    async def clone_repository(
        self,
        repo_url: str,
        branch: str,
        temp_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Clone repository branch to temporary location.
        
        Args:
            repo_url: Repository URL
            branch: Branch name to clone
            temp_dir: Optional temporary directory path
            
        Returns:
            Repository path and metadata
        """
        logger.info(f"Cloning branch '{branch}' from {repo_url}")
        
        try:
            if not temp_dir:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                temp_dir = str(Path(tempfile.gettempdir()) / f"config_collector_{timestamp}_{branch}")
            
            repo_path = Path(temp_dir)
            repo = ensure_repo_ready(repo_url, repo_path)
            
            if not repo:
                return {
                    "status": "error",
                    "error": "Failed to clone repository",
                    "timestamp": datetime.now().isoformat()
                }
            
            # Switch to requested branch
            switch_to_branch(repo, branch)
            
            return {
                "status": "success",
                "repo_path": str(repo_path),
                "branch": branch,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Repository clone failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    @tool
    async def extract_config_files(
        self,
        repo_path: str,
        target_folder: str = ""
    ) -> Dict[str, Any]:
        """
        Extract configuration files from repository.
        
        Args:
            repo_path: Path to cloned repository
            target_folder: Optional subfolder to analyze
            
        Returns:
            List of configuration file paths
        """
        logger.info(f"Extracting config files from: {repo_path}")
        
        try:
            repo = git.Repo(repo_path)
            config_files = get_config_file_paths(repo, target_folder)
            
            return {
                "status": "success",
                "config_files": config_files,
                "total_files": len(config_files),
                "target_folder": target_folder or "entire_repository",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Config file extraction failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    @tool
    async def create_golden_snapshot(
        self,
        repo_url: str,
        main_branch: str,
        environment: str,
        service_id: str,
        config_paths: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create golden snapshot branch from main branch.
    
        Args:
            repo_url: Repository URL
            main_branch: Source branch name
            environment: Environment name
            service_id: Service identifier
            config_paths: List of config file patterns (defaults to standard patterns)
        
        Returns:
            Golden branch name and metadata
        """
        logger.info(f"Creating golden snapshot for {service_id}/{environment}")
        
        try:
            # Generate unique branch name
            golden_branch = generate_unique_branch_name("golden", environment)
            
            # Default config paths if not provided
            if not config_paths:
                config_paths = [
                    "*.yml", "*.yaml", "*.properties", "*.toml", "*.ini",
                    "*.cfg", "*.conf", "*.config", "Dockerfile", "docker-compose.yml",
                    "pom.xml", "build.gradle", "requirements.txt", "pyproject.toml", "go.mod"
                ]
            
            # Create environment-specific config branch (filtered by environment)
            # This ensures golden branches only contain files relevant to the target environment
            success = create_env_specific_config_branch(
                repo_url=repo_url,
                main_branch=main_branch,
                new_branch_name=golden_branch,
                environment=environment,
                config_paths=config_paths,
                gitlab_token=os.getenv('GITLAB_TOKEN')
            )
            
            if not success:
                return {
                    "status": "error",
                    "error": f"Failed to create golden branch {golden_branch}",
                    "timestamp": datetime.now().isoformat()
                }
            
            logger.info(f"✅ Created golden branch: {golden_branch}")
            
            return {
                "status": "success",
                "golden_branch": golden_branch,
                "source_branch": main_branch,
                "environment": environment,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Golden snapshot creation failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    @tool
    async def create_drift_snapshot(
        self,
        repo_url: str,
        main_branch: str,
        environment: str,
        service_id: str,
        config_paths: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create drift snapshot branch from main branch.
        
        Args:
            repo_url: Repository URL
            main_branch: Source branch name
            environment: Environment name
            service_id: Service identifier
            config_paths: List of config file patterns
            
        Returns:
            Drift branch name and metadata
        """
        logger.info(f"Creating drift snapshot for {service_id}/{environment}")
        
        try:
            # Generate unique branch name
            drift_branch = generate_unique_branch_name("drift", environment)
            
            # Default config paths if not provided
            if not config_paths:
                config_paths = [
                    "*.yml", "*.yaml", "*.properties", "*.toml", "*.ini",
                    "*.cfg", "*.conf", "*.config", "Dockerfile", "docker-compose.yml",
                    "pom.xml", "build.gradle", "requirements.txt", "pyproject.toml", "go.mod"
                ]
            
            # Create environment-specific config branch (filtered by environment)
            # This ensures drift branches only contain files relevant to the target environment
            success = create_env_specific_config_branch(
                repo_url=repo_url,
                main_branch=main_branch,
                new_branch_name=drift_branch,
                environment=environment,
                config_paths=config_paths,
                gitlab_token=os.getenv('GITLAB_TOKEN')
            )
            
            if not success:
                return {
                    "status": "error",
                    "error": f"Failed to create drift branch {drift_branch}",
                    "timestamp": datetime.now().isoformat()
                }
            
            logger.info(f"✅ Created drift branch: {drift_branch}")
            
            return {
                "status": "success",
                "drift_branch": drift_branch,
                "source_branch": main_branch,
                "environment": environment,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Drift snapshot creation failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        
    @tool
    async def prepare_repository_snapshots(
        self,
        repo_url: str,
        main_branch: str,
        environment: str,
        service_id: str,
        target_folder: str = ""
    ) -> Dict[str, Any]:
        """
        Complete workflow: Create snapshots and extract config files.
        
        CONVENIENCE TOOL: This is a deterministic convenience tool for standard cases.
        It orchestrates the complete workflow:
        1. Create golden snapshot branch
        2. Create drift snapshot branch
        3. Clone both branches to temporary locations
        4. Extract config files from both
        
        For edge cases or custom workflows, use individual tools:
        - create_golden_snapshot
        - create_drift_snapshot
        - clone_repository
        - extract_config_files
        
        Args:
            repo_url: Repository URL
            main_branch: Main branch name
            environment: Environment name
            service_id: Service identifier
            target_folder: Optional subfolder to analyze
            
        Returns:
            Complete snapshot information with paths and config files:
            {
                "status": "success",
                "golden_branch": "...",
                "drift_branch": "...",
                "golden_path": "...",
                "drift_path": "...",
                "config_files": [...],
                "golden_config_files": [...],
                "drift_config_files": [...]
            }
        """
        logger.info("=" * 60)
        logger.info(f"📦 Preparing Repository Snapshots")
        logger.info(f"   Service: {service_id}")
        logger.info(f"   Environment: {environment}")
        logger.info(f"   Main Branch: {main_branch}")
        logger.info("=" * 60)
        
        try:
            # Step 1: Get or create golden snapshot branch
            logger.info("\n📸 Step 1: Getting/creating golden snapshot branch...")
            
            # Check if golden branch already exists in database
            existing_golden = get_active_golden_branch(service_id, environment)
            
            if existing_golden:
                logger.info(f"✅ Found existing golden branch in database: {existing_golden}")
                logger.info(f"✅ Reusing golden branch from database (database is source of truth)")
                golden_branch = existing_golden
                # No need to check Git - if cloning fails later, we'll handle it then
            else:
                logger.info(f"ℹ️  No existing golden branch found for {service_id}/{environment}, creating new one...")
                # Create new golden branch
                golden_result = await self.create_golden_snapshot(
                    repo_url=repo_url,
                    main_branch=main_branch,
                    environment=environment,
                    service_id=service_id
                )
                
                if golden_result.get('status') != 'success':
                    return {
                        "status": "error",
                        "error": f"Failed to create golden snapshot: {golden_result.get('error')}",
                        "timestamp": datetime.now().isoformat()
                    }
                
                golden_branch = golden_result['golden_branch']
                # Track in database
                add_golden_branch(service_id, environment, golden_branch)
                logger.info(f"✅ Golden branch created and tracked: {golden_branch}")
            
            # Step 2: Create drift snapshot branch (always create new)
            logger.info("\n📸 Step 2: Creating new drift snapshot branch...")
            drift_result = await self.create_drift_snapshot(
                repo_url=repo_url,
                main_branch=main_branch,
                environment=environment,
                service_id=service_id
            )
            
            if drift_result.get('status') != 'success':
                return {
                    "status": "error",
                    "error": f"Failed to create drift snapshot: {drift_result.get('error')}",
                    "timestamp": datetime.now().isoformat()
                }
            
            drift_branch = drift_result['drift_branch']
            # Track in database
            add_drift_branch(service_id, environment, drift_branch)
            logger.info(f"✅ Drift branch created and tracked: {drift_branch}")
            
            # Step 3: Clone both branches to temporary locations
            logger.info("\n📥 Step 3: Cloning branches to temporary locations...")
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_temp = Path(tempfile.gettempdir()) / "config_collector" / f"{service_id}_{environment}_{timestamp}"
            base_temp.mkdir(parents=True, exist_ok=True)
            
            golden_temp = base_temp / "golden"
            drift_temp = base_temp / "drift"
            
            # Clone golden branch
            logger.info(f"Cloning golden branch '{golden_branch}'...")
            configure_git_user()
            golden_repo = ensure_repo_ready(repo_url, golden_temp)
            if not golden_repo:
                return {
                    "status": "error",
                    "error": "Failed to clone golden branch",
                    "timestamp": datetime.now().isoformat()
                }
            switch_to_branch(golden_repo, golden_branch)
            logger.info(f"✅ Golden branch cloned to: {golden_temp}")
            
            # Clone drift branch
            logger.info(f"Cloning drift branch '{drift_branch}'...")
            drift_repo = ensure_repo_ready(repo_url, drift_temp)
            if not drift_repo:
                return {
                    "status": "error",
                    "error": "Failed to clone drift branch",
                    "timestamp": datetime.now().isoformat()
                }
            switch_to_branch(drift_repo, drift_branch)
            logger.info(f"✅ Drift branch cloned to: {drift_temp}")
            
            # Step 4: Extract config files from both branches
            logger.info("\n🔍 Step 4: Extracting configuration files...")
            
            golden_config_files = get_config_file_paths(golden_repo, target_folder)
            drift_config_files = get_config_file_paths(drift_repo, target_folder)
            
            # Combine and deduplicate
            all_config_files = sorted(set(golden_config_files + drift_config_files))
            
            logger.info(f"✅ Found {len(all_config_files)} unique configuration files")
            logger.info(f"   Golden branch: {len(golden_config_files)} files")
            logger.info(f"   Drift branch: {len(drift_config_files)} files")
            
            logger.info("\n" + "=" * 60)
            logger.info("✅ Repository Snapshots Prepared Successfully")
            logger.info("=" * 60)
            logger.info(f"   Golden branch: {golden_branch}")
            logger.info(f"   Drift branch: {drift_branch}")
            logger.info(f"   Golden path: {golden_temp}")
            logger.info(f"   Drift path: {drift_temp}")
            logger.info(f"   Config files: {len(all_config_files)}")
            logger.info("=" * 60)
        
            return {
                "status": "success",
                "golden_branch": golden_branch,
                "drift_branch": drift_branch,
                "golden_path": str(golden_temp),
                "drift_path": str(drift_temp),
                "config_files": all_config_files,
                "golden_config_files": golden_config_files,
                "drift_config_files": drift_config_files,
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.exception(f"❌ Failed to prepare repository snapshots: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        
    @tool
    async def certify_drift_as_golden(
        self,
        repo_url: str,
        drift_branch: str,
        environment: str,
        service_id: str
    ) -> Dict[str, Any]:
        """
        Certify a drift branch as the new golden branch.
        
        This is used when configurations have been validated and approved.
        The drift branch becomes the new golden baseline for future comparisons.
        
        Args:
            repo_url: Repository URL
            drift_branch: Drift branch to certify (e.g., "drift_prod_20251201_143052")
            environment: Environment name
            service_id: Service identifier
            
        Returns:
            New golden branch information
        """
        logger.info(f"🏆 Certifying drift branch as golden: {drift_branch}")
        
        try:
            # Generate new golden branch name
            golden_branch = generate_unique_branch_name("golden", environment)
            
            # Create golden branch from drift branch
            # Use Git operations to copy drift branch to golden branch
            authenticated_url = setup_git_auth(repo_url, os.getenv('GITLAB_TOKEN'))
            
            # Clone drift branch temporarily
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_dir = Path(tempfile.gettempdir()) / f"certify_{timestamp}"
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            try:
                # Clone the drift branch
                repo = git.Repo.clone_from(authenticated_url, temp_dir, branch=drift_branch)
                
                # Create new golden branch from current state
                repo.git.checkout('-b', golden_branch)
                
                # Push to remote
                repo.git.push('origin', golden_branch)
                
                logger.info(f"✅ Pushed new golden branch: {golden_branch}")
                
                # Track in database (this will become the new active golden)
                add_golden_branch(service_id, environment, golden_branch)
                
                logger.info(f"✅ Certified {drift_branch} as new golden branch: {golden_branch}")
                
                return {
                    "status": "success",
                    "golden_branch": golden_branch,
                    "source_drift_branch": drift_branch,
                    "environment": environment,
                    "service_id": service_id,
                    "timestamp": datetime.now().isoformat(),
                    "message": f"Drift branch {drift_branch} certified as golden {golden_branch}"
                }
        
            finally:
                # Cleanup temp directory
                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    
        except Exception as e:
            logger.error(f"Failed to certify drift as golden: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }