######################################## gitlab code #############################################

"""
Script to list all services/repositories in a GitLab group (VSAT)
"""
import os
import sys
import requests
import json
from typing import List, Dict, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add the parent directory to the path to import shared modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared.config import Config

def check_branch_exists(project_id: int, branch_name: str, gitlab_url: str, headers: dict, session: requests.Session = None) -> bool:
    """
    Check if a specific branch exists in a project
    
    Args:
        project_id: The project ID
        branch_name: The branch name to check (e.g., 'main', 'master')
        gitlab_url: Base GitLab URL
        headers: Request headers with authentication
        session: Optional requests Session for connection pooling
    
    Returns:
        True if branch exists, False otherwise
    """
    # URL encode the project ID
    encoded_project_id = str(project_id).replace('/', '%2F')
    encoded_branch = branch_name.replace('/', '%2F')
    
    # API endpoint for specific branch
    api_url = f"{gitlab_url}/api/v4/projects/{encoded_project_id}/repository/branches/{encoded_branch}"
    
    try:
        # Use session for connection pooling if provided, otherwise use requests directly
        http_client = session if session else requests
        response = http_client.get(api_url, headers=headers, verify=True, timeout=5)
        return response.status_code == 200
    except:
        return False


def get_gitlab_group_projects(group_path: str, gitlab_url: str = "https://gitlab.verizon.com", 
                               private_token: str = None) -> Tuple[List[Dict], int]:
    """
    Fetch all projects in a GitLab group and filter by 'main' branch presence
    
    Args:
        group_path: The group path (e.g., 'ev6v_cxp')
        gitlab_url: Base GitLab URL
        private_token: GitLab personal access token (optional if using session auth)
    
    Returns:
        Tuple of (filtered_projects, total_count)
        - filtered_projects: List of projects that have 'main' branch
        - total_count: Total number of projects fetched (for statistics)
    """
    # URL encode the group path
    encoded_group = group_path.replace('/', '%2F')
    
    # API endpoint for group projects
    api_url = f"{gitlab_url}/api/v4/groups/{encoded_group}/projects"
    
    headers = {}
    if private_token:
        headers['PRIVATE-TOKEN'] = private_token
    
    # Create a session for connection pooling (reuses TCP connections)
    session = requests.Session()
    session.headers.update(headers)
    
    all_projects = []
    page = 1
    per_page = 100  # Maximum allowed by GitLab API
    
    print(f"Fetching projects from group: {group_path}")
    print(f"API URL: {api_url}\n")
    
    while True:
        params = {
            'page': page,
            'per_page': per_page,
            'include_subgroups': False,  # Set to True if you want subgroups too
            'order_by': 'name',
            'sort': 'asc'
        }
        
        try:
            response = requests.get(api_url, headers=headers, params=params, verify=True)
            
            if response.status_code == 401:
                print("Authentication required. You need to provide a GitLab Personal Access Token.")
                print("\nTo create a token:")
                print("1. Go to https://gitlab.verizon.com/-/profile/personal_access_tokens")
                print("2. Create a token with 'read_api' scope")
                print("3. Run this script with the token\n")
                return [], 0
            
            response.raise_for_status()
            
            projects = response.json()
            
            if not projects:
                break
            
            all_projects.extend(projects)
            print(f"Fetched page {page}: {len(projects)} projects")
            
            # Check if there are more pages
            if len(projects) < per_page:
                break
            
            page += 1
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching projects: {e}")
            break
    
    # Close session after fetching all projects
    session.close()
    
    total_count = len(all_projects)
    
    # Optimized: Check branches only when needed, using parallel processing
    print(f"\nChecking branches for all {total_count} projects...")
    print("Using optimized approach: checking default branch first, then 'main' in parallel if needed...\n")
    
    # Separate projects by default branch (fast path vs slow path)
    projects_with_main_default = []
    projects_to_check = []
    
    for project in all_projects:
        default_branch = project.get('default_branch', 'unknown')
        
        # Fast path: default branch is 'main' - no API call needed!
        if default_branch == 'main':
            project['has_main_branch'] = True
            project['has_master_branch'] = False
            projects_with_main_default.append(project)
        else:
            # Slow path: need to check if 'main' exists
            projects_to_check.append(project)
    
    print(f"✓ {len(projects_with_main_default)} projects have default='main' (skipping API calls)")
    print(f"  Checking 'main' branch for {len(projects_to_check)} projects in parallel...\n")
    
    # Parallel check for projects where default != 'main'
    filtered_projects = list(projects_with_main_default)  # Start with fast path projects
    
    if projects_to_check:
        # Use ThreadPoolExecutor for parallel API calls
        # Create a session per thread for connection pooling
        def check_project_main(project):
            """Check if project has 'main' branch"""
            project_id = project['id']
            # Each thread gets its own session for connection pooling
            thread_session = requests.Session()
            thread_session.headers.update(headers)
            has_main = check_branch_exists(project_id, 'main', gitlab_url, headers, thread_session)
            thread_session.close()  # Clean up session
            project['has_main_branch'] = has_main
            project['has_master_branch'] = False
            return project, has_main
        
        # Process in parallel (use 20-30 workers for optimal speed)
        # GitLab API can typically handle 20-30 concurrent requests without rate limiting
        max_workers = min(25, len(projects_to_check))  # Cap at 25 concurrent requests
        
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_project = {
                executor.submit(check_project_main, project): project 
                for project in projects_to_check
            }
            
            # Process results as they complete
            for future in as_completed(future_to_project):
                try:
                    project, has_main = future.result()
                    completed += 1
                    
                    # Only include if 'main' branch exists
                    if has_main:
                        filtered_projects.append(project)
                    
                    # Progress update every 10 completions
                    if completed % 10 == 0 or completed == len(projects_to_check):
                        print(f"  Processed {completed}/{len(projects_to_check)} branch checks... "
                              f"({len(filtered_projects)} projects with 'main' branch so far)")
                
                except Exception as e:
                    completed += 1
                    project = future_to_project[future]
                    print(f"  ⚠️  Error checking project '{project['name']}': {e}")
    
    print(f"\n✓ Completed branch checks for all {total_count} projects")
    print(f"✓ Filtered to {len(filtered_projects)} projects with 'main' branch")
    print(f"✓ Speed improvement: Used parallel processing ({max_workers if projects_to_check else 0} concurrent requests)\n")
    
    return filtered_projects, total_count  # Return filtered projects and total count


