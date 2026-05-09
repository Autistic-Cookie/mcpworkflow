import streamlit as st
import json
import os
import uuid
import time
from mcp_client import MCPClient
from llm_client import LLMClient

SETTINGS_FILE = "settings.json"
CONV_DIR = "conversations"

if not os.path.exists(CONV_DIR):
    os.makedirs(CONV_DIR)

def load_settings():
    default_prompts = ["You are a helpful assistant with access to tools. Use them when needed."]
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
                # Migration: convert single prompt to list
                if "system_prompt" in data:
                    data["system_prompts"] = [data["system_prompt"]]
                    del data["system_prompt"]
                
                if "system_prompts" not in data or not data["system_prompts"]:
                    data["system_prompts"] = default_prompts
                
                if "selected_prompt_index" not in data:
                    data["selected_prompt_index"] = 0
                
                if "tool_calling_enabled" not in data:
                    data["tool_calling_enabled"] = True
                return data
        except:
            pass
    return {
        "system_prompts": default_prompts,
        "selected_prompt_index": 0,
        "enabled_tools": None,
        "tool_calling_enabled": True
    }

def save_settings(prompts, selected_index, tools, tool_calling_enabled):
    with open(SETTINGS_FILE, "w") as f:
        json.dump({
            "system_prompts": prompts,
            "selected_prompt_index": selected_index,
            "enabled_tools": tools,
            "tool_calling_enabled": tool_calling_enabled
        }, f)

def get_saved_conversations():
    files = [f for f in os.listdir(CONV_DIR) if f.endswith(".json")]
    convs = []
    for f in files:
        path = os.path.join(CONV_DIR, f)
        try:
            mtime = os.path.getmtime(path)
            with open(path, "r") as file:
                data = json.load(file)
                convs.append({
                    "id": f.replace(".json", ""), 
                    "title": data.get("title", "Untitled Chat"),
                    "mtime": mtime
                })
        except:
            pass
    
    # Sort by modification time, most recent first
    convs.sort(key=lambda x: x["mtime"], reverse=True)
    return convs

def save_conversation(conv_id, messages, metrics=None):
    if not messages: return
    # Filter out None messages before saving
    clean_messages = [m for m in messages if m is not None]
    if not clean_messages: return
    title = clean_messages[0]["content"][:30] + "..." if clean_messages else "Untitled Chat"
    with open(os.path.join(CONV_DIR, f"{conv_id}.json"), "w") as f:
        json.dump({"title": title, "messages": clean_messages, "metrics": metrics}, f)

def delete_conversation(conv_id):
    path = os.path.join(CONV_DIR, f"{conv_id}.json")
    if os.path.exists(path):
        os.remove(path)

st.set_page_config(page_title="MCP Tool-Calling Demo", layout="wide")

# Custom CSS to cap button height to one line
st.markdown("""
<style>
    /* Target all Streamlit buttons */
    button[data-testid="baseButton-secondary"],
    button[data-testid="baseButton-primary"],
    button[data-testid="baseButton-tertiary"],
    button[data-testid="stChatInputSubmitButton"],
    div[data-testid="stPopover"] > button,
    div.stButton > button {
        height: 2.2rem !important;
        min-height: 2.2rem !important;
        max-height: 2.2rem !important;
        padding-top: 0px !important;
        padding-bottom: 0px !important;
        line-height: 2.2rem !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        overflow: hidden !important;
        white-space: nowrap !important;
    }

    /* Position popover inside chat input */
    [data-testid="stChatInput"] {
        /* padding-left: 45px !important; */
        /*padding-left: 0px !important;*/
        top:780%;
    }
    
    /* Target the popover container specifically when inside our input area */
    div.upload-container {
        /*position: fixed;*/
        padding-left:100px;
        /*left: calc(10% );*/ /* Adjust based on sidebar width (15%) and padding */
        /*z-index: 100;*/
        /*width: 40px;*/
    }

    @media (max-width: 68px) {
        div.upload-container {
            bottom: 2px;
        padding-left:100px;
        }
    }
</style>
""", unsafe_allow_html=True)

# Load persistent settings
settings = load_settings()

# Session State for Current Conversation and Partial Progress
if "current_conv_id" not in st.session_state:
    st.session_state.current_conv_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "partial_msg" not in st.session_state:
    st.session_state.partial_msg = None
if "delete_id" not in st.session_state:
    st.session_state.delete_id = None
if "last_error" not in st.session_state:
    st.session_state.last_error = None

# Display persistent error if any (Popup/Toast behavior)
if st.session_state.last_error:
    st.error(st.session_state.last_error)
    st.toast(st.session_state.last_error, icon="⚠️")
    if st.button("🗑️ Clear Error Message"):
        st.session_state.last_error = None
        st.rerun()

