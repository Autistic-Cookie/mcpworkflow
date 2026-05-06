#!/usr/bin/env bash
set -uo pipefail

# ──────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────
WORK_DIR_MAIN="/home/mint/pysand/python-mcp-sandbox"
LOG_MAIN="$WORK_DIR_MAIN/main.py.log"
LOG_LLAMA="$WORK_DIR_MAIN/llama-server.log"
STREAMLIT_DIR="/home/mint/cs/1"
VENV_PYTHON="/home/mint/pvenv/bin/python"
LLAMA_BIN="/home/mint/Downloads/cuda-12.8/llama-server"
CONTAINER_NAME="python-sandbox-dcac81e6"

# PIDs (initialized empty for safe cleanup)
MAIN_PID=""
LLAMA_PID=""
STREAMLIT_PID=""

# ──────────────────────────────────────────────────────────────
# Cleanup & Signal Handling
# ──────────────────────────────────────────────────────────────
cleanup() {
  echo -e "\n🛑 Caught signal! Cleaning up processes..."

  [ -n "$STREAMLIT_PID" ] && kill "$STREAMLIT_PID" 2>/dev/null || true
  [ -n "$MAIN_PID" ] && kill "$MAIN_PID" 2>/dev/null || true
  [ -n "$LLAMA_PID" ] && kill "$LLAMA_PID" 2>/dev/null || true

  # Fallback pkill (only if PIDs were lost)
  pkill -f "uv run main.py" 2>/dev/null || true
  pkill -f "llama-server" 2>/dev/null || true

  echo "Stopping Docker container..."
  docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true

  echo "✅ Cleanup complete."
  exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# ──────────────────────────────────────────────────────────────
# Helper: Wait for log string
# ──────────────────────────────────────────────────────────────
wait_for_ready() {
  local log_file="$1" ready_string="$2" timeout="${3:-300}"
  local count=0

  echo "⏳ Waiting for '$ready_string' in $log_file (timeout: ${timeout}s)..."
  while ! tail -n 50 "$log_file" 2>/dev/null | grep -q "$ready_string"; do
    sleep 1
    count=$((count + 1))
    [ $count -ge $timeout ] && {
      echo "❌ Timeout waiting for process to be ready."
      exit 1
    }
  done
  echo "✅ Process is ready."
}

# ──────────────────────────────────────────────────────────────
# 1. Start Docker Container
# ──────────────────────────────────────────────────────────────
echo "🐳 Starting Docker container..."
sudo docker start "$CONTAINER_NAME" || {
  echo "❌ Docker start failed."
  exit 1
}
sleep 2 # Give container time to initialize

# ──────────────────────────────────────────────────────────────
# 2. Start main.py
# ──────────────────────────────────────────────────────────────
echo "🐍 Starting main.py..."
cd "$WORK_DIR_MAIN"
export PYTHONUNBUFFERED=1 # Prevents log buffering delays
nohup sudo /home/linuxbrew/.linuxbrew/bin/uv run main.py >"$LOG_MAIN" 2>&1 &
MAIN_PID=$!
wait_for_ready "$LOG_MAIN" "Application startup complete"

# ──────────────────────────────────────────────────────────────
# 3. Start llama-server
# ──────────────────────────────────────────────────────────────
echo "🦙 Starting llama-server..."
LD_LIBRARY_PATH="/home/mint/Downloads/cuda-12.8/" nohup "$LLAMA_BIN" \
  -c 60000 -np 1 --webui-mcp-proxy --temp 0.6 --jinja \
  -m "/home/mint/.lmstudio/models/lmstudio-community/gemma-4-26B-A4B-it-GGUF/gemma-4-26B-A4B-it-Q4_K_M.gguf" \
  --spec-type ngram-mod --spec-ngram-mod-n-match 24 --spec-draft-n-min 48 --spec-draft-n-max 64 \
  >"$LOG_LLAMA" 2>&1 &
LLAMA_PID=$!
wait_for_ready "$LOG_LLAMA" "model loaded"
#  -m "/home/mint/.lmstudio/models/unsloth/Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-UD-IQ4_XS.gguf" \

# ──────────────────────────────────────────────────────────────
# 4. Start Streamlit
# ──────────────────────────────────────────────────────────────
echo "🌊 Starting Streamlit app..."
cd "$STREAMLIT_DIR"
$VENV_PYTHON -m streamlit run app.py &
STREAMLIT_PID=$!

# Keep script alive while Streamlit runs
wait "$STREAMLIT_PID"
