"""Tests for workflow resume functionality."""

import datetime
import pathlib
import unittest

from imbi_automations import models


class ResumeStateTestCase(unittest.TestCase):
    """Tests for ResumeState model serialization and deserialization."""

    def test_resume_state_serialization(self) -> None:
        """Test ResumeState can be serialized to and from MessagePack."""
        # Create a resume state
        state = models.ResumeState(
            workflow_slug='test-workflow',
            workflow_path=pathlib.Path('/tmp/workflows/test-workflow'),  # noqa: S108
            project_id=123,
            project_slug='test-project',
            failed_action_index=2,
            failed_action_name='test-action',
            completed_action_indices=[0, 1],
            starting_commit='abc123',
            has_repository_changes=True,
            github_repository=None,
            error_message='Test error message',
            error_timestamp=datetime.datetime(
                2025, 1, 1, 12, 0, 0, tzinfo=datetime.UTC
            ),
            preserved_directory_path=pathlib.Path('/tmp/errors/test-project'),  # noqa: S108
            configuration_hash='abc123def456',
        )

        # Serialize to MessagePack
        msgpack_data = state.to_msgpack()
        self.assertIsInstance(msgpack_data, bytes)
        self.assertGreater(len(msgpack_data), 0)

        # Deserialize from MessagePack
        restored_state = models.ResumeState.from_msgpack(msgpack_data)

        # Verify all fields match
        self.assertEqual(restored_state.workflow_slug, state.workflow_slug)
        self.assertEqual(restored_state.workflow_path, state.workflow_path)
        self.assertEqual(restored_state.project_id, state.project_id)
        self.assertEqual(restored_state.project_slug, state.project_slug)
        self.assertEqual(
            restored_state.failed_action_index, state.failed_action_index
        )
        self.assertEqual(
            restored_state.failed_action_name, state.failed_action_name
        )
        self.assertEqual(
            restored_state.completed_action_indices,
            state.completed_action_indices,
        )
        self.assertEqual(restored_state.starting_commit, state.starting_commit)
        self.assertEqual(
            restored_state.has_repository_changes, state.has_repository_changes
        )
        self.assertEqual(
            restored_state.github_repository, state.github_repository
        )
        self.assertEqual(restored_state.error_message, state.error_message)
        self.assertEqual(restored_state.error_timestamp, state.error_timestamp)
        self.assertEqual(
            restored_state.preserved_directory_path,
            state.preserved_directory_path,
        )
        self.assertEqual(
            restored_state.configuration_hash, state.configuration_hash
        )

    def test_resume_state_without_github_repository(self) -> None:
        """Test ResumeState serialization without GitHub repository."""
        state = models.ResumeState(
            workflow_slug='test-workflow',
            workflow_path=pathlib.Path('/tmp/workflows/test-workflow'),  # noqa: S108
            project_id=123,
            project_slug='test-project',
            failed_action_index=1,
            failed_action_name='failing-action',
            completed_action_indices=[0],
            starting_commit='def456',
            has_repository_changes=False,
            github_repository=None,
            error_message='Network timeout',
            error_timestamp=datetime.datetime.now(tz=datetime.UTC),
            preserved_directory_path=pathlib.Path('/tmp/errors/test-project'),  # noqa: S108
            configuration_hash='fedcba987654',
        )

        # Serialize and deserialize
        msgpack_data = state.to_msgpack()
        restored_state = models.ResumeState.from_msgpack(msgpack_data)

        # Verify fields match
        self.assertEqual(restored_state.failed_action_name, 'failing-action')
        self.assertIsNone(restored_state.github_repository)
