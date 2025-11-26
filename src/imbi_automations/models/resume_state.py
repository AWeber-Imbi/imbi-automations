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


class ResumeState(pydantic.BaseModel):
    """State required to resume a failed workflow execution.

    This model captures all context needed to reconstruct the workflow
    execution state and resume from the point of failure. Serialized
    to MessagePack binary format (.state file) in the error directory.
    """

    # Workflow identification
    workflow_slug: str
    workflow_path: pathlib.Path

    # Project information
    project_id: int
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

    def to_msgpack(self) -> bytes:
        """Serialize to MessagePack binary format.

        Returns:
            MessagePack-encoded bytes representing the state

        """
        return msgpack.packb(self.model_dump(mode='json'), use_bin_type=True)

    @classmethod
    def from_msgpack(cls, data: bytes) -> 'ResumeState':
        """Deserialize from MessagePack binary format.

        Args:
            data: MessagePack-encoded bytes

        Returns:
            Deserialized ResumeState instance

        Raises:
            msgpack.exceptions.ExtraData: If data contains extra bytes
            msgpack.exceptions.UnpackException: If data is malformed
            pydantic.ValidationError: If data doesn't match model schema

        """
        return cls.model_validate(msgpack.unpackb(data, raw=False))
