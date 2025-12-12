# VSAT Automation - Integrated with main.py

## ✅ NO SEPARATE SCRIPTS NEEDED!

The VSAT automation is **fully integrated** into `main.py`. When you run your backend server, VSAT automation starts automatically.

## How It Works

Just run `main.py` as you normally would:
```bash
python main.py
```

The system automatically:
- ✅ Starts VSAT file watcher
- ✅ Starts weekly scheduler
- ✅ Runs initial sync
- ✅ Detects config changes instantly
- ✅ Creates golden branches (parallel, fast)

## How the System Detects New VSATs

### Current Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   vsat_scheduler.py                          │
│  (Must be running for automation to work)                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. File Watcher (Continuous)                               │
│     • Monitors config/vsat_master.yaml                      │
│     • Detects changes within 5 seconds                      │
│     • Triggers immediate sync                               │
│                                                              │
│  2. Weekly Scheduler (Cron)                                 │
│     • Runs every Sunday at 2 AM                             │
│     • Full sync of all VSATs                                │
│     • Catches new repos in existing VSATs                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                            ↓
                   When config changes
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                     vsat_sync.py                             │
│  (Triggered by scheduler or manually)                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Load config/vsat_master.yaml                            │
│  2. For each VSAT:                                          │
│     • Fetch all repos from GitLab                           │
│     • Check for main branch (parallel)                      │
│     • Filter by patterns                                    │
│  3. Sync to database:                                       │
│     • Add new services                                      │
│     • Update changed services                               │
│     • Remove deleted services                               │
│  4. Create golden branches (parallel, 5x faster)            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Setup Options

### Option 1: Manual Start (Temporary)

**Use case**: Testing, development

```bash
# Start scheduler (runs in foreground)
python scripts/vsat_scheduler.py

# Keep terminal open - scheduler is running
# Stop with Ctrl+C
```

**Limitations**:
- ❌ Stops when terminal closes
- ❌ Doesn't survive system reboot
- ❌ No automatic restart on crash

---

### Option 2: Background Process (Basic)

**Use case**: Quick deployment, testing

```bash
# Start in background
nohup python scripts/vsat_scheduler.py > logs/vsat_scheduler.log 2>&1 &

# Check if running
ps aux | grep vsat_scheduler

# Stop
pkill -f vsat_scheduler.py
```

**Limitations**:
- ❌ Doesn't survive system reboot
- ❌ No automatic restart on crash
- ✅ Runs in background

---

### Option 3: System Service (Recommended)

**Use case**: Production, permanent deployment

#### Automated Setup

```bash
# Run setup script
./scripts/setup_vsat_service.sh
```

This will:
- ✅ Create system service (macOS LaunchAgent or Linux systemd)
- ✅ Start automatically on system boot
- ✅ Restart automatically if it crashes
- ✅ Run in background permanently
- ✅ Redirect logs to files

#### Manual Setup (macOS)

1. **Create LaunchAgent**:

```bash
# Create plist file
cat > ~/Library/LaunchAgents/com.verizon.vsat-scheduler.plist <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.verizon.vsat-scheduler</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>/path/to/gcpv1/scripts/vsat_scheduler.py</string>
    </array>
    
    <key>WorkingDirectory</key>
    <string>/path/to/gcpv1</string>
    
    <key>RunAtLoad</key>
    <true/>
    
    <key>KeepAlive</key>
    <true/>
    
    <key>StandardOutPath</key>
    <string>/path/to/gcpv1/logs/vsat_scheduler.log</string>
    
    <key>StandardErrorPath</key>
    <string>/path/to/gcpv1/logs/vsat_scheduler_error.log</string>
</dict>
</plist>
EOF

# Load the service
launchctl load ~/Library/LaunchAgents/com.verizon.vsat-scheduler.plist
```

2. **Control Commands**:

```bash
# Start
launchctl start com.verizon.vsat-scheduler

# Stop
launchctl stop com.verizon.vsat-scheduler

# Status
launchctl list | grep vsat-scheduler

# View logs
tail -f logs/vsat_scheduler.log
```

#### Manual Setup (Linux)

1. **Create systemd service**:

```bash
# Create service file
sudo tee /etc/systemd/system/vsat-scheduler.service > /dev/null <<'EOF'
[Unit]
Description=VSAT Master Config Sync Scheduler
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/path/to/gcpv1
ExecStart=/usr/bin/python3 /path/to/gcpv1/scripts/vsat_scheduler.py
Restart=always
RestartSec=10
StandardOutput=append:/path/to/gcpv1/logs/vsat_scheduler.log
StandardError=append:/path/to/gcpv1/logs/vsat_scheduler_error.log

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
sudo systemctl daemon-reload

# Enable (start on boot)
sudo systemctl enable vsat-scheduler

# Start now
sudo systemctl start vsat-scheduler
```

2. **Control Commands**:

```bash
# Start
sudo systemctl start vsat-scheduler

# Stop
sudo systemctl stop vsat-scheduler

# Restart
sudo systemctl restart vsat-scheduler

# Status
sudo systemctl status vsat-scheduler

# View logs
sudo journalctl -u vsat-scheduler -f
```

