import streamlit as st
from sred.ui.api_client import get_client, APIError
from sred.ui.state import get_run_id
from sred.api.schemas.tasks import ContradictionStatusDTO, ReviewTaskStatusDTO

st.title("Tasks & Gates")

run_id = get_run_id()
if not run_id:
    st.error("Please select a Run first.")
    st.stop()

client = get_client()

# --- Gate Status Banner ---
try:
    gate = client.get_gate_status(run_id)
    if gate.run_status == "NEEDS_REVIEW":
        st.error("**Run is blocked (NEEDS_REVIEW).** Resolve all BLOCKING contradictions and tasks before proceeding.")
    else:
        st.success(f"Run status: **{gate.run_status}** \u2014 no blocking issues.")
except APIError as e:
    st.error(f"Failed to check gate status: {e.detail}")

st.divider()

# =========================================================================
# CONTRADICTIONS
# =========================================================================
st.subheader("Contradictions")

try:
    contradictions_resp = client.list_contradictions(run_id)
    contradictions = contradictions_resp.items
except APIError as e:
    st.error(f"Failed to load contradictions: {e.detail}")
    contradictions = []

open_contradictions = [c for c in contradictions if c.status == ContradictionStatusDTO.OPEN]
resolved_contradictions = [c for c in contradictions if c.status == ContradictionStatusDTO.RESOLVED]

if not contradictions:
    st.info("No contradictions recorded.")
else:
    st.caption(f"{len(open_contradictions)} open, {len(resolved_contradictions)} resolved")

    for c in contradictions:
        sev_icon = {"LOW": "\U0001f7e2", "MEDIUM": "\U0001f7e1", "HIGH": "\U0001f7e0", "BLOCKING": "\U0001f534"}.get(c.severity.value, "\u26aa")
        status_icon = "\U0001f513" if c.status == ContradictionStatusDTO.RESOLVED else "\u26a0\ufe0f"

        with st.expander(f"{status_icon} {sev_icon} [{c.contradiction_type.value}] {c.description[:80]}"):
            st.write(f"**Issue Key:** `{c.issue_key}`")
            st.write(f"**Severity:** {c.severity.value} | **Status:** {c.status.value}")
            st.write(f"**Description:** {c.description}")
            if c.related_entity_type:
                st.write(f"**Related:** {c.related_entity_type} #{c.related_entity_id}")

st.divider()

# =========================================================================
# REVIEW TASKS
# =========================================================================
st.subheader("Review Tasks")

try:
    tasks_resp = client.list_tasks(run_id)
    tasks = tasks_resp.items
except APIError as e:
    st.error(f"Failed to load tasks: {e.detail}")
    tasks = []

open_tasks = [t for t in tasks if t.status == ReviewTaskStatusDTO.OPEN]

if not tasks:
    st.info("No review tasks.")
else:
    st.caption(f"{len(open_tasks)} open, {len(tasks) - len(open_tasks)} resolved/superseded")

    for t in tasks:
        sev_icon = {"LOW": "\U0001f7e2", "MEDIUM": "\U0001f7e1", "HIGH": "\U0001f7e0", "BLOCKING": "\U0001f534"}.get(t.severity.value, "\u26aa")
        is_open = t.status == ReviewTaskStatusDTO.OPEN

        with st.expander(f"{'\U0001f4cb' if is_open else '\u2705'} {sev_icon} {t.title} ({t.status.value})"):
            st.write(f"**Issue Key:** `{t.issue_key}`")
            st.write(f"**Severity:** {t.severity.value}")
            st.write(f"**Description:** {t.description}")

            if is_open:
                st.markdown("---")
                st.markdown("**Resolve this task:**")
                decision_text = st.text_area(
                    "Decision / Resolution",
                    key=f"decision_{t.id}",
                    placeholder="Describe how this issue was resolved...",
                )
                if st.button("Resolve & Lock", key=f"resolve_{t.id}", type="primary"):
                    if not decision_text.strip():
                        st.warning("Please enter a decision.")
                    else:
                        try:
                            client.resolve_task(run_id, t.id, decision_text.strip())
                            st.success(f"Task resolved and locked: `{t.issue_key}`")
                            st.rerun()
                        except APIError as e:
                            st.error(f"Failed: {e.detail}")

st.divider()

# =========================================================================
# DECISION LOCKS
# =========================================================================
st.subheader("Decision Locks")

try:
    locks_resp = client.list_locks(run_id)
    locks = locks_resp.items
except APIError as e:
    st.error(f"Failed to load locks: {e.detail}")
    locks = []

active_locks = [lk for lk in locks if lk.active]
inactive_locks = [lk for lk in locks if not lk.active]

if not locks:
    st.info("No decision locks.")
else:
    st.caption(f"{len(active_locks)} active, {len(inactive_locks)} superseded")

    for lk in locks:
        icon = "\U0001f512" if lk.active else "\U0001f513"
        with st.expander(f"{icon} `{lk.issue_key}` \u2014 {'ACTIVE' if lk.active else 'SUPERSEDED'}"):
            st.write(f"**Reason:** {lk.reason}")
            if lk.created_at:
                st.write(f"**Created:** {lk.created_at.strftime('%Y-%m-%d %H:%M')}")

            if lk.active:
                st.markdown("---")
                new_reason = st.text_area(
                    "New decision (supersede)",
                    key=f"supersede_{lk.id}",
                    placeholder="Why are you overriding this lock?",
                )
                if st.button("Supersede Lock", key=f"sup_btn_{lk.id}"):
                    if not new_reason.strip():
                        st.warning("Please enter a reason.")
                    else:
                        try:
                            client.supersede_lock(run_id, lk.id, new_reason.strip())
                            st.success(f"Lock superseded for `{lk.issue_key}`")
                            st.rerun()
                        except APIError as e:
                            st.error(f"Failed: {e.detail}")
