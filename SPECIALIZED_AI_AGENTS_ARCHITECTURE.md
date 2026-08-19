# SPECIALIZED_AI_AGENTS_ARCHITECTURE.md

# Enterprise Hospital Operating System (EHOS)

# Specialized AI Agents Architecture

**Version:** 1.0.0
**Document Type:** Multi-Agent Artificial Intelligence Architecture
**Audience:** AI Engineers, Software Architects, Clinical Informatics Teams, Security Engineers, Department Leads

---

## 1. Purpose

This document defines the architecture for the ten **specialized AI agents** that
make up the EHOS AI workforce. Each agent is purpose-built for one hospital
domain and is defined as a **configuration-driven agent definition** running on
the HospitalGPT platform (`ai-service`, `knowledge-service`).

This document extends:

| Governing standard | Applies to |
|---|---|
| `AI_AGENT_ARCHITECTURE.md` | agent anatomy, safety layer, approval levels 1–4, forbidden practices |
| `AI_AGENT_DEVELOPMENT_SPECIFICATION.md` | agent design rules, lifecycle, tool access control |
| `HOSPITALGPT_ARCHITECTURE.md` | ai-service/knowledge-service binding, adapter pattern, RAG grounding |
| `AI Behaviour & Operational Policy Standard.md` | local-only, truthfulness, refusal phrase, human authority |
| `EVENT_BUS.md` | event names (`EntityAction`), topic format (`domain.entity.event`) |
| `API_DESIGN_STANDARD.md` | EHOS envelope `{success, data, statusCode}` |
| `AI Behaviour & Operational Policy Standard.md` | output refusal, safety rules |

Agents are **not autonomous**. Every specialized agent is a *trusted assistant*
bound by the human-in-the-loop approval model.

---

## 2. Agent Anatomy

Every specialized agent is composed of the same nine parts, mapped to the
existing HospitalGPT platform implementation:

```
┌─────────────────────────────────────────────────────────────┐
│                   SPECIALIZED AGENT                         │
│                                                             │
│  Identity      key = agent_definition.key (registry row)     │
│  Reasoning     ReasoningEngine (mock|ollama|llamacpp)        │
│  Knowledge     RagService + permission-scoped data APIs      │
│  Memory        MemoryManager (session / workflow / patient)  │
│  Tools         ToolAccess (permission-scoped domain APIs)    │
│  Prompts       PromptManager (versioned prompt_templates)    │
│  Permissions   identity roles → tool + data scopes            │
│  Safety        SafetyLayer (output filter, refusal, score)    │
│  Audit         human approvals + ai_requests (append-only)    │
│  Events        Kafka subscriptions (domain.entity.event)     │
└─────────────────────────────────────────────────────────────┘
```

### 2.1 Mapping to storage

| Agent facet | Persisted in |
|---|---|
| Identity, capabilities, tools, approvals, config | `ai_db.agent_definitions` (`key`, `allowed_tools`, `approval_policy`, `config`) |
| Run instance + progress | `ai_db.agent_runs` (status incl. `AWAITING_APPROVAL`) |
| Every tool call | `ai_db.agent_actions` (`tool`, `input`, `output`, `requires_approval`) |
| Prompt templates | `ai_db.prompt_templates` (`code`, `vars_schema`, `safety_rules`) |
| Short-term memory | `ai_db.ai_conversations` / `ai_messages` |
| Long-term memory | `ai_db.ai_memories` |
| Request audit + approvals | `ai_db.ai_requests` (append-only) + `ai_db.ai_request_approvals` |
| Knowledge base | `knowledge_db` corpora: `GUIDELINE`, `POLICY`, `MEDICATION`, `LAB_REFERENCE` |

Agents never read another service's database directly; all data access goes
through **permission-scoped domain APIs** (per DATABASE_DESIGN.md §8.1 rule).

---

## 3. Agent Configuration Model

An agent is declared once via `agent_definitions.config` JSON. Schema:

