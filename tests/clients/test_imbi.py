"""Tests for the Imbi API client."""

import base64
import http
import json
import time
import typing
import unittest

import httpx

from imbi_automations import models
from imbi_automations.clients import http as ia_http
from imbi_automations.clients import imbi
from tests import base

BASE = 'https://imbi.test.com'
ORG = 'test-org'
ORG_BASE = f'{BASE}/api/organizations/{ORG}'


def _make_jwt(*, exp_offset: int = 900) -> str:
    """Return an unsigned JWT with the given exp offset (seconds from now)."""

    def _b64(payload: dict[str, typing.Any]) -> str:
        return (
            base64.urlsafe_b64encode(json.dumps(payload).encode('utf-8'))
            .rstrip(b'=')
            .decode('ascii')
        )

    header = _b64({'alg': 'none', 'typ': 'JWT'})
    claims = _b64({'exp': int(time.time()) + exp_offset})
    return f'{header}.{claims}.'


def project_payload(
    project_id: str = 'proj_abc',
    *,
    slug: str = 'test-project',
    name: str = 'Test Project',
    team_slug: str = 'platform',
    project_type_slugs: list[str] | None = None,
    environments: list[str] | None = None,
    links: dict[str, str] | None = None,
    identifiers: dict[str, int | str] | None = None,
    extras: dict[str, typing.Any] | None = None,
    description: str | None = None,
) -> dict[str, typing.Any]:
    """Build a v2 ProjectResponse-shaped dict."""
    if project_type_slugs is None:
        project_type_slugs = ['api']
    payload: dict[str, typing.Any] = {
        'id': project_id,
        'name': name,
        'slug': slug,
        'description': description,
        'team': {
            'id': 'team_xyz',
            'name': team_slug.title(),
            'slug': team_slug,
        },
        'project_types': [
            {'id': f'pt_{slug}', 'name': slug.title(), 'slug': slug}
            for slug in project_type_slugs
        ],
        'environments': [
            {'id': f'env_{slug}', 'name': slug.title(), 'slug': slug}
            for slug in (environments or [])
        ],
        'links': links or {},
        'identifiers': identifiers or {},
    }
    if extras:
        payload.update(extras)
    return payload


class _Recorder:
    """httpx mock that records each request and returns canned responses."""

    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError(
                f'unexpected request: {request.method} {request.url}'
            )
        return self._responses.pop(0)


def _resp(
    status: int, *, json_body: typing.Any = None, text: str | None = None
) -> httpx.Response:
    if json_body is None and text is None:
        return httpx.Response(status)
    if json_body is not None:
        return httpx.Response(status, json=json_body)
    return httpx.Response(status, text=text or '')


