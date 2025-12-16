"""Unit tests for error handler models and validation."""

import pathlib
import unittest

from imbi_automations import models


class ErrorHandlerModelTestCase(unittest.TestCase):
    """Test error handler model validation."""

    def test_error_recovery_behavior_enum_values(self) -> None:
        """Test ErrorRecoveryBehavior enum has correct values."""
        self.assertEqual(models.ErrorRecoveryBehavior.retry, 'retry')
        self.assertEqual(models.ErrorRecoveryBehavior.skip, 'skip')
        self.assertEqual(models.ErrorRecoveryBehavior.fail, 'fail')

    def test_error_filter_action_types(self) -> None:
        """Test ErrorFilter with action_types."""
        error_filter = models.ErrorFilter(
            action_types=[
                models.WorkflowActionTypes.claude,
                models.WorkflowActionTypes.shell,
            ]
        )
        self.assertEqual(len(error_filter.action_types), 2)
        self.assertIn(
            models.WorkflowActionTypes.claude, error_filter.action_types
        )

    def test_error_filter_action_names(self) -> None:
        """Test ErrorFilter with action_names."""
        error_filter = models.ErrorFilter(action_names=['action1', 'action2'])
        self.assertEqual(error_filter.action_names, ['action1', 'action2'])

    def test_error_filter_stages(self) -> None:
        """Test ErrorFilter with stages."""
        error_filter = models.ErrorFilter(
            stages=[
                models.WorkflowActionStage.primary,
                models.WorkflowActionStage.followup,
            ]
        )
        self.assertEqual(len(error_filter.stages), 2)

    def test_error_filter_exception_types(self) -> None:
        """Test ErrorFilter with exception_types."""
        error_filter = models.ErrorFilter(
            exception_types=['TimeoutError', 'RuntimeError']
        )
        self.assertEqual(
            error_filter.exception_types, ['TimeoutError', 'RuntimeError']
        )

    def test_error_filter_exception_message_contains(self) -> None:
        """Test ErrorFilter with exception_message_contains."""
        error_filter = models.ErrorFilter(
            exception_message_contains='ruff.....Failed'
        )
        self.assertEqual(
            error_filter.exception_message_contains, 'ruff.....Failed'
        )

    def test_error_filter_condition(self) -> None:
        """Test ErrorFilter with Jinja2 condition."""
        error_filter = models.ErrorFilter(
            condition='{{ failed_action.type == "claude" }}'
        )
        self.assertIsNotNone(error_filter.condition)