# Handle Interruption/Recovery from partial progress
if st.session_state.get("partial_msg"):
    p = st.session_state.partial_msg
    p["content"] = (p.get("content") or "") + " \n\n **[🛑 INTERRUPTED BY USER]**"
    p["interrupted"] = True
    st.session_state.messages.append(p)
    save_conversation(st.session_state.current_conv_id, st.session_state.messages, st.session_state.get("last_metrics"))
    st.session_state.partial_msg = None

# Layout: Main Chat (Left) and History (Right), history_col is empty
main_col, history_col = st.columns([0.85, 0.15])

# Sidebar for tool information and filtering
with st.sidebar:

    settings_tab, history_tab = st.tabs(["Settings","History"])

    with settings_tab:
        st.header("LLM Configuration")
        
        # --- System Prompt Manager ---
        st.subheader("System Prompts")
        prompts = settings["system_prompts"]
        sel_idx = settings["selected_prompt_index"]
        
        # Ensure index is valid
        if sel_idx >= len(prompts): sel_idx = 0
        
        # Choose Prompt
        selected_idx = st.selectbox(
            "Choose Preset",
            range(len(prompts)),
            format_func=lambda i: prompts[i][:40].replace("\n", " ") + ("..." if len(prompts[i]) > 40 else ""),
            index=sel_idx,
            key="prompt_selector"
        )
        
        # Edit/View Area
        current_sys_prompt = st.text_area(
            "Prompt Content",
            value=prompts[selected_idx],
            height=150,
            key=f"sys_prompt_area_{selected_idx}"
        )
        
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("➕ New", help="Add new preset",type="tertiary"):
                prompts.append("You are a helpful assistant.")
                save_settings(prompts, len(prompts)-1, settings["enabled_tools"], settings["tool_calling_enabled"])
                st.rerun()
        with c2:
            if st.button("💾 Save", help="Save changes to current preset",type="tertiary"):
                prompts[selected_idx] = current_sys_prompt
                save_settings(prompts, selected_idx, settings["enabled_tools"], settings["tool_calling_enabled"])
                st.toast("Preset updated!", icon="✅")
        with c3:
            if st.button("🗑️ Del", help="Delete current preset",type="tertiary") and len(prompts) > 1:
                del prompts[selected_idx]
                new_idx = max(0, selected_idx - 1)
                save_settings(prompts, new_idx, settings["enabled_tools"], settings["tool_calling_enabled"])
                st.rerun()

        # Handle dropdown change
        if selected_idx != sel_idx:
            save_settings(prompts, selected_idx, settings.get("enabled_tools"), settings.get("tool_calling_enabled"))
            st.rerun()
        
        st.divider()
        st.header("MCP Configuration")
        tool_calling_enabled = st.checkbox(
            "Enable Tool Calling",
            value=settings["tool_calling_enabled"],
            key="tool_calling_enabled_input"
        )

        if "tools" in st.session_state and st.session_state.tools:
            tool_names = [t['name'] for t in st.session_state.tools]

            saved_enabled = settings.get("enabled_tools")
            default_selection = saved_enabled if saved_enabled is not None else tool_names
            default_selection = [t for t in default_selection if t in tool_names]

            current_enabled_tools = st.multiselect(
                "Enabled Tools",
                options=tool_names,
                default=default_selection,
                key="enabled_tools_input",
                disabled=not tool_calling_enabled
            )

            if (current_enabled_tools != settings.get("enabled_tools") or
                tool_calling_enabled != settings.get("tool_calling_enabled")):
                save_settings(prompts, selected_idx, current_enabled_tools, tool_calling_enabled)

            if tool_calling_enabled:
                active_tools = [t for t in st.session_state.tools if t['name'] in current_enabled_tools]
            else:
                active_tools = []

            st.divider()
            st.header("Available Tool Details")
            for tool in st.session_state.tools:
                status = "✅" if (tool['name'] in current_enabled_tools and tool_calling_enabled) else "❌"
                with st.expander(f"{status} {tool['name']}"):
                    st.write(tool.get('description', "No description provided."))
        else:
            st.info("No tools loaded.")
            active_tools = []
            if tool_calling_enabled != settings.get("tool_calling_enabled"):
                save_settings(prompts, selected_idx, settings.get("enabled_tools"), tool_calling_enabled)
