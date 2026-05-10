import httpx
import json
import uuid
import threading
import queue
import time

class MCPClient:
    def __init__(self, sse_url="http://localhost:8181/sse"):
        self.sse_url = sse_url
        self.post_url = None
        self.tools = []
        self.responses = {} # Map request_id to Queue
        self._sse_thread = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def connect(self):
        # 1. Start SSE connection in background thread
        self._sse_thread = threading.Thread(target=self._listen_sse, daemon=True)
        self._sse_thread.start()
        
        # Wait for post_url to be populated from 'endpoint' event
        timeout = 10
        start_time = time.time()
        while self.post_url is None:
            if time.time() - start_time > timeout:
                raise TimeoutError("Failed to get endpoint from MCP server")
            time.sleep(0.1)

        # 2. Initialize
        self._call("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "streamlit-mcp-client", "version": "1.0.0"}
        })
        self._notify("notifications/initialized")
        
        # 3. List tools
        res = self._call("tools/list", {})
        self.tools = res.get("tools", [])
        return self.tools

    def _listen_sse(self):
        try:
            from urllib.parse import urljoin
            print(f"DEBUG: Connecting to SSE at {self.sse_url}")
            with httpx.stream("GET", self.sse_url, timeout=None) as response:
                event_type = "message"
                for line in response.iter_lines():
                    if self._stop_event.is_set():
                        break
                    if not line:
                        continue
                    
                    if line.startswith("event: "):
                        event_type = line[7:].strip()
                    elif line.startswith("data: "):
                        data_content = line[6:].strip()
                        
                        if event_type == "endpoint":
                            # Handle relative URLs
                            if data_content.startswith("/"):
                                self.post_url = urljoin(self.sse_url, data_content)
                            else:
                                self.post_url = data_content
                            print(f"DEBUG: MCP Post URL resolved to: {self.post_url}")
                        elif event_type == "message":
                            try:
                                data = json.loads(data_content)
                                if "id" in data:
                                    req_id = str(data["id"])
                                    with self._lock:
                                        if req_id in self.responses:
                                            self.responses[req_id].put(data)
                            except json.JSONDecodeError:
                                print(f"DEBUG: Failed to decode message data: {data_content}")
                        
                        # Reset for next event
                        event_type = "message"
        except Exception as e:
            print(f"DEBUG: SSE Connection Error: {e}")
            import traceback
            traceback.print_exc()

    def _call(self, method, params):
        req_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params
        }
        with self._lock:
            self.responses[req_id] = queue.Queue()
        
        # Send via POST
        try:
            httpx.post(self.post_url, json=payload)
            response = self.responses[req_id].get(timeout=30)
        finally:
            # This ensures the ID is deleted even if timeout or error occurs
            if req_id in self.responses:
                del self.responses[req_id]
        #httpx.post(self.post_url, json=payload)
        # Wait for response from SSE
        #response = self.responses[req_id].get(timeout=30)
        #del self.responses[req_id]
        if "error" in response:
            raise Exception(f"MCP Error: {response['error']}")
        return response.get("result")

    def _notify(self, method, params=None):
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        httpx.post(self.post_url, json=payload)

    def call_tool(self, name, arguments):
        return self._call("tools/call", {
            "name": name,
            "arguments": arguments
        })

    def stop(self):
        self._stop_event.set()
