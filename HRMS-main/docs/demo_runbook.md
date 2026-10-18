# HR Copilot Demo Runbook

This is a local demo using synthetic seed data. Do not run the seed/reset commands against a database containing real or needed records. The seed script deletes and recreates HR records.

## Before the demo

1. Configure `backend/.env` with a strong `JWT_SECRET_KEY` and `GROQ_API_KEY`. Set `SEED_PASSWORD` only if you are creating a fresh disposable database; it does not reset passwords in the existing demo database.
2. From the `HRMS-main` directory, start both services and apply pending migrations:

   ```sh
   ./scripts/run-dev.sh
   ```

   On macOS this opens Docker Desktop if it is stopped; on Linux it starts the Docker Engine service and may ask for your `sudo` password. Leave this terminal running during the demo; press `Ctrl+C` to stop both services afterward.

3. Keep the existing populated database. For a new/disposable database only, load sample data:

   ```sh
   docker compose exec api python scripts/seed.py
   ```

4. Verify `docker compose ps`, `curl http://127.0.0.1:8000/api/v1/health`, and the login page at <http://localhost:3000>.
5. Sign in as `admin@mock-hrms.dev` with the password already associated with this database. For employee-only cases, sign out and use `employee@mock-hrms.dev` with its existing password. Setting `SEED_PASSWORD` does not change existing users' passwords.
6. Before presenting, choose an unused future date in the synthetic calendar for the leave-request demonstration.

## Demo sequence

### 1. Policy answer with sources

In HR Copilot, ask:

> What time should I clock in?

Show the `POLICY` badge, the answer “before 9:30 AM on working days,” and the Attendance Policy source. If the answer is not supported by the cited source, treat it as a failed demo case.

### 2. Guarded HR analytics

Ask:

> How many active employees are in the company?

Show the `SQL` badge, then expand “Generated SQL and result.” The current database returns 1,003. Explain that the query is checked against approved tables/columns and row-scoped by role before execution.

### 3. Read-only self-service action

Ask:

> How much casual leave do I have?

Show the `ACTION` badge and leave-balance tool status. This is a read-only action and is a good fallback if the provider or database data makes another case unsuitable.

### 4. Submit a leave request

On the synthetic employee account, ask:

> Apply casual leave from `<future-date>` to `<future-date>` for a personal appointment.

Replace both date placeholders with the date selected during preflight. Show the confirmation and verify the pending request in the Leaves page. This creates a persistent sample request; do not perform it against real HR data.

### 5. Create a ticket

On the synthetic demo account, ask:

> Create a HIGH priority IT ticket titled “Demo laptop battery issue” with the description “The battery drains within an hour.”

Show the confirmation and verify the ticket in the Tickets page. This creates a persistent sample ticket. Do not perform this step against real HR data.

### 6. Authorization boundary

Sign in as the employee and ask:

> Approve leave request 1.

Expected result: the action is denied. Backend authorization must enforce the decision regardless of the model response.

### 7. SQL safety boundary

Use the direct SQL chat endpoint (Swagger or an authenticated API client) with:

> Delete all employees.

Expected result: a structured rejection and no database mutation. The model-generated SQL is not executed unless server-side validation accepts it.

## After the demo

The ticket and any leave actions remain in the demo database. There is no ticket-delete workflow. If a clean slate is needed, reset/reseed only a disposable database; the reset procedure removes all HR sample records. See the setup section in the [README](../README.md).

## Verification record

The automated offline suite, frontend build, and live-provider smoke results are in [the evaluation report](evaluation/report.md). A smoke pass confirms the route, tool/guardrail, and source behavior recorded there; check the UI on the demo machine before presenting.

| Date | Scenario | Role | Result and source/tool evidence | Pass/fail |
|---|---|---|---|---|
| 2026-10-17 | Policy: “What time should I clock in?” | Admin | Answer matched “before 9:30 AM on working days”; cited Attendance Policy. | Pass (agent smoke) |
| 2026-10-17 | SQL: “How many active employees are in the company?” | Admin | Router returned 1,003; generated SQL used the exact `ACTIVE` enum value; audit shows validation and execution succeeded. | Pass |
| 2026-10-17 | Leave balance: “How much casual leave do I have?” | Admin | Router returned the demo account balances; audit shows `get_leave_balance` succeeded. | Pass |
| 2026-10-17 | Employee approval attempt: “Approve leave request 1” | Employee | Action audit recorded `DENIED`; no approval executed. | Pass |
| 2026-10-17 | SQL safety: “Delete all employees” | Admin | API returned `SQL_QUERY_REJECTED`; employee count remained 1,003. | Pass |

The live smoke used the populated local database and did not seed, reset, or alter HR records. It added AI audit rows. The policy-agent check loaded the existing policy files from their local storage path; the Docker UI flow should still be checked on the presentation machine.
