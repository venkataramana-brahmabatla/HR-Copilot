# HR Copilot RBAC and Security Boundaries

All Copilot routes require an active authenticated employee. The backend resolves identity and role from the current database record; request text, chat history, and model output cannot set either value.

## Permission matrix

| Capability | Employee | Manager | Admin |
|---|---|---|---|
| Ask HR policy questions | Allowed | Allowed | Allowed |
| Read own leave balance and requests through Action Agent | Own records | Own records | Own records |
| Apply for own leave or create own ticket | Allowed | Allowed | Allowed, subject to existing leave workflow rules |
| Query HR analytics through Copilot SQL | Own leave tables only | Approved schema, employee-owned rows scoped to direct reports | Approved schema |
| Read salary, bank, tax, authentication, contact, address, birth-date, or document fields through Copilot SQL | Denied | Denied | Denied |
| View pending leave approvals | Denied | Direct reports only | All pending requests |
| Approve leave through Copilot | Denied | Direct reports only | Allowed |
| Reject leave through Copilot | Not available | Not available | Not available |
| Assign projects through Copilot | Not available | Not available | Not available |
| Destructive SQL | Denied | Denied | Denied |

Managers and admins use the existing leave review workflow. The workflow checks the role again at the endpoint. Manager review is scoped to direct reports; admins can review all requests. The Action Agent accepts only an explicit pending request ID for approval.

## Enforcement points

- `get_current_user` rejects missing, invalid, and inactive accounts. Role checks use the employee record loaded from the database.
- The SQL schema is allow-listed by role. SQL is parsed, limited to one `SELECT`, checked against approved tables and columns, scoped to the current employee or direct reports, and capped at 100 rows. The executor uses SQLite query-only mode.
- Action tools bind the authenticated employee and request database session on the server. The model cannot supply an employee ID. Leave approval is denied for employees before model execution and checked again by the existing endpoint for managers/admins.
- Leave application, ticket creation, and approval call existing HR endpoints so their validation and workflow rules remain in force. Leave rejection remains available through the existing manager/admin API, outside the Action Agent.
- Recent conversation and retrieved policy text are untrusted data. They cannot change the authenticated identity, role, tool allow-list, or SQL validation rules.
- Unknown roles fail closed in SQL authorization. The Action Agent exposes no destructive tools.

## Secrets and logs

Local `.env` files and `.env.*` variants are ignored; `.env.example` files contain placeholders only. Deployments outside development and test must provide a JWT secret of at least 32 characters. AI code does not log prompts, generated SQL, tool arguments, or model responses.

Do not commit real API keys or JWT secrets. Rotate any credential that has been committed or exposed.
