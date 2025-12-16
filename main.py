#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Golden Config AI - Multi-Agent System Main Server

This server orchestrates the complete multi-agent validation workflow:
- Supervisor Agent coordinates the pipeline
- Config Collector Agent fetches Git diffs
- Diff Policy Engine Agent analyzes with AI

Server configuration via environment variables (defaults to localhost:3000).
Set HOST, PORT, and BASE_URL in .env to customize.
"""

import uvicorn
import json
import os
import sys
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

# Setup logging
logger = logging.getLogger(__name__)

# Fix encoding for Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Import database functions
from shared.db import (
    get_run_by_id, get_all_validation_runs,
    get_context_bundle, get_llm_output, get_policy_validation,
    get_certification, get_report, get_aggregated_results,
    # NEW: Services configuration
    get_all_services, get_service_by_id, add_service, init_db
)

# Strands agent system imports
from shared.config import Config
from Agents.Supervisor.supervisor_agent import run_validation


# Setup templates directory
templates_dir = Path(__file__).parent / "api" / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Initialize FastAPI app
app = FastAPI(
    title="Golden Config AI - Multi-Agent System",
    description="Complete Configuration Drift Analysis with Supervisor + Worker Agents",
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Load default values from environment
config = Config()


# Default config file paths for sparse checkout (config-only branches)
# These patterns match what drift_v1.py classifies as "config" files (line 63)
# Excludes .json and .xml as per user request
DEFAULT_CONFIG_PATHS = [
    "*.yml",                   # YAML config files
    "*.yaml",                  # YAML config files
    "*.properties",            # Properties files
    "*.toml",                  # TOML config files
    "*.ini",                   # INI config files
    "*.cfg",                   # Configuration files
    "*.conf",                  # Configuration files
    "*.config",                # Configuration files
    "Dockerfile",              # Docker configuration
    "docker-compose.yml",      # Docker Compose
    ".env.example",            # Environment template
    # Build files (also analyzed for config changes)
    "pom.xml",                 # Maven build file
    "build.gradle",            # Gradle build file
    "build.gradle.kts",        # Gradle Kotlin build file
    "settings.gradle",         # Gradle settings
    "settings.gradle.kts",     # Gradle Kotlin settings
    "requirements.txt",        # Python requirements (excluded package.json)
    "pyproject.toml",          # Python project file
    "go.mod",                  # Go module file
]

# ============================================================================
# SERVICE CONFIGURATION - Load from Database
# ============================================================================

def load_services_from_db() -> Dict[str, Any]:
    """
    Load services configuration from database.
    Only loads services that have golden branches (i.e., services with config files).
    """
    try:
        # Only load services with golden branches (filters out services without config files)
        services_list = get_all_services(active_only=True, with_branches_only=True)
        services_dict = {}
        
        for service in services_list:
            service_id = service['service_id']
            services_dict[service_id] = {
                "name": service['service_name'],
                "repo_url": service['repo_url'],
                "main_branch": service['main_branch'],
                "environments": service['environments'],
                "config_paths": service['config_paths'] or DEFAULT_CONFIG_PATHS,
                "description": service.get('description'),
                "metadata": service.get('metadata', {})
            }
        
        return services_dict
    except Exception as e:
        logger.warning(f"⚠️ Could not load services from database: {e}")
        logger.warning("⚠️ Using empty services config. Please add services to database.")
        return {}


def initialize_services_display():
    """
    Display services loaded from database.
    Services are managed via VSAT Master Config system.
    Only shows services with golden branches (services with config files).
    """
    try:
        # Only show services with golden branches
        services_list = get_all_services(active_only=True, with_branches_only=True)
        
        if not services_list:
            logger.info("ℹ️  No services with golden branches in database")
            logger.info("💡 To add services:")
            logger.info("   1. Add VSATs to config/vsat_master.yaml")
            logger.info("   2. Services will be automatically synced from GitLab")
            logger.info("   3. Or use: python scripts/migrate_add_services_table.py")
            logger.info("   ⚠️  Note: Services without config files are stored but not displayed")
            return
        
        print(f"🏢 Services Loaded from Database (with config files):")
        for service in services_list:
            print(f"   {service['service_id']}: {service['service_name']}")
            print(f"      Repo: {service['repo_url']}")
            print(f"      Main Branch: {service['main_branch']}")
            print(f"      Environments: {', '.join(service['environments'])}")
        print()
    except Exception as e:
        logger.error(f"❌ Error loading services: {e}")


# Initialize database and load services
init_db()
SERVICES_CONFIG = load_services_from_db()
initialize_services_display()

# Set defaults from first service for backward compatibility (if services exist)
# Note: These are only used for legacy endpoints - each service has its own URL
DEFAULT_REPO_URL = os.getenv("DEFAULT_REPO_URL", 
                             list(SERVICES_CONFIG.values())[0]["repo_url"] if SERVICES_CONFIG else "https://gitlab.example.com/org/golden_config.git")
DEFAULT_MAIN_BRANCH = os.getenv("DEFAULT_MAIN_BRANCH", 
                                list(SERVICES_CONFIG.values())[0]["main_branch"] if SERVICES_CONFIG else "main")
DEFAULT_ENVIRONMENT = os.getenv("DEFAULT_ENVIRONMENT", 
                               list(SERVICES_CONFIG.values())[0]["environments"][0] if SERVICES_CONFIG else "prod")

if SERVICES_CONFIG:
    print(f"🔧 Legacy Default Configuration (from {list(SERVICES_CONFIG.keys())[0]}):")
    print(f"   DEFAULT_REPO_URL: {DEFAULT_REPO_URL}")
    print(f"   DEFAULT_MAIN_BRANCH: {DEFAULT_MAIN_BRANCH}")
    print(f"   DEFAULT_ENVIRONMENT: {DEFAULT_ENVIRONMENT}")
    print(f"   ⚠️  Note: Each service uses its own configured URL and environments")
    print()

# Request models
class ValidationRequest(BaseModel):
    """Request for configuration drift validation"""
    repo_url: str = Field(
        default=DEFAULT_REPO_URL,
        description="GitLab repository URL (legacy default - each service has its own URL)"
    )
    main_branch: str = Field(
        default=DEFAULT_MAIN_BRANCH,
        description="Main branch name (source of current configs)"
    )
    environment: str = Field(
        default=DEFAULT_ENVIRONMENT,
        description="Environment to validate (prod, dev, qa, staging)"
    )
    target_folder: str = Field(
        default="",
        description="Optional: specific folder to analyze (empty = entire repo)"
    )
    project_id: str = Field(
        default="config-validation",
        description="Project identifier"
    )
    mr_iid: str = Field(
        default="auto",
        description="Merge request ID or validation identifier"
    )
    
    @field_validator('repo_url')
    @classmethod
    def validate_repo_url(cls, v):
        if not v.startswith(('http://', 'https://')):
            raise ValueError('repo_url must be a valid HTTP/HTTPS URL')
        return v


class QuickAnalysisRequest(BaseModel):
    """Quick analysis with default settings"""
    pass


class InferenceRequest(BaseModel):
    """Simple inference API request with service name and environment"""
    service_name: str = Field(
        description="Service identifier (e.g., 'cxp_ptg_adapter')"
    )
    environment: str = Field(
        description="Environment to analyze (e.g., 'prod', 'alpha', 'beta1', 'beta2')"
    )
    
    @field_validator('service_name')
    @classmethod
    def validate_service_name(cls, v):
        if not v or not v.strip():
            raise ValueError('service_name cannot be empty')
        return v.strip()
    
    @field_validator('environment')
    @classmethod
    def validate_environment(cls, v):
        if not v or not v.strip():
            raise ValueError('environment cannot be empty')
        return v.strip().lower()


# Global state
latest_results: Optional[Dict[str, Any]] = None
validation_in_progress: bool = False


@app.get("/", response_class=HTMLResponse)
async def serve_ui(request: Request):
    """Serve the services overview dashboard"""
    return templates.TemplateResponse("overview.html", {"request": request})


@app.get("/branch-environment", response_class=HTMLResponse)
async def serve_branch_environment(request: Request):
    """Serve the branch & environment tracking page"""
    print("🌿 Serving Branch & Environment tracking page")
    print(f"🔍 Request URL: {request.url}")
    print(f"🔍 Query params: {dict(request.query_params)}")
    
    try:
        return templates.TemplateResponse("branch_env.html", {"request": request})
    except Exception as e:
        print(f"❌ Template error: {e}")
        print(f"📁 Templates directory: {templates_dir}")
        
        # Check if template file exists
        template_path = Path(__file__).parent / "api" / "templates" / "branch_env.html"
        print(f"🔍 Looking for template at: {template_path}")
        print(f"📄 File exists: {template_path.exists()}")
        
        # Fallback: serve the HTML content directly
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                content = f.read()
                print("✅ Successfully read template file directly")
                return HTMLResponse(content=content)
        except Exception as e2:
            print(f"❌ File read error: {e2}")
            # Return a basic HTML page as last resort
            return HTMLResponse(content=f"""
            <!DOCTYPE html>
            <html>
            <head><title>Branch Environment - Error</title></head>
            <body>
                <h1>Branch Environment Page</h1>
                <p>Error loading page: {str(e2)}</p>
                <p>Template path: {template_path}</p>
                <button onclick="window.history.back()">← Back</button>
            </body>
            </html>
            """)


# Legacy route removed - use service-specific dashboards instead
# Each service now has its own dashboard at /service/{service_id}


@app.get("/api/info")
async def api_info():
    """API information endpoint"""
    return {
        "service": "Golden Config AI - Multi-Agent System",
        "version": "2.0.0",
        "status": "running",
        "architecture": "supervisor_orchestration",
        "agents": {
            "supervisor": "Orchestrates the validation workflow",
            "config_collector": "Fetches Git diffs and analyzes changes",
            "diff_policy_engine": "AI-powered drift analysis and policy validation"
        },
        "communication": "file_based",
        "legacy_default_repo": DEFAULT_REPO_URL,
        "legacy_default_config": {
            "main_branch": DEFAULT_MAIN_BRANCH,
            "environment": DEFAULT_ENVIRONMENT
        },
        "note": "Each service has its own configured repository and environments",
        "endpoints": {
            "ui": "GET /",
            "branch_environment": "GET /branch-environment",
            "validate": "POST /api/validate",
            "quick_analyze": "POST /api/analyze/quick",
            "latest_results": "GET /api/latest-results",
            "validation_status": "GET /api/validation-status",
            "config": "GET /api/config",
            "llm_output": "GET /api/llm-output",
            "health": "GET /health"
        }
    }


@app.get("/api/validation-status")
async def validation_status():
    """Check if validation is in progress"""
    global validation_in_progress
    
    return {
        "in_progress": validation_in_progress,
        "has_results": latest_results is not None,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.post("/api/validate")
async def validate_configuration(request: ValidationRequest, background_tasks: BackgroundTasks):
    """
    Run complete multi-agent validation workflow.
    
    This orchestrates:
    1. Supervisor Agent - Creates validation run and coordinates workflow
    2. Config Collector Agent - Fetches Git diffs from repository
    3. Diff Policy Engine Agent - AI-powered drift analysis
    
    Returns file paths to analysis results.
    """
    global validation_in_progress, latest_results
    
    if validation_in_progress:
        raise HTTPException(
            status_code=409,
            detail="Validation already in progress. Please wait for completion."
        )
    
    print("=" * 80)
    print("🚀 MULTI-AGENT VALIDATION REQUEST")
    print("=" * 80)
    print(f"📦 Repository: {request.repo_url}")
    print(f"🌿 Main Branch: {request.main_branch}")
    print(f"🌍 Environment: {request.environment}")
    print(f"📁 Target Folder: {request.target_folder or 'entire repository'}")
    print(f"🆔 Project ID: {request.project_id}")
    print(f"🔢 MR/ID: {request.mr_iid}")
    print("=" * 80)
    
    try:
        validation_in_progress = True
        start_time = datetime.now()
        
        # Generate MR ID if auto
        mr_iid = request.mr_iid
        if mr_iid == "auto":
            mr_iid = f"val_{int(datetime.now().timestamp())}"
        
        print("\n🤖 Starting Supervisor Agent orchestration...")
        print("   ├─ Supervisor Agent: Coordinates workflow")
        print("   ├─ Config Collector Agent: Fetches Git diffs")
        print("   └─ Diff Policy Engine Agent: AI-powered analysis")
        print()
        
        # Run validation through supervisor
        result = run_validation(
            project_id=request.project_id,
            mr_iid=mr_iid,
            repo_url=request.repo_url,
            main_branch=request.main_branch,
            environment=request.environment,
            target_folder=request.target_folder
        )
        
        # Calculate execution time
        execution_time = (datetime.now() - start_time).total_seconds()
        
        print("\n" + "=" * 80)
        print("✅ VALIDATION COMPLETED")
        print("=" * 80)
        print(f"⏱️  Execution Time: {execution_time:.2f}s")
        print(f"🆔 Run ID: {result.get('run_id', 'N/A')}")
        print(f"📊 Verdict: {result.get('verdict', 'N/A')}")
        print("=" * 80)
        
        # Try to load enhanced analysis data if available
        enhanced_data = None
        validation_run_id = result.get('run_id')
        try:
            # Try to get enhanced analysis data from database
            if validation_run_id:
                from shared.db import get_aggregated_results
                aggregated = get_aggregated_results(validation_run_id)
                if aggregated:
                    enhanced_data = aggregated
                    print(f"✅ Loaded enhanced analysis data from database")
        except Exception as e:
            print(f"⚠️ Could not load enhanced analysis data: {e}")
        
        # Prepare response with enhanced data if available
        validation_result = result
        if enhanced_data:
            # Merge enhanced data into validation result
            validation_result = {
                **result,
                "enhanced_data": enhanced_data,
                "clusters": enhanced_data.get("clusters", []),
                "analyzed_deltas": enhanced_data.get("analyzed_deltas_with_ai", []),
                "total_clusters": len(enhanced_data.get("clusters", [])),
                "policy_violations": enhanced_data.get("policy_violations", []),
                "policy_violations_count": len(enhanced_data.get("policy_violations", [])),
                "overall_risk_level": enhanced_data.get("overall_risk_level", "unknown"),
                "verdict": enhanced_data.get("verdict", "UNKNOWN"),
                "environment": enhanced_data.get("environment", "unknown"),
                "critical_violations": len([v for v in enhanced_data.get("policy_violations", []) if v.get('severity') == 'critical']),
                "high_violations": len([v for v in enhanced_data.get("policy_violations", []) if v.get('severity') == 'high'])
            }
        
        response = {
            "status": "success",
            "architecture": "multi_agent_supervisor",
            "agents_used": ["supervisor", "config_collector", "diff_policy_engine"],
            "communication_method": "file_based",
            "validation_result": validation_result,
            "execution_time_seconds": execution_time,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_params": {
                "repo_url": request.repo_url,
                "main_branch": request.main_branch,
                "environment": request.environment,
                "target_folder": request.target_folder or "/"
            }
        }
        
        latest_results = response
        
        return response
        
    except Exception as e:
        print("\n" + "=" * 80)
        print("❌ VALIDATION FAILED")
        print("=" * 80)
        print(f"Error: {str(e)}")
        print("=" * 80)
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")
    
    finally:
        validation_in_progress = False


@app.post("/api/analyze/quick")
async def quick_analyze(request: QuickAnalysisRequest):
    """
    Quick analysis with default settings from environment variables.
    
    This is a convenience endpoint that uses predefined repository and main branch from .env
    """
    print("🚀 Quick Analysis Request (using defaults from .env)")
    
    default_request = ValidationRequest(
        repo_url=DEFAULT_REPO_URL,
        main_branch=DEFAULT_MAIN_BRANCH,
        environment=DEFAULT_ENVIRONMENT,
        target_folder="",
        project_id="quick_analysis",
        mr_iid="quick_analysis"
    )
    
    # Use background tasks to avoid timeout
    from fastapi import BackgroundTasks
    background_tasks = BackgroundTasks()
    
    return await validate_configuration(default_request, background_tasks)


@app.get("/api/latest-results")
async def get_latest_results():
    """Get the latest validation results"""
    if latest_results:
        return latest_results
    else:
        raise HTTPException(status_code=404, detail="No validation results available yet")


@app.get("/api/sample-data")
async def get_sample_data():
    """
    Trigger a quick analysis for sample data.
    This is for UI compatibility with the old agent_analysis_server.
    """
    return await quick_analyze(QuickAnalysisRequest())


@app.post("/api/analyze/agent")
async def analyze_agent_compat(request: Dict[str, Any]):
    """
    Compatibility endpoint for UI that expects /api/analyze/agent.
    Maps to the new validation endpoint.
    """
    print("🔄 Legacy endpoint called (/api/analyze/agent), redirecting to new validation...")
    
    validation_request = ValidationRequest(
        repo_url=request.get("repo_url", DEFAULT_REPO_URL),
        main_branch=request.get("main_branch", DEFAULT_MAIN_BRANCH),
        environment=request.get("environment", DEFAULT_ENVIRONMENT),
        target_folder=request.get("target_folder", ""),
        project_id=request.get("project_id", "config-validation"),
        mr_iid=request.get("mr_iid", "auto")
    )
    
    from fastapi import BackgroundTasks
    background_tasks = BackgroundTasks()
    
    return await validate_configuration(validation_request, background_tasks)


@app.get("/api/agent-status")
async def agent_status():
    """Check agent system status"""
    try:
        config = Config()
        return {
            "status": "initialized",
            "architecture": "multi_agent_supervisor",
            "agents": {
                "supervisor": {
                    "status": "ready",
                    "description": "Orchestrates validation workflow",
                    "model": config.bedrock_model_id
                },
                "config_collector": {
                    "status": "ready",
                    "description": "Fetches Git diffs",
                    "model": config.bedrock_worker_model_id
                },
                "diff_policy_engine": {
                    "status": "ready",
                    "description": "AI-powered drift analysis",
                    "model": config.bedrock_worker_model_id
                }
            },
            "communication": "file_based",
            "output_location": "config_data/",
            "message": "All agents ready for validation"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": "Agent initialization failed"
        }


@app.get("/api/config")
async def get_config():
    """Get legacy environment configuration for UI"""
    return {
        "legacy_repo_url": DEFAULT_REPO_URL,
        "legacy_main_branch": DEFAULT_MAIN_BRANCH,
        "legacy_environment": DEFAULT_ENVIRONMENT,
        "note": "These are legacy defaults - each service has its own configured repository and environments",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/llm-output")
async def get_llm_output_endpoint():
    """Get the latest LLM output in adjudicator format"""
    try:
        # Get the most recent validation run
        all_runs = get_all_validation_runs()
        if not all_runs:
            raise HTTPException(status_code=404, detail="No validation runs found")
        
        # Get LLM output from the most recent run
        run_id = all_runs[0]['run_id']
        llm_data = get_llm_output(run_id)
        
        if llm_data:
            return {
                "status": "success",
                "run_id": run_id,
                "data": llm_data
            }
        else:
            raise HTTPException(status_code=404, detail="No LLM output found for latest run")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read LLM output from database: {str(e)}")


@app.get("/api/services")
async def get_services():
    """Get configured services with their status (loaded from database)"""
    # Reload services from database to get latest changes
    global SERVICES_CONFIG
    SERVICES_CONFIG = load_services_from_db()
    
    services = []
    
    for service_id, config in SERVICES_CONFIG.items():
        # Get last validation for this service
        last_result = get_last_service_result(service_id)
        
        # Determine status based on result
        status = "healthy"
        issues_count = 0
        
        if last_result:
            # Debug: Print what we have
            print(f"🔍 Debug: last_result keys for {service_id}: {list(last_result.keys())}")
            
            # Navigate to the correct nested structure: result → validation_result → llm_output → summary
            validation_result = last_result.get("validation_result", {})
            
            # Count ALL drifts from LLM output summary (high + medium + low + allowed variance)
            if validation_result and "llm_output" in validation_result:
                llm_output = validation_result["llm_output"]
                print(f"🔍 Debug: Found llm_output with keys: {list(llm_output.keys())}")
                
                llm_summary = llm_output.get("summary", {})
                print(f"🔍 Debug: llm_summary: {llm_summary}")
                
                issues_count = llm_summary.get("total_drifts", 0)  # Count all drifts
                print(f"✅ Debug: Found {issues_count} total drifts for {service_id}")
                
                # Determine status based on risk distribution
                high_risk = llm_summary.get("high_risk", 0)
                medium_risk = llm_summary.get("medium_risk", 0)
                
                if high_risk > 0:
                    status = "critical"
                elif medium_risk > 0:
                    status = "warning"
                elif issues_count > 0:
                    status = "healthy"  # Only low risk or allowed variance
            # Fallback: Try direct llm_output (old structure)
            elif "llm_output" in last_result and last_result["llm_output"]:
                llm_output = last_result["llm_output"]
                llm_summary = llm_output.get("summary", {})
                issues_count = llm_summary.get("total_drifts", 0)
                print(f"✅ Debug: Found {issues_count} drifts (direct llm_output)")
            # Fallback to enhanced_data structure
            elif "enhanced_data" in last_result:
                enhanced = last_result["enhanced_data"]
                issues_count = enhanced.get("policy_violations_count", 0)
                if issues_count > 0:
                    status = "warning" if enhanced.get("overall_risk_level") in ["medium", "high"] else "healthy"
                print(f"✅ Debug: Found {issues_count} issues (enhanced_data)")
            else:
                print(f"⚠️ Debug: No recognized data structure in last_result for {service_id}")
                print(f"    Available keys: {list(last_result.keys())}")
        
        services.append({
            "id": service_id,
            "name": config["name"],
            "status": status,
            "last_check": last_result.get("timestamp") if last_result else None,
            "issues": issues_count,
            "repo_url": config["repo_url"],
            "main_branch": config["main_branch"],
            "environments": config["environments"],
            "total_environments": len(config["environments"])
        })
    
    return {
        "services": services,
        "total_services": len(services),
        "active_issues": sum(s["issues"] for s in services),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.post("/api/services/{service_id}/analyze")
async def analyze_service_legacy(service_id: str, background_tasks: BackgroundTasks):
    """Legacy endpoint for backward compatibility - defaults to 'prod' environment"""
    return await analyze_service(service_id, "prod", background_tasks)


@app.post("/api/services/{service_id}/analyze/{environment}")
async def analyze_service(service_id: str, environment: str, background_tasks: BackgroundTasks):
    """Analyze specific service for a specific environment using dynamic branch creation"""
    if service_id not in SERVICES_CONFIG:
        raise HTTPException(404, f"Service {service_id} not found")
    
    config = SERVICES_CONFIG[service_id]
    
    # Validate environment
    if environment not in config["environments"]:
        raise HTTPException(400, f"Invalid environment '{environment}'. Must be one of: {config['environments']}")
    
    print("=" * 80)
    print(f"🚀 SERVICE-SPECIFIC ANALYSIS REQUEST")
    print("=" * 80)
    print(f"🆔 Service ID: {service_id}")
    print(f"📦 Repository: {config['repo_url']}")
    print(f"🌿 Main Branch: {config['main_branch']}")
    print(f"🌍 Environment: {environment}")
    print("=" * 80)
    
    # Use ValidationRequest with service-specific config
    request = ValidationRequest(
        repo_url=config["repo_url"],
        main_branch=config["main_branch"],
        environment=environment,
        target_folder="",
        project_id=f"{service_id}_{environment}",
        mr_iid=f"{service_id}_{environment}_analysis_{int(datetime.now().timestamp())}"
    )
    
    # Call validation function
    result = await validate_configuration(request, background_tasks)
    
    # Store service-specific result for future reference
    store_service_result(service_id, environment, result)
    
    return result


@app.post("/api/inference")
async def inference_api(request: InferenceRequest, background_tasks: BackgroundTasks):
    """
    🤖 Simple Inference API - Run drift analysis with JSON input
    
    **Input:**
    ```json
    {
      "service_name": "cxp_ptg_adapter",
      "environment": "alpha"
    }
    ```
    
    **Output:**
    Complete drift analysis results with:
    - Configuration deltas
    - Risk assessment
    - Policy violations
    - AI-powered recommendations
    
    **Use Case:**
    Perfect for external systems/tools that need to:
    - Trigger analysis programmatically
    - Get results in a single API call
    - Integrate with CI/CD pipelines
    - Build custom dashboards
    """
    service_name = request.service_name
    environment = request.environment
    
    # Validate service exists
    if service_name not in SERVICES_CONFIG:
        available_services = list(SERVICES_CONFIG.keys())
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Service '{service_name}' not found",
                "available_services": available_services,
                "hint": f"Use one of: {', '.join(available_services)}"
            }
        )
    
    config = SERVICES_CONFIG[service_name]
    
    # Validate environment
    if environment not in config["environments"]:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Invalid environment '{environment}' for service '{service_name}'",
                "valid_environments": config["environments"],
                "hint": f"Use one of: {', '.join(config['environments'])}"
            }
        )
    
    print("\n" + "=" * 80)
    print("🤖 INFERENCE API REQUEST")
    print("=" * 80)
    print(f"📋 Service Name: {service_name}")
    print(f"🌍 Environment: {environment}")
    print(f"📦 Repository: {config['repo_url']}")
    print(f"🌿 Main Branch: {config['main_branch']}")
    print("=" * 80)
    print("🔄 Running drift analysis...")
    print("=" * 80)
    
    # Create validation request
    validation_request = ValidationRequest(
        repo_url=config["repo_url"],
        main_branch=config["main_branch"],
        environment=environment,
        target_folder="",
        project_id=f"{service_name}_{environment}",
        mr_iid=f"{service_name}_{environment}_inference_{int(datetime.now().timestamp())}"
    )
    
    try:
        # Run analysis
        result = await validate_configuration(validation_request, background_tasks)
        
        # Store result for future reference
        store_service_result(service_name, environment, result)
        
        # Get LLM output for enhanced response
        llm_output = None
        validation_result = result.get("validation_result", {})
        run_id = validation_result.get("run_id", "unknown")
        
        try:
            last_result = get_last_service_result(service_name, environment)
            if last_result:
                llm_output = last_result.get("validation_result", {}).get("llm_output", {})
        except Exception as e:
            print(f"⚠️ Could not load LLM output: {e}")
        
        # Extract summary data
        llm_summary = llm_output.get("summary", {}) if llm_output else {}
        total_config_files = llm_summary.get("total_config_files", 0)
        files_with_drift = llm_summary.get("files_with_drift", 0)
        total_drifts = llm_summary.get("total_drifts", 0)
        high_risk = llm_summary.get("high_risk", 0)
        medium_risk = llm_summary.get("medium_risk", 0)
        low_risk = llm_summary.get("low_risk", 0)
        allowed_variance = llm_summary.get("allowed_variance", 0)
        
        # Determine overall risk level
        if high_risk > 0:
            overall_risk = "HIGH"
        elif medium_risk > 0:
            overall_risk = "MEDIUM"
        elif low_risk > 0:
            overall_risk = "LOW"
        else:
            overall_risk = "NONE"
        
        # Generate URL to drift analysis tab
        base_url = os.getenv("BASE_URL", "http://localhost:3000")
        analysis_url = f"{base_url}/branch-environment?id={service_name}&run_id={run_id}&tab=deployment"
        
        # Prepare clean inference response (metadata only)
        inference_response = {
            "status": "success",
            "service_name": service_name,
            "environment": environment,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "metrics": {
                "total_config_files": total_config_files,
                "files_with_drift": files_with_drift,
                "total_drifts": total_drifts,
                "high_risk_drifts": high_risk,
                "medium_risk_drifts": medium_risk,
                "low_risk_drifts": low_risk,
                "allowed_variance": allowed_variance,
                "overall_risk_level": overall_risk
            },
            "execution_time_seconds": result.get("execution_time_seconds", 0),
            "analysis_url": analysis_url
        }
        
        print("\n" + "=" * 80)
        print("✅ INFERENCE COMPLETED")
        print("=" * 80)
        print(f"📊 Total Config Files:    {total_config_files}")
        print(f"📁 Files with Drift:      {files_with_drift}")
        print(f"🔍 Total Drifts:          {total_drifts}")
        print(f"   ├─ ⚠️  High Risk:       {high_risk}")
        print(f"   ├─ ⚡ Medium Risk:      {medium_risk}")
        print(f"   ├─ ℹ️  Low Risk:        {low_risk}")
        print(f"   └─ ✅ Allowed:          {allowed_variance}")
        print(f"🎯 Overall Risk Level:    {overall_risk}")
        print(f"⏱️  Execution Time:        {result.get('execution_time_seconds', 0):.2f}s")
        print(f"🔗 View Details:          {analysis_url}")
        print("=" * 80)
        
        return inference_response
        
    except Exception as e:
        print("\n" + "=" * 80)
        print("❌ INFERENCE FAILED")
        print("=" * 80)
        print(f"Error: {str(e)}")
        print("=" * 80)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Inference failed",
                "message": str(e),
                "service_name": service_name,
                "environment": environment
            }
        )


@app.get("/run/{run_id}", response_class=HTMLResponse)
async def view_run_details(request: Request, run_id: str):
    """
    View specific analysis run details in a new tab
    
    Shows drift analysis results for a specific run ID.
    This opens in a new browser tab/window for detailed review.
    """
    # Extract service_id from run_id (format: run_YYYYMMDD_HHMMSS_service_env_analysis_timestamp)
    # Example: run_20251015_185827_cxp_credit_services_prod_analysis_1760569065
    try:
        # Split by '_' but need to be smarter about service names with underscores
        parts = run_id.split('_')
        print(f"🔍 BACKEND: Parsing run_id '{run_id}' -> parts: {parts}")
        if len(parts) >= 7:  # run_20251015_185827_cxp_credit_services_prod_analysis_1760569065
                # Service name is between parts[3] and the environment (prod)
                # parts[0] = "run"
                # parts[1] = "20251015" (date)
                # parts[2] = "185827" (time)
                # parts[3:] = service name until environment
                env_positions = []
                for i, part in enumerate(parts):
                    if part in ['prod', 'dev', 'qa', 'staging']:
                        env_positions.append(i)
                
                if env_positions:
                    env_pos = env_positions[0]
                    # Service name is from parts[3] to env_pos-1 (skip run, date, time)
                    service_parts = parts[3:env_pos]
                    service_id = '_'.join(service_parts)  # cxp_credit_services
                    
                    print(f"🔍 BACKEND: Environment found at position {env_pos}, service_parts: {service_parts}")
                    print(f"🔍 Extracted service_id: '{service_id}' from run_id: '{run_id}'")
                
                from fastapi.responses import RedirectResponse
                return RedirectResponse(url=f"/branch-environment?id={service_id}&run_id={run_id}&tab=deployment", status_code=301)
    except:
        pass
    
    # Fallback: redirect without service_id, let frontend handle it
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/branch-environment?run_id={run_id}&tab=deployment", status_code=301)


@app.get("/service/{service_id}", response_class=HTMLResponse)
async def service_detail(request: Request, service_id: str):
    """
    [DEPRECATED] Service-specific dashboard
    
    This endpoint is deprecated. All functionality has been moved to the 
    Branch & Environment page's "Drift Analysis" tab for better UX.
    
    Redirecting to: /branch-environment?id={service_id}&tab=deployment
    """
    if service_id not in SERVICES_CONFIG:
        raise HTTPException(404, f"Service {service_id} not found")
    
    # Redirect to Branch & Environment page with Drift Analysis tab
    # This provides the same functionality without a separate page
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/branch-environment?id={service_id}&tab=deployment", status_code=301)


@app.get("/api/services/{service_id}/llm-output")
async def get_service_llm_output(service_id: str, environment: Optional[str] = None):
    """Get LLM output data for a specific service (for React dashboard)"""
    if service_id not in SERVICES_CONFIG:
        raise HTTPException(404, f"Service {service_id} not found")
    
    # ✅ FIXED: Get the last result for this service AND environment
    last_result = get_last_service_result(service_id, environment)
    
    if not last_result:
        raise HTTPException(
            status_code=404,
            detail=f"No analysis results available for {service_id}. Run analysis first."
        )
    
    # Extract validation_result
    result_data = last_result.get("validation_result", last_result)
    
    # Try to load LLM output from database
    try:
        run_id = result_data.get("run_id") or last_result.get("run_id")
        if run_id:
            llm_data = get_llm_output(run_id)
            if llm_data:
                return {
                    "status": "success",
                    "data": llm_data,
                    "service_id": service_id,
                    "timestamp": last_result.get("timestamp")
                }
    except Exception as e:
        print(f"⚠️ Could not load LLM output from database for {service_id}: {e}")
    
    # If no LLM output file found, return error
    raise HTTPException(
        status_code=404,
        detail=f"LLM output data not found for {service_id}"
    )


def get_last_service_result(service_id: str, environment: Optional[str] = None):
    """
    Get most recent validation result for a service.
    
    Args:
        service_id: Service identifier
        environment: Optional environment name. If None, returns latest from any environment.
        
    Returns:
        Latest validation result or None
    """
    # First check in-memory latest_results
    if latest_results:
        req_params = latest_results.get("request_params", {})
        # Check if it matches service_id (and environment if specified)
        project_id = req_params.get("project_id", "")
        if project_id.startswith(service_id):
            if environment is None or req_params.get("environment") == environment:
                return latest_results
    
    # Try to load from database
    try:
        if environment:
            # Get the most recent run for this specific environment
            all_runs = get_all_validation_runs()
            filtered_runs = [
                run for run in all_runs
                if run.get('service_name') == service_id and run.get('environment') == environment
            ]
            
            if filtered_runs:
                run_id = filtered_runs[0]['run_id']
                # Build comprehensive result from database
                from shared.db import get_aggregated_results
                aggregated = get_aggregated_results(run_id)
                llm_output = get_llm_output(run_id)
                
                if aggregated or llm_output:
                    validation_result = {
                        "run_id": run_id,
                        "llm_output": llm_output
                    }
                    # Add aggregated data if available
                    if aggregated:
                        validation_result.update(aggregated)
                    
                    result = {
                        "run_id": run_id,
                        "service_id": service_id,
                        "environment": environment,
                        "timestamp": filtered_runs[0].get('created_at'),
                        "validation_result": validation_result
                    }
                    print(f"✅ Loaded stored result for {service_id}/{environment} from database")
                    return result
        else:
            # No environment specified - find most recent from any environment
            all_runs = get_all_validation_runs()
            service_runs = [run for run in all_runs if run.get('service_name') == service_id]
            
            if service_runs:
                run_id = service_runs[0]['run_id']
                env = service_runs[0].get('environment', 'unknown')
                from shared.db import get_aggregated_results
                aggregated = get_aggregated_results(run_id)
                llm_output = get_llm_output(run_id)
                
                if aggregated or llm_output:
                    validation_result = {
                        "run_id": run_id,
                        "llm_output": llm_output
                    }
                    # Add aggregated data if available
                    if aggregated:
                        validation_result.update(aggregated)
                    
                    result = {
                        "run_id": run_id,
                        "service_id": service_id,
                        "environment": env,
                        "timestamp": service_runs[0].get('created_at'),
                        "validation_result": validation_result
                    }
                    print(f"✅ Loaded stored result for {service_id} from database")
                    return result
    except Exception as e:
        print(f"⚠️ Failed to load stored result from database: {e}")
        import traceback
        traceback.print_exc()
    
    return None


def store_service_result(service_id: str, environment: str, result: dict):
    """Store validation results with service and environment context"""
    global latest_results
    latest_results = result
    
    # Results are stored in database by agents and supervisor
    print(f"✅ Validation results for {service_id}/{environment} stored in database")


# Helper functions removed - all data stored in database


@app.post("/api/services/{service_id}/import-result/{environment}")
async def import_service_result(service_id: str, environment: str, result_data: dict):
    """Import analysis result for a service/environment (useful for transferring results from other machines)"""
    if service_id not in SERVICES_CONFIG:
        raise HTTPException(404, f"Service {service_id} not found")
    
    config = SERVICES_CONFIG[service_id]
    if environment not in config["environments"]:
        raise HTTPException(400, f"Invalid environment '{environment}'. Must be one of: {config['environments']}")
    
    try:
        # Store the imported result
        store_service_result(service_id, environment, result_data)
        
        return {
            "status": "success",
            "message": f"Result imported successfully for {service_id}/{environment}",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to import result: {str(e)}")


@app.get("/api/services/{service_id}/results")
async def get_service_results(service_id: str):
    """Get all stored results for a service"""
    if service_id not in SERVICES_CONFIG:
        raise HTTPException(404, f"Service {service_id} not found")
    
    service_results_dir = Path("config_data") / "service_results" / service_id
    results = []
    
    if service_results_dir.exists():
        result_files = sorted(service_results_dir.glob("validation_*.json"), reverse=True)
        for result_file in result_files:
            try:
                with open(result_file, 'r', encoding='utf-8') as f:
                    stored_data = json.load(f)
                    results.append({
                        "file_name": result_file.name,
                        "timestamp": stored_data.get("timestamp"),
                        "service_id": stored_data.get("service_id"),
                        "has_result": "result" in stored_data
                    })
            except Exception as e:
                print(f"⚠️ Could not read result file {result_file}: {e}")
    
    return {
        "service_id": service_id,
        "total_results": len(results),
        "results": results
    }


@app.post("/api/services/{service_id}/set-golden/{environment}")
async def set_golden_branch(service_id: str, environment: str, branch_name: Optional[str] = None):
    """
    Set a golden branch for a service and environment.
    If branch_name is not provided, creates a new golden branch from main.
    """
    if service_id not in SERVICES_CONFIG:
        raise HTTPException(404, f"Service {service_id} not found")
    
    config = SERVICES_CONFIG[service_id]
    if environment not in config["environments"]:
        raise HTTPException(400, f"Invalid environment '{environment}'. Must be one of: {config['environments']}")
    
    try:
        from shared.golden_branch_tracker import add_golden_branch
        from shared.git_operations import (
            generate_unique_branch_name, 
            create_env_specific_config_branch,  # Environment-specific filtering
            check_branch_exists
        )
        
        # If branch_name not provided, create new golden branch
        if not branch_name:
            branch_name = generate_unique_branch_name("golden", environment)
            
            # Create environment-specific config branch (filtered by environment)
            config_paths = config.get("config_paths", DEFAULT_CONFIG_PATHS)
            success = create_env_specific_config_branch(
                repo_url=config["repo_url"],
                main_branch=config["main_branch"],
                new_branch_name=branch_name,
                environment=environment,
                config_paths=config_paths,
                gitlab_token=os.getenv('GITLAB_TOKEN')
            )
            
            if not success:
                raise HTTPException(500, f"Failed to create golden branch {branch_name}")
        else:
            # Validate that the provided branch exists
            if not check_branch_exists(config["repo_url"], branch_name, os.getenv('GITLAB_TOKEN')):
                raise HTTPException(404, f"Branch {branch_name} does not exist in repository")
        
        # Add to tracker
        add_golden_branch(service_id, environment, branch_name)
        
        return {
            "status": "success",
            "message": f"Golden branch set for {service_id}/{environment}",
            "branch_name": branch_name,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set golden branch: {str(e)}")


@app.post("/api/services/{service_id}/certify-selective/{environment}")
async def certify_selective_files(service_id: str, environment: str, request: Request):
    """
    Create a new golden branch with only selected files from drift branch.
    Rejected files are kept from the old golden branch.
    """
    if service_id not in SERVICES_CONFIG:
        raise HTTPException(404, f"Service {service_id} not found")
    
    config = SERVICES_CONFIG[service_id]
    if environment not in config["environments"]:
        raise HTTPException(400, f"Invalid environment '{environment}'. Must be one of: {config['environments']}")
    
    try:
        # Get approved files from request
        data = await request.json()
        approved_files = data.get("approved_files", [])
        
        if not approved_files:
            raise HTTPException(400, "No files selected for certification")
        
        from shared.golden_branch_tracker import get_active_golden_branch, get_active_drift_branch, add_golden_branch
        from shared.git_operations import (
            generate_unique_branch_name,
            create_selective_golden_branch
        )
        
        # Get current golden and drift branches
        old_golden_branch = get_active_golden_branch(service_id, environment)
        drift_branch = get_active_drift_branch(service_id, environment)
        
        if not old_golden_branch:
            raise HTTPException(404, f"No golden branch found for {service_id}/{environment}")
        
        if not drift_branch:
            raise HTTPException(404, f"No drift branch found for {service_id}/{environment}")
        
        # Generate new golden branch name
        new_golden_branch = generate_unique_branch_name("golden", environment)
        
        # Create new golden branch with selective files
        success = create_selective_golden_branch(
            repo_url=config["repo_url"],
            old_golden_branch=old_golden_branch,
            drift_branch=drift_branch,
            new_branch_name=new_golden_branch,
            approved_files=approved_files,
            config_paths=config.get("config_paths", DEFAULT_CONFIG_PATHS),
            gitlab_token=os.getenv('GITLAB_TOKEN')
        )
        
        if not success:
            raise HTTPException(500, f"Failed to create selective golden branch")
        
        # Add new golden branch to tracker
        add_golden_branch(service_id, environment, new_golden_branch)
        
        return {
            "status": "success",
            "message": f"Selective certification completed for {service_id}/{environment}",
            "golden_branch": new_golden_branch,
            "approved_files_count": len(approved_files),
            "approved_files": approved_files,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Selective certification failed: {str(e)}")


@app.get("/api/services/{service_id}/branches/{environment}")
async def get_service_branches(service_id: str, environment: str):
    """Get all golden and drift branches for a service and environment"""
    if service_id not in SERVICES_CONFIG:
        raise HTTPException(404, f"Service {service_id} not found")
    
    config = SERVICES_CONFIG[service_id]
    if environment not in config["environments"]:
        raise HTTPException(400, f"Invalid environment '{environment}'. Must be one of: {config['environments']}")
    
    try:
        from shared.golden_branch_tracker import get_all_branches, get_active_golden_branch
        
        branches_data = get_all_branches(service_id, environment)
        golden_branches = branches_data.get('golden_branches', [])
        drift_branches = branches_data.get('drift_branches', [])
        active_golden = get_active_golden_branch(service_id, environment)
        
        # Get drift count from last validation result for this environment
        drift_count = 0
        last_result = get_last_service_result(service_id, environment)
        if last_result:
            # Navigate to the correct nested structure
            validation_result = last_result.get("validation_result", {})
            if validation_result and "llm_output" in validation_result:
                llm_output = validation_result["llm_output"]
                llm_summary = llm_output.get("summary", {})
                drift_count = llm_summary.get("total_drifts", 0)
            # Fallback: Try direct llm_output
            elif "llm_output" in last_result:
                llm_output = last_result["llm_output"]
                llm_summary = llm_output.get("summary", {})
                drift_count = llm_summary.get("total_drifts", 0)
        
        return {
            "service_id": service_id,
            "environment": environment,
            "active_golden_branch": active_golden,
            "golden_branches": golden_branches,
            "drift_branches": drift_branches,
            "total_golden": len(golden_branches),
            "total_drift": len(drift_branches),
            "drift_count": drift_count,  # ✅ NEW: Include drift count from last analysis
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get branches: {str(e)}")


@app.get("/api/services/{service_id}/validate-golden/{environment}")
async def validate_golden_branch(service_id: str, environment: str):
    """Check if a golden branch exists for a service and environment"""
    if service_id not in SERVICES_CONFIG:
        raise HTTPException(404, f"Service {service_id} not found")
    
    config = SERVICES_CONFIG[service_id]
    if environment not in config["environments"]:
        raise HTTPException(400, f"Invalid environment '{environment}'. Must be one of: {config['environments']}")
    
    try:
        from shared.golden_branch_tracker import get_active_golden_branch
        
        active_branch = get_active_golden_branch(service_id, environment)
        exists = active_branch is not None
        
        # Get drift count from last validation result for this environment
        drift_count = 0
        last_result = get_last_service_result(service_id, environment)
        if last_result:
            # Navigate to the correct nested structure
            validation_result = last_result.get("validation_result", {})
            if validation_result and "llm_output" in validation_result:
                llm_output = validation_result["llm_output"]
                llm_summary = llm_output.get("summary", {})
                drift_count = llm_summary.get("total_drifts", 0)
            # Fallback: Try direct llm_output
            elif "llm_output" in last_result:
                llm_output = last_result["llm_output"]
                llm_summary = llm_output.get("summary", {})
                drift_count = llm_summary.get("total_drifts", 0)
        
        return {
            "service_id": service_id,
            "environment": environment,
            "golden_exists": exists,
            "active_golden_branch": active_branch,
            "drift_count": drift_count,  # ✅ NEW: Include drift count from last analysis
            "message": "Golden branch found" if exists else "No golden branch found. Please create a golden baseline first.",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to validate golden branch: {str(e)}")

@app.delete("/api/services/{service_id}/revoke-golden/{environment}")
async def revoke_golden_branch(service_id: str, environment: str):
    """Revoke (delete) the active golden branch for a service and environment"""
    if service_id not in SERVICES_CONFIG:
        raise HTTPException(404, f"Service {service_id} not found")
    
    config = SERVICES_CONFIG[service_id]
    if environment not in config["environments"]:
        raise HTTPException(400, f"Invalid environment '{environment}'. Must be one of: {config['environments']}")
    
    try:
        from shared.golden_branch_tracker import get_active_golden_branch, remove_golden_branch
        
        # Get the active golden branch
        active_branch = get_active_golden_branch(service_id, environment)
        
        # Check if golden branch exists
        if not active_branch:
            raise HTTPException(400, f"No golden branch found for {service_id}/{environment}")
        
        # Remove the golden branch from tracking
        remove_golden_branch(service_id, environment, active_branch)
        
        print(f"✅ Revoked golden branch {active_branch} for {service_id}/{environment}")
        
        return {
            "service_id": service_id,
            "environment": environment,
            "revoked_branch": active_branch,
            "message": f"Golden branch {active_branch} has been revoked",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error revoking golden branch for {service_id}/{environment}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to revoke golden branch: {str(e)}")


@app.get("/api/services/{service_id}/run-history/{environment}")
async def get_run_history(service_id: str, environment: str):
    """Get run history for a specific service/environment"""
    if service_id not in SERVICES_CONFIG:
        raise HTTPException(404, f"Service {service_id} not found")
    
    config = SERVICES_CONFIG[service_id]
    if environment not in config["environments"]:
        raise HTTPException(400, f"Invalid environment '{environment}'. Must be one of: {config['environments']}")
    
    try:
        # Get all runs from database for this service/environment
        all_runs = get_all_validation_runs()
        
        # Filter by service and environment
        filtered_runs = [
            run for run in all_runs
            if run.get('service_name') == service_id and run.get('environment') == environment
        ]
        
        # Transform runs to match UI expectations
        transformed_runs = []
        for run in filtered_runs:
            # Get additional data for each run
            llm_output = get_llm_output(run['run_id'])
            
            # Build metrics from llm_output
            metrics = {}
            if llm_output:
                summary = llm_output.get('summary', {})
                metrics = {
                    'total_drifts': summary.get('total_drifts', 0),
                    'high_risk': summary.get('high_risk', 0),
                    'medium_risk': summary.get('medium_risk', 0),
                    'low_risk': summary.get('low_risk', 0),
                    'allowed_variance': summary.get('allowed_variance', 0)
                }
            
            transformed_run = {
                'run_id': run['run_id'],
                'verdict': run.get('verdict', 'UNKNOWN'),
                'status': run.get('status', 'unknown'),
                'timestamp': run.get('created_at', ''),
                'created_at': run.get('created_at', ''),
                'environment': run.get('environment', ''),
                'service_name': run.get('service_name', service_id),
                'metrics': metrics,
                'branches': {
                    'golden': run.get('golden_branch', ''),
                    'drift': run.get('drift_branch', '')
                }
            }
            transformed_runs.append(transformed_run)
        
        return {
            "service_id": service_id,
            "environment": environment,
            "runs": transformed_runs
        }
    except Exception as e:
        logger.error(f"Failed to get run history from database: {e}")
        return {
            "service_id": service_id,
            "environment": environment,
            "runs": []
        }


@app.get("/api/services/{service_id}/run/{run_id}")
async def get_run_details(service_id: str, run_id: str):
    """Get detailed results for a specific run from database"""
    if service_id not in SERVICES_CONFIG:
        raise HTTPException(404, f"Service {service_id} not found")
    
    try:
        # Get run details from database
        run_data = get_run_by_id(run_id)
        
        if not run_data:
            raise HTTPException(404, f"Run {run_id} not found")
        
        # Verify it belongs to the requested service
        if run_data.get('service_name') != service_id:
            raise HTTPException(404, f"Run {run_id} not found for service {service_id}")
        
        # Get aggregated results
        aggregated = get_aggregated_results(run_id)
        
        # Get LLM output
        llm_output = get_llm_output(run_id)
        
        # Get certification if available
        certification = get_certification(run_id)
        
        # Build comprehensive response
        response = {
            "run": run_data,
            "aggregated_results": aggregated,
            "llm_output": llm_output,
            "certification": certification,
            "environment": run_data.get('environment'),
            "service_name": run_data.get('service_name')
        }
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"⚠️ Error loading run details: {e}")
        raise HTTPException(500, f"Failed to load run details: {str(e)}")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    
    return {
        "status": "healthy",
        "service": "Golden Config AI - Multi-Agent System",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "2.0.0",
        "architecture": "supervisor_orchestration",
        "validation_in_progress": validation_in_progress,
        "has_results": latest_results is not None
    }


# ============================================================================
# SERVICE MANAGEMENT API ENDPOINTS (NEW)
# ============================================================================

@app.post("/api/services")
async def create_service(request: Request):
    """
    Add a new service to the database.
    
    Body:
    {
        "service_id": "my_service",
        "service_name": "My Service",
        "repo_url": "https://gitlab.example.com/org/repo.git",
        "main_branch": "main",
        "environments": ["prod", "dev"],
        "config_paths": [...],  // optional
        "description": "..."     // optional
    }
    """
    try:
        data = await request.json()
        
        # Validate required fields
        required_fields = ["service_id", "service_name", "repo_url", "main_branch", "environments"]
        for field in required_fields:
            if field not in data:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        # Add service to database
        # VSAT will be auto-extracted from repo_url if not provided
        add_service(
            service_id=data["service_id"],
            service_name=data["service_name"],
            repo_url=data["repo_url"],
            main_branch=data["main_branch"],
            environments=data["environments"],
            config_paths=data.get("config_paths"),
            vsat=data.get("vsat"),  # Optional - will be auto-extracted
            vsat_url=data.get("vsat_url"),  # Optional - will be auto-extracted
            description=data.get("description")
        )
        
        # Reload services
        global SERVICES_CONFIG
        SERVICES_CONFIG = load_services_from_db()
        
        return {
            "status": "success",
            "message": f"Service '{data['service_id']}' added successfully",
            "service": data
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add service: {str(e)}")


@app.put("/api/services/{service_id}")
async def update_service_endpoint(service_id: str, request: Request):
    """Update an existing service."""
    try:
        from shared.db import update_service
        
        service = get_service_by_id(service_id)
        if not service:
            raise HTTPException(status_code=404, detail=f"Service '{service_id}' not found")
        
        data = await request.json()
        update_service(service_id, data)
        
        # Reload services
        global SERVICES_CONFIG
        SERVICES_CONFIG = load_services_from_db()
        
        return {
            "status": "success",
            "message": f"Service '{service_id}' updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update service: {str(e)}")


@app.delete("/api/services/{service_id}")
async def delete_service_endpoint(service_id: str):
    """Deactivate a service (soft delete)."""
    try:
        from shared.db import deactivate_service
        
        service = get_service_by_id(service_id)
        if not service:
            raise HTTPException(status_code=404, detail=f"Service '{service_id}' not found")
        
        deactivate_service(service_id)
        
        # Reload services
        global SERVICES_CONFIG
        SERVICES_CONFIG = load_services_from_db()
        
        return {
            "status": "success",
            "message": f"Service '{service_id}' deactivated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to deactivate service: {str(e)}")


@app.get("/api/services/{service_id}/config")
async def get_service_config(service_id: str):
    """Get detailed configuration for a specific service."""
    try:
        service = get_service_by_id(service_id)
        if not service:
            raise HTTPException(status_code=404, detail=f"Service '{service_id}' not found")
        
        return {
            "status": "success",
            "service": service
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get service config: {str(e)}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Start the multi-agent validation server"""
    print("\n" + "=" * 80)
    print("🚀 GOLDEN CONFIG AI - MULTI-AGENT SYSTEM")
    print("=" * 80)
    print()
    print("🌐 Server URLs:")
    port = int(os.getenv("PORT", "3000"))
    print(f"   Dashboard:  http://localhost:{port}")
    print(f"   API Docs:   http://localhost:{port}/docs")
    print(f"   Health:     http://localhost:{port}/health")
    print()
    print("🤖 AGENT ARCHITECTURE:")
    print("   ┌─────────────────────────────────┐")
    print("   │     Supervisor Agent            │  ← Orchestrates workflow")
    print("   │  (Claude 3.5 Sonnet)            │")
    print("   └──────────┬──────────────────────┘")
    print("              │")
    print("              ├──► Config Collector Agent")
    print("              │    (Fetches Git diffs)")
    print("              │    (Claude 3 Haiku)")
    print("              │")
    print("              └──► Diff Policy Engine Agent")
    print("                   (AI-powered analysis)")
    print("                   (Claude 3 Haiku)")
    print()
    print("💾 Communication: File-Based")
    print("   ├─ Config Collector → config_data/drift_analysis/*.json")
    print("   ├─ Diff Engine     → config_data/diff_analysis/*.json")
    print("   └─ Supervisor      → config_data/reports/*.md")
    print()
    print("🎯 LEGACY DEFAULT CONFIGURATION (for backward compatibility):")
    print(f"   Repository: {DEFAULT_REPO_URL}")
    print(f"   Main Branch: {DEFAULT_MAIN_BRANCH}")
    print(f"   Environment: {DEFAULT_ENVIRONMENT}")
    print(f"   ⚠️  Note: Each service uses its own configured repository and environments")
    print()
    print("📚 ENDPOINTS:")
    print("   POST /api/validate          - Run full validation (custom params)")
    print("   POST /api/analyze/quick     - Quick analysis (default settings)")
    print("   POST /api/analyze/agent     - Legacy compatibility endpoint")
    print("   GET  /api/latest-results    - Get most recent validation results")
    print("   GET  /api/validation-status - Check if validation is running")
    print("   GET  /api/agent-status      - Check agent system status")
    print()
    port = int(os.getenv("PORT", "3000"))
    print("🎮 USAGE:")
    print(f"   1. Open http://localhost:{port} in your browser")
    print("   2. Click 'Load Sample Data' or 'Analyze' to start validation")
    print("   3. Watch the multi-agent system coordinate the analysis")
    print("   4. Review comprehensive drift analysis results")
    print()
    print("✨ FEATURES:")
    print("   ✅ Complete Supervisor orchestration")
    print("   ✅ File-based inter-agent communication")
    print("   ✅ Real GitLab repository analysis")
    print("   ✅ AI-powered drift detection with enhanced prompts")
    print("   ✅ Comprehensive risk assessment")
    print("   ✅ Policy violation detection")
    print("   ✅ Actionable recommendations")
    print()
    print("🛑 Press Ctrl+C to stop")
    print("=" * 80)
    print()
    
    # Get host and port from environment or use defaults
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "3000"))
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )


