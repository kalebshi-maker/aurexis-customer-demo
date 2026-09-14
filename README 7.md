# Aurexis Systems — Customer V3

A customer-facing Streamlit MVP for **AI Governance Evidence Intelligence**.

## V3 flow

1. **System** — capture AI system context.
2. **Evidence** — upload one or more model cards, evaluation reports, risk/security documents, policies, CSVs, JSON, Markdown, or text files.
3. **Findings** — Aurexis extracts text and runs a transparent deterministic evidence scan across governance categories.
4. **Report** — review evidence signals, confirm control maturity, see prioritized remediation, framework mapping, and download a PDF report.

## Evidence categories

- Intended use & purpose
- Performance evaluation
- Fairness & subgroup testing
- Monitoring & drift
- Security & access controls
- Explainability & transparency
- Human oversight & escalation
- System documentation & ownership
- Privacy & data governance
- Risk governance & accountability

## Important limitation

The V3 evidence scanner is a **heuristic MVP**. It uses deterministic keyword/phrase matching over extracted document text. A result of “Not detected” means the scanner did not find a textual signal; it does **not** prove that a control is absent. A result of “Found” does **not** prove that the control is effective, current, operational, or legally sufficient.

This app is not legal advice, regulatory certification, or a determination of legal compliance.

## Local run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud

Use this repository's `app.py` as the main file and commit `requirements.txt` alongside it. Streamlit Community Cloud can then install the dependencies and run the app.

## Data handling in this MVP

Uploaded files are processed in the Streamlit session. The app retains hashes and extracted assessment metadata in session state, but does not implement a production database, object storage, authentication, tenant isolation, CRM integration, or persistent lead storage.

Streamlit's session state is tied to the browser session and resets when the session ends/reloads. Uploaded files are handled through Streamlit's uploader/session mechanisms rather than a production document store.

## Recommended production architecture

`Streamlit customer UI → FastAPI API → PostgreSQL → object storage → background evidence extraction → governance assessment service → PDF/report service → CRM/email`

Before handling real customer evidence, add authentication, tenant isolation, encrypted object storage, access controls, retention/deletion policies, audit logging, malware/content validation, and a production evidence-processing service.
