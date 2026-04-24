"""Tests for the Jira Cloud client."""

import base64
import http
import json

import httpx

from imbi_automations import models
from imbi_automations.clients import jira
from tests import base


class TestJiraClient(base.AsyncTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.config = models.JiraConfiguration(
            domain='example.atlassian.net',
            email='tester@example.com',
            api_key='abc123',  # noqa: S106
        )
        self.instance = jira.Jira(self.config, self.http_client_transport)

    async def test_auth_header_is_basic_email_and_token(self) -> None:
        expected = base64.b64encode(b'tester@example.com:abc123').decode()
        self.assertEqual(
            self.instance.http_client.headers['Authorization'],
            f'Basic {expected}',
        )

    async def test_base_url_derived_from_domain(self) -> None:
        self.assertEqual(
            self.instance.base_url, 'https://example.atlassian.net'
        )

    async def test_browse_url_format(self) -> None:
        self.assertEqual(
            self.instance.browse_url('SEC-42'),
            'https://example.atlassian.net/browse/SEC-42',
        )

    async def test_create_issue_minimal_payload(self) -> None:
        captured: dict[str, httpx.Request] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured['request'] = request
            return httpx.Response(
                http.HTTPStatus.CREATED,
                request=request,
                json={
                    'id': '10001',
                    'key': 'SEC-1',
                    'self': (
                        'https://example.atlassian.net/rest/api/3/issue/10001'
                    ),
                },
            )

        transport = httpx.MockTransport(handler)
        client = jira.Jira(self.config, transport)

        issue = await client.create_issue(
            project_key='SEC', summary='Summary here', issue_type='Task'
        )

        self.assertEqual(issue.key, 'SEC-1')
        self.assertEqual(issue.id, '10001')

        request = captured['request']
        self.assertEqual(request.method, 'POST')
        self.assertEqual(request.url.path, '/rest/api/3/issue')
        body = json.loads(request.content)
        self.assertEqual(body['fields']['project']['key'], 'SEC')
        self.assertEqual(body['fields']['summary'], 'Summary here')
        self.assertEqual(body['fields']['issuetype']['name'], 'Task')
        self.assertNotIn('description', body['fields'])
        self.assertNotIn('labels', body['fields'])
        self.assertNotIn('components', body['fields'])

    async def test_create_issue_wraps_description_as_adf(self) -> None:
        captured: dict[str, httpx.Request] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured['request'] = request
            return httpx.Response(
                http.HTTPStatus.CREATED,
                request=request,
                json={
                    'id': '2',
                    'key': 'SEC-2',
                    'self': (
                        'https://example.atlassian.net/rest/api/3/issue/2'
                    ),
                },
            )

        client = jira.Jira(self.config, httpx.MockTransport(handler))
        await client.create_issue(
            project_key='SEC',
            summary='S',
            description='Para one.\n\nPara two line1\nPara two line2',
        )

        body = json.loads(captured['request'].content)
        adf = body['fields']['description']
        self.assertEqual(adf['type'], 'doc')
        self.assertEqual(adf['version'], 1)
        self.assertEqual(len(adf['content']), 2)
        para1, para2 = adf['content']
        self.assertEqual(
            para1['content'], [{'type': 'text', 'text': 'Para one.'}]
        )
        # Second paragraph contains a hardBreak between the two lines.
        self.assertEqual(
            para2['content'],
            [
                {'type': 'text', 'text': 'Para two line1'},
                {'type': 'hardBreak'},
                {'type': 'text', 'text': 'Para two line2'},
            ],
        )

    async def test_create_issue_labels_components_priority(self) -> None:
        captured: dict[str, httpx.Request] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured['request'] = request
            return httpx.Response(
                http.HTTPStatus.CREATED,
                request=request,
                json={
                    'id': '3',
                    'key': 'SEC-3',
                    'self': (
                        'https://example.atlassian.net/rest/api/3/issue/3'
                    ),
                },
            )

        client = jira.Jira(self.config, httpx.MockTransport(handler))
        await client.create_issue(
            project_key='SEC',
            summary='S',
            labels=['security-review', 'automated'],
            components=['AppSec', 'Platform'],
            priority='High',
        )

        fields = json.loads(captured['request'].content)['fields']
        self.assertEqual(fields['labels'], ['security-review', 'automated'])
        self.assertEqual(
            fields['components'], [{'name': 'AppSec'}, {'name': 'Platform'}]
        )
        self.assertEqual(fields['priority'], {'name': 'High'})

    async def test_create_issue_raises_on_4xx(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                http.HTTPStatus.BAD_REQUEST,
                request=request,
                json={'errorMessages': ['project key invalid']},
            )

        client = jira.Jira(self.config, httpx.MockTransport(handler))
        with self.assertRaises(httpx.HTTPStatusError):
            await client.create_issue(
                project_key='NOPE', summary='x', issue_type='Task'
            )


class TestMarkdownToADF(base.AsyncTestCase):
    async def test_blank_input_produces_single_empty_paragraph(self) -> None:
        adf = jira._markdown_to_adf('')
        self.assertEqual(
            adf,
            {
                'type': 'doc',
                'version': 1,
                'content': [{'type': 'paragraph', 'content': []}],
            },
        )
