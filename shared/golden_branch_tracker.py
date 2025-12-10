"""
Golden Branch Tracker - Manages golden and drift branch metadata

This module tracks which golden and drift branches exist for each service and environment,
storing the data in SQLite database instead of JSON files.
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from .db import (
    save_golden_branch, 
    get_active_golden_branch,
    deactivate_branches as db_deactivate_branches
)

logger = logging.getLogger(__name__)


def add_golden_branch(service_name: str, environment: str, branch_name: str, 
                      certification_score: int = None, metadata: Dict = None) -> None:
    """
    Add a new golden branch for a service/environment.
    Deactivates all previous golden branches and marks this as active.
    
    Args:
        service_name: Service identifier
        environment: Environment (prod, dev, qa, etc.)
        branch_name: Git branch name
        certification_score: Confidence score from certification (0-100)
        metadata: Additional metadata dictionary
    """
    try:
        # Deactivate all existing golden branches
        db_deactivate_branches(service_name, environment, 'golden')
        
        # Add new golden branch
        save_golden_branch(
            service_name=service_name,
            environment=environment,
            branch_name=branch_name,
            branch_type='golden',
            certification_score=certification_score,
            metadata=metadata
        )
        
        logger.info(f"Added golden branch: {service_name}/{environment} -> {branch_name}")
        
    except Exception as e:
        logger.error(f"Failed to add golden branch: {e}")
        raise


def add_drift_branch(service_name: str, environment: str, branch_name: str, 
                     metadata: Dict = None) -> None:
    """
    Add a new drift branch for a service/environment.
    
    Args:
        service_name: Service identifier
        environment: Environment (prod, dev, qa, etc.)
        branch_name: Git branch name
        metadata: Additional metadata dictionary
    """
    try:
        save_golden_branch(
            service_name=service_name,
            environment=environment,
            branch_name=branch_name,
            branch_type='drift',
            certification_score=None,
            metadata=metadata
        )
        
        logger.info(f"Added drift branch: {service_name}/{environment} -> {branch_name}")
        
    except Exception as e:
        logger.error(f"Failed to add drift branch: {e}")
        raise


def get_active_golden(service_name: str, environment: str) -> Optional[str]:
    """
    Get the active golden branch for a service/environment.
    
    Args:
        service_name: Service identifier
        environment: Environment (prod, dev, qa, etc.)
        
    Returns:
        Branch name or None if not found
    """
    try:
        branch_name = get_active_golden_branch(service_name, environment)
        
        if branch_name:
            logger.debug(f"Active golden branch: {service_name}/{environment} -> {branch_name}")
        else:
            logger.warning(f"No active golden branch for {service_name}/{environment}")
        
        return branch_name
        
    except Exception as e:
        logger.error(f"Failed to get active golden branch: {e}")
        return None
    

def validate_golden_exists(service_name: str, environment: str, golden_branch: str) -> bool:
    """
    Validate that a golden branch exists and is active.
    
    Args:
        service_name: Service identifier
        environment: Environment (prod, dev, qa, etc.)
        golden_branch: Expected golden branch name
    
    Returns:
        True if golden branch exists and is active, False otherwise
    """
    try:
        active_branch = get_active_golden_branch(service_name, environment)
        
        if not active_branch:
            logger.warning(f"No golden branch found for {service_name}/{environment}")
            return False
        
        if active_branch != golden_branch:
            logger.warning(f"Golden branch mismatch for {service_name}/{environment}: expected {golden_branch}, found {active_branch}")
            return False
        
        logger.info(f"Golden branch validated: {service_name}/{environment} -> {golden_branch}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to validate golden branch: {e}")
        return False


def get_active_drift_branch(service_name: str, environment: str) -> Optional[str]:
    """
    Get the most recent drift branch for a service/environment.
    
    Args:
        service_name: Service identifier
        environment: Environment (prod, dev, qa, etc.)
        
    Returns:
        Branch name or None if not found
    """
    # Note: This uses the same get_active_golden_branch but with drift type
    # You may want to add a separate function in db.py for drift branches
    try:
        from .db import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT branch_name FROM golden_branches 
                WHERE service_name = ? AND environment = ? 
                AND branch_type = 'drift' AND is_active = 1
                ORDER BY created_at DESC LIMIT 1
            """, (service_name, environment))
            row = cursor.fetchone()
            
            if row:
                logger.debug(f"Active drift branch: {service_name}/{environment} -> {row['branch_name']}")
                return row['branch_name']
            else:
                logger.warning(f"No active drift branch for {service_name}/{environment}")
                return None
                
    except Exception as e:
        logger.error(f"Failed to get active drift branch: {e}")
        return None


def get_all_branches(service_name: str, environment: str) -> Dict[str, List[Dict]]:
    """
    Get all golden and drift branches for a service/environment.
    
    Args:
        service_name: Service identifier
        environment: Environment (prod, dev, qa, etc.)
        
    Returns:
        Dictionary with 'golden_branches' and 'drift_branches' lists
    """
    try:
        from .db import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Get golden branches
            cursor.execute("""
                SELECT branch_name, is_active, created_at, certification_score
                FROM golden_branches 
                WHERE service_name = ? AND environment = ? AND branch_type = 'golden'
                ORDER BY created_at DESC
            """, (service_name, environment))
            
            golden_branches = [
                {
                    'branch_name': row['branch_name'],
                    'is_active': bool(row['is_active']),
                    'created_at': row['created_at'],
                    'certification_score': row['certification_score']
                }
                for row in cursor.fetchall()
            ]
            
            # Get drift branches
            cursor.execute("""
                SELECT branch_name, is_active, created_at
                FROM golden_branches 
                WHERE service_name = ? AND environment = ? AND branch_type = 'drift'
                ORDER BY created_at DESC
            """, (service_name, environment))
            
            drift_branches = [
                {
                    'branch_name': row['branch_name'],
                    'is_active': bool(row['is_active']),
                    'created_at': row['created_at']
                }
                for row in cursor.fetchall()
            ]
            
            return {
                'golden_branches': golden_branches,
                'drift_branches': drift_branches
            }
            
    except Exception as e:
        logger.error(f"Failed to get all branches: {e}")
        return {
            'golden_branches': [],
            'drift_branches': []
        }


def remove_golden_branch(service_name: str, environment: str, branch_name: str) -> bool:
    """
    Remove (deactivate) a specific golden branch.
    
    Args:
        service_name: Service identifier
        environment: Environment (prod, dev, qa, etc.)
        branch_name: Branch name to remove
        
    Returns:
        True if successful, False otherwise
    """
    try:
        from .db import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE golden_branches SET is_active = 0
                WHERE service_name = ? AND environment = ? 
                AND branch_name = ? AND branch_type = 'golden'
            """, (service_name, environment, branch_name))
    
            if cursor.rowcount > 0:
                logger.info(f"Removed golden branch: {service_name}/{environment} -> {branch_name}")
                return True
            else:
                logger.warning(f"Golden branch not found: {service_name}/{environment} -> {branch_name}")
                return False
                
    except Exception as e:
        logger.error(f"Failed to remove golden branch: {e}")
        return False
