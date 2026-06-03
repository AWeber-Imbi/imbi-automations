"""Imbi actions for workflow execution."""

import typing

import httpx

from imbi_automations import clients, mixins, models, prompts


class ImbiActions(mixins.WorkflowLoggerMixin):
    """Executes Imbi project management system operations.

    Provides integration with Imbi API for project data access and
    modification.
    """

    def __init__(
        self,
        configuration: models.Configuration,
        context: models.WorkflowContext,
        verbose: bool,
    ) -> None:
        super().__init__(verbose)
        self._set_workflow_logger(context.workflow)
        self.configuration = configuration
        self.context = context

    async def execute(self, action: models.WorkflowImbiAction) -> None:
        """Execute an Imbi action.

        Args:
            action: Imbi action to execute

        Raises:
            RuntimeError: If command is not supported

        """
        match action.command:
            case models.WorkflowImbiActionCommand.add_project_link:
                await self._add_project_link(action)
            case models.WorkflowImbiActionCommand.add_project_note:
                await self._add_project_note(action)
            case models.WorkflowImbiActionCommand.batch_update_facts:
                await self._batch_update_facts(action)
            case models.WorkflowImbiActionCommand.delete_project_fact:
                await self._delete_project_fact(action)
            case models.WorkflowImbiActionCommand.get_project_fact:
                await self._get_project_fact(action)
            case models.WorkflowImbiActionCommand.request:
                await self._request_passthrough(action)
            case models.WorkflowImbiActionCommand.set_project_fact:
                await self._set_project_fact(action)
            case models.WorkflowImbiActionCommand.set_environments:
                await self._set_environments(action)
            case models.WorkflowImbiActionCommand.update_project:
                await self._update_project(action)
            case models.WorkflowImbiActionCommand.update_project_type:
                await self._update_project_type(action)
            case _:
                raise RuntimeError(f'Unsupported command: {action.command}')

    # -- Helpers --------------------------------------------------------

    def _client(self) -> clients.Imbi:
        return clients.Imbi.get_instance(config=self.configuration.imbi)

    def _project_id(self) -> str:
        return self.context.imbi_project.id

    def _attribute_name(self, action: models.WorkflowImbiAction) -> str:
        if not action.attribute_name:
            raise ValueError(
                f"'attribute_name' is required for command '{action.command}'"
            )
        return action.attribute_name

    def _render(self, template: str) -> str:
        return prompts.render_template_string(
            template,
            workflow=self.context.workflow,
            github_repository=self.context.github_repository,
            imbi_project=self.context.imbi_project,
            working_directory=self.context.working_directory,
            starting_commit=self.context.starting_commit,
            variables=self.context.variables,
        )

    def _render_body(self, value: typing.Any) -> typing.Any:
        """Recursively render Jinja2 in string leaves of a request body."""
        if isinstance(value, str):
            return self._render(value)
        if isinstance(value, dict):
            return {key: self._render_body(val) for key, val in value.items()}
        if isinstance(value, list):
            return [self._render_body(item) for item in value]
        return value

    # -- Commands -------------------------------------------------------

    async def _set_environments(
        self, action: models.WorkflowImbiAction
    ) -> None:
        if not action.values:
            raise ValueError('values is required for set_environments')
        if not self.context.registry:
            raise ValueError(
                'ImbiMetadataCache registry not available in context'
            )
        try:
            env_slugs = self.context.registry.translate_environments(
                action.values
            )
        except ValueError as exc:
            self.logger.error(
                '%s %s failed to translate environments: %s',
                self.context.imbi_project.slug,
                action.name,
                exc,
            )
            raise

        self.logger.debug(
            '%s [%s/%s] %s setting environments to %s for project %s (%s)',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            env_slugs,
            self._project_id(),
            self.context.imbi_project.name,
        )
        try:
            await self._client().set_project_environments(
                project_id=self._project_id(), env_slugs=env_slugs
            )
        except httpx.HTTPError as exc:
            self.logger.error(
                '%s [%s/%s] %s failed to set environments: %s',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                exc,
            )
            raise
        self.logger.info(
            '%s [%s/%s] %s updated environments for project %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            self._project_id(),
        )

    async def _update_project(self, action: models.WorkflowImbiAction) -> None:
        if not action.attributes:
            raise ValueError('attributes is required for update_project')

        rendered: dict[str, typing.Any] = {}
        for name, value in action.attributes.items():
            rendered[name] = (
                self._render(value) if isinstance(value, str) else value
            )

        attr_summary = ', '.join(f'{k}="{v}"' for k, v in rendered.items())
        self.logger.debug(
            '%s [%s/%s] %s updating project %s (%s) with: %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            self._project_id(),
            self.context.imbi_project.name,
            attr_summary,
        )
        try:
            await self._client().set_project_attributes(
                project_id=self._project_id(), attributes=rendered
            )
        except (httpx.HTTPError, ValueError) as exc:
            self.logger.error(
                '%s [%s/%s] %s failed to update project %s: %s',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                self._project_id(),
                exc,
            )
            raise
        self.logger.info(
            '%s [%s/%s] %s updated project %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            self._project_id(),
        )

    async def _set_project_fact(
        self, action: models.WorkflowImbiAction
    ) -> None:
        name = self._attribute_name(action)
        if action.value is None:
            raise ValueError('value is required for set_project_fact')
        self.logger.debug(
            '%s [%s/%s] %s setting attribute "%s" = "%s" on project %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            name,
            action.value,
            self._project_id(),
        )
        try:
            await self._client().set_project_attribute(
                project_id=self._project_id(), name=name, value=action.value
            )
        except (httpx.HTTPError, ValueError) as exc:
            self.logger.error(
                '%s [%s/%s] %s failed to set attribute "%s": %s',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                name,
                exc,
            )
            raise
        self.logger.info(
            '%s [%s/%s] %s updated attribute "%s" on project %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            name,
            self._project_id(),
        )

    async def _get_project_fact(
        self, action: models.WorkflowImbiAction
    ) -> None:
        name = self._attribute_name(action)
        self.logger.debug(
            '%s [%s/%s] %s reading attribute "%s" on project %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            name,
            self._project_id(),
        )
        try:
            value = await self._client().get_project_attribute(
                project_id=self._project_id(), name=name
            )
        except httpx.HTTPError as exc:
            self.logger.error(
                '%s [%s/%s] %s failed to read attribute "%s": %s',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                name,
                exc,
            )
            raise
        self.logger.info(
            '%s [%s/%s] %s attribute "%s" = "%s" on project %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            name,
            value,
            self._project_id(),
        )
        if action.variable_name:
            self.context.variables[action.variable_name] = value

    async def _delete_project_fact(
        self, action: models.WorkflowImbiAction
    ) -> None:
        name = self._attribute_name(action)
        self.logger.debug(
            '%s [%s/%s] %s removing attribute "%s" on project %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            name,
            self._project_id(),
        )
        try:
            deleted = await self._client().delete_project_attribute(
                project_id=self._project_id(), name=name
            )
        except (httpx.HTTPError, ValueError) as exc:
            self.logger.error(
                '%s [%s/%s] %s failed to remove attribute "%s": %s',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                name,
                exc,
            )
            raise
        action_msg = 'removed' if deleted else 'already absent'
        self.logger.info(
            '%s [%s/%s] %s attribute "%s" %s on project %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            name,
            action_msg,
            self._project_id(),
        )

    async def _add_project_link(
        self, action: models.WorkflowImbiAction
    ) -> None:
        slug = action.link_definition_slug
        if not slug or not action.url:
            raise ValueError(
                "'link_definition_slug' and 'url' are required for "
                'add_project_link'
            )
        rendered = self._render(action.url)
        self.logger.debug(
            '%s [%s/%s] %s adding link "%s"="%s" on project %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            slug,
            rendered,
            self._project_id(),
        )
        try:
            await self._client().add_project_link(
                project_id=self._project_id(),
                link_definition_slug=slug,
                url=rendered,
            )
        except (httpx.HTTPError, ValueError) as exc:
            self.logger.error(
                '%s [%s/%s] %s failed to add link "%s": %s',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                slug,
                exc,
            )
            raise
        self.logger.info(
            '%s [%s/%s] %s added link "%s" on project %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            slug,
            self._project_id(),
        )

    async def _add_project_note(
        self, action: models.WorkflowImbiAction
    ) -> None:
        if not action.title or not action.content:
            raise ValueError(
                "'title' and 'content' are required for add_project_note"
            )
        title = self._render(action.title)
        body = self._render(action.content)
        self.logger.debug(
            '%s [%s/%s] %s creating document "%s" (%d chars) on project %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            title,
            len(body),
            self._project_id(),
        )
        try:
            document = await self._client().add_project_document(
                project_id=self._project_id(),
                title=title,
                content=body,
                tags=action.tags,
            )
        except httpx.HTTPError as exc:
            self.logger.error(
                '%s [%s/%s] %s failed to create document: %s',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                exc,
            )
            raise
        self.logger.info(
            '%s [%s/%s] %s created document %s on project %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            document.id,
            self._project_id(),
        )

    async def _request_passthrough(
        self, action: models.WorkflowImbiAction
    ) -> None:
        if not action.method or not action.path:
            raise ValueError("'method' and 'path' are required for request")
        method = action.method.upper()
        if method not in {'GET', 'HEAD'} and not action.allow_writes:
            raise ValueError(
                f'{action.name}: {method} requires allow_writes = true'
            )
        path = self._render(action.path)
        params = {
            key: self._render(val) for key, val in action.query.items()
        } or None
        body = self._render_body(action.body)
        self.logger.debug(
            '%s [%s/%s] %s request %s %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            method,
            path,
        )
        result = await self._client().request_json(
            method, path, params=params, json=body
        )
        if action.variable_name:
            self.context.variables[action.variable_name] = result

    async def _update_project_type(
        self, action: models.WorkflowImbiAction
    ) -> None:
        slugs = action.project_types
        if not slugs:
            raise ValueError(
                "'project_types' is required for update_project_type"
            )
        self.logger.debug(
            '%s [%s/%s] %s setting project types to %s on project %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            slugs,
            self._project_id(),
        )
        try:
            await self._client().set_project_types(
                project_id=self._project_id(), slugs=slugs
            )
        except (httpx.HTTPError, ValueError) as exc:
            self.logger.error(
                '%s [%s/%s] %s failed to set project types: %s',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                exc,
            )
            raise
        self.logger.info(
            '%s [%s/%s] %s set project types to %s on project %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            slugs,
            self._project_id(),
        )

    async def _batch_update_facts(
        self, action: models.WorkflowImbiAction
    ) -> None:
        if not action.facts:
            raise ValueError('facts is required for batch_update_facts')
        fact_summary = ', '.join(f'{k}="{v}"' for k, v in action.facts.items())
        self.logger.debug(
            '%s [%s/%s] %s batch updating attributes on project %s: %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            self._project_id(),
            fact_summary,
        )
        try:
            await self._client().set_project_attributes(
                project_id=self._project_id(), attributes=dict(action.facts)
            )
        except (httpx.HTTPError, ValueError) as exc:
            self.logger.error(
                '%s [%s/%s] %s failed to batch update attributes: %s',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                exc,
            )
            raise
        self.logger.info(
            '%s [%s/%s] %s batch updated %d attribute(s) on project %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            len(action.facts),
            self._project_id(),
        )