class ImbiClientAuthTestCase(base.AsyncTestCase):
    """Auth flows: api-key, refresh-on-401, client_credentials."""

    def setUp(self) -> None:
        super().setUp()
        self.api_key_config = models.ImbiConfiguration(
            organization=ORG, base_url=BASE, api_key='ik_secret'
        )
        self.password_config = models.ImbiConfiguration(
            organization=ORG,
            base_url=BASE,
            auth=models.ImbiPasswordAuth(
                email='user@test.com',
                password='hunter2',  # noqa: S106
            ),
        )

    async def test_api_key_is_sent_as_bearer_token(self) -> None:
        recorder = _Recorder([_resp(http.HTTPStatus.OK, json_body=[])])
        transport = httpx.MockTransport(recorder)
        client = imbi.Imbi(self.api_key_config, transport)
        await client.get_environments()
        self.assertEqual(len(recorder.requests), 1)
        request = recorder.requests[0]
        self.assertEqual(
            request.headers.get('Authorization'), 'Bearer ik_secret'
        )
        self.assertEqual(str(request.url), f'{ORG_BASE}/environments/')

    async def test_password_login_exchange_then_request(self) -> None:
        access_token = _make_jwt()
        recorder = _Recorder(
            [
                _resp(
                    http.HTTPStatus.OK,
                    json_body={
                        'access_token': access_token,
                        'refresh_token': 'refresh-1',
                        'token_type': 'bearer',
                    },
                ),
                _resp(http.HTTPStatus.OK, json_body=[]),
            ]
        )
        transport = httpx.MockTransport(recorder)
        client = imbi.Imbi(self.password_config, transport)
        await client.get_project_types()
        self.assertEqual(len(recorder.requests), 2)
        login = recorder.requests[0]
        self.assertEqual(login.method, 'POST')
        self.assertEqual(str(login.url), f'{BASE}/api/auth/login')
        body = json.loads(login.content)
        self.assertEqual(body['email'], 'user@test.com')
        self.assertEqual(body['password'], 'hunter2')
        api_call = recorder.requests[1]
        self.assertEqual(
            api_call.headers['Authorization'], f'Bearer {access_token}'
        )

    async def test_refresh_on_401_then_retry(self) -> None:
        first_access = _make_jwt()
        second_access = _make_jwt()
        recorder = _Recorder(
            [
                _resp(  # login
                    http.HTTPStatus.OK,
                    json_body={
                        'access_token': first_access,
                        'refresh_token': 'refresh-1',
                        'token_type': 'bearer',
                    },
                ),
                _resp(http.HTTPStatus.UNAUTHORIZED),  # request 1
                _resp(  # refresh
                    http.HTTPStatus.OK,
                    json_body={
                        'access_token': second_access,
                        'refresh_token': 'refresh-2',
                        'token_type': 'bearer',
                    },
                ),
                _resp(http.HTTPStatus.OK, json_body=[]),  # request retry
            ]
        )
        transport = httpx.MockTransport(recorder)
        client = imbi.Imbi(self.password_config, transport)
        await client.get_environments()
        self.assertEqual(len(recorder.requests), 4)
        # refresh request uses the refresh token
        refresh = recorder.requests[2]
        self.assertEqual(str(refresh.url), f'{BASE}/api/auth/token/refresh')
        self.assertEqual(
            json.loads(refresh.content)['refresh_token'], 'refresh-1'
        )
        # retried request uses the new access token
        self.assertEqual(
            recorder.requests[3].headers['Authorization'],
            f'Bearer {second_access}',
        )

    async def test_api_key_401_does_not_attempt_refresh(self) -> None:
        recorder = _Recorder(
            [_resp(http.HTTPStatus.UNAUTHORIZED, text='nope')]
        )
        transport = httpx.MockTransport(recorder)
        client = imbi.Imbi(self.api_key_config, transport)
        with self.assertRaises(httpx.HTTPStatusError):
            await client.get_environments()
        self.assertEqual(len(recorder.requests), 1)


