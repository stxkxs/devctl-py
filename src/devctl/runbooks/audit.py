"""Runbook execution audit logging."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from devctl.core.logging import get_logger
from devctl.runbooks.schema import RunbookResult

logger = get_logger(__name__)


class RunbookAuditLogger:
    """Log runbook executions for audit purposes."""

    def __init__(
        self,
        log_dir: str | Path | None = None,
        max_logs: int = 1000,
    ):
        """Initialize audit logger.

        Args:
            log_dir: Directory to store audit logs
            max_logs: Maximum number of logs to retain
        """
        if log_dir:
            self._log_dir = Path(log_dir)
            self._log_dir.mkdir(parents=True, exist_ok=True)
        else:
            self._log_dir = None

        self._max_logs = max_logs

    def log_execution(
        self,
        result: RunbookResult,
        user: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Log a runbook execution.

        Args:
            result: Runbook execution result
            user: User who ran the runbook
            metadata: Additional metadata

        Returns:
            Audit log ID
        """
        audit_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")

        audit_entry = {
            "audit_id": audit_id,
            "timestamp": datetime.utcnow().isoformat(),
            "user": user or "unknown",
            "runbook_name": result.runbook_name,
            "status": result.status.value,
            "dry_run": result.dry_run,
            "started_at": result.started_at.isoformat(),
            "ended_at": result.ended_at.isoformat() if result.ended_at else None,
            "duration_seconds": result.duration_seconds,
            "summary": {
                "total_steps": len(result.step_results),
                "successful": result.successful_steps,
                "failed": result.failed_steps,
                "skipped": result.skipped_steps,
            },
            "error": result.error,
            "metadata": metadata or {},
        }

        # Log to file if directory configured
        if self._log_dir:
            self._write_log(audit_id, audit_entry, result)

        # Also log via standard logger
        logger.info(
            "Runbook execution audit",
            audit_id=audit_id,
            runbook=result.runbook_name,
            status=result.status.value,
            user=user,
        )

        return audit_id

    def _write_log(
        self,
        audit_id: str,
        audit_entry: dict[str, Any],
        result: RunbookResult,
    ) -> None:
        """Write audit log to file."""
        # Write summary
        summary_file = self._log_dir / f"{audit_id}_summary.json"
        with open(summary_file, "w") as f:
            json.dump(audit_entry, f, indent=2)

        # Write full result
        detail_file = self._log_dir / f"{audit_id}_detail.json"
        with open(detail_file, "w") as f:
            json.dump(result.to_dict(), f, indent=2)

        # Cleanup old logs
        self._cleanup_old_logs()

    def _cleanup_old_logs(self) -> None:
        """Remove old audit logs beyond max_logs limit."""
        if not self._log_dir:
            return

        summary_files = sorted(self._log_dir.glob("*_summary.json"))

        if len(summary_files) > self._max_logs:
            for old_file in summary_files[: -self._max_logs]:
                old_file.unlink(missing_ok=True)
                # Also remove corresponding detail file
                detail_file = old_file.parent / old_file.name.replace("_summary", "_detail")
                detail_file.unlink(missing_ok=True)

    def get_history(
        self,
        runbook_name: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get execution history.

        Args:
            runbook_name: Filter by runbook name
            limit: Maximum entries to return
            offset: Skip first N entries

        Returns:
            List of audit entries
        """
        if not self._log_dir:
            return []

        entries: list[dict[str, Any]] = []
        summary_files = sorted(self._log_dir.glob("*_summary.json"), reverse=True)

        for summary_file in summary_files:
            try:
                with open(summary_file) as f:
                    entry = json.load(f)

                if runbook_name and entry.get("runbook_name") != runbook_name:
                    continue

                entries.append(entry)

            except Exception as e:
                logger.warning(f"Failed to read audit log {summary_file}: {e}")

        return entries[offset : offset + limit]

    def get_execution(self, audit_id: str) -> dict[str, Any] | None:
        """Get full execution details by audit ID.

        Args:
            audit_id: Audit log ID

        Returns:
            Full execution result or None
        """
        if not self._log_dir:
            return None

        detail_file = self._log_dir / f"{audit_id}_detail.json"

        if not detail_file.exists():
            return None

        try:
            with open(detail_file) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read audit log {detail_file}: {e}")
            return None

    def get_stats(self, days: int = 30) -> dict[str, Any]:
        """Get execution statistics.

        Args:
            days: Number of days to include

        Returns:
            Statistics summary
        """
        if not self._log_dir:
            return {}

        cutoff = datetime.utcnow().timestamp() - (days * 86400)
        stats = {
            "total_executions": 0,
            "successful": 0,
            "failed": 0,
            "dry_runs": 0,
            "runbooks": {},
        }

        for summary_file in self._log_dir.glob("*_summary.json"):
            try:
                with open(summary_file) as f:
                    entry = json.load(f)

                # Check if within time range
                ts = datetime.fromisoformat(entry["timestamp"]).timestamp()
                if ts < cutoff:
                    continue

                stats["total_executions"] += 1

                if entry.get("status") == "success":
                    stats["successful"] += 1
                elif entry.get("status") == "failed":
                    stats["failed"] += 1

                if entry.get("dry_run"):
                    stats["dry_runs"] += 1

                # Track per-runbook stats
                rb_name = entry.get("runbook_name", "unknown")
                if rb_name not in stats["runbooks"]:
                    stats["runbooks"][rb_name] = {"runs": 0, "failures": 0}

                stats["runbooks"][rb_name]["runs"] += 1
                if entry.get("status") == "failed":
                    stats["runbooks"][rb_name]["failures"] += 1

            except Exception:
                pass

        return stats
