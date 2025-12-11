"""
Drift Detector Agent - Configuration Drift Detection (Database-Only)

This agent performs precision drift analysis using drift.py and saves to database.

Responsibilities:
- Context parsing (parse YAML/JSON/properties/XML files)
- Compare algorithms (structural diff, semantic diff)
- Diff generation (line-by-line deltas with exact locators)
- Save context_bundle to database (context_bundles table)

NO risk analysis or LLM prompt generation - that's done by Triaging-Routing Agent.

Input: Repository snapshots from Config Collector (golden_path, drift_path) + run_id
Output: bundle_id (database reference), no JSON files
"""

import logging
import json
import time
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.tools import tool

from shared.config import Config
from shared.models import TaskRequest, TaskResponse
from shared.db import save_context_bundle, save_config_delta

# Import drift analysis functions
from shared.drift_analyzer import (
    extract_repo_tree,
    classify_files,
    diff_structural,
    semantic_config_diff,
    extract_dependencies,
    dependency_diff,
    detector_spring_profiles,
    detector_jenkinsfile,
    detector_dockerfiles,
    build_code_hunk_deltas,
    build_binary_deltas,
    emit_context_bundle,
)

logger = logging.getLogger(__name__)

# Define PROJECT_ROOT for policies.yaml lookup
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()


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


