import streamlit as st
from sred.ui.api_client import get_client, APIError
from sred.ui.state import get_run_id

st.title("Labour Ledger")

run_id = get_run_id()
if not run_id:
    st.error("Please select a Run first.")
    st.stop()

client = get_client()

try:
    data = client.get_ledger_summary(run_id)
except APIError as e:
    st.error(f"Failed to load ledger data: {e.detail}")
    st.stop()

# ------------------------------------------------------------------
# 1. Summary Metrics
# ------------------------------------------------------------------
st.subheader("Summary")

if not data.ledger_rows:
    cols = st.columns(3)
    cols[0].metric("Staging Rows", data.staging.total)
    cols[1].metric("Promoted", data.staging.promoted)
    cols[2].metric("Pending", data.staging.pending)
    st.info(
        "No ledger entries yet. Use the Agent to run `ledger_populate` "
        "after confirming person aliases."
    )
    st.stop()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Ledger Entries", len(data.ledger_rows))
c2.metric("Total Hours", f"{data.total_hours:,.1f}")
c3.metric("SR&ED Hours", f"{data.sred_hours:,.1f}")
c4.metric("People Mapped", data.person_count)
c5.metric("Avg Confidence", f"{data.avg_confidence:.0%}")

# Staging row progress bar
if data.staging.total > 0:
    progress = data.staging.promoted / data.staging.total
    st.progress(progress, text=f"Staging rows: {data.staging.promoted}/{data.staging.total} promoted ({progress:.0%})")

st.divider()

# ------------------------------------------------------------------
# 2. Per-Person Breakdown
# ------------------------------------------------------------------
st.subheader("Per-Person Breakdown")

table_data = []
for pb in data.person_breakdowns:
    table_data.append({
        "Person": pb.person_name,
        "Role": pb.role,
        "Total Hours": f"{pb.total_hours:,.1f}",
        "SR&ED Hours": f"{pb.sred_hours:,.1f}",
        "Inclusion %": f"{pb.inclusion_pct:.1%}",
        "Confidence": f"{pb.avg_confidence:.0%}",
        "Bucket": ", ".join(pb.buckets),
        "Date Range": pb.date_range,
    })

st.table(table_data)

st.divider()

# ------------------------------------------------------------------
# 3. Detailed Ledger Entries
# ------------------------------------------------------------------
with st.expander("Detailed Ledger Entries", expanded=False):
    detail_data = []
    for r in data.ledger_rows:
        # Find person name from breakdowns
        person_name = next(
            (pb.person_name for pb in data.person_breakdowns
             if str(r.person_id) in pb.person_name or True),
            f"ID {r.person_id}",
        )
        detail_data.append({
            "ID": r.id,
            "Person ID": r.person_id,
            "Date": str(r.date),
            "Hours": f"{r.hours:,.1f}",
            "Bucket": r.bucket,
            "Inclusion": f"{r.inclusion_fraction:.1%}",
            "Confidence": f"{r.confidence:.0%}" if r.confidence else "\u2014",
            "Description": r.description or "\u2014",
        })
    st.dataframe(detail_data, use_container_width=True)

st.divider()

# ------------------------------------------------------------------
# 4. Unmatched Staging Rows
# ------------------------------------------------------------------
st.subheader("Unmatched Staging Rows")

if not data.unmatched_rows:
    st.success("All staging rows have been promoted to the ledger.")
else:
    st.warning(f"{len(data.unmatched_rows)} staging row(s) still pending \u2014 names may not match any confirmed alias.")

    unmatched_data = []
    for ur in data.unmatched_rows:
        unmatched_data.append({
            "Staging ID": ur.staging_id,
            "Name": ur.name,
            "Type": ur.row_type,
            "Has Alias?": "\u2705" if ur.has_alias else "\u274c",
            "Status": ur.status,
        })

    st.table(unmatched_data)

    if any(not ur.has_alias for ur in data.unmatched_rows):
        st.caption(
            "Names without a confirmed alias need to be resolved. "
            "Use the Agent with `aliases_resolve` or `aliases_confirm` to map them to Person records, "
            "then run `ledger_populate` again."
        )
