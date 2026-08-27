# EHOS — User Guide

A plain-language guide to EHOS (Enterprise Hospital Operating System). It
explains every module (the *services*), the four screens you work in (the
*apps*), and the everyday processes you run — from registering a patient to
printing a financial report.

Staff who will find this helpful: front desk / registration staff, nurses, and
physicians, billing and claims staff, pharmacy and laboratory technicians,
inventory and operations officers, and hospital management.

If anything below refers to a port, an IP address or a command, you can ignore
it — that is for the IT team. This guide is about **what each screen does** and
**how to get a task done**.

---

## 1. What EHOS does

EHOS is the hospital's "operating system" — one platform that connects:

- **The patient journey** — registration, appointments, queues, care,
  laboratory and imaging, medicines, billing and insurance.
- **The back office** — inventory, workflows, documentation, reporting,
  notifications, audits and analytics.
- **Artificial intelligence** — a hospital chat assistant, a knowledge base of
  approved documents, and forecasting that predicts things like bed occupancy.

Every piece of the platform is called a **service**, and each one looks after
one department's job. They talk to each other automatically: for example, when a
doctor prescribes a medicine, the pharmacy and billing services are notified,
and an audit record is created — without anyone re-typing anything.

---

## 2. The four screens (apps)

EHOS has four web applications. Each opens in a normal browser.

| Screen | What it is for |
|---|---|
| **Patient Registration** | Front desk and registration staff. Captures a new patient's details for the first time (the "Master Patient Index"). |
| **Clinical EHR Portal** | Nurses and physicians. The full patient chart — notes, vitals, diagnoses, medicines, tests, scans and more, all in tabs. |
| **HospitalGPT (AI Assistant)** | Everyone. Ask questions in plain language; the assistant answers from the hospital's approved knowledge base. |
| **Executive Dashboard** | Management. Live KPIs, forecasts and AI briefings about how the hospital is running. |

> The screens are designed to be **cross-linked** — you register a patient,
> then open the same patient in the clinical portal using a search or the
> patient's ID number.

---

## 3. Your identity and roles

- You sign in with a **username and password** (the IT team will give you your
  first one). A strong password (12+ characters with capitals, numbers and
  symbols) is required.
- **Two-factor (MFA):** the first time you log in you can add your phone
  authenticator app — after that you will enter a 6-digit code on login.
- **Roles** control what you can do:
  - *administrator* — manages system settings, users and configuration;
  - *clinician / nurse* — patient care tabs; *registration* — patient intake;
  - *billing / pharmacy / lab / radiology / inventory / claims* — their own
    departmental screens;
  - regular *user* — read access and assigned tasks.
- Every important action you take is recorded in the **audit trail** (see §13),
  so hospitals can prove who did what, when.

---

## 4. The patient journey, step by step

### Step 1 — Register the patient (Patient Registration)

A patient is registered once, creating their unique **patient ID / MRN**
(medical record number). Details include name, date of birth, gender, blood
group, language, national ID, phone, address, emergency contact and any
immediate **alerts** (such as allergies or important conditions).

- Search before registering to avoid **duplicates** — the system can merge two
  records if a mistake is found later.

### Step 2 — Book an appointment (Appointments)

Staff (or the patient by phone) can book, reschedule, cancel or complete
appointments. Available slots depend on the clinic and provider, and the system
shows what is free before you pick a time.

### Step 3 — Join the queue (Queues)

At the clinic, the patient can be added to a digital queue. Staff can:

- see the **queue board** and who is next;
- **advance** the queue when one patient is done;
- **start** and **complete** each patient's service, and **cancel** a spot.

### Step 4 — Open the encounter and record care (Clinical EHR Portal)

Open the patient's **encounter** (the current visit) and build their record:

- **Vitals** — temperature, blood pressure, heart rate, oxygen, weight, pain
  score, and more.
- **Notes** — SOAP/progress notes and discharge summaries, written and then
  **signed** (a signed note is permanent, with a full version history).
- **Diagnoses** (ICD-10), **medications**, **clinical orders**, **allergies**
  and the **problem list** (current problems, each resolvable).
- **Medical history** and a **timeline** that shows everything that has
  happened for this patient in sequence.

### Step 5 — Order and receive tests

- **Laboratory:** pick a test from the catalog (e.g. CBC, chemistry) and create
  an **order**; the lab records a **sample**, reports the **result**, and a
  clinician verifies it. Results show up in the chart with normal/high/low
  flags.
