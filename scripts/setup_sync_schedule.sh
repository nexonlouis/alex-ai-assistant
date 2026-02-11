#!/bin/bash
# Setup daily database sync schedule using macOS launchd
#
# This script creates a launchd job that runs the sync every day at 2:00 AM
# The sync pushes local Alex database to remote Neon database

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLIST_NAME="com.alex.dbsync"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
LOG_DIR="$HOME/.alex/logs"
PYTHON_PATH="${PYTHON_PATH:-/opt/anaconda3/bin/python}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================"
echo "Alex Database Sync Scheduler Setup"
echo "========================================"
echo

# Check if Python exists
if [ ! -f "$PYTHON_PATH" ]; then
    echo -e "${YELLOW}Warning: Python not found at $PYTHON_PATH${NC}"
    echo "Trying to find Python..."
    if command -v python3 &> /dev/null; then
        PYTHON_PATH=$(which python3)
        echo "Found Python at: $PYTHON_PATH"
    else
        echo -e "${RED}Error: Python not found. Please set PYTHON_PATH environment variable.${NC}"
        exit 1
    fi
fi

# Create log directory
mkdir -p "$LOG_DIR"

# Check if remote URI is configured
if [ -z "$REMOTE_POSTGRES_URI" ] && [ -z "$NEON_POSTGRES_URI" ]; then
    # Try to extract from .env
    if [ -f "$PROJECT_DIR/.env" ]; then
        REMOTE_URI=$(grep "^POSTGRES_URI=" "$PROJECT_DIR/.env" | cut -d'=' -f2-)
        if [[ "$REMOTE_URI" == *"neon.tech"* ]] || [[ "$REMOTE_URI" == *"supabase"* ]]; then
            export REMOTE_POSTGRES_URI="$REMOTE_URI"
            echo -e "${GREEN}✓ Found remote database URI in .env${NC}"
        fi
    fi
fi

if [ -z "$REMOTE_POSTGRES_URI" ] && [ -z "$NEON_POSTGRES_URI" ]; then
    echo -e "${YELLOW}Warning: REMOTE_POSTGRES_URI not set.${NC}"
    echo "The sync script will try to read from .env file at runtime."
fi

# Unload existing job if present
if launchctl list | grep -q "$PLIST_NAME"; then
    echo "Unloading existing sync job..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi

# Create the launchd plist
echo "Creating launchd plist at $PLIST_PATH..."

cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>-m</string>
        <string>alex.sync.db_sync</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>${PROJECT_DIR}</string>
        <key>LOCAL_POSTGRES_URI</key>
        <string>postgresql://localhost:5432/alex</string>
    </dict>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>2</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>${LOG_DIR}/sync.log</string>

    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/sync.error.log</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF

echo -e "${GREEN}✓ Created plist file${NC}"

# Load the job
echo "Loading launchd job..."
launchctl load "$PLIST_PATH"

if launchctl list | grep -q "$PLIST_NAME"; then
    echo -e "${GREEN}✓ Sync job loaded successfully${NC}"
else
    echo -e "${RED}✗ Failed to load sync job${NC}"
    exit 1
fi

echo
echo "========================================"
echo "Setup Complete!"
echo "========================================"
echo
echo "Schedule: Daily at 2:00 AM"
echo "Logs: $LOG_DIR/sync.log"
echo
echo "Commands:"
echo "  Run sync now:     $PYTHON_PATH -m alex.sync.db_sync"
echo "  Check status:     $PYTHON_PATH -m alex.sync.db_sync --status"
echo "  Force full sync:  $PYTHON_PATH -m alex.sync.db_sync --force-full"
echo "  View logs:        tail -f $LOG_DIR/sync.log"
echo "  Unload schedule:  launchctl unload $PLIST_PATH"
echo "  Reload schedule:  launchctl unload $PLIST_PATH && launchctl load $PLIST_PATH"
echo
