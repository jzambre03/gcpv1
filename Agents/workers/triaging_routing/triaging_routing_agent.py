"""
Triaging-Routing Agent - AI-Powered Delta Analysis and Risk Categorization (Database-Only)

This agent uses LLM to analyze and categorize configuration deltas from the Drift Detector.

Responsibilities:
- Fetch context_bundle from database using run_id
- LLM-based analysis of configuration changes
- Risk categorization (HIGH/MEDIUM/LOW/ALLOWED)
- Hard fail detection (critical violations)
- Save llm_output to database (llm_outputs table)

Input: run_id (fetches context_bundle from DB)
Output: Database record in llm_outputs table, no JSON files
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.tools import tool

from shared.config import Config
from shared.models import TaskRequest, TaskResponse
from shared.model_factory import create_worker_model
from shared.db import save_llm_output

from .prompts.llm_format_prompt import build_llm_format_prompt, validate_llm_output

logger = logging.getLogger(__name__)


class TriagingRoutingAgent(Agent):
    """
    Triaging-Routing Agent - AI-Powered Delta Analysis and Risk Categorization
    
    This agent:
    1. Loads context_bundle.json from Drift Detector
    2. Groups deltas by file for batch processing
    3. Uses LLM to analyze and categorize deltas
    4. Generates LLM output format (high/medium/low/allowed_variance)
    5. Saves to llm_output.json
    """

    def __init__(self, config: Optional[Config] = None):
        if config is None:
            config = Config()
        
        system_prompt = self._get_system_prompt()
        
        super().__init__(
            model=create_worker_model(config),
            system_prompt=system_prompt,
            tools=[
                self.load_context_bundle,
                self.analyze_deltas_batch_llm_format,
                self.merge_llm_outputs,
                self.detect_hard_fails,
                self.categorize_risk
            ]
        )
        self.config = config

    def _get_system_prompt(self) -> str:
        return """You are the Triaging-Routing Agent in the Golden Config AI system.

**Your Role:**
Analyze configuration deltas using AI to understand semantic meaning and categorize risk levels.

**Your Responsibilities:**
1. Analyze configuration deltas using LLM to understand semantic meaning
2. Categorize risk levels (HIGH/MEDIUM/LOW/ALLOWED)
3. Detect hard failures (critical violations that must block deployment)
4. Generate LLM output format matching exact schema

**Standard Workflow:**
1. Load context_bundle.json from Drift Detector
2. Group deltas by file for batch processing
3. Analyze each batch with LLM using specialized prompts
4. Merge all LLM outputs into single file
5. Generate llm_output.json with categorized deltas

**Output Format:**
Return LLM output format with:
- high: Critical issues requiring immediate attention
- medium: Moderate risks requiring review
- low: Minor changes, low impact
- allowed_variance: Expected variance (environment-specific)

