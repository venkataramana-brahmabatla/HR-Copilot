from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.leaves import approve_leave_request, my_leave_balances, my_leave_requests, submit_leave_request
from app.api.v1.endpoints.tickets import create_ticket as create_ticket_endpoint
from app.models.employee import Employee
from app.models.enums import Role
from app.schemas.leave import LeaveRequestCreate
from app.schemas.ticket import TicketCreate


async def get_leave_balance(arguments: dict, current_user: Employee, db: AsyncSession) -> dict:
    _ = arguments
    return await my_leave_balances(current_user=current_user, db=db)


async def get_my_leave_requests(arguments: dict, current_user: Employee, db: AsyncSession) -> dict:
    _ = arguments
    return await my_leave_requests(limit=20, offset=0, current_user=current_user, db=db)


async def apply_leave(arguments: dict, current_user: Employee, db: AsyncSession) -> dict:
    payload = LeaveRequestCreate.model_validate(arguments)
    return await submit_leave_request(payload=payload, current_user=current_user, db=db)


async def create_ticket(arguments: dict, current_user: Employee, db: AsyncSession) -> dict:
    payload = TicketCreate.model_validate(arguments)
    return await create_ticket_endpoint(payload=payload, current_user=current_user, db=db)


async def approve_leave(arguments: dict, current_user: Employee, db: AsyncSession) -> dict:
    if current_user.role not in {Role.MANAGER, Role.ADMIN}:
        raise HTTPException(status_code=403, detail="Only managers and admins can approve leave requests")
    return await approve_leave_request(
        request_id=arguments["request_id"],
        current_user=current_user,
        db=db,
    )


def unwrap_tool_result(result: dict) -> dict:
    """Unwrap the existing API response and reject unexpected handler output."""
    if result.get("success") is not True or not isinstance(result.get("data"), (dict, list)):
        raise HTTPException(status_code=500, detail="The HR workflow returned an invalid result")
    return result["data"]
