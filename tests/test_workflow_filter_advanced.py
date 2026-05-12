"""Advanced tests for workflow filter functionality.

Tests blueprint-attribute filtering, field-level filtering with various
operators, GitHub workflow status filtering, and complex combined
filter scenarios.
"""

import pathlib
import typing
from unittest import mock

from imbi_automations import models, workflow_filter
from imbi_automations.models import workflow as workflow_models
from tests import base, factories


class WorkflowFilterAdvancedTestCase(base.AsyncTestCase):
    """Advanced test cases for :class:`workflow_filter.Filter`."""

    def setUp(self) -> None:
        super().setUp()
        self.configuration = models.Configuration(
            github=models.GitHubConfiguration(
                token='test-key'  # noqa: S106
            ),
            imbi=models.ImbiConfiguration(
                organization='test-org',
                base_url='https://imbi.test.com',
                api_key='ik_test',
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

    # -- Factory --------------------------------------------------------

    def _create_project(
        self,
        *,
        attributes: dict[str, typing.Any] | None = None,
        project_id: str = 'proj_123',
        slug: str = 'test-project',
        name: str = 'test-project',
        description: str | None = 'Test project',
        team_slug: str = 'platform',
        project_type_slugs: tuple[str, ...] = ('api',),
        environments: list[models.ImbiEnvironment] | None = None,
        identifiers: dict[str, int | str] | None = None,
        score: float | None = None,
    ) -> models.ImbiProject:
        return factories.make_project(
            id=project_id,
            name=name,
            slug=slug,
            description=description,
            team_slug=team_slug,
            project_type_slugs=project_type_slugs,
            environments=environments,
            identifiers=identifiers,
            score=score,
            attributes=attributes,
        )

    # -- Blueprint attribute filtering ----------------------------------

    def test_filter_project_facts_string_match(self) -> None:
        project = self._create_project(
            attributes={'programming_language': 'Python 3.12'}
        )
        wf = models.WorkflowFilter(
            project_facts={'programming_language': 'Python 3.12'}
        )
        result = self.filter._filter_project_facts(project, wf)
        self.assertIsNotNone(result)
        self.assertEqual(result.id, 'proj_123')

    def test_filter_project_facts_snake_case_keys(self) -> None:
        project = self._create_project(
            attributes={'programming_language': 'Python 3.12'}
        )
        wf = models.WorkflowFilter(
            project_facts={'programming_language': 'Python 3.12'}
        )
        self.assertIsNotNone(self.filter._filter_project_facts(project, wf))

    def test_filter_project_facts_boolean_match(self) -> None:
        project = self._create_project(
            attributes={'has_tests': True, 'is_deprecated': False}
        )
        wf = models.WorkflowFilter(
            project_facts={'has_tests': True, 'is_deprecated': False}
        )
        self.assertIsNotNone(self.filter._filter_project_facts(project, wf))

    def test_filter_project_facts_integer_match(self) -> None:
        project = self._create_project(attributes={'test_coverage': 85})
        wf = models.WorkflowFilter(project_facts={'test_coverage': 85})
        self.assertIsNotNone(self.filter._filter_project_facts(project, wf))

    def test_filter_project_facts_float_match(self) -> None:
        project = self._create_project(attributes={'api_version': 1.5})
        wf = models.WorkflowFilter(project_facts={'api_version': 1.5})
        self.assertIsNotNone(self.filter._filter_project_facts(project, wf))

    def test_filter_project_facts_no_match(self) -> None:
        project = self._create_project(
            attributes={'programming_language': 'Python 3.11'}
        )
        wf = models.WorkflowFilter(
            project_facts={'programming_language': 'Python 3.12'}
        )
        self.assertIsNone(self.filter._filter_project_facts(project, wf))

    def test_filter_project_facts_missing_fact(self) -> None:
        project = self._create_project(
            attributes={'programming_language': 'Python'}
        )
        wf = models.WorkflowFilter(project_facts={'test_framework': 'pytest'})
        self.assertIsNone(self.filter._filter_project_facts(project, wf))

    def test_filter_project_facts_no_facts(self) -> None:
        project = self._create_project()
        wf = models.WorkflowFilter(
            project_facts={'programming_language': 'Python'}
        )
        self.assertIsNone(self.filter._filter_project_facts(project, wf))

    def test_filter_project_facts_multiple_facts_all_match(self) -> None:
        project = self._create_project(
            attributes={
                'programming_language': 'Python 3.12',
                'test_framework': 'pytest',
                'has_ci': True,
            }
        )
        wf = models.WorkflowFilter(
            project_facts={
                'programming_language': 'Python 3.12',
                'test_framework': 'pytest',
                'has_ci': True,
            }
        )
        self.assertIsNotNone(self.filter._filter_project_facts(project, wf))

    def test_filter_project_facts_multiple_facts_partial_match(self) -> None:
        project = self._create_project(
            attributes={
                'programming_language': 'Python 3.12',
                'test_framework': 'pytest',
            }
        )
        wf = models.WorkflowFilter(
            project_facts={
                'programming_language': 'Python 3.12',
                'test_framework': 'unittest',
            }
        )
        self.assertIsNone(self.filter._filter_project_facts(project, wf))

    # -- Field-level filtering ------------------------------------------

    def test_filter_project_fields_is_null_true(self) -> None:
        project = self._create_project(score=None)
        wf = models.WorkflowFilter(
            project={'score': workflow_models.ProjectFieldFilter(is_null=True)}
        )
        self.assertIsNotNone(self.filter._filter_project_fields(project, wf))

    def test_filter_project_fields_is_null_false(self) -> None:
        project = self._create_project(score=85.0)
        wf = models.WorkflowFilter(
            project={'score': workflow_models.ProjectFieldFilter(is_null=True)}
        )
        self.assertIsNone(self.filter._filter_project_fields(project, wf))

    def test_filter_project_fields_is_not_null_true(self) -> None:
        project = self._create_project(score=85.0)
        wf = models.WorkflowFilter(
            project={
                'score': workflow_models.ProjectFieldFilter(is_not_null=True)
            }
        )
        self.assertIsNotNone(self.filter._filter_project_fields(project, wf))

    def test_filter_project_fields_is_not_null_false(self) -> None:
        project = self._create_project(score=None)
        wf = models.WorkflowFilter(
            project={
                'score': workflow_models.ProjectFieldFilter(is_not_null=True)
            }
        )
        self.assertIsNone(self.filter._filter_project_fields(project, wf))

    def test_filter_project_fields_equals_match(self) -> None:
        project = self._create_project(slug='my-api-service')
        wf = models.WorkflowFilter(
            project={
                'slug': workflow_models.ProjectFieldFilter(
                    equals='my-api-service'
                )
            }
        )
        self.assertIsNotNone(self.filter._filter_project_fields(project, wf))

    def test_filter_project_fields_equals_no_match(self) -> None:
        project = self._create_project(slug='my-api-service')
        wf = models.WorkflowFilter(
            project={
                'slug': workflow_models.ProjectFieldFilter(equals='other')
            }
        )
        self.assertIsNone(self.filter._filter_project_fields(project, wf))

    def test_filter_project_fields_not_equals_match(self) -> None:
        project = self._create_project(slug='my-api-service')
        wf = models.WorkflowFilter(
            project={
                'slug': workflow_models.ProjectFieldFilter(
                    not_equals='other-slug'
                )
            }
        )
        self.assertIsNotNone(self.filter._filter_project_fields(project, wf))

    def test_filter_project_fields_not_equals_no_match(self) -> None:
        project = self._create_project(slug='my-api-service')
        wf = models.WorkflowFilter(
            project={
                'slug': workflow_models.ProjectFieldFilter(
                    not_equals='my-api-service'
                )
            }
        )
        self.assertIsNone(self.filter._filter_project_fields(project, wf))

    def test_filter_project_fields_contains_match(self) -> None:
        project = self._create_project(description='Python API service')
        wf = models.WorkflowFilter(
            project={
                'description': workflow_models.ProjectFieldFilter(
                    contains='Python'
                )
            }
        )
        self.assertIsNotNone(self.filter._filter_project_fields(project, wf))

    def test_filter_project_fields_contains_no_match(self) -> None:
        project = self._create_project(description='Python API service')
        wf = models.WorkflowFilter(
            project={
                'description': workflow_models.ProjectFieldFilter(
                    contains='Ruby'
                )
            }
        )
        self.assertIsNone(self.filter._filter_project_fields(project, wf))

    def test_filter_project_fields_contains_non_string(self) -> None:
        project = self._create_project(score=85.0)
        wf = models.WorkflowFilter(
            project={'score': workflow_models.ProjectFieldFilter(contains='8')}
        )
        self.assertIsNone(self.filter._filter_project_fields(project, wf))

    def test_filter_project_fields_regex_match(self) -> None:
        project = self._create_project(name='my-api-service')
        wf = models.WorkflowFilter(
            project={
                'name': workflow_models.ProjectFieldFilter(regex=r'.*-api-.*')
            }
        )
        self.assertIsNotNone(self.filter._filter_project_fields(project, wf))

    def test_filter_project_fields_regex_no_match(self) -> None:
        project = self._create_project(name='my-consumer-service')
        wf = models.WorkflowFilter(
            project={
                'name': workflow_models.ProjectFieldFilter(regex=r'.*-api-.*')
            }
        )
        self.assertIsNone(self.filter._filter_project_fields(project, wf))

    def test_filter_project_fields_regex_invalid_pattern(self) -> None:
        project = self._create_project(name='my-service')
        wf = models.WorkflowFilter(
            project={
                'name': workflow_models.ProjectFieldFilter(
                    regex=r'[invalid(regex'
                )
            }
        )
        self.assertIsNone(self.filter._filter_project_fields(project, wf))

    def test_filter_project_fields_regex_non_string(self) -> None:
        project = self._create_project(score=85.0)
        wf = models.WorkflowFilter(
            project={'score': workflow_models.ProjectFieldFilter(regex=r'\d+')}
        )
        self.assertIsNone(self.filter._filter_project_fields(project, wf))

    def test_filter_project_fields_is_empty_string_true(self) -> None:
        project = self._create_project(description='')
        wf = models.WorkflowFilter(
            project={
                'description': workflow_models.ProjectFieldFilter(
                    is_empty=True
                )
            }
        )
        self.assertIsNotNone(self.filter._filter_project_fields(project, wf))

    def test_filter_project_fields_is_empty_whitespace_true(self) -> None:
        project = self._create_project(description='   ')
        wf = models.WorkflowFilter(
            project={
                'description': workflow_models.ProjectFieldFilter(
                    is_empty=True
                )
            }
        )
        self.assertIsNotNone(self.filter._filter_project_fields(project, wf))

    def test_filter_project_fields_is_empty_null_true(self) -> None:
        project = self._create_project(description=None)
        wf = models.WorkflowFilter(
            project={
                'description': workflow_models.ProjectFieldFilter(
                    is_empty=True
                )
            }
        )
        self.assertIsNotNone(self.filter._filter_project_fields(project, wf))

    def test_filter_project_fields_is_empty_false(self) -> None:
        project = self._create_project(description='Test project')
        wf = models.WorkflowFilter(
            project={
                'description': workflow_models.ProjectFieldFilter(
                    is_empty=True
                )
            }
        )
        self.assertIsNone(self.filter._filter_project_fields(project, wf))

    def test_filter_project_fields_is_empty_false_check(self) -> None:
        project = self._create_project(description='Test project')
        wf = models.WorkflowFilter(
            project={
                'description': workflow_models.ProjectFieldFilter(
                    is_empty=False
                )
            }
        )
        self.assertIsNotNone(self.filter._filter_project_fields(project, wf))

    def test_filter_project_fields_nonexistent_field(self) -> None:
        project = self._create_project()
        wf = models.WorkflowFilter(
            project={
                'nonexistent_field': workflow_models.ProjectFieldFilter(
                    equals='value'
                )
            }
        )
        self.assertIsNone(self.filter._filter_project_fields(project, wf))

    def test_filter_project_fields_multiple_fields_all_match(self) -> None:
        project = self._create_project(
            slug='my-api', description='Test API', score=85.0
        )
        wf = models.WorkflowFilter(
            project={
                'slug': workflow_models.ProjectFieldFilter(equals='my-api'),
                'score': workflow_models.ProjectFieldFilter(is_not_null=True),
                'description': workflow_models.ProjectFieldFilter(
                    contains='API'
                ),
            }
        )
        self.assertIsNotNone(self.filter._filter_project_fields(project, wf))

    def test_filter_project_fields_multiple_fields_partial_match(self) -> None:
        project = self._create_project(
            slug='my-api', description='Test Consumer', score=85.0
        )
        wf = models.WorkflowFilter(
            project={
                'slug': workflow_models.ProjectFieldFilter(equals='my-api'),
                'description': workflow_models.ProjectFieldFilter(
                    contains='API'
                ),
            }
        )
        self.assertIsNone(self.filter._filter_project_fields(project, wf))

    # -- GitHub workflow status filtering -------------------------------

    async def test_filter_github_workflow_status_exclude_match(self) -> None:
        project = self._create_project(
            identifiers={'github': 'test-org/test-repo'}
        )
        with mock.patch.object(
            self.filter, '_filter_github_action_status', return_value='failure'
        ):
            wf = models.WorkflowFilter(
                github_identifier_required=True,
                github_workflow_status_exclude={'failure'},
            )
            self.assertIsNone(await self.filter.filter_project(project, wf))

    async def test_filter_github_workflow_status_no_exclude_match(
        self,
    ) -> None:
        project = self._create_project(
            identifiers={'github': 'test-org/test-repo'}
        )
        with mock.patch.object(
            self.filter, '_filter_github_action_status', return_value='success'
        ):
            wf = models.WorkflowFilter(
                github_identifier_required=True,
                github_workflow_status_exclude={'failure'},
            )
            self.assertIsNotNone(await self.filter.filter_project(project, wf))

    async def test_filter_github_workflow_status_no_repository(self) -> None:
        project = self._create_project(
            identifiers={'github': 'test-org/nonexistent-repo'}
        )
        with mock.patch.object(
            self.filter, '_filter_github_action_status', return_value=None
        ):
            wf = models.WorkflowFilter(
                github_identifier_required=True,
                github_workflow_status_exclude={'failure'},
            )
            self.assertIsNotNone(await self.filter.filter_project(project, wf))

    # -- Open workflow PR filtering -------------------------------------

    async def test_filter_exclude_open_workflow_prs_open_pr_excluded(
        self,
    ) -> None:
        project = self._create_project(
            identifiers={'github': 'test-org/test-repo'}
        )
        with mock.patch.object(
            self.filter, '_filter_open_workflow_pr', return_value=True
        ):
            wf = models.WorkflowFilter(exclude_open_workflow_prs=True)
            self.assertIsNone(await self.filter.filter_project(project, wf))

    async def test_filter_exclude_open_workflow_prs_no_pr_allowed(
        self,
    ) -> None:
        project = self._create_project(
            identifiers={'github': 'test-org/test-repo'}
        )
        with mock.patch.object(
            self.filter, '_filter_open_workflow_pr', return_value=False
        ):
            wf = models.WorkflowFilter(exclude_open_workflow_prs=True)
            self.assertIsNotNone(await self.filter.filter_project(project, wf))

    async def test_filter_exclude_open_workflow_prs_with_workflow_slug(
        self,
    ) -> None:
        project = self._create_project(
            identifiers={'github': 'test-org/test-repo'}
        )
        with mock.patch.object(
            self.filter, '_filter_open_workflow_pr', return_value=True
        ):
            wf = models.WorkflowFilter(
                exclude_open_workflow_prs='other-workflow'
            )
            self.assertIsNone(await self.filter.filter_project(project, wf))

    async def test_filter_exclude_open_workflow_prs_disabled(self) -> None:
        project = self._create_project(
            identifiers={'github': 'test-org/test-repo'}
        )
        wf = models.WorkflowFilter(exclude_open_workflow_prs=False)
        with mock.patch.object(
            self.filter, '_filter_open_workflow_pr'
        ) as mock_filter:
            result = await self.filter.filter_project(project, wf)
            self.assertIsNotNone(result)
            mock_filter.assert_not_called()

    # -- Combined filter scenarios --------------------------------------

    async def test_filter_project_combined_all_match(self) -> None:
        project = self._create_project(
            project_type_slugs=('api',),
            attributes={'programming_language': 'Python 3.12'},
            environments=[
                models.ImbiEnvironment(name='Production', slug='production')
            ],
            identifiers={'github': 'test-org/test-repo'},
            description='Python API service',
        )
        wf = models.WorkflowFilter(
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
        result = await self.filter.filter_project(project, wf)
        self.assertIsNotNone(result)
        self.assertEqual(result.id, 'proj_123')

    async def test_filter_project_combined_type_mismatch(self) -> None:
        project = self._create_project(
            project_type_slugs=('consumer',),
            attributes={'programming_language': 'Python 3.12'},
            identifiers={'github': 'test-org/test-repo'},
        )
        wf = models.WorkflowFilter(
            project_types={'api'},
            project_facts={'programming_language': 'Python 3.12'},
            github_identifier_required=True,
        )
        self.assertIsNone(await self.filter.filter_project(project, wf))

    async def test_filter_project_combined_facts_mismatch(self) -> None:
        project = self._create_project(
            project_type_slugs=('api',),
            attributes={'programming_language': 'Python 3.11'},
            identifiers={'github': 'test-org/test-repo'},
        )
        wf = models.WorkflowFilter(
            project_types={'api'},
            project_facts={'programming_language': 'Python 3.12'},
            github_identifier_required=True,
        )
        self.assertIsNone(await self.filter.filter_project(project, wf))

    async def test_filter_project_combined_no_github(self) -> None:
        project = self._create_project(
            project_type_slugs=('api',),
            attributes={'programming_language': 'Python 3.12'},
            identifiers={},
        )
        wf = models.WorkflowFilter(
            project_types={'api'},
            project_facts={'programming_language': 'Python 3.12'},
            github_identifier_required=True,
        )
        self.assertIsNone(await self.filter.filter_project(project, wf))

    async def test_filter_project_no_filter(self) -> None:
        project = self._create_project()
        result = await self.filter.filter_project(project, None)
        self.assertIsNotNone(result)
        self.assertEqual(result.id, 'proj_123')

    async def test_filter_project_empty_filter(self) -> None:
        project = self._create_project()
        wf = models.WorkflowFilter()
        result = await self.filter.filter_project(project, wf)
        self.assertIsNotNone(result)

    async def test_filter_project_ids_match(self) -> None:
        project = self._create_project(project_id='proj_123')
        wf = models.WorkflowFilter(project_ids={'proj_123', 'proj_456'})
        result = await self.filter.filter_project(project, wf)
        self.assertIsNotNone(result)

    async def test_filter_project_ids_no_match(self) -> None:
        project = self._create_project(project_id='proj_789')
        wf = models.WorkflowFilter(project_ids={'proj_123', 'proj_456'})
        self.assertIsNone(await self.filter.filter_project(project, wf))

    async def test_exclude_project_ids_excluded(self) -> None:
        project = self._create_project(project_id='proj_123')
        wf = models.WorkflowFilter(
            exclude_project_ids={'proj_123', 'proj_456'}
        )
        self.assertIsNone(await self.filter.filter_project(project, wf))

    async def test_exclude_project_ids_not_excluded(self) -> None:
        project = self._create_project(project_id='proj_789')
        wf = models.WorkflowFilter(
            exclude_project_ids={'proj_123', 'proj_456'}
        )
        result = await self.filter.filter_project(project, wf)
        self.assertIsNotNone(result)
        self.assertEqual(result.id, 'proj_789')

    async def test_exclude_project_ids_wins_over_allowlist(self) -> None:
        project = self._create_project(project_id='proj_123')
        wf = models.WorkflowFilter(
            project_ids={'proj_123', 'proj_456'},
            exclude_project_ids={'proj_123'},
        )
        self.assertIsNone(await self.filter.filter_project(project, wf))
