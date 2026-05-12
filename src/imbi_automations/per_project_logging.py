"""Per-project log capture for debugging concurrent workflow executions."""

import contextvars
import logging
import logging.handlers
import pathlib
import threading

# Context variable to track current project being executed
current_project_id: contextvars.ContextVar = contextvars.ContextVar(
    'current_project_id', default=None
)

# Global state for managing root logger level across concurrent captures
_capture_lock = threading.Lock()
_active_captures = 0
_original_root_level: int | None = None


class ProjectLogFilter(logging.Filter):
    """Filter that only allows logs from a specific project context.

    Uses contextvars to check if the log record was generated within
    the async context of the target project.
    """

    def __init__(self, project_id: str) -> None:
        """Initialize filter for specific project ID.

        Args:
            project_id: Project ID to filter for

        """
        super().__init__()
        self.project_id = project_id

    def filter(self, record: logging.LogRecord) -> bool:
        """Check if record belongs to this project's context.

        Args:
            record: Log record to evaluate

        Returns:
            True if record should be logged, False otherwise

        """
        ctx_value = current_project_id.get()
        result = ctx_value == self.project_id
        return result


class ProjectLogCapture:
    """Captures all DEBUG logs for a single project execution.

    Uses MemoryHandler to buffer logs in memory during execution,
    then writes to file only on error. Works with concurrent execution
    by using contextvars to isolate logs per async task.
    """

    def __init__(self, project_id: str, buffer_size: int = 10000) -> None:
        """Initialize log capture for specific project.

        Args:
            project_id: Project ID to capture logs for
            buffer_size: Maximum number of log records to buffer

        """
        self.project_id = project_id
        self.handler = logging.handlers.MemoryHandler(
            capacity=buffer_size,
            flushLevel=logging.CRITICAL,  # Never auto-flush
            target=None,  # We'll manually write to file
        )
        self.handler.setLevel(logging.DEBUG)  # Always capture DEBUG
        self.handler.addFilter(ProjectLogFilter(project_id))

    def start(self) -> contextvars.Token:
        """Start capturing logs for this project.

        Sets the context variable to this project's ID and attaches
        the memory handler to the root logger. Thread-safely manages
        root logger level across concurrent captures. Ensures console
        handlers maintain their original level to avoid DEBUG spam.

        Returns:
            Token for resetting context variable later

        """
        global _active_captures, _original_root_level

        # Set context variable so all logs in this async context
        # are tagged with this project ID
        token = current_project_id.set(self.project_id)

        # Thread-safely manage root logger level
        with _capture_lock:
            root_logger = logging.getLogger()

            # First capture saves original level and sets to DEBUG
            if _active_captures == 0:
                _original_root_level = root_logger.level
                root_logger.setLevel(logging.DEBUG)

                # Ensure console/stream handlers don't show DEBUG logs
                # while still allowing our MemoryHandler to capture them
                # Only adjust handlers if --debug flag was NOT used
                # (if root logger was already at DEBUG, keep console
                # at DEBUG)
                if _original_root_level != logging.DEBUG:
                    for handler in root_logger.handlers:
                        # Only adjust StreamHandler (console), not
                        # MemoryHandlers
                        if (
                            isinstance(handler, logging.StreamHandler)
                            and not isinstance(
                                handler, logging.handlers.MemoryHandler
                            )
                            and handler.level == logging.NOTSET
                        ):
                            # Ensure console stays at INFO minimum
                            handler.setLevel(logging.INFO)

            _active_captures += 1

        # Attach handler to root logger to capture all logs
        root_logger.addHandler(self.handler)

        return token

    def write_to_file(self, log_path: pathlib.Path) -> None:
        """Write buffered logs to file.

        Args:
            log_path: Path where log file should be written

        """
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        log_path.parent.mkdir(parents=True, exist_ok=True)

        with log_path.open('w', encoding='utf-8') as f:
            for record in self.handler.buffer:
                f.write(formatter.format(record) + '\n')

    def cleanup(self, token: contextvars.Token) -> None:
        """Remove handler and reset context.

        Thread-safely manages restoring root logger level when the
        last active capture completes.

        Args:
            token: Token from start() to reset context variable

        """
        global _active_captures, _original_root_level

        root_logger = logging.getLogger()

        # Remove handler and close it
        root_logger.removeHandler(self.handler)
        self.handler.close()

        # Thread-safely manage root logger level restoration
        with _capture_lock:
            _active_captures -= 1

            # Last capture restores original level
            if _active_captures == 0 and _original_root_level is not None:
                root_logger.setLevel(_original_root_level)

        # Reset context variable
        current_project_id.reset(token)
