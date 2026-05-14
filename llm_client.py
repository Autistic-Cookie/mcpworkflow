import httpx
import json

class LLMClient:
    def __init__(self, base_url="http://localhost:8080"):
        self.base_url = base_url

    def stream_chat_completion(self, messages, tools=None, **kwargs):
        url = f"{self.base_url}/v1/chat/completions"
        
        formatted_tools = []
        if tools:
            for tool in tools:
                formatted_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("inputSchema", {
                            "type": "object",
                            "properties": {}
                        })
                    }
                })

        payload = {
            "messages": messages,
            "model": "gpt-3.5-turbo",
            "tools": formatted_tools if formatted_tools else None,
            "tool_choice": "auto" if formatted_tools else None,
            "stream": True,
            **kwargs
        }
        
        try:
            with httpx.stream("POST", url, json=payload, timeout=None) as response:
                if response.status_code != 200:
                    error_detail = response.read().decode()
                    try:
                        # Try to extract message from JSON if possible
                        err_json = json.loads(error_detail)
                        error_detail = err_json.get("error", {}).get("message", error_detail)
                    except:
                        pass
                    yield {"error": f"HTTP {response.status_code}: {error_detail}"}
                    return

                for line in response.iter_lines():
                    if line.startswith("data: "):
                        data = line[6:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            yield json.loads(data)
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            yield {"error": str(e)}