- **Radiology / imaging:** order a scan (X-ray, CT, MRI, ultrasound…) with the
  required **modality**; the radiology team schedules a **study** and the
  radiologist writes a **report** that is signed.

### Step 6 — Prescribe and dispense medicines

- **Prescribe** in the **Prescriptions** service — the chart shows current
  prescriptions and known allergies before you prescribe.
- **Pharmacy** dispenses the medicine against available stock. The pharmacist
  sees batches and expiry dates, and every dispensing is recorded.

### Step 7 — Bill and claim

- **Billing** — charges are added (consultation, tests, procedures, medicines,
  etc.) and collected into an **invoice**; payments are recorded and a receipt
  is generated.
- **Insurance** — enter the patient's **coverage** (payer, policy), create
  **claims** against a coverage, submit them, and track adjudication. **Prior
  authorizations** can be requested and approved for expensive services before
  the work is done.

### Step 8 — Support the department (back office)

- **Inventory** — maintain the item catalog and **stock on hand** (location,
  lot, expiry) and record movements (receipts and dispensations). The system
  raises **reorder alerts** when stock falls too low and shows what is
  **expiring soon**.
- **Workflows** — route work through defined stages (e.g. imaging orders or
  approval chains). Each piece of work is an **instance** that moves between
  **states**; you can see its history of **transitions**.
- **Clinical Documentation** — reusable note **templates** make writing fast;
  every note keeps a **version history** when edited.
- **Reporting** — create **report definitions** (patient, financial, clinical,
  operational, regulatory), **generate** them on demand, and **schedule**
  recurring reports with optional email delivery.

---

## 5. Using the Clinical EHR Portal (tab by tab)

Once a patient is open, the portal shows a banner with their details and the
following tabs:

- **Info** — demographics, contacts, alerts and insurance summary.
- **Chart** — a condensed clinical picture of this patient.
- **Appointments** · **Queues** · **Billing** — visit logistics and finance.
- **Prescriptions** — current and past prescriptions.
- **Pharmacy** — dispensing history for this patient.
- **Laboratory** — test catalog, orders for this patient, and results.
- **Radiology** — imaging orders, studies and reports.
- **Inventory** — stock and movements for the facility.
- **Workflows** — workflow instances that involve this patient.
- **Documentation** — the patient's notes and templates.
- **Insurance** — coverages, claims and prior authorizations.
- **Reporting** — report definitions/instances and schedules.
- **Encounters, Notes, Vitals, Diagnoses, Medications, Orders, Allergies,
  Problems, Medical History, Timeline** — the clinical record itself.

Each tab lets you **add** (via a form) and **review** (via a table). For
example, on the Laboratory tab you create an order, create a sample, and record
a result; on Notes you pick a template, write, and sign.

---

## 6. HospitalGPT (the AI assistant)

A chat box connected to the hospital's approved knowledge base:

- Type a question (e.g. *"maximum paracetamol dose for an adult"*).
- The answer is **grounded in approved documents** — the reply shows its
  **sources**, so clinicians can check them.
- Sensitive or high-risk requests can be routed for **human approval** before a
  final answer is given.
- It also offers **speech-to-text** (dictate the question), **text-to-speech**
  and **OCR** (read text from an image).
- Your chat **conversations and memories** are private to you, and a feedback
  rating helps improve it.

The assistant is **offline-first**: it runs inside the hospital, not on the
public internet.

---

## 7. The Executive Dashboard

Management view with live tiles, including: admissions, discharges, revenue,
expenses, **bed occupancy**, waiting time, staff utilisation, inventory,
mortality and readmissions. It shows:

- current values with **trends (sparklines)**;
- **forecasts** (e.g. predicted bed occupancy for the next week);
- an **AI executive briefing** summarising what management should know;
- **export to PDF and Excel** for meetings and reporting.

---

## 8. Notification service

The hospital's messaging layer. It sends **emails, SMS, push** and **in-app**
notifications from ready-made **templates** (e.g. "your lab result is ready").
Departments create templates once and reuse them; the system can also send
notifications automatically when an event happens (like a patient being
registered or a result becoming ready).

---

## 9. Configuration service

A control panel for **feature flags** and **reference settings** (e.g. enabling
or disabling tele-health, or storing a standard configuration key). Only
administrators change these; the rest of the system reads them live.

---

## 10. Analytics (data warehouse)

Data from the departments is collected into a central **analytics warehouse**
and turned into **metrics** (department and operational KPIs). Dashboards and
reports pull from here — it is the "number engine" behind the Executive
Dashboard and Reporting service.

