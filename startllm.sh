#!/bin/bash

# Function to wait for a process to be ready by checking its log file
wait_for_ready() {
  local log_file=$1
  local ready_string=$2
  local timeout=${3:-300} # Default timeout 300 seconds
  local count=0

  echo "Waiting for process to be ready (looking for '$ready_string' in $log_file)..."
  while ! grep -q "$ready_string" "$log_file"; do
    sleep 1
    count=$((count + 1))
    if [ $count -ge $timeout ]; then
      echo "Timeout waiting for process to be ready."
      exit 1
    fi
  done
  echo "Process is ready."
}

# 0. Cleanup function to handle signals and exits
cleanup() {
  echo ""
  echo "Caught signal! Cleaning up processes..."
  
  # Stop Streamlit if it's still running (though usually foreground)
  [ -n "$STREAMLIT_PID" ] && kill $STREAMLIT_PID 2>/dev/null
  
  # Kill main.py (sudo requires special handling or pkill)
  echo "Stopping main.py..."
  sudo pkill -f "uv run main.py"
  
  # Kill llama-server
  echo "Stopping llama-server..."
  [ -n "$LLAMA_PID" ] && kill $LLAMA_PID 2>/dev/null
  pkill llama-server
  
  # Stop Docker
  echo "Stopping Docker container..."
  sudo docker stop python-sandbox-dcac81e6 >/dev/null 2>&1
  
  echo "Cleanup complete. Exiting."
  exit
}

# Trap SIGINT (Ctrl+C), SIGTERM, and EXIT
trap cleanup SIGINT SIGTERM EXIT

# 1. Start Docker container
echo "Starting Docker container..."
sudo docker start python-sandbox-dcac81e6

# 2. Start main.py
echo "Starting main.py..."
cd ~/pysand/python-mcp-sandbox/
# Redirect output to a log file to check for readiness
nohup sudo /home/linuxbrew/.linuxbrew/bin/uv run main.py >main.py.log 2>&1 &
MAIN_PID=$!

# Wait for main.py to be ready
# IMPORTANT: Replace "ready" with a string that main.py actually prints when ready
# (e.g., "listening on port", "MCP server started", etc.)
wait_for_ready "/home/mint/pysand/python-mcp-sandbox/main.py.log" "Application startup complete"

# 3. Start llama-server
echo "Starting llama-server..."
export LD_LIBRARY_PATH="/home/mint/Downloads/cuda-12.8/"
nohup /home/mint/Downloads/cuda-12.8/llama-server \
  -c 60000 \
  -np 1 \
  --webui-mcp-proxy \
  --temp 0.05 \
  --jinja \
  -m /home/mint/.lmstudio/models/unsloth/Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-UD-IQ4_XS.gguf \
  --spec-type ngram-mod --spec-ngram-size-n 24 --draft-min 12 --draft-max 48 \
  >llama-server.log 2>&1 &
LLAMA_PID=$!

# Wait for llama-server to be ready
# llama-server typically prints "listening on port 8080" when ready
wait_for_ready "/home/mint/pysand/python-mcp-sandbox/llama-server.log" "model loaded"

# 4. Run streamlit
echo "Starting Streamlit app..."
source ~/pvenv/bin/activate
cd ~/cs/1
# Run streamlit in foreground, or background if we want to wait
streamlit run app.py &
STREAMLIT_PID=$!

# Wait for streamlit to finish
wait $STREAMLIT_PID
