"""Test workflow TOML loading and validation."""

import pathlib
import tomllib
import unittest

import pydantic

from imbi_automations.models.workflow import WorkflowConfiguration


class WorkflowLoadingTestCase(unittest.TestCase):
    """Test cases for workflow TOML loading and validation."""

    def test_comprehensive_workflow_loading(self) -> None:
        """Test loading the comprehensive workflow TOML."""
        workflow_file = pathlib.Path(
            'tests/data/workflows/comprehensive-test-workflow.toml'
        )

        # Load and parse the TOML file
        with workflow_file.open('rb') as f:
            toml_data = tomllib.load(f)

        # Validate with Pydantic model
        workflow_config = WorkflowConfiguration.model_validate(toml_data)

        # Verify all action types are present (except callable which requires
        # Python objects)
        action_types = {action.type for action in workflow_config.actions}
        expected_types = {
            'claude',
            'docker',
            'file',
            'git',
            'github',
            'shell',
            'template',
        }

        self.assertEqual(action_types, expected_types)

        # Verify file action commands
        file_actions = [a for a in workflow_config.actions if a.type == 'file']
        file_commands = {a.command for a in file_actions}
        expected_file_commands = {
            'append',
            'copy',
            'delete',
            'move',
            'rename',
            'write',
        }

        self.assertEqual(file_commands, expected_file_commands)

        # Verify docker action commands
        docker_actions = [
            a for a in workflow_config.actions if a.type == 'docker'
        ]
        docker_commands = {a.command for a in docker_actions}
        expected_docker_commands = {'build', 'extract', 'pull', 'push'}

        self.assertEqual(docker_commands, expected_docker_commands)

        # Check specific validation scenarios

        # Find delete actions (should have both path and pattern variants)
        delete_actions = [a for a in file_actions if a.command == 'delete']
        has_path_delete = any(a.path is not None for a in delete_actions)
        has_pattern_delete = any(a.pattern is not None for a in delete_actions)

        self.assertTrue(has_path_delete, 'Missing path-based delete action')
        self.assertTrue(
            has_pattern_delete, 'Missing pattern-based delete action'
        )

        # Check docker actions tags; default tag is 'latest' when omitted
        docker_with_tag = [a for a in docker_actions if a.tag]

        self.assertTrue(docker_with_tag, 'Missing docker actions with tags')

        # Check conditions (both local and remote)
        local_conditions = [
            c
            for c in workflow_config.conditions
            if c.file_exists or c.file_not_exists or c.file_contains
        ]
        remote_conditions = [
            c
            for c in workflow_config.conditions
            if c.remote_file_exists
            or c.remote_file_not_exists
            or c.remote_file_contains
        ]

        self.assertTrue(local_conditions, 'Missing local conditions')
        self.assertTrue(remote_conditions, 'Missing remote conditions')

        # Check filter configuration
        self.assertIsNotNone(
            workflow_config.filter, 'Missing filter configuration'
        )
        self.assertTrue(
            workflow_config.filter.project_ids, 'Missing project IDs in filter'
        )
        self.assertTrue(
            workflow_config.filter.project_types,
            'Missing project types in filter',
        )
        self.assertTrue(
            workflow_config.filter.project_facts,
            'Missing project facts in filter',
        )

    def test_invalid_file_action_validation(self) -> None:
        """Test that invalid file action configurations fail validation."""
        workflow_file = pathlib.Path(
            'tests/data/workflows/invalid-file-actions.toml'
        )

        # Load the TOML file
        with workflow_file.open('rb') as f:
            toml_data = tomllib.load(f)

        # Validation should fail due to invalid field combinations
        with self.assertRaises(pydantic.ValidationError) as exc_context:
            WorkflowConfiguration.model_validate(toml_data)

        error_str = str(exc_context.exception)

        # Check that we get expected validation error types
        expected_errors = [
            "Field 'content' is required for command 'append'",
            "Field 'content' is not allowed for command 'copy'",
            "Field 'path' is required for command 'write'",
            "Field 'path' or 'pattern' is required for command 'delete'",
            "Field 'content' is not allowed for command 'move'",
            "Field 'encoding' is not allowed for command 'rename'",
            "Field 'source' is not allowed for command 'write'",
        ]

        found_errors = sum(
            1 for error in expected_errors if error in error_str
        )
        self.assertGreaterEqual(
            found_errors,
            6,
            f'Expected at least 6 validation errors, found {found_errors}',
        )

    def test_invalid_docker_action_validation(self) -> None:
        """Test that invalid docker action configurations fail validation."""
        workflow_file = pathlib.Path(
            'tests/data/workflows/invalid-docker-actions.toml'
        )

        # Load the TOML file
        with workflow_file.open('rb') as f:
            toml_data = tomllib.load(f)

        # Validation should fail due to invalid field combinations
        with self.assertRaises(pydantic.ValidationError) as exc_context:
            WorkflowConfiguration.model_validate(toml_data)

        error_str = str(exc_context.exception)

        # Check that we get expected validation error types
        expected_errors = [
            "Field 'path' is required for command 'build'",
            "Field 'source' is required for command 'extract'",
            "Field 'destination' is required for command 'extract'",
            "Field 'path' is not allowed for command 'pull'",
            "Field 'source' is not allowed for command 'push'",
            "Field 'source' is not allowed for command 'build'",
            "Field 'destination' is not allowed for command 'build'",
            "Field 'destination' is not allowed for command 'push'",
        ]

        found_errors = sum(
            1 for error in expected_errors if error in error_str
        )
        self.assertGreaterEqual(
            found_errors,
            6,
            f'Expected at least 6 validation errors, found {found_errors}',
        )

    def test_commit_message_validation(self) -> None:
        """Test that commit_message validation works correctly."""
        from imbi_automations.models.workflow import WorkflowFileAction

        # Valid: commit_message with ai_commit=False and committable=True
        valid_action = WorkflowFileAction(
            name='test-action',
            type='file',
            command='copy',
            source='file:///src',
            destination='file:///dst',
            ai_commit=False,
            committable=True,
            commit_message='Manual commit message',
        )
        self.assertIsNotNone(valid_action.commit_message)

        # Invalid: commit_message with ai_commit=True
        with self.assertRaises(pydantic.ValidationError) as exc_context:
            WorkflowFileAction(
                name='test-action',
                type='file',
                command='copy',
                source='file:///src',
                destination='file:///dst',
                ai_commit=True,
                commit_message='Should fail',
            )
        self.assertIn(
            'commit_message cannot be set when ai_commit is True',
            str(exc_context.exception),
        )

        # Invalid: commit_message with committable=False
        with self.assertRaises(pydantic.ValidationError) as exc_context:
            WorkflowFileAction(
                name='test-action',
                type='file',
                command='copy',
                source='file:///src',
                destination='file:///dst',
                committable=False,
                commit_message='Should fail',
            )
        self.assertIn(
            'commit_message cannot be set when committable is False',
            str(exc_context.exception),
        )


if __name__ == '__main__':
    unittest.main()
