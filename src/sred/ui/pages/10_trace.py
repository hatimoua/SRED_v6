"""Execution Trace Inspector \u2014 browse past agent sessions via API."""
import streamlit as st
import json
from sred.ui.api_client import get_client, APIError
from sred.ui.state import get_run_id
from sred.api.schemas.logs import ToolCallLogRead, LLMCallLogRead

st.title("Execution Trace Inspector")

run_id = get_run_id()
if not run_id:
    st.error("Please select a Run first.")
    st.stop()

client = get_client()

# ---------------------------------------------------------------------------
# 1. Discover all sessions for this run
# ---------------------------------------------------------------------------
try:
    sessions = client.list_sessions(run_id)
except APIError as e:
    st.error(f"Failed to load sessions: {e.detail}")
    st.stop()

if not sessions:
    st.info("No agent sessions recorded yet for this run. Run the agent first on the Agent Runner page.")
    st.stop()

# ---------------------------------------------------------------------------
# 2. Session selector
# ---------------------------------------------------------------------------
st.subheader(f"{len(sessions)} Agent Session(s)")

session_labels = [
    f"{s['started_at'][:19]} \u2014 {s['model']} \u2014 \"{s['first_prompt']}\u2026\""
    for s in sessions
]

selected_idx = st.selectbox(
    "Select a session to inspect",
    range(len(sessions)),
    format_func=lambda i: session_labels[i],
)

selected = sessions[selected_idx]
sid = selected["session_id"]
st.caption(f"Session ID: `{sid}`")

# ---------------------------------------------------------------------------
# 3. Load full trace for selected session
# ---------------------------------------------------------------------------
try:
    trace = client.get_session_trace(run_id, sid)
except APIError as e:
    st.error(f"Failed to load trace: {e.detail}")
    st.stop()

llm_calls = [LLMCallLogRead.model_validate(c) for c in trace["llm_calls"]]
tool_calls = [ToolCallLogRead.model_validate(c) for c in trace["tool_calls"]]

# ---------------------------------------------------------------------------
# 4. Build interleaved event timeline
# ---------------------------------------------------------------------------
events: list[tuple[str, str, LLMCallLogRead | ToolCallLogRead]] = []
for l in llm_calls:
    events.append((str(l.created_at), "llm", l))
for t in tool_calls:
    events.append((str(t.created_at), "tool", t))
events.sort(key=lambda e: e[0])

# ---------------------------------------------------------------------------
# 5. Summary metrics
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Session Summary")

total_tokens = sum(l.total_tokens for l in llm_calls)
total_tool_time = sum(t.duration_ms for t in tool_calls)
failed_tools = sum(1 for t in tool_calls if not t.success)

cols = st.columns(5)
cols[0].metric("LLM Calls", len(llm_calls))
cols[1].metric("Tool Calls", len(tool_calls))
cols[2].metric("Total Tokens", f"{total_tokens:,}")
cols[3].metric("Tool Time", f"{total_tool_time:,} ms")
cols[4].metric("Failed Tools", failed_tools)

# ---------------------------------------------------------------------------
# 6. Markdown export
# ---------------------------------------------------------------------------
def _build_trace_md() -> str:
    lines: list[str] = []
    lines.append(f"# Execution Trace \u2014 Session {sid[:8]}")
    lines.append(f"- **Run ID:** {run_id}")
    lines.append(f"- **Session ID:** `{sid}`")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| LLM Calls | {len(llm_calls)} |")
    lines.append(f"| Tool Calls | {len(tool_calls)} |")
    lines.append(f"| Total Tokens | {total_tokens:,} |")
    lines.append(f"| Tool Execution Time | {total_tool_time:,} ms |")
    lines.append(f"| Failed Tools | {failed_tools} |")
    lines.append("")
    lines.append("## Step-by-Step Trace")
    lines.append("")
    step = 0
    for ts, kind, obj in events:
        if kind == "llm":
            step += 1
            lines.append(f"### Step {step} \u2014 LLM Call (`{obj.model}`) \u2014 {ts}")
            lines.append(f"- Tokens: {obj.total_tokens} (prompt: {obj.prompt_tokens}, completion: {obj.completion_tokens})")
            lines.append(f"- Finish reason: {obj.finish_reason}")
            lines.append("")
        elif kind == "tool":
            status = "SUCCESS" if obj.success else "FAILED"
            lines.append(f"#### Tool: `{obj.tool_name}` \u2014 {status} \u2014 {obj.duration_ms} ms")
            lines.append("```json")
            try:
                lines.append(json.dumps(json.loads(obj.arguments_json), indent=2))
            except Exception:
                lines.append(obj.arguments_json)
            lines.append("```")
            lines.append("")
    return "\n".join(lines)

