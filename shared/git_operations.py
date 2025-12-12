"""
Git Operations Module - Handles Git branch creation and validation

This module provides functions to create branches, check if branches exist,
and manage Git operations for the drift detection system.
"""

import os
import tempfile
import shutil
import uuid
import fnmatch
from pathlib import Path
from datetime import datetime
from typing import List, Optional
import logging

import git
from git.exc import GitCommandError

from .env_filter import filter_files_for_environment, log_environment_distribution

# Configure logging to show in terminal
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Print to console/terminal
    ]
)

logger = logging.getLogger(__name__)


def log_and_print(message: str, level: str = "info"):
    """
    Log message and also print to console to ensure visibility.
    
    Args:
        message: Message to log
        level: Log level (info, warning, error)
    """
    # Always print to console
    print(message)
    
    # Also log
    if level == "info":
        logger.info(message)
    elif level == "warning":
        logger.warning(message)
    elif level == "error":
        logger.error(message)
    else:
        logger.info(message)


def generate_unique_branch_name(prefix: str, environment: str) -> str:
    """
    Generate a unique branch name with timestamp and UUID.
    
    Args:
        prefix: Branch prefix ("golden" or "drift")
        environment: Environment name (e.g., "prod", "dev", "qa", "staging")
        
    Returns:
        Unique branch name (e.g., "drift_prod_20251015_143052_abc123")
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:6]  # Short UUID for readability
    
    return f"{prefix}_{environment}_{timestamp}_{unique_id}"


def setup_git_auth(repo_url: str, gitlab_token: Optional[str] = None) -> str:
    """
    Set up Git authentication using environment variables or provided token.
    
    Args:
        repo_url: Repository URL
        gitlab_token: Optional GitLab personal access token
        
    Returns:
        Authenticated repository URL
    """
    token = gitlab_token or os.getenv('GITLAB_TOKEN')
    gitlab_username = os.getenv('GITLAB_USERNAME')
    gitlab_password = os.getenv('GITLAB_PASSWORD')
    
    if token:
        logger.info("Using GitLab personal access token for authentication")
        if repo_url.startswith('https://'):
            return repo_url.replace('https://', f'https://oauth2:{token}@')
    elif gitlab_username and gitlab_password:
        logger.info("Using username/password for authentication")
        if repo_url.startswith('https://'):
            return repo_url.replace('https://', f'https://{gitlab_username}:{gitlab_password}@')
    
    logger.warning("No authentication credentials found. Proceeding without auth")
    return repo_url


def check_branch_exists(repo_url: str, branch_name: str, gitlab_token: Optional[str] = None) -> bool:
    """
    Check if a branch exists on the remote repository.
    
    Args:
        repo_url: Repository URL
        branch_name: Branch name to check
        gitlab_token: Optional GitLab token for authentication
        
    Returns:
        True if branch exists, False otherwise
    """
    temp_dir = None
    try:
        # Create temporary directory for checking
        temp_dir = tempfile.mkdtemp(prefix="git_check_")
        
        # Setup authentication
        auth_url = setup_git_auth(repo_url, gitlab_token)
        
        # Clone with minimal depth (just to list refs)
        logger.info(f"Checking if branch {branch_name} exists in {repo_url}")
        repo = git.Repo.clone_from(auth_url, temp_dir, depth=1, single_branch=False, no_checkout=True)
        
        # Fetch ALL remote refs (not just main)
        # The --all flag ensures we get all branches, not just the default
        repo.remotes.origin.fetch(refspec='refs/heads/*:refs/remotes/origin/*')
        
        # Check if branch exists in remote
        remote_branches = [ref.name for ref in repo.remotes.origin.refs]
        branch_exists = f"origin/{branch_name}" in remote_branches
        
        logger.info(f"Branch {branch_name} exists: {branch_exists}")
        
        # Enhanced debugging: Show all remote branches
        if not branch_exists:
            logger.warning(f"🔍 DEBUG: Branch '{branch_name}' not found. Available remote branches:")
            for idx, ref_name in enumerate(sorted(remote_branches)[:10], 1):
                logger.warning(f"   {idx}. {ref_name}")
            if len(remote_branches) > 10:
                logger.warning(f"   ... and {len(remote_branches) - 10} more branches")
            logger.warning(f"🔍 DEBUG: Looking for: 'origin/{branch_name}'")
        
        return branch_exists
        
    except GitCommandError as e:
        logger.error(f"Git error checking branch {branch_name}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error checking branch {branch_name}: {e}")
        return False
    finally:
        # Cleanup temporary directory
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp directory {temp_dir}: {e}")


def create_branch_from_main(
    repo_url: str,
    main_branch: str,
    new_branch_name: str,
    gitlab_token: Optional[str] = None
) -> bool:
    """
    Create a new branch from the main branch and push it to remote.
    
    Args:
        repo_url: Repository URL
        main_branch: Source branch name (e.g., "main", "master")
        new_branch_name: Name for the new branch
        gitlab_token: Optional GitLab token for authentication
        
    Returns:
        True if successful, False otherwise
    """
    temp_dir = None
    try:
        # Create temporary directory
        temp_dir = tempfile.mkdtemp(prefix="git_branch_create_")
        logger.info(f"Creating branch {new_branch_name} from {main_branch} in temp dir: {temp_dir}")
        
        # Setup authentication
        auth_url = setup_git_auth(repo_url, gitlab_token)
        
        # Clone the repository
        logger.info(f"Cloning repository from {main_branch}")
        repo = git.Repo.clone_from(auth_url, temp_dir, branch=main_branch)
        
        # Create new branch from main
        logger.info(f"Creating new branch: {new_branch_name}")
        new_branch = repo.create_head(new_branch_name)
        new_branch.checkout()
        
        # Push the new branch to remote
        logger.info(f"Pushing branch {new_branch_name} to remote")
        repo.git.push('--set-upstream', 'origin', new_branch_name)
        
        logger.info(f"✅ Successfully created and pushed branch {new_branch_name}")
        return True
        
    except GitCommandError as e:
        logger.error(f"Git error creating branch {new_branch_name}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error creating branch {new_branch_name}: {e}")
        return False
    finally:
        # Cleanup temporary directory
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logger.info(f"Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to cleanup temp directory {temp_dir}: {e}")


def create_config_only_branch(
    repo_url: str,
    main_branch: str,
    new_branch_name: str,
    config_paths: List[str],
    gitlab_token: Optional[str] = None
) -> bool:
    """
    Create a new branch containing ONLY configuration files (FAST - sparse checkout).
    This is much faster than cloning the entire repository.
    
    Args:
        repo_url: Repository URL
        main_branch: Source branch name (e.g., "main", "master")
        new_branch_name: Name for the new branch
        config_paths: List of config file paths/patterns to include (e.g., ["*.yml", "*.properties"])
        gitlab_token: Optional GitLab token for authentication
        
    Returns:
        True if successful, False otherwise
    """
    temp_dir = None
    try:
        # Create temporary directory
        temp_dir = tempfile.mkdtemp(prefix="git_config_branch_")
        log_and_print(f"🌿 Creating config-only branch: {new_branch_name}")
        log_and_print(f"🎯 Source branch: {main_branch}")
        
        # Setup authentication
        auth_url = setup_git_auth(repo_url, gitlab_token)
        
        # Initialize empty repo
        log_and_print(f"Initializing Git repository...")
        repo = git.Repo.init(temp_dir)
        
        # Add remote
        log_and_print(f"Adding remote origin...")
        origin = repo.create_remote('origin', auth_url)
        
        # Enable sparse checkout BEFORE fetching
        log_and_print(f"Configuring sparse-checkout...")
        with repo.config_writer() as config:
            config.set_value('core', 'sparseCheckout', 'true')
            config.set_value('core', 'sparseCheckoutCone', 'false')  # Use non-cone mode for patterns
        
        # Write sparse-checkout patterns
        sparse_checkout_file = Path(temp_dir) / '.git' / 'info' / 'sparse-checkout'
        sparse_checkout_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(sparse_checkout_file, 'w') as f:
            # Explicitly exclude .git directory
            f.write("!.git/\n")
            for path in config_paths:
                f.write(f"{path}\n")
        
        # Fetch only the main branch with depth=1 (shallow clone) and filter
        log_and_print(f"Fetching {main_branch} with config filtering...")
        origin.fetch(main_branch, depth=1)
        
        # Checkout the main branch (sparse-checkout will apply here)
        log_and_print(f"Checking out {main_branch}...")
        repo.git.checkout(f'origin/{main_branch}')
        
        # Count files in working directory
        checked_out_files = []
        for root, dirs, files in os.walk(temp_dir):
            # Skip .git directory
            if '.git' in root:
                continue
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), temp_dir)
                checked_out_files.append(rel_path)
        
        log_and_print(f"Filtered {len(checked_out_files)} config files")
        
        # Create orphan branch with only config files
        log_and_print(f"Creating orphan branch with config files only...")
        
        # Create an orphan branch (no parent commits)
        repo.git.checkout('--orphan', new_branch_name)
        
        # Clear the index completely to remove any references to files from the original branch
        repo.git.rm('-rf', '--cached', '.')
        
        # Use git read-tree to explicitly build tree with config files only
        try:
            # Start with empty index
            repo.git.read_tree('--empty')
            
            # Get list of all files in the original branch
            ls_tree_output = repo.git.ls_tree('-r', '--name-only', f'origin/{main_branch}')
            all_files_in_original = ls_tree_output.strip().split('\n') if ls_tree_output.strip() else []
            
            # Filter files using our config patterns
            import fnmatch
            filtered_files = []
            
            for file_path in all_files_in_original:
                # Skip .git directory files - these are internal Git files, not configuration files
                if file_path.startswith('.git/'):
                    continue
                    
                for pattern in config_paths:
                    # Support both full path matching and filename matching
                    if (fnmatch.fnmatch(file_path, pattern) or 
                        fnmatch.fnmatch(os.path.basename(file_path), pattern)):
                        filtered_files.append(file_path)
                        break
            
            # Add each filtered file to the index from the original tree
            files_actually_added = 0
            for file_path in filtered_files:
                try:
                    # Get the full object info for this file from the original tree
                    ls_tree_result = repo.git.ls_tree(f'origin/{main_branch}', '--', file_path)
                    if ls_tree_result.strip():
                        # Parse the ls-tree output: mode, type, hash, filename
                        parts = ls_tree_result.strip().split(None, 3)  # Split on whitespace, max 4 parts
                        if len(parts) >= 3:
                            mode = parts[0]
                            obj_hash = parts[2]
                            
                            # Add this file to the index with its original content
                            repo.git.update_index('--add', '--cacheinfo', f'{mode},{obj_hash},{file_path}')
                            files_actually_added += 1
                            
                except Exception as e:
                    log_and_print(f"⚠️ Could not add {file_path} to index: {e}", "warning")
                    # Continue with other files
            
        except Exception as e:
            log_and_print(f"⚠️ Tree approach failed, using fallback method: {e}", "warning")
            
            # Fallback: Add files from working directory individually
            files_added = 0
            for file_path in checked_out_files:
                full_path = Path(temp_dir) / file_path
                if full_path.exists() and full_path.is_file():
                    try:
                        repo.git.add(file_path)
                        files_added += 1
                    except Exception as e:
                        log_and_print(f"⚠️ Warning: Could not add {file_path}: {e}", "warning")
            
            files_actually_added = files_added
        
        # Verify staged files
        try:
            staged_files = repo.git.diff('--cached', '--name-only').strip().split('\n')
            staged_files = [f for f in staged_files if f.strip()]  # Remove empty strings
            
            # Basic validation
            expected_count = len(filtered_files) if 'filtered_files' in locals() else len(checked_out_files)
            
            if len(staged_files) > expected_count * 3:  # Flag major issues
                log_and_print(f"🚨 WARNING: Staged {len(staged_files)} files but expected ~{expected_count}", "error")
                log_and_print(f"The branch may contain non-config files!", "error")
            else:
                log_and_print(f"Staged {len(staged_files)} config files for commit")
                
        except Exception as e:
            log_and_print(f"⚠️ Could not verify staged files: {e}", "warning")
        
        # Create commit with only config files
        log_and_print(f"Creating commit and pushing to remote...")
        commit_message = f"Merge branch '{new_branch_name}'\n\nConfig-only snapshot from {main_branch}\n\nContains only configuration files ({files_actually_added} files):\n- YAML configs\n- Properties files\n- Build configs\n- Container configs"
        repo.git.commit('-m', commit_message)
        
        # Push the new branch to remote
        repo.git.push('--set-upstream', 'origin', new_branch_name)
        
        log_and_print(f"✅ Config-only branch {new_branch_name} created with {files_actually_added} files")
        return True
        
    except GitCommandError as e:
        log_and_print(f"❌ Git error creating config-only branch {new_branch_name}: {e}", "error")
        return False
    except Exception as e:
        log_and_print(f"❌ Error creating config-only branch {new_branch_name}: {e}", "error")
        return False
    finally:
        # Cleanup temporary directory
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                log_and_print(f"⚠️ Failed to cleanup temp directory: {e}", "warning")


def create_env_specific_config_branch(
    repo_url: str,
    main_branch: str,
    new_branch_name: str,
    environment: str,
    config_paths: List[str],
    gitlab_token: Optional[str] = None
) -> bool:
    """
    Create a golden branch containing ONLY environment-specific configuration files.
    
    This function filters config files based on environment to prevent cross-environment
    config leakage:
    - Prod files (e.g., *prod*) → ONLY in prod branch
    - Alpha files (e.g., *alpha*) → ONLY in alpha branch
    - Beta1 files (e.g., *beta1*, *T1.yml) → ONLY in beta1 branch
    - Beta2 files (e.g., *beta2*, *T2.yml, *T3.yml) → ONLY in beta2 branch
    - Global files (e.g., pom.xml, Dockerfile) → in ALL branches
    
    Args:
        repo_url: Repository URL
        main_branch: Source branch name (e.g., "main")
        new_branch_name: Name for the new golden branch (e.g., "golden_prod_20231215_120000")
        environment: Target environment ('prod', 'alpha', 'beta1', 'beta2')
        config_paths: Base config file patterns (e.g., ["*.yml", "*.properties"])
        gitlab_token: Optional GitLab token for authentication
        
    Returns:
        True if successful, False otherwise
    """
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix=f"git_{environment}_config_")
        log_and_print(f"🌿 Creating environment-specific config branch: {new_branch_name}")
        log_and_print(f"🎯 Environment: {environment}")
        log_and_print(f"🎯 Source branch: {main_branch}")
        
        # Setup authentication
        auth_url = setup_git_auth(repo_url, gitlab_token)
        
        # Initialize empty repo
        log_and_print(f"Initializing Git repository...")
        repo = git.Repo.init(temp_dir)
        
        # Add remote
        log_and_print(f"Adding remote origin...")
        origin = repo.create_remote('origin', auth_url)
        
        # Enable sparse checkout
        log_and_print(f"Configuring sparse-checkout...")
        with repo.config_writer() as config:
            config.set_value('core', 'sparseCheckout', 'true')
            config.set_value('core', 'sparseCheckoutCone', 'false')
        
        # Write sparse-checkout patterns (start with base config patterns)
        sparse_checkout_file = Path(temp_dir) / '.git' / 'info' / 'sparse-checkout'
        sparse_checkout_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(sparse_checkout_file, 'w') as f:
            f.write("!.git/\n")
            for path in config_paths:
                f.write(f"{path}\n")
        
        # Fetch the main branch
        log_and_print(f"Fetching {main_branch}...")
        origin.fetch(main_branch, depth=1)
        
        # Checkout the main branch
        log_and_print(f"Checking out {main_branch}...")
        repo.git.checkout(f'origin/{main_branch}')
        
        # Get list of all checked out config files
        checked_out_files = []
        for root, dirs, files in os.walk(temp_dir):
            if '.git' in root:
                continue
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), temp_dir)
                checked_out_files.append(rel_path)
        
        log_and_print(f"Found {len(checked_out_files)} config files in {main_branch}")
        
        # Log file distribution before filtering
        log_environment_distribution(checked_out_files)
        
        # Filter files for this specific environment
        log_and_print(f"🔍 Filtering files for environment: {environment}")
        env_specific_files = filter_files_for_environment(checked_out_files, environment)
        
        log_and_print(f"✅ {len(env_specific_files)}/{len(checked_out_files)} files included for {environment}")
        
        # Create orphan branch
        log_and_print(f"Creating orphan branch with {environment}-specific config files...")
        repo.git.checkout('--orphan', new_branch_name)
        repo.git.rm('-rf', '--cached', '.')
        
        # Build tree with environment-specific files only
        repo.git.read_tree('--empty')
        
        # Get list of all files in the original branch
        ls_tree_output = repo.git.ls_tree('-r', '--name-only', f'origin/{main_branch}')
        all_files_in_original = ls_tree_output.strip().split('\n') if ls_tree_output.strip() else []
        
        # Filter to config files first (using base patterns)
        filtered_config_files = []
        for file_path in all_files_in_original:
            if file_path.startswith('.git/'):
                continue
            for pattern in config_paths:
                if (fnmatch.fnmatch(file_path, pattern) or 
                    fnmatch.fnmatch(os.path.basename(file_path), pattern)):
                    filtered_config_files.append(file_path)
                    break
        
        # Then filter by environment
        env_filtered_files = filter_files_for_environment(filtered_config_files, environment)
        
        # Add each environment-specific file to the index
        files_actually_added = 0
        for file_path in env_filtered_files:
            try:
                ls_tree_result = repo.git.ls_tree(f'origin/{main_branch}', '--', file_path)
                if ls_tree_result.strip():
                    parts = ls_tree_result.strip().split(None, 3)
                    if len(parts) >= 3:
                        mode = parts[0]
                        obj_hash = parts[2]
                        # Add file to index with its original mode and hash
                        repo.git.update_index('--add', '--cacheinfo', f'{mode},{obj_hash},{file_path}')
                        files_actually_added += 1
            except Exception as e:
                log_and_print(f"⚠️ Warning: Could not add {file_path}: {e}", "warning")
        
        log_and_print(f"Staged {files_actually_added} config files for {environment}")
        
        if files_actually_added == 0:
            log_and_print(f"❌ No files to commit for {environment}", "error")
            return False
        
        # Create commit
        commit_message = f"Merge branch '{new_branch_name}'\n\nConfig snapshot for {environment} environment\n\nContains {files_actually_added} environment-specific configuration files"
        
        # Configure git user
        with repo.config_writer() as config:
            config.set_value('user', 'name', os.getenv('GIT_USER_NAME', 'Golden Config AI'))
            config.set_value('user', 'email', os.getenv('GIT_USER_EMAIL', 'golden-config@example.com'))
        
        repo.index.commit(commit_message)
        log_and_print(f"Created commit with {files_actually_added} files")
        
        # Push to remote
        log_and_print(f"Pushing branch {new_branch_name} to remote...")
        origin.push(refspec=f'HEAD:refs/heads/{new_branch_name}')
        
        log_and_print(f"✅ Environment-specific config branch {new_branch_name} created with {files_actually_added} files", "info")
        return True
        
    except Exception as e:
        log_and_print(f"❌ Failed to create environment-specific config branch: {e}", "error")
        logger.exception("Detailed error:")
        return False
    
    finally:
        # Cleanup
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                log_and_print(f"⚠️ Failed to cleanup temp directory: {e}", "warning")


def create_selective_golden_branch(
    repo_url: str,
    old_golden_branch: str,
    drift_branch: str,
    new_branch_name: str,
    approved_files: List[str],
    config_paths: List[str],
    gitlab_token: Optional[str] = None
) -> bool:
    """
    Create a new golden branch by merging old golden branch with selected files from drift branch.
    
    Workflow:
    1. Clone old golden branch as base
    2. For each approved file: Copy from drift branch (overwrite)
    3. For each rejected file: Keep from old golden branch (no change)
    4. Commit and push as new golden branch
    
    Args:
        repo_url: Repository URL
        old_golden_branch: Current golden branch name (base for new golden)
        drift_branch: Drift branch name (source for approved files)
        new_branch_name: Name for the new golden branch
        approved_files: List of files to accept from drift branch
        config_paths: List of config file paths/patterns
        gitlab_token: Optional GitLab token for authentication
        
    Returns:
        True if successful, False otherwise
    """
    temp_golden_dir = None
    temp_drift_dir = None
    
    try:
        log_and_print(f"🔄 Creating selective golden branch: {new_branch_name}")
        log_and_print(f"📦 Old Golden: {old_golden_branch}")
        log_and_print(f"📦 Drift: {drift_branch}")
        log_and_print(f"✅ Approved Files: {len(approved_files)}")
        
        # Setup authentication
        auth_url = setup_git_auth(repo_url, gitlab_token)
        
        # Step 1: Clone old golden branch as base
        log_and_print(f"📥 Cloning old golden branch as base...")
        temp_golden_dir = tempfile.mkdtemp(prefix="golden_base_")
        golden_repo = git.Repo.clone_from(auth_url, temp_golden_dir, branch=old_golden_branch, depth=1)
        
        # Step 2: Clone drift branch to get new files
        log_and_print(f"📥 Cloning drift branch to get approved files...")
        temp_drift_dir = tempfile.mkdtemp(prefix="drift_source_")
        drift_repo = git.Repo.clone_from(auth_url, temp_drift_dir, branch=drift_branch, depth=1)
        
        # Step 3: Copy approved files from drift to golden
        log_and_print(f"📝 Copying {len(approved_files)} approved files...")
        files_copied = 0
        for file_path in approved_files:
            try:
                drift_file = Path(temp_drift_dir) / file_path
                golden_file = Path(temp_golden_dir) / file_path
                
                if drift_file.exists():
                    # Ensure parent directory exists
                    golden_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Copy file from drift to golden
                    shutil.copy2(drift_file, golden_file)
                    files_copied += 1
                else:
                    log_and_print(f"⚠️ Warning: {file_path} not found in drift branch", "warning")
            except Exception as e:
                log_and_print(f"⚠️ Error copying {file_path}: {e}", "warning")
        
        log_and_print(f"✅ Copied {files_copied} files from drift to golden base")
        
        # Step 4: Create new orphan branch with the merged state
        log_and_print(f"🌿 Creating new golden branch with merged state...")
        golden_repo.git.checkout('--orphan', new_branch_name)
        
        # Clear index
        golden_repo.git.rm('-rf', '--cached', '.')
        
        # Add all files (old golden + approved drift files)
        golden_repo.git.add('.')
        
        # Verify what we're committing
        try:
            staged_files = golden_repo.git.diff('--cached', '--name-only').strip().split('\n')
            staged_files = [f for f in staged_files if f.strip()]
            log_and_print(f"📋 Staging {len(staged_files)} files for new golden branch")
        except Exception as e:
            log_and_print(f"⚠️ Could not verify staged files: {e}", "warning")
        
        # Create commit
        commit_message = (
            f"Merge branch '{new_branch_name}'\n\n"
            f"Selective certification: {new_branch_name}\n\n"
            f"Base: {old_golden_branch}\n"
            f"Accepted {files_copied} files from drift branch {drift_branch}\n"
            f"Rejected files kept from old golden branch"
        )
        golden_repo.git.commit('-m', commit_message)
        
        # Push new golden branch
        log_and_print(f"📤 Pushing new golden branch to remote...")
        golden_repo.git.push('--set-upstream', 'origin', new_branch_name)
        
        log_and_print(f"✅ Selective golden branch {new_branch_name} created successfully!")
        return True
        
    except GitCommandError as e:
        log_and_print(f"❌ Git error creating selective golden branch: {e}", "error")
        return False
    except Exception as e:
        log_and_print(f"❌ Error creating selective golden branch: {e}", "error")
        return False
    finally:
        # Cleanup temporary directories
        for temp_dir in [temp_golden_dir, temp_drift_dir]:
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    log_and_print(f"⚠️ Failed to cleanup temp directory: {e}", "warning")


def list_branches_by_pattern(
    repo_url: str,
    pattern: str,
    gitlab_token: Optional[str] = None
) -> List[str]:
    """
    List all branches matching a specific pattern.
    
    Args:
        repo_url: Repository URL
        pattern: Pattern to match (e.g., "drift_prod_*")
        gitlab_token: Optional GitLab token for authentication
        
    Returns:
        List of branch names matching the pattern
    """
    temp_dir = None
    try:
        # Create temporary directory
        temp_dir = tempfile.mkdtemp(prefix="git_list_")
        
        # Setup authentication
        auth_url = setup_git_auth(repo_url, gitlab_token)
        
        # Clone with minimal depth
        logger.info(f"Listing branches matching pattern: {pattern}")
        repo = git.Repo.clone_from(auth_url, temp_dir, depth=1, single_branch=False, no_checkout=True)
        
        # Fetch remote refs
        repo.remotes.origin.fetch()
        
        # Get all remote branches
        remote_branches = [ref.name.replace('origin/', '') for ref in repo.remotes.origin.refs]
        
        # Filter by pattern (simple prefix matching)
        pattern_prefix = pattern.replace('*', '')
        matching_branches = [b for b in remote_branches if b.startswith(pattern_prefix)]
        
        logger.info(f"Found {len(matching_branches)} branches matching {pattern}")
        return sorted(matching_branches)
        
    except Exception as e:
        logger.error(f"Error listing branches with pattern {pattern}: {e}")
        return []
    finally:
        # Cleanup temporary directory
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp directory {temp_dir}: {e}")


def delete_remote_branch(
    repo_url: str,
    branch_name: str,
    gitlab_token: Optional[str] = None
) -> bool:
    """
    Delete a branch from the remote repository.
    
    Args:
        repo_url: Repository URL
        branch_name: Branch name to delete
        gitlab_token: Optional GitLab token for authentication
        
    Returns:
        True if successful, False otherwise
    """
    temp_dir = None
    try:
        # Create temporary directory
        temp_dir = tempfile.mkdtemp(prefix="git_delete_")
        
        # Setup authentication
        auth_url = setup_git_auth(repo_url, gitlab_token)
        
        # Clone repository (minimal)
        logger.info(f"Deleting remote branch: {branch_name}")
        repo = git.Repo.clone_from(auth_url, temp_dir, depth=1, single_branch=False, no_checkout=True)
        
        # Delete remote branch
        repo.git.push('origin', '--delete', branch_name)
        
        logger.info(f"✅ Successfully deleted branch {branch_name}")
        return True
        
    except GitCommandError as e:
        logger.error(f"Git error deleting branch {branch_name}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error deleting branch {branch_name}: {e}")
        return False
    finally:
        # Cleanup temporary directory
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp directory {temp_dir}: {e}")


def validate_git_credentials() -> bool:
    """
    Validate that Git credentials are configured.
    
    Returns:
        True if credentials are available, False otherwise
    """
    gitlab_token = os.getenv('GITLAB_TOKEN')
    gitlab_username = os.getenv('GITLAB_USERNAME')
    gitlab_password = os.getenv('GITLAB_PASSWORD')
    
    has_token = bool(gitlab_token)
    has_credentials = bool(gitlab_username and gitlab_password)
    
    return has_token or has_credentials