class WorkflowActionErrorConfigTestCase(unittest.TestCase):
    """Test WorkflowAction error configuration validation."""

    def test_action_with_on_error_reference(self) -> None:
        """Test action can reference error handler via on_error."""
        action = models.WorkflowShellAction(
            name='test-action',
            type='shell',
            command='echo "test"',
            on_error='error-handler',
        )
        self.assertEqual(action.on_error, 'error-handler')

    def test_error_action_defaults(self) -> None:
        """Test error action has correct defaults."""
        action = models.WorkflowShellAction(
            name='error-handler',
            type='shell',
            stage='on_error',
            command='echo "error"',
            committable=False,
            error_filter=models.ErrorFilter(
                action_types=[models.WorkflowActionTypes.shell]
            ),
        )
        self.assertEqual(action.stage, models.WorkflowActionStage.on_error)
        self.assertEqual(
            action.recovery_behavior, models.ErrorRecoveryBehavior.skip
        )
        self.assertEqual(action.max_retry_attempts, 3)
        self.assertFalse(action.committable)

    def test_error_action_cannot_have_on_error(self) -> None:
        """Test error action cannot have on_error field."""
        with self.assertRaises(ValueError) as cm:
            models.WorkflowShellAction(
                name='error-handler',
                type='shell',
                stage='on_error',
                command='echo "error"',
                on_error='another-handler',
                error_filter=models.ErrorFilter(
                    action_types=[models.WorkflowActionTypes.shell]
                ),
            )
        self.assertIn('cannot have on_error', str(cm.exception))

    def test_error_action_cannot_have_ignore_errors(self) -> None:
        """Test error action cannot have ignore_errors=True."""
        with self.assertRaises(ValueError) as cm:
            models.WorkflowShellAction(
                name='error-handler',
                type='shell',
                stage='on_error',
                command='echo "error"',
                ignore_errors=True,
                error_filter=models.ErrorFilter(
                    action_types=[models.WorkflowActionTypes.shell]
                ),
            )
        self.assertIn('cannot have ignore_errors', str(cm.exception))

    def test_error_action_cannot_be_committable(self) -> None:
        """Test error action cannot be committable."""
        with self.assertRaises(ValueError) as cm:
            models.WorkflowShellAction(
                name='error-handler',
                type='shell',
                stage='on_error',
                command='echo "error"',
                committable=True,
                error_filter=models.ErrorFilter(
                    action_types=[models.WorkflowActionTypes.shell]
                ),
            )
        self.assertIn('cannot be committable', str(cm.exception))

    def test_non_error_action_cannot_have_recovery_behavior(self) -> None:
        """Test non-error action cannot set recovery_behavior."""
        with self.assertRaises(ValueError) as cm:
            models.WorkflowShellAction(
                name='test-action',
                type='shell',
                command='echo "test"',
                recovery_behavior='retry',
            )
        self.assertIn('only valid for stage=on_error', str(cm.exception))

    def test_non_error_action_cannot_have_max_retry_attempts(self) -> None:
        """Test non-error action cannot set max_retry_attempts."""
        with self.assertRaises(ValueError) as cm:
            models.WorkflowShellAction(
                name='test-action',
                type='shell',
                command='echo "test"',
                max_retry_attempts=5,
            )
        self.assertIn('only valid for stage=on_error', str(cm.exception))

    def test_non_error_action_cannot_have_error_filter(self) -> None:
        """Test non-error action cannot have error_filter."""
        with self.assertRaises(ValueError) as cm:
            models.WorkflowShellAction(
                name='test-action',
                type='shell',
                command='echo "test"',
                error_filter=models.ErrorFilter(
                    action_types=[models.WorkflowActionTypes.shell]
                ),
            )
        self.assertIn('only valid for stage=on_error', str(cm.exception))


