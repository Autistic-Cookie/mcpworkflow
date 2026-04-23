import streamlit as st
import json
import time
import os
import uuid
from mcp_client import MCPClient
from llm_client import LLMClient

SETTINGS_FILE = "settings.json"
CONV_DIR = "conversations"

if not os.path.exists(CONV_DIR):
    os.makedirs(CONV_DIR)

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {"system_prompt": "You are a helpful assistant with access to tools. Use them when needed.", "enabled_tools": None}

def save_settings(prompt, tools):
    with open(SETTINGS_FILE, "w") as f:
        json.dump({"system_prompt": prompt, "enabled_tools": tools}, f)

def get_saved_conversations():
    files = [f for f in os.listdir(CONV_DIR) if f.endswith(".json")]
    convs = []
    for f in files:
        try:
            with open(os.path.join(CONV_DIR, f), "r") as file:
                data = json.load(file)
                convs.append({"id": f.replace(".json", ""), "title": data.get("title", "Untitled Chat")})
        except:
            pass
    return convs

def save_conversation(conv_id, messages):
    if not messages: return
    title = messages[0]["content"][:30] + "..." if messages else "Untitled Chat"
    with open(os.path.join(CONV_DIR, f"{conv_id}.json"), "w") as f:
        json.dump({"title": title, "messages": messages}, f)

def delete_conversation(conv_id):
    path = os.path.join(CONV_DIR, f"{conv_id}.json")
    if os.path.exists(path):
        os.remove(path)

st.set_page_config(page_title="MCP Tool-Calling Demo", layout="wide")

# Load persistent settings
settings = load_settings()

# Session State for Current Conversation
if "current_conv_id" not in st.session_state:
    st.session_state.current_conv_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []

# Layout: Main Chat (Left) and History (Right)
main_col, history_col = st.columns([0.75, 0.25])

# Sidebar for tool information and filtering
with st.sidebar:
    st.header("LLM Configuration")
    
    current_sys_prompt = st.text_area(
        "System Prompt",
        value=settings["system_prompt"],
        height=100,
        key="sys_prompt_input"
    )
    
    st.header("MCP Configuration")
    if "tools" in st.session_state and st.session_state.tools:
        tool_names = [t['name'] for t in st.session_state.tools]
        
        saved_enabled = settings.get("enabled_tools")
        default_selection = saved_enabled if saved_enabled is not None else tool_names
        default_selection = [t for t in default_selection if t in tool_names]

        current_enabled_tools = st.multiselect(
            "Enabled Tools",
            options=tool_names,
            default=default_selection,
            key="enabled_tools_input"
        )
        
        if current_sys_prompt != settings["system_prompt"] or current_enabled_tools != settings["enabled_tools"]:
            save_settings(current_sys_prompt, current_enabled_tools)
        
        active_tools = [t for t in st.session_state.tools if t['name'] in current_enabled_tools]
        
        st.divider()
        st.header("Available Tool Details")
        for tool in st.session_state.tools:
            status = "✅" if tool['name'] in current_enabled_tools else "❌"
            with st.expander(f"{status} {tool['name']}"):
                st.write(tool.get('description', "No description provided."))
    else:
        st.info("No tools loaded.")
        active_tools = []
        if current_sys_prompt != settings["system_prompt"]:
            save_settings(current_sys_prompt, settings.get("enabled_tools"))

# --- RIGHT PANEL: CONVERSATION HISTORY ---
with history_col:
    st.header("📜 Past Chats")
    if st.button("➕ New Chat", use_container_width=True):
        st.session_state.current_conv_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()

    st.divider()
    saved_chats = get_saved_conversations()
    if not saved_chats:
        st.info("No saved conversations.")
    
    for chat in saved_chats:
        col1, col2 = st.columns([0.8, 0.2])
        with col1:
            if st.button(chat["title"], key=f"load_{chat['id']}", use_container_width=True):
                with open(os.path.join(CONV_DIR, f"{chat['id']}.json"), "r") as f:
                    data = json.load(f)
                    st.session_state.current_conv_id = chat["id"]
                    st.session_state.messages = data["messages"]
                st.rerun()
        with col2:
            if st.button("🗑️", key=f"del_{chat['id']}"):
                delete_conversation(chat["id"])
                if st.session_state.current_conv_id == chat["id"]:
                    st.session_state.current_conv_id = str(uuid.uuid4())
                    st.session_state.messages = []
                st.rerun()

