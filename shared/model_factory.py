"""
Model factory for creating LLM model instances.
Uses AWS Bedrock exclusively through Strands SDK.
"""

import os
from strands.models.bedrock import BedrockModel


def create_model(model_id: str = None, region_name: str = None):
    """
    Create a Bedrock model instance.
    
    Args:
        model_id: Bedrock model ID (e.g., 'anthropic.claude-3-5-sonnet-20241022-v2:0')
        region_name: AWS region (defaults to AWS_REGION env or 'us-east-1')
    
    Returns:
        BedrockModel instance configured for the specified model
    """
    aws_region = region_name or os.getenv("AWS_REGION", "us-east-1")
    final_model_id = model_id or os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0")
    
    print(f"✅ Creating Bedrock model: {final_model_id} in region {aws_region}")
    
    return BedrockModel(model_id=final_model_id, region_name=aws_region)


def create_supervisor_model(config):
    """
    Create Bedrock model for supervisor agent (Claude Sonnet).
    
    Args:
        config: Config object with bedrock_model_id and aws_region
    
    Returns:
        BedrockModel instance for supervisor
    """
    return create_model(model_id=config.bedrock_model_id, region_name=config.aws_region)


def create_worker_model(config):
    """
    Create Bedrock model for worker agents (Claude Haiku).
    
    Args:
        config: Config object with bedrock_worker_model_id and aws_region
    
    Returns:
        BedrockModel instance for worker
    """
    return create_model(model_id=config.bedrock_worker_model_id, region_name=config.aws_region)