```json
{
  "key": "clinical-agent",
  "model": {"family": "LLM", "preferred": "llama-3.1-8b", "fallback": "qwen-2.5-7b"},
  "approval_policy": {
    "default_level": 1,
    "level_by_tool": {"create_note_draft": 4, "search_guidelines": 1}
  },
  "memory": {
    "session_windows": 24,
    "patient_context": true,
    "workflow_context": "care-pathway"
  },
  "knowledge": {
    "corpora": ["GUIDELINE", "POLICY", "MEDICATION", "LAB_REFERENCE"],
    "top_k": 5
  },
  "events": {
    "subscribe": ["clinical.ehr.encounter.created", "clinical.patient.admitted"],
    "autonomous": ["summarize-new-encounter"]
  }
}
```

New agents are registered via the agent registry API, reviewed, and activated
exactly like models — pending review until approved (`agent_definitions.is_active`).

---

## 4. Shared Tool Catalog

| Tool | Read-only | Side effect | Closure |
|---|---|---|---|
| `search_knowledge(doc_type, query)` | ✅ | — | RAG retrieval; always audited in `knowledge_access_log` |
| `read_patient_summary(patient_ref)` | ✅ | — | redacted; consented read only |
| `read_vitals(patient_ref)` | ✅ | — | redacted read |
| `read_lab_results(patient_ref)` | ✅ | — | redacted read |
| `read_medications(patient_ref)` | ✅ | — | active orders |
| `read_imaging(patient_ref)` | ✅ | — | orders + reports |
| `check_interactions(order, meds, allergies)` | ✅ | — | medication DB + patient allergies |
| `check_dosage(med, patient_attrs)` | ✅ | — | medication DB |
| `check_contrast_safety(patient_ref, modality)` | ✅ | — | renal + allergy data |
| `classify_lab(panel, age, sex)` | ✅ | — | reference ranges |
| `forecast_demand(item, horizon)` | ✅ | — | consumption history |
| `validate_charge(charge_ref)` | ✅ | — | pricing + procedures |
| `check_duplicate_billing(invoice_ref)` | ✅ | — | billing history |
| `forecast_staffing(department, shift)` | ✅ | — | demand + availability |
| `check_credentials(staff_ref)` | ✅ | — | HR records |
| `query_audit_trail(entity, window)` | ✅ | — | audit/event store |
| `create_note_draft(patient_ref, kind)` | ⚠️ draft only | writes draft | *human finalizes* |
| `create_handover_draft(shift)` | ⚠️ draft only | writes draft | *human finalizes* |
| `suggest_reorder(item, qty)` | ⚠️ suggestion | none | Level 3 approval |
| `create_purchase_request(item, qty)` | ✋ action | order draft | Level 3 approval |
| `flag_violation(policy, entity)` | ⚠️ suggestion | alert | Compliance review |
| `suggest_roster(department, period)` | ⚠️ suggestion | none | HR review (Level 2) |
| `draft_report_impression(order_ref)` | ⚠️ draft only | draft | Radiologist finalizes (Level 3) |

**Rules:** read-only tools auto-run at Level 1–2; any tool that mutates or
creates a real operational record requires `requires_approval = true` and is
recorded in `agent_actions` with `approval_status = PENDING` until a human of
the required role approves.

---

## 5. Permissions Model

- **Identity** from `identity-service` (roles: `physician`, `nurse`, `pharmacist`,
  `lab-scientist`, `radiologist`, `inventory-manager`, `finance-officer`,
  `hr-officer`, `executive`, `compliance-officer`).
- **Tool scopes** are granted per agent and checked by `AgentGateway` before a
  tool call (deny-by-default). A clinical agent can call `search_knowledge` but
  never `create_purchase_request`.
- **Data scopes** mirror data governance: PHI requires an active patient
  authorization; results are served redacted through domain APIs.
- **Approval roles** (`ai_request_approvals.required_role`) name the human who
  may action Level 2–4 outputs, e.g. `pharmacist` for reorder, `radiologist`
  for impression finalize, `finance-officer` for write-off.

---

## 6. Memory Architecture per Agent

| Memory type | Content | Retention |
|---|---|---|
| Session (short-term) | current conversation turns | conversation lifetime |
| Workflow (approved operational history) | open tasks, care pathway step, order context | until task completion |
| Patient-context | redacted authorized patient lens (never full raw record) | consent window |
| Knowledge | retrieved RAG chunks | per retrieval, audited |

Per agent, `hidden in ai_memories` with `scope`, tags and expiry; prompts +
answers only. Raw uncontrolled patient information (Forbidden Memory) is never
stored.

---

## 7. Prompt Template Registry Convention

