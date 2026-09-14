
import hashlib
import io
import json
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False


st.set_page_config(
    page_title="Aurexis — AI Governance Readiness Audit",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# -----------------------------
# Styling
# -----------------------------
st.markdown("""
<style>
.block-container {max-width: 1180px; padding-top: 2rem; padding-bottom: 4rem;}
.hero {
    padding: 2.2rem 2.4rem;
    border: 1px solid rgba(128,128,128,.22);
    border-radius: 22px;
    background: linear-gradient(135deg, rgba(120,120,120,.08), rgba(120,120,120,.02));
    margin-bottom: 1.5rem;
}
.hero h1 {font-size: 3rem; margin-bottom: .4rem;}
.hero p {font-size: 1.15rem; color: #777;}
.badge {
    display:inline-block; padding:.35rem .65rem; border-radius:999px;
    border:1px solid rgba(128,128,128,.25); font-size:.82rem; margin-right:.35rem;
}
.card {
    border:1px solid rgba(128,128,128,.22); border-radius:16px;
    padding:1.1rem 1.2rem; margin:.5rem 0;
}
.small {color:#777; font-size:.9rem;}
.good {border-left:4px solid #2e8b57; padding-left:12px;}
.warn {border-left:4px solid #d28b00; padding-left:12px;}
.risk {border-left:4px solid #c94c4c; padding-left:12px;}
</style>
""", unsafe_allow_html=True)


# -----------------------------
# Session state
# -----------------------------
defaults = {
    "step": 1,
    "audit": None,
    "evidence_name": None,
    "evidence_hash": None,
}
for k, v in defaults.items():
    st.session_state.setdefault(k, v)


# -----------------------------
# Demo analysis engine
# This is intentionally deterministic for the first customer demo.
# Replace these functions with your FastAPI service later.
# -----------------------------
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def score_from_inputs(domain, jurisdiction, model_type, high_impact, monitoring,
                      fairness, explainability, documentation, security, file_bytes):
    score = 0.10

    domain_weights = {
        "Financial services": 0.22,
        "Healthcare": 0.24,
        "Employment / HR": 0.21,
        "Education": 0.16,
        "Insurance": 0.20,
        "Marketing / recommendations": 0.07,
        "Other": 0.05,
    }
    score += domain_weights.get(domain, 0.08)

    if jurisdiction in ["EU / EEA", "EU + U.S."]:
        score += 0.07
    elif jurisdiction == "U.S.":
        score += 0.04

    if model_type in ["Generative AI / LLM", "Computer vision"]:
        score += 0.04

    if high_impact:
        score += 0.12

    # Weak controls increase governance exposure.
    controls = [monitoring, fairness, explainability, documentation, security]
    for value in controls:
        score += (1.0 - value) * 0.06

    # Having evidence reduces uncertainty.
    if file_bytes:
        score -= 0.04

    return max(0.0, min(score, 0.99))


def risk_label(score):
    if score >= 0.75:
        return "HIGH", "Do not deploy without documented governance review."
    if score >= 0.50:
        return "ELEVATED", "Additional controls and evidence should be completed before production."
    if score >= 0.30:
        return "MODERATE", "Proceed with a documented monitoring and review plan."
    return "LOWER", "Basic governance controls appear sufficient for this demo assessment."


def control_status(value):
    if value >= 0.80:
        return "Strong"
    if value >= 0.55:
        return "Partial"
    return "Gap"


def generate_findings(data):
    findings = []

    if data["fairness"] < 0.60:
        findings.append({
            "severity": "High",
            "area": "Fairness",
            "finding": "Fairness evidence is incomplete or controls are not yet mature.",
            "action": "Run subgroup performance / fairness testing and retain the results as evidence.",
        })

    if data["explainability"] < 0.60:
        findings.append({
            "severity": "Medium",
            "area": "Explainability",
            "finding": "The current explainability control is limited.",
            "action": "Document decision factors, limitations, and an explanation method appropriate to the model.",
        })

    if data["monitoring"] < 0.60:
        findings.append({
            "severity": "High",
            "area": "Monitoring",
            "finding": "Production monitoring coverage is incomplete.",
            "action": "Define drift, performance, incident, and human-review thresholds.",
        })

    if data["documentation"] < 0.60:
        findings.append({
            "severity": "Medium",
            "area": "Documentation",
            "finding": "Governance documentation is incomplete.",
            "action": "Create or update the model card, intended-use statement, limitations, owner, and approval record.",
        })

    if data["security"] < 0.60:
        findings.append({
            "severity": "Medium",
            "area": "Security",
            "finding": "Security controls need additional evidence.",
            "action": "Document access control, data handling, secrets management, and incident response.",
        })

    if not findings:
        findings.append({
            "severity": "Low",
            "area": "Overall",
            "finding": "No major control gaps were identified in this demo assessment.",
            "action": "Maintain evidence and schedule periodic reassessment.",
        })

    return findings


def framework_mapping(jurisdiction, high_impact):
    rows = [
        ["NIST AI RMF", "Govern", "Governance roles, policies, monitoring, evidence"],
        ["ISO/IEC 42001", "AIMS", "AI management-system documentation and accountability"],
    ]
    if jurisdiction in ["EU / EEA", "EU + U.S."]:
        rows.append(["EU AI Act", "Risk / controls", "Risk classification, documentation, human oversight, monitoring"])
    if high_impact:
        rows.append(["Responsible AI", "Human oversight", "Escalation and documented human review"])
    return rows


def build_report_text(audit):
    lines = [
        "AUREXIS SYSTEMS — AI GOVERNANCE READINESS AUDIT",
        "",
        f"Generated: {audit['timestamp']}",
        f"Model / System: {audit['model_name']}",
        f"Organization: {audit['organization']}",
        f"Domain: {audit['domain']}",
        f"Jurisdiction: {audit['jurisdiction']}",
        f"Risk score: {audit['risk_score']:.2f}",
        f"Risk level: {audit['risk_label']}",
        "",
        "KEY FINDINGS",
    ]
    for i, f in enumerate(audit["findings"], 1):
        lines += [
            f"{i}. [{f['severity']}] {f['area']}: {f['finding']}",
            f"   Recommended action: {f['action']}",
        ]
    lines += ["", "FRAMEWORK MAPPING"]
    for row in audit["frameworks"]:
        lines.append(" - " + " | ".join(row))
    lines += [
        "",
        "DISCLAIMER",
        "This demo provides governance-readiness guidance and is not legal advice, regulatory certification,",
        "or a determination of legal compliance. Production assessments should be reviewed by qualified experts.",
    ]
    return "\n".join(lines)


def make_pdf(audit):
    if not REPORTLAB_AVAILABLE:
        return None

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 45

    def write_line(text, size=9, gap=13):
        nonlocal y
        if y < 45:
            c.showPage()
            y = height - 45
        c.setFont("Helvetica", size)
        c.drawString(45, y, text[:105])
        y -= gap

    write_line("AUREXIS SYSTEMS — AI GOVERNANCE READINESS AUDIT", 14, 22)
    write_line(f"Generated: {audit['timestamp']}")
    write_line(f"Organization: {audit['organization']}")
    write_line(f"Model / System: {audit['model_name']}")
    write_line(f"Domain: {audit['domain']}")
    write_line(f"Jurisdiction: {audit['jurisdiction']}")
    write_line(f"Risk score: {audit['risk_score']:.2f}")
    write_line(f"Risk level: {audit['risk_label']}", 11, 20)

    write_line("KEY FINDINGS", 11, 18)
    for i, f in enumerate(audit["findings"], 1):
        write_line(f"{i}. [{f['severity']}] {f['area']}: {f['finding']}")
        write_line(f"   Action: {f['action']}")

    write_line("FRAMEWORK MAPPING", 11, 18)
    for row in audit["frameworks"]:
        write_line(" | ".join(row))

    write_line("DISCLAIMER", 10, 18)
    write_line("This is a demo governance-readiness assessment, not legal advice or certification.")
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


# -----------------------------
# Header
# -----------------------------
st.markdown("""
<div class="hero">
    <div>
      <span class="badge">AUREXIS SYSTEMS</span>
      <span class="badge">AI GOVERNANCE</span>
      <span class="badge">READINESS AUDIT</span>
    </div>
    <h1>Is your AI system ready for deployment?</h1>
    <p>Upload your evidence, answer a few questions, and get a governance-readiness assessment in minutes.</p>
</div>
""", unsafe_allow_html=True)

steps = ["1. System", "2. Evidence", "3. Assessment", "4. Report"]
cols = st.columns(4)
for i, label in enumerate(steps, 1):
    with cols[i-1]:
        if st.session_state.step == i:
            st.markdown(f"**→ {label}**")
        elif st.session_state.step > i:
            st.markdown(f"✓ {label}")
        else:
            st.markdown(label)

st.divider()


# -----------------------------
# STEP 1
# -----------------------------
if st.session_state.step == 1:
    st.subheader("Tell us about your AI system")
    st.caption("This is the information a real customer provides during the first Aurexis audit.")

    with st.form("system_form"):
        c1, c2 = st.columns(2)

        with c1:
            organization = st.text_input(
                "Organization",
                placeholder="Acme AI, Example Health, Startup Inc."
            )
            model_name = st.text_input(
                "Model / AI system name",
                value="Customer Support Copilot"
            )
            domain = st.selectbox(
                "Primary domain",
                [
                    "Financial services",
                    "Healthcare",
                    "Employment / HR",
                    "Education",
                    "Insurance",
                    "Marketing / recommendations",
                    "Other",
                ],
            )

        with c2:
            jurisdiction = st.selectbox(
                "Primary deployment market",
                ["U.S.", "EU / EEA", "EU + U.S.", "Other"]
            )
            model_type = st.selectbox(
                "AI system type",
                [
                    "Predictive ML",
                    "Generative AI / LLM",
                    "Computer vision",
                    "Recommendation system",
                    "Other",
                ],
            )
            high_impact = st.checkbox(
                "This system can materially affect a person's access to an important service, opportunity, or outcome."
            )

        intended_use = st.text_area(
            "What does the AI system do?",
            placeholder="Example: The model predicts whether a transaction should receive additional fraud review.",
            height=120,
        )

        submitted = st.form_submit_button("Continue to Evidence →", type="primary", use_container_width=True)

    if submitted:
        if not organization.strip() or not model_name.strip() or not intended_use.strip():
            st.error("Please complete the organization, model name, and intended-use fields.")
        else:
            st.session_state.audit = {
                "organization": organization.strip(),
                "model_name": model_name.strip(),
                "domain": domain,
                "jurisdiction": jurisdiction,
                "model_type": model_type,
                "high_impact": high_impact,
                "intended_use": intended_use.strip(),
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            }
            st.session_state.step = 2
            st.rerun()


# -----------------------------
# STEP 2
# -----------------------------
elif st.session_state.step == 2:
    st.subheader("Add evidence")
    st.caption("For the live customer demo, ask the customer to upload one model card, test report, or governance document.")

    uploaded = st.file_uploader(
        "Upload model governance evidence",
        type=["pdf", "txt", "csv", "json", "md"],
        help="Do not upload confidential personal data for this demo.",
    )

    if uploaded:
        raw = uploaded.getvalue()
        st.session_state.evidence_name = uploaded.name
        st.session_state.evidence_hash = sha256_bytes(raw)

        c1, c2, c3 = st.columns(3)
        c1.metric("File", uploaded.name)
        c2.metric("Size", f"{len(raw)/1024:.1f} KB")
        c3.metric("SHA-256", st.session_state.evidence_hash[:12] + "…")

        st.success("Evidence received. Aurexis will treat this file as an evidence artifact for the demo assessment.")

    st.markdown("**No evidence yet?** You can still continue. This is useful when demonstrating an evidence-gap workflow.")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Back", use_container_width=True):
            st.session_state.step = 1
            st.rerun()
    with c2:
        if st.button("Continue to Assessment →", type="primary", use_container_width=True):
            st.session_state.step = 3
            st.rerun()


# -----------------------------
# STEP 3
# -----------------------------
elif st.session_state.step == 3:
    audit = st.session_state.audit
    st.subheader("Governance controls")
    st.caption("Rate the current maturity of your controls. In a real pilot, Aurexis would calculate these from evidence and connected evaluation data.")

    labels = {
        "monitoring": "Production monitoring & drift detection",
        "fairness": "Fairness / subgroup testing",
        "explainability": "Explainability / decision transparency",
        "documentation": "Model documentation / model card",
        "security": "Security / access / data controls",
    }

    values = {}
    for key, label in labels.items():
        values[key] = st.slider(label, 0, 100, 50, 5) / 100.0

    st.markdown("---")
    st.write("**Live preview**")

    score = score_from_inputs(
        audit["domain"],
        audit["jurisdiction"],
        audit["model_type"],
        audit["high_impact"],
        values["monitoring"],
        values["fairness"],
        values["explainability"],
        values["documentation"],
        values["security"],
        st.session_state.evidence_hash,
    )
    label, recommendation = risk_label(score)

    c1, c2, c3 = st.columns(3)
    c1.metric("Governance risk score", f"{score:.2f}")
    c2.metric("Readiness level", label)
    c3.metric("Evidence supplied", "Yes" if st.session_state.evidence_name else "No")

    if label == "HIGH":
        st.error(recommendation)
    elif label == "ELEVATED":
        st.warning(recommendation)
    else:
        st.info(recommendation)

    if st.button("Run Aurexis Assessment →", type="primary", use_container_width=True):
        audit["controls"] = values
        audit["risk_score"] = score
        audit["risk_label"] = label
        audit["recommendation"] = recommendation
        audit["findings"] = generate_findings({
            **audit,
            **values,
        })
        audit["frameworks"] = framework_mapping(audit["jurisdiction"], audit["high_impact"])
        audit["evidence_name"] = st.session_state.evidence_name
        audit["evidence_hash"] = st.session_state.evidence_hash
        st.session_state.audit = audit
        st.session_state.step = 4
        st.rerun()

    if st.button("← Back", use_container_width=True):
        st.session_state.step = 2
        st.rerun()


# -----------------------------
# STEP 4
# -----------------------------
elif st.session_state.step == 4:
    audit = st.session_state.audit
    st.subheader("Your Aurexis Governance Readiness Report")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Risk score", f"{audit['risk_score']:.2f}")
    c2.metric("Readiness", audit["risk_label"])
    c3.metric("Findings", len(audit["findings"]))
    c4.metric("Evidence", "Attached" if audit["evidence_name"] else "Missing")

    if audit["risk_label"] == "HIGH":
        st.error(audit["recommendation"])
    elif audit["risk_label"] == "ELEVATED":
        st.warning(audit["recommendation"])
    else:
        st.success(audit["recommendation"])

    st.markdown("### 1. Executive summary")
    st.markdown(
        f"""
**Organization:** {audit['organization']}  
**AI system:** {audit['model_name']}  
**Domain:** {audit['domain']}  
**Market:** {audit['jurisdiction']}  
**Intended use:** {audit['intended_use']}

Aurexis identified a **{audit['risk_label']}** governance-readiness profile with a demo score of
**{audit['risk_score']:.2f}**. The purpose of this assessment is to identify evidence and control gaps
before production deployment.
"""
    )

    st.markdown("### 2. Control maturity")
    control_df = pd.DataFrame([
        {"Control": "Monitoring & drift", "Maturity": control_status(audit["controls"]["monitoring"]),
         "Score": round(audit["controls"]["monitoring"] * 100)},
        {"Control": "Fairness", "Maturity": control_status(audit["controls"]["fairness"]),
         "Score": round(audit["controls"]["fairness"] * 100)},
        {"Control": "Explainability", "Maturity": control_status(audit["controls"]["explainability"]),
         "Score": round(audit["controls"]["explainability"] * 100)},
        {"Control": "Documentation", "Maturity": control_status(audit["controls"]["documentation"]),
         "Score": round(audit["controls"]["documentation"] * 100)},
        {"Control": "Security", "Maturity": control_status(audit["controls"]["security"]),
         "Score": round(audit["controls"]["security"] * 100)},
    ])
    st.dataframe(control_df, use_container_width=True, hide_index=True)

    st.markdown("### 3. Priority findings")
    for finding in audit["findings"]:
        css = "risk" if finding["severity"] == "High" else ("warn" if finding["severity"] == "Medium" else "good")
        st.markdown(
            f"""
<div class="{css}">
<b>{finding['severity']} — {finding['area']}</b><br>
{finding['finding']}<br>
<span class="small"><b>Recommended action:</b> {finding['action']}</span>
</div>
""",
            unsafe_allow_html=True,
        )

    st.markdown("### 4. Framework mapping")
    mapping_df = pd.DataFrame(audit["frameworks"], columns=["Framework", "Area", "Aurexis focus"])
    st.dataframe(mapping_df, use_container_width=True, hide_index=True)

    st.markdown("### 5. Evidence record")
    if audit["evidence_name"]:
        st.code(
            json.dumps(
                {
                    "file_name": audit["evidence_name"],
                    "sha256": audit["evidence_hash"],
                    "recorded_at": audit["timestamp"],
                },
                indent=2,
            ),
            language="json",
        )
    else:
        st.warning("No evidence artifact was supplied. Evidence completeness is therefore a priority gap.")

    pdf_bytes = make_pdf(audit)
    if pdf_bytes:
        st.download_button(
            "📥 Download Customer PDF Report",
            data=pdf_bytes,
            file_name=f"aurexis_{audit['model_name'].replace(' ', '_').lower()}_governance_report.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True,
        )
    else:
        st.download_button(
            "📥 Download Report (TXT)",
            data=build_report_text(audit),
            file_name="aurexis_governance_report.txt",
            mime="text/plain",
            use_container_width=True,
        )

    st.markdown("---")
    st.markdown("### What happens next?")
    st.info(
        "For a real pilot, Aurexis should turn this report into an action plan: "
        "assign owners, deadlines, evidence requirements, approval status, and recurring monitoring."
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Start another assessment", use_container_width=True):
            for k, v in defaults.items():
                st.session_state[k] = v
            st.rerun()
    with c2:
        st.button("Request a pilot review", type="primary", use_container_width=True,
                  help="Connect this button to your booking/contact workflow later.")

st.markdown("---")
st.caption(
    "Aurexis Systems — AI Governance Readiness Audit Demo | "
    "NIST AI RMF • EU AI Act • ISO/IEC 42001 • Responsible AI"
)
