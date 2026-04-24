"""Jira API response models."""

import pydantic


class JiraIssueCreated(pydantic.BaseModel):
    """Response body from `POST /rest/api/3/issue`."""

    model_config = pydantic.ConfigDict(populate_by_name=True)

    id: str
    key: str
    self_url: pydantic.HttpUrl = pydantic.Field(alias='self')
