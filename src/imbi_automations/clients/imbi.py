"""Imbi API client.

Targets the org-scoped Imbi API. Authenticates via API key
(``Bearer ik_…``), OAuth2 client credentials, or password login;
JWTs are refreshed transparently on 401. Project mutations are
expressed as RFC 6902 JSON Patch.
"""

from __future__ import annotations

import base64
import datetime
import json
import logging
import typing

import async_lru
import httpx

from imbi_automations import models

from . import http

LOGGER = logging.getLogger(__name__)

_TOKEN_SKEW = datetime.timedelta(seconds=30)

# Mirrors imbi-api's ``projects._RESERVED_FIELDS`` plus the two
# response-only fields (``score``, ``relationships``) the server
# never accepts on a PATCH. Fields with dedicated setters
# (``/team``, ``/project_types``, ``/environments``) live here so
# misuse of the attribute-PATCH path raises locally rather than
# round-tripping a 400.
_DOC_PATH_RESERVED = frozenset(
    [
        '/id',
        '/team',
        '/project_types',
        '/environments',
        '/created_at',
        '/updated_at',
        '/archived',
        '/archived_at',
        '/score',
        '/relationships',
    ]
)


def _patch_op(
    path: str, current: typing.Any, value: typing.Any
) -> dict[str, typing.Any] | None:
    """Return a single JSON Patch op, or ``None`` when no change is needed.

    ``value=None`` means "remove". ``current=None`` (with a non-None
    ``value``) becomes ``add``; otherwise ``replace``.
    """
    if value is None:
        if current is None:
            return None
        return {'op': 'remove', 'path': path}
    if current == value:
        return None
    op = 'replace' if current is not None else 'add'
    return {'op': op, 'path': path, 'value': value}


def _decode_jwt_exp(token: str) -> datetime.datetime | None:
    """Return the JWT's ``exp`` claim as an aware UTC datetime."""
    try:
        _, payload_b64, _ = token.split('.')
    except ValueError:
        return None
    padding = '=' * (-len(payload_b64) % 4)
    try:
        payload = json.loads(
            base64.urlsafe_b64decode(payload_b64 + padding).decode('utf-8')
        )
    except (ValueError, UnicodeDecodeError):
        return None
    exp = payload.get('exp')
    if not isinstance(exp, (int, float)):
        return None
    return datetime.datetime.fromtimestamp(float(exp), tz=datetime.UTC)


