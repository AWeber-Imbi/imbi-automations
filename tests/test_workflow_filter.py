"""Tests for workflow filter."""

import pathlib

from imbi_automations import models, workflow_filter
from tests import base


class WorkflowFilterTestCase(base.AsyncTestCase):
    """Test cases for Filter class."""

    def setUp(self) -> None:
        super().setUp()
        # Create mock configuration
        self.configuration = models.Configuration(
            github=models.GitHubConfiguration(api_key='test-key'),
            imbi=models.ImbiConfiguration(
                api_key='test-key', hostname='imbi.example.com'
            ),
        )

        # Create mock workflow
        self.workflow = models.Workflow(
            path=pathlib.Path('/workflows/test'),
            configuration=models.WorkflowConfiguration(
                name='test-workflow', actions=[]
            ),
        )

        # Create filter instance
        self.filter = workflow_filter.Filter(
            self.configuration, self.workflow, verbose=False
        )

    def test_filter_environments_match_by_name(self) -> None:
        """Test filtering environments by matching name."""
        # Create project with environments
        project = models.ImbiProject(
            id=123,
            dependencies=None,
            description='Test project',
            environments=[
                models.ImbiEnvironment(
                    name='Production', icon_class='fa-prod'
                ),
                models.ImbiEnvironment(name='Staging', icon_class='fa-stage'),
            ],
            facts=None,
            identifiers=None,
            links=None,
            name='test-project',
            namespace='test-namespace',
            namespace_slug='test-namespace',
            project_score=None,
            project_type='API',
            project_type_slug='api',
            slug='test-project',
            urls=None,
            imbi_url='https://imbi.example.com/projects/123',
        )

        # Create filter that matches by name
        wf_filter = models.WorkflowFilter(
            project_environments={'Production', 'Staging'}
        )

        result = self.filter._filter_environments(project, wf_filter)
        self.assertIsNotNone(result)
        self.assertEqual(result.id, 123)

    def test_filter_environments_match_by_slug(self) -> None:
        """Test filtering environments by matching slug."""
        # Create project with environments
        project = models.ImbiProject(
            id=123,
            dependencies=None,
            description='Test project',
            environments=[
                models.ImbiEnvironment(
                    name='Production', icon_class='fa-prod'
                ),
                models.ImbiEnvironment(name='Staging', icon_class='fa-stage'),
            ],
            facts=None,
            identifiers=None,
            links=None,
            name='test-project',
            namespace='test-namespace',
            namespace_slug='test-namespace',
            project_score=None,
            project_type='API',
            project_type_slug='api',
            slug='test-project',
            urls=None,
            imbi_url='https://imbi.example.com/projects/123',
        )

        # Create filter that matches by slug
        wf_filter = models.WorkflowFilter(
            project_environments={'production', 'staging'}
        )

        result = self.filter._filter_environments(project, wf_filter)
        self.assertIsNotNone(result)
        self.assertEqual(result.id, 123)

    def test_filter_environments_no_match(self) -> None:
        """Test filtering environments with no match returns None."""
        # Create project with environments
        project = models.ImbiProject(
            id=123,
            dependencies=None,
            description='Test project',
            environments=[
                models.ImbiEnvironment(
                    name='Production', icon_class='fa-prod'
                ),
                models.ImbiEnvironment(name='Staging', icon_class='fa-stage'),
            ],
            facts=None,
            identifiers=None,
            links=None,
            name='test-project',
            namespace='test-namespace',
            namespace_slug='test-namespace',
            project_score=None,
            project_type='API',
            project_type_slug='api',
            slug='test-project',
            urls=None,
            imbi_url='https://imbi.example.com/projects/123',
        )

        # Create filter that doesn't match
        wf_filter = models.WorkflowFilter(
            project_environments={'development', 'testing'}
        )

        result = self.filter._filter_environments(project, wf_filter)
        self.assertIsNone(result)

    def test_filter_environments_partial_match(self) -> None:
        """Test filtering with partial match returns None."""
        # Create project with environments
        project = models.ImbiProject(
            id=123,
            dependencies=None,
            description='Test project',
            environments=[
                models.ImbiEnvironment(
                    name='Production', icon_class='fa-prod'
                ),
                models.ImbiEnvironment(name='Staging', icon_class='fa-stage'),
            ],
            facts=None,
            identifiers=None,
            links=None,
            name='test-project',
            namespace='test-namespace',
            namespace_slug='test-namespace',
            project_score=None,
            project_type='API',
            project_type_slug='api',
            slug='test-project',
            urls=None,
            imbi_url='https://imbi.example.com/projects/123',
        )

        # Create filter with one matching, one non-matching
        wf_filter = models.WorkflowFilter(
            project_environments={'Production', 'Development'}
        )

        result = self.filter._filter_environments(project, wf_filter)
        self.assertIsNone(result)

    def test_filter_environments_project_no_environments(self) -> None:
        """Test filtering when project has no environments returns None."""
        # Create project without environments
        project = models.ImbiProject(
            id=123,
            dependencies=None,
            description='Test project',
            environments=None,
            facts=None,
            identifiers=None,
            links=None,
            name='test-project',
            namespace='test-namespace',
            namespace_slug='test-namespace',
            project_score=None,
            project_type='API',
            project_type_slug='api',
            slug='test-project',
            urls=None,
            imbi_url='https://imbi.example.com/projects/123',
        )

        wf_filter = models.WorkflowFilter(project_environments={'production'})

        result = self.filter._filter_environments(project, wf_filter)
        self.assertIsNone(result)

    def test_filter_environments_empty_project_environments(self) -> None:
        """Test filtering when project has empty environments list."""
        # Create project with empty environments
        project = models.ImbiProject(
            id=123,
            dependencies=None,
            description='Test project',
            environments=[],
            facts=None,
            identifiers=None,
            links=None,
            name='test-project',
            namespace='test-namespace',
            namespace_slug='test-namespace',
            project_score=None,
            project_type='API',
            project_type_slug='api',
            slug='test-project',
            urls=None,
            imbi_url='https://imbi.example.com/projects/123',
        )

        wf_filter = models.WorkflowFilter(project_environments={'production'})

        result = self.filter._filter_environments(project, wf_filter)
        self.assertIsNone(result)

    def test_filter_environments_mixed_case(self) -> None:
        """Test filtering with mixed case environment names."""
        # Create project with environments
        project = models.ImbiProject(
            id=123,
            dependencies=None,
            description='Test project',
            environments=[
                models.ImbiEnvironment(
                    name='Production', icon_class='fa-prod'
                ),
                models.ImbiEnvironment(
                    name='Testing Environment', icon_class='fa-test'
                ),
            ],
            facts=None,
            identifiers=None,
            links=None,
            name='test-project',
            namespace='test-namespace',
            namespace_slug='test-namespace',
            project_score=None,
            project_type='API',
            project_type_slug='api',
            slug='test-project',
            urls=None,
            imbi_url='https://imbi.example.com/projects/123',
        )

        # Filter using slug for one, name for another
        wf_filter = models.WorkflowFilter(
            project_environments={'production', 'Testing Environment'}
        )

        result = self.filter._filter_environments(project, wf_filter)
        self.assertIsNotNone(result)
        self.assertEqual(result.id, 123)
