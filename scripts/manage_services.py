#!/usr/bin/env python3
"""
Service Management Utility Script

This script helps you manage services in the database without hardcoding them in main.py.

Usage:
    python scripts/manage_services.py list
    python scripts/manage_services.py add
    python scripts/manage_services.py update <service_id>
    python scripts/manage_services.py deactivate <service_id>
    python scripts/manage_services.py activate <service_id>
"""

import sys
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from shared.db import (
    init_db, get_all_services, get_service_by_id,
    add_service, update_service, deactivate_service,
    activate_service, delete_service
)


DEFAULT_CONFIG_PATHS = [
    "*.yml", "*.yaml", "*.properties", "*.toml", "*.ini",
    "*.cfg", "*.conf", "*.config",
    "Dockerfile", "docker-compose.yml",
    "pom.xml", "build.gradle", "requirements.txt"
]


def list_services():
    """List all services in the database."""
    print("\n📋 Services in Database:")
    print("=" * 80)
    
    services = get_all_services(active_only=False)
    
    if not services:
        print("❌ No services found in database.")
        print("💡 Run 'python scripts/manage_services.py add' to add a service.")
        return
    
    for service in services:
        status = "✅ Active" if service['is_active'] else "❌ Inactive"
        print(f"\n{status} {service['service_id']}")
        print(f"   Name: {service['service_name']}")
        print(f"   Repo: {service['repo_url']}")
        print(f"   Branch: {service['main_branch']}")
        print(f"   Environments: {', '.join(service['environments'])}")
        if service.get('vsat'):
            print(f"   VSAT: {service['vsat']}")
        if service.get('vsat_url'):
            print(f"   VSAT URL: {service['vsat_url']}")
        if service['description']:
            print(f"   Description: {service['description']}")
        print(f"   Created: {service['created_at']}")
    
    print("\n" + "=" * 80)


def add_service_interactive():
    """Add a service interactively."""
    print("\n➕ Add New Service")
    print("=" * 80)
    
    # Get service details
    service_id = input("Service ID (e.g., cxp_ptg_adapter): ").strip()
    if not service_id:
        print("❌ Service ID is required!")
        return
    
    # Check if already exists
    existing = get_service_by_id(service_id)
    if existing:
        print(f"⚠️ Service '{service_id}' already exists!")
        overwrite = input("Do you want to update it? (y/n): ").strip().lower()
        if overwrite != 'y':
            return
    
    service_name = input("Service Name (e.g., CXP PTG Adapter): ").strip()
    if not service_name:
        print("❌ Service name is required!")
        return
    
    repo_url = input("Repository URL: ").strip()
    if not repo_url:
        print("❌ Repository URL is required!")
        return
    
    main_branch = input("Main Branch (default: main): ").strip() or "main"
    
    environments_str = input("Environments (comma-separated, e.g., prod,alpha,beta1): ").strip()
    if not environments_str:
        print("❌ At least one environment is required!")
        return
    
    environments = [env.strip() for env in environments_str.split(",")]
    
    description = input("Description (optional): ").strip() or None
    
    use_default_config = input("Use default config paths? (y/n): ").strip().lower()
    config_paths = DEFAULT_CONFIG_PATHS if use_default_config == 'y' else None
    
    # Auto-extract VSAT from repo URL
    from shared.db import _extract_vsat_from_url
    detected_vsat, detected_vsat_url = _extract_vsat_from_url(repo_url)
    
    if detected_vsat:
        print(f"\n🔍 Auto-detected from URL:")
        print(f"   VSAT: {detected_vsat}")
        print(f"   VSAT URL: {detected_vsat_url}")
        use_detected = input("Use auto-detected VSAT? (y/n): ").strip().lower()
        if use_detected == 'y':
            vsat = detected_vsat
            vsat_url = detected_vsat_url
        else:
            vsat = input("VSAT group (leave blank to skip): ").strip() or None
            vsat_url = input("VSAT URL (leave blank to skip): ").strip() or None
    else:
        print("\n⚠️  Could not auto-detect VSAT from URL")
        vsat = input("VSAT group (leave blank to skip): ").strip() or None
        vsat_url = input("VSAT URL (leave blank to skip): ").strip() or None
    
    # Add service
    try:
        add_service(
            service_id=service_id,
            service_name=service_name,
            repo_url=repo_url,
            main_branch=main_branch,
            environments=environments,
            config_paths=config_paths,
            vsat=vsat,
            vsat_url=vsat_url,
            description=description
        )
        print(f"\n✅ Service '{service_id}' added successfully!")
    except Exception as e:
        print(f"\n❌ Error adding service: {e}")