# --- MAIN PANEL: CHAT ---
with main_col:
    st.title("MCP Tool-Calling Workflow")
    
    # Initialize clients and tools
    if "mcp_client" not in st.session_state:
        try:
            mcp = MCPClient()
            tools = mcp.connect()
            st.session_state.mcp_client = mcp
            st.session_state.tools = tools
            st.success(f"Connected to MCP server.")
        except Exception as e:
            st.error(f"Failed to connect to MCP server: {e}")
            st.session_state.mcp_client = None
            st.session_state.tools = []

    if "llm_client" not in st.session_state:
        st.session_state.llm_client = LLMClient()

    # Display chat history
    for message in st.session_state.messages:
        role = message["role"]
        content = message.get("content", "")
        reasoning = message.get("reasoning_content", "")
        
        if content or reasoning:
            with st.chat_message(role):
                if reasoning:
                    with st.expander("Model's Thinking Process", expanded=False):
                        st.write(reasoning)
                if content:
                    st.markdown(content)
        
        if "tool_calls" in message:
            with st.chat_message("assistant"):
                for tc in message["tool_calls"]:
                    st.info(f"Tool Call: {tc['function']['name']}({tc['function']['arguments']})")
        
        if role == "tool":
            with st.chat_message("system"):
                st.info(f"Tool Output: **{message.get('name', 'Unknown')}**")
                try:
                    json_content = json.loads(content)
                    st.json(json_content)
                except:
                    st.code(content)

# Chat input
if prompt := st.chat_input("Ask a question that might use tools..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with main_col:
        with st.chat_message("user"):
            st.markdown(prompt)

        # Thinking state
        with st.chat_message("assistant"):
            with st.status("Thinking...") as status:
                while True:
                    # Prepare message list with System Prompt
                    full_messages = [{"role": "system", "content": current_sys_prompt}] + st.session_state.messages
                    
                    # LLM Inference
                    response = st.session_state.llm_client.get_chat_completion(
                        full_messages,
                        active_tools
                    )
                    
                    if "error" in response:
                        st.error(f"Error: {response['error']}")
                        break

                    message = response["choices"][0]["message"]
                    # Store message in history
                    st.session_state.messages.append(message)
                    
                    # Live Thinking Output
                    reasoning = st.session_state.llm_client.get_reasoning(response)
                    if reasoning:
                        with st.expander("Reasoning", expanded=True):
                            st.write(reasoning)

                    # Check for tool calls
                    tool_calls = st.session_state.llm_client.parse_tool_calls(response)
                    
                    if tool_calls:
                        status.update(label="Executing Tools...", state="running")
                        for tc in tool_calls:
                            tool_name = tc["function"]["name"]
                            args = json.loads(tc["function"]["arguments"])
                            
                            st.info(f"Executing: `{tool_name}` with `{args}`")
                            
                            try:
                                # Execute MCP Tool
                                tool_result = st.session_state.mcp_client.call_tool(tool_name, args)
                                
                                # Append result to history
                                st.session_state.messages.append({
                                    "role": "tool",
                                    "tool_call_id": tc.get("id"),
                                    "name": tool_name,
                                    "content": json.dumps(tool_result)
                                })
                                st.success(f"Result from `{tool_name}`: Success")
                                with st.expander("View Tool Output"):
                                    st.json(tool_result)
                            except Exception as e:
                                st.error(f"Tool Execution Error: {e}")
                                st.session_state.messages.append({
                                    "role": "tool",
                                    "tool_call_id": tc.get("id"),
                                    "name": tool_name,
                                    "content": json.dumps({"error": str(e)})
                                })
                        
                        status.update(label="Thinking again...", state="running")
                        continue
                    else:
                        final_text = st.session_state.llm_client.get_final_text(response)
                        status.update(label="Done!", state="complete")
                        if final_text:
                            st.markdown(final_text)
                        break
        # Save the conversation after each response
        save_conversation(st.session_state.current_conv_id, st.session_state.messages)
        st.rerun()