---

## 11. Knowledge base (RAG)

The AI assistant's memory. Approved documents (guidelines, SOPs, policies) are
**ingested** — automatically broken into searchable chunks — and the AI can
**search** them semantically (searching by meaning, not just keywords). A
document goes through a **review/approval** state before it is used.

---

## 12. Prediction service

Forecasting for operations — for example, **bed occupancy** for the next 7 days
based on recent history. Models are **trained, then approved** (a human
reviews before a model's forecasts are used), and **reconciled** against what
actually happened afterwards. All forecasts are advisory.

---

## 13. Audit trail (accountability)

Every significant event (logins, patient registrations, record changes,
prescriptions, payments, …) is written to an **immutable audit record**. Records
form a **hash chain** — the system continuously verifies the chain, so any
tampering is detected and reported on the **integrity** check. This is how EHOS
demonstrates compliance (HIPAA/GDPR-style audit requirements).

---

## 14. Everyday processes — quick how-tos

**Register a new patient**
Registration screen → *Search first* (avoid duplicates) → fill the form →
save. Note their patient ID / MRN for later use.

**Open a patient chart**
Use the search box, or paste the patient UUID (from another screen).

**Record a visit**
Clinical portal → *Encounters* → *New encounter* → fill in the reason.

**Write and sign a note**
*Notes* tab → continue the SOAP note (or pick a template) → *Save* → *Sign*.
Remember: signing is final.

**Order lab tests**
*Laboratory* tab → create an order → choose tests → save. Then the lab records
the sample and result.

**Order and complete an imaging study**
*Radiology* tab → create order → the team schedules and completes the study → a
report is written and signed.

**Prescribe a medicine**
*Prescriptions* tab → *New prescription* → review allergies first → save. The
pharmacy will prepare it.

**Dispense at the pharmacy**
*Pharmacy* tab → find the medicine and stock → record **receive** (stock in) /
**dispense** (stock out).

**Add or pay an invoice**
*Billing* tab → add charges → create invoice → record payment → give receipt.

**Submit an insurance claim**
*Insurance* tab → add **coverage** → create a **claim** against it → *Submit* →
track **status** until paid/denied.

**Restock a low item**
*Inventory* tab → watch **reorder alerts** → receive stock to the right
location/lot → the alert clears.

**Generate a report**
*Reporting* tab → create/open a **definition** → *Generate Report* → or
*schedule* it with a daily/weekly time and an email recipient.

**Ask the AI assistant**
Open HospitalGPT → sign in → type your question → review the cited sources →
rate the answer.

---

## 15. Roles and responsibilities (typical)

| Department | Screen / service they mainly use |
|---|---|
| Front desk / registration | Patient Registration, Appointments, Queues |
| Nurses | Clinical Portal: vitals, notes, orders, medications |
| Physicians | Clinical Portal: chart, notes, diagnoses, prescribing, results |
| Laboratory | Laboratory service / tab |
| Radiology | Radiology service / tab |
| Pharmacy | Pharmacy + Prescriptions |
| Billing / cashier | Billing |
| Claims / insurance | Insurance |
| Inventory / stores | Inventory |
| Quality / ops | Workflows, Documentation, Configuration |
| Management | Executive Dashboard, Reporting, Analytics |
| Administration / IT | Everything, plus Audit + Notification + Keycloak |

---

## 16. Frequently asked questions

**I made a mistake in a patient's details — can I fix it?**
Yes. Names/demographics can be updated (merge or edit). Clinical items that have
been **signed** or **dispensed** are kept as history — corrections create a new
version, never a silent overwrite.

**Where are the official documents the AI uses?**
In the **Knowledge Base**. Only reviewed/approved documents are searchable by
the assistant.

**Are the forecasts a guarantee?**
No. Predictions are advisory and are reconciled against real results
afterwards.

**Who can see what I did?**
The **Audit trail** records all important actions, and the integrity check
guarantees that trail hasn't been altered.

**The AI answered something I am unsure about.**
Verify against the cited sources — that is exactly why citations are shown —
and follow your hospital's clinical protocols.

---

## 17. Getting help

- For **operational questions** about a screen, ask your department
  administrator.
- For **technical issues** (a screen won't load, a service is down), contact
  IT — the IT team uses `IT_ENGINEER_GUIDE.md` and checks service health
  (`http://localhost:8000/health`) and logs.
- The full system conditions are documented in `README.md` and
  `INSTALLATION_AND_USAGE.md`.