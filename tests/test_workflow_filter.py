"""Tests for workflow filter."""

import pathlib
import typing

from imbi_automations import models, workflow_filter
from tests import base


def make_project(
    project_id: str = 'proj_123',
    *,
    slug: str = 'test-project',
    name: str = 'test-project',
    team_slug: str = 'platform',
    project_type_slugs: tuple[str, ...] = ('api',),
    environments: list[models.ImbiEnvironment] | None = None,
    links: dict[str, str] | None = None,
    identifiers: dict[str, int | str] | None = None,
    extras: dict[str, typing.Any] | None = None,
) -> models.ImbiProject:
    """Build an :class:`ImbiProject` populated with sensible v2 defaults."""
    payload: dict[str, typing.Any] = {
        'id': project_id,
        'name': name,
        'slug': slug,
        'team': {'name': team_slug.title(), 'slug': team_slug},
        'project_types': [
            {'name': pt.title(), 'slug': pt} for pt in project_type_slugs
        ],
        'environments': [env.model_dump() for env in environments or []],
        'links': links or {},
        'identifiers': identifiers or {},
    }
    if extras:
        payload.update(extras)
    return models.ImbiProject.model_validate(payload)


PROD = models.ImbiEnvironment(name='Production', slug='production')
STAGE = models.ImbiEnvironment(name='Staging', slug='staging')
TEST_ENV = models.ImbiEnvironment(
    name='Testing Environment', slug='testing-environment'
)


class WorkflowFilterTestCase(base.AsyncTestCase):
    """Test cases for :class:`workflow_filter.Filter`."""

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

    def test_filter_environments_match_by_name(self) -> None:
        project = make_project(environments=[PROD, STAGE])
        wf = models.WorkflowFilter(
            project_environments={'Production', 'Staging'}
        )
        result = self.filter._filter_environments(project, wf)
        self.assertIsNotNone(result)
        self.assertEqual(result.id, 'proj_123')

    def test_filter_environments_match_by_slug(self) -> None:
        project = make_project(environments=[PROD, STAGE])
        wf = models.WorkflowFilter(
            project_environments={'production', 'staging'}
        )
        result = self.filter._filter_environments(project, wf)
        self.assertIsNotNone(result)

    def test_filter_environments_no_match(self) -> None:
        project = make_project(environments=[PROD, STAGE])
        wf = models.WorkflowFilter(
            project_environments={'development', 'testing'}
        )
        self.assertIsNone(self.filter._filter_environments(project, wf))

    def test_filter_environments_partial_match(self) -> None:
        project = make_project(environments=[PROD, STAGE])
        wf = models.WorkflowFilter(
            project_environments={'Production', 'Development'}
        )
        self.assertIsNone(self.filter._filter_environments(project, wf))

    def test_filter_environments_project_no_environments(self) -> None:
        project = make_project()
        wf = models.WorkflowFilter(project_environments={'production'})
        self.assertIsNone(self.filter._filter_environments(project, wf))

    def test_filter_environments_empty_project_environments(self) -> None:
        project = make_project(environments=[])
        wf = models.WorkflowFilter(project_environments={'production'})
        self.assertIsNone(self.filter._filter_environments(project, wf))

    def test_filter_environments_mixed_case(self) -> None:
        project = make_project(environments=[PROD, TEST_ENV])
        wf = models.WorkflowFilter(
            project_environments={'production', 'Testing Environment'}
        )
        result = self.filter._filter_environments(project, wf)
        self.assertIsNotNone(result)

    async def test_github_identifier_required_no_identifiers(self) -> None:
        project = make_project(identifiers={})
        wf = models.WorkflowFilter(github_identifier_required=True)
        self.assertIsNone(await self.filter.filter_project(project, wf))

    async def test_github_identifier_required_empty_identifiers(self) -> None:
        project = make_project(identifiers={})
        wf = models.WorkflowFilter(github_identifier_required=True)
        self.assertIsNone(await self.filter.filter_project(project, wf))

    async def test_github_identifier_required_missing_github(self) -> None:
        project = make_project(identifiers={'gitlab': 'some-org/some-repo'})
        wf = models.WorkflowFilter(github_identifier_required=True)
        self.assertIsNone(await self.filter.filter_project(project, wf))

    async def test_github_identifier_required_has_github(self) -> None:
        project = make_project(identifiers={'github': 'some-org/some-repo'})
        wf = models.WorkflowFilter(github_identifier_required=True)
        result = await self.filter.filter_project(project, wf)
        self.assertIsNotNone(result)
        self.assertEqual(result.id, 'proj_123')
