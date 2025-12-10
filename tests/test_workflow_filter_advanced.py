"""Advanced tests for workflow filter functionality.

Tests project facts filtering with type validation, field-level filtering
with various operators, GitHub workflow status filtering, and complex
combined filter scenarios.
"""

import pathlib
from unittest import mock

from imbi_automations import models, workflow_filter
from imbi_automations.models import workflow as workflow_models
from tests import base


class WorkflowFilterAdvancedTestCase(base.AsyncTestCase):
    """Advanced test cases for Filter class."""

    def setUp(self) -> None:
        super().setUp()
        self.configuration = models.Configuration(
            github=models.GitHubConfiguration(
                token='test-key'  # noqa: S106
            ),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )

        self.workflow = models.Workflow(
            path=pathlib.Path('/workflows/test'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow', actions=[]
            ),
        )

        self.filter = workflow_filter.Filter(
            self.configuration, self.workflow, verbose=False
        )

    def _create_project(
        self,
        facts: dict[str, bool | int | float | str] | None = None,
        **kwargs: object,
    ) -> models.ImbiProject:
        """Helper to create a test project with default values."""
        defaults = {
            'id': 123,
            'dependencies': None,
            'description': 'Test project',
            'environments': None,
            'facts': facts,
            'identifiers': None,
            'links': None,
            'name': 'test-project',
            'namespace': 'test-namespace',
            'namespace_slug': 'test-namespace',
            'project_score': None,
            'project_type': 'API',
            'project_type_slug': 'api',
            'slug': 'test-project',
            'urls': None,
            'imbi_url': 'https://imbi.example.com/projects/123',
        }
        defaults.update(kwargs)
        return models.ImbiProject(**defaults)

    # Project Facts Filtering Tests

    def test_filter_project_facts_string_match(self) -> None:
        """Test filtering by string fact value."""
        project = self._create_project(
            facts={'programming_language': 'Python 3.12'}
        )

        wf_filter = models.WorkflowFilter(
            project_facts={'Programming Language': 'Python 3.12'}
        )

        result = self.filter._filter_project_facts(project, wf_filter)
        self.assertIsNotNone(result)
        self.assertEqual(result.id, 123)

    def test_filter_project_facts_case_insensitive_keys(self) -> None:
        """Test that fact keys are normalized to lowercase with underscores."""
        project = self._create_project(
            facts={'programming_language': 'Python 3.12'}
        )

        # Filter uses human-readable format
        wf_filter = models.WorkflowFilter(
            project_facts={'Programming Language': 'Python 3.12'}
        )

        result = self.filter._filter_project_facts(project, wf_filter)
        self.assertIsNotNone(result)

    def test_filter_project_facts_boolean_match(self) -> None:
        """Test filtering by boolean fact value."""
        project = self._create_project(
            facts={'has_tests': True, 'is_deprecated': False}
        )

        wf_filter = models.WorkflowFilter(
            project_facts={'has_tests': True, 'is_deprecated': False}
        )

        result = self.filter._filter_project_facts(project, wf_filter)
        self.assertIsNotNone(result)

    def test_filter_project_facts_integer_match(self) -> None:
        """Test filtering by integer fact value."""
        project = self._create_project(facts={'test_coverage': 85})

        wf_filter = models.WorkflowFilter(project_facts={'test_coverage': 85})

        result = self.filter._filter_project_facts(project, wf_filter)
        self.assertIsNotNone(result)

    def test_filter_project_facts_float_match(self) -> None:
        """Test filtering by float fact value."""
        project = self._create_project(facts={'api_version': 1.5})

        wf_filter = models.WorkflowFilter(project_facts={'api_version': 1.5})

        result = self.filter._filter_project_facts(project, wf_filter)
        self.assertIsNotNone(result)

    def test_filter_project_facts_no_match(self) -> None:
        """Test filtering when fact value doesn't match."""
        project = self._create_project(
            facts={'programming_language': 'Python 3.11'}
        )

        wf_filter = models.WorkflowFilter(
            project_facts={'programming_language': 'Python 3.12'}
        )

        result = self.filter._filter_project_facts(project, wf_filter)
        self.assertIsNone(result)

    def test_filter_project_facts_missing_fact(self) -> None:
        """Test filtering when project is missing a required fact."""
        project = self._create_project(
            facts={'programming_language': 'Python'}
        )

        wf_filter = models.WorkflowFilter(
            project_facts={'test_framework': 'pytest'}
        )

        result = self.filter._filter_project_facts(project, wf_filter)
        self.assertIsNone(result)

    def test_filter_project_facts_no_facts(self) -> None:
        """Test filtering when project has no facts."""
        project = self._create_project(facts=None)

        wf_filter = models.WorkflowFilter(
            project_facts={'programming_language': 'Python'}
        )

        result = self.filter._filter_project_facts(project, wf_filter)
        self.assertIsNone(result)

    def test_filter_project_facts_multiple_facts_all_match(self) -> None:
        """Test filtering with multiple facts that all match."""
        project = self._create_project(
            facts={
                'programming_language': 'Python 3.12',
                'test_framework': 'pytest',
                'has_ci': True,
            }
        )

        wf_filter = models.WorkflowFilter(
            project_facts={
                'programming_language': 'Python 3.12',
                'test_framework': 'pytest',
                'has_ci': True,
            }
        )

        result = self.filter._filter_project_facts(project, wf_filter)
        self.assertIsNotNone(result)

    def test_filter_project_facts_multiple_facts_partial_match(self) -> None:
        """Test filtering with multiple facts where one doesn't match."""
        project = self._create_project(
            facts={
                'programming_language': 'Python 3.12',
                'test_framework': 'pytest',
            }
        )

        wf_filter = models.WorkflowFilter(
            project_facts={
                'programming_language': 'Python 3.12',
                'test_framework': 'unittest',  # Doesn't match
            }
        )

        result = self.filter._filter_project_facts(project, wf_filter)
        self.assertIsNone(result)

    # Field-level Filtering Tests

    def test_filter_project_fields_is_null_true(self) -> None:
        """Test field filter with is_null=True when field is None."""
        project = self._create_project(project_score=None)

        wf_filter = models.WorkflowFilter(
            project={
                'project_score': workflow_models.ProjectFieldFilter(
                    is_null=True
                )
            }
        )

        result = self.filter._filter_project_fields(project, wf_filter)
        self.assertIsNotNone(result)

    def test_filter_project_fields_is_null_false(self) -> None:
        """Test field filter with is_null=True when field has value."""
        project = self._create_project(project_score='85')

        wf_filter = models.WorkflowFilter(
            project={
                'project_score': workflow_models.ProjectFieldFilter(
                    is_null=True
                )
            }
        )

        result = self.filter._filter_project_fields(project, wf_filter)
        self.assertIsNone(result)

    def test_filter_project_fields_is_not_null_true(self) -> None:
        """Test field filter with is_not_null=True when field has value."""
        project = self._create_project(project_score='85')

        wf_filter = models.WorkflowFilter(
            project={
                'project_score': workflow_models.ProjectFieldFilter(
                    is_not_null=True
                )
            }
        )

        result = self.filter._filter_project_fields(project, wf_filter)
        self.assertIsNotNone(result)

    def test_filter_project_fields_is_not_null_false(self) -> None:
        """Test field filter with is_not_null=True when field is None."""
        project = self._create_project(project_score=None)

        wf_filter = models.WorkflowFilter(
            project={
                'project_score': workflow_models.ProjectFieldFilter(
                    is_not_null=True
                )
            }
        )

        result = self.filter._filter_project_fields(project, wf_filter)
        self.assertIsNone(result)

    def test_filter_project_fields_equals_match(self) -> None:
        """Test field filter with equals operator matching."""
        project = self._create_project(project_type='API')

        wf_filter = models.WorkflowFilter(
            project={
                'project_type': workflow_models.ProjectFieldFilter(
                    equals='API'
                )
            }
        )

        result = self.filter._filter_project_fields(project, wf_filter)
        self.assertIsNotNone(result)

    def test_filter_project_fields_equals_no_match(self) -> None:
        """Test field filter with equals operator not matching."""
        project = self._create_project(project_type='API')

        wf_filter = models.WorkflowFilter(
            project={
                'project_type': workflow_models.ProjectFieldFilter(
                    equals='Consumer'
                )
            }
        )

        result = self.filter._filter_project_fields(project, wf_filter)
        self.assertIsNone(result)

    def test_filter_project_fields_not_equals_match(self) -> None:
        """Test field filter with not_equals operator matching."""
        project = self._create_project(project_type='API')

        wf_filter = models.WorkflowFilter(
            project={
                'project_type': workflow_models.ProjectFieldFilter(
                    not_equals='Consumer'
                )
            }
        )

        result = self.filter._filter_project_fields(project, wf_filter)
        self.assertIsNotNone(result)

    def test_filter_project_fields_not_equals_no_match(self) -> None:
        """Test field filter with not_equals when values are equal."""
        project = self._create_project(project_type='API')

        wf_filter = models.WorkflowFilter(
            project={
                'project_type': workflow_models.ProjectFieldFilter(
                    not_equals='API'
                )
            }
        )

        result = self.filter._filter_project_fields(project, wf_filter)
        self.assertIsNone(result)

    def test_filter_project_fields_contains_match(self) -> None:
        """Test field filter with contains operator matching."""
        project = self._create_project(description='Python API service')

        wf_filter = models.WorkflowFilter(
            project={
                'description': workflow_models.ProjectFieldFilter(
                    contains='Python'
                )
            }
        )

        result = self.filter._filter_project_fields(project, wf_filter)
        self.assertIsNotNone(result)

    def test_filter_project_fields_contains_no_match(self) -> None:
        """Test field filter with contains operator not matching."""
        project = self._create_project(description='Python API service')

        wf_filter = models.WorkflowFilter(
            project={
                'description': workflow_models.ProjectFieldFilter(
                    contains='Ruby'
                )
            }
        )

        result = self.filter._filter_project_fields(project, wf_filter)
        self.assertIsNone(result)

    def test_filter_project_fields_contains_non_string(self) -> None:
        """Test field filter with contains on non-string field."""
        project = self._create_project(id=12345)

        wf_filter = models.WorkflowFilter(
            project={'id': workflow_models.ProjectFieldFilter(contains='123')}
        )

        result = self.filter._filter_project_fields(project, wf_filter)
        self.assertIsNone(result)

    def test_filter_project_fields_regex_match(self) -> None:
        """Test field filter with regex operator matching."""
        project = self._create_project(name='my-api-service')

        wf_filter = models.WorkflowFilter(
            project={
                'name': workflow_models.ProjectFieldFilter(regex=r'.*-api-.*')
            }
        )

        result = self.filter._filter_project_fields(project, wf_filter)
        self.assertIsNotNone(result)

    def test_filter_project_fields_regex_no_match(self) -> None:
        """Test field filter with regex operator not matching."""
        project = self._create_project(name='my-consumer-service')

        wf_filter = models.WorkflowFilter(
            project={
                'name': workflow_models.ProjectFieldFilter(regex=r'.*-api-.*')
            }
        )

        result = self.filter._filter_project_fields(project, wf_filter)
        self.assertIsNone(result)

    def test_filter_project_fields_regex_invalid_pattern(self) -> None:
        """Test field filter with invalid regex pattern."""
        project = self._create_project(name='my-service')

        wf_filter = models.WorkflowFilter(
            project={
                'name': workflow_models.ProjectFieldFilter(
                    regex=r'[invalid(regex'
                )
            }
        )

        result = self.filter._filter_project_fields(project, wf_filter)
        self.assertIsNone(result)

    def test_filter_project_fields_regex_non_string(self) -> None:
        """Test field filter with regex on non-string field."""
        project = self._create_project(id=12345)

        wf_filter = models.WorkflowFilter(
            project={'id': workflow_models.ProjectFieldFilter(regex=r'\d+')}
        )

        result = self.filter._filter_project_fields(project, wf_filter)
        self.assertIsNone(result)

    def test_filter_project_fields_is_empty_string_true(self) -> None:
        """Test field filter with is_empty=True for empty string."""
        project = self._create_project(description='')

        wf_filter = models.WorkflowFilter(
            project={
                'description': workflow_models.ProjectFieldFilter(
                    is_empty=True
                )
            }
        )

        result = self.filter._filter_project_fields(project, wf_filter)
        self.assertIsNotNone(result)

    def test_filter_project_fields_is_empty_whitespace_true(self) -> None:
        """Test field filter with is_empty=True for whitespace-only string."""
        project = self._create_project(description='   ')

        wf_filter = models.WorkflowFilter(
            project={
                'description': workflow_models.ProjectFieldFilter(
                    is_empty=True
                )
            }
        )

        result = self.filter._filter_project_fields(project, wf_filter)
        self.assertIsNotNone(result)

    def test_filter_project_fields_is_empty_null_true(self) -> None:
        """Test field filter with is_empty=True for None value."""
        project = self._create_project(description=None)

        wf_filter = models.WorkflowFilter(
            project={
                'description': workflow_models.ProjectFieldFilter(
                    is_empty=True
                )
            }
        )

        result = self.filter._filter_project_fields(project, wf_filter)
        self.assertIsNotNone(result)

    def test_filter_project_fields_is_empty_false(self) -> None:
        """Test field filter with is_empty=True for non-empty value."""
        project = self._create_project(description='Test project')

        wf_filter = models.WorkflowFilter(
            project={
                'description': workflow_models.ProjectFieldFilter(
                    is_empty=True
                )
            }
        )

        result = self.filter._filter_project_fields(project, wf_filter)
        self.assertIsNone(result)

    def test_filter_project_fields_is_empty_false_check(self) -> None:
        """Test field filter with is_empty=False for non-empty value."""
        project = self._create_project(description='Test project')

        wf_filter = models.WorkflowFilter(
            project={
                'description': workflow_models.ProjectFieldFilter(
                    is_empty=False
                )
            }
        )

        result = self.filter._filter_project_fields(project, wf_filter)
        self.assertIsNotNone(result)

    def test_filter_project_fields_nonexistent_field(self) -> None:
        """Test field filter with non-existent field name."""
        project = self._create_project()

        wf_filter = models.WorkflowFilter(
            project={
                'nonexistent_field': workflow_models.ProjectFieldFilter(
                    equals='value'
                )
            }
        )

        result = self.filter._filter_project_fields(project, wf_filter)
        self.assertIsNone(result)

    def test_filter_project_fields_multiple_fields_all_match(self) -> None:
        """Test field filter with multiple fields all matching."""
        project = self._create_project(
            project_type='API', project_score='85', description='Test API'
        )

        wf_filter = models.WorkflowFilter(
            project={
                'project_type': workflow_models.ProjectFieldFilter(
                    equals='API'
                ),
                'project_score': workflow_models.ProjectFieldFilter(
                    is_not_null=True
                ),
                'description': workflow_models.ProjectFieldFilter(
                    contains='API'
                ),
            }
        )

        result = self.filter._filter_project_fields(project, wf_filter)
        self.assertIsNotNone(result)

    def test_filter_project_fields_multiple_fields_partial_match(self) -> None:
        """Test field filter with multiple fields where one doesn't match."""
        project = self._create_project(
            project_type='API', project_score='85', description='Test Consumer'
        )

        wf_filter = models.WorkflowFilter(
            project={
                'project_type': workflow_models.ProjectFieldFilter(
                    equals='API'
                ),
                'description': workflow_models.ProjectFieldFilter(
                    contains='API'
                ),
            }
        )

        result = self.filter._filter_project_fields(project, wf_filter)
        self.assertIsNone(result)

    # GitHub Workflow Status Filtering Tests

    async def test_filter_github_workflow_status_exclude_match(self) -> None:
        """Test filtering out project with matching workflow status."""
        project = self._create_project(
            identifiers={'github': 'test-org/test-repo'}
        )

        # Mock the _filter_github_action_status method directly
        with mock.patch.object(
            self.filter, '_filter_github_action_status', return_value='failure'
        ):
            wf_filter = models.WorkflowFilter(
                github_identifier_required=True,
                github_workflow_status_exclude={'failure'},
            )

            result = await self.filter.filter_project(project, wf_filter)
            self.assertIsNone(result)

    async def test_filter_github_workflow_status_no_exclude_match(
        self,
    ) -> None:
        """Test allowing project when workflow status doesn't match exclude."""
        project = self._create_project(
            identifiers={'github': 'test-org/test-repo'}
        )

        # Mock the _filter_github_action_status method directly
        with mock.patch.object(
            self.filter, '_filter_github_action_status', return_value='success'
        ):
            wf_filter = models.WorkflowFilter(
                github_identifier_required=True,
                github_workflow_status_exclude={'failure'},
            )

            result = await self.filter.filter_project(project, wf_filter)
            self.assertIsNotNone(result)

    async def test_filter_github_workflow_status_no_repository(self) -> None:
        """Test handling when GitHub repository lookup returns None."""
        project = self._create_project(
            identifiers={'github': 'test-org/nonexistent-repo'}
        )

        # Mock the _filter_github_action_status method to return None
        with mock.patch.object(
            self.filter, '_filter_github_action_status', return_value=None
        ):
            wf_filter = models.WorkflowFilter(
                github_identifier_required=True,
                github_workflow_status_exclude={'failure'},
            )

            # Should pass through because no status could be determined
            result = await self.filter.filter_project(project, wf_filter)
            self.assertIsNotNone(result)

    # Open Workflow PR Filtering Tests

    async def test_filter_exclude_open_workflow_prs_open_pr_excluded(
        self,
    ) -> None:
        """Test project excluded when open PR exists."""
        project = self._create_project(
            identifiers={'github': 'test-org/test-repo'}
        )

        # Mock the _filter_open_workflow_pr method to return True (exclude)
        with mock.patch.object(
            self.filter, '_filter_open_workflow_pr', return_value=True
        ):
            wf_filter = models.WorkflowFilter(exclude_open_workflow_prs=True)

            result = await self.filter.filter_project(project, wf_filter)
            self.assertIsNone(result)

    async def test_filter_exclude_open_workflow_prs_no_pr_allowed(
        self,
    ) -> None:
        """Test project allowed when no open PR exists."""
        project = self._create_project(
            identifiers={'github': 'test-org/test-repo'}
        )

        # Mock the _filter_open_workflow_pr method to return False (allow)
        with mock.patch.object(
            self.filter, '_filter_open_workflow_pr', return_value=False
        ):
            wf_filter = models.WorkflowFilter(exclude_open_workflow_prs=True)

            result = await self.filter.filter_project(project, wf_filter)
            self.assertIsNotNone(result)

    async def test_filter_exclude_open_workflow_prs_with_workflow_slug(
        self,
    ) -> None:
        """Test filter with specific workflow slug."""
        project = self._create_project(
            identifiers={'github': 'test-org/test-repo'}
        )

        # Mock the _filter_open_workflow_pr method
        with mock.patch.object(
            self.filter, '_filter_open_workflow_pr', return_value=True
        ):
            wf_filter = models.WorkflowFilter(
                exclude_open_workflow_prs='other-workflow'
            )

            result = await self.filter.filter_project(project, wf_filter)
            self.assertIsNone(result)

    async def test_filter_exclude_open_workflow_prs_disabled(self) -> None:
        """Test filter disabled by default."""
        project = self._create_project(
            identifiers={'github': 'test-org/test-repo'}
        )

        wf_filter = models.WorkflowFilter(exclude_open_workflow_prs=False)

        # Should not call the filter method at all
        with mock.patch.object(
            self.filter, '_filter_open_workflow_pr'
        ) as mock_filter:
            result = await self.filter.filter_project(project, wf_filter)
            self.assertIsNotNone(result)
            mock_filter.assert_not_called()

    # Combined Filter Scenarios

    async def test_filter_project_combined_all_match(self) -> None:
        """Test combined filters with all conditions matching."""
        project = self._create_project(
            project_type='API',
            project_type_slug='api',
            facts={'programming_language': 'Python 3.12'},
            environments=[
                models.ImbiEnvironment(
                    name='Production', slug='production', icon_class='fa-prod'
                )
            ],
            identifiers={'github': 'test-org/test-repo'},
            description='Python API service',
        )

        wf_filter = models.WorkflowFilter(
            project_types={'api'},
            project_facts={'programming_language': 'Python 3.12'},
            project_environments={'production'},
            github_identifier_required=True,
            project={
                'description': workflow_models.ProjectFieldFilter(
                    contains='Python'
                )
            },
        )

        result = await self.filter.filter_project(project, wf_filter)
        self.assertIsNotNone(result)
        self.assertEqual(result.id, 123)

    async def test_filter_project_combined_type_mismatch(self) -> None:
        """Test combined filters failing on project type."""
        project = self._create_project(
            project_type='Consumer',
            project_type_slug='consumer',
            facts={'programming_language': 'Python 3.12'},
            identifiers={'github': 'test-org/test-repo'},
        )

        wf_filter = models.WorkflowFilter(
            project_types={'api'},  # Doesn't match 'consumer'
            project_facts={'programming_language': 'Python 3.12'},
            github_identifier_required=True,
        )

        result = await self.filter.filter_project(project, wf_filter)
        self.assertIsNone(result)

    async def test_filter_project_combined_facts_mismatch(self) -> None:
        """Test combined filters failing on project facts."""
        project = self._create_project(
            project_type_slug='api',
            facts={'programming_language': 'Python 3.11'},  # Wrong version
            identifiers={'github': 'test-org/test-repo'},
        )

        wf_filter = models.WorkflowFilter(
            project_types={'api'},
            project_facts={'programming_language': 'Python 3.12'},
            github_identifier_required=True,
        )

        result = await self.filter.filter_project(project, wf_filter)
        self.assertIsNone(result)

    async def test_filter_project_combined_no_github(self) -> None:
        """Test combined filters failing on missing GitHub identifier."""
        project = self._create_project(
            project_type_slug='api',
            facts={'programming_language': 'Python 3.12'},
            identifiers=None,  # No GitHub identifier
        )

        wf_filter = models.WorkflowFilter(
            project_types={'api'},
            project_facts={'programming_language': 'Python 3.12'},
            github_identifier_required=True,
        )

        result = await self.filter.filter_project(project, wf_filter)
        self.assertIsNone(result)

    async def test_filter_project_no_filter(self) -> None:
        """Test that None filter allows all projects through."""
        project = self._create_project()

        result = await self.filter.filter_project(project, None)
        self.assertIsNotNone(result)
        self.assertEqual(result.id, 123)

    async def test_filter_project_empty_filter(self) -> None:
        """Test that empty filter allows all projects through."""
        project = self._create_project()

        wf_filter = models.WorkflowFilter()

        result = await self.filter.filter_project(project, wf_filter)
        self.assertIsNotNone(result)
        self.assertEqual(result.id, 123)

    async def test_filter_project_ids_match(self) -> None:
        """Test filtering by project IDs with matching ID."""
        project = self._create_project(id=123)

        wf_filter = models.WorkflowFilter(project_ids={123, 456})

        result = await self.filter.filter_project(project, wf_filter)
        self.assertIsNotNone(result)

    async def test_filter_project_ids_no_match(self) -> None:
        """Test filtering by project IDs with non-matching ID."""
        project = self._create_project(id=789)

        wf_filter = models.WorkflowFilter(project_ids={123, 456})

        result = await self.filter.filter_project(project, wf_filter)
        self.assertIsNone(result)
