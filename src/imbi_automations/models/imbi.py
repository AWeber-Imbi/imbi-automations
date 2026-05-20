"""Imbi API models.

Pydantic models for the org-scoped Imbi API: projects, teams,
environments, project types, link definitions, documents, and the
blueprint-merged project schema. ``ImbiProject`` uses
``extra='allow'`` so blueprint-defined attributes round-trip through
parse → patch → serialize without being mentioned by name here.
"""

import datetime
import typing

import pydantic

from . import base


class ImbiOrganization(base.BaseModel):
    """Reference to the owning organization."""

    id: str | None = None
    name: str
    slug: str


class ImbiTeam(base.BaseModel):
    """A team within an organization."""

    id: str | None = None
    name: str
    slug: str
    description: str | None = None
    icon: pydantic.HttpUrl | str | None = None
    organization: ImbiOrganization | None = None


class ImbiEnvironment(base.BaseModel):
    """Imbi environment.

    Blueprint-defined edge properties (e.g. ``url``) flow through
    via ``extra='allow'`` when an environment appears on a project's
    ``DEPLOYED_IN`` edge.
    """

    model_config = pydantic.ConfigDict(extra='allow')

    id: str | None = None
    name: str
    slug: str
    description: str | None = None
    icon: pydantic.HttpUrl | str | None = None
    sort_order: int = 0
    label_color: str | None = None
    organization: ImbiOrganization | None = None


class ImbiProjectType(base.BaseModel):
    """Project type definition."""

    id: str | None = None
    name: str
    slug: str
    description: str | None = None
    icon: pydantic.HttpUrl | str | None = None
    organization: ImbiOrganization | None = None


class ImbiLinkDefinition(base.BaseModel):
    """Per-organization link definition.

    Each definition is keyed by ``slug`` (e.g. ``github-repository``)
    and may carry an ``url_template`` rendered with project context.
    """

    id: str | None = None
    name: str
    slug: str
    description: str | None = None
    icon: pydantic.HttpUrl | str | None = None
    url_template: str | None = None
    organization: ImbiOrganization | None = None


class ImbiRelationshipLink(base.BaseModel):
    """Hypermedia-style link to a related collection."""

    href: str
    count: int = 0


class ImbiRelationships(base.BaseModel):
    """Project relationship summary returned by the Imbi API."""

    href: str
    outbound_count: int = 0
    inbound_count: int = 0


class ImbiProject(base.BaseModel):
    """Imbi project.

    Blueprint-defined attributes are accepted as model extras and
    round-trip cleanly. Read attributes directly off the instance
    (``project.programming_language``) or via ``model_extra``.
    """

    model_config = pydantic.ConfigDict(extra='allow')

    id: str
    name: str
    slug: str
    description: str | None = None
    icon: pydantic.HttpUrl | str | None = None
    created_at: datetime.datetime | None = None
    updated_at: datetime.datetime | None = None
    archived: bool = False
    archived_at: datetime.datetime | None = None
    team: ImbiTeam
    project_types: list[ImbiProjectType] = []
    environments: list[ImbiEnvironment] = []
    links: dict[str, pydantic.AnyUrl] = {}
    identifiers: dict[str, int | str] = {}
    score: float | None = None
    relationships: ImbiRelationships | None = None


class ImbiDocument(base.BaseModel):
    """Project-attached document."""

    id: str
    title: str = ''
    content: str
    project_id: str
    created_by: str
    created_at: datetime.datetime
    updated_by: str | None = None
    updated_at: datetime.datetime | None = None
    is_pinned: bool = False
    tags: list[dict[str, str]] = []


class ImbiBlueprintSectionProperty(base.BaseModel):
    """One property from a blueprint's JSON Schema."""

    model_config = pydantic.ConfigDict(extra='allow')

    type: str | None = None
    format: str | None = None
    title: str | None = None
    description: str | None = None
    enum: list[str] | None = None
    default: typing.Any = None
    minimum: float | None = None
    maximum: float | None = None


class ImbiBlueprintSection(base.BaseModel):
    """One blueprint's contribution to the project schema."""

    name: str
    slug: str
    description: str | None = None
    properties: dict[str, ImbiBlueprintSectionProperty] = {}


class ImbiProjectSchema(base.BaseModel):
    """Merged blueprint schema for a single project."""

    sections: list[ImbiBlueprintSection] = []

    def property_keys(self) -> set[str]:
        """Return every blueprint-defined property key for the project."""
        keys: set[str] = set()
        for section in self.sections:
            keys.update(section.properties.keys())
        return keys
