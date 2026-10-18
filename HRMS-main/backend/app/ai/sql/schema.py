from app.models.enums import EmployeeStatus, LeaveRequestStatus, LeaveType, ProjectStatus, Role


APPROVED_SCHEMA: dict[str, set[str]] = {
    "employees": {"id", "name", "department_id", "manager_id", "role", "status", "joining_date"},
    "departments": {"id", "name", "location"},
    "skills": {"id", "name", "normalized_name"},
    "employee_skills": {"id", "employee_id", "skill_id", "level"},
    "projects": {"id", "name", "description", "status"},
    "employee_projects": {"id", "employee_id", "project_id", "role_on_project"},
    "leave_balances": {"id", "employee_id", "leave_type", "total", "used", "remaining"},
    "leave_requests": {
        "id", "employee_id", "leave_type", "start_date", "end_date", "is_half_day", "half_day_period", "status",
    },
}

EMPLOYEE_TABLES = {"leave_balances", "leave_requests"}
EMPLOYEE_OWNED_TABLES = {
    "employees", "employee_skills", "employee_projects", "leave_balances", "leave_requests",
}
SUPPORTED_ROLES = {"EMPLOYEE", "MANAGER", "ADMIN"}


def role_name(role: object) -> str:
    return role.value if hasattr(role, "value") else str(role)


def schema_for_role(role: object) -> dict[str, set[str]]:
    name = role_name(role)
    if name not in SUPPORTED_ROLES:
        return {}
    if name == "EMPLOYEE":
        return {table: APPROVED_SCHEMA[table] for table in EMPLOYEE_TABLES}
    return APPROVED_SCHEMA


def describe_schema(role: object) -> str:
    schema = schema_for_role(role)
    lines = ["Approved SQLite tables and columns:"]
    for table, columns in schema.items():
        lines.append(f"- {table}({', '.join(sorted(columns))})")
    lines.extend([
        "Sensitive payroll, banking, tax, contact, address, birth-date, password, and document fields are not available.",
        "Return one SQLite SELECT statement only. Do not use SELECT *, CTEs, subqueries, or multiple statements.",
        "Qualify column names with their table name or alias when a query reads more than one table.",
        "Enum values are case-sensitive. Use these exact stored values when filtering enum columns:",
        f"employees.status: {', '.join(item.value for item in EmployeeStatus)}; "
        f"employees.role: {', '.join(item.value for item in Role)}; "
        f"projects.status: {', '.join(item.value for item in ProjectStatus)}; "
        f"leave_balances.leave_type and leave_requests.leave_type: {', '.join(item.value for item in LeaveType)}; "
        f"leave_requests.status: {', '.join(item.value for item in LeaveRequestStatus)}.",
    ])
    name = role_name(role)
    if name == "EMPLOYEE":
        lines.append("Employee access is limited to the signed-in employee's own leave_balances or leave_requests rows.")
    elif name == "MANAGER":
        lines.append("Employee-owned records are automatically limited to this manager's direct reports.")
    return "\n".join(lines)