Template codes follow `agent_<key>_<purpose>_v<N>`:

```
clinical_summary_v1, clinical_timeline_v1, note_draft_v1,
nursing_handover_v1, pharmacy_interaction_v1, pharmacy_review_v1,
lab_critical_v1, radiol_appropriate_v1, inventory_reorder_v1,
finance_charge_validation_v1, hr_staffing_v1, executive_brief_v1,
compliance_policy_answer_v1
```

Each template declares `vars_schema` (e.g. `{{conversation}}`, `{{context}}`,
`{{query}}`, `{{patient_context}}`, `{{order}}`) and `safety_rules` (refusal
phrase, no-diagnosis directive, no-prescription directive). Rendered by
`PromptManager`; all templates require approval to go live.

---

## 8. Output Formats

1. **EHOS envelope** — every API response: `{"success": true, "data": ...}`.
2. **Markdown answer with sources** — human-readable; sources cited per chunk
   (doc, doc_type, score).
3. **Structured JSON** — machine-consumable: `{"type": "summary", "sections": []}`,
   `{"type": "task_list", "items": [...]}`, `{"type": "alert", "severity": ...}`.
4. **Dashboard/table payload** — KPI rows for frontends (beds, ER load, staffing, KPI list).
5. **Draft documents** — clinical note draft, handover draft, report impression —
   always gated behind a human finalize step. Never auto-persisted to EHR.

---

## 9. Event Subscriptions

Topic format `domain.entity.event` (EVENT_BUS.md §9). Agents subscribe via the
event bus and may **trigger reactive goals** (always gated by approval policy):

| Agent | Subscribes to (Kafka topics) | Reactive behavior |
|---|---|---|
| Clinical | `clinical.ehr.*`, `clinical.lab.*`, `clinical.radiology.*` | prepare summary/timeline drafts; guideline checklist on new encounter |
| Nursing | `clinical.ehr.*`, `clinical.lab.*`, `clinical.pharmacy.*` | shift handover refresh, vitals/alert triage, task list update |
| Pharmacy | `clinical.ehr.*`, `clinical.pharmacy.*`, `supply.inventory.*` | auto prescription review on `MedicationOrdered`; interaction flags |
| Laboratory | `clinical.lab.*` | result triage on `ResultAvailable`; critical alert on abnormal |
| Radiology | `clinical.radiology.*` | appropriateness & contrast checks on `ImagingRequested` |
| Inventory | `supply.inventory.*`, `clinical.pharmacy.*` | reorder suggestion on `StockLow`; forecast refresh on consumption |
| Finance | `finance.billing.*` | validate invoice on `InvoiceGenerated`; duplicate/charge checks |
| HR | `hr.*`, `clinical.scheduling.*` | staffing forecast refresh on `ShiftAssigned`; credential alerts |
| Executive | `ai.*`, `clinical.*`, `finance.*`, `supply.*`, `hr.*` | aggregate situational briefs, risk digest |
| Compliance | `ai.*`, `security.*`, `clinical.*` | policy-consent/audit gap checks on `AIRequestCreated`; access review |

---

## 10. Specialized Agents

Shared design headings per agent:

> **Tools · Memory · Permissions · Knowledge Sources · Prompt Templates · Output Formats · Event Subscriptions · Approval Level · Safety Rules**

---

### 10.1 Clinical Agent

**Purpose:** Physician-facing documentation, patient summaries, medical timeline
generation and guideline-grounded decision support for outpatient, inpatient and
emergency care.

- **Tools:** `search_knowledge`, `read_patient_summary`, `read_vitals`,
  `read_lab_results`, `read_medications`, `create_note_draft`
- **Memory:** session; patient-context (authorized, redacted); workflow
  (open encounter); knowledge (retrieved guidelines)
- **Permissions:** role `physician`; scopes `ehr:read`, `knowledge:read`,
  `note-draft:create`; **never** writes to a live EHR record
- **Knowledge Sources:** Guidance corpus `GUIDELINE`, `MEDICATION`,
  `LAB_REFERENCE`, `POLICY`; scoped domain APIs for vitals/labs/orders
- **Prompt Templates:** `clinical_summary_v1`, `clinical_timeline_v1`,
  `note_draft_v1`, `guideline_checklist_v1`
