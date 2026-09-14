# Aurexis Customer Demo

## Goal

This is the first customer-facing MVP for Aurexis Systems:
**AI Governance Readiness Audit**.

The customer flow is:

1. Describe AI system
2. Upload governance evidence
3. Rate governance controls
4. Receive risk score, findings, framework mapping, and PDF report

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## Deploy

Upload `app.py` and `requirements.txt` to a Streamlit deployment or GitHub repository.

## Important

This version is intentionally a customer-demo MVP. The scoring engine is deterministic and does NOT claim legal compliance or regulatory certification.

Next production step:
- move scoring into FastAPI
- store customer/audit records in PostgreSQL
- store uploaded evidence in object storage
- add authentication and tenant isolation
- add real model evaluation metrics
- connect the PDF report to the evidence and audit trail
