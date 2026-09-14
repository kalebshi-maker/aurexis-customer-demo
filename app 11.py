import hashlib
import io
import json
import re
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except Exception:
    PYPDF_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False


# ============================================================
# AUREXIS V3 — EVIDENCE INTELLIGENCE CUSTOMER MVP
# ============================================================
# Customer-facing MVP.
#
# V3 changes the experience from:
#   "tell us your control maturity"
# to:
#   "upload your existing evidence -> Aurexis scans it ->
#    review the evidence signals -> receive prioritized actions."
#
# The evidence scanner is intentionally deterministic and
# transparent. It is a heuristic document scan, NOT an AI/legal
# compliance determination and NOT a substitute for expert review.
# ============================================================

st.set_page_config(
    page_title="Aurexis — AI Governance Evidence Intelligence",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# -----------------------------
# Styling
# -----------------------------
st.markdown(
    """
<style>
.block-container {
    max-width: 1180px;
    padding-top: 1.5rem;
    padding-bottom: 4rem;
}
.hero {
    padding: 2.6rem 2.7rem;
    border: 1px solid rgba(128,128,128,.20);
    border-radius: 24px;
    background: linear-gradient(135deg, rgba(110,110,110,.10), rgba(110,110,110,.025));
    margin-bottom: 1.35rem;
}
.hero h1 {
    font-size: 3rem;
    line-height: 1.05;
    margin: .75rem 0 .65rem 0;
    letter-spacing: -0.04em;
}
.hero p {
    font-size: 1.12rem;
    color: #777;
    max-width: 900px;
    margin-bottom: 0;
}
.badge {
    display:inline-block;
    padding:.35rem .65rem;
    border-radius:999px;
    border:1px solid rgba(128,128,128,.25);
    font-size:.78rem;
    margin-right:.35rem;
}
.card {
    border:1px solid rgba(128,128,128,.20);
    border-radius:16px;
    padding:1.1rem 1.2rem;
    margin:.5rem 0;
}
.small { color:#777; font-size:.88rem; }
.good { border-left:4px solid #2e8b57; padding:.75rem 0 .75rem 12px; }
.warn { border-left:4px solid #d28b00; padding:.75rem 0 .75rem 12px; }
.risk { border-left:4px solid #c94c4c; padding:.75rem 0 .75rem 12px; }
.info-box {
    border:1px solid rgba(128,128,128,.18);
    border-radius:14px;
    padding:1rem 1.05rem;
    height:100%;
}
.score-box {
    border:1px solid rgba(128,128,128,.20);
    border-radius:18px;
    padding:1.25rem;
    text-align:center;
    min-height:130px;
}
.score-number { font-size:3.3rem; font-weight:700; letter-spacing:-0.04em; }
.pill-high { color:#b42318; font-weight:700; }
.pill-medium { color:#b54708; font-weight:700; }
.pill-low { color:#067647; font-weight:700; }
.evidence-found { color:#067647; font-weight:700; }
.evidence-partial { color:#b54708; font-weight:700; }
.evidence-missing { color:#b42318; font-weight:700; }
.method-note {
    border:1px solid rgba(128,128,128,.18);
    border-radius:14px;
    padding:.9rem 1rem;
    background:rgba(128,128,128,.035);
}
.stButton > button, .stDownloadButton > button { border-radius:10px; }
footer {visibility:hidden;}
</style>
""",
    unsafe_allow_html=True,
)


# -----------------------------
# Evidence taxonomy
# -----------------------------
EVIDENCE_CATEGORIES = {
    "intended_use": {
        "label": "Intended use & purpose",
        "description": "Purpose, scope, users, deployment context, or intended use is documented.",
        "keywords": [
            "intended use", "intended purpose", "use case", "purpose", "scope",
            "deployment context", "target users", "intended users",
        ],
        "weight": 1.0,
    },
    "performance": {
        "label": "Performance evaluation",
        "description": "Evaluation, validation, test results, metrics, or performance limitations are documented.",
        "keywords": [
            "accuracy", "precision", "recall", "f1", "auc", "performance",
            "evaluation", "evaluated", "validation", "test set", "benchmark",
            "false positive", "false negative", "error rate", "limitations",
        ],
        "weight": 1.0,
    },
    "fairness": {
        "label": "Fairness & subgroup testing",
        "description": "Fairness, bias, subgroup, protected-group, or disparate-impact analysis is documented.",
        "keywords": [
            "fairness", "fairness testing", "bias", "demographic parity",
            "equalized odds", "disparate impact", "subgroup", "protected group",
            "protected attribute", "intersectional", "adverse impact",
        ],
        "weight": 1.2,
    },
    "monitoring": {
        "label": "Monitoring & drift",
        "description": "Production monitoring, drift detection, alerting, thresholds, or ongoing evaluation is documented.",
        "keywords": [
            "monitoring", "monitor", "drift", "data drift", "model drift",
            "concept drift", "alert", "threshold", "performance monitoring",
            "production monitoring", "retraining", "continuous monitoring",
        ],
        "weight": 1.1,
    },
    "security": {
        "label": "Security & access controls",
        "description": "Security, access, authentication, authorization, encryption, secrets, or incident response is documented.",
        "keywords": [
            "security", "access control", "authentication", "authorization",
            "encryption", "secrets", "credential", "least privilege", "incident response",
            "vulnerability", "penetration test", "threat model",
        ],
        "weight": 1.0,
    },
    "explainability": {
        "label": "Explainability & transparency",
        "description": "Interpretability, explanation methods, feature importance, or user-facing transparency is documented.",
        "keywords": [
            "explainability", "explainable", "interpretability", "interpretable",
            "shap", "lime", "feature importance", "explanation", "transparency",
            "reason code", "decision factors",
        ],
        "weight": 0.9,
    },
    "human_oversight": {
        "label": "Human oversight & escalation",
        "description": "Human review, intervention, override, appeal, escalation, or human-in-the-loop processes are documented.",
        "keywords": [
            "human oversight", "human review", "human-in-the-loop", "human in the loop",
            "human intervention", "override", "escalation", "appeal", "manual review",
            "reviewer", "approval workflow", "operator",
        ],
        "weight": 1.1,
    },
    "documentation": {
        "label": "System documentation & ownership",
        "description": "Model/system documentation, owner, version, lifecycle, limitations, or change history is documented.",
        "keywords": [
            "model card", "system card", "documentation", "documented",
            "limitations", "owner", "system owner", "version", "version history",
            "change log", "lifecycle", "maintenance", "responsible team",
        ],
        "weight": 1.0,
    },
    "privacy": {
        "label": "Privacy & data governance",
        "description": "Personal data, privacy, retention, consent, data protection, or PII controls are documented.",
        "keywords": [
            "privacy", "personal data", "pii", "personally identifiable",
            "gdpr", "data retention", "retention period", "consent", "data protection",
            "data minimization", "anonymization", "pseudonymization",
        ],
        "weight": 1.0,
    },
    "governance": {
        "label": "Risk governance & accountability",
        "description": "Risk assessment, governance roles, approval, accountability, policy, or risk-management evidence is documented.",
        "keywords": [
            "risk assessment", "risk management", "governance", "governance policy",
            "accountability", "approval", "risk owner", "responsibility",
            "risk register", "policy", "control", "oversight committee",
        ],
        "weight": 1.1,
    },
}

CONTROL_TO_CATEGORY = {
    "monitoring": "monitoring",
    "fairness": "fairness",
    "explainability": "explainability",
    "documentation": "documentation",
    "security": "security",
}


# -----------------------------
# Session state
# -----------------------------
def init_state():
    defaults = {
        "step": 1,
        "audit": None,
        "evidence_records": [],
        "evidence_scan": None,
        "review_statuses": {},
        "control_answers": {},
        "lead": {},
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


init_state()


# -----------------------------
# General helpers
# -----------------------------
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def safe_filename(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return value[:80] or "aurexis_report"


def snippet_around(text: str, keyword: str, radius: int = 110) -> str:
    lowered = text.lower()
    idx = lowered.find(keyword.lower())
    if idx < 0:
        return clean_text(text)[:220]
    start = max(0, idx - radius)
    end = min(len(text), idx + len(keyword) + radius)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return clean_text(text[start:end])[:260] + suffix if prefix == "" else prefix + clean_text(text[start:end])[:250] + suffix


def decode_text(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


# -----------------------------
# File extraction
# -----------------------------
def extract_document(uploaded_file):
    """Return page-like text units from an uploaded supported document."""
    raw = uploaded_file.getvalue()
    name = uploaded_file.name
    suffix = name.lower().rsplit(".", 1)[-1] if "." in name else ""

    pages = []
    warnings = []

    try:
        if suffix == "pdf":
            if not PYPDF_AVAILABLE:
                return {
                    "name": name,
                    "hash": sha256_bytes(raw),
                    "size": len(raw),
                    "pages": [],
                    "warnings": ["PDF extraction requires the pypdf package."],
                }
            reader = PdfReader(io.BytesIO(raw))
            for page_number, page in enumerate(reader.pages, 1):
                text = page.extract_text() or ""
                pages.append({"page": page_number, "text": text})
            if not any(clean_text(p["text"]) for p in pages):
                warnings.append("The PDF did not yield extractable text. It may be scanned/image-only.")

        elif suffix in {"txt", "md"}:
            pages = [{"page": 1, "text": decode_text(raw)}]

        elif suffix == "json":
            parsed = json.loads(decode_text(raw))
            pages = [{"page": 1, "text": json.dumps(parsed, indent=2, ensure_ascii=False)}]

        elif suffix == "csv":
            df = pd.read_csv(io.BytesIO(raw))
            # Bound extraction size for predictable demo performance.
            preview = df.head(500).to_csv(index=False)
            pages = [{"page": 1, "text": preview}]
            if len(df) > 500:
                warnings.append("Only the first 500 CSV rows were scanned in this demo.")

        else:
            warnings.append("Unsupported file type.")

    except Exception as exc:
        warnings.append(f"Could not extract this file: {type(exc).__name__}.")

    return {
        "name": name,
        "hash": sha256_bytes(raw),
        "size": len(raw),
        "pages": pages,
        "warnings": warnings,
    }


# -----------------------------
# Evidence intelligence
# -----------------------------
def scan_evidence(documents):
    """Deterministic, explainable evidence scan across uploaded documents."""
    category_results = {}

    all_units = []
    for doc in documents:
        for unit in doc.get("pages", []):
            text = unit.get("text", "") or ""
            if text.strip():
                all_units.append({
                    "file": doc["name"],
                    "page": unit.get("page", 1),
                    "text": text,
                })

    for category_key, meta in EVIDENCE_CATEGORIES.items():
        matches = []
        unique_keywords = set()
        total_hits = 0

        for unit in all_units:
            lowered = unit["text"].lower()
            for keyword in meta["keywords"]:
                count = lowered.count(keyword.lower())
                if count:
                    total_hits += min(count, 3)
                    unique_keywords.add(keyword)
                    if len(matches) < 5:
                        matches.append({
                            "file": unit["file"],
                            "page": unit["page"],
                            "keyword": keyword,
                            "snippet": snippet_around(unit["text"], keyword),
                        })

        if total_hits >= 3 or len(unique_keywords) >= 3:
            status = "Found"
            confidence = min(0.96, 0.62 + 0.07 * min(len(unique_keywords), 5))
        elif total_hits >= 1:
            status = "Partial"
            confidence = min(0.72, 0.40 + 0.10 * min(len(unique_keywords), 3))
        else:
            status = "Not detected"
            confidence = 0.25

        category_results[category_key] = {
            "label": meta["label"],
            "description": meta["description"],
            "status": status,
            "confidence": confidence,
            "keywords": sorted(unique_keywords),
            "matches": matches,
            "hit_count": total_hits,
            "weight": meta["weight"],
        }

    return category_results


def evidence_completeness(scan):
    if not scan:
        return 0.0
    weighted_total = 0.0
    weighted_found = 0.0
    for result in scan.values():
        weight = result["weight"]
        weighted_total += weight
        value = {"Found": 1.0, "Partial": 0.55, "Not detected": 0.0}[result["status"]]
        weighted_found += value * weight
    return (weighted_found / weighted_total * 100.0) if weighted_total else 0.0


def status_value(status):
    return {"Implemented": 1.0, "Partial": 0.55, "Not yet": 0.20, "Not sure": 0.35}.get(status, 0.35)


def status_from_evidence(result):
    if not result:
        return "Not sure"
    return {"Found": "Implemented", "Partial": "Partial", "Not detected": "Not yet"}[result["status"]]


def status_class(status):
    if status == "Found":
        return "evidence-found"
    if status == "Partial":
        return "evidence-partial"
    return "evidence-missing"


def evidence_signal_label(result):
    return result["status"]


# -----------------------------
# Governance assessment
# -----------------------------
def exposure_score(domain, jurisdiction, model_type, high_impact, control_values, evidence_score):
    """Demo-only exposure score. Higher means greater governance exposure."""
    score = 10.0

    domain_weights = {
        "Financial services": 22,
        "Healthcare": 24,
        "Employment / HR": 21,
        "Education": 16,
        "Insurance": 20,
        "Marketing / recommendations": 7,
        "Other": 5,
    }
    score += domain_weights.get(domain, 8)

    if jurisdiction in ["EU / EEA", "EU + U.S."]:
        score += 7
    elif jurisdiction == "U.S.":
        score += 4

    if model_type in ["Generative AI / LLM", "Computer vision"]:
        score += 4

    if high_impact:
        score += 12

    for value in control_values.values():
        score += (1.0 - value) * 5.0

    score += max(0.0, (65.0 - evidence_score) * 0.18)
    score -= min(8.0, evidence_score * 0.05)

    return max(0.0, min(score, 99.0))


def readiness_label(score):
    if score >= 75:
        return "HIGH EXPOSURE", "Do not treat this assessment as deployment approval. Close the highest-priority governance gaps and retain evidence of remediation."
    if score >= 50:
        return "ELEVATED EXPOSURE", "Additional controls and evidence should be completed before production deployment."
    if score >= 30:
        return "MODERATE EXPOSURE", "Proceed only with a documented monitoring, ownership, review, and remediation plan."
    return "LOWER EXPOSURE", "The assessment found comparatively fewer governance gaps. Maintain evidence and reassess when the system or context changes."


def maturity_label(value):
    if value >= 0.80:
        return "Strong"
    if value >= 0.55:
        return "Partial"
    return "Gap"


def finding_severity(status, category):
    high_categories = {"fairness", "monitoring", "security", "human_oversight", "governance"}
    if status == "Not detected" and category in high_categories:
        return "High"
    if status == "Not detected":
        return "Medium"
    if status == "Partial":
        return "Medium"
    return "Low"


def generate_findings(scan, controls, audit):
    findings = []

    if not audit.get("evidence_records"):
        findings.append({
            "severity": "High",
            "area": "Evidence completeness",
            "finding": "No governance evidence artifact was supplied for this assessment.",
            "action": "Upload the model card, evaluation report, risk assessment, security assessment, or equivalent governance documentation.",
            "category": "evidence",
        })

    for category_key, result in scan.items():
        if result["status"] == "Found":
            continue

        severity = finding_severity(result["status"], category_key)
        meta = EVIDENCE_CATEGORIES[category_key]
        action_map = {
            "intended_use": "Document the system purpose, intended users, scope, deployment context, and material limitations.",
            "performance": "Retain evaluation methodology, metrics, validation results, test conditions, and known performance limitations.",
            "fairness": "Run appropriate subgroup/fairness testing and retain the methodology, results, thresholds, and remediation decisions.",
            "monitoring": "Define production monitoring, drift/performance thresholds, alerting, ownership, and escalation procedures.",
            "security": "Document access control, authentication, data handling, secrets management, vulnerability management, and incident response.",
            "explainability": "Document an appropriate explanation method, important decision factors, limitations, and user-facing transparency.",
            "human_oversight": "Define human review, intervention, override, escalation, and appeal paths appropriate to the system's impact.",
            "documentation": "Maintain a model/system record covering owner, version, intended use, limitations, evaluation, and lifecycle changes.",
            "privacy": "Document personal-data handling, data minimization, retention, privacy controls, and applicable data-protection obligations.",
            "governance": "Assign accountability, document risk decisions, maintain approvals/policies, and retain evidence of governance review.",
        }
        findings.append({
            "severity": severity,
            "area": meta["label"],
            "finding": f"Aurexis {result['status'].lower()} evidence for {meta['label'].lower()} in the uploaded material.",
            "action": action_map[category_key],
            "category": category_key,
        })

    # Add a control-specific finding when the self-reported answer conflicts with strong evidence.
    for control_key, value in controls.items():
        category = CONTROL_TO_CATEGORY.get(control_key)
        evidence = scan.get(category)
        if evidence and evidence["status"] == "Found" and value < 0.55:
            findings.append({
                "severity": "Medium",
                "area": EVIDENCE_CATEGORIES[category]["label"],
                "finding": "Uploaded evidence contains governance signals, but the current control self-assessment is below 'Partial'.",
                "action": "Review the underlying evidence and confirm whether the control is implemented, current, and operational rather than merely documented.",
                "category": category,
            })

    priority_order = {"High": 0, "Medium": 1, "Low": 2}
    findings.sort(key=lambda item: priority_order[item["severity"]])

    # De-duplicate identical area/severity combinations.
    deduped = []
    seen = set()
    for finding in findings:
        key = (finding["area"], finding["severity"])
        if key not in seen:
            seen.add(key)
            deduped.append(finding)

    if not deduped:
        deduped = [{
            "severity": "Low",
            "area": "Overall",
            "finding": "No major evidence gaps were identified by this deterministic demo scan.",
            "action": "Validate the findings with the system owner and maintain evidence as the system changes.",
            "category": "overall",
        }]

    return deduped


def framework_mapping(jurisdiction, high_impact):
    rows = [
        ["NIST AI RMF", "Govern / Map / Measure / Manage", "Roles, risk identification, measurement, monitoring, and evidence"],
        ["ISO/IEC 42001", "AI management system", "Accountability, planning, operation, evaluation, and continual improvement"],
    ]
    if jurisdiction in ["EU / EEA", "EU + U.S."]:
        rows.append([
            "EU AI Act",
            "Potential risk/control relevance",
            "Potential relevance of risk classification, documentation, human oversight, monitoring, and record keeping",
        ])
    if high_impact:
        rows.append([
            "Responsible AI",
            "Human oversight",
            "Review, escalation, accountability, intervention, and transparency controls",
        ])
    return rows


def build_executive_summary(audit):
    high_count = sum(f["severity"] == "High" for f in audit["findings"])
    medium_count = sum(f["severity"] == "Medium" for f in audit["findings"])
    evidence_score = audit.get("evidence_completeness", 0.0)

    if high_count:
        return (
            f"Aurexis identified {high_count} high-priority governance gap(s) and {medium_count} "
            f"medium-priority gap(s) for {audit['model_name']}. Evidence completeness was approximately "
            f"{evidence_score:.0f}%. The most important next step is to close high-priority gaps and retain "
            "evidence showing that the controls are implemented and operational."
        )
    if medium_count:
        return (
            f"Aurexis identified {medium_count} medium-priority governance gap(s) for "
            f"{audit['model_name']}. Evidence completeness was approximately {evidence_score:.0f}%. "
            "The next step is to strengthen partial or missing evidence and validate control operation."
        )
    return (
        f"Aurexis did not identify major governance gaps in this deterministic demo scan for {audit['model_name']}. "
        f"Evidence completeness was approximately {evidence_score:.0f}%. Continue monitoring and reassess when "
        "the system or deployment context changes."
    )


def next_actions(audit):
    actions = []
    for finding in audit["findings"]:
        if finding["severity"] in ["High", "Medium"]:
            actions.append(finding["action"])
    return actions[:5]


def build_report_text(audit):
    lines = [
        "AUREXIS SYSTEMS — AI GOVERNANCE READINESS ASSESSMENT",
        "",
        f"Generated: {audit['timestamp']}",
        f"Organization: {audit['organization']}",
        f"Model / System: {audit['model_name']}",
        f"Domain: {audit['domain']}",
        f"Jurisdiction: {audit['jurisdiction']}",
        f"Exposure score: {audit['risk_score']:.0f}/100",
        f"Exposure level: {audit['risk_label']}",
        f"Evidence completeness: {audit['evidence_completeness']:.0f}%",
        "",
        "EXECUTIVE SUMMARY",
        build_executive_summary(audit),
        "",
        "EVIDENCE INTELLIGENCE MATRIX",
    ]

    for result in audit["evidence_scan"].values():
        lines.append(
            f"- {result['label']}: {result['status']} | confidence {result['confidence']:.0%}"
        )
        for match in result["matches"][:2]:
            lines.append(
                f"  Evidence: {match['file']} p.{match['page']} | {match['snippet']}"
            )

    lines += ["", "PRIORITY FINDINGS"]
    for i, finding in enumerate(audit["findings"], 1):
        lines += [
            f"{i}. [{finding['severity']}] {finding['area']}: {finding['finding']}",
            f"   Recommended action: {finding['action']}",
        ]

    lines += ["", "NEXT ACTIONS"]
    for action in next_actions(audit):
        lines.append("- " + action)

    lines += ["", "FRAMEWORK MAPPING"]
    for row in audit["frameworks"]:
        lines.append("- " + " | ".join(row))

    lines += ["", "EVIDENCE RECORD"]
    for record in audit["evidence_records"]:
        lines.append(f"- {record['name']} | {record['size']/1024:.1f} KB | SHA-256 {record['hash']}")

    lines += [
        "",
        "METHOD",
        "The evidence intelligence layer uses a deterministic keyword/phrase scan over extracted text. "
        "A finding means evidence was not detected by this demo scanner; it does not prove that a control is absent.",
        "",
        "DISCLAIMER",
        "This assessment provides governance-readiness guidance and is not legal advice, regulatory certification, "
        "or a determination of legal compliance. Production assessments should be reviewed by qualified experts.",
    ]
    return "\n".join(lines)


# -----------------------------
# PDF report
# -----------------------------
def make_pdf(audit):
    if not REPORTLAB_AVAILABLE:
        return None

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 48

    def write_line(text, size=9, gap=13):
        nonlocal y
        if y < 48:
            c.showPage()
            y = height - 48
        c.setFont("Helvetica", size)
        c.drawString(45, y, str(text)[:112])
        y -= gap

    write_line("AUREXIS SYSTEMS", 18, 23)
    write_line("AI Governance Readiness Assessment", 13, 22)
    write_line(f"Generated: {audit['timestamp']}")
    write_line(f"Organization: {audit['organization']}")
    write_line(f"Model / System: {audit['model_name']}")
    write_line(f"Domain: {audit['domain']}")
    write_line(f"Jurisdiction: {audit['jurisdiction']}")
    write_line(f"Exposure score: {audit['risk_score']:.0f}/100", 11, 17)
    write_line(f"Exposure level: {audit['risk_label']}", 11, 17)
    write_line(f"Evidence completeness: {audit['evidence_completeness']:.0f}%", 11, 22)

    write_line("EXECUTIVE SUMMARY", 11, 18)
    for sentence in re.split(r"(?<=[.!?])\s+", build_executive_summary(audit)):
        if sentence.strip():
            write_line(sentence.strip(), 9, 13)

    write_line("EVIDENCE INTELLIGENCE", 11, 18)
    for result in audit["evidence_scan"].values():
        write_line(f"{result['label']}: {result['status']} | confidence {result['confidence']:.0%}")
        if result["matches"]:
            match = result["matches"][0]
            write_line(f"  Source: {match['file']} p.{match['page']} | {match['snippet']}")

    write_line("PRIORITY FINDINGS", 11, 18)
    for i, finding in enumerate(audit["findings"], 1):
        write_line(f"{i}. [{finding['severity']}] {finding['area']}: {finding['finding']}")
        write_line(f"   Action: {finding['action']}")

    write_line("NEXT ACTIONS", 11, 18)
    for action in next_actions(audit):
        write_line("- " + action)

    write_line("FRAMEWORK MAPPING", 11, 18)
    for row in audit["frameworks"]:
        write_line(" | ".join(row))

    write_line("EVIDENCE RECORD", 11, 18)
    for record in audit["evidence_records"]:
        write_line(f"{record['name']} | SHA-256 {record['hash'][:24]}…")

    write_line("METHOD", 11, 18)
    write_line("Deterministic keyword/phrase scan over extracted document text. Evidence detection is not proof of control implementation.")

    write_line("DISCLAIMER", 10, 18)
    write_line("This is a governance-readiness assessment, not legal advice, regulatory certification, or a determination of legal compliance.")
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


# -----------------------------
# Reset
# -----------------------------
def reset_assessment():
    st.session_state.step = 1
    st.session_state.audit = None
    st.session_state.evidence_records = []
    st.session_state.evidence_scan = None
    st.session_state.review_statuses = {}
    st.session_state.control_answers = {}
    st.session_state.lead = {}


# ============================================================
# HEADER
# ============================================================
st.markdown(
    """
<div class="hero">
    <div>
      <span class="badge">AUREXIS SYSTEMS</span>
      <span class="badge">EVIDENCE INTELLIGENCE</span>
      <span class="badge">AI GOVERNANCE</span>
    </div>
    <h1>Turn AI documentation into a governance readiness assessment.</h1>
    <p>
      Upload your existing model card, evaluation report, risk assessment, or security documentation.
      Aurexis scans the evidence, identifies governance signals and gaps, and turns them into prioritized actions.
    </p>
</div>
""",
    unsafe_allow_html=True,
)

if st.session_state.step == 1:
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown('<div class="info-box"><b>🔎 Detect</b><br><span class="small">Find governance evidence across your existing AI documentation.</span></div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="info-box"><b>📊 Assess</b><br><span class="small">Review evidence coverage, control signals, exposure, and confidence.</span></div>', unsafe_allow_html=True)
    with c3:
        st.markdown('<div class="info-box"><b>🛠️ Act</b><br><span class="small">Get prioritized remediation actions and a shareable PDF report.</span></div>', unsafe_allow_html=True)

    st.caption("Typical assessment time: 5–10 minutes · No credit card required")


# ============================================================
# PROGRESS
# ============================================================
steps = ["1. System", "2. Evidence", "3. Findings", "4. Report"]
cols = st.columns(4)
for index, label in enumerate(steps, 1):
    with cols[index - 1]:
        if st.session_state.step == index:
            st.markdown(f"**→ {label}**")
        elif st.session_state.step > index:
            st.markdown(f"✓ {label}")
        else:
            st.markdown(label)

st.divider()


# ============================================================
# STEP 1 — SYSTEM
# ============================================================
if st.session_state.step == 1:
    st.subheader("Tell us about your AI system")
    st.caption("Aurexis uses this context to interpret the evidence scan and prioritize governance issues.")

    with st.form("system_form"):
        c1, c2 = st.columns(2)

        with c1:
            organization = st.text_input("Organization *", placeholder="Acme AI")
            model_name = st.text_input("AI system name *", placeholder="LoanRisk Predictor")
            domain = st.selectbox(
                "Primary domain",
                [
                    "Financial services", "Healthcare", "Employment / HR", "Education",
                    "Insurance", "Marketing / recommendations", "Other",
                ],
            )

        with c2:
            jurisdiction = st.selectbox("Primary deployment market", ["U.S.", "EU / EEA", "EU + U.S.", "Other"])
            model_type = st.selectbox(
                "AI system type",
                ["Predictive ML", "Generative AI / LLM", "Computer vision", "Recommendation system", "Other"],
            )
            high_impact = st.radio(
                "Could this system materially affect access to an important service, opportunity, or outcome?",
                ["Yes", "No", "Not sure"],
                horizontal=True,
            )

        intended_use = st.text_area(
            "What does the AI system do? *",
            placeholder="Example: The model predicts whether a transaction should receive additional fraud review.",
            height=110,
        )

        st.caption("* Required fields")
        submitted = st.form_submit_button("Continue to Evidence →", type="primary", use_container_width=True)

    if submitted:
        if not organization.strip() or not model_name.strip() or not intended_use.strip():
            st.error("Please complete the three required fields before continuing.")
        else:
            st.session_state.audit = {
                "organization": organization.strip(),
                "model_name": model_name.strip(),
                "domain": domain,
                "jurisdiction": jurisdiction,
                "model_type": model_type,
                "high_impact": high_impact == "Yes",
                "high_impact_answer": high_impact,
                "intended_use": intended_use.strip(),
                "timestamp": now_utc(),
            }
            st.session_state.step = 2
            st.rerun()


# ============================================================
# STEP 2 — EVIDENCE INTELLIGENCE
# ============================================================
elif st.session_state.step == 2:
    st.subheader("Upload your existing AI documentation")
    st.caption("Upload the evidence your team already has. Aurexis will extract text and scan it for governance signals.")

    st.markdown(
        """
<div class="card">
<b>Useful evidence examples</b><br>
<span class="small">Model card · system card · evaluation report · fairness test · risk assessment · security assessment · monitoring report · governance policy</span>
</div>
""",
        unsafe_allow_html=True,
    )

    uploaded_files = st.file_uploader(
        "Upload governance evidence",
        type=["pdf", "txt", "csv", "json", "md"],
        accept_multiple_files=True,
        help="For this public demo, do not upload confidential personal data, secrets, credentials, or regulated records.",
        key="evidence_uploader_v3",
    )

    if uploaded_files:
        documents = []
        for uploaded_file in uploaded_files:
            documents.append(extract_document(uploaded_file))

        scan = scan_evidence(documents)
        completeness = evidence_completeness(scan)

        st.session_state.evidence_records = [
            {"name": d["name"], "hash": d["hash"], "size": d["size"]} for d in documents
        ]
        st.session_state.evidence_scan = scan

        st.success(f"Aurexis scanned {len(documents)} evidence file(s).")

        c1, c2, c3 = st.columns(3)
        c1.metric("Files scanned", len(documents))
        c2.metric("Evidence completeness", f"{completeness:.0f}%")
        c3.metric("Governance areas", len(EVIDENCE_CATEGORIES))

        st.markdown("### Evidence intelligence preview")
        preview_rows = []
        for key, result in scan.items():
            preview_rows.append({
                "Area": result["label"],
                "Signal": result["status"],
                "Confidence": f"{result['confidence']:.0%}",
                "Evidence hits": result["hit_count"],
            })
        st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)

        with st.expander("Review detected evidence", expanded=False):
            for result in scan.values():
                css = status_class(result["status"])
                st.markdown(
                    f"**{result['label']}** — <span class='{css}'>{result['status']}</span> · confidence {result['confidence']:.0%}",
                    unsafe_allow_html=True,
                )
                if result["matches"]:
                    for match in result["matches"][:2]:
                        st.caption(f"{match['file']} · p.{match['page']} · {match['keyword']}: {match['snippet']}")
                else:
                    st.caption("No matching evidence signal was detected by the demo scanner.")

        warnings = [w for d in documents for w in d.get("warnings", [])]
        if warnings:
            with st.expander("Extraction notes", expanded=False):
                for warning in warnings:
                    st.warning(warning)

        with st.expander("Evidence integrity details", expanded=False):
            for record in st.session_state.evidence_records:
                st.write(f"**{record['name']}** · {record['size']/1024:.1f} KB")
                st.code(record["hash"], language="text")
            st.caption("SHA-256 values are integrity fingerprints for this demo session. They are not legal certifications or proof that a document is accurate.")

    else:
        st.info("Upload one or more documents to activate Evidence Intelligence. You can continue without evidence, but the report will flag evidence completeness as a priority gap.")

    st.markdown(
        '<div class="method-note"><b>How this works:</b> V3 uses a deterministic phrase/keyword scan over extracted text. “Not detected” means the scanner did not find a signal; it does <i>not</i> prove that the control is absent.</div>',
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Back", use_container_width=True):
            st.session_state.step = 1
            st.rerun()
    with c2:
        if st.button("Review Findings →", type="primary", use_container_width=True):
            st.session_state.step = 3
            st.rerun()


# ============================================================
# STEP 3 — FINDINGS / HUMAN REVIEW
# ============================================================
elif st.session_state.step == 3:
    audit = st.session_state.audit
    scan = st.session_state.evidence_scan or {}

    st.subheader("Review Aurexis' evidence signals")
    st.caption("Confirm what is actually implemented. Documentation alone does not prove an operational control.")

    if scan:
        review_rows = []
        for key, result in scan.items():
            default = st.session_state.review_statuses.get(key, status_from_evidence(result))
            choice = st.radio(
                f"{result['label']}",
                ["Implemented", "Partial", "Not yet", "Not sure"],
                index=["Implemented", "Partial", "Not yet", "Not sure"].index(default),
                horizontal=True,
                key=f"review_{key}",
                help=result["description"],
            )
            st.session_state.review_statuses[key] = choice
            review_rows.append({
                "Area": result["label"],
                "Aurexis signal": result["status"],
                "Your review": choice,
                "Confidence": f"{result['confidence']:.0%}",
            })

        st.markdown("### Review summary")
        st.dataframe(pd.DataFrame(review_rows), use_container_width=True, hide_index=True)
    else:
        st.warning("No evidence was uploaded. You can still complete the self-reported control review below.")

    st.markdown("### Control confirmation")
    control_definitions = [
        ("monitoring", "Monitoring & drift", "Do you monitor model performance, drift, incidents, or other production signals?"),
        ("fairness", "Fairness / subgroup testing", "Do you have documented subgroup or fairness testing appropriate to the system?"),
        ("explainability", "Explainability / transparency", "Can your team explain important model behavior and communicate relevant limitations?"),
        ("documentation", "System documentation", "Do you maintain intended use, limitations, owner, evaluation, and lifecycle documentation?"),
        ("security", "Security / access / data controls", "Are access, data handling, secrets, and incident-response controls documented?"),
    ]

    controls = {}
    for key, title, question in control_definitions:
        evidence_category = CONTROL_TO_CATEGORY[key]
        evidence_result = scan.get(evidence_category)
        default = st.session_state.review_statuses.get(evidence_category)
        if not default:
            default = status_from_evidence(evidence_result)
        choices = ["Implemented", "Partial", "Not yet", "Not sure"]
        selected = st.selectbox(
            title,
            choices,
            index=choices.index(default),
            key=f"control_confirmation_{key}",
            help=question,
        )
        controls[key] = status_value(selected)

    evidence_score = evidence_completeness(scan) if scan else 0.0
    control_score = (sum(controls.values()) / len(controls) * 100.0) if controls else 0.0
    combined_readiness = 0.60 * evidence_score + 0.40 * control_score

    score = exposure_score(
        audit["domain"],
        audit["jurisdiction"],
        audit["model_type"],
        audit["high_impact"],
        controls,
        evidence_score,
    )
    label, recommendation = readiness_label(score)

    # Build a temporary audit for preview findings.
    temp_audit = {
        **audit,
        "evidence_records": st.session_state.evidence_records,
    }
    findings = generate_findings(scan, controls, temp_audit)

    st.divider()
    st.markdown("### Assessment preview")
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f'<div class="score-box"><div class="small">Governance exposure</div><div class="score-number">{score:.0f}</div><div>/ 100</div></div>', unsafe_allow_html=True)
    c2.markdown(f'<div class="score-box"><div class="small">Evidence completeness</div><div style="font-size:1.7rem;font-weight:700;margin-top:1rem;">{evidence_score:.0f}%</div></div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="score-box"><div class="small">Control confirmation</div><div style="font-size:1.7rem;font-weight:700;margin-top:1rem;">{control_score:.0f}%</div></div>', unsafe_allow_html=True)
    c4.markdown(f'<div class="score-box"><div class="small">Exposure level</div><div style="font-size:1.1rem;font-weight:700;margin-top:1.2rem;">{label}</div></div>', unsafe_allow_html=True)

    if "HIGH" in label:
        st.error(recommendation)
    elif "ELEVATED" in label or "MODERATE" in label:
        st.warning(recommendation)
    else:
        st.success(recommendation)

    st.markdown("### What Aurexis would prioritize")
    for finding in findings[:5]:
        icon = "🔴" if finding["severity"] == "High" else ("🟠" if finding["severity"] == "Medium" else "🟢")
        st.markdown(f"{icon} **{finding['severity']} — {finding['area']}**  ")
        st.caption(f"{finding['finding']} Recommended action: {finding['action']}")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Back", use_container_width=True):
            st.session_state.step = 2
            st.rerun()
    with c2:
        if st.button("Generate My Readiness Report →", type="primary", use_container_width=True):
            frameworks = framework_mapping(audit["jurisdiction"], audit["high_impact"])
            final_audit = {
                **audit,
                "evidence_records": st.session_state.evidence_records,
                "evidence_scan": scan,
                "evidence_completeness": evidence_score,
                "control_score": control_score,
                "combined_readiness": combined_readiness,
                "controls": controls,
                "risk_score": score,
                "risk_label": label,
                "recommendation": recommendation,
                "findings": findings,
                "frameworks": frameworks,
            }
            st.session_state.audit = final_audit
            st.session_state.control_answers = controls
            st.session_state.step = 4
            st.rerun()


# ============================================================
# STEP 4 — REPORT
# ============================================================
elif st.session_state.step == 4:
    audit = st.session_state.audit
    st.subheader("Your Aurexis Governance Readiness Report")
    st.caption(f"Generated {audit['timestamp']} · {audit['organization']} · {audit['model_name']}")

    high_count = sum(f["severity"] == "High" for f in audit["findings"])
    medium_count = sum(f["severity"] == "Medium" for f in audit["findings"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Exposure score", f"{audit['risk_score']:.0f}/100")
    c2.metric("Evidence completeness", f"{audit['evidence_completeness']:.0f}%")
    c3.metric("High-priority gaps", high_count)
    c4.metric("Evidence files", len(audit["evidence_records"]))

    if "HIGH" in audit["risk_label"]:
        st.error(audit["recommendation"])
    elif "ELEVATED" in audit["risk_label"] or "MODERATE" in audit["risk_label"]:
        st.warning(audit["recommendation"])
    else:
        st.success(audit["recommendation"])

    st.markdown("## Executive assessment")
    st.markdown(f"**{audit['organization']} — {audit['model_name']}**  \n{build_executive_summary(audit)}")

    st.markdown("## Evidence intelligence")
    matrix_rows = []
    for result in audit["evidence_scan"].values():
        source = ""
        if result["matches"]:
            source = f"{result['matches'][0]['file']} · p.{result['matches'][0]['page']}"
        matrix_rows.append({
            "Governance area": result["label"],
            "Evidence signal": result["status"],
            "Confidence": f"{result['confidence']:.0%}",
            "Source": source or "No source detected",
        })
    st.dataframe(pd.DataFrame(matrix_rows), use_container_width=True, hide_index=True)

    with st.expander("View evidence excerpts and sources", expanded=False):
        for result in audit["evidence_scan"].values():
            css = status_class(result["status"])
            st.markdown(
                f"**{result['label']}** — <span class='{css}'>{result['status']}</span> · confidence {result['confidence']:.0%}",
                unsafe_allow_html=True,
            )
            if result["matches"]:
                for match in result["matches"][:3]:
                    st.caption(f"{match['file']} · p.{match['page']} · {match['keyword']}: {match['snippet']}")
            else:
                st.caption("No evidence excerpt detected by the demo scanner.")

    st.markdown("## What should you fix first?")
    actions = next_actions(audit)
    if actions:
        for index, action in enumerate(actions, 1):
            st.markdown(f"**{index}.** {action}")
    else:
        st.success("No immediate remediation action was identified by this demo assessment.")

    st.markdown("## Control maturity")
    control_titles = {
        "monitoring": "Monitoring & drift",
        "fairness": "Fairness",
        "explainability": "Explainability",
        "documentation": "Documentation",
        "security": "Security",
    }
    control_rows = []
    for key, title in control_titles.items():
        value = audit["controls"][key]
        category = CONTROL_TO_CATEGORY[key]
        evidence = audit["evidence_scan"].get(category, {})
        control_rows.append({
            "Control": title,
            "Maturity": maturity_label(value),
            "Current signal": f"{value*100:.0f}%",
            "Evidence signal": evidence.get("status", "Not detected"),
        })
    st.dataframe(pd.DataFrame(control_rows), use_container_width=True, hide_index=True)

    st.markdown("## Priority findings")
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

    st.markdown("## Governance framework mapping")
    mapping_df = pd.DataFrame(audit["frameworks"], columns=["Framework", "Relevant area", "Aurexis focus"])
    st.dataframe(mapping_df, use_container_width=True, hide_index=True)

    st.markdown("## Evidence record")
    for record in audit["evidence_records"]:
        with st.expander(record["name"], expanded=False):
            st.write(f"**Size:** {record['size']/1024:.1f} KB")
            st.code(record["hash"], language="text")
    if not audit["evidence_records"]:
        st.warning("No evidence artifact was supplied. Evidence completeness is a priority gap.")

    pdf_bytes = make_pdf(audit)
    if pdf_bytes:
        st.download_button(
            "📥 Download Governance Readiness Report (PDF)",
            data=pdf_bytes,
            file_name=f"aurexis_{safe_filename(audit['model_name']).lower()}_readiness_report.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True,
        )
    else:
        st.download_button(
            "📥 Download Governance Readiness Report (TXT)",
            data=build_report_text(audit),
            file_name="aurexis_governance_readiness_report.txt",
            mime="text/plain",
            use_container_width=True,
        )

    st.markdown(
        '<div class="method-note"><b>Assessment method:</b> The Evidence Intelligence layer is a deterministic heuristic scanner. It identifies textual evidence signals; it does not independently verify that a control is implemented, effective, current, or legally sufficient.</div>',
        unsafe_allow_html=True,
    )

    st.divider()
    st.markdown("## Want a deeper Aurexis pilot assessment?")
    st.caption("Leave your contact details if you want Aurexis to review the system beyond this self-service demo.")

    with st.form("pilot_form"):
        lc1, lc2 = st.columns(2)
        with lc1:
            lead_name = st.text_input("Name", placeholder="Jane Smith")
            lead_email = st.text_input("Work email", placeholder="jane@company.com")
        with lc2:
            lead_company = st.text_input("Company", value=audit["organization"])
            lead_role = st.text_input("Role", placeholder="CTO, AI Product Lead, Compliance")
        pilot_submitted = st.form_submit_button("Request Pilot Review →", type="primary", use_container_width=True)

    if pilot_submitted:
        if not lead_name.strip() or not lead_email.strip():
            st.error("Please provide your name and work email.")
        elif "@" not in lead_email or "." not in lead_email.split("@")[-1]:
            st.error("Please enter a valid work email address.")
        else:
            st.session_state.lead = {
                "name": lead_name.strip(),
                "email": lead_email.strip(),
                "company": lead_company.strip(),
                "role": lead_role.strip(),
                "submitted_at": now_utc(),
            }
            st.success("Pilot request captured in this demo session. Connect this form to your CRM/email workflow before using it for real leads.")
            st.json(st.session_state.lead)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Start another assessment", use_container_width=True):
            reset_assessment()
            st.rerun()
    with c2:
        st.info("Production next step: connect pilot requests and assessment records to a secure backend/CRM rather than relying on browser-session state.")


# ============================================================
# FOOTER
# ============================================================
st.markdown("---")
st.caption("Aurexis Systems — AI Governance Evidence Intelligence Demo · NIST AI RMF · EU AI Act · ISO/IEC 42001 · Responsible AI")
st.caption("Aurexis provides governance-readiness guidance. This demo is not legal advice, regulatory certification, or a determination of legal compliance.")