- **Output Formats:** structured clinical summary (JSON), SOAP/note draft
  (markdown, draft status), medical timeline table, checklist with cited sources
- **Event Subscriptions:** `clinical.ehr.encounter.created`,
  `clinical.lab.result.available`, `clinical.radiology.report.completed`,
  `clinical.patient.admitted` → auto-prepare summary drafts
- **Approval Level:** L1 info/summary; L2 recommendations; **L4** — note draft
  is drafted only, saved to EHR solely via explicit clinician approval
- **Safety Rules:** never issue a final diagnosis; always cite sources; redundant
  to forbid prescribing; temporarily block summaries for patients without an
  active consent

---

### 10.2 Nursing Agent

**Purpose:** Nursing shift support: handover documents, task/priority lists,
vitals monitoring assistance and care-plan reinforcement.

- **Tools:** `search_knowledge`, `read_patient_summary`, `read_vitals`,
  `read_medications`, `create_handover_draft`
- **Memory:** session; workflow (shift context, open rounds); patient-context (redacted)
- **Permissions:** role `nurse`; scopes `ehr:read`, `knowledge:read`,
  `handover-draft:create`; no order modification
- **Knowledge Sources:** `POLICY` (nursing + safety protocols), `GUIDELINE`
  (care pathways), unit rosters via domain API
- **Prompt Templates:** `nursing_handover_v1`, `nursing_task_priority_v1`,
  `nursing_vitals_alert_v1`
- **Output Formats:** handover draft (markdown/JSON), priority task list,
  vitals alert text with severity
- **Event Subscriptions:** `clinical.patient.admitted`,
  `clinical.ehr.encounter.created`, `clinical.lab.result.available`,
  `clinical.medication.dispensed` → refresh task list & handover
- **Approval Level:** L1 handover summary, L2 task re-prioritization
  recommendation; handover persisted to shift record only on charge-nurse approval
- **Safety Rules:** never prioritize a task above a clinician directive; alerts
  must be re-validated; never auto-assign medication tasks

---

### 10.3 Pharmacy Agent

**Purpose:** Medication safety: prescription review (allergy, interaction,
dose/weight, duplicate therapy), stock forecasts and reorder support.

- **Tools:** `search_knowledge`, `check_interactions`, `check_dosage`,
  `read_medications`, `forecast_demand`, `suggest_reorder`
- **Memory:** session; workflow (prescription context); knowledge (medication database)
- **Permissions:** role `pharmacist`/`pharmacy-tech`; scopes `prescription:read`,
  `knowledge:read`, `reorder:suggest`; no direct order mutation
- **Knowledge Sources:** `MEDICATION` corpus (monographs, interactions, doses),
  `GUIDELINE` (antimicrobial stewardship), `POLICY`
- **Prompt Templates:** `pharmacy_interaction_v1`, `pharmacy_review_v1`,
  `pharmacy_reorder_v1`, `pharmacy_antimicrobial_v1`
- **Output Formats:** interaction risk report (JSON), prescription review
  (recommendation list), reorder suggestion, controlled-drug summary
- **Event Subscriptions:** `clinical.ehr.medication.ordered` (auto-review),
  `clinical.medication.dispensed`, `clinical.medication.expired`,
  `supply.stock.low`
- **Approval Level:** L1 monograph/info, L2 interaction & stewardship flags
  (pharmacist review), **L3** reorder/order proposals (pharmacist approval)
- **Safety Rules:** never prescribe; every interaction flag must be
  human-confirmed before clinical action; controlled substances require extra
  role check

---

### 10.4 Laboratory Agent

**Purpose:** Diagnostics workflow: reference-range classification, delta
tracking, result prioritization and report summarization.

- **Tools:** `search_knowledge`, `read_lab_results`, `classify_lab`,
  `read_patient_summary`
- **Memory:** session; workflow (result session, time-series context);
  patient-context (redacted)
- **Permissions:** role `lab-scientist`/`pathologist`; scope `lab:read`,
  `knowledge:read`; **cannot** modify results
- **Knowledge Sources:** `LAB_REFERENCE` corpus, `POLICY` (lab quality),
  `GUIDELINE`
- **Prompt Templates:** `lab_critical_alert_v1`, `lab_delta_analysis_v1`,
  `lab_report_summary_v1`
- **Output Formats:** critical-result alert (text with severity + reason),
  delta table (JSON), report summary (markdown), normal/abnormal matrics
