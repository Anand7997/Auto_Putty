#!/bin/bash

# IXIGO Test Automation - Isolated VNC Streaming Setup Script
# Enhanced version that supports multiple isolated sessions
# Usage: ./start_stream.sh <display_id>

set -e  # Exit on any error

# Configuration - can be overridden by arguments
DISPLAY_ID=${1:-1}

# Special handling for display 0 (global server)
if [ "$DISPLAY_ID" -eq 0 ]; then
    VNC_PORT=5900
    NOVNC_PORT=6005  # Global noVNC port as expected by the system
else
    VNC_PORT=$((5900 + DISPLAY_ID))
    NOVNC_PORT=$((6080 + DISPLAY_ID))
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to check if process is running
is_running() {
    pgrep -f "$1" > /dev/null 2>&1
}

# Function to kill process by pattern
kill_process() {
    local pattern="$1"
    if is_running "$pattern"; then
        echo -e "${YELLOW}[STREAM_SETUP] Killing existing $pattern processes...${NC}"
        pkill -f "$pattern" || true
        sleep 2
    fi
}

# Function to check if port is in use
is_port_used() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0  # Port is used
    else
        return 1  # Port is free
    fi
}

echo -e "${BLUE}[STREAM_SETUP] Starting isolated VNC streaming setup for Display :$DISPLAY_ID${NC}"
echo -e "${BLUE}[STREAM_SETUP] VNC Port: $VNC_PORT, noVNC Port: $NOVNC_PORT${NC}"

# 1. Check if ports are already in use
if is_port_used $VNC_PORT; then
    echo -e "${RED}[STREAM_SETUP] ERROR: VNC port $VNC_PORT is already in use${NC}"
    exit 1
fi

if is_port_used $NOVNC_PORT; then
    echo -e "${RED}[STREAM_SETUP] ERROR: noVNC port $NOVNC_PORT is already in use${NC}"
    exit 1
fi

# 2. Kill any existing processes for this display
echo -e "${YELLOW}[STREAM_SETUP] Cleaning up existing processes for display :$DISPLAY_ID...${NC}"
kill_process "Xvnc.*:$DISPLAY_ID"
kill_process "x11vnc.*:$DISPLAY_ID"
kill_process "websockify.*localhost:$VNC_PORT"

# 3. Start Xvnc (VNC server)
echo -e "${BLUE}[STREAM_SETUP] Starting Xvnc server on display :$DISPLAY_ID...${NC}"
Xvnc ":$DISPLAY_ID" \
    -geometry 1920x1080 \
    -depth 24 \
    -SecurityTypes None \
    -AlwaysShared \
    -DisconnectClients=0 \
    -MaxDisconnectionTime=0 \
    > "/tmp/xvnc_$DISPLAY_ID.log" 2>&1 &

# Wait for Xvnc to start
sleep 3
if ! is_running "Xvnc.*:$DISPLAY_ID"; then
    echo -e "${RED}[STREAM_SETUP] ERROR: Xvnc failed to start for display :$DISPLAY_ID${NC}"
    echo -e "${RED}[STREAM_SETUP] Check /tmp/xvnc_$DISPLAY_ID.log for details${NC}"
    exit 1
fi
echo -e "${GREEN}[STREAM_SETUP] Xvnc started successfully for display :$DISPLAY_ID${NC}"

# 4. Start x11vnc with enhanced options for multiple viewers and stability
echo -e "${BLUE}[STREAM_SETUP] Starting x11vnc for display :$DISPLAY_ID...${NC}"
x11vnc -display ":$DISPLAY_ID" \
    -rfbport "$VNC_PORT" \
    -forever \
    -shared \
    -nopw \
    -ncache 10 \
    -ncache_cr \
    -quiet \
    > "/tmp/x11vnc_$DISPLAY_ID.log" 2>&1 &

# Wait for x11vnc to start
sleep 2
if ! is_running "x11vnc.*:$DISPLAY_ID"; then
    echo -e "${RED}[STREAM_SETUP] ERROR: x11vnc failed to start for display :$DISPLAY_ID${NC}"
    echo -e "${RED}[STREAM_SETUP] Check /tmp/x11vnc_$DISPLAY_ID.log for details${NC}"
    # Cleanup Xvnc
    kill_process "Xvnc.*:$DISPLAY_ID"
    exit 1
fi
echo -e "${GREEN}[STREAM_SETUP] x11vnc started successfully for display :$DISPLAY_ID${NC}"

# 5. Start noVNC proxy
echo -e "${BLUE}[STREAM_SETUP] Starting noVNC proxy on port $NOVNC_PORT...${NC}"
/home/admin/Anand_QFast/venv/bin/websockify \
    --web /home/admin/Anand_QFast/noVNC \
    0.0.0.0:"$NOVNC_PORT" \
    localhost:"$VNC_PORT" \
    > "/tmp/novnc_$DISPLAY_ID.log" 2>&1 &

# Wait for noVNC to start
sleep 2
if ! is_running "websockify.*localhost:$VNC_PORT"; then
    echo -e "${RED}[STREAM_SETUP] ERROR: noVNC proxy failed to start for display :$DISPLAY_ID${NC}"
    echo -e "${RED}[STREAM_SETUP] Check /tmp/novnc_$DISPLAY_ID.log for details${NC}"
    # Cleanup
    kill_process "Xvnc.*:$DISPLAY_ID"
    kill_process "x11vnc.*:$DISPLAY_ID"
    exit 1
fi
echo -e "${GREEN}[STREAM_SETUP] noVNC proxy started successfully for display :$DISPLAY_ID${NC}"

# 6. Verify services are running
echo -e "${BLUE}[STREAM_SETUP] Verifying services for display :$DISPLAY_ID...${NC}"
if is_running "Xvnc.*:$DISPLAY_ID" && is_running "x11vnc.*:$DISPLAY_ID" && is_running "websockify.*localhost:$VNC_PORT"; then
    echo -e "${GREEN}[STREAM_SETUP] ✅ All VNC streaming services are running for display :$DISPLAY_ID!${NC}"
    echo -e "${GREEN}[STREAM_SETUP] 📺 noVNC URL: http://10.30.3.85:$NOVNC_PORT/vnc.html${NC}"
    echo -e "${GREEN}[STREAM_SETUP] 🔢 Display ID: $DISPLAY_ID${NC}"
    echo -e "${GREEN}[STREAM_SETUP] 🔌 VNC Port: $VNC_PORT${NC}"
    echo -e "${GREEN}[STREAM_SETUP] 🌐 noVNC Port: $NOVNC_PORT${NC}"
    exit 0
else
    echo -e "${RED}[STREAM_SETUP] ❌ Some services failed to start for display :$DISPLAY_ID${NC}"
    # Cleanup on failure
    kill_process "Xvnc.*:$DISPLAY_ID"
    kill_process "x11vnc.*:$DISPLAY_ID"
    kill_process "websockify.*localhost:$VNC_PORT"
    exit 1
fi