class ImbiClientReadsTestCase(base.AsyncTestCase):
    """Reads: environments, project types, link defs, projects, schema."""

    def setUp(self) -> None:
        super().setUp()
        self.config = models.ImbiConfiguration(
            organization=ORG, base_url=BASE, api_key='ik_test'
        )

    def _client(
        self, responses: list[httpx.Response]
    ) -> tuple[imbi.Imbi, _Recorder]:
        recorder = _Recorder(responses)
        transport = httpx.MockTransport(recorder)
        return imbi.Imbi(self.config, transport), recorder

    async def test_get_environments(self) -> None:
        client, recorder = self._client(
            [
                _resp(
                    http.HTTPStatus.OK,
                    json_body=[
                        {'name': 'Prod', 'slug': 'production'},
                        {'name': 'Stage', 'slug': 'staging'},
                    ],
                )
            ]
        )
        envs = await client.get_environments()
        self.assertEqual([e.slug for e in envs], ['production', 'staging'])
        self.assertEqual(
            str(recorder.requests[0].url), f'{ORG_BASE}/environments/'
        )

    async def test_get_project_types(self) -> None:
        client, _ = self._client(
            [
                _resp(
                    http.HTTPStatus.OK,
                    json_body=[
                        {'name': 'API', 'slug': 'api'},
                        {'name': 'Consumer', 'slug': 'consumer'},
                    ],
                )
            ]
        )
        types = await client.get_project_types()
        self.assertEqual({t.slug for t in types}, {'api', 'consumer'})

    async def test_get_link_definitions(self) -> None:
        client, _ = self._client(
            [
                _resp(
                    http.HTTPStatus.OK,
                    json_body=[
                        {
                            'name': 'GitHub Repository',
                            'slug': 'github-repository',
                            'url_template': None,
                        }
                    ],
                )
            ]
        )
        defs = await client.get_link_definitions()
        self.assertEqual(defs[0].slug, 'github-repository')

    async def test_get_project_returns_typed_model(self) -> None:
        payload = project_payload(
            project_id='proj_x', extras={'programming_language': 'Python 3.12'}
        )
        client, _ = self._client(
            [_resp(http.HTTPStatus.OK, json_body=payload)]
        )
        project = await client.get_project('proj_x')
        self.assertIsNotNone(project)
        self.assertEqual(project.id, 'proj_x')
        self.assertEqual(project.team.slug, 'platform')
        self.assertEqual([pt.slug for pt in project.project_types], ['api'])
        self.assertEqual(
            project.model_extra.get('programming_language'), 'Python 3.12'
        )

    async def test_get_project_404_returns_none(self) -> None:
        client, _ = self._client(
            [_resp(http.HTTPStatus.NOT_FOUND, text='nope')]
        )
        self.assertIsNone(await client.get_project('proj_missing'))

    async def test_get_projects_sorts_by_slug(self) -> None:
        client, recorder = self._client(
            [
                _resp(
                    http.HTTPStatus.OK,
                    json_body=[
                        project_payload(project_id='2', slug='z-svc'),
                        project_payload(project_id='1', slug='a-svc'),
                    ],
                )
            ]
        )
        projects = await client.get_projects()
        self.assertEqual([p.slug for p in projects], ['a-svc', 'z-svc'])
        self.assertEqual(
            str(recorder.requests[0].url), f'{ORG_BASE}/projects/'
        )

    async def test_get_projects_by_type_passes_filter(self) -> None:
        client, recorder = self._client(
            [_resp(http.HTTPStatus.OK, json_body=[])]
        )
        await client.get_projects_by_type('api')
        url = recorder.requests[0].url
        self.assertEqual(str(url.path), f'/api/organizations/{ORG}/projects/')
        self.assertEqual(url.params.get('project_type'), 'api')

    async def test_search_projects_by_github_url_filters_client_side(
        self,
    ) -> None:
        client, _ = self._client(
            [
                _resp(
                    http.HTTPStatus.OK,
                    json_body=[
                        project_payload(
                            project_id='1',
                            slug='match',
                            links={
                                'github-repository': (
                                    'https://github.com/org/match'
                                )
                            },
                        ),
                        project_payload(
                            project_id='2',
                            slug='no-match',
                            links={
                                'github-repository': (
                                    'https://github.com/org/other'
                                )
                            },
                        ),
                    ],
                )
            ]
        )
        result = await client.search_projects_by_github_url(
            'https://github.com/org/match'
        )
        self.assertEqual([p.slug for p in result], ['match'])

    async def test_get_project_schema(self) -> None:
        client, recorder = self._client(
            [
                _resp(
                    http.HTTPStatus.OK,
                    json_body={
                        'sections': [
                            {
                                'name': 'Tech',
                                'slug': 'tech',
                                'properties': {
                                    'programming_language': {
                                        'type': 'string',
                                        'enum': ['Python 3.12', 'Go 1.22'],
                                    }
                                },
                            }
                        ]
                    },
                )
            ]
        )
        schema = await client.get_project_schema('proj_x')
        self.assertEqual(schema.property_keys(), {'programming_language'})
        self.assertEqual(
            str(recorder.requests[0].url), f'{ORG_BASE}/projects/proj_x/schema'
        )