# ============================================================================
# VSAT Automation Integration
# ============================================================================

# Global instances
scheduler = None
config_observer = None


class VSATConfigFileHandler(FileSystemEventHandler):
    """Handle VSAT config file changes"""
    
    def __init__(self):
        self.last_sync = datetime.now()
        self.debounce_seconds = 5
    
    def on_modified(self, event):
        # Watch for both master and detailed config files
        if event.src_path.endswith('vsat_master.yaml') or event.src_path.endswith('vsat_config.yaml'):
            now = datetime.now()
            if (now - self.last_sync).total_seconds() > self.debounce_seconds:
                logger.info("📝 VSAT config changed - triggering sync")
                self.last_sync = now
                try:
                    from scripts.vsat_sync import run_sync
                    run_sync(force=True)
                except Exception as e:
                    logger.error(f"❌ VSAT sync failed: {e}")


def scheduled_vsat_sync():
    """Scheduled VSAT sync"""
    logger.info("⏰ Scheduled VSAT sync triggered")
    try:
        from scripts.vsat_sync import run_sync
        run_sync(force=True)
    except Exception as e:
        logger.error(f"❌ VSAT sync failed: {e}")


def start_vsat_automation():
    """Start VSAT scheduler and file watcher"""
    global scheduler, config_observer
    
    vsat_config = Path(__file__).parent / "config" / "vsat_master.yaml"
    
    if not vsat_config.exists():
        logger.info("ℹ️  VSAT config not found - automation disabled")
        logger.info(f"   Create {vsat_config} to enable auto-discovery")
        return
    
    try:
        logger.info("="*80)
        logger.info("🚀 VSAT Automation Starting")
        logger.info("="*80)
        
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            scheduled_vsat_sync,
            CronTrigger(day_of_week='sun', hour=2, minute=0),
            id='weekly_vsat_sync',
            replace_existing=True
        )
        scheduler.start()
        logger.info("✅ Scheduler: Weekly sync (Sunday 2 AM)")
        
        config_observer = Observer()
        config_observer.schedule(
            VSATConfigFileHandler(),
            str(vsat_config.parent),
            recursive=False
        )
        config_observer.start()
        logger.info("✅ File watcher: Monitoring config files (vsat_master.yaml, vsat_config.yaml)")
        
        # Initial sync
        logger.info("🔄 Running initial VSAT sync...")
        try:
            from scripts.vsat_sync import run_sync
            result = run_sync(force=False)
            if result.get('status') == 'success':
                logger.info(f"✅ Initial sync: +{result.get('added', 0)} added, ~{result.get('updated', 0)} updated")
            elif result.get('status') == 'skipped':
                logger.info("✅ Config unchanged - sync skipped")
        except Exception as e:
            logger.warning(f"⚠️  Initial sync failed: {e}")
        
        logger.info("="*80)
            
    except Exception as e:
        logger.error(f"❌ VSAT automation failed: {e}")


def stop_vsat_automation():
    """Stop VSAT automation"""
    global scheduler, config_observer
    if scheduler:
        try:
            scheduler.shutdown()
            logger.info("✅ VSAT Scheduler stopped")
        except:
            pass
    if config_observer:
        try:
            config_observer.stop()
            config_observer.join(timeout=5)
            logger.info("✅ VSAT File watcher stopped")
        except:
            pass


@app.on_event("startup")
async def startup_event():
    """Start VSAT automation on server startup"""
    start_vsat_automation()


@app.on_event("shutdown")
async def shutdown_event():
    """Stop VSAT automation on server shutdown"""
    stop_vsat_automation()


if __name__ == "__main__":
    main()