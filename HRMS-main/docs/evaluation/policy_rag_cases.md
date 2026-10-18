# Policy RAG Evaluation Cases

Run these questions as an authenticated user through `POST /api/v1/chat/policy`. A passing answer should use the stated fact, cite the expected policy source, and avoid adding unsupported details.

| Question | Expected answer point | Expected source |
| --- | --- | --- |
| What time should I clock in? | Before 9:30 AM on working days. | Attendance Policy |
| How soon must I report a security incident? | Report it to IT within 1 hour. | Incident Reporting |
| When should I submit a travel claim? | Within 15 days of returning. | Travel Reimbursement |
| How long is the probation period? | Six months unless explicitly waived. | Probation Policy |
| How can I raise a grievance? | Through the HR ticket workflow. | Grievance Policy |
| How many casual leave days do I get? | Say the available policies do not specify a number. | Leave Policy |
| What is the policy for employees working on Mars? | Say the available policies do not contain that information. | No source required |

The seeded Leave Policy says employees may use casual, sick, and earned leave according to their allocated balances; it does not state a numeric allocation. The assistant must not invent one.
