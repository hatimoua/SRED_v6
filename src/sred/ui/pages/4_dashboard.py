import streamlit as st
from sred.ui.api_client import get_client, APIError
from sred.ui.state import get_run_id

st.title("Run Dashboard")

run_id = get_run_id()
if not run_id:
    st.warning("Please select a Run to view status.")
    st.stop()

client = get_client()

try:
    summary = client.get_dashboard(run_id)
except APIError as e:
    st.error(f"Failed to load dashboard: {e.detail}")
    st.stop()

# --- Status Cards ---
c1, c2, c3 = st.columns(3)
c1.metric("Run Status", summary.run_status)
c2.metric(
    "People", summary.person_count,
    delta=f"-{summary.pending_rates} Pending" if summary.pending_rates else "All Set",
)
c3.metric("Files", summary.file_count)

st.divider()

# --- Readiness Checks ---
st.subheader("Readiness Checklist")

ready = True

if summary.person_count == 0:
    st.error("No people added. Go to 'People' page.")
    ready = False
elif summary.pending_rates > 0:
    st.warning(f"{summary.pending_rates} people have missing rates. Claim generation will be blocked.")
    ready = False
else:
    st.success("People data complete.")

if summary.file_count == 0:
    st.error("No files uploaded. Go to 'Uploads' page.")
    ready = False
else:
    st.success("Files uploaded.")

st.info("Blocking Tasks: None (Task system not implemented yet)")

st.divider()

if ready:
    st.success("Ready for Processing (Coming Soon)")
else:
    st.warning("Please resolve issues above to proceed.")
