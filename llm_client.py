import httpx
import json

class LLMClient:
    def __init__(self, base_url="http://localhost:8080"):
        self.base_url = base_url

    def stream_chat_completion(self, messages, tools=None):
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
            "stream": True
        }
        
        try:
            with httpx.stream("POST", url, json=payload, timeout=None) as response:
                response.raise_for_status()
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
"""
    def get_chat_completion(self, messages, tools=None):
        url = f"{self.base_url}/v1/chat/completions"
        
        # Format tools for llama-server (OpenAI format)
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
            "model": "gpt-3.5-turbo", # dummy model name for llama-server compatibility
            "tools": formatted_tools if formatted_tools else None,
            "tool_choice": "auto" if formatted_tools else None,
            "stream": False
        }
        
        try:
            response = httpx.post(url, json=payload, timeout=None)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"DEBUG: LLM Error: {e}")
            return {"error": str(e)}

    def parse_tool_calls(self, response):
        if "choices" in response and len(response["choices"]) > 0:
            message = response["choices"][0].get("message", {})
            if "tool_calls" in message:
                return message["tool_calls"]
        return None

    def get_reasoning(self, response):
        if "choices" in response and len(response["choices"]) > 0:
            message = response["choices"][0].get("message", {})
            return message.get("reasoning_content", "")
        return ""

    def get_final_text(self, response):
        if "choices" in response and len(response["choices"]) > 0:
            return response["choices"][0].get("message", {}).get("content", "")
        return ""
"""