class ImbiClientPatchesTestCase(base.AsyncTestCase):
    """JSON Patch shapes for attribute / link / identifier / type / env."""

    def setUp(self) -> None:
        super().setUp()
        self.config = models.ImbiConfiguration(
            organization=ORG, base_url=BASE, api_key='ik_test'
        )

    def _client(
        self, responses: list[httpx.Response]
    ) -> tuple[imbi.Imbi, _Recorder]:
        recorder = _Recorder(responses)
        transport = httpx.MockTransport(recorder)
        return imbi.Imbi(self.config, transport), recorder

    def _patch_ops(
        self, request: httpx.Request
    ) -> list[dict[str, typing.Any]]:
        self.assertEqual(request.method, 'PATCH')
        return json.loads(request.content)

    async def test_set_project_attribute_replaces_existing_value(self) -> None:
        project = project_payload(
            project_id='proj_x', extras={'programming_language': 'Python 3.11'}
        )
        updated = project_payload(
            project_id='proj_x', extras={'programming_language': 'Python 3.12'}
        )
        client, recorder = self._client(
            [
                _resp(http.HTTPStatus.OK, json_body=project),  # GET
                _resp(http.HTTPStatus.OK, json_body=updated),  # PATCH
            ]
        )
        changed = await client.set_project_attribute(
            'proj_x', 'programming_language', 'Python 3.12'
        )
        self.assertTrue(changed)
        ops = self._patch_ops(recorder.requests[1])
        self.assertEqual(
            ops,
            [
                {
                    'op': 'replace',
                    'path': '/programming_language',
                    'value': 'Python 3.12',
                }
            ],
        )

    async def test_set_project_attribute_skips_when_unchanged(self) -> None:
        project = project_payload(
            project_id='proj_x', extras={'programming_language': 'Python 3.12'}
        )
        client, recorder = self._client(
            [_resp(http.HTTPStatus.OK, json_body=project)]
        )
        changed = await client.set_project_attribute(
            'proj_x', 'programming_language', 'Python 3.12'
        )
        self.assertFalse(changed)
        self.assertEqual(len(recorder.requests), 1)  # no PATCH

    async def test_set_project_attribute_remove_when_value_is_none(
        self,
    ) -> None:
        project = project_payload(
            project_id='proj_x', extras={'programming_language': 'Python 3.12'}
        )
        client, recorder = self._client(
            [
                _resp(http.HTTPStatus.OK, json_body=project),
                _resp(
                    http.HTTPStatus.OK,
                    json_body=project_payload(project_id='proj_x'),
                ),
            ]
        )
        changed = await client.set_project_attribute(
            'proj_x', 'programming_language', None
        )
        self.assertTrue(changed)
        ops = self._patch_ops(recorder.requests[1])
        self.assertEqual(
            ops, [{'op': 'remove', 'path': '/programming_language'}]
        )

    async def test_add_project_link_uses_link_definition_slug(self) -> None:
        project = project_payload(project_id='proj_x')
        defs = [
            {
                'name': 'GitHub Repository',
                'slug': 'github-repository',
                'url_template': None,
            }
        ]
        client, recorder = self._client(
            [
                _resp(http.HTTPStatus.OK, json_body=defs),  # link definitions
                _resp(http.HTTPStatus.OK, json_body=project),  # GET project
                _resp(http.HTTPStatus.OK, json_body=project),  # PATCH response
            ]
        )
        changed = await client.add_project_link(
            'proj_x', 'github-repository', 'https://github.com/org/repo'
        )
        self.assertTrue(changed)
        ops = self._patch_ops(recorder.requests[2])
        self.assertEqual(
            ops,
            [
                {
                    'op': 'add',
                    'path': '/links/github-repository',
                    'value': 'https://github.com/org/repo',
                }
            ],
        )

    async def test_add_project_link_rejects_unknown_slug(self) -> None:
        client, _ = self._client([_resp(http.HTTPStatus.OK, json_body=[])])
        with self.assertRaises(ValueError):
            await client.add_project_link('proj_x', 'unknown', 'https://x')

    async def test_set_project_identifier_add(self) -> None:
        project = project_payload(project_id='proj_x', identifiers={})
        client, recorder = self._client(
            [
                _resp(http.HTTPStatus.OK, json_body=project),
                _resp(http.HTTPStatus.OK, json_body=project),
            ]
        )
        await client.set_project_identifier('proj_x', 'github', 12345)
        ops = self._patch_ops(recorder.requests[1])
        self.assertEqual(
            ops, [{'op': 'add', 'path': '/identifiers/github', 'value': 12345}]
        )

    async def test_set_project_identifier_replace(self) -> None:
        project = project_payload(
            project_id='proj_x', identifiers={'github': 999}
        )
        client, recorder = self._client(
            [
                _resp(http.HTTPStatus.OK, json_body=project),
                _resp(http.HTTPStatus.OK, json_body=project),
            ]
        )
        await client.set_project_identifier('proj_x', 'github', 12345)
        ops = self._patch_ops(recorder.requests[1])
        self.assertEqual(
            ops,
            [{'op': 'replace', 'path': '/identifiers/github', 'value': 12345}],
        )

    async def test_set_project_identifier_remove(self) -> None:
        project = project_payload(
            project_id='proj_x', identifiers={'github': 999}
        )
        client, recorder = self._client(
            [
                _resp(http.HTTPStatus.OK, json_body=project),
                _resp(http.HTTPStatus.OK, json_body=project),
            ]
        )
        await client.set_project_identifier('proj_x', 'github', None)
        ops = self._patch_ops(recorder.requests[1])
        self.assertEqual(
            ops, [{'op': 'remove', 'path': '/identifiers/github'}]
        )

    async def test_set_project_types_replaces_full_list(self) -> None:
        project = project_payload(
            project_id='proj_x', project_type_slugs=['api']
        )
        client, recorder = self._client(
            [
                _resp(http.HTTPStatus.OK, json_body=project),
                _resp(http.HTTPStatus.OK, json_body=project),
            ]
        )
        await client.set_project_types('proj_x', ['api', 'cli'])
        ops = self._patch_ops(recorder.requests[1])
        self.assertEqual(
            ops,
            [
                {
                    'op': 'replace',
                    'path': '/project_type_slugs',
                    'value': ['api', 'cli'],
                }
            ],
        )

    async def test_set_project_types_skips_when_unchanged(self) -> None:
        project = project_payload(
            project_id='proj_x', project_type_slugs=['api', 'cli']
        )
        client, recorder = self._client(
            [_resp(http.HTTPStatus.OK, json_body=project)]
        )
        changed = await client.set_project_types('proj_x', ['api', 'cli'])
        self.assertFalse(changed)
        self.assertEqual(len(recorder.requests), 1)

    async def test_set_project_environments_emits_add_and_remove(self) -> None:
        project = project_payload(
            project_id='proj_x', environments=['production', 'staging']
        )
        client, recorder = self._client(
            [
                _resp(http.HTTPStatus.OK, json_body=project),
                _resp(http.HTTPStatus.OK, json_body=project),
            ]
        )
        changed = await client.set_project_environments(
            'proj_x', ['production', 'testing']
        )
        self.assertTrue(changed)
        ops = self._patch_ops(recorder.requests[1])
        self.assertEqual(
            ops,
            [
                {'op': 'add', 'path': '/environments/testing', 'value': {}},
                {'op': 'remove', 'path': '/environments/staging'},
            ],
        )

    async def test_add_project_document(self) -> None:
        client, recorder = self._client(
            [
                _resp(
                    http.HTTPStatus.CREATED,
                    json_body={
                        'id': 'doc_x',
                        'title': 'Release Notes',
                        'content': 'body',
                        'created_by': 'gavinr',
                        'created_at': '2026-05-11T00:00:00+00:00',
                        'project_id': 'proj_x',
                        'is_pinned': False,
                        'tags': [],
                    },
                )
            ]
        )
        document = await client.add_project_document(
            'proj_x', 'Release Notes', 'body', tags=['release']
        )
        self.assertEqual(document.id, 'doc_x')
        request = recorder.requests[0]
        self.assertEqual(request.method, 'POST')
        self.assertEqual(
            str(request.url), f'{ORG_BASE}/projects/proj_x/documents/'
        )
        body = json.loads(request.content)
        self.assertEqual(body['title'], 'Release Notes')
        self.assertEqual(body['content'], 'body')
        self.assertEqual(body['tags'], ['release'])


class ImbiClientInheritanceTestCase(base.AsyncTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.config = models.ImbiConfiguration(
            organization=ORG, base_url=BASE, api_key='ik_test'
        )

    def test_imbi_inherits_from_base_url_client(self) -> None:
        client = imbi.Imbi(self.config)
        self.assertIsInstance(client, ia_http.BaseURLHTTPClient)


if __name__ == '__main__':
    unittest.main()