---

## How It Works: Complete Flow

### Scenario 1: Adding a New VSAT

**Manual Steps**:
```bash
1. Edit config/vsat_master.yaml
2. Add new VSAT:
   - name: new_team
     url: https://gitlab.verizon.com/new_team
     enabled: true
3. Save file
```

**Automatic Steps** (if scheduler running):
```
✅ File watcher detects change (within 5 seconds)
✅ Triggers immediate sync
✅ Fetches all repos from new_team VSAT
✅ Checks for main branch (parallel, fast)
✅ Adds services to database
✅ Creates golden branches (parallel, 5x faster)
✅ Logs results
```

**Timeline**: ~2-5 minutes for 50 services (with parallel branch creation)

### Scenario 2: New Repo Added to Existing VSAT

**No manual steps needed!**

**Automatic Steps** (weekly sync):
```
✅ Sunday 2 AM: Weekly sync runs
✅ Fetches latest repos from all VSATs
✅ Detects new repo
✅ Adds to database
✅ Creates golden branches
```

### Scenario 3: Removing a VSAT

**Manual Steps**:
```bash
1. Edit config/vsat_master.yaml
2. Remove VSAT or set enabled: false
3. Save file
```

**Automatic Steps** (if scheduler running):
```
✅ File watcher detects change
✅ Triggers immediate sync
✅ Identifies services from removed VSAT
✅ Marks for deletion (with safety checks)
✅ Removes from database
✅ Logs results
```

---

## Verification

### Check if Scheduler is Running

**macOS**:
```bash
launchctl list | grep vsat-scheduler
# Should show: com.verizon.vsat-scheduler
```

**Linux**:
```bash
sudo systemctl status vsat-scheduler
# Should show: active (running)
```

**Any system**:
```bash
ps aux | grep vsat_scheduler
```

### Check Logs

```bash
# Real-time logs
tail -f logs/vsat_scheduler.log

# Recent activity
tail -100 logs/vsat_scheduler.log

# Search for errors
grep ERROR logs/vsat_scheduler.log
```

### Test File Watcher

```bash
# Edit config
nano config/vsat_master.yaml

# Add a comment and save
# last_updated: "2024-12-12T12:00:00Z"  # Test change

# Check logs immediately
tail -f logs/vsat_scheduler.log

# Should see:
# 📝 Config file changed - triggering sync
# 🔄 Syncing VSAT: ...
```

---

## Troubleshooting

### Issue: Scheduler not running

**Check**:
```bash
ps aux | grep vsat_scheduler
launchctl list | grep vsat-scheduler  # macOS
systemctl status vsat-scheduler       # Linux
```

**Fix**:
```bash
# macOS
launchctl load ~/Library/LaunchAgents/com.verizon.vsat-scheduler.plist

# Linux
sudo systemctl start vsat-scheduler
```

### Issue: New VSAT not detected

**Check**:
1. Is scheduler running?
2. Is file watcher active?
3. Are logs showing activity?

**Fix**:
```bash
# Force manual sync
python scripts/vsat_sync.py --force

# Restart scheduler
# macOS
launchctl stop com.verizon.vsat-scheduler
launchctl start com.verizon.vsat-scheduler

# Linux
sudo systemctl restart vsat-scheduler
```

### Issue: Changes not triggering sync

**Check logs**:
```bash
tail -f logs/vsat_scheduler.log
```

**Common causes**:
- Scheduler not running
- File watcher crashed (check error logs)
- Config file syntax error (prevents loading)

**Fix**:
```bash
# Validate config
python -c "import yaml; yaml.safe_load(open('config/vsat_master.yaml'))"

# Restart scheduler
```

---

## Summary

### ✅ What's Automated

- File watching (detects config changes instantly)
- Weekly syncing (catches new repos)
- Service discovery (fetches from GitLab)
- Golden branch creation (parallel, fast)
- Error handling and retries

### ⚠️ What Requires Setup

- Starting the scheduler initially
- Setting up as system service (for permanent operation)
- Monitoring logs periodically

### 🚀 Recommended Setup

**For Production**:
```bash
# One-time setup
./scripts/setup_vsat_service.sh

# Verify
tail -f logs/vsat_scheduler.log

# Done! System is now fully automated
```

**For Development**:
```bash
# Start in terminal
python scripts/vsat_scheduler.py

# Keep terminal open while testing
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Setup service | `./scripts/setup_vsat_service.sh` |
| Start (macOS) | `launchctl start com.verizon.vsat-scheduler` |
| Start (Linux) | `sudo systemctl start vsat-scheduler` |
| Stop (macOS) | `launchctl stop com.verizon.vsat-scheduler` |
| Stop (Linux) | `sudo systemctl stop vsat-scheduler` |
| Status (macOS) | `launchctl list \| grep vsat` |
| Status (Linux) | `sudo systemctl status vsat-scheduler` |
| View logs | `tail -f logs/vsat_scheduler.log` |
| Manual sync | `python scripts/vsat_sync.py --force` |
| Test mode | `python scripts/vsat_sync.py --dry-run` |

