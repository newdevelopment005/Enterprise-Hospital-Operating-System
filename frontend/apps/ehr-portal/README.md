# ehr-portal

EHOS Clinical EHR portal (React + TypeScript + Vite). Talks to the ehr-service
REST API under `/api/v1/patients/{patient_id}/...`. Vite dev proxy forwards
`/api` to `http://localhost:8502`.

## Screens

- **Patient UUID** (top) opens the chart for any patient-service record.
- **Chart** — dashboard of section counts for the patient; click a tile to jump
  to that module.
- **Encounters** — open an encounter and copy its UUID (diagnoses need one).
- **Notes** — create SOAP (structured S/O/A/P), progress, discharge or generic
  typed notes; filter the list by note type.
- **Vitals** — single-reading entry in any vital type.
- **Diagnoses** — add (needs encounter UUID), resolve.
- **Medications** — prescribe, discontinue.
- **Orders** — LAB/IMAGING/… + priority, complete.
- **Allergies** — record by allergen/type/severity, resolve.
- **Problem List** — add / resolve problems.
- **Medical History** — past / surgical / family / social / … entries.
- **Timeline** — source-tagged clinical event feed.

## Development

```bash
npm install
npm run dev        # http://localhost:5174
npm run build      # tsc -b && vite build
```

> When the machine's global npm `shell` config is non-standard, run the steps
> directly: `node node_modules/typescript/bin/tsc -b && node node_modules/vite/bin/vite.js build`.