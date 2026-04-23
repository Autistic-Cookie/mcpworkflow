# MCP Tool-Calling Streamlit App

This application implements a complete MCP tool-calling workflow using Streamlit for the UI and `llama-server` as the LLM backend.

## Architecture

1.  **Streamlit UI**: Captures user input and maintains chat history.
2.  **MCP Client**: Connects to an MCP server at `http://localhost:8181/sse`, performs handshake, and executes tools via SSE/HTTP POST.
3.  **LLM Client**: Interfaces with `llama-server` at `http://localhost:8080`, providing tool definitions and reasoning.
4.  **Orchestration Loop**: Automatically executes tool calls requested by the model and feeds results back until a final answer is generated.

## Requirements

- Python 3.9+
- `pip install -r requirements.txt`
- A running MCP server on `http://localhost:8181`
- A running `llama-server` on `http://localhost:8080`

## How to Run

```bash
streamlit run app.py
```

## Implementation Details

- **mcp_client.py**: Implements the legacy SSE transport for MCP.
- **llm_client.py**: Implements an OpenAI-compatible client for `llama-server`.
- **app.py**: Orchestrates the multi-turn interaction loop.