**Important:**
- Use exact delta IDs from context_bundle
- Preserve locator structure from deltas
- Provide clear "why" or "rationale" for each delta
- Include remediation snippets for high/medium/low items
"""

    def process_task(self, task: TaskRequest) -> TaskResponse:
        """
        Process a triaging task.
        
        Args:
            task: TaskRequest with parameters:
                - run_id: Validation run ID (to fetch context_bundle from DB)
                - environment: Environment name (optional)
                
        Returns:
            TaskResponse with summary data (no file paths)
        """
        start_time = time.time()
        
        try:
            logger.info("=" * 60)
            logger.info(f"🎯 Triaging-Routing processing task: {task.task_id}")
            logger.info("=" * 60)
            
            params = task.parameters
            
            # Extract parameters
            run_id = params.get('run_id')
            environment = params.get('environment', 'production')
            
            if not run_id:
                return TaskResponse(
                    task_id=task.task_id,
                    status="failure",
                    result={},
                    error="Missing required parameter: run_id",
                    processing_time_seconds=time.time() - start_time,
                    metadata={"agent": "triaging_routing"}
                )
            
            # Load context bundle from database
            logger.info(f"\n📂 Loading context bundle from database for run: {run_id}")
            logger.info("-" * 60)
            
            try:
                from shared.db import get_latest_context_bundle
                context_bundle = get_latest_context_bundle(run_id)
                
                if not context_bundle:
                    return TaskResponse(
                        task_id=task.task_id,
                        status="failure",
                        result={},
                        error=f"Context bundle not found in database for run: {run_id}",
                        processing_time_seconds=time.time() - start_time,
                        metadata={"agent": "triaging_routing"}
                    )
                    
            except Exception as e:
                return TaskResponse(
                    task_id=task.task_id,
                    status="failure",
                    result={},
                    error=f"Failed to load context bundle from database: {str(e)}",
                    processing_time_seconds=time.time() - start_time,
                    metadata={"agent": "triaging_routing"}
                )
            
            # Extract data from context bundle
            deltas = context_bundle.get('deltas', [])
            overview = context_bundle.get('overview', {})
            file_changes = context_bundle.get('file_changes', {})
            
            logger.info(f"📦 Context Bundle loaded:")
            logger.info(f"   Total deltas: {len(deltas)}")
            logger.info(f"   File changes: {len(file_changes.get('modified', []))}")
            
            # Check if there are deltas to analyze
            if not deltas:
                logger.warning("No deltas found in context bundle")
                
                # Create empty LLM output (save to DB only)
                empty_llm_output = {
                    "summary": {
                        "total_drifts": 0,
                        "high_risk": 0,
                        "medium_risk": 0,
                        "low_risk": 0,
                        "allowed_variance": 0
                    },
                    "high": [],
                    "medium": [],
                    "low": [],
                    "allowed_variance": [],
                    "environment": environment,
                    "analysis_timestamp": datetime.now().isoformat(),
                    "message": "No deltas detected - environments are in sync"
                }
                
                # Save to database
                try:
                    save_llm_output(run_id, empty_llm_output)
                    logger.info(f"✅ Empty LLM output saved to database (no deltas detected)")
                except Exception as e:
                    logger.error(f"Failed to save LLM output to database: {e}")
                
                return TaskResponse(
                    task_id=task.task_id,
                    status="success",
                    result={
                        "summary": {
                            "total_deltas_analyzed": 0,
                            "high_risk": 0,
                            "medium_risk": 0,
                            "low_risk": 0,
                            "allowed_variance": 0
                        }
                    },
                    error=None,
                    processing_time_seconds=time.time() - start_time,
                    metadata={"agent": "triaging_routing"}
                )
            
            # Group deltas by category for analysis
            config_deltas = [d for d in deltas if d.get('category') in ['config', 'spring_profile']]
            dep_deltas = [d for d in deltas if d.get('category') == 'dependency']
            code_deltas = [d for d in deltas if d.get('category') in ['code_hunk', 'file']]
            
            logger.info(f"   Config deltas: {len(config_deltas)}")
            logger.info(f"   Dependency deltas: {len(dep_deltas)}")
            logger.info(f"   Code deltas: {len(code_deltas)}")
            
            # Focus on config and dependency deltas (most important)
            all_deltas_to_analyze = config_deltas[:30] + dep_deltas[:10]
            
            # Deduplicate deltas
            logger.info(f"\n🔍 Deduplicating {len(all_deltas_to_analyze)} deltas before LLM analysis...")
            logger.info("-" * 60)
            
            seen_deltas = {}
            deduplicated_deltas = []
            
            for delta in all_deltas_to_analyze:
                locator_value = delta.get('locator', {}).get('value', '')
                old_val = str(delta.get('old', ''))
                new_val = str(delta.get('new', ''))
                file = delta.get('file', '')
                
                unique_key = f"{file}:{locator_value}:{old_val}:{new_val}"
                
                if unique_key not in seen_deltas:
                    seen_deltas[unique_key] = delta
                    deduplicated_deltas.append(delta)
                else:
                    logger.info(f"   🔄 Skipping duplicate delta: {file}:{locator_value}")
            
            logger.info(f"   ✅ Deduplicated: {len(all_deltas_to_analyze)} → {len(deduplicated_deltas)} deltas")
            
            # Group deltas by file and split large files into smaller batches
            deltas_by_file = {}
            for delta in deduplicated_deltas:
                file = delta.get('file', 'unknown')
                if file not in deltas_by_file:
                    deltas_by_file[file] = []
                deltas_by_file[file].append(delta)
            
            # Split large file batches into smaller chunks (max 10 deltas per batch)
            final_batches = []
            for file, file_deltas in deltas_by_file.items():
                if len(file_deltas) <= 10:
                    final_batches.append((file, file_deltas))
                else:
                    # Split into chunks of 10
                    for i in range(0, len(file_deltas), 10):
                        chunk = file_deltas[i:i+10]
                        batch_name = f"{file}_batch_{i//10 + 1}"
                        final_batches.append((batch_name, chunk))
            
            logger.info(f"\n📦 Grouped {len(deduplicated_deltas)} deltas into {len(final_batches)} batches for analysis")
            logger.info("-" * 60)
            
            # Analyze each batch with LLM
            llm_outputs = []
            
            for batch_name, batch_deltas in final_batches:
                logger.info(f"\n  📄 Analyzing {batch_name} ({len(batch_deltas)} deltas)")
                
                # Get environment from overview
                environment = overview.get('environment', 'production')
                
                try:
                    # Batch analyze with LLM format output
                    llm_format = asyncio.run(self.analyze_deltas_batch_llm_format(
                        file=batch_name,
                        deltas=batch_deltas,
                        environment=environment,
                        overview=overview
                    ))
                    
                    llm_outputs.append(llm_format)
                    
                    logger.info(f"     ✅ LLM format: High={len(llm_format.get('high', []))}, "
                               f"Medium={len(llm_format.get('medium', []))}, "
                               f"Low={len(llm_format.get('low', []))}, "
                               f"Allowed={len(llm_format.get('allowed_variance', []))}")
                    
                except Exception as e:
                    logger.warning(f"     ❌ LLM format analysis failed for {batch_name}: {e}")
                    # Use fallback categorization
                    llm_format = self._fallback_llm_categorization(batch_deltas, batch_name)
                    llm_outputs.append(llm_format)
            
            # Merge all LLM outputs into single LLM output
            logger.info(f"\n📦 Generating final LLM output...")
            logger.info("-" * 60)
            
            merged_llm_output = self.merge_llm_outputs(llm_outputs, overview, context_bundle)
            
            # Save to database only (no JSON files)
            try:
                save_llm_output(run_id, merged_llm_output)
                logger.info(f"✅ LLM output saved to database for run: {run_id}")
            except Exception as e:
                logger.error(f"Failed to save LLM output to database: {e}")
                return TaskResponse(
                    task_id=task.task_id,
                    status="failure",
                    result={},
                    error=f"Failed to save LLM output to database: {str(e)}",
                    processing_time_seconds=time.time() - start_time,
                    metadata={"agent": "triaging_routing"}
                )
            
            logger.info(f"   Total items: {len(merged_llm_output['high']) + len(merged_llm_output['medium']) + len(merged_llm_output['low']) + len(merged_llm_output['allowed_variance'])}")
            
            logger.info("\n✅ Triaging-Routing completed!")
            logger.info("=" * 60)
            
            return TaskResponse(
                task_id=task.task_id,
                status="success",
                result={
                    "summary": {
                        "total_deltas_analyzed": len(deduplicated_deltas),
                        "high_risk": len(merged_llm_output.get('high', [])),
                        "medium_risk": len(merged_llm_output.get('medium', [])),
                        "low_risk": len(merged_llm_output.get('low', [])),
                        "allowed_variance": len(merged_llm_output.get('allowed_variance', []))
                    }
                },
                error=None,
                processing_time_seconds=time.time() - start_time,
                metadata={
                    "agent": "triaging_routing",
                    "deltas_analyzed": len(deduplicated_deltas)
                }
            )
            
        except Exception as e:
            logger.exception(f"❌ Triaging-Routing task processing failed: {e}")
            return TaskResponse(
                task_id=task.task_id,
                status="failure",
                result={},
                error=str(e),
                processing_time_seconds=time.time() - start_time,
                metadata={"agent": "triaging_routing"}
            )

    @tool
    def load_context_bundle(self, run_id: str) -> Dict[str, Any]:
        """
        Load context bundle from database.
        
        Args:
            run_id: Validation run ID
            
        Returns:
            Loaded context bundle data from database
        """
        logger.info(f"Loading context bundle from database for run: {run_id}")
        
        try:
            from shared.db import get_latest_context_bundle
            context_bundle = get_latest_context_bundle(run_id)
            
            if not context_bundle:
                return {
                    "status": "error",
                    "error": f"Context bundle not found for run: {run_id}"
                }
            
            return {
                "status": "success",
                "deltas": context_bundle.get('deltas', []),
                "overview": context_bundle.get('overview', {}),
                "file_changes": context_bundle.get('file_changes', {}),
                "dependencies": context_bundle.get('dependencies', {}),
                "configs": context_bundle.get('configs', {})
            }
            
        except Exception as e:
            logger.error(f"Failed to load context bundle from database: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    @tool
    async def analyze_deltas_batch_llm_format(
        self,
        file: str,
        deltas: list,
        environment: str = "production",
        overview: dict = None
    ) -> dict:
        """
        Batch analyze ALL deltas in a single file with one AI call - LLM OUTPUT FORMAT.
        
        This method returns the LLM output format DIRECTLY (high/medium/low/allowed_variance)
        instead of the nested delta_analyses structure.
        
        Args:
            file: File path
            deltas: List of all deltas in this file
            environment: Target environment (production, staging, dev, qa)
            overview: Repository overview context
        
        Returns:
            Dict with high, medium, low, allowed_variance arrays (LLM format)
        """
        logger.info(f"     📋 Building LLM format prompt for {len(deltas)} deltas...")
        
        # Get policies from overview
        policies = overview.get('policies', {}) if overview else {}
        
        # Build prompt using template
        prompt = build_llm_format_prompt(
            file=file,
            deltas=deltas,
            environment=environment,
            policies=policies
        )
        
        logger.info(f"     🤖 Calling AI for LLM format analysis (max_tokens=8000)...")
        
        # Call AI with LLM format prompt
        messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        
        ai_response = ""
        async for event in self.model.stream(messages, max_tokens=8000):
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"].get("delta", {})
                if "text" in delta:
                    ai_response += delta["text"]
        
        logger.info(f"     ✅ Received AI response ({len(ai_response)} chars)")
        
        # Parse JSON response with robust error handling
        try:
            result = self._parse_ai_json_response(ai_response)
            
            # Validate LLM output structure
            if not validate_llm_output(result):
                logger.warning(f"     ⚠️ LLM output validation failed, missing required fields")
                raise ValueError("Invalid LLM output structure")
            
            logger.info(f"     ✅ Valid LLM format: High={len(result.get('high', []))}, "
                       f"Medium={len(result.get('medium', []))}, "
                       f"Low={len(result.get('low', []))}, "
                       f"Allowed={len(result.get('allowed_variance', []))}")
            
            return result
            
        except Exception as e:
            logger.error(f"     ❌ Failed to parse LLM output: {e}")
            logger.error(f"     Raw response (first 500 chars): {ai_response[:500]}")
            raise

    @tool
    def merge_llm_outputs(
        self,
        llm_outputs: list,
        overview: dict,
        context_bundle: dict
    ) -> dict:
        """
        Merge LLM outputs from multiple files into single LLM output with summary statistics.
        
        Args:
            llm_outputs: List of per-file/batch LLM outputs
            overview: Context bundle overview
            context_bundle: Full context bundle for metadata
        
        Returns:
            Single merged LLM output with summary statistics
        """
        logger.info(f"📦 Merging {len(llm_outputs)} LLM outputs...")
        
        # Initialize merged structure - EXACT FORMAT
        merged = {
            "high": [],
            "medium": [],
            "low": [],
            "allowed_variance": []
        }
        
        # Merge all buckets from all files
        for output in llm_outputs:
            merged["high"].extend(output.get("high", []))
            merged["medium"].extend(output.get("medium", []))
            merged["low"].extend(output.get("low", []))
            merged["allowed_variance"].extend(output.get("allowed_variance", []))
        
        # Sort items within each bucket (by file, then by id)
        def sort_key(item):
            return (item.get("file", ""), item.get("id", ""))
        
        merged["high"] = sorted(merged["high"], key=sort_key)
        merged["medium"] = sorted(merged["medium"], key=sort_key)
        merged["low"] = sorted(merged["low"], key=sort_key)
        merged["allowed_variance"] = sorted(merged["allowed_variance"], key=sort_key)
        
        # Calculate summary statistics
        all_merged_items = (
            merged.get('high', []) + 
            merged.get('medium', []) + 
            merged.get('low', []) + 
            merged.get('allowed_variance', [])
        )
        files_with_drift = len(set(item.get("file", "") for item in all_merged_items if item.get("file")))
        
        total_config_files = overview.get("total_files", 0)
        if not total_config_files:
            total_config_files = overview.get("candidate_files", 0) + len(context_bundle.get("file_changes", {}).get("removed", []))
        
        total_drifts = len(all_merged_items)
        
        # Add summary statistics and metadata for DB save compatibility
        merged["summary"] = {
            "total_config_files": total_config_files,
            "files_with_drift": files_with_drift,
            "total_drifts": total_drifts,
            "high_risk": len(merged["high"]),
            "medium_risk": len(merged["medium"]),
            "low_risk": len(merged["low"]),
            "allowed_variance": len(merged["allowed_variance"])
        }
        
        # Add meta and overview for save_llm_output compatibility
        merged["meta"] = context_bundle.get("meta", {})
        merged["overview"] = {
            "total_files": total_config_files,
            "drifted_files": files_with_drift,
            "total_deltas": total_drifts
        }
        
        logger.info(f"✅ Merged LLM output with summary:")
        logger.info(f"   📊 Summary: {total_config_files} config files, {files_with_drift} with drift, {total_drifts} total drifts")
        logger.info(f"   🎯 Risk Distribution: High={len(merged['high'])}, Medium={len(merged['medium'])}, Low={len(merged['low'])}, Allowed={len(merged['allowed_variance'])}")
        
        return merged

    @tool
    def detect_hard_fails(self, deltas: list) -> List[Dict[str, Any]]:
        """
        Detect hard failures (critical violations that must block deployment).
        
        Args:
            deltas: List of deltas to check
            
        Returns:
            List of hard fail deltas
        """
        hard_fails = []
        
        for delta in deltas:
            policy_tag = delta.get('policy', {}).get('tag', '') if isinstance(delta.get('policy'), dict) else ''
            new_value = str(delta.get('new', '')).lower()
            old_value = str(delta.get('old', '')).lower()
            
            # Check for invariant breaches
            if policy_tag == 'invariant_breach':
                hard_fails.append(delta)
                continue
            
            # Check for security issues
            if any(keyword in new_value for keyword in ['password', 'secret', 'key', 'token', 'credential']):
                if old_value != new_value:
                    hard_fails.append(delta)
                    continue
            
            # Check for disabled security features
            if any(keyword in new_value for keyword in ['ssl=false', 'tls=false', 'security=false', 'auth=false']):
                hard_fails.append(delta)
                continue
        
        return hard_fails

    @tool
    def categorize_risk(self, deltas: list) -> Dict[str, List[Dict[str, Any]]]:
        """
        Categorize risk levels (HIGH/MEDIUM/LOW) based on simple rules.
        
        Args:
            deltas: List of deltas to categorize
            
        Returns:
            Dict with high, medium, low lists
        """
        categorized = {
            "high": [],
            "medium": [],
            "low": []
        }
        
        for delta in deltas:
            policy_tag = delta.get('policy', {}).get('tag', '') if isinstance(delta.get('policy'), dict) else ''
            new_value = str(delta.get('new', '')).lower()
            
            # High risk: policy violations or security changes
            if policy_tag == 'invariant_breach' or any(keyword in new_value for keyword in ['password', 'secret', 'key', 'token']):
                categorized["high"].append(delta)
            # Medium risk: network or dependency changes
            elif any(keyword in new_value for keyword in ['port', 'host', 'url', 'endpoint', 'dependency']):
                categorized["medium"].append(delta)
            # Low risk: everything else
            else:
                categorized["low"].append(delta)
        
        return categorized

    def _parse_ai_json_response(self, ai_response):
        """Robust JSON parsing with multiple fallback strategies"""
        if not ai_response.strip():
            raise json.JSONDecodeError("Empty AI response", ai_response, 0)
        
        # Strategy 1: Try to find complete JSON block
        start_idx = ai_response.find('{')
        end_idx = ai_response.rfind('}') + 1
        if start_idx >= 0 and end_idx > start_idx:
            json_str = ai_response[start_idx:end_idx]
            try:
                result = json.loads(json_str)
                return result
            except json.JSONDecodeError as e:
                logger.warning(f"     ⚠️ JSON parsing failed (strategy 1): {e}")
        
        # Strategy 2: Try to fix common JSON issues
        try:
            cleaned = ai_response[ai_response.find('{'):ai_response.rfind('}')+1]
            cleaned = cleaned.replace('\n', ' ').replace('\r', ' ')
            cleaned = cleaned.replace('},}', '}}')
            cleaned = cleaned.replace(',}', '}')
            cleaned = cleaned.replace(',]', ']')
            
            result = json.loads(cleaned)
            return result
        except json.JSONDecodeError as e:
            logger.warning(f"     ⚠️ JSON parsing failed (strategy 2): {e}")
        
        # Strategy 3: Create minimal valid JSON
        logger.warning(f"     ⚠️ All JSON parsing strategies failed, creating minimal response")
        return {
            "high": [],
            "medium": [],
            "low": [],
            "allowed_variance": []
        }

    def _fallback_llm_categorization(self, deltas: list, file: str) -> dict:
        """
        Fallback: Simple rule-based categorization in EXACT LLM format when AI fails.
        
        Args:
            deltas: List of deltas to categorize
            file: File path
        
        Returns:
            LLM format output (high/medium/low/allowed_variance)
        """
        logger.info(f"     🔄 Using fallback categorization for {len(deltas)} deltas")
        
        result = {
            "high": [],
            "medium": [],
            "low": [],
            "allowed_variance": []
        }
        
        for delta in deltas:
            delta_id = delta.get('id', 'unknown')
            locator = delta.get('locator', {})
            old_val = str(delta.get('old', ''))
            new_val = str(delta.get('new', ''))
            policy_tag = delta.get('policy', {}).get('tag', '') if isinstance(delta.get('policy'), dict) else ''
            
            # Build item in LLM format
            item = {
                "id": delta_id,
                "file": file,
                "locator": locator,
                "why": f"Configuration change from {old_val} to {new_val}",
                "remediation": {
                    "snippet": old_val  # Suggest reverting to old value
                }
            }
            
            # Categorize based on simple rules
            if policy_tag == 'invariant_breach' or any(kw in new_val.lower() for kw in ['password', 'secret', 'key', 'token']):
                result["high"].append(item)
            elif policy_tag == 'allowed_variance':
                result["allowed_variance"].append({
                    "id": delta_id,
                    "file": file,
                    "locator": locator,
                    "rationale": "Environment-specific configuration difference"
                })
            elif any(kw in new_val.lower() for kw in ['port', 'host', 'url', 'endpoint']):
                result["medium"].append(item)
            else:
                result["low"].append(item)
        
        return result
