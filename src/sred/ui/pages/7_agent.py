import streamlit as st
from sred.ui.api_client import get_client, APIError
from sred.ui.state import get_run_id

st.title("Agent Runner")

run_id = get_run_id()
if not run_id:
    st.error("Please select a Run first.")
    st.stop()

client = get_client()

# --- Run Agent ---
st.subheader("Run Agent")

max_steps = st.slider("Max Steps", min_value=1, max_value=20, value=5)
user_msg = st.text_area(
    "Instruction for the agent", height=120,
    placeholder="e.g. Process all uploaded files, then profile the CSVs and summarise findings.",
)
context_notes = st.text_input(
    "Context notes (optional)",
    placeholder="e.g. We are currently resolving identities for File #12",
    help="Injected into the system prompt so the agent knows its immediate goal.",
)

if st.button("Run Agent", type="primary"):
    if not user_msg.strip():
        st.warning("Please enter an instruction.")
    else:
        # Agent endpoint is deferred to Phase 3 (LangGraph).
        # For now show a placeholder.
        st.info(
            "Agent execution via API is coming with LangGraph integration. "
            "For now, use the CLI or run the agent directly."
        )

st.divider()

# --- Tool Call History ---
st.subheader("Tool Call Log")
try:
    tool_logs = client.list_tool_calls(run_id, limit=50)
    if not tool_logs.items:
        st.info("No tool calls recorded yet for this run.")
    else:
        for log in tool_logs.items:
            icon = "\u2705" if log.success else "\u274c"
            ts = log.created_at.strftime("%H:%M:%S") if log.created_at else ""
            with st.expander(f"{icon} {log.tool_name} \u2014 {log.duration_ms}ms \u2014 {ts}"):
                st.caption("Arguments")
                try:
                    st.json(log.arguments_json)
                except Exception:
                    st.code(log.arguments_json)
                st.caption("Result")
                try:
                    st.json(log.result_json)
                except Exception:
                    st.code(log.result_json)
except APIError as e:
    st.error(f"Failed to load tool calls: {e.detail}")

# --- LLM Call History ---
st.subheader("LLM Call Log")
try:
    llm_logs = client.list_llm_calls(run_id, limit=20)
    if not llm_logs.items:
        st.info("No LLM calls recorded yet for this run.")
    else:
        for log in llm_logs.items:
            ts = log.created_at.strftime("%H:%M:%S") if log.created_at else ""
            with st.expander(f"\U0001f916 {log.model} \u2014 {log.total_tokens} tokens \u2014 {ts}"):
                st.write(f"**Messages:** {log.message_count} | **Tool calls:** {log.tool_calls_count}")
                st.write(f"**Tokens:** prompt={log.prompt_tokens}, completion={log.completion_tokens}")
                st.write(f"**Finish reason:** {log.finish_reason}")
                st.caption("Prompt summary")
                st.text(log.prompt_summary)
except APIError as e:
    st.error(f"Failed to load LLM calls: {e.detail}")
