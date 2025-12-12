#!/bin/bash
# Setup VSAT Scheduler as a System Service
# This ensures the scheduler runs automatically on system startup

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PYTHON_PATH=$(which python3)
USER=$(whoami)

echo "=========================================="
echo "VSAT Scheduler Service Setup"
echo "=========================================="
echo ""
echo "Project root: $PROJECT_ROOT"
echo "Python path: $PYTHON_PATH"
echo "User: $USER"
echo ""

# For macOS (LaunchAgent)
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "Setting up macOS LaunchAgent..."
    
    PLIST_PATH="$HOME/Library/LaunchAgents/com.verizon.vsat-scheduler.plist"
    
    cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.verizon.vsat-scheduler</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_PATH</string>
        <string>$PROJECT_ROOT/scripts/vsat_scheduler.py</string>
    </array>
    
    <key>WorkingDirectory</key>
    <string>$PROJECT_ROOT</string>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    
    <key>RunAtLoad</key>
    <true/>
    
    <key>KeepAlive</key>
    <true/>
    
    <key>StandardOutPath</key>
    <string>$PROJECT_ROOT/logs/vsat_scheduler.log</string>
    
    <key>StandardErrorPath</key>
    <string>$PROJECT_ROOT/logs/vsat_scheduler_error.log</string>
</dict>
</plist>
EOF
    
    # Create logs directory
    mkdir -p "$PROJECT_ROOT/logs"
    
    # Load the service
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    launchctl load "$PLIST_PATH"
    
    echo "✅ macOS LaunchAgent installed: $PLIST_PATH"
    echo ""
    echo "Control commands:"
    echo "  Start:  launchctl start com.verizon.vsat-scheduler"
    echo "  Stop:   launchctl stop com.verizon.vsat-scheduler"
    echo "  Status: launchctl list | grep vsat-scheduler"
    echo "  Logs:   tail -f $PROJECT_ROOT/logs/vsat_scheduler.log"
    echo ""

# For Linux (systemd)
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "Setting up Linux systemd service..."
    
    SERVICE_FILE="/etc/systemd/system/vsat-scheduler.service"
    
    sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=VSAT Master Config Sync Scheduler
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_ROOT
ExecStart=$PYTHON_PATH $PROJECT_ROOT/scripts/vsat_scheduler.py
Restart=always
RestartSec=10
StandardOutput=append:$PROJECT_ROOT/logs/vsat_scheduler.log
StandardError=append:$PROJECT_ROOT/logs/vsat_scheduler_error.log

[Install]
WantedBy=multi-user.target
EOF
    
    # Create logs directory
    mkdir -p "$PROJECT_ROOT/logs"
    
    # Reload systemd and enable service
    sudo systemctl daemon-reload
    sudo systemctl enable vsat-scheduler.service
    sudo systemctl start vsat-scheduler.service
    
    echo "✅ Linux systemd service installed: $SERVICE_FILE"
    echo ""
    echo "Control commands:"
    echo "  Start:   sudo systemctl start vsat-scheduler"
    echo "  Stop:    sudo systemctl stop vsat-scheduler"
    echo "  Status:  sudo systemctl status vsat-scheduler"
    echo "  Restart: sudo systemctl restart vsat-scheduler"
    echo "  Logs:    sudo journalctl -u vsat-scheduler -f"
    echo ""

else
    echo "❌ Unsupported OS: $OSTYPE"
    echo ""
    echo "Manual setup required. Run in background:"
    echo "  nohup python scripts/vsat_scheduler.py > logs/vsat_scheduler.log 2>&1 &"
    exit 1
fi

echo "=========================================="
echo "✅ Setup Complete!"
echo "=========================================="
echo ""
echo "The VSAT scheduler is now running and will:"
echo "  • Start automatically on system boot"
echo "  • Watch for config file changes"
echo "  • Run weekly syncs (Sunday 2 AM)"
echo "  • Restart automatically if it crashes"
echo ""
echo "Next steps:"
echo "  1. Edit config/vsat_master.yaml to add VSATs"
echo "  2. Check logs to verify sync is working"
echo "  3. Monitor for errors"

