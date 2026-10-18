# CB Nest HRMS and HR Copilot

CB Nest is a learning human resources management system with an AI copilot for HR policies, role-scoped HR analytics, and employee workflows. The app includes a Next.js web frontend, a FastAPI backend, and a SQLite database managed with Alembic migrations.

## Features

- Employee profiles, organization chart, attendance, leave balances and requests, payroll views, and employee documents.
- Projects, tickets, announcements, polls, team calendar, and a searchable HR policy library.
- Copilot policy answers with policy citations, guarded HR data questions, and supported leave and ticket actions.
- Role-based access for employees, managers, and admins, with AI request audit records for admins.

Copilot analytics use approved tables and columns, enforce role-based row scoping, and execute read-only SQL with a result limit. Copilot actions call existing backend workflows. Chat sessions are not stored on the server; recent conversation context is sent with each request.

## Run locally

### Requirements

- Docker Desktop or Docker Engine with Docker Compose v2.
- A Groq API key for live Copilot responses.

### Configure and start

From the repository root:

```sh
cd HRMS-main
cp backend/.env.example backend/.env
```

Edit `backend/.env` and set:

- `JWT_SECRET_KEY` to a unique random value of at least 32 characters. Generate one with `openssl rand -hex 32`.
- `GROQ_API_KEY` to your Groq API key.
- `SEED_PASSWORD` to a unique value of at least 16 characters if you plan to create a fresh demo database.

Then start the API and frontend:

```sh
./scripts/run-dev.sh
```

The launcher builds the containers, applies pending database migrations, and runs both services. It does not seed or reset the database. Press `Ctrl+C` to stop the services.

Open the app at <http://localhost:3000>. The FastAPI interactive docs are at <http://localhost:8000/docs>, and the health endpoint is <http://localhost:8000/api/v1/health>.

To seed a new, disposable development database, set `SEED_PASSWORD` first and run this from `HRMS-main` while the API is running:

```sh
docker compose exec api python scripts/seed.py
```

**Seeding deletes and recreates sample HR records. Do not run it against data you need to keep.** Changing `SEED_PASSWORD` does not update passwords in an existing database. Seeded demo accounts include `admin@mock-hrms.dev`, `manager@mock-hrms.dev`, and `employee@mock-hrms.dev`.

## Project layout

```text
.
├── HRMS-main/
│   ├── backend/       # FastAPI app, Alembic migrations, tests, and local storage
│   ├── frontend/      # Next.js app
│   ├── docs/          # Product, API, security, evaluation, and demo docs
│   ├── docker-compose.yml
│   └── scripts/run-dev.sh
└── docs/              # Assignment implementation plan
```

The detailed application README is in [`HRMS-main/README.md`](HRMS-main/README.md).

## Copilot API

All API routes are prefixed with `/api/v1`.

| Route | Purpose |
| --- | --- |
| `POST /auth/login` | Authenticate and issue tokens |
| `POST /chat/policy` | Ask an HR policy question |
| `POST /chat/sql` | Ask a guarded HR data question |
| `POST /chat/action` | Request a supported HR action |
| `POST /chat/router` | Route a question to the policy, SQL, or action agent |
| `GET /chat/audit` | View AI audit records (admin only) |
| `GET /health` | Check API and database health |

The `/chat/sessions` endpoints are currently contract stubs and return `501`.

## Roles and data access

| Capability | Employee | Manager | Admin |
| --- | :---: | :---: | :---: |
| Ask policy questions | Yes | Yes | Yes |
| Query HR analytics | Own leave data | Approved schema; team rows scoped to direct reports | Approved schema; sensitive fields excluded |
| Check own leave balance, view requests, submit leave, create ticket | Yes | Yes | Yes |
| Approve leave | No | Direct reports only | Yes |
| View AI audit logs | No | No | Yes |

The backend enforces authorization; frontend visibility is not used as an access control.

## Development checks

Run backend tests from `HRMS-main/backend` with the project dependencies installed:

```sh
python -m unittest discover -s tests -v
```

Build the frontend from `HRMS-main/frontend`:

```sh
npm ci
npm run build
```

## Security and local demo notes

- Keep `backend/.env` private. It is ignored by Git; `.env.example` files contain configuration names and placeholders only.
- The provided Docker Compose ports bind to localhost. The reload server, SQLite database, and browser token storage are intended for local development and demos, not public production deployment.
- Avoid entering real employee information into an external model provider during a demo.
- Review the [security assessment](HRMS-main/docs/security/project_review.md) before deployment beyond localhost.

## Documentation

- [Application README](HRMS-main/README.md)
- [Learner guide](HRMS-main/docs/Learner_Guide.md)
- [Product requirements](HRMS-main/docs/PRD.md)
- [Database table reference](HRMS-main/docs/db_tables_samples.md)
- [API examples](HRMS-main/docs/api/)
- [AI evaluation report and cases](HRMS-main/docs/evaluation/)
- [Security review](HRMS-main/docs/security/project_review.md)
- [Demo runbook](HRMS-main/docs/demo_runbook.md)
- [Assignment implementation plan](docs/assignment5_hr_copilot_implementation_plan.md)
