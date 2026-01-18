# tools/utility_tools.py
"""Utility tools (undo, redo, history, state, transactions)"""

from utils.logger import get_logger
from core.snapshot import SnapshotManager
from core.audit import AuditLogger
from models.tool_results import ToolResult
from livekit.agents import function_tool, RunContext

logger = get_logger(__name__)

_last_snapshot_id = None
_last_undone_snapshot_id = None
_active_transaction = None

@function_tool()
async def set_last_snapshot(context: RunContext, snapshot_id: str) -> dict:
    """Set the last snapshot ID"""
    global _last_snapshot_id
    _last_snapshot_id = snapshot_id

    return ToolResult(
        success=True,
        message="Last snapshot updated",
        data={"snapshot_id": snapshot_id}
    ).to_dict()


@function_tool()
async def undo_last_action_tool(context: RunContext) -> dict:
    """Undo the last file operation"""
    try:
        global _last_snapshot_id, _last_undone_snapshot_id

        if not _last_snapshot_id:
            return ToolResult(
                success=False,
                error="No recent action to undo"
            ).to_dict()

        snapshot_mgr = SnapshotManager()
        result = await snapshot_mgr.rollback(_last_snapshot_id)

        if result.get("success"):
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="undo",
                status="success",
                details={
                    "snapshot_id": _last_snapshot_id,
                    "restored": result.get("restored", 0)
                }
            )

            logger.info("undo_successful", snapshot_id=_last_snapshot_id)

            _last_undone_snapshot_id = _last_snapshot_id
            _last_snapshot_id = None

            return ToolResult(
                success=True,
                data={
                    "restored": result.get("restored", 0),
                    "files": result.get("files", [])
                },
                message="Undo completed successfully"
            ).to_dict()

        return ToolResult(
            success=False,
            error=result.get("error", "Undo failed")
        ).to_dict()

    except Exception as e:
        logger.error("undo_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def show_history_tool(context: RunContext, limit: int = 10) -> dict:
    """Show recent operations"""
    try:
        audit = AuditLogger()
        operations = await audit.get_recent_operations(limit)

        history = [
            {
                "time": op["timestamp"],
                "operation": op["operation_type"],
                "status": op["status"],
                "details": op.get("details", {})
            }
            for op in operations
        ]

        return ToolResult(
            success=True,
            data={"operations": history},
            message=f"Showing last {len(history)} operations"
        ).to_dict()

    except Exception as e:
        logger.error("history_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()

@function_tool()
async def redo_last_action_tool(context: RunContext) -> dict:
    """Redo the last undone action (if supported)"""
    global _last_undone_snapshot_id

    if not _last_undone_snapshot_id:
        return ToolResult(
            success=False,
            error="No action available to redo"
        ).to_dict()

    return ToolResult(
        success=False,
        error="Redo is not yet supported by SnapshotManager"
    ).to_dict()


@function_tool()
async def undo_to_snapshot_tool(
    context: RunContext,
    snapshot_id: str,
) -> dict:
    """Undo to a specific snapshot ID"""
    try:
        snapshot_mgr = SnapshotManager()
        result = await snapshot_mgr.rollback(snapshot_id)

        if result.get("success"):
            return ToolResult(
                success=True,
                data={
                    "snapshot_id": snapshot_id,
                    "restored": result.get("restored", 0)
                },
                message="Rollback to snapshot completed"
            ).to_dict()

        return ToolResult(
            success=False,
            error=result.get("error", "Rollback failed")
        ).to_dict()

    except Exception as e:
        logger.error("undo_to_snapshot_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def list_available_snapshots_tool(context: RunContext) -> dict:
    """List available snapshots (if supported)"""
    try:
        snapshot_mgr = SnapshotManager()

        if not hasattr(snapshot_mgr, "list_snapshots"):
            return ToolResult(
                success=False,
                error="Snapshot listing not supported"
            ).to_dict()

        snapshots = await snapshot_mgr.list_snapshots()

        return ToolResult(
            success=True,
            data={"snapshots": snapshots},
            message=f"Found {len(snapshots)} snapshots"
        ).to_dict()

    except Exception as e:
        logger.error("list_snapshots_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def begin_transaction_tool(context: RunContext, name: str) -> dict:
    """Begin a logical transaction for grouped actions"""
    global _active_transaction

    if _active_transaction:
        return ToolResult(
            success=False,
            error="A transaction is already active"
        ).to_dict()

    _active_transaction = name

    return ToolResult(
        success=True,
        message=f"Transaction '{name}' started"
    ).to_dict()


@function_tool()
async def end_transaction_tool(context: RunContext) -> dict:
    """End the active transaction"""
    global _active_transaction

    if not _active_transaction:
        return ToolResult(
            success=False,
            error="No active transaction"
        ).to_dict()

    name = _active_transaction
    _active_transaction = None

    return ToolResult(
        success=True,
        message=f"Transaction '{name}' ended"
    ).to_dict()


@function_tool()
async def utility_diagnostics_tool(context: RunContext) -> dict:
    """Inspect internal utility system state"""
    return ToolResult(
        success=True,
        data={
            "last_snapshot_id": _last_snapshot_id,
            "last_undone_snapshot_id": _last_undone_snapshot_id,
            "active_transaction": _active_transaction,
        },
        message="Utility diagnostics retrieved"
    ).to_dict()

@function_tool()
async def clear_undo_state_tool(context: RunContext) -> dict:
    """Clear undo / redo state"""
    global _last_snapshot_id, _last_undone_snapshot_id

    _last_snapshot_id = None
    _last_undone_snapshot_id = None

    return ToolResult(
        success=True,
        message="Undo and redo state cleared"
    ).to_dict()

@function_tool()
async def peek_last_action_tool(context: RunContext) -> dict:
    """Preview the last undoable action"""
    if not _last_snapshot_id:
        return ToolResult(
            success=False,
            error="No undoable action available"
        ).to_dict()

    return ToolResult(
        success=True,
        data={"snapshot_id": _last_snapshot_id},
        message="Undoable action is available"
    ).to_dict()


@function_tool()
async def system_state_tool(context: RunContext) -> dict:
    """Inspect internal utility state"""
    return ToolResult(
        success=True,
        data={
            "last_snapshot_id": _last_snapshot_id,
            "last_undone_snapshot_id": _last_undone_snapshot_id,
        },
        message="System state retrieved"
    ).to_dict()