#!/usr/bin/env python3
"""
VSAT Sync Scheduler - Automated Service Discovery

Runs VSAT sync on schedule:
1. File watcher: Sync immediately when config changes (checks every minute)
2. Weekly sync: Every Sunday at 2 AM (configurable)
3. Manual trigger: Can be triggered via API

Usage:
    python scripts/vsat_scheduler.py
"""

import sys
import time
import logging
from pathlib import Path
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from scripts.vsat_sync import run_sync, CONFIG_FILE

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ConfigFileHandler(FileSystemEventHandler):
    """Handle config file changes"""
    
    def __init__(self, scheduler):
        self.scheduler = scheduler
        self.last_sync = datetime.now()
        self.debounce_seconds = 5  # Avoid multiple syncs for same change
    
    def on_modified(self, event):
        if event.src_path.endswith('vsat_master.yaml'):
            # Debounce: Only sync if enough time has passed
            now = datetime.now()
            if (now - self.last_sync).total_seconds() > self.debounce_seconds:
                logger.info("📝 Config file changed - triggering sync")
                self.last_sync = now
                self.scheduler.add_job(
                    run_sync,
                    kwargs={'force': True},
                    id='config_change_sync',
                    replace_existing=True
                )


def scheduled_sync():
    """Scheduled sync job"""
    logger.info("⏰ Scheduled sync triggered")
    run_sync(force=True)


def main():
    """Main scheduler loop"""
    logger.info("="*80)
    logger.info("🚀 VSAT SYNC SCHEDULER STARTING")
    logger.info("="*80)
    logger.info("")
    logger.info("📅 Scheduled syncs:")
    logger.info("   • Weekly: Every Sunday at 2:00 AM")
    logger.info("   • Config watch: Continuous (detects changes)")
    logger.info("")
    logger.info("🛑 Press Ctrl+C to stop")
    logger.info("="*80)
    
    # Create scheduler
    scheduler = BackgroundScheduler()
    
    # Add weekly sync job (every Sunday at 2 AM)
    scheduler.add_job(
        scheduled_sync,
        CronTrigger(day_of_week='sun', hour=2, minute=0),
        id='weekly_sync',
        name='Weekly VSAT Sync',
        replace_existing=True
    )
    
    # Start scheduler
    scheduler.start()
    logger.info("✅ Scheduler started")
    
    # Setup file watcher for config changes
    config_dir = CONFIG_FILE.parent
    event_handler = ConfigFileHandler(scheduler)
    observer = Observer()
    observer.schedule(event_handler, str(config_dir), recursive=False)
    observer.start()
    logger.info(f"✅ File watcher started: {config_dir}")
    
    # Run initial sync
    logger.info("\n🔄 Running initial sync...")
    run_sync(force=False)
    
    # Keep running
    try:
        while True:
            time.sleep(60)  # Check every minute
    except (KeyboardInterrupt, SystemExit):
        logger.info("\n🛑 Stopping scheduler...")
        scheduler.shutdown()
        observer.stop()
        observer.join()
        logger.info("✅ Scheduler stopped")


if __name__ == "__main__":
    main()