# --- history_tab: CONVERSATION HISTORY ---
    with history_tab:
        st.header("📜 Past Chats")
        if st.button("➕ New Chat", use_container_width=True,type="tertiary"):
            st.session_state.current_conv_id = str(uuid.uuid4())
            st.session_state.messages = []
            st.session_state.last_metrics = None
            st.rerun()

        st.divider()
        saved_chats = get_saved_conversations()
        if not saved_chats:
            st.info("No saved conversations.")
        
        for chat in saved_chats:
            col1, col2 = st.columns([0.7, 0.3])
            with col1:
                if st.button(chat["title"], key=f"load_{chat['id']}", use_container_width=True,type="tertiary"):
                    with open(os.path.join(CONV_DIR, f"{chat['id']}.json"), "r") as f:
                        data = json.load(f)
                        st.session_state.current_conv_id = chat["id"]
                        st.session_state.messages = data["messages"]
                        st.session_state.last_metrics = data.get("metrics")
                    st.rerun()
            with col2:
                if st.session_state.delete_id == chat["id"]:
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("✅", key=f"conf_{chat['id']}", help="Confirm Delete",type="tertiary"):
                            delete_conversation(chat["id"])
                            if st.session_state.current_conv_id == chat["id"]:
                                st.session_state.current_conv_id = str(uuid.uuid4())
                                st.session_state.messages = []
                                st.session_state.last_metrics = None
                            st.session_state.delete_id = None
                            st.rerun()
                    with c2:
                        if st.button("❌", key=f"canc_{chat['id']}", help="Cancel",type="tertiary"):
                            st.session_state.delete_id = None
                            st.rerun()
                else:
                    if st.button("🗑️", key=f"del_{chat['id']}", help="Delete Conversation",type="tertiary"):
                        st.session_state.delete_id = chat["id"]
                        st.rerun()

# --- MAIN PANEL: CHAT ---
with main_col:
    #st.title("MCP Tool-Calling Workflow")
    st.markdown("<div id='top'></div>", unsafe_allow_html=True)
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

    # Display chat history (defensive check for None)
    for message in st.session_state.messages:
        if message is None: continue
        role = message["role"]
        content = message.get("content", "")
        reasoning = message.get("reasoning_content", "")
        
        if content or reasoning:
            with st.chat_message(role):
                if reasoning:
                    with st.expander("Model's Thinking Process", expanded=True):
                        st.write(reasoning)
                if content:
                    if "--- Attached Files ---" in content and "\n\nUser Message: " in content:
                        parts = content.split("\n\nUser Message: ", 1)
                        with st.expander("📎 Attached Files", expanded=False):
                            st.code(parts[0].replace("--- Attached Files ---\n", ""))
                        st.markdown(parts[1])
                    else:
                        st.markdown(content)
        
        if message.get("tool_calls"):
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
    
    # Display performance metrics for the last interaction
    if "last_metrics" in st.session_state and st.session_state.last_metrics:
        st.divider()
        st.markdown(f"***{st.session_state.last_metrics}*** [↑ Back to Top](#top)")
        #st.markdown("[↑ Back to Top](#top)")

# Chat input and File Upload
with main_col:
    prompt = st.chat_input("Ask a question that might use tools...")
    # Use a div container for the upload button to position it via CSS
    #st.markdown('<div class="upload-container">', unsafe_allow_html=True)
    with st.popover("📎", help="Upload files for context",type="tertiary"):
        uploaded_files = st.file_uploader("Upload files", accept_multiple_files=True, key="file_uploader")
    #st.markdown('</div>', unsafe_allow_html=True)
    
