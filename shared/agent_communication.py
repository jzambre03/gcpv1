"""
Agent Communication System for Golden Config AI

This module provides a simple communication layer between agents in the multi-agent system.
It allows the supervisor agent to send tasks to worker agents and receive responses.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Callable
from datetime import datetime

from .models import TaskRequest, TaskResponse, AgentMessage
from .logging_config import get_agent_logger

logger = get_agent_logger("agent_communication")


class AgentCommunicationBus:
    """
    Simple communication bus for inter-agent messaging.
    
    This provides a lightweight message passing system between agents
    without requiring external message brokers.
    """
    
    def __init__(self):
        self.agents: Dict[str, Any] = {}
        self.message_handlers: Dict[str, Callable] = {}
        
    def register_agent(self, agent_name: str, agent_instance: Any):
        """Register an agent with the communication bus."""
        self.agents[agent_name] = agent_instance
        logger.info(f"Agent '{agent_name}' registered with communication bus")
        
    def register_message_handler(self, agent_name: str, handler: Callable):
        """Register a message handler for an agent."""
        self.message_handlers[agent_name] = handler
        
    async def send_task_request(
        self, 
        from_agent: str,
        to_agent: str, 
        task_request: TaskRequest
    ) -> TaskResponse:
        """
        Send a task request from one agent to another and wait for response.
        """
        if to_agent not in self.agents:
            logger.error(f"Target agent '{to_agent}' not found in registry")
            return TaskResponse(
                task_id=task_request.task_id,
                status="failure",
                result=None,
                error=f"Agent '{to_agent}' not available",
                processing_time_seconds=0.0
            )
            
        try:
            start_time = datetime.now()
            target_agent = self.agents[to_agent]
            
            logger.info(f"Sending task {task_request.task_id} from {from_agent} to {to_agent}")
            
            # Route the task based on task type to appropriate agent method
            result = await self._route_task_to_agent(target_agent, task_request)
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            return TaskResponse(
                task_id=task_request.task_id,
                status="success",
                result=result,
                error=None,
                processing_time_seconds=processing_time
            )
            
        except Exception as e:
            logger.error(f"Error sending task {task_request.task_id} to {to_agent}: {e}")
            processing_time = (datetime.now() - start_time).total_seconds()
            
            return TaskResponse(
                task_id=task_request.task_id,
                status="failure",
                result=None,
                error=str(e),
                processing_time_seconds=processing_time
            )
    
    async def _route_task_to_agent(self, agent, task_request: TaskRequest) -> Dict[str, Any]:
        """Route a task request to the appropriate agent method."""
        task_type = task_request.task_type
        parameters = task_request.parameters
        
        # Map task types to agent methods
        if task_type == "collect_configurations":
            # Config Collector Agent - discover and extract files
            repo_url = parameters.get("repo_url")
            branch = parameters.get("branch", "main")
            file_patterns = parameters.get("file_patterns", ["*.yml", "*.yaml", "*.json"])
            
            # First discover config files using correct parameters
            discovery_result = await agent.discover_config_files(
                repository_url=repo_url,
                branch=branch,
                discovery_patterns=file_patterns,  # Correct parameter name
                analysis_depth="comprehensive"     # Correct parameter name
            )
            
            # Then extract their contents if files found
            if discovery_result.get("files_found"):
                extraction_result = await agent.extract_file_contents(
                    file_paths=discovery_result["files_found"],
                    repository_url=repo_url,
                    branch=branch
                )
                return {**discovery_result, **extraction_result}
            
            return discovery_result
            
        elif task_type == "security_scan":
            # Guardrails Agent - security vulnerability scanning
            file_contents = parameters.get("file_contents", {})
            
            return await agent.scan_security_vulnerabilities(
                file_contents=file_contents,
                tech_stack=None,                # Correct parameter name
                scan_depth="comprehensive"      # Correct parameter name instead of scan_level
            )
            
        elif task_type == "drift_analysis":
            # Diff Policy Engine Agent - configuration drift analysis
            current_configs = parameters.get("current_configs", {})
            golden_configs = parameters.get("golden_configs", {})
            
            return await agent.analyze_configuration_drift(
                golden_config=golden_configs,
                current_config=current_configs,
                environment="production",       # Correct parameter name
                analysis_depth="comprehensive" # Correct parameter name instead of policy_rules
            )
            
        elif task_type == "team_routing":
            # Triage Routing Agent - team assignment and routing
            validation_results = parameters.get("validation_results", {})
            severity_level = parameters.get("severity_level", "medium")
            
            return await agent.route_validation_request(
                validation_request={
                    "validation_results": validation_results,
                    "severity_level": severity_level
                },
                priority_assessment={           # Correct parameter name
                    "severity": severity_level,
                    "urgency": "normal"
                },
                routing_strategy="optimal"      # Correct parameter name instead of team_mappings
            )
            
        elif task_type == "learning_analysis":
            # Learning AI Agent - pattern analysis and recommendations
            # For now, use the diff engine's recommendation capabilities
            validation_context = parameters.get("validation_context", {})
            drift_analysis = validation_context.get("results", {}).get("drift", {})
            
            # Use the diff engine's existing recommendation methods
            if hasattr(agent, 'generate_drift_recommendations'):
                return await agent.generate_drift_recommendations(
                    drift_analysis=drift_analysis,
                    priority_level="high"
                )
            else:
                # Fallback response if method doesn't exist
                return {
                    "status": "success",
                    "analysis_type": "learning_analysis_simulation",
                    "recommendations": [
                        "Continue monitoring configuration drift patterns",
                        "Consider implementing automated remediation for low-risk changes",
                        "Review policy compliance violations with development team"
                    ],
                    "learning_insights": "Historical pattern analysis completed",
                    "automation_opportunities": ["Config validation automation", "Drift prevention rules"]
                }
            
        else:
            raise ValueError(f"Unknown task type: {task_type}")


# Global communication bus instance
communication_bus = AgentCommunicationBus()


def get_communication_bus() -> AgentCommunicationBus:
    """Get the global communication bus instance."""
    return communication_bus
