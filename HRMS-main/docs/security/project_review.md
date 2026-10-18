# Security and Requirements Review

**Review date:** 2026-10-17
**Scope:** source review of the FastAPI, Next.js, AI agents, seed/deployment configuration, assignment plan, PRD, and current dependency manifests. This is a code and dependency review, not a penetration test or production certification.

## Requirements status

The Assignment 5 plan marks Phases 1–10 complete. The repository contains the corresponding HR foundation, policy retrieval, SQL agent, action agent, router, RBAC guards, Copilot UI, audit log, and offline evaluation tests. This review completed the documentation and demo-preparation work in Phases 11–12; the checklist is updated in [`assignment5_hr_copilot_implementation_plan.md`](../../../docs/assignment5_hr_copilot_implementation_plan.md).

| Requirement | Current implementation | Status / gap |
|---|---|---|
| One chat surface routes policy/data/actions | `/copilot` calls authenticated `POST /api/v1/chat/router` | Implemented |
| Policy answers use company policy and cite sources | Local chunking + TF-IDF retrieval; no hosted vector DB | Implemented; verify live answer/source before external presentation |
| Safe HR analytics | SQLGlot validation, approved schemas, per-role scoping, SQLite query-only mode, result cap | Implemented and offline-tested |
| HR actions reuse application workflows | LangChain tools call existing leave/ticket handlers and enforce user identity/role | Implemented and offline-tested |
| Conversation context | Browser sends at most eight recent messages | Bounded client context; no server-side session persistence |
| Chat session endpoints | `/chat/sessions` routes return `501` | Stub; disclose as not implemented |
| Auditability | AI request/result metadata stored in `ai_audit_logs`; listing is admin-only | Implemented; retention and completeness policy remain undefined |
| Evaluation | Offline deterministic tests and case sheets | Automated coverage passes; live provider quality is not recorded |
| Skills management | Schema and sample data only | `HRMS-015` APIs/UI remain planned |
| Product decisions | Notification policy, admin-upload deletion, and CI threshold remain open in the PRD | Product/engineering decisions still needed |

The earlier PRD described AI integration as planned. It now describes the delivered Assignment 5 scope and explicitly excludes payroll explanation, leave-compliance reasoning, persistent chat sessions, and live quality evaluation.

## Remediations present in the repository

- Production configuration rejects a missing, default, or short JWT secret. Local development generates a random key when one is not configured; the local ignored `.env` was rotated during remediation.
- Access and refresh tokens have distinct types, and the API accepts access tokens only. Inactive employees are rejected.
- Non-admin employee detail responses omit salary, banking, tax, and personal fields.
- Upload routes use bounded chunk reads, and `pypdf` is pinned to 6.19.0.
- Seed creation requires a configured `SEED_PASSWORD` and is disabled outside development/test. Seeded accounts share that configured value.
- Compose ports bind to `127.0.0.1`.
- Frontend dependencies are lockfile-backed, with `npm ci` used in the container build. The backend image now uses Python 3.12 to match the project requirement and installs the generated, hash-verified Python 3.12 lockfile.
- The vulnerable `python-jose` package was removed in favor of PyJWT; FastAPI, Starlette, and `python-multipart` were upgraded after the dependency scan.

## Remaining security risks

