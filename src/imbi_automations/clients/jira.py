"""Jira Cloud REST API client."""

import base64
import logging
import typing

import httpx

from imbi_automations import adf, models

from . import http

LOGGER = logging.getLogger(__name__)


class Jira(http.BaseURLHTTPClient):
    """Jira Cloud REST v3 client (Basic auth)."""

    def __init__(
        self,
        config: models.JiraConfiguration,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(transport=transport)
        self._base_url = f'https://{config.domain}'
        self._browse_base = f'https://{config.domain}/browse'
        credential = (
            f'{config.email}:{config.api_key.get_secret_value()}'
        ).encode()
        encoded = base64.b64encode(credential).decode()
        self.add_header('Authorization', f'Basic {encoded}')
        self.add_header('Accept', 'application/json')

    def browse_url(self, key: str) -> str:
        """Return the Jira browse URL for an issue key."""
        return f'{self._browse_base}/{key}'

    async def create_issue(
        self,
        *,
        project_key: str,
        summary: str,
        issue_type: str = 'Task',
        description: str | None = None,
        labels: list[str] | None = None,
        components: list[str] | None = None,
        priority: str | None = None,
        extra_fields: dict[str, typing.Any] | None = None,
    ) -> models.JiraIssueCreated:
        """Create a Jira issue.

        `description` is accepted as a markdown string and converted to an
        Atlassian Document Format (ADF) document — callers should not
        hand-author ADF.
        """
        fields: dict[str, typing.Any] = {
            'project': {'key': project_key},
            'summary': summary,
            'issuetype': {'name': issue_type},
        }
        if description is not None:
            fields['description'] = adf.markdown_to_adf(description)
        if labels:
            fields['labels'] = labels
        if components:
            fields['components'] = [{'name': c} for c in components]
        if priority:
            fields['priority'] = {'name': priority}
        if extra_fields:
            fields.update(extra_fields)

        LOGGER.debug(
            'Creating Jira issue in project %s (type=%s)',
            project_key,
            issue_type,
        )
        response = await self.post(
            '/rest/api/3/issue', json={'fields': fields}
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            try:
                error_body = response.text
            except AttributeError, UnicodeDecodeError:
                error_body = '<unable to read response body>'
            LOGGER.error(
                'Failed to create Jira issue in %s: HTTP %d - %s',
                project_key,
                response.status_code,
                error_body,
            )
            raise
        return models.JiraIssueCreated.model_validate(response.json())