st.download_button(
    label="Download Trace as Markdown",
    data=_build_trace_md(),
    file_name=f"trace_{sid[:8]}.md",
    mime="text/markdown",
)

# ---------------------------------------------------------------------------
# 7. Interleaved timeline
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Step-by-Step Trace")

step_num = 0
for ts, kind, obj in events:
    if kind == "llm":
        step_num += 1
        with st.container(border=True):
            header_cols = st.columns([4, 1])
            header_cols[0].markdown(f"**Step {step_num} \u2014 \U0001f916 LLM Call** (`{obj.model}`)")
            header_cols[1].caption(ts[11:19] if len(ts) > 19 else ts)

            mcols = st.columns(4)
            mcols[0].write(f"Messages: **{obj.message_count}**")
            mcols[1].write(f"Tool calls: **{obj.tool_calls_count}**")
            mcols[2].write(f"Tokens: **{obj.total_tokens}** (p:{obj.prompt_tokens} c:{obj.completion_tokens})")
            mcols[3].write(f"Finish: **{obj.finish_reason}**")

            with st.expander("Prompt Summary"):
                st.text(obj.prompt_summary or "(empty)")

    elif kind == "tool":
        icon = "\u2705" if obj.success else "\u274c"
        with st.container(border=True):
            header_cols = st.columns([4, 1, 1])
            header_cols[0].markdown(f"**{icon} \U0001f527 {obj.tool_name}**")
            header_cols[1].caption(f"{obj.duration_ms} ms")
            header_cols[2].caption(ts[11:19] if len(ts) > 19 else ts)

            with st.expander("Arguments"):
                try:
                    st.json(obj.arguments_json)
                except Exception:
                    st.code(obj.arguments_json)

            with st.expander("Result"):
                try:
                    st.json(obj.result_json)
                except Exception:
                    st.code(obj.result_json)

# ---------------------------------------------------------------------------
# 8. Raw data tables
# ---------------------------------------------------------------------------
st.divider()
with st.expander("Raw LLM Call Data"):
    if llm_calls:
        st.dataframe([
            {
                "Time": str(l.created_at)[:19] if l.created_at else "",
                "Model": l.model,
                "Messages": l.message_count,
                "Tool Calls": l.tool_calls_count,
                "Prompt Tokens": l.prompt_tokens,
                "Completion Tokens": l.completion_tokens,
                "Total Tokens": l.total_tokens,
                "Finish": l.finish_reason,
            }
            for l in llm_calls
        ], use_container_width=True)

with st.expander("Raw Tool Call Data"):
    if tool_calls:
        st.dataframe([
            {
                "Time": str(t.created_at)[:19] if t.created_at else "",
                "Tool": t.tool_name,
                "Success": "\u2705" if t.success else "\u274c",
                "Duration (ms)": t.duration_ms,
                "Args": t.arguments_json[:80] + "\u2026" if len(t.arguments_json) > 80 else t.arguments_json,
                "Result": t.result_json[:80] + "\u2026" if len(t.result_json) > 80 else t.result_json,
            }
            for t in tool_calls
        ], use_container_width=True)
