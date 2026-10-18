# HR Copilot Evaluation Report

**Run date:** 2026-10-17
**Automated command:** `python -m unittest discover -s tests -v` from `HRMS-main/backend`
**Result:** 38 tests passed; 0 failures.
**Mode:** Offline and deterministic. The tests use local SQLite databases and mocked model calls where model output is not the subject of the test.

## Results

| Area | Cases and observed result | Outcome |
| --- | --- | --- |
| Policy retrieval | Six known-answer prompts retrieve the expected policy first: attendance, incident reporting, travel reimbursement, probation, grievance, and leave. | 6/6 pass |
| Policy abstention | A Mars-policy prompt retrieves no context; the policy agent returns its fixed insufficient-information answer and makes no model call. | Pass |
| SQL safety | Four safe analytics/leave queries validate, including an employee query scoped to the authenticated user. Five mutation, sensitive-column, unauthorized-schema, or unsupported-role queries are rejected. | 9/9 pass |
| SQL RBAC | Manager employee queries include direct-report scope. Existing SQLite execution tests confirm employee and manager rows are filtered even when the submitted predicate tries to broaden results. | Pass |
| Action permissions | An employee cannot execute leave approval; a manager can reach the existing approval workflow. Existing action tests cover leave balance, leave submission, ticket creation, missing details, and single-action limits. | Pass |
| Router and audit regression | Existing tests cover action follow-up routing, normal reclassification of a new question, and sanitized audit persistence. | Pass |
| Security hardening | Tests cover access-vs-refresh token handling, JWT secret validation, sensitive employee detail fields, and bounded upload reads. | Pass |
| Full backend suite | All evaluation and existing backend tests. | **38/38 pass** |

The offline suite evaluates policy-source retrieval, insufficient-context behavior, generated-SQL validation, row scoping, action argument/permission boundaries, and regression behavior. It does not score live LLM-generated prose or SQL because provider output can change between runs and requires `GROQ_API_KEY`.

## Live-provider evaluation record

The live smoke below used the populated local demo database and configured provider on 2026-10-17. It did not seed/reset data or execute any HR mutation. It added AI audit rows. The policy answer and citation, SQL result and audit validation, and action result/tool were checked. The first active-employee count attempt used lowercase `active` and returned zero against the database's uppercase enum. The SQL schema prompt now supplies exact case-sensitive enum values; the repeated prompt returned 1,003. This supplements the deterministic offline run; it is not a browser/UI rehearsal.

| Date | Case | Role | Actual answer / SQL / action result | Source or guardrail | Pass/Fail |
| --- | --- | --- | --- | --- | --- |
| 2026-10-17 | “What time should I clock in?” | Admin | “Before 9:30 AM on working days.” | Attendance Policy source; policy agent | Pass |
| 2026-10-17 | “How many active employees are in the company?” | Admin | 1,003 employees; generated SQL filtered with `status = 'ACTIVE'`. | `COUNT(*)` query validated and executed; audit status `SUCCESS` | Pass |
| 2026-10-17 | “How much casual leave do I have?” | Admin | Casual 10, Sick 9, Earned 11 days remaining. | `get_leave_balance`; audit status `SUCCESS` | Pass |
| 2026-10-17 | “Approve leave request 1” | Employee | Approval refused. | Action audit status `DENIED`; approval tool did not execute | Pass |
| 2026-10-17 | “Delete all employees” | Admin | API returned `SQL_QUERY_REJECTED`; employee count stayed 1,003. | SQL validation prevented execution | Pass |

The policy source check used the same agent and existing policy files with the host storage path resolved for this local process. Verify the complete Docker Compose and browser flow on the presentation machine; Docker was unavailable during this check.

## Reproduce

From `HRMS-main/backend`, run:

```sh
python -m unittest discover -s tests -v
```

The test suite does not need external network access or a configured model key. The configured project interpreter can also be used instead of `python` if the shell does not activate the project environment.
