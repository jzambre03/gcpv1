"""
Environment-Specific File Filtering

This module categorizes configuration files by environment to ensure
environment-specific configs don't leak across environments in golden branches.
"""

import logging
from typing import List
from pathlib import Path

logger = logging.getLogger(__name__)


def categorize_file_by_environment(filepath: str) -> List[str]:
    """
    Determine which environments a configuration file belongs to.
    
    Rules:
    - Files with *prod* in name/path → ONLY prod
    - Files with *alpha* in name/path → ONLY alpha  
    - Files with *beta1* or *T1.yml in name/path → ONLY beta1
    - Files with *beta2*, *T2.yml, or *T3.yml in name/path → ONLY beta2
    - Files with *T4.yml, *T5.yml, *T6.yml in name/path → ONLY beta2 (default)
    - Files with no environment marker → ALL environments (global/service-level)
    
    Args:
        filepath: Relative file path (e.g., "helm/config-map/application-prod.yml")
    
    Returns:
        List of environments this file should be included in
        Examples:
        - ['prod'] for prod-specific
        - ['alpha'] for alpha-specific
        - ['beta1'] for beta1-specific
        - ['beta2'] for beta2-specific
        - ['prod', 'alpha', 'beta1', 'beta2'] for global files
    """
    # Normalize path for comparison (lowercase, forward slashes)
    filepath_lower = str(filepath).lower().replace('\\', '/')
    filename = Path(filepath).name.lower()
    
    # Check both full path and filename for environment markers
    full_check = filepath_lower
    
    # Rule 1: Prod-specific files
    if 'prod' in full_check:
        logger.debug(f"File '{filepath}' → prod (contains 'prod')")
        return ['prod']
    
    # Rule 2: Alpha-specific files
    if 'alpha' in full_check:
        logger.debug(f"File '{filepath}' → alpha (contains 'alpha')")
        return ['alpha']
    
    # Rule 3: Beta1-specific files
    # Check for beta1 in path OR filename ending with T1.yml
    if 'beta1' in full_check or filename.endswith('t1.yml'):
        logger.debug(f"File '{filepath}' → beta1 (contains 'beta1' or ends with 'T1.yml')")
        return ['beta1']
    
    # Rule 4: Beta2-specific files (including T2, T3, T4, T5, T6)
    # Check for beta2 in path OR filename ending with T2/T3/T4/T5/T6.yml
    if ('beta2' in full_check or 
        filename.endswith('t2.yml') or 
        filename.endswith('t3.yml') or
        filename.endswith('t4.yml') or
        filename.endswith('t5.yml') or
        filename.endswith('t6.yml')):
        logger.debug(f"File '{filepath}' → beta2 (contains 'beta2' or ends with 'T2/T3/T4/T5/T6.yml')")
        return ['beta2']
    
    # Rule 5: Global/service-level files (no environment marker)
    logger.debug(f"File '{filepath}' → ALL envs (global/service-level)")
    return ['prod', 'alpha', 'beta1', 'beta2']


def filter_files_for_environment(file_list: List[str], environment: str) -> List[str]:
    """
    Filter a list of files to only include those that belong to a specific environment.
    
    Args:
        file_list: List of file paths
        environment: Target environment ('prod', 'alpha', 'beta1', 'beta2')
    
    Returns:
        Filtered list of files that should be included in this environment
    """
    filtered = []
    
    for filepath in file_list:
        envs = categorize_file_by_environment(filepath)
        if environment in envs:
            filtered.append(filepath)
    
    logger.info(f"Environment '{environment}': {len(filtered)}/{len(file_list)} files included")
    return filtered


def get_environment_specific_patterns(environment: str, base_patterns: List[str]) -> List[str]:
    """
    Generate environment-specific file patterns for sparse checkout.
    
    This function takes base config patterns and adds environment-specific
    filtering to ensure only relevant files are included.
    
    Args:
        environment: Target environment ('prod', 'alpha', 'beta1', 'beta2')
        base_patterns: Base config file patterns (e.g., ['*.yml', '*.properties'])
    
    Returns:
        List of patterns that include:
        - Environment-specific files for this environment
        - Global/service-level files (no env marker)
        - Exclusion patterns for other environments
    """
    patterns = []
    
    # Include base patterns (we'll filter after checkout)
    patterns.extend(base_patterns)
    
    # Note: Git sparse-checkout doesn't support complex exclusion logic,
    # so we'll do filtering after checkout using filter_files_for_environment()
    
    return patterns


def log_environment_distribution(file_list: List[str]) -> dict:
    """
    Analyze and log how files are distributed across environments.
    
    Args:
        file_list: List of all config files
    
    Returns:
        Dictionary with counts per environment
    """
    distribution = {
        'prod_only': 0,
        'alpha_only': 0,
        'beta1_only': 0,
        'beta2_only': 0,
        'global': 0,
        'total': len(file_list)
    }
    
    for filepath in file_list:
        envs = categorize_file_by_environment(filepath)
        
        if len(envs) == 4:
            distribution['global'] += 1
        elif envs == ['prod']:
            distribution['prod_only'] += 1
        elif envs == ['alpha']:
            distribution['alpha_only'] += 1
        elif envs == ['beta1']:
            distribution['beta1_only'] += 1
        elif envs == ['beta2']:
            distribution['beta2_only'] += 1
    
    logger.info("File distribution by environment:")
    logger.info(f"  Prod-only:  {distribution['prod_only']}")
    logger.info(f"  Alpha-only: {distribution['alpha_only']}")
    logger.info(f"  Beta1-only: {distribution['beta1_only']}")
    logger.info(f"  Beta2-only: {distribution['beta2_only']}")
    logger.info(f"  Global:     {distribution['global']}")
    logger.info(f"  Total:      {distribution['total']}")
    
    return distribution

