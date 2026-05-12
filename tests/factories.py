"""Test factories for Imbi entities."""

from __future__ import annotations

import json
import pathlib
import typing

from imbi_automations import models

_FIXTURES = pathlib.Path(__file__).parent / 'data' / 'imbi'


def load_imbi_fixture(name: str) -> typing.Any:
    """Return the parsed JSON fixture at ``tests/data/imbi/<name>``."""
    return json.loads((_FIXTURES / name).read_text(encoding='utf-8'))


def auth_response(
    access_token: str,
    refresh_token: str = 'refresh-1',  # noqa: S107
) -> dict[str, typing.Any]:
    """Return an ``auth_token_response.json`` fixture with tokens filled in."""
    payload = load_imbi_fixture('auth_token_response.json')
    payload['access_token'] = access_token
    payload['refresh_token'] = refresh_token
    return payload


def make_project(
    *,
    id: str = 'proj_test',
    name: str = 'test-project',
    slug: str = 'test-project',
    description: str | None = 'Test project',
    team_slug: str = 'platform',
    team_name: str | None = None,
    project_type_slugs: typing.Sequence[str] = ('api',),
    environments: typing.Sequence[models.ImbiEnvironment] | None = None,
    links: dict[str, str] | None = None,
    identifiers: dict[str, int | str] | None = None,
    score: float | None = None,
    attributes: dict[str, typing.Any] | None = None,
) -> models.ImbiProject:
    """Return an :class:`ImbiProject` populated with v2-shaped data.

    ``attributes`` are spread onto the model as blueprint-defined
    extras (``extra='allow'``).
    """
    payload: dict[str, typing.Any] = {
        'id': id,
        'name': name,
        'slug': slug,
        'description': description,
        'team': {
            'name': team_name or team_slug.replace('-', ' ').title(),
            'slug': team_slug,
        },
        'project_types': [
            {'name': pt.replace('-', ' ').title(), 'slug': pt}
            for pt in project_type_slugs
        ],
        'environments': [env.model_dump() for env in environments or ()],
        'links': links or {},
        'identifiers': identifiers or {},
        'score': score,
    }
    if attributes:
        payload.update(attributes)
    return models.ImbiProject.model_validate(payload)
