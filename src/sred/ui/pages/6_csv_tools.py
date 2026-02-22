import streamlit as st
from sred.ui.api_client import get_client, APIError
from sred.ui.state import get_run_id

st.title("CSV Intelligence Lab")

run_id = get_run_id()
if not run_id:
    st.warning("Select a Run first.")
    st.stop()

client = get_client()

# --- Select CSV ---
try:
    file_list = client.list_files(run_id)
except APIError as e:
    st.error(f"Failed to load files: {e.detail}")
    st.stop()

csv_files = [f for f in file_list.items if f.original_filename.lower().endswith(".csv")]

if not csv_files:
    st.info("No CSV files found in this run.")
    st.stop()

selected_file_name = st.selectbox("Select CSV File", [f.original_filename for f in csv_files])
selected_file = next(f for f in csv_files if f.original_filename == selected_file_name)

# --- Labs ---
tab1, tab2, tab3 = st.tabs(["Profile", "SQL Console", "Schema Hypotheses"])

with tab1:
    st.subheader("File Profile")
    if st.button("Generate Profile", key="btn_profile"):
        try:
            profile = client.csv_profile(run_id, selected_file.id)
            st.metric("Row Count", profile.row_count)
            st.write("**Columns**")
            st.dataframe(profile.columns)
            st.write("**Sample Data**")
            st.dataframe(profile.sample_rows)
        except APIError as e:
            st.error(f"Profiling failed: {e.detail}")

with tab2:
    st.subheader("DuckDB SQL Console")
    st.caption("Write SQL referencing table as `df`.")

    query = st.text_area("SQL Query", value="SELECT * FROM df LIMIT 5", height=150)

    if st.button("Run Query", key="btn_query"):
        try:
            result = client.csv_query(run_id, selected_file.id, query)
            if result.error:
                st.error(result.error)
            else:
                st.dataframe(result.rows)
        except APIError as e:
            st.error(f"Query failed: {e.detail}")

with tab3:
    st.subheader("Schema Mapping Proposals")

    try:
        proposals = client.csv_list_proposals(run_id, selected_file.id)
    except APIError as e:
        st.error(f"Failed to load proposals: {e.detail}")
        proposals = None

    if proposals and proposals.items:
        st.success(f"Found {proposals.total} existing proposals.")
        for p in proposals.items:
            with st.expander(f"Proposal (Conf: {p.confidence})"):
                st.json(p.mapping_json)
                st.write(f"**Reasoning:** {p.reasoning}")
    else:
        st.info("No proposals yet.")
        if st.button("Generate Proposal (LLM)", key="btn_prop"):
            with st.spinner("Analyzing schema..."):
                try:
                    client.csv_generate_proposals(run_id, selected_file.id)
                    st.rerun()
                except APIError as e:
                    st.error(f"Generation failed: {e.detail}")
