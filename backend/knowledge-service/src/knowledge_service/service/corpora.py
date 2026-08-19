"""Default local RAG corpora for HospitalGPT.

These are bootstrapped, offline knowledge documents covering the four requested
knowledge sources: Clinical Guidelines, Hospital Policies, Medication Database,
Laboratory Reference. They are illustrative starter content; real deployments
replace/append via the ingestion API from hospital-approved sources.
"""

from __future__ import annotations

DEFAULT_CORPORA: list[dict] = [
    {
        "key": "clinical_guidelines",
        "name": "Clinical Guidelines",
        "doc_type": "GUIDELINE",
        "description": "Evidence-based internal clinical practice guidelines.",
        "documents": [
            {
                "title": "Acute Myocardial Infarction Management Guideline",
                "doc_type": "GUIDELINE",
                "content": (
                    "Acute myocardial infarction (AMI) must be triaged as a high-priority emergency. "
                    "Initial assessment within 10 minutes of arrival: 12-lead ECG and troponin sampling. "
                    "Aspirin 300 mg chewed immediately unless contraindicated (documented allergy to aspirin). "
                    "If ST-elevation MI (STEMI): primary PCI is the preferred reperfusion strategy within 90 minutes "
                    "of first medical contact; if PCI unavailable within 120 minutes, fibrinolysis may be considered. "
                    "Continuous ECG monitoring, oxygen only if SpO2 < 90%, morphine for pain titrated to effect. "
                    "Admit to CCU/cardiology. All STEMI care decisions require clinician confirmation; "
                    "AI does not make the final diagnosis."
                ),
            },
            {
                "title": "Adult Sepsis Management Guideline",
                "doc_type": "GUIDELINE",
                "content": (
                    "Suspect sepsis when infection plus SIRS criteria coexist (temp <36 or >38.3C, HR >90, "
                    "RR >20 or PaCO2 <32, WBC <4 or >12). Measure lactate within first hour. "
                    "Administer 30 mL/kg crystalloid within 3 hours of identification in hypoperfusion or "
                    "lactate >= 4 mmol/L. Reassess after each fluid bolus for signs of fluid overload. "
                    "Start empiric broad-spectrum antibiotics within 1 hour of recognition, after blood cultures "
                    "where feasible. Escalate to critical care for vasopressor dependence. "
                    "Guideline-driven care never replaces clinical judgement."
                ),
            },
        ],
    },
    {
        "key": "hospital_policies",
        "name": "Hospital Policies",
        "doc_type": "POLICY",
        "description": "Internal hospital operational and safety policies.",
        "documents": [
            {
                "title": "Patient Identification Policy",
                "doc_type": "POLICY",
                "content": (
                    "Every patient interaction must begin with positive identification using two identifiers: "
                    "full name and date of birth (or a government-issued ID). Wristbands must be applied on "
                    "admission and checked before medication administration, blood sampling, and procedures. "
                    "Never use bed location or diagnosis as an identifier. Discrepancies must be reported to "
                    "registrar/nursing lead immediately."
                ),
            },
            {
                "title": "Medication Administration Safety Policy",
                "doc_type": "POLICY",
                "content": (
                    "Medication must be verified against the seven rights: right patient, right drug, "
                    "right dose, right route, right time, right indication, right documentation. "
                    "High-alert medications (insulin, opioids, anticoagulants) require a second independent "
                    "check prior to administration. Never administer a medication listed in the patient's "
                    "documented allergy profile without allergist/clinician review."
                ),
            },
            {
                "title": "Data Privacy and Access Policy",
                "doc_type": "POLICY",
                "content": (
                    "Patient data access follows need-to-know and minimum-necessary principles. "
                    "Access to the EHR is role-scoped; every access is audit-logged. AI systems may retrieve "
                    "only permission-approved knowledge and must never send patient data outside the hospital "
                    "network. Any request to 'show all records' without authorization must be refused."
                ),
            },
        ],
    },
    {
        "key": "medication_database",
        "name": "Medication Database",
        "doc_type": "MEDICATION",
        "description": "Local formulary and medication reference data.",
        "documents": [
            {
                "title": "Paracetamol (Acetaminophen) Formulary",
                "doc_type": "MEDICATION",
                "content": (
                    "Paracetamol is an analgesic/antipyretic. Adult oral dose 500-1000 mg every 4-6 hours, "
                    "maximum 4 g per day. IV route for adults 1 g every 6 hours, maximum 4 g/day. "
                    "Reduce dose in hepatic impairment. Overdose risk: hepatotoxicity above 4 g/day in adults; "
                    "seek immediate clinical review for suspected ingestion over the maximum. "
                    "Contraindicated in severe hepatic failure."
                ),
            },
            {
                "title": "Amoxicillin Formulary",
                "doc_type": "MEDICATION",
                "content": (
                    "Amoxicillin is a broad-spectrum penicillin antibiotic active against Gram-positive cocci "
                    "and some Gram-negative organisms. Adult oral dose 500 mg every 8 hours or 875 mg every "
                    "12 hours depending on infection. Adjust for renal impairment. "
                    "Contraindicated with documented penicillin allergy; use with caution in mononucleosis "
                    "(rash risk). Common adverse effects: diarrhoea, nausea, rash."
                ),
            },
        ],
    },
    {
        "key": "laboratory_reference",
        "name": "Laboratory Reference",
        "doc_type": "LAB_REFERENCE",
        "description": "Normal reference ranges for laboratory results.",
        "documents": [
            {
                "title": "Complete Blood Count Reference Ranges",
                "doc_type": "LAB_REFERENCE",
                "content": (
                    "Adult reference ranges (may vary by lab): Haemoglobin 13.5-17.5 g/dL (male), "
                    "12.0-15.5 g/dL (female). White blood cell count 4.0-11.0 x10^9/L. "
                    "Platelets 150-400 x10^9/L. Haematocrit 38.8-50.0% (male), 34.9-44.5% (female). "
                    "MCV 80-100 fL. Results outside the range alarm/flag the clinician for context review; "
                    "interpretation requires clinical correlation."
                ),
            },
            {
                "title": "Serum Electrolytes Reference Ranges",
                "doc_type": "LAB_REFERENCE",
                "content": (
                    "Serum sodium 135-145 mmol/L. Potassium 3.5-5.1 mmol/L. Chloride 97-107 mmol/L. "
                    "Bicarbonate 22-29 mmol/L. Creatinine 0.6-1.2 mg/dL (adult). eGFR >= 60 mL/min/1.73m2 "
                    "is generally normal. Potassium below 3.0 or above 6.0 mmol/L is a critical result "
                    "requiring immediate clinical review."
                ),
            },
        ],
    },
]