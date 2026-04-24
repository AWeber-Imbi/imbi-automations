"""Jira Cloud REST API client."""

import base64
import logging
import typing

import httpx

from imbi_automations import models

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

        `description` is accepted as a plain-text / markdown string and
        wrapped into a minimal Atlassian Document Format (ADF) envelope —
        callers should not hand-author ADF.
        """
        fields: dict[str, typing.Any] = {
            'project': {'key': project_key},
            'summary': summary,
            'issuetype': {'name': issue_type},
        }
        if description is not None:
            fields['description'] = _markdown_to_adf(description)
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
            except (AttributeError, UnicodeDecodeError):
                error_body = '<unable to read response body>'
            LOGGER.error(
                'Failed to create Jira issue in %s: HTTP %d - %s',
                project_key,
                response.status_code,
                error_body,
            )
            raise
        return models.JiraIssueCreated.model_validate(response.json())


def _markdown_to_adf(text: str) -> dict[str, typing.Any]:
    """Wrap a plain-text/markdown string into a minimal ADF document.

    Each blank-line-separated block becomes a paragraph; newlines inside a
    block become hard breaks. This is intentionally minimal — rich ADF
    authoring is out of scope for the `jira` action's v1.
    """
    blocks = [block for block in text.split('\n\n') if block.strip()]
    if not blocks:
        blocks = ['']
    paragraphs: list[dict[str, typing.Any]] = []
    for block in blocks:
        lines = block.split('\n')
        content: list[dict[str, typing.Any]] = []
        for idx, line in enumerate(lines):
            if idx > 0:
                content.append({'type': 'hardBreak'})
            if line:
                content.append({'type': 'text', 'text': line})
        paragraphs.append({'type': 'paragraph', 'content': content})
    return {'type': 'doc', 'version': 1, 'content': paragraphs}
