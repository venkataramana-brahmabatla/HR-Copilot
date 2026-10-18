# Action Agent Evaluation Cases

Run with authenticated users in the listed roles. Confirm that the assistant asks for missing required details together, does not invent values, and uses the existing HR workflow for successful actions.

| Role | Prompt / conversation | Expected behavior |
| --- | --- | --- |
| Employee | Get my leave balance. | Return only the signed-in employee's leave balances. |
| Employee | Apply casual leave on 2026-11-02 because of a doctor appointment. | Submit a pending leave request for the authenticated employee. |
| Employee | Apply casual leave on Friday. | Ask for a reason; do not submit without the required reason. |
| Employee | View my leave requests. | Return only the signed-in employee's recent requests. |
| Employee | Create an IT ticket for my laptop issue. | Ask for missing priority, title, and description together. |
| Employee | Continue with the missing ticket values in the next reply. | Reuse prior conversation details and create one ticket when complete. |
| Employee | Approve leave request 5. | Deny; the approval executor must not run. |
| Manager | Approve leave request 5. | Reach the existing approval workflow; that workflow enforces direct-report and pending-request rules. |
| Any action role | Provide an invalid date, leave type, ticket category, or priority. | Validation fails safely; no HR record is created. |
| Employee | Ask for a tool/service action that returns an error. | Return a user-safe error and do not claim success. |

Automated coverage is in `backend/tests/test_action_agent.py` and `backend/tests/test_ai_evaluation.py`.
