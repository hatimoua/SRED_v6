import streamlit as st
from sred.ui.api_client import get_client, APIError
from sred.ui.state import get_run_id

st.title("Payroll Validation")

run_id = get_run_id()
if not run_id:
    st.error("Please select a Run first.")
    st.stop()

client = get_client()

try:
    data = client.get_payroll_validation(run_id)
except APIError as e:
    st.error(f"Failed to load payroll data: {e.detail}")
    st.stop()

# --- Payroll Extracts ---
st.subheader("Payroll Extracts")

if not data.extracts:
    st.info("No payroll extracts yet. Use the Agent to run `payroll_extract` on a payroll file.")
else:
    for e in data.extracts:
        with st.expander(
            f"Period: {e.period_start} to {e.period_end} \u2014 "
            f"Hours: {e.total_hours or 'N/A'} | Wages: {e.total_wages or 'N/A'} | "
            f"Confidence: {e.confidence:.0%}"
        ):
            cols = st.columns(4)
            cols[0].metric("Hours", f"{e.total_hours or 'N/A'}")
            cols[1].metric("Wages", f"${e.total_wages:,.2f}" if e.total_wages else "N/A")
            cols[2].metric("Employees", e.employee_count or "N/A")
            cols[3].metric("Confidence", f"{e.confidence:.0%}")
            st.caption(f"File ID: {e.file_id} | Currency: {e.currency}")

st.divider()

# --- Mismatch Breakdown ---
st.subheader("Mismatch Breakdown")

if not data.mismatches:
    st.info("No mismatch data available.")
else:
    st.table([m.model_dump() for m in data.mismatches])

# Overall
st.divider()
st.subheader("Overall Summary")

cols = st.columns(4)
cols[0].metric("Payroll Total", f"{data.payroll_total:.1f}h")
cols[1].metric("Timesheet Total", f"{data.timesheet_total:.1f}h")
cols[2].metric("Mismatch", f"{data.overall_mismatch_pct:.1f}%")
cols[3].metric("Threshold", f"{data.threshold_pct:.0f}%")

if data.overall_mismatch_pct > data.threshold_pct:
    st.error(
        f"Overall mismatch ({data.overall_mismatch_pct:.1f}%) exceeds threshold "
        f"({data.threshold_pct:.0f}%). Check Tasks & Gates for BLOCKING contradictions."
    )
else:
    st.success(f"Overall mismatch ({data.overall_mismatch_pct:.1f}%) is within threshold.")

# Show related contradictions
st.divider()
st.subheader("Payroll Contradictions")

if not data.contradictions:
    st.info("No payroll mismatch contradictions.")
else:
    for c in data.contradictions:
        icon = "\U0001f534" if c.get("status") == "OPEN" else "\u2705"
        with st.expander(f"{icon} {c.get('issue_key', '')} \u2014 {c.get('severity', '')} \u2014 {c.get('status', '')}"):
            st.write(c.get("description", ""))
