#!/usr/bin/env bash
set -euo pipefail

# scripts/setup_studio_service.sh
# Manages starting, checking, and stopping the local ComfyUI service on 127.0.0.1:8188.

COMFY_DIR="$HOME/.local/share/code-anime/ComfyUI"
VENV_DIR="$COMFY_DIR/.venv"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="$REPO_ROOT/runtime"
PID_FILE="$RUNTIME_DIR/comfyui.pid"
LOG_FILE="$RUNTIME_DIR/comfyui.log"

ACTION="${1:-status}"

case "$ACTION" in
    start)
        if [ -f "$PID_FILE" ] && ps -p "$(cat "$PID_FILE")" > /dev/null 2>&1; then
            echo "[service] ComfyUI already running (PID $(cat "$PID_FILE")) on port 8188"
            exit 0
        fi
        echo "[service] Starting ComfyUI on 127.0.0.1:8188 (lowvram/MPS)..."
        "$VENV_DIR/bin/python" "$COMFY_DIR/main.py" --listen 127.0.0.1 --port 8188 --lowvram > "$LOG_FILE" 2>&1 &
        echo $! > "$PID_FILE"
        echo "[service] Started ComfyUI with PID $(cat "$PID_FILE"). Waiting for readiness..."
        for i in {1..30}; do
            if curl -s http://127.0.0.1:8188/system_stats > /dev/null 2>&1; then
                echo "[service] ComfyUI is up and responding!"
                exit 0
            fi
            sleep 1
        done
        echo "[service] Timeout waiting for ComfyUI to respond. Check $LOG_FILE"
        exit 1
        ;;
    stop)
        if [ -f "$PID_FILE" ]; then
            PID="$(cat "$PID_FILE")"
            if ps -p "$PID" > /dev/null 2>&1; then
                echo "[service] Stopping ComfyUI (PID $PID)..."
                kill "$PID" || true
                rm -f "$PID_FILE"
                echo "[service] Stopped."
            else
                echo "[service] Process $PID is not running. Removing stale PID file."
                rm -f "$PID_FILE"
            fi
        else
            echo "[service] No PID file found."
        fi
        ;;
    status)
        if [ -f "$PID_FILE" ] && ps -p "$(cat "$PID_FILE")" > /dev/null 2>&1; then
            echo "[service] ComfyUI is RUNNING (PID $(cat "$PID_FILE"))"
            curl -s http://127.0.0.1:8188/system_stats | python3 -m json.tool | head -n 25
        else
            echo "[service] ComfyUI is NOT running."
            exit 1
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|status}"
        exit 1
        ;;
esac