- **Event Subscriptions:** `clinical.lab.order.created`,
  `clinical.lab.result.available` (auto triage → alert),
  `clinical.lab.result.verified`
- **Approval Level:** L1 classification/summary; L2 recommendation (e.g. repeat
  suggestion); **never** diagnosis — pathologist always finalizes
- **Safety Rules:** result classification must never be presented as diagnosis;
  alerts that meet critical-threshold rules go straight to responsible clinician

---

### 10.5 Radiology Agent

**Purpose:** Imaging workflow: appropriateness screening, contrast-safety
checks, structured impression drafting and voice-capture expansion.

- **Tools:** `search_knowledge`, `read_imaging`, `check_contrast_safety`,
  `read_lab_results` (renal), `draft_report_impression`
- **Memory:** session; workflow (order context); patient-context (redacted, renal/allergy lens)
- **Permissions:** role `radiologist`/`rad-tech`; scopes `imaging:read`,
  `knowledge:read`, `impression-draft:create`
- **Knowledge Sources:** `GUIDELINE` (imaging appropriateness, contrast safety),
  `LAB_REFERENCE`, `POLICY`
- **Prompt Templates:** `radiol_appropriate_v1`, `radiol_contrast_v1`,
  `radiol_impression_v1`, `radiol_dictation_v1`
- **Output Formats:** appropriateness checklist (JSON), contrast-safety alert,
  impression draft (markdown), structured report skeleton
- **Event Subscriptions:** `clinical.radiology.imaging.requested` (auto
  appropriateness + contrast run), `clinical.radiology.image.captured`,
  `clinical.radiology.report.completed`
- **Approval Level:** L1 appropriateness info, L2 contrast-risk recommendation,
  **L3** impression draft finalized only with explicit radiologist approval;
  never auto-finalizes
- **Safety Rules:** impression text is never a diagnosis; contrast decisions
  require renal + allergy verification via APIs before screen confirms

---

### 10.6 Inventory Agent

**Purpose:** Supply chain: demand forecasting, expiry monitoring, stock
(reorder-point) alerts and replenishment proposals for medical supplies and
standard medications.

- **Tools:** `search_knowledge`, `forecast_demand`, `read_medications`,
  `suggest_reorder`, `create_purchase_request`
- **Memory:** session; workflow (procurement context); knowledge (formulary, policy)
- **Permissions:** role `inventory-manager`/`procurement`; scopes `inventory:read`,
  `knowledge:read`, `purchase-request:create` (approval-gated)
- **Knowledge Sources:** `POLICY` (procurement, storage, cold-chain), `MEDICATION`
  corpus, consumption history via domain API
- **Prompt Templates:** `inventory_reorder_v1`, `inventory_shortage_v1`,
  `inventory_expiry_v1`, `inventory_forecast_v1`
- **Output Formats:** reorder recommendation list (JSON), shortage warning
  (text), expiry report (table), forecast (chart data payload)
- **Event Subscriptions:** `supply.stock.low` (trigger reorder draft),
  `supply.stock.received`, `supply.stock.consumed`,
  `clinical.medication.dispensed` (forecast input)
- **Approval Level:** L1 info, L2 forecast recommendation, **L3** purchase
  request (inventory-manager approval, cost rule check)
- **Safety Rules:** never interrupt an in-progress order; every purchase draft
  records an audit trail; controlled-drug levels get extra review

---

### 10.7 Finance Agent

**Purpose:** Revenue integrity: charge/billing validation, duplicate-charge
detection, coding checks and claim-readiness assessment.

- **Tools:** `search_knowledge`, `validate_charge`, `check_duplicate_billing`,
  `read_medications`, (read-only billing APIs)
- **Memory:** session; workflow (invoice context); knowledge (finance policy)
- **Permissions:** role `finance-officer`; scopes `billing:read`, `knowledge:read`;
  **cannot** edit invoices or claim status
- **Knowledge Sources:** `POLICY` (billing + pricing), financial reference DB,
  clinical charge APIs (redacted)
- **Prompt Templates:** `finance_charge_validation_v1`,
  `finance_duplicate_alert_v1`, `finance_coding_check_v1`,
  `finance_claim_readiness_v1`
- **Output Formats:** charge-validation exception report (JSON table), duplicate
  billing alert, coding-check result, claim-readiness summary
