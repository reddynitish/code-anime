#!/usr/bin/env bash
set -euo pipefail

# scripts/setup_studio_runtime.sh
# Sets up ComfyUI in ~/.local/share/code-anime/ComfyUI using uv and Python 3.12,
# pins dependencies, verifies PyTorch MPS acceleration, and starts ComfyUI.

COMFY_DIR="$HOME/.local/share/code-anime/ComfyUI"
VENV_DIR="$COMFY_DIR/.venv"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="$REPO_ROOT/runtime"

mkdir -p "$COMFY_DIR" "$RUNTIME_DIR" "$RUNTIME_DIR/workflows"

if [ ! -d "$COMFY_DIR/.git" ]; then
    echo "[setup] Cloning pinned official ComfyUI into $COMFY_DIR..."
    git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git "$COMFY_DIR"
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "[setup] Creating isolated uv Python 3.12 virtualenv..."
    uv venv "$VENV_DIR" --python python3.12
fi

PYTHON_BIN="$VENV_DIR/bin/python"

echo "[setup] Installing official PyTorch with Apple Silicon MPS support..."
uv pip install --python "$PYTHON_BIN" torch torchvision torchaudio

echo "[setup] Installing ComfyUI official requirements..."
uv pip install --python "$PYTHON_BIN" -r "$COMFY_DIR/requirements.txt"

echo "[setup] Testing PyTorch MPS availability..."
"$PYTHON_BIN" -c "
import torch
assert torch.backends.mps.is_available(), 'MPS backend is not available!'
print('PyTorch MPS verified successfully. Device: mps')
"

echo "[setup] Runtime setup complete."
