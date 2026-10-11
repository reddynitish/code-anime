#!/usr/bin/env bash
set -euo pipefail

# scripts/setup_studio_health.sh
# Diagnostic health check for the local video generation studio runtime.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMFY_DIR="$HOME/.local/share/code-anime/ComfyUI"
VENV_DIR="$COMFY_DIR/.venv"
PID_FILE="$REPO_ROOT/runtime/comfyui.pid"

echo "=================================================="
echo "    Studio Video Generation Runtime Health Check   "
echo "=================================================="

# 1. ComfyUI Service
if [ -f "$PID_FILE" ] && ps -p "$(cat "$PID_FILE")" > /dev/null 2>&1; then
    PID="$(cat "$PID_FILE")"
    echo "[PASS] ComfyUI service running (PID: $PID)"
else
    echo "[FAIL] ComfyUI service not running"
    exit 1
fi

# 2. System stats endpoint
HTTP_CODE="$(curl -s -o /tmp/comfy_stats.json -w "%{http_code}" http://127.0.0.1:8188/system_stats)"
if [ "$HTTP_CODE" = "200" ]; then
    DEVICE="$(python3 -c "import json; d=json.load(open('/tmp/comfy_stats.json')); print(d['devices'][0]['type'])")"
    RAM_GB="$(python3 -c "import json; d=json.load(open('/tmp/comfy_stats.json')); print(round(d['system']['ram_total']/(1024**3), 1))")"
    echo "[PASS] /system_stats reachable (Device: $DEVICE, RAM: ${RAM_GB}GB)"
else
    echo "[FAIL] /system_stats returned HTTP $HTTP_CODE"
    exit 1
fi

# 3. Object info endpoint
HTTP_CODE="$(curl -s -o /tmp/comfy_obj.json -w "%{http_code}" http://127.0.0.1:8188/object_info)"
if [ "$HTTP_CODE" = "200" ]; then
    NODE_COUNT="$(python3 -c "import json; d=json.load(open('/tmp/comfy_obj.json')); print(len(d))")"
    echo "[PASS] /object_info reachable (Registered node classes: $NODE_COUNT)"
else
    echo "[FAIL] /object_info returned HTTP $HTTP_CODE"
    exit 1
fi

# 4. Storage & Budget
DISK_USED="$(du -sh "$COMFY_DIR" | cut -f1)"
FREE_DISK="$(df -h "$HOME" | awk 'NR==2 {print $4}')"
echo "[INFO] ComfyUI + venv disk usage: $DISK_USED (Free disk: $FREE_DISK)"

# 5. Doctor preflight check
echo ""
echo "--- Studio Doctor Preflight Report ---"
STUDIO_CATALOG_PATH="$REPO_ROOT/runtime/models.json" python3 -m studio doctor || true

echo "=================================================="
echo "Health check completed."
