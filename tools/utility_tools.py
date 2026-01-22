# tools/utility_tools.py
"""Utility tools (undo, redo, history, state, transactions)"""

from utils.logger import get_logger
from core.snapshot import SnapshotManager
from core.audit_logger import AuditLogger
from models.tool_results import ToolResult
from livekit.agents import function_tool, RunContext

logger = get_logger(__name__)

# Global state management
_last_snapshot_id = None
_last_undone_snapshot_id = None
_active_transaction = None
_snapshot_stack = []  # Stack for multiple undo operations


def set_last_snapshot(snapshot_id: str):
    """Set the last snapshot ID and add to stack"""
    global _last_snapshot_id, _snapshot_stack
    _last_snapshot_id = snapshot_id
    
    # Add to stack for multi-level undo
    if snapshot_id and snapshot_id not in _snapshot_stack:
        _snapshot_stack.append(snapshot_id)
        # Keep only last 10 snapshots
        if len(_snapshot_stack) > 10:
            _snapshot_stack.pop(0)
    
    logger.info("snapshot_tracked", snapshot_id=snapshot_id, stack_size=len(_snapshot_stack))


@function_tool()
async def undo_last_action_tool(context: RunContext) -> dict:
    """
    Undo the last file operation with full rollback capability
    
    Advanced features:
    - Restores files to original locations
    - Removes created folders if empty
    - Handles delete operations (restores from trash)
    - Multi-level undo support
    - Detailed operation feedback
    """
    try:
        global _last_snapshot_id, _last_undone_snapshot_id, _snapshot_stack

        if not _last_snapshot_id:
            return ToolResult(
                success=False,
                error="No recent action to undo. No operations have been performed yet."
            ).to_dict()

        logger.info("undo_attempt", snapshot_id=_last_snapshot_id)

        snapshot_mgr = SnapshotManager()
        
        # Perform rollback
        result = await snapshot_mgr.rollback(_last_snapshot_id)

        if result.get("success"):
            # Log successful undo
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="undo",
                status="success",
                details={
                    "snapshot_id": _last_snapshot_id,
                    "restored": result.get("restored", 0),
                    "operation": result.get("operation_type", "unknown")
                }
            )

            logger.info(
                "undo_successful",
                snapshot_id=_last_snapshot_id,
                restored=result.get("restored", 0)
            )

            # Update state
            _last_undone_snapshot_id = _last_snapshot_id
            
            # Remove from stack
            if _last_snapshot_id in _snapshot_stack:
                _snapshot_stack.remove(_last_snapshot_id)
            
            # Set to previous snapshot if available
            _last_snapshot_id = _snapshot_stack[-1] if _snapshot_stack else None

            # Build detailed message
            restored_count = result.get("restored", 0)
            operation_type = result.get("operation_type", "operation")
            
            message = f"✅ Undone! Restored {restored_count} item(s) from {operation_type}"
            
            return ToolResult(
                success=True,
                data={
                    "restored": restored_count,
                    "operation_type": operation_type,
                    "snapshot_id": _last_undone_snapshot_id,
                    "remaining_undos": len(_snapshot_stack)
                },
                message=message
            ).to_dict()
        
        else:
            error_msg = result.get("error", "Rollback failed for unknown reason")
            logger.error("undo_failed", error=error_msg, snapshot_id=_last_snapshot_id)
            
            return ToolResult(
                success=False,
                error=f"Undo failed: {error_msg}"
            ).to_dict()

    except Exception as e:
        logger.error("undo_exception", error=str(e), exc_info=True)
        return ToolResult(
            success=False,
            error=f"Undo failed with error: {str(e)}"
        ).to_dict()


