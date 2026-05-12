"""Resume state model for workflow resumability.

Provides state serialization and deserialization for resuming failed workflows
from the point of failure, using MessagePack binary format to discourage
manual editing while remaining debuggable with appropriate tools.
"""

import datetime
import pathlib

import msgpack
import pydantic

from . import github

SCHEMA_VERSION = 2


class ResumeState(pydantic.BaseModel):
    """State required to resume a failed workflow execution.

    This model captures all context needed to reconstruct the workflow
    execution state and resume from the point of failure. Serialized
    to MessagePack binary format (.state file) in the error directory.

    ``schema_version`` is bumped whenever the on-disk shape changes;
    older ``.state`` files are rejected at load time rather than
    silently re-keyed.
    """

    schema_version: int = SCHEMA_VERSION

    # Workflow identification
    workflow_slug: str
    workflow_path: pathlib.Path

    project_id: str
    project_slug: str

    # Execution state
    failed_action_index: int
    failed_action_name: str
    completed_action_indices: list[int]

    # Stage tracking (for stage-aware resumability)
    current_stage: str = 'primary'  # 'primary' or 'followup'
    followup_cycle: int = 0  # Followup cycle number (0 = primary stage)

    # WorkflowContext restoration
    starting_commit: str | None
    has_repository_changes: bool
    github_repository: github.GitHubRepository | None

    # PR information (for resuming followup stage)
    pull_request_number: int | None = None
    pull_request_url: str | None = None
    pr_branch: str | None = None

    # Error details
    error_message: str
    error_timestamp: datetime.datetime
    preserved_directory_path: pathlib.Path

    # Configuration snapshot
    configuration_hash: str  # To detect config changes

    # Error handler tracking
    retry_counts: dict[str, int] = {}
    active_error_handler: str | None = None
    handler_failed: bool = False
    original_exception_type: str | None = None
    original_exception_message: str | None = None

    def to_msgpack(self) -> bytes:
        """Serialize to MessagePack binary format.

        Returns:
            MessagePack-encoded bytes representing the state

        """
        return msgpack.packb(self.model_dump(mode='json'), use_bin_type=True)

    @classmethod
    def from_msgpack(cls, data: bytes) -> ResumeState:
        """Deserialize from MessagePack binary format.

        Args:
            data: MessagePack-encoded bytes

        Returns:
            Deserialized ResumeState instance

        Raises:
            ValueError: If the schema_version does not match
            msgpack.exceptions.ExtraData: If data contains extra bytes
            msgpack.exceptions.UnpackException: If data is malformed
            pydantic.ValidationError: If data doesn't match model schema

        """
        payload = msgpack.unpackb(data, raw=False)
        if isinstance(payload, dict) and payload.get('schema_version') not in (
            None,
            SCHEMA_VERSION,
        ):
            raise ValueError(
                f'Resume state schema version {payload["schema_version"]} '
                f'is not compatible with current version {SCHEMA_VERSION}'
            )
        return cls.model_validate(payload)
