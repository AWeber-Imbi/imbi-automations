"""Test factories for Imbi entities."""

from __future__ import annotations

import typing

from imbi_automations import models


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