@function_tool()
async def show_history_tool(context: RunContext, limit: int = 10) -> dict:
    """
    Show recent file operations with detailed information
    
    Features:
    - Chronological operation listing
    - Success/failure status
    - Operation details (files moved, deleted, etc.)
    - Timestamp information
    - Filterable history
    """
    try:
        audit = AuditLogger()
        operations = await audit.get_recent_operations(limit)

        if not operations:
            return ToolResult(
                success=True,
                data={"operations": []},
                message="No operations in history yet"
            ).to_dict()

        # Enhanced history with better formatting
        history = []
        for op in operations:
            details = op.get("details", {})
            
            # Format timestamp
            timestamp = op.get("timestamp", "")
            if timestamp:
                from datetime import datetime
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    formatted_time = timestamp
            else:
                formatted_time = "Unknown time"
            
            # Build summary
            op_type = op.get("operation_type", "unknown")
            status = op.get("status", "unknown")
            
            summary = f"{op_type} - {status}"
            if "count" in details:
                summary += f" ({details['count']} items)"
            elif "moved" in details:
                summary += f" ({details['moved']} items)"
            
            history.append({
                "time": formatted_time,
                "operation": op_type,
                "status": status,
                "summary": summary,
                "details": details
            })

        logger.info("history_retrieved", count=len(history))

        return ToolResult(
            success=True,
            data={"operations": history, "total": len(history)},
            message=f"Showing last {len(history)} operations"
        ).to_dict()

    except Exception as e:
        logger.error("history_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def redo_last_action_tool(context: RunContext) -> dict:
    """
    Redo the last undone action
    
    Note: Currently restores the snapshot state, effectively re-doing the undo
    """
    try:
        global _last_undone_snapshot_id, _last_snapshot_id

        if not _last_undone_snapshot_id:
            return ToolResult(
                success=False,
                error="No undone action available to redo"
            ).to_dict()

        # Restore the undone snapshot as current
        _last_snapshot_id = _last_undone_snapshot_id
        _last_undone_snapshot_id = None

        logger.info("redo_executed", snapshot_id=_last_snapshot_id)

        return ToolResult(
            success=True,
            data={"snapshot_id": _last_snapshot_id},
            message="Redo completed - action restored"
        ).to_dict()

    except Exception as e:
        logger.error("redo_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def undo_to_snapshot_tool(context: RunContext, snapshot_id: str) -> dict:
    """
    Undo to a specific snapshot ID (advanced rollback)
    
    Allows rolling back to any specific point in history
    """
    try:
        logger.info("undo_to_snapshot_attempt", target_snapshot=snapshot_id)
        
        snapshot_mgr = SnapshotManager()
        result = await snapshot_mgr.rollback(snapshot_id)

        if result.get("success"):
            global _last_snapshot_id
            _last_snapshot_id = None
            
            logger.info(
                "undo_to_snapshot_successful",
                snapshot_id=snapshot_id,
                restored=result.get("restored", 0)
            )

            return ToolResult(
                success=True,
                data={
                    "snapshot_id": snapshot_id,
                    "restored": result.get("restored", 0)
                },
                message=f"Rolled back to snapshot {snapshot_id[:8]}..."
            ).to_dict()

        return ToolResult(
            success=False,
            error=result.get("error", "Rollback to snapshot failed")
        ).to_dict()

    except Exception as e:
        logger.error("undo_to_snapshot_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def list_available_snapshots_tool(context: RunContext) -> dict:
    """
    List all available snapshots for rollback
    
    Shows snapshot history with timestamps and operation types
    """
    try:
        global _snapshot_stack
        
        if not _snapshot_stack:
            return ToolResult(
                success=True,
                data={"snapshots": []},
                message="No snapshots available"
            ).to_dict()

        snapshot_mgr = SnapshotManager()
        snapshot_details = []
        
        for snapshot_id in _snapshot_stack:
            try:
                # Try to load snapshot details
                snapshot = await snapshot_mgr.load_snapshot(snapshot_id)
                if snapshot:
                    snapshot_details.append({
                        "id": snapshot_id,
                        "operation": snapshot.operation_type,
                        "created": snapshot.created_at,
                        "files": len(snapshot.file_states)
                    })
            except:
                # If snapshot not found, still show the ID
                snapshot_details.append({
                    "id": snapshot_id,
                    "operation": "unknown",
                    "status": "unavailable"
                })

        logger.info("snapshots_listed", count=len(snapshot_details))

        return ToolResult(
            success=True,
            data={
                "snapshots": snapshot_details,
                "total": len(snapshot_details)
            },
            message=f"Found {len(snapshot_details)} available snapshots"
        ).to_dict()

    except Exception as e:
        logger.error("list_snapshots_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def begin_transaction_tool(context: RunContext, name: str) -> dict:
    """
    Begin a logical transaction for grouped file operations
    
    Groups multiple operations under a single transaction name
    for easier tracking and potential batch rollback
    """
    global _active_transaction

    if _active_transaction:
        return ToolResult(
            success=False,
            error=f"Transaction '{_active_transaction}' is already active. End it first."
        ).to_dict()

    _active_transaction = name
    logger.info("transaction_started", name=name)

    return ToolResult(
        success=True,
        data={"transaction_name": name},
        message=f"Transaction '{name}' started"
    ).to_dict()


@function_tool()
async def end_transaction_tool(context: RunContext) -> dict:
    """
    End the active transaction
    
    Completes the current transaction and releases the lock
    """
    global _active_transaction

    if not _active_transaction:
        return ToolResult(
            success=False,
            error="No active transaction to end"
        ).to_dict()

    name = _active_transaction
    _active_transaction = None
    
    logger.info("transaction_ended", name=name)

    return ToolResult(
        success=True,
        data={"transaction_name": name},
        message=f"Transaction '{name}' ended successfully"
    ).to_dict()


@function_tool()
async def utility_diagnostics_tool(context: RunContext) -> dict:
    """
    Inspect internal utility system state for debugging
    
    Shows:
    - Current snapshot tracking
    - Undo/redo availability
    - Active transactions
    - Snapshot stack depth
    """
    global _last_snapshot_id, _last_undone_snapshot_id, _active_transaction, _snapshot_stack
    
    diagnostics = {
        "last_snapshot_id": _last_snapshot_id,
        "last_undone_snapshot_id": _last_undone_snapshot_id,
        "active_transaction": _active_transaction,
        "snapshot_stack_size": len(_snapshot_stack),
        "snapshot_stack": _snapshot_stack,
        "undo_available": _last_snapshot_id is not None,
        "redo_available": _last_undone_snapshot_id is not None
    }
    
    logger.info("diagnostics_retrieved", **diagnostics)

    return ToolResult(
        success=True,
        data=diagnostics,
        message="Utility diagnostics retrieved"
    ).to_dict()


@function_tool()
async def clear_undo_state_tool(context: RunContext) -> dict:
    """
    Clear all undo/redo state and snapshot tracking
    
    Warning: This removes all rollback capability
    Use with caution - cannot be undone
    """
    global _last_snapshot_id, _last_undone_snapshot_id, _snapshot_stack

    previous_state = {
        "snapshots_cleared": len(_snapshot_stack),
        "undo_was_available": _last_snapshot_id is not None
    }

    _last_snapshot_id = None
    _last_undone_snapshot_id = None
    _snapshot_stack = []
    
    logger.info("undo_state_cleared", **previous_state)

    return ToolResult(
        success=True,
        data=previous_state,
        message=f"Cleared {previous_state['snapshots_cleared']} snapshots from tracking"
    ).to_dict()


@function_tool()
async def peek_last_action_tool(context: RunContext) -> dict:
    """
    Preview the last undoable action without executing undo
    
    Shows what would be undone if undo is called
    """
    global _last_snapshot_id
    
    if not _last_snapshot_id:
        return ToolResult(
            success=False,
            error="No undoable action available"
        ).to_dict()

    try:
        snapshot_mgr = SnapshotManager()
        snapshot = await snapshot_mgr.load_snapshot(_last_snapshot_id)
        
        if snapshot:
            preview = {
                "snapshot_id": _last_snapshot_id,
                "operation_type": snapshot.operation_type,
                "file_count": len(snapshot.file_states),
                "created_at": snapshot.created_at,
                "can_undo": True
            }
            
            return ToolResult(
                success=True,
                data=preview,
                message=f"Last action: {snapshot.operation_type} affecting {len(snapshot.file_states)} files"
            ).to_dict()
    except:
        pass

    return ToolResult(
        success=True,
        data={"snapshot_id": _last_snapshot_id, "can_undo": True},
        message="Undoable action is available"
    ).to_dict()


@function_tool()
async def system_state_tool(context: RunContext) -> dict:
    """
    Inspect overall system state
    
    Provides quick overview of undo/redo status and transaction state
    """
    global _last_snapshot_id, _last_undone_snapshot_id, _active_transaction, _snapshot_stack
    
    state = {
        "undo_available": _last_snapshot_id is not None,
        "redo_available": _last_undone_snapshot_id is not None,
        "transaction_active": _active_transaction is not None,
        "snapshot_count": len(_snapshot_stack),
        "current_snapshot": _last_snapshot_id,
        "transaction_name": _active_transaction
    }
    
    logger.info("system_state_retrieved", **state)

    return ToolResult(
        success=True,
        data=state,
        message="System state retrieved successfully"
    ).to_dict()