class _AuthManager:
    """Issues and refreshes the Imbi access token."""

    def __init__(
        self, client: httpx.AsyncClient, base_url: str, auth: models.ImbiAuth
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip('/')
        self._auth = auth
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._exp: datetime.datetime | None = None

    @property
    def static_api_key(self) -> str | None:
        """Return the raw API key when using ``api_key`` auth, else None."""
        if isinstance(self._auth, models.ImbiApiKeyAuth):
            return self._auth.value.get_secret_value()
        return None

    def _is_expired(self) -> bool:
        if self._exp is None:
            return True
        now = datetime.datetime.now(datetime.UTC)
        return now + _TOKEN_SKEW >= self._exp

    async def access_token(self) -> str:
        """Return a usable access token, fetching one if needed."""
        key = self.static_api_key
        if key is not None:
            return key
        if self._access_token and not self._is_expired():
            return self._access_token
        await self._issue()
        return typing.cast('str', self._access_token)

    async def refresh(self) -> str:
        """Force a refresh and return the new access token."""
        if self.static_api_key is not None:
            return self.static_api_key
        if self._refresh_token:
            try:
                await self._refresh()
                return typing.cast('str', self._access_token)
            except httpx.HTTPStatusError:
                LOGGER.debug('Imbi refresh token rejected, re-authenticating')
        await self._issue()
        return typing.cast('str', self._access_token)

    async def _issue(self) -> None:
        if isinstance(self._auth, models.ImbiClientCredentialsAuth):
            response = await self._client.post(
                f'{self._base_url}/api/auth/token',
                data={
                    'grant_type': 'client_credentials',
                    'client_id': self._auth.client_id.get_secret_value(),
                    'client_secret': (
                        self._auth.client_secret.get_secret_value()
                    ),
                },
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
            )
        elif isinstance(self._auth, models.ImbiPasswordAuth):
            response = await self._client.post(
                f'{self._base_url}/api/auth/login',
                json={
                    'email': self._auth.email,
                    'password': self._auth.password.get_secret_value(),
                },
            )
        else:
            raise RuntimeError(
                f'Unsupported Imbi auth mode: {type(self._auth).__name__}'
            )
        response.raise_for_status()
        self._store(response.json())

    async def _refresh(self) -> None:
        response = await self._client.post(
            f'{self._base_url}/api/auth/token/refresh',
            json={'refresh_token': self._refresh_token},
        )
        response.raise_for_status()
        self._store(response.json())

    def _store(self, payload: dict[str, typing.Any]) -> None:
        access = payload.get('access_token')
        if not isinstance(access, str):
            raise RuntimeError('Imbi auth response missing access_token')
        self._access_token = access
        refresh = payload.get('refresh_token')
        if isinstance(refresh, str):
            self._refresh_token = refresh
        self._exp = _decode_jwt_exp(access)


class Imbi(http.BaseURLHTTPClient):
    """Imbi API client.

    All requests are scoped to a single organization. Path prefix
    ``/api/organizations/{org_slug}`` is added automatically; only
    auth endpoints (``/api/auth/...``) bypass the org scope.
    """

    def __init__(
        self,
        config: models.ImbiConfiguration,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(transport=transport)
        self._base_url = str(config.base_url).rstrip('/')
        self._org_slug = config.organization
        self._config = config
        if config.auth is None:
            raise RuntimeError('ImbiConfiguration is missing an auth block')
        self._auth_manager = _AuthManager(
            self.http_client, self._base_url, config.auth
        )

    @property
    def org_slug(self) -> str:
        """Return the org slug this client is bound to."""
        return self._org_slug

    @property
    def org_base(self) -> str:
        """Return the URL prefix for every org-scoped endpoint."""
        return f'{self._base_url}/api/organizations/{self._org_slug}'

    async def _request(
        self, method: str, path: str, **kwargs: typing.Any
    ) -> httpx.Response:
        """Issue an HTTP request with bearer auth + one 401-refresh retry."""
        url = self._url_for(path)
        token = await self._auth_manager.access_token()
        headers = dict(kwargs.pop('headers', None) or {})
        headers['Authorization'] = f'Bearer {token}'
        response = await self.http_client.request(
            method, url, headers=headers, **kwargs
        )
        if response.status_code != 401 or self._auth_manager.static_api_key:
            return response
        token = await self._auth_manager.refresh()
        headers['Authorization'] = f'Bearer {token}'
        return await self.http_client.request(
            method, url, headers=headers, **kwargs
        )

    def _url_for(self, path: str) -> str:
        if path.startswith(('http://', 'https://')):
            return path
        if path.startswith('/api/'):
            return f'{self._base_url}{path}'
        return f'{self.org_base}/{path.lstrip("/")}'

    # -- Reads ----------------------------------------------------------

    @async_lru.alru_cache(maxsize=1)
    async def get_environments(self) -> list[models.ImbiEnvironment]:
        """List environments defined for the organization."""
        response = await self._request('GET', 'environments/')
        response.raise_for_status()
        return [
            models.ImbiEnvironment.model_validate(entry)
            for entry in response.json()
        ]

    @async_lru.alru_cache(maxsize=1)
    async def get_project_types(self) -> list[models.ImbiProjectType]:
        """List project types defined for the organization."""
        response = await self._request('GET', 'project-types/')
        response.raise_for_status()
        return [
            models.ImbiProjectType.model_validate(entry)
            for entry in response.json()
        ]

    @async_lru.alru_cache(maxsize=1)
    async def get_link_definitions(self) -> list[models.ImbiLinkDefinition]:
        """List link definitions defined for the organization."""
        response = await self._request('GET', 'link-definitions/')
        response.raise_for_status()
        return [
            models.ImbiLinkDefinition.model_validate(entry)
            for entry in response.json()
        ]

    async def get_project(self, project_id: str) -> models.ImbiProject | None:
        """Fetch a single project by Nano-ID."""
        response = await self._request('GET', f'projects/{project_id}')
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return models.ImbiProject.model_validate(response.json())

    async def get_projects(
        self, include_archived: bool = False
    ) -> list[models.ImbiProject]:
        """List every project in the organization."""
        params: dict[str, typing.Any] = {}
        if include_archived:
            params['include_archived'] = 'true'
        response = await self._request(
            'GET', 'projects/', params=params or None
        )
        response.raise_for_status()
        projects = [
            models.ImbiProject.model_validate(entry)
            for entry in response.json()
        ]
        projects.sort(key=lambda p: p.slug)
        return projects

    async def get_projects_by_type(
        self, project_type_slug: str, include_archived: bool = False
    ) -> list[models.ImbiProject]:
        """List every project of a specific type slug in the organization."""
        params: dict[str, typing.Any] = {'project_type': project_type_slug}
        if include_archived:
            params['include_archived'] = 'true'
        response = await self._request('GET', 'projects/', params=params)
        response.raise_for_status()
        projects = [
            models.ImbiProject.model_validate(entry)
            for entry in response.json()
        ]
        projects.sort(key=lambda p: p.slug)
        return projects

    async def get_project_schema(
        self, project_id: str
    ) -> models.ImbiProjectSchema:
        """Return the merged blueprint schema for a project."""
        response = await self._request('GET', f'projects/{project_id}/schema')
        response.raise_for_status()
        return models.ImbiProjectSchema.model_validate(response.json())

    async def search_projects_by_github_url(
        self, github_url: str
    ) -> list[models.ImbiProject]:
        """Find projects whose links dict contains ``github_url``.

        Imbi has no server-side search endpoint, so this lists every
        project in the org and filters client-side. Cost is O(N) per
        call; cache results in the workflow when scanning many URLs.
        """
        normalized = github_url.rstrip('/')
        projects = await self.get_projects()
        matches: list[models.ImbiProject] = []
        for project in projects:
            for url in project.links.values():
                if str(url).rstrip('/') == normalized:
                    matches.append(project)
                    break
        return matches

    # -- Project attribute writes ---------------------------------------

    async def get_project_attribute(
        self, project_id: str, name: str
    ) -> typing.Any:
        """Return the value of a blueprint-defined attribute, or None."""
        project = await self.get_project(project_id)
        if project is None:
            return None
        extras = project.model_extra or {}
        if name in extras:
            return extras[name]
        return getattr(project, name, None)

    async def set_project_attribute(
        self, project_id: str, name: str, value: typing.Any
    ) -> bool:
        """Set a blueprint-defined attribute via JSON Patch.

        Returns ``True`` when a PATCH was issued, ``False`` when the
        value already matched. ``value=None`` removes the attribute.
        """
        return await self.set_project_attributes(project_id, {name: value})

    async def set_project_attributes(
        self, project_id: str, attributes: dict[str, typing.Any]
    ) -> bool:
        """Patch one or more attributes in a single request."""
        if not attributes:
            return False
        project = await self.get_project(project_id)
        if project is None:
            raise ValueError(f'Project not found: {project_id}')
        extras = project.model_extra or {}

        ops: list[dict[str, typing.Any]] = []
        for name, value in attributes.items():
            path = f'/{name}'
            if path in _DOC_PATH_RESERVED:
                raise ValueError(
                    f'Attribute {name!r} is read-only on a project'
                )
            current = extras.get(name, getattr(project, name, None))
            op = _patch_op(path, current, value)
            if op is not None:
                ops.append(op)

        if not ops:
            return False
        await self._patch_project(project_id, ops)
        return True

    async def delete_project_attribute(
        self, project_id: str, name: str
    ) -> bool:
        """Remove a blueprint-defined attribute.

        Returns ``True`` if the attribute existed and was removed,
        ``False`` if it was already absent.
        """
        project = await self.get_project(project_id)
        if project is None:
            raise ValueError(f'Project not found: {project_id}')
        extras = project.model_extra or {}
        if name not in extras and getattr(project, name, None) is None:
            return False
        await self._patch_project(
            project_id, [{'op': 'remove', 'path': f'/{name}'}]
        )
        return True

    # -- Project relationship writes ------------------------------------

    async def add_project_document(
        self,
        project_id: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
    ) -> models.ImbiDocument:
        """Attach a document to a project."""
        payload: dict[str, typing.Any] = {
            'title': title,
            'content': content,
            'tags': list(tags or []),
        }
        response = await self._request(
            'POST', f'projects/{project_id}/documents/', json=payload
        )
        response.raise_for_status()
        return models.ImbiDocument.model_validate(response.json())

    async def add_project_link(
        self, project_id: str, link_definition_slug: str, url: str
    ) -> bool:
        """Attach an external link to a project."""
        definitions = await self.get_link_definitions()
        slugs = {d.slug for d in definitions}
        if link_definition_slug not in slugs:
            raise ValueError(
                f'Unknown link definition slug: {link_definition_slug}'
            )
        project = await self.get_project(project_id)
        if project is None:
            raise ValueError(f'Project not found: {project_id}')
        current = project.links.get(link_definition_slug)
        normalized_current = (
            str(current).rstrip('/') if current is not None else None
        )
        op = _patch_op(
            f'/links/{link_definition_slug}',
            normalized_current,
            url.rstrip('/'),
        )
        if op is None:
            return False
        if op['op'] != 'remove':
            op['value'] = url
        await self._patch_project(project_id, [op])
        return True

    async def remove_project_link(
        self, project_id: str, link_definition_slug: str
    ) -> bool:
        """Remove an external link from a project."""
        project = await self.get_project(project_id)
        if project is None:
            raise ValueError(f'Project not found: {project_id}')
        if link_definition_slug not in project.links:
            return False
        await self._patch_project(
            project_id,
            [{'op': 'remove', 'path': f'/links/{link_definition_slug}'}],
        )
        return True

    async def set_project_identifier(
        self, project_id: str, name: str, value: int | str | None
    ) -> bool:
        """Set or remove a project identifier."""
        project = await self.get_project(project_id)
        if project is None:
            raise ValueError(f'Project not found: {project_id}')
        current = project.identifiers.get(name)
        # Identifiers are compared as strings (server stores int|str).
        normalized_current = str(current) if current is not None else None
        normalized_value = str(value) if value is not None else None
        op = _patch_op(
            f'/identifiers/{name}', normalized_current, normalized_value
        )
        if op is None:
            return False
        if op['op'] != 'remove':
            op['value'] = value
        await self._patch_project(project_id, [op])
        return True

    async def set_project_types(
        self, project_id: str, slugs: list[str]
    ) -> bool:
        """Replace the project's type slugs.

        The PATCH document exposes types as ``project_type_slugs``
        (a deduplicated list of slugs); ``project_types`` on
        ``ProjectResponse`` is the materialized list of types.
        """
        if not slugs:
            raise ValueError('project must have at least one type slug')
        deduped = list(dict.fromkeys(slugs))
        project = await self.get_project(project_id)
        if project is None:
            raise ValueError(f'Project not found: {project_id}')
        current = [pt.slug for pt in project.project_types]
        if current == deduped:
            return False
        await self._patch_project(
            project_id,
            [
                {
                    'op': 'replace',
                    'path': '/project_type_slugs',
                    'value': deduped,
                }
            ],
        )
        return True

    async def set_project_environments(
        self, project_id: str, env_slugs: list[str]
    ) -> bool:
        """Replace the project's environments.

        Emits one PATCH op per env added or removed (vs the project's
        current set). Edge properties on existing environments are
        preserved by the API because we only touch the slugs that
        actually changed.
        """
        project = await self.get_project(project_id)
        if project is None:
            raise ValueError(f'Project not found: {project_id}')
        current = {env.slug for env in project.environments}
        desired = set(env_slugs)
        if current == desired:
            return False
        ops: list[dict[str, typing.Any]] = []
        for slug in sorted(desired - current):
            ops.append(
                {'op': 'add', 'path': f'/environments/{slug}', 'value': {}}
            )
        for slug in sorted(current - desired):
            ops.append({'op': 'remove', 'path': f'/environments/{slug}'})
        await self._patch_project(project_id, ops)
        return True

    # -- Low-level patch -------------------------------------------------

    async def _patch_project(
        self, project_id: str, operations: list[dict[str, typing.Any]]
    ) -> models.ImbiProject:
        """Apply RFC 6902 operations to a project and return the result."""
        LOGGER.debug(
            'PATCH project %s with %d op(s): %s',
            project_id,
            len(operations),
            operations,
        )
        response = await self._request(
            'PATCH', f'projects/{project_id}', json=operations
        )
        if response.status_code == 304:
            project = await self.get_project(project_id)
            if project is None:
                raise RuntimeError(
                    f'Project {project_id} disappeared during PATCH'
                )
            return project
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            LOGGER.error(
                'PATCH failed for project %s: HTTP %d — %s',
                project_id,
                response.status_code,
                response.text,
            )
            raise
        return models.ImbiProject.model_validate(response.json())
