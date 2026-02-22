import streamlit as st
from sred.ui.api_client import get_client, APIError
from sred.ui.state import set_run_context

st.title("Projects & Runs")

client = get_client()

# --- Create New ---
st.subheader("Create New Run")
with st.form("new_run_form"):
    new_name = st.text_input("Run Name", placeholder="e.g. Acme Corp FY2024")
    submitted = st.form_submit_button("Create Run")

    if submitted and new_name:
        try:
            run = client.create_run(new_name)
            st.success(f"Created run '{run.name}' (ID: {run.id})")
            set_run_context(run.id, run.name)
            st.rerun()
        except APIError as e:
            st.error(f"Failed to create run: {e.detail}")

st.divider()

# --- Select Existing ---
st.subheader("Existing Runs")
try:
    run_list = client.list_runs()
except APIError as e:
    st.error(f"Failed to load runs: {e.detail}")
    st.stop()

runs = run_list.items

if not runs:
    st.info("No runs found. Create one above.")
else:
    for run in runs:
        col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
        col1.write(f"**{run.name}**")
        col2.write(f"_{run.status.value}_")
        col3.write(f"ID: {run.id}")

        is_selected = st.session_state.get("run_id") == run.id
        btn_label = "Selected" if is_selected else "Select"

        if col4.button(btn_label, key=f"sel_{run.id}", disabled=is_selected):
            set_run_context(run.id, run.name)
            st.rerun()

# Show current context
current_id = st.session_state.get("run_id")
if current_id:
    run_name = st.session_state.get("run_name", f"Run #{current_id}")
    st.sidebar.success(f"Active Run: {run_name}")
else:
    st.sidebar.warning("No Run Selected")