def display_projects(projects: List[Dict]):
    """Display projects in a readable format"""
    print(f"\n{'='*80}")
    print(f"Total Services Found: {len(projects)}")
    print(f"{'='*80}\n")
    
    for i, project in enumerate(projects, 1):
        print(f"{i}. {project['name']}")
        print(f"   URL: {project['web_url']}")
        print(f"   Path: {project['path_with_namespace']}")
        print(f"   Default Branch: {project.get('default_branch', 'unknown')}")
        print(f"   Has 'main' branch: {'✓' if project.get('has_main_branch') else '✗'}")
        print(f"   Has 'master' branch: {'✓' if project.get('has_master_branch') else '✗'}")
        if project.get('description'):
            print(f"   Description: {project['description']}")
        print()


def save_to_file(projects: List[Dict], filename: str = 'gitlab_services.json'):
    """Save projects list to a JSON file"""
    
    # Check if file exists to preserve any additional data
    existing_data = {}
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                existing_data = json.load(f)
                print(f"📝 Updating existing file: {filename}")
        except:
            print(f"📝 Creating new file: {filename}")
    
    # Group services by default branch
    branch_stats = {}
    main_branch_stats = {
        'has_main': 0,
        'has_master': 0,
        'has_both': 0,
        'has_neither': 0
    }
    
    for p in projects:
        # Default branch statistics
        branch = p.get('default_branch', 'unknown')
        branch_stats[branch] = branch_stats.get(branch, 0) + 1
        
        # Main/Master branch existence statistics
        has_main = p.get('has_main_branch', False)
        has_master = p.get('has_master_branch', False)
        
        if has_main:
            main_branch_stats['has_main'] += 1
        if has_master:
            main_branch_stats['has_master'] += 1
        if has_main and has_master:
            main_branch_stats['has_both'] += 1
        if not has_main and not has_master:
            main_branch_stats['has_neither'] += 1
    
    output = {
        'total_count': len(projects),
        'last_updated': datetime.now().isoformat(),
        'default_branch_statistics': branch_stats,
        'branch_existence_statistics': {
            'services_with_main_branch': main_branch_stats['has_main'],
            'services_with_master_branch': main_branch_stats['has_master'],
            'services_with_both_main_and_master': main_branch_stats['has_both'],
            'services_with_neither_main_nor_master': main_branch_stats['has_neither']
        },
        'services': [
            {
                'name': p['name'],
                'path': p['path'],
                'full_path': p['path_with_namespace'],
                'url': p['web_url'],
                'ssh_url': p['ssh_url_to_repo'],
                'http_url': p['http_url_to_repo'],
                'description': p.get('description', ''),
                'last_activity': p.get('last_activity_at', ''),
                'default_branch': p.get('default_branch', 'unknown'),
                'has_main_branch': p.get('has_main_branch', False),
                'has_master_branch': p.get('has_master_branch', False),
                'created_at': p.get('created_at', ''),
                'archived': p.get('archived', False)
            }
            for p in projects
        ]
    }
    
    with open(filename, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n{'='*80}")
    print(f"Results saved to: {filename}")
    print(f"{'='*80}\n")
    
    # Display branch statistics
    print(f"{'='*80}")
    print(f"Branch Existence Statistics:")
    print(f"{'='*80}")
    print(f"  Services with 'main' branch: {main_branch_stats['has_main']}")
    print(f"  Services with 'master' branch: {main_branch_stats['has_master']}")
    print(f"  Services with both 'main' and 'master': {main_branch_stats['has_both']}")
    print(f"  Services with neither 'main' nor 'master': {main_branch_stats['has_neither']}")
    print(f"{'='*80}\n")
    
    print(f"{'='*80}")
    print(f"Default Branch Statistics:")
    print(f"{'='*80}")
    for branch, count in sorted(branch_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"  {branch}: {count} services")
    print(f"{'='*80}\n")


def main():
    # Configuration
    GROUP_PATH = "ev6v_cxp"
    GITLAB_URL = "https://gitlab.verizon.com"
    
    # Load configuration from shared config (uses environment variables)
    config = Config()
    token = config.gitlab_token
    
    if not token:
        print("❌ GitLab Personal Access Token not found in environment.")
        print("Please ensure GITLAB_TOKEN is set in your environment or .env file")
        print("\nYou can set it using: $env:GITLAB_TOKEN='your-token-here'")
        return
    
    print(f"✓ Using GitLab token from environment configuration")
    
    # Fetch projects (returns filtered projects and total count)
    projects, total_count = get_gitlab_group_projects(GROUP_PATH, GITLAB_URL, token)
    
    if projects:
        print(f"\n{'='*80}")
        print(f"Summary:")
        print(f"  Total projects fetched: {total_count}")
        print(f"  Projects with 'main' branch: {len(projects)}")
        print(f"  Projects filtered out (no 'main' branch): {total_count - len(projects)}")
        print(f"{'='*80}\n")
        
        # Display results
        display_projects(projects)
        
        # Save to file
        save_to_file(projects, 'ev6v_cxp_services.json')
        
        # Create a simple text list with branch info
        with open('ev6v_cxp_services.txt', 'w') as f:
            f.write(f"Services in {GROUP_PATH} (with 'main' branch)\n")
            f.write(f"{'='*80}\n\n")
            for i, project in enumerate(projects, 1):
                f.write(f"{i}. {project['name']}\n")
                f.write(f"   URL: {project['web_url']}\n")
                f.write(f"   Default Branch: {project.get('default_branch', 'unknown')}\n")
                f.write(f"   Has 'main' branch: {'Yes' if project.get('has_main_branch') else 'No'}\n")
                f.write(f"   Has 'master' branch: {'Yes' if project.get('has_master_branch') else 'No'}\n\n")
        
        print(f"Simple text list saved to: ev6v_cxp_services.txt\n")
    else:
        print("No projects found or unable to fetch projects.")


if __name__ == "__main__":
    main()