if prompt:
    # Reset last error on new input
    st.session_state.last_error = None
    
    # Process uploaded files
    file_context = ""
    if st.session_state.get("file_uploader"):
        file_data = []
        for f in st.session_state.file_uploader:
            try:
                f.seek(0)
                content = f.read().decode("utf-8")
                file_data.append(f"File: {f.name}\n---\n{content}")
            except Exception as e:
                file_data.append(f"File: {f.name} (Error reading: {e})")
        
        if file_data:
            file_context = "--- Attached Files ---\n" + "\n\n".join(file_data)
    
    if file_context:
        full_content = f"{file_context}\n\nUser Message: {prompt}"
    else:
        full_content = prompt

    st.session_state.messages.append({"role": "user", "content": full_content})
    
    # Track performance metrics
    start_time = time.time()
    total_tokens = 0
    
    with main_col:
        with st.chat_message("user"):
            st.markdown(prompt)

        # Create a container for assistant's work to keep it above metrics
        assistant_work_area = st.container()
        
        # Metrics placeholder at the absolute bottom of the main panel
        st.divider()
        metrics_placeholder = st.empty()

        with assistant_work_area:
            with st.chat_message("assistant"):
                if st.button("🛑 Stop Generation",type="tertiary"):
                    st.stop()
                
                with st.status("Thinking...", expanded=True) as status:
                    while True:
                        full_messages = [{"role": "system", "content": current_sys_prompt}] + st.session_state.messages
                        
                        content = ""
                        reasoning = ""
                        tool_calls_map = {}
                        
                        r_placeholder = st.empty()
                        c_placeholder = st.empty()

                        st.session_state.partial_msg = {
                            "role": "assistant",
                            "content": "",
                            "reasoning_content": "",
                            "tool_calls": None
                        }

                        has_llm_error = False
                        error_msg = ""
                        for chunk in st.session_state.llm_client.stream_chat_completion(full_messages, active_tools):
                            if "error" in chunk:
                                error_msg = chunk["error"]
                                # Persist error for display after rerun
                                st.session_state.last_error = f"LLM Error: {error_msg}"
                                has_llm_error = True
                                break
                            
                            if not chunk.get("choices"): continue

                            # Update metrics
                            if "usage" in chunk and chunk["usage"]:
                                total_tokens = chunk["usage"].get("total_tokens", total_tokens)
                            else:
                                # Estimate tokens: content or reasoning chunk usually = 1 token
                                delta = chunk["choices"][0].get("delta", {})
                                if delta.get("content") or delta.get("reasoning_content"):
                                    total_tokens += 1
                            
                            elapsed = time.time() - start_time
                            tps = total_tokens / elapsed if elapsed > 0 else 0
                            st.session_state.last_metrics = f"⏱️ {elapsed:.1f}s | 🚀 {tps:.1f} t/s | 📦 {total_tokens} tokens"
                            metrics_placeholder.markdown(f"***{st.session_state.last_metrics}***")

                            delta = chunk["choices"][0].get("delta", {})
                            
                            if "reasoning_content" in delta:
                                reasoning += delta["reasoning_content"]
                                with r_placeholder.container():
                                    with st.expander("Model's Thinking Process", expanded=True):
                                        st.write(reasoning)
                            
                            if "content" in delta and delta["content"]:
                                content += delta["content"]
                                c_placeholder.markdown(content)
                                
                            if "tool_calls" in delta:
                                for tc_delta in delta["tool_calls"]:
                                    index = tc_delta["index"]
                                    if index not in tool_calls_map:
                                        tool_calls_map[index] = {
                                            "id": tc_delta.get("id"),
                                            "type": "function",
                                            "function": {"name": "", "arguments": ""}
                                        }
                                    f_delta = tc_delta.get("function", {})
                                    if f_delta.get("name"):
                                        tool_calls_map[index]["function"]["name"] += f_delta["name"]
                                    if f_delta.get("arguments"):
                                        tool_calls_map[index]["function"]["arguments"] += f_delta["arguments"]
                            
                            st.session_state.partial_msg = {
                                "role": "assistant",
                                "content": content,
                                "reasoning_content": reasoning,
                                "tool_calls": list(tool_calls_map.values()) if tool_calls_map else None
                            }

                        if has_llm_error:
                            status.update(label="Inference Failed", state="error", expanded=True)
                            st.session_state.partial_msg = None
                            break

                        message = st.session_state.partial_msg
                        if message:
                            st.session_state.messages.append(message)
                        st.session_state.partial_msg = None 
                        
                        if not message:
                            break

                        tool_calls = message.get("tool_calls")
                        
                        if tool_calls:
                            status.update(label="Executing Tools...", state="running", expanded=True)
                            for tc in tool_calls:
                                tool_name = tc["function"]["name"]
                                args = json.loads(tc["function"]["arguments"])
                                st.info(f"Executing: `{tool_name}`")
                                try:
                                    tool_result = st.session_state.mcp_client.call_tool(tool_name, args)
                                    st.session_state.messages.append({
                                        "role": "tool",
                                        "tool_call_id": tc.get("id"),
                                        "name": tool_name,
                                        "content": json.dumps(tool_result)
                                    })
                                    st.success(f"Result from `{tool_name}`: Success")
                                    with st.expander("View Tool Output", expanded=True):
                                        st.json(tool_result)
                                except Exception as e:
                                    st.error(f"Tool Error: {e}")
                                    st.session_state.messages.append({
                                        "role": "tool",
                                        "tool_call_id": tc.get("id"),
                                        "name": tool_name,
                                        "content": json.dumps({"error": str(e)})
                                    })
                            
                            status.update(label="Thinking again...", state="running", expanded=True)
                            continue
                        else:
                            status.update(label="Done!", state="complete", expanded=True)
                            break
        
        save_conversation(st.session_state.current_conv_id, st.session_state.messages, st.session_state.get("last_metrics"))
        st.rerun()