class DriftDetectorAgent(Agent):
    """
    Drift Detector Agent - Precision Configuration Drift Detection
    
    Responsibilities:
    1. Parse configuration files (YAML, JSON, properties, XML, TOML)
    2. Compare golden and drift branches using precision algorithms
    3. Generate structured deltas with exact line-level locators
    4. Create context_bundle.json for downstream agents
    
    NO risk analysis or LLM reasoning - that's handled by Triaging-Routing Agent.
    """

    def __init__(self, config: Optional[Config] = None):
        if config is None:
            config = Config()
        
        system_prompt = self._get_system_prompt()
        
        super().__init__(
            model=BedrockModel(model_id=config.bedrock_worker_model_id),
            system_prompt=system_prompt,
            tools=[
                self.run_drift_analysis,
                self.extract_file_trees,
                self.compute_structural_diff,
                self.compute_semantic_diff,
                self.run_specialized_detectors,
                self.generate_context_bundle
            ]
        )
        self.config = config

    def _get_system_prompt(self) -> str:
        return """You are the Drift Detector Agent in the Golden Config AI system.

**Your Role:**
Perform precision drift analysis between golden and drift branch snapshots.

**Your Responsibilities:**
1. Parse configuration files (YAML, JSON, properties, XML, TOML)
2. Compare golden and drift branches using precision algorithms
3. Generate structured deltas with exact line-level locators
4. Create context_bundle.json for downstream agents

**Standard Workflow:**
Use the `run_drift_analysis` tool which will:
- Extract file trees from both branches
- Classify files by type (config, code, build, etc.)
- Compute structural diff (added, removed, modified, renamed)
- Compute semantic diff (key-level changes in config files)
- Run specialized detectors (Spring profiles, Jenkinsfile, Docker)
- Build code hunks with line numbers
- Generate context_bundle.json

**Important:**
- You do NOT perform risk analysis - that's handled by Triaging-Routing Agent
- You do NOT generate LLM prompts - just structured deltas
- Always maintain exact locators (yamlpath, jsonpath, line numbers)
- Focus only on configuration files

**Available Tools:**
- `run_drift_analysis`: Complete workflow (use this for standard cases)
- `extract_file_trees`: Extract file lists from repositories
- `compute_structural_diff`: Find added/removed/modified/renamed files
- `compute_semantic_diff`: Find key-level changes in config files
- `run_specialized_detectors`: Run Spring/Jenkins/Docker detectors
- `generate_context_bundle`: Create context_bundle.json

**Output Format:**
Return path to context_bundle.json with structured deltas.
"""

    def process_task(self, task: TaskRequest) -> TaskResponse:
        """
        Process a drift detection task.
        
        HYBRID APPROACH: LLM receives task and decides how to execute.
        For 99% of cases, LLM uses run_drift_analysis tool.
        
        Args:
            task: TaskRequest with parameters:
                - golden_path: Path to golden branch clone
                - drift_path: Path to drift branch clone
                - golden_branch: Golden branch name
                - drift_branch: Drift branch name
                - config_files: List of config files to analyze
                - target_folder: Optional subfolder to analyze
                
        Returns:
            TaskResponse with bundle_id (database reference)
        """
        start_time = time.time()
        
        try:
            logger.info(f"🔍 Drift Detector processing task: {task.task_id}")
            
            params = task.parameters
            
            # Extract parameters
            golden_path = params.get('golden_path')
            drift_path = params.get('drift_path')
            golden_branch = params.get('golden_branch', 'golden')
            drift_branch = params.get('drift_branch', 'drift')
            target_folder = params.get('target_folder', '')
            
            # Support legacy format with repository_snapshots
            if not golden_path and 'repository_snapshots' in params:
                snapshots = params['repository_snapshots']
                golden_path = snapshots.get('golden_path')
                drift_path = snapshots.get('drift_path')
                golden_branch = snapshots.get('golden_branch', golden_branch)
                drift_branch = snapshots.get('drift_branch', drift_branch)
            
            if not golden_path or not drift_path:
                return TaskResponse(
                    task_id=task.task_id,
                    status="failure",
                    result={},
                    error="Missing required parameters: golden_path and drift_path",
                    processing_time_seconds=time.time() - start_time,
                    metadata={"agent": "drift_detector"}
                )
            
            # Build task description for LLM
            task_description = f"""
You need to perform precision drift analysis between golden and drift branches.

**Task Parameters:**
- Golden Path: {golden_path}
- Drift Path: {drift_path}
- Golden Branch: {golden_branch}
- Drift Branch: {drift_branch}
- Target Folder: {target_folder if target_folder else "entire repository"}

**Standard Workflow:**
Use the `run_drift_analysis` tool with the provided parameters.
This will:
1. Extract file trees from both branches
2. Classify files by type
3. Compute structural diff (added/removed/modified/renamed)
4. Compute semantic diff (key-level changes)
5. Run specialized detectors (Spring, Jenkins, Docker)
6. Generate context_bundle.json

**Expected Output:**
Return the path to context_bundle.json containing structured deltas.

Execute the analysis now.
"""
            
            logger.info("🤖 Invoking LLM agent to execute drift analysis...")
            
            # Let the LLM agent handle the task
            agent_response = self(task_description)
            
            logger.info("✅ Agent completed execution")
            
            # Debug: Inspect agent response structure
            logger.info(f"🔍 DEBUG: Agent response type: {type(agent_response)}")
            if hasattr(agent_response, 'structured_output'):
                logger.info(f"🔍 DEBUG: structured_output type: {type(agent_response.structured_output)}")
                if isinstance(agent_response.structured_output, list):
                    logger.info(f"🔍 DEBUG: structured_output length: {len(agent_response.structured_output)}")
                    if len(agent_response.structured_output) > 0:
                        logger.info(f"🔍 DEBUG: Last tool result type: {type(agent_response.structured_output[-1])}")
            
            # Parse the agent's response
            result_data = self._parse_agent_response(agent_response)
            
            # Validate we got the expected output
            if not isinstance(result_data, dict):
                return TaskResponse(
                    task_id=task.task_id,
                    status="failure",
                    result={},
                    error=f"Agent did not return expected data format: {str(result_data)[:200]}",
                    processing_time_seconds=time.time() - start_time,
                    metadata={"agent": "drift_detector"}
                )
            
            # Check for errors
            if result_data.get('status') == 'error':
                return TaskResponse(
                    task_id=task.task_id,
                    status="failure",
                    result={},
                    error=result_data.get('error', 'Unknown error'),
                    processing_time_seconds=time.time() - start_time,
                    metadata={"agent": "drift_detector"}
                )
            
            # Extract bundle data and save to database
            bundle_data = result_data.get('bundle_data')
            summary = result_data.get('summary', {})
            
            if not bundle_data:
                return TaskResponse(
                    task_id=task.task_id,
                    status="failure",
                    result={},
                    error="Agent did not return bundle_data",
                    processing_time_seconds=time.time() - start_time,
                    metadata={"agent": "drift_detector"}
                )
            
            # Save to database only (no JSON files)
            run_id = params.get('run_id', task.task_id)
            try:
                bundle_id = save_context_bundle(run_id, bundle_data)
                logger.info(f"✅ Context bundle saved to database: {bundle_id}")
            except Exception as e:
                logger.error(f"Failed to save context bundle to database: {e}")
                return TaskResponse(
                    task_id=task.task_id,
                    status="failure",
                    result={},
                    error=f"Failed to save to database: {str(e)}",
                    processing_time_seconds=time.time() - start_time,
                    metadata={"agent": "drift_detector"}
                )
            
            logger.info(f"✅ Drift Detector completed")
            logger.info(f"   Bundle ID: {bundle_id}")
            logger.info(f"   Total deltas: {summary.get('total_deltas', 0)}")
            
            return TaskResponse(
                task_id=task.task_id,
                status="success",
                result={
                    "bundle_id": bundle_id,
                    "summary": summary
                },
                error=None,
                processing_time_seconds=time.time() - start_time,
                metadata={
                    "agent": "drift_detector",
                    "bundle_id": bundle_id
                }
            )
            
        except Exception as e:
            logger.exception(f"❌ Drift Detector task processing failed: {e}")
            return TaskResponse(
                task_id=task.task_id,
                status="failure",
                result={},
                error=str(e),
                processing_time_seconds=time.time() - start_time,
                metadata={"agent": "drift_detector"}
            )

    def _parse_agent_response(self, agent_response) -> Dict[str, Any]:
        """
        Parse the agent's response to extract structured data.
        
        Priority order:
        1. structured_output (Strands AI returns tool results here)
        2. tool_results (legacy support)
        3. Direct dict response
        4. JSON in content/messages
        5. JSON extracted from markdown code blocks
        6. JSON extracted from mixed text
        """
        try:
            # CASE 0: Check structured_output attribute (Strands AI framework)
            if hasattr(agent_response, 'structured_output') and agent_response.structured_output:
                logger.info("Found structured_output from Strands AI")
                structured_output = agent_response.structured_output
                
                # structured_output is typically a list of tool results
                if isinstance(structured_output, list) and len(structured_output) > 0:
                    last_tool_result = structured_output[-1]  # Get last tool call
                    logger.info(f"Last tool result type: {type(last_tool_result)}")
                    
                    # The tool result should be a dict from run_drift_analysis
                    if isinstance(last_tool_result, dict):
                        logger.info("✅ Extracted dict from structured_output")
                        return last_tool_result
                    
                    # Sometimes it's wrapped in another structure
                    if hasattr(last_tool_result, 'output'):
                        if isinstance(last_tool_result.output, dict):
                            logger.info("✅ Extracted dict from structured_output.output")
                            return last_tool_result.output
            
            # CASE 1: Response has tool_results attribute (HIGHEST PRIORITY - legacy)
            if hasattr(agent_response, 'tool_results') and agent_response.tool_results:
                logger.debug(f"Found tool_results with {len(agent_response.tool_results)} results")
                last_result = agent_response.tool_results[-1]
                
                if isinstance(last_result, dict):
                    logger.debug("Tool result is already a dict")
                    return last_result
                
                if hasattr(last_result, 'result'):
                    if isinstance(last_result.result, dict):
                        logger.debug("Extracted dict from tool_result.result")
                        return last_result.result
                
                if hasattr(last_result, 'output'):
                    if isinstance(last_result.output, dict):
                        logger.debug("Extracted dict from tool_result.output")
                        return last_result.output
                    if isinstance(last_result.output, str):
                        try:
                            parsed = json.loads(last_result.output)
                            if isinstance(parsed, dict):
                                logger.debug("Parsed JSON from tool_result.output string")
                                return parsed
                        except json.JSONDecodeError:
                            pass
            
            # CASE 2: Response is already a dict
            if isinstance(agent_response, dict):
                logger.debug("Agent response is already a dict")
                return agent_response
            
            # CASE 3: Response has content attribute
            if hasattr(agent_response, 'content'):
                content = agent_response.content
                logger.debug(f"Found content attribute, type: {type(content)}")
                
                if isinstance(content, dict):
                    logger.debug("Content is already a dict")
                    return content
                
                if isinstance(content, str):
                    # Direct JSON parse
                    try:
                        parsed = json.loads(content)
                        if isinstance(parsed, dict):
                            logger.debug("Parsed JSON from content string")
                            return parsed
                    except json.JSONDecodeError:
                        pass
                    
                    # Extract from markdown
                    json_from_markdown = self._extract_json_from_markdown(content)
                    if json_from_markdown:
                        logger.debug("Extracted JSON from markdown in content")
                        return json_from_markdown
                    
                    # Extract from mixed text
                    json_from_text = self._extract_json_from_text(content)
                    if json_from_text:
                        logger.debug("Extracted JSON from mixed text in content")
                        return json_from_text
            
            # CASE 4: Response has messages attribute
            if hasattr(agent_response, 'messages') and agent_response.messages:
                logger.debug(f"Found {len(agent_response.messages)} messages")
                last_message = agent_response.messages[-1]
                if hasattr(last_message, 'content'):
                    if isinstance(last_message.content, dict):
                        logger.debug("Last message content is a dict")
                        return last_message.content
                    if isinstance(last_message.content, str):
                        try:
                            parsed = json.loads(last_message.content)
                            logger.debug("Parsed JSON from last message content")
                            return parsed
                        except json.JSONDecodeError:
                            pass
                        
                        json_from_markdown = self._extract_json_from_markdown(last_message.content)
                        if json_from_markdown:
                            logger.debug("Extracted JSON from markdown in last message")
                            return json_from_markdown
                        
                        json_from_text = self._extract_json_from_text(last_message.content)
                        if json_from_text:
                            logger.debug("Extracted JSON from mixed text in last message")
                            return json_from_text
            
            # CASE 5: String representation
            response_str = str(agent_response)
            logger.debug(f"Trying string representation parse, length: {len(response_str)}")
            
            if response_str.strip().startswith('{'):
                try:
                    parsed = json.loads(response_str)
                    logger.debug("Parsed JSON from string representation")
                    return parsed
                except json.JSONDecodeError:
                    pass
            
            json_from_markdown = self._extract_json_from_markdown(response_str)
            if json_from_markdown:
                logger.debug("Extracted JSON from markdown in string representation")
                return json_from_markdown
            
            json_from_text = self._extract_json_from_text(response_str)
            if json_from_text:
                logger.debug("Extracted JSON from mixed text in string representation")
                return json_from_text
            
            logger.warning(f"Could not parse agent response format: {type(agent_response)}")
            logger.warning(f"Response preview: {str(agent_response)[:200]}")
            
            return {
                "error": "Failed to parse agent response",
                "raw_response_type": str(type(agent_response)),
                "raw_response": str(agent_response)[:500]
            }
            
        except Exception as e:
            logger.error(f"Error parsing agent response: {e}", exc_info=True)
            return {
                "error": f"Failed to parse response: {e}",
                "raw_response": str(agent_response)[:500] if agent_response else "None"
            }
    
    def _extract_json_from_markdown(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from markdown code blocks."""
        import re
        
        patterns = [
            r'```json\s*\n(.*?)\n```',
            r'```\s*\n(\{.*?\})\s*\n```',
            r'```\s*\n(\[.*?\])\s*\n```',
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
        """Extract JSON object from mixed text."""
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
                    potential_json = text[start_idx:i+1]
                    try:
                        parsed = json.loads(potential_json)
                        if isinstance(parsed, dict):
                            return parsed
                    except json.JSONDecodeError:
                        start_idx = text.find('{', i+1)
                        if start_idx == -1:
                            return None
                        brace_count = 0
                        continue
        
        return None

    @tool
    def run_drift_analysis(
        self,
        golden_path: str,
        drift_path: str,
        target_folder: str = ""
    ) -> Dict[str, Any]:
        """
        Run complete drift analysis workflow using drift.py precision.
        
        This is the main method that performs:
        1. Extract file trees from both branches
        2. Classify files by type
        3. Compute structural diff (added/removed/modified/renamed)
        4. Compute semantic diff (key-level changes)
        5. Analyze dependencies
        6. Run specialized detectors (Spring, Jenkins, Docker)
        7. Build code hunks with line numbers
        8. Generate context_bundle.json
        
        Args:
            golden_path: Path to golden branch clone
            drift_path: Path to drift branch clone
            target_folder: Optional subfolder to analyze
            
        Returns:
            Analysis results with context_bundle.json path
        """
        logger.info("=" * 60)
        logger.info("🔍 Starting Drift Analysis with drift.py Precision")
        logger.info(f"   Golden: {golden_path}")
        logger.info(f"   Drift: {drift_path}")
        logger.info("=" * 60)
        
        golden_temp = Path(golden_path)
        drift_temp = Path(drift_path)
        
        if not golden_temp.exists():
            return {
                "status": "error",
                "error": f"Golden path does not exist: {golden_path}",
                "timestamp": datetime.now().isoformat()
            }
        
        if not drift_temp.exists():
            return {
                "status": "error",
                "error": f"Drift path does not exist: {drift_path}",
                "timestamp": datetime.now().isoformat()
            }
        
        try:
            # ================================================================
            # PHASE 1: EXTRACT FILE TREES
            # ================================================================
            logger.info("\n📂 Phase 1: Extracting file trees")
            logger.info("-" * 60)
            
            all_golden_paths = extract_repo_tree(golden_temp)
            all_drift_paths = extract_repo_tree(drift_temp)
            
            # Filter to only configuration files
            logger.info("Filtering for configuration files only...")
            golden_paths = [f for f in all_golden_paths if is_config_file(f)]
            drift_paths = [f for f in all_drift_paths if is_config_file(f)]
            
            logger.info(f"  All Golden files: {len(all_golden_paths)} -> Config files: {len(golden_paths)}")
            logger.info(f"  All Drift files: {len(all_drift_paths)} -> Config files: {len(drift_paths)}")
            
            # Log first 10 config files
            if golden_paths:
                logger.info("\n  📂 Configuration files in Golden:")
                for idx, f in enumerate(golden_paths[:10], 1):
                    logger.info(f"    {idx}. {f}")
                if len(golden_paths) > 10:
                    logger.info(f"    ... and {len(golden_paths) - 10} more")
            
            # ================================================================
            # PHASE 2: CLASSIFY FILES
            # ================================================================
            logger.info("\n📋 Phase 2: Classifying files by type")
            logger.info("-" * 60)
            
            golden_files = classify_files(golden_temp, golden_paths)
            drift_files = classify_files(drift_temp, drift_paths)
            
            logger.info(f"  Classified {len(golden_files)} golden files")
            logger.info(f"  Classified {len(drift_files)} drift files")
            
            # ================================================================
            # PHASE 3: STRUCTURAL DIFF
            # ================================================================
            logger.info("\n🔄 Phase 3: Computing structural diff")
            logger.info("-" * 60)
            
            file_changes = diff_structural(golden_files, drift_files)
            
            logger.info(f"  Added: {len(file_changes['added'])} files")
            logger.info(f"  Removed: {len(file_changes['removed'])} files")
            logger.info(f"  Modified: {len(file_changes['modified'])} files")
            logger.info(f"  Renamed: {len(file_changes['renamed'])} files")
            
            # ================================================================
            # PHASE 4: SEMANTIC DIFF (Key-level changes)
            # ================================================================
            logger.info("\n🔑 Phase 4: Computing semantic diff (key-level changes)")
            logger.info("-" * 60)
            
            config_changed_paths = []
            for f in sorted(set(file_changes["modified"]) | set(file_changes["added"])):
                if is_config_file(f):
                    config_changed_paths.append(f)
            
            config_diff = semantic_config_diff(golden_temp, drift_temp, config_changed_paths)
            
            logger.info(f"  Config files analyzed: {len(config_changed_paths)}")
            logger.info(f"  Keys added: {len(config_diff.get('added', {}))}")
            logger.info(f"  Keys removed: {len(config_diff.get('removed', {}))}")
            logger.info(f"  Keys changed: {len(config_diff.get('changed', {}))}")
            
            # ================================================================
            # PHASE 5: DEPENDENCY ANALYSIS
            # ================================================================
            logger.info("\n📦 Phase 5: Analyzing dependencies")
            logger.info("-" * 60)
            
            golden_deps = extract_dependencies(golden_temp)
            drift_deps = extract_dependencies(drift_temp)
            dep_diff = dependency_diff(golden_deps, drift_deps)
            
            dep_changes = 0
            for eco, changes in dep_diff.items():
                dep_changes += len(changes.get('added', {}))
                dep_changes += len(changes.get('removed', {}))
                dep_changes += len(changes.get('changed', {}))
            
            logger.info(f"  Dependency changes: {dep_changes}")
            
            # ================================================================
            # PHASE 6: SPECIALIZED DETECTORS
            # ================================================================
            logger.info("\n🔬 Phase 6: Running specialized detectors")
            logger.info("-" * 60)
            
            config_files_for_detectors = golden_paths + drift_paths
            has_spring_files = any("application" in f and (".yml" in f or ".yaml" in f or ".properties" in f) for f in config_files_for_detectors)
            has_jenkins_files = any("jenkinsfile" in f.lower() for f in config_files_for_detectors)
            has_docker_files = any("dockerfile" in f.lower() or "docker-compose" in f.lower() for f in config_files_for_detectors)
            
            spring_deltas = detector_spring_profiles(golden_temp, drift_temp) if has_spring_files else []
            jenkins_deltas = detector_jenkinsfile(golden_temp, drift_temp) if has_jenkins_files else []
            docker_deltas = detector_dockerfiles(golden_temp, drift_temp) if has_docker_files else []
            
            logger.info(f"  Spring profile deltas: {len(spring_deltas)}")
            logger.info(f"  Jenkinsfile deltas: {len(jenkins_deltas)}")
            logger.info(f"  Docker deltas: {len(docker_deltas)}")
            
            # ================================================================
            # PHASE 7: CODE HUNKS (Line-level diffs)
            # ================================================================
            logger.info("\n📝 Phase 7: Building code hunks with line numbers")
            logger.info("-" * 60)
            
            config_modified_files = [f for f in file_changes.get("modified", []) if is_config_file(f)]
            code_hunks = build_code_hunk_deltas(golden_temp, drift_temp, config_modified_files)
            
            logger.info(f"  Code hunks: {len(code_hunks)}")
            
            # ================================================================
            # PHASE 8: BINARY FILE ANALYSIS
            # ================================================================
            logger.info("\n📦 Phase 8: Analyzing binary files")
            logger.info("-" * 60)
            
            binary_deltas = build_binary_deltas(golden_temp, drift_temp, config_modified_files)
            
            logger.info(f"  Binary file changes: {len(binary_deltas)}")
            
            # ================================================================
            # PHASE 9: BUILD CONTEXT BUNDLE
            # ================================================================
            logger.info("\n📦 Phase 9: Building context bundle")
            logger.info("-" * 60)
            
            # Note: We use a temp directory for emit_context_bundle (it writes a file as side effect)
            # but we only use the returned bundle_data dict for DB storage
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            import tempfile
            output_dir = Path(tempfile.mkdtemp(prefix=f"bundle_{timestamp}_"))
            
            # Build overview
            config_golden_files = [f for f in golden_files if is_config_file(f.get("name", f.get("path", "")))]
            config_drift_files = [f for f in drift_files if is_config_file(f.get("name", f.get("path", "")))]
            
            overview = {
                "golden_repo_name": golden_temp.name,
                "candidate_repo_name": drift_temp.name,
                "golden_repo_path": str(golden_temp),
                "candidate_repo_path": str(drift_temp),
                "golden_files": len(config_golden_files),
                "candidate_files": len(config_drift_files),
                "total_files": len(config_golden_files) + len(config_drift_files),
                "drifted_files": len([f for f in file_changes.get("modified", []) + file_changes.get("added", []) + file_changes.get("removed", []) if is_config_file(f)]),
                "ci_present": any("jenkinsfile" in f.get("name", f.get("path", "")).lower() for f in config_drift_files),
                "build_tools": [f.get("name", f.get("path", "")) for f in config_drift_files if f.get("file_type") == "build"][:10]
            }
            
            # Combine all extra deltas
            extra_deltas = spring_deltas + jenkins_deltas + docker_deltas + code_hunks + binary_deltas
            
            # Filter to config files only
            config_extra_deltas = []
            for delta in extra_deltas:
                delta_file = delta.get("file", "")
                if delta_file and is_config_file(delta_file):
                    config_extra_deltas.append(delta)
                elif not delta_file:
                    config_extra_deltas.append(delta)
            
            logger.info(f"  Extra deltas: {len(extra_deltas)} -> Config deltas: {len(config_extra_deltas)}")
            
            # Load policies (optional)
            policies_path = PROJECT_ROOT / "shared" / "policies.yaml"
            if not policies_path.exists():
                logger.warning("⚠️  policies.yaml not found, proceeding without policy tagging")
                policies_path = None
            else:
                logger.info(f"✅ Using policies from: {policies_path}")
            
            # Set global variables for drift_v1.py
            import shared.drift_analyzer.drift_v1 as drift_v1_module
            drift_v1_module.golden_root = golden_temp
            drift_v1_module.candidate_root = drift_temp
            drift_v1_module.g_files = config_golden_files
            drift_v1_module.c_files = config_drift_files
            
            # Emit context bundle (returns dict, file write is just a side effect)
            logger.info("Generating context bundle data...")
            bundle_data = emit_context_bundle(
                output_dir,
                golden_temp,
                drift_temp,
                overview,
                dep_diff,
                config_diff,
                file_changes,
                config_extra_deltas,
                policies_path
            )
            
            # Note: emit_context_bundle writes context_bundle.json as side effect,
            # but we only use the returned bundle_data dict for DB storage
            
            # ================================================================
            # PHASE 10: PREPARE RESPONSE
            # ================================================================
            logger.info("\n✅ Phase 10: Analysis Complete!")
            logger.info("-" * 60)
            
            # Calculate summary stats
            deltas = bundle_data.get("deltas", [])
            config_deltas = [d for d in deltas if is_config_file(d.get("file", ""))]
            files_with_drift = len(set(d.get("file", "") for d in config_deltas))
            
            config_added = [f for f in file_changes.get("added", []) if is_config_file(f)]
            config_removed = [f for f in file_changes.get("removed", []) if is_config_file(f)]
            config_modified = [f for f in file_changes.get("modified", []) if is_config_file(f)]
            
            summary = {
                "total_files": overview["total_files"],
                "drifted_files": overview["drifted_files"],
                "added": len(config_added),
                "removed": len(config_removed),
                "modified": len(config_modified),
                "files_with_drift": files_with_drift,
                "total_deltas": len(config_deltas),
                "config_changes": len(config_diff.get("changed", {})),
                "dependency_changes": dep_changes,
                "code_hunks": len(code_hunks),
                "policies_applied": policies_path is not None
            }
            
            logger.info("📊 Summary:")
            logger.info(f"   Total files: {summary['total_files']}")
            logger.info(f"   Drifted files: {summary['drifted_files']}")
            logger.info(f"   Files added: {summary['added']}")
            logger.info(f"   Files removed: {summary['removed']}")
            logger.info(f"   Files modified: {summary['modified']}")
            logger.info(f"   Total deltas: {summary['total_deltas']}")
            logger.info("=" * 60)
            
            # Clean up temp directory
            import shutil
            try:
                shutil.rmtree(output_dir)
                logger.info(f"✅ Cleaned up temp directory: {output_dir}")
            except Exception as e_cleanup:
                logger.warning(f"Failed to clean up temp directory {output_dir}: {e_cleanup}")
            
            return {
                "status": "success",
                "bundle_data": bundle_data,
                "summary": summary,
                "overview": overview,
                "meta": bundle_data.get("meta", {}),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.exception(f"❌ Error in drift analysis: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    @tool
    def extract_file_trees(
        self,
        golden_path: str,
        drift_path: str
    ) -> Dict[str, Any]:
        """
        Extract file trees from golden and drift branches.
        
        Args:
            golden_path: Path to golden branch clone
            drift_path: Path to drift branch clone
            
        Returns:
            File lists for both branches
        """
        logger.info("Extracting file trees...")
        
        try:
            golden_temp = Path(golden_path)
            drift_temp = Path(drift_path)
            
            all_golden_paths = extract_repo_tree(golden_temp)
            all_drift_paths = extract_repo_tree(drift_temp)
            
            # Filter to config files
            golden_paths = [f for f in all_golden_paths if is_config_file(f)]
            drift_paths = [f for f in all_drift_paths if is_config_file(f)]
            
            return {
                "status": "success",
                "golden_files": golden_paths,
                "drift_files": drift_paths,
                "golden_total": len(all_golden_paths),
                "drift_total": len(all_drift_paths),
                "golden_config_count": len(golden_paths),
                "drift_config_count": len(drift_paths),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to extract file trees: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    @tool
    def compute_structural_diff(
        self,
        golden_path: str,
        drift_path: str,
        golden_files: List[str],
        drift_files: List[str]
    ) -> Dict[str, Any]:
        """
        Compute structural diff between golden and drift branches.
        
        Args:
            golden_path: Path to golden branch clone
            drift_path: Path to drift branch clone
            golden_files: List of files in golden branch
            drift_files: List of files in drift branch
            
        Returns:
            Structural diff (added, removed, modified, renamed)
        """
        logger.info("Computing structural diff...")
        
        try:
            golden_temp = Path(golden_path)
            drift_temp = Path(drift_path)
            
            golden_classified = classify_files(golden_temp, golden_files)
            drift_classified = classify_files(drift_temp, drift_files)
            
            file_changes = diff_structural(golden_classified, drift_classified)
            
            return {
                "status": "success",
                "file_changes": file_changes,
                "added_count": len(file_changes['added']),
                "removed_count": len(file_changes['removed']),
                "modified_count": len(file_changes['modified']),
                "renamed_count": len(file_changes['renamed']),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to compute structural diff: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    @tool
    def compute_semantic_diff(
        self,
        golden_path: str,
        drift_path: str,
        changed_files: List[str]
    ) -> Dict[str, Any]:
        """
        Compute semantic diff (key-level changes) for config files.
        
        Args:
            golden_path: Path to golden branch clone
            drift_path: Path to drift branch clone
            changed_files: List of changed files to analyze
            
        Returns:
            Semantic diff (keys added, removed, changed)
        """
        logger.info("Computing semantic diff...")
        
        try:
            golden_temp = Path(golden_path)
            drift_temp = Path(drift_path)
            
            config_diff = semantic_config_diff(golden_temp, drift_temp, changed_files)
            
            return {
                "status": "success",
                "config_diff": config_diff,
                "keys_added": len(config_diff.get('added', {})),
                "keys_removed": len(config_diff.get('removed', {})),
                "keys_changed": len(config_diff.get('changed', {})),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to compute semantic diff: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    @tool
    def run_specialized_detectors(
        self,
        golden_path: str,
        drift_path: str
    ) -> Dict[str, Any]:
        """
        Run specialized detectors for Spring, Jenkins, and Docker files.
        
        Args:
            golden_path: Path to golden branch clone
            drift_path: Path to drift branch clone
            
        Returns:
            Deltas from specialized detectors
        """
        logger.info("Running specialized detectors...")
        
        try:
            golden_temp = Path(golden_path)
            drift_temp = Path(drift_path)
            
            spring_deltas = detector_spring_profiles(golden_temp, drift_temp)
            jenkins_deltas = detector_jenkinsfile(golden_temp, drift_temp)
            docker_deltas = detector_dockerfiles(golden_temp, drift_temp)
            
            return {
                "status": "success",
                "spring_deltas": spring_deltas,
                "jenkins_deltas": jenkins_deltas,
                "docker_deltas": docker_deltas,
                "spring_count": len(spring_deltas),
                "jenkins_count": len(jenkins_deltas),
                "docker_count": len(docker_deltas),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to run specialized detectors: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    @tool
    def generate_context_bundle(
        self,
        output_dir: str,
        golden_path: str,
        drift_path: str,
        overview: Dict[str, Any],
        dep_diff: Dict[str, Any],
        config_diff: Dict[str, Any],
        file_changes: Dict[str, Any],
        extra_deltas: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Generate context_bundle.json with structured deltas.
        
        Args:
            output_dir: Output directory path
            golden_path: Path to golden branch clone
            drift_path: Path to drift branch clone
            overview: Repository overview
            dep_diff: Dependency diff
            config_diff: Config key-level diff
            file_changes: Structural file changes
            extra_deltas: Additional deltas from detectors
            
        Returns:
            Path to generated context_bundle.json
        """
        logger.info("Generating context bundle data...")
        
        try:
            import tempfile
            import shutil
            
            # Use temp directory (emit_context_bundle writes file as side effect)
            output_path = Path(tempfile.mkdtemp(prefix="bundle_"))
            golden_temp = Path(golden_path)
            drift_temp = Path(drift_path)
            
            # Load policies (PROJECT_ROOT defined at module level)
            policies_path = PROJECT_ROOT / "shared" / "policies.yaml"
            if not policies_path.exists():
                policies_path = None
            
            bundle_data = emit_context_bundle(
                output_path,
                golden_temp,
                drift_temp,
                overview,
                dep_diff,
                config_diff,
                file_changes,
                extra_deltas,
                policies_path
            )
            
            # Clean up temp directory
            try:
                shutil.rmtree(output_path)
                logger.info(f"✅ Cleaned up temp directory: {output_path}")
            except Exception as e_cleanup:
                logger.warning(f"Failed to clean up temp directory {output_path}: {e_cleanup}")
            
            return {
                "status": "success",
                "bundle_data": bundle_data,  # Return dict for DB storage
                "deltas_count": len(bundle_data.get("deltas", [])),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to generate context bundle: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
