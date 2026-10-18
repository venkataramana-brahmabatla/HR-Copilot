from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from app.ai.sql.schema import EMPLOYEE_OWNED_TABLES, EMPLOYEE_TABLES, SUPPORTED_ROLES, role_name, schema_for_role


MAX_RESULT_ROWS = 100
_ALLOWED_FUNCTIONS = {
    "ABS", "AND", "AVG", "BETWEEN", "CAST", "COALESCE", "COUNT", "DATE", "DATETIME", "IFNULL",
    "IN", "IS", "JULIANDAY", "LENGTH", "LIKE", "LOWER", "MAX", "MIN", "NOT", "OR", "ROUND",
    "STRFTIME", "SUBSTR", "SUM", "TIME_TO_STR", "TS_OR_DS_TO_TIMESTAMP", "UPPER",
}


class SQLValidationError(ValueError):
    """Raised when generated SQL does not satisfy the read-only policy."""

    def __init__(self, message: str, *, generated_sql: str | None = None):
        super().__init__(message)
        self.generated_sql = generated_sql


@dataclass(frozen=True)
class ValidatedQuery:
    sql: str
    parameters: dict[str, int]


def validate_and_scope_sql(sql: str, role: str, employee_id: int) -> ValidatedQuery:
    """Parse, constrain, row-scope, and cap one model-generated SELECT."""
    current_role = role_name(role)
    if current_role not in SUPPORTED_ROLES:
        raise SQLValidationError("The authenticated role is not allowed to query HR data")

    try:
        statements = sqlglot.parse(sql, read="sqlite")
    except sqlglot.errors.ParseError as exc:
        raise SQLValidationError("The generated query is not valid SQLite SQL") from exc

    statements = [statement for statement in statements if statement is not None]
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise SQLValidationError("Only one read-only SELECT statement is allowed")

    query = statements[0]
    if query.args.get("with") or query.args.get("into") or query.args.get("offset"):
        raise SQLValidationError("CTEs, SELECT INTO, and OFFSET are not allowed")
    if any(True for _ in query.find_all(exp.Subquery)) or sum(1 for _ in query.find_all(exp.Select)) != 1:
        raise SQLValidationError("Subqueries are not allowed")
    for star in query.find_all(exp.Star):
        if not isinstance(star.parent, exp.Count):
            raise SQLValidationError("Wildcard selections are not allowed; name approved columns explicitly")

    schema = schema_for_role(role)
    tables = list(query.find_all(exp.Table))
    if not tables:
        raise SQLValidationError("Queries must read from an approved HR table")

    alias_to_table: dict[str, str] = {}
    for table in tables:
        name = table.name.lower()
        if name not in schema or table.db or table.catalog or not isinstance(table.this, exp.Identifier):
            raise SQLValidationError("The query references a table outside the approved HR schema")
        alias_to_table[table.alias_or_name.lower()] = name

    for column in query.find_all(exp.Column):
        if column.is_star:
            raise SQLValidationError("Wildcard selections are not allowed")
        if column.table:
            table_name = alias_to_table.get(column.table.lower())
            if table_name is None:
                raise SQLValidationError("Column qualifier does not match an approved table")
        else:
            candidates = [table for table in set(alias_to_table.values()) if column.name.lower() in schema[table]]
            if len(candidates) != 1:
                raise SQLValidationError("Every selected or filtered column must be unambiguous and approved")
            table_name = candidates[0]
        if column.name.lower() not in schema[table_name]:
            raise SQLValidationError("The query references a sensitive or unapproved column")

    for function in query.find_all(exp.Func):
        if function.sql_name().upper() not in _ALLOWED_FUNCTIONS:
            raise SQLValidationError("The query contains a function outside the approved read-only set")

    if current_role == "EMPLOYEE":
        if len(tables) != 1 or alias_to_table[next(iter(alias_to_table))] not in EMPLOYEE_TABLES:
            raise SQLValidationError("Employees may query only their own leave data")
        table = tables[0]
        _add_predicate(query, _column_for(table, "employee_id").eq(exp.Placeholder(this="current_employee_id")))
        parameters = {"current_employee_id": employee_id}
    elif current_role == "MANAGER":
        parameters = {"current_employee_id": employee_id}
        seen: set[tuple[str, str]] = set()
        for table in tables:
            table_name = table.name.lower()
            if table_name not in EMPLOYEE_OWNED_TABLES:
                continue
            alias = table.alias_or_name
            key = (table_name, alias.lower())
            if key in seen:
                continue
            seen.add(key)
            if table_name == "employees":
                predicate = _column_for(table, "manager_id").eq(exp.Placeholder(this="current_employee_id"))
            else:
                team_ids = (
                    exp.select(exp.column("id"))
                    .from_("employees")
                    .where(exp.column("manager_id").eq(exp.Placeholder(this="current_employee_id")))
                )
                predicate = _column_for(table, "employee_id").isin(team_ids)
            _add_predicate(query, predicate)
    else:
        parameters = {}

    limit = query.args.get("limit")
    if limit is None:
        query.set("limit", exp.Limit(expression=exp.Literal.number(MAX_RESULT_ROWS)))
    else:
        limit_value = limit.expression
        if not isinstance(limit_value, exp.Literal) or not limit_value.is_number:
            raise SQLValidationError("LIMIT must be a numeric constant")
        query.set("limit", exp.Limit(expression=exp.Literal.number(min(int(limit_value.this), MAX_RESULT_ROWS))))

    return ValidatedQuery(sql=query.sql(dialect="sqlite"), parameters=parameters)


def _column_for(table: exp.Table, name: str) -> exp.Column:
    qualifier = table.alias or exp.to_identifier(table.name)
    return exp.column(name, table=qualifier)


def _add_predicate(query: exp.Select, predicate: exp.Expression) -> None:
    where = query.args.get("where")
    if where is None:
        query.set("where", exp.Where(this=predicate))
    else:
        query.set("where", exp.Where(this=exp.and_(where.this, predicate)))