- **Event Subscriptions:** `finance.billing.invoice.generated` (auto validate),
  `finance.billing.charge.created`, `finance.billing.payment.received`
- **Approval Level:** L1 validation info, L2 recommendation (review flags),
  **L3** adjustment/write-off proposals require finance-officer approval
- **Safety Rules:** financial decisions never auto-execute; billing actions
  cross-refer clinical record before proposing change; PHI redacted in outputs

---

### 10.8 HR Agent

**Purpose:** Workforce planning: staffing forecasts, shift coverage analysis,
credential/education monitoring and workload-balancing suggestions.

- **Tools:** `search_knowledge`, `forecast_staffing`, `check_credentials`,
  `suggest_roster`, (read-only HR APIs)
- **Memory:** session; workflow (roster context); knowledge (HR/labor policy)
- **Permissions:** role `hr-officer`/`scheduler`; scopes `hr:read`,
  `knowledge:read`; no direct roster write without approval
- **Knowledge Sources:** `POLICY` (HR, labor, credentialing), workforce demand
  data (patient volume/visits), schedule APIs
- **Prompt Templates:** `hr_staffing_forecast_v1`, `hr_roster_suggestion_v1`,
  `hr_credential_alert_v1`, `hr_workload_v1`
- **Output Formats:** coverage table (JSON), roster suggestion list, credential
  expiry alert, workload summary
- **Event Subscriptions:** `hr.shift.assigned`, `hr.employee.created`,
  `ai.*` (demand signals), `clinical.patient.admitted` (volume proxy)
- **Approval Level:** L1 HR info, **L2** roster/coverage suggestions (HR
  manager approval), **L3** for any schedule mutation (approval-gated)
- **Safety Rules:** staffing suggestions respect labor policy + fair
  allocation; never exposes personal employee PHI

---

### 10.9 Executive Agent

**Purpose:** Command-center executive intelligence: situational awareness,
KPI/target variance analysis, risk summary and strategic briefing.

- **Tools:** `search_knowledge`, read-only dashboard APIs (beds, ER load,
  staffing, inventory, finance KPIs), `forecast_demand` (open-loop)
- **Memory:** session; workflow (briefing context); knowledge (governance/corporate policy)
- **Permissions:** role `executive`/`department-head`; **aggregated/anonymized
  read-only** — never raw PHI
- **Knowledge Sources:** aggregated analytics, `POLICY` (governance), KPI
  repository; **no** direct FHIR/PHI access
- **Prompt Templates:** `executive_brief_v1`, `executive_kpi_digest_v1`,
  `executive_risk_report_v1`, `executive_scenario_v1`
- **Output Formats:** situational dashboard JSON, KPI digest (markdown),
  risk report, scenario summary
- **Event Subscriptions:** `ai.*`, `clinical.bed.*`, `clinical.emergency.*`,
  `finance.billing.*`, `supply.inventory.*`, `hr.*`
- **Approval Level:** **L1** read-only / L2 recommendations only; no mutating
  tools at all
- **Safety Rules:** only anonymized/aggregated data; forecasts labeled as
  model-based; executives never see raw patient records

---

### 10.10 Compliance Agent

**Purpose:** Governance and oversight: policy answering, consent/gaps checks,
audit-trail assertion, access reviews and documentation-capture monitoring.

- **Tools:** `search_knowledge`, `query_audit_trail`, `flag_violation`,
  (read-only auth/audit APIs)
- **Memory:** session; workflow (case context); knowledge (compliance corpus)
- **Permissions:** role `compliance-officer`/`audit`; scopes `audit:read`,
  `consent:read`, `knowledge:read`; no data modification
- **Knowledge Sources:** `POLICY` corpus, `DATA_GOVERNANCE.md` retention rules,
  `SECURITY_ARCHITECTURE.md` controls, audit/event store
- **Prompt Templates:** `compliance_policy_answer_v1`, `compliance_gap_alert_v1`,
  `compliance_audit_summary_v1`, `compliance_access_review_v1`
- **Output Formats:** policy answer (markdown + citations), gap alert, audit
  summary (JSON), access-review report
- **Event Subscriptions:** `ai.*` (AIRequestCreated → consent/retention check),
  `security.*` (policy updates, denials), `clinical.*` (documentation capture)
