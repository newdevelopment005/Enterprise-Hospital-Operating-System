# patient-registration

EHOS frontend for the Patient Registration Service (patient-service). React +
TypeScript + Vite, talks to `patient-service` REST API under `/api/v1/patients`.

## Screens

- **Register** — demographics, National ID, emergency contact, addresses,
  insurance card, medical alerts, consents. Mirrors the backend DTO validation
  (no digits in names, real past DOB, NID format, phone/card patterns).
- **Search** — fuzzy lookup across name / MRN / patient number / National ID with
  pagination results.
- **Merge** — pick survivor and duplicate records from search results to run
  `/merge` (children re-homed, SAME_PERSON link created, duplicate soft-deleted).
- **Patient detail** — opens from search: demographics, emergency contact,
  add/resolve alerts, and the patient timeline.

## API

Typed client in `src/lib/client.ts` (envelope-aware: raises on
`success:false`), shared types in `src/lib/types.ts`, server-mirroring
validation in `src/lib/validation.ts`. Vite dev proxy forwards `/api` to
`http://localhost:8501` (patient-service).

## Development

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # tsc -b && vite build
npm run typecheck
```

> Note: typecheck/build are run via the local binaries when the machine's
> global npm `shell` config is non-standard:
> `node node_modules/typescript/bin/tsc -b && node node_modules/vite/bin/vite.js build`