class WorkflowErrorHandlerValidationTestCase(unittest.TestCase):
    """Test workflow-level error handler validation."""

    def test_on_error_must_reference_existing_action(self) -> None:
        """Test on_error must reference existing action."""
        with self.assertRaises(ValueError) as cm:
            models.Workflow(
                path=pathlib.Path('/mock/workflow'),
                configuration=models.WorkflowConfiguration(
                    name='test-workflow',
                    actions=[
                        models.WorkflowShellAction(
                            name='test-action',
                            type='shell',
                            command='echo "test"',
                            on_error='nonexistent-handler',
                        )
                    ],
                ),
            )
        self.assertIn('non-existent error handler', str(cm.exception))

    def test_on_error_must_reference_error_stage_action(self) -> None:
        """Test on_error must reference action with stage=on_error."""
        with self.assertRaises(ValueError) as cm:
            models.Workflow(
                path=pathlib.Path('/mock/workflow'),
                configuration=models.WorkflowConfiguration(
                    name='test-workflow',
                    actions=[
                        models.WorkflowShellAction(
                            name='test-action',
                            type='shell',
                            command='echo "test"',
                            on_error='not-an-error-handler',
                        ),
                        models.WorkflowShellAction(
                            name='not-an-error-handler',
                            type='shell',
                            command='echo "handler"',
                        ),
                    ],
                ),
            )
        self.assertIn('not stage=on_error', str(cm.exception))

    def test_error_action_must_be_referenced_or_have_filter(self) -> None:
        """Test error action must be referenced or have filter."""
        with self.assertRaises(ValueError) as cm:
            models.Workflow(
                path=pathlib.Path('/mock/workflow'),
                configuration=models.WorkflowConfiguration(
                    name='test-workflow',
                    actions=[
                        models.WorkflowShellAction(
                            name='orphan-handler',
                            type='shell',
                            stage='on_error',
                            command='echo "error"',
                            committable=False,
                        )
                    ],
                ),
            )
        self.assertIn('must be either referenced', str(cm.exception))
        self.assertIn('or have an error_filter', str(cm.exception))

    def test_valid_workflow_with_action_specific_handler(self) -> None:
        """Test valid workflow with action-specific error handler."""
        workflow = models.Workflow(
            path=pathlib.Path('/mock/workflow'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                actions=[
                    models.WorkflowShellAction(
                        name='test-action',
                        type='shell',
                        command='echo "test"',
                        on_error='error-handler',
                    ),
                    models.WorkflowShellAction(
                        name='error-handler',
                        type='shell',
                        stage='on_error',
                        command='echo "error"',
                        committable=False,
                        recovery_behavior='retry',
                        max_retry_attempts=2,
                    ),
                ],
            ),
        )
        self.assertEqual(len(workflow.configuration.actions), 2)

    def test_valid_workflow_with_global_handler(self) -> None:
        """Test valid workflow with global error handler."""
        workflow = models.Workflow(
            path=pathlib.Path('/mock/workflow'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow',
                actions=[
                    models.WorkflowShellAction(
                        name='test-action', type='shell', command='echo "test"'
                    ),
                    models.WorkflowShellAction(
                        name='global-handler',
                        type='shell',
                        stage='on_error',
                        command='echo "error"',
                        committable=False,
                        error_filter=models.ErrorFilter(
                            action_types=[models.WorkflowActionTypes.shell]
                        ),
                    ),
                ],
            ),
        )
        self.assertEqual(len(workflow.configuration.actions), 2)


class ResumeStateErrorTrackingTestCase(unittest.TestCase):
    """Test ResumeState error handler tracking fields."""

    def test_resume_state_has_retry_counts(self) -> None:
        """Test ResumeState includes retry_counts field."""
        state = models.ResumeState(
            workflow_slug='test-workflow',
            workflow_path=pathlib.Path('/workflow'),
            project_id=123,
            project_slug='test-project',
            failed_action_index=0,
            failed_action_name='test-action',
            completed_action_indices=[],
            starting_commit='abc123',
            has_repository_changes=False,
            github_repository=None,
            error_message='Test error',
            error_timestamp='2025-01-01T00:00:00',
            preserved_directory_path=pathlib.Path('/preserved'),
            configuration_hash='hash123',
            retry_counts={'action1': 2, 'action2': 1},
        )
        self.assertEqual(state.retry_counts, {'action1': 2, 'action2': 1})

    def test_resume_state_has_handler_tracking(self) -> None:
        """Test ResumeState includes handler tracking fields."""
        state = models.ResumeState(
            workflow_slug='test-workflow',
            workflow_path=pathlib.Path('/workflow'),
            project_id=123,
            project_slug='test-project',
            failed_action_index=0,
            failed_action_name='test-action',
            completed_action_indices=[],
            starting_commit='abc123',
            has_repository_changes=False,
            github_repository=None,
            error_message='Test error',
            error_timestamp='2025-01-01T00:00:00',
            preserved_directory_path=pathlib.Path('/preserved'),
            configuration_hash='hash123',
            active_error_handler='my-handler',
            handler_failed=True,
            original_exception_type='RuntimeError',
            original_exception_message='Original error',
        )
        self.assertEqual(state.active_error_handler, 'my-handler')
        self.assertTrue(state.handler_failed)
        self.assertEqual(state.original_exception_type, 'RuntimeError')
        self.assertEqual(state.original_exception_message, 'Original error')