def update_service_interactive(service_id: str):
    """Update a service interactively."""
    service = get_service_by_id(service_id)
    if not service:
        print(f"❌ Service '{service_id}' not found!")
        return
    
    print(f"\n✏️ Update Service: {service_id}")
    print("=" * 80)
    print("Press Enter to keep current value\n")
    
    updates = {}
    
    new_name = input(f"Service Name [{service['service_name']}]: ").strip()
    if new_name:
        updates['service_name'] = new_name
    
    new_repo = input(f"Repository URL [{service['repo_url']}]: ").strip()
    if new_repo:
        updates['repo_url'] = new_repo
    
    new_branch = input(f"Main Branch [{service['main_branch']}]: ").strip()
    if new_branch:
        updates['main_branch'] = new_branch
    
    current_envs = ','.join(service['environments'])
    new_envs = input(f"Environments [{current_envs}]: ").strip()
    if new_envs:
        updates['environments'] = [e.strip() for e in new_envs.split(",")]
    
    new_desc = input(f"Description [{service.get('description', 'None')}]: ").strip()
    if new_desc:
        updates['description'] = new_desc
    
    if not updates:
        print("ℹ️ No changes made.")
        return
    
    try:
        update_service(service_id, updates)
        print(f"\n✅ Service '{service_id}' updated successfully!")
    except Exception as e:
        print(f"\n❌ Error updating service: {e}")


def deactivate_service_cmd(service_id: str):
    """Deactivate a service."""
    service = get_service_by_id(service_id)
    if not service:
        print(f"❌ Service '{service_id}' not found!")
        return
    
    confirm = input(f"⚠️ Deactivate service '{service_id}'? (y/n): ").strip().lower()
    if confirm == 'y':
        deactivate_service(service_id)
        print(f"✅ Service '{service_id}' deactivated.")
    else:
        print("ℹ️ Cancelled.")


def activate_service_cmd(service_id: str):
    """Activate a service."""
    service = get_service_by_id(service_id)
    if not service:
        print(f"❌ Service '{service_id}' not found!")
        return
    
    activate_service(service_id)
    print(f"✅ Service '{service_id}' activated.")


def show_help():
    """Show help message."""
    print("""
Service Management Utility
==========================

Commands:
    list                    - List all services
    add                     - Add a new service (interactive)
    update <service_id>     - Update a service (interactive)
    deactivate <service_id> - Deactivate a service
    activate <service_id>   - Activate a service
    help                    - Show this help message

Examples:
    python scripts/manage_services.py list
    python scripts/manage_services.py add
    python scripts/manage_services.py update cxp_ptg_adapter
    python scripts/manage_services.py deactivate cxp_ptg_adapter
    """)


def main():
    """Main entry point."""
    # Initialize database
    init_db()
    
    if len(sys.argv) < 2:
        print("❌ Missing command!")
        show_help()
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "list":
        list_services()
    
    elif command == "add":
        add_service_interactive()
    
    elif command == "update":
        if len(sys.argv) < 3:
            print("❌ Missing service_id!")
            print("Usage: python scripts/manage_services.py update <service_id>")
            sys.exit(1)
        update_service_interactive(sys.argv[2])
    
    elif command == "deactivate":
        if len(sys.argv) < 3:
            print("❌ Missing service_id!")
            print("Usage: python scripts/manage_services.py deactivate <service_id>")
            sys.exit(1)
        deactivate_service_cmd(sys.argv[2])
    
    elif command == "activate":
        if len(sys.argv) < 3:
            print("❌ Missing service_id!")
            print("Usage: python scripts/manage_services.py activate <service_id>")
            sys.exit(1)
        activate_service_cmd(sys.argv[2])
    
    elif command == "help":
        show_help()
    
    else:
        print(f"❌ Unknown command: {command}")
        show_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