- **Approval Level:** L1 policy answers, **L2** findings (compliance-officer
  review); flags recommend, humans decide
- **Safety Rules:** compliance agent observes audit, never alters; cannot
  suppress or override any other agent's alert

---

## 11. Multi-Agent Workflows

Agents hand off through the orchestrator (event + shared run context); no agent
directly invokes another's DB.

### 11.1 Sepsis care pathway
```
LabOrderCreated ─► Laboratory Agent: classify (ResultAvailable)
        │ critical flag
        ▼
Clinical Agent: guideline checklist + patient timeline   (L2 recommend)
        │ apply + order
        ▼
Pharmacy Agent: interaction + dose review                (L2 flag)
        │ pharmacist approve
        ▼
Nursing Agent: refreshed task list + handover note       (L1/L2)
```

### 11.2 Medication procurement
```
MedicationDispensed ─► Inventory Agent: forecast refresh
StockLow (threshold) ─► Inventory Agent: reorder proposal (L3)
        │ inventory-manager approve
        ▼
Finance Agent: validates proposed cost vs budget         (L1/L2)
        │ finance-officer ok
        ▼
create_purchase_request (audited, approval record kept)
```

### 11.3 Emergency capacity
```
Emergency surge event ─► Executive Agent: situational brief (L1)
        │ capacity signal
        ▼
HR Agent: staffing forecast + roster suggestion           (L2)
        │ HR manager approve
        ▼
Clinical + Nursing: coverage-aware task support           (L1/L2)
```

### 11.4 Compliance trace of any run
```
AIRequestCreated (any agent) ─► Compliance Agent: consent + retention +
access-trace check (L1) ─► audit summary on request closure
```

---

## 12. Approval Level Summary by Agent

| Agent | L1 (info) | L2 (recommend) | L3 (action) | L4 (clinical decision) |
|---|---|---|---|---|
| Clinical | summary, timeline | pathway recommendation | — | finalize note draft (clinician) |
| Nursing | handover, tasks | reprioritize suggestion | persist handover (charge nurse) | — |
| Pharmacy | monograph, info | interaction/stewardship flag | reorder/draft order | — |
| Laboratory | classification | repeat/review suggestion | — | diagnosis (pathologist) |
| Radiology | appropriateness | contrast-risk recommendation | finalize impression | — |
| Inventory | info | forecast | purchase request | — |
| Finance | validation | review flags | adjust/write-off | — |
| HR | HR info | roster/coverage | schedule mutation | — |
| Executive | insight, KPI | recommendation | (none) | — |
| Compliance | policy answer | findings | — | — |

---

## 13. Safety & Governance

- **Output filter** runs on every agent response: refusal phrase, source
  citation requirement, "not-a-diagnosis" guard for clinical agents.
- **Prompt injection** hardening from `PromptManager.safety_rules` +
  `AI Behaviour` policy.
- **Forbidden for every agent:** accessing another service's DB directly,
  storing raw uncontrolled patient data, auto-writing clinical or financial
  records, external (cloud) inference, silent autonomous mutations.
- **Auditability:** agent -> tool -> action chain is fully recorded in
  `agent_runs`/`agent_actions`; every tool call has input/output hashes.

---

## 14. Implementation Mapping

| Artifact | Location |
|---|---|
| Agent definitions (10) | seeded `ai_db.agent_definitions` rows |
| Prompt templates (registry) | seeded `ai_db.prompt_templates` rows |
| Tool implementations | `ai-service` `/tools` + domain API clients per EHOS service |
| Event subscriptions | `ai-service` consumer groups on Kafka topics (§9) |
| RAG corpora | `knowledge_db` `GUIDELINE`/`POLICY`/`MEDICATION`/`LAB_REFERENCE` |
| Agent gateway + orchestrator | `ai-service` `AgentRuntime` (approvals, handoffs) |
| Audit & approvals | `ai_requests`, `ai_request_approvals`, `agent_actions` |
| Frontend control | `ai-assistant` (agent pickers, approval toasts, outputs) |

---

## 15. Final Principle

> The ten specialized EHOS agents are a coordinated digital workforce — each
> expert in its domain, each permission-scoped, each audited, and each subservient
> to human healthcare, financial, and governance professionals.

# END OF SPECIALIZED AI AGENTS ARCHITECTURE