| Priority | Finding | Evidence and next step |
|---|---|---|
| High before public deployment | Browser access token is stored in `localStorage`; a successful same-origin script injection could read it. `hrms_auth` is a JavaScript-set marker cookie, not an HttpOnly credential. | `frontend/app/login/page.tsx`, `frontend/lib/api.ts`. Move authentication behind an HttpOnly, Secure, SameSite cookie/BFF design and add CSP before production. Backend authorization remains authoritative today. |
| High before public deployment | Login, AI-provider, and upload endpoints have no application-level rate limits. | Add rate limits at an API gateway or shared backend store; include request-body and upload limits at the edge. This protects credentials, provider spend, CPU, and disk. |
| High for real HR data | SQLite and uploaded records are not encrypted at rest by this app; Compose mounts the database and files directly. | Use managed encrypted storage/database, backups, access controls, and a production secret manager. Treat current seeded content as synthetic only. |
| Medium | Audit redaction is heuristic. It removes common emails, phone-like strings, and selected free-text fields, but cannot guarantee names or all personal data are removed. There is no retention/expiry policy. | Minimize what is stored, define retention/access/deletion rules, and review audit content against applicable privacy requirements. |
| Medium | Copilot prompts and retrieved policy excerpts are sent to the configured external Groq-compatible provider. | Confirm provider data-processing terms and avoid entering real employee data unless approved. |
| Medium | `docker-compose.yml` and Dockerfiles run development servers/reload mode; CORS allows localhost origins only. There is no production TLS or deployment configuration here. | Keep this setup local. A real deployment needs TLS termination, trusted hosts, environment-specific CORS, production server settings, and hardened storage. |
| Medium | Full npm audit reports seven advisories in the Tailwind 3 development/build chain (`braces`, `chokidar`, `fast-glob`, `micromatch`, `tailwindcss`, `postcss-nested`, and `postcss-selector-parser`). Production-only npm audit reports zero. | npm's suggested Tailwind 4 fix is a major CSS migration; the braces advisory has no patched release. Plan a tested Tailwind migration and continue dependency monitoring. Advisories: [braces](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm), [selector parser](https://github.com/advisories/GHSA-rj75-hqrm-r3gf). |
| Low / operational | The existing local database still accepts its legacy shared demo password; `SEED_PASSWORD` is empty and changing it does not rotate existing users. Re-seeding deletes and recreates HR data. | Keep the existing credential local to this synthetic demo; do not publish it or use it with real HR data. |

## Dependency review

On 2026-10-17, `pip-audit` found critical `python-jose` exposure and vulnerable Starlette/multipart versions in the installed app environment. `python-jose` had no patched version in the advisory; the app uses HS256 explicitly, but the dependency was still removed. It was replaced with PyJWT 2.15.1; FastAPI is pinned to 0.143.3, Starlette 1.8.0, and `python-multipart` 0.0.32. The subsequent installed-environment scan and hash-checked requirements-lock scan reported no known Python vulnerabilities.

The `python-jose` advisory describes a critical asymmetric-key/HMAC confusion issue and lists versions through 3.5.0 as affected ([GitHub Advisory](https://github.com/advisories/GHSA-3qf3-8w2g-rqmx)). The multipart parser's unbounded-header DoS was fixed upstream ([GitHub Advisory](https://github.com/advisories/GHSA-pp6c-gr5w-3c5g)); Starlette's security advisories are tracked by the maintainers ([Starlette advisories](https://github.com/Kludex/starlette/security/advisories)).

Frontend scan results: `npm audit --omit=dev` reports zero vulnerabilities; full `npm audit` reports seven development/build-chain findings described above. Continue scanning because advisory databases and package releases change.

## Verification evidence

- Backend: 38 offline unit tests pass, including role scoping, action permission, follow-up routing, JWT type/configuration, employee detail privacy, upload limits, audit redaction, and case-sensitive enum guidance for SQL generation.
- Frontend: `npm run build` succeeds with the locked dependency tree.
- Local health/login smoke checks were successful before the final framework dependency upgrade; restart/rebuild the API before the next live demo.
- Live-provider smoke cases now cover policy citation, SQL aggregate execution, leave-balance lookup, employee approval denial, and destructive-SQL rejection against the populated synthetic database. Full Docker/browser rehearsal remains for the presentation machine. See [the demo runbook](../demo_runbook.md) and [evaluation report](../evaluation/report.md).

## Deployment decision

The project is suitable for a localhost learning/demo environment with synthetic data. It is **not ready for deployment with real employee records or public exposure** until the browser-token design, rate limiting, data-at-rest controls, production server/TLS configuration, and remaining dependency advisories are addressed.
