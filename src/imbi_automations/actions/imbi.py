"""Imbi actions for workflow execution."""

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
            case models.WorkflowImbiActionCommand.batch_update_facts:
                await self._batch_update_facts(action)
            case models.WorkflowImbiActionCommand.delete_project_fact:
                await self._delete_project_fact(action)
            case models.WorkflowImbiActionCommand.get_project_fact:
                await self._get_project_fact(action)
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

    async def _set_environments(
        self, action: models.WorkflowImbiAction
    ) -> None:
        """Set environments via Imbi API.

        Args:
            action: Action with values list of environment slugs or names

        Raises:
            ValueError: If values is missing or registry is not available
            httpx.HTTPError: If API request fails

        """
        if not action.values:
            raise ValueError('values is required for set_environments')

        if not self.context.registry:
            raise ValueError(
                'ImbiMetadataCache registry not available in context'
            )

        # Translate environment slugs/names to names
        try:
            environment_names = self.context.registry.translate_environments(
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

        client = clients.Imbi.get_instance(config=self.configuration.imbi)

        self.logger.debug(
            '%s [%s/%s] %s setting environments to %s for project %d (%s)',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            environment_names,
            self.context.imbi_project.id,
            self.context.imbi_project.name,
        )

        try:
            await client.update_project_environments(
                project_id=self.context.imbi_project.id,
                environments=environment_names,
            )
        except httpx.HTTPError as exc:
            self.logger.error(
                '%s [%s/%s] %s failed to set environments for project %d: %s',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                self.context.imbi_project.id,
                exc,
            )
            raise
        else:
            self.logger.info(
                '%s [%s/%s] %s successfully updated environments for '
                'project %d',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                self.context.imbi_project.id,
            )

    async def _update_project(self, action: models.WorkflowImbiAction) -> None:
        """Update project attributes via Imbi API.

        Args:
            action: Action with attributes dict (supports Jinja2 templates)

        Raises:
            ValueError: If attributes is missing or empty
            httpx.HTTPError: If API request fails

        """
        if not action.attributes:
            raise ValueError('attributes is required for update_project')

        # Render Jinja2 templates in attribute values
        rendered_attributes = {}
        for attr_name, attr_value in action.attributes.items():
            # Only render string values (templates)
            if isinstance(attr_value, str):
                rendered_value = prompts.render_template_string(
                    attr_value,
                    workflow=self.context.workflow,
                    github_repository=self.context.github_repository,
                    imbi_project=self.context.imbi_project,
                    working_directory=self.context.working_directory,
                    starting_commit=self.context.starting_commit,
                    variables=self.context.variables,
                )
                rendered_attributes[attr_name] = rendered_value
            else:
                # Pass through non-string values unchanged
                rendered_attributes[attr_name] = attr_value

        client = clients.Imbi.get_instance(config=self.configuration.imbi)

        # Log which attributes are being updated
        attr_summary = ', '.join(
            f'{k}="{v}"' for k, v in rendered_attributes.items()
        )
        self.logger.debug(
            '%s [%s/%s] %s updating project %d (%s) with: %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            self.context.imbi_project.id,
            self.context.imbi_project.name,
            attr_summary,
        )

        try:
            await client.update_project_attributes(
                project_id=self.context.imbi_project.id,
                attributes=rendered_attributes,
            )
        except (httpx.HTTPError, ValueError) as exc:
            self.logger.error(
                '%s [%s/%s] %s failed to update project %d: %s',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                self.context.imbi_project.id,
                exc,
            )
            raise
        else:
            self.logger.info(
                '%s [%s/%s] %s successfully updated project %d',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                self.context.imbi_project.id,
            )

    async def _set_project_fact(
        self, action: models.WorkflowImbiAction
    ) -> None:
        """Set a project fact via Imbi API.

        Args:
            action: Action with fact_name and value

        Raises:
            ValueError: If fact_name or value is missing
            httpx.HTTPError: If API request fails

        """
        if not action.fact_name or action.value is None:
            raise ValueError(
                'fact_name and value are required for set_project_fact'
            )

        client = clients.Imbi.get_instance(config=self.configuration.imbi)

        self.logger.debug(
            '%s [%s/%s] %s setting fact "%s" to "%s" for project %d (%s)',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            action.fact_name,
            action.value,
            self.context.imbi_project.id,
            self.context.imbi_project.name,
        )

        try:
            await client.update_project_fact(
                project_id=self.context.imbi_project.id,
                fact_name=action.fact_name,
                value=action.value,
                skip_validations=action.skip_validations,
            )
        except (httpx.HTTPError, ValueError, RuntimeError) as exc:
            self.logger.error(
                '%s [%s/%s] %s failed to set fact "%s" for project %d: %s',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                action.fact_name,
                self.context.imbi_project.id,
                exc,
            )
            raise
        else:
            self.logger.info(
                '%s [%s/%s] %s successfully updated fact "%s" for project %d',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                action.fact_name,
                self.context.imbi_project.id,
            )

    async def _get_project_fact(
        self, action: models.WorkflowImbiAction
    ) -> None:
        """Get a project fact value and optionally store it in a variable.

        Args:
            action: Action with fact_name and optional variable_name

        Raises:
            ValueError: If fact_name is missing
            httpx.HTTPError: If API request fails

        """
        if not action.fact_name:
            raise ValueError('fact_name is required for get_project_fact')

        client = clients.Imbi.get_instance(config=self.configuration.imbi)

        self.logger.debug(
            '%s [%s/%s] %s getting fact "%s" for project %d (%s)',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            action.fact_name,
            self.context.imbi_project.id,
            self.context.imbi_project.name,
        )

        try:
            value = await client.get_project_fact_value(
                project_id=self.context.imbi_project.id,
                fact_name=action.fact_name,
            )
        except httpx.HTTPError as exc:
            self.logger.error(
                '%s [%s/%s] %s failed to get fact "%s" for project %d: %s',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                action.fact_name,
                self.context.imbi_project.id,
                exc,
            )
            raise
        else:
            self.logger.info(
                '%s [%s/%s] %s got fact "%s" = "%s" for project %d',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                action.fact_name,
                value,
                self.context.imbi_project.id,
            )

            # Store in workflow variables if variable_name specified
            if action.variable_name:
                self.context.variables[action.variable_name] = value
                self.logger.debug(
                    '%s stored fact value in variable "%s"',
                    self.context.imbi_project.slug,
                    action.variable_name,
                )

    async def _delete_project_fact(
        self, action: models.WorkflowImbiAction
    ) -> None:
        """Delete a project fact via Imbi API.

        Args:
            action: Action with fact_name

        Raises:
            ValueError: If fact_name is missing
            httpx.HTTPError: If API request fails

        """
        if not action.fact_name:
            raise ValueError('fact_name is required for delete_project_fact')

        client = clients.Imbi.get_instance(config=self.configuration.imbi)

        self.logger.debug(
            '%s [%s/%s] %s deleting fact "%s" for project %d (%s)',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            action.fact_name,
            self.context.imbi_project.id,
            self.context.imbi_project.name,
        )

        try:
            deleted = await client.delete_project_fact(
                project_id=self.context.imbi_project.id,
                fact_name=action.fact_name,
            )
        except (httpx.HTTPError, ValueError) as exc:
            self.logger.error(
                '%s [%s/%s] %s failed to delete fact "%s" for project %d: %s',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                action.fact_name,
                self.context.imbi_project.id,
                exc,
            )
            raise
        else:
            if deleted:
                self.logger.info(
                    '%s [%s/%s] %s deleted fact "%s" for project %d',
                    self.context.imbi_project.slug,
                    self.context.current_action_index,
                    self.context.total_actions,
                    action.name,
                    action.fact_name,
                    self.context.imbi_project.id,
                )
            else:
                self.logger.info(
                    '%s [%s/%s] %s fact "%s" not set for project %d, '
                    'nothing to delete',
                    self.context.imbi_project.slug,
                    self.context.current_action_index,
                    self.context.total_actions,
                    action.name,
                    action.fact_name,
                    self.context.imbi_project.id,
                )

    async def _add_project_link(
        self, action: models.WorkflowImbiAction
    ) -> None:
        """Add a link to a project via Imbi API.

        Args:
            action: Action with link_type and url

        Raises:
            ValueError: If link_type or url is missing
            httpx.HTTPError: If API request fails

        """
        if not action.link_type or not action.url:
            raise ValueError(
                'link_type and url are required for add_project_link'
            )

        # Render URL template if it contains Jinja2 syntax
        rendered_url = prompts.render_template_string(
            action.url,
            workflow=self.context.workflow,
            github_repository=self.context.github_repository,
            imbi_project=self.context.imbi_project,
            working_directory=self.context.working_directory,
            starting_commit=self.context.starting_commit,
            variables=self.context.variables,
        )

        client = clients.Imbi.get_instance(config=self.configuration.imbi)

        self.logger.debug(
            '%s [%s/%s] %s adding %s link "%s" for project %d (%s)',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            action.link_type,
            rendered_url,
            self.context.imbi_project.id,
            self.context.imbi_project.name,
        )

        try:
            await client.add_project_link(
                project_id=self.context.imbi_project.id,
                link_type=action.link_type,
                url=rendered_url,
            )
        except (httpx.HTTPError, ValueError) as exc:
            self.logger.error(
                '%s [%s/%s] %s failed to add link for project %d: %s',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                self.context.imbi_project.id,
                exc,
            )
            raise
        else:
            self.logger.info(
                '%s [%s/%s] %s added %s link for project %d',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                action.link_type,
                self.context.imbi_project.id,
            )

    async def _update_project_type(
        self, action: models.WorkflowImbiAction
    ) -> None:
        """Update the project type via Imbi API.

        Args:
            action: Action with project_type (slug)

        Raises:
            ValueError: If project_type is missing
            httpx.HTTPError: If API request fails

        """
        if not action.project_type:
            raise ValueError(
                'project_type is required for update_project_type'
            )

        client = clients.Imbi.get_instance(config=self.configuration.imbi)

        self.logger.debug(
            '%s [%s/%s] %s updating project type to "%s" for project %d (%s)',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            action.project_type,
            self.context.imbi_project.id,
            self.context.imbi_project.name,
        )

        try:
            await client.update_project_type(
                project_id=self.context.imbi_project.id,
                project_type_slug=action.project_type,
            )
        except (httpx.HTTPError, ValueError) as exc:
            self.logger.error(
                '%s [%s/%s] %s failed to update project type for '
                'project %d: %s',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                self.context.imbi_project.id,
                exc,
            )
            raise
        else:
            self.logger.info(
                '%s [%s/%s] %s updated project type to "%s" for project %d',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                action.project_type,
                self.context.imbi_project.id,
            )

    async def _batch_update_facts(
        self, action: models.WorkflowImbiAction
    ) -> None:
        """Update multiple project facts in a single operation.

        Args:
            action: Action with facts dict (fact_name -> value)

        Raises:
            ValueError: If facts is empty
            httpx.HTTPError: If API request fails

        """
        if not action.facts:
            raise ValueError('facts is required for batch_update_facts')

        client = clients.Imbi.get_instance(config=self.configuration.imbi)

        # Convert fact names to fact_type_ids
        facts_to_update: list[tuple[int, bool | int | float | str]] = []
        for fact_name, value in action.facts.items():
            fact_type_id = await client.get_project_fact_type_id_by_name(
                fact_name
            )
            if not fact_type_id:
                raise ValueError(f'Fact type not found: {fact_name}')
            facts_to_update.append((fact_type_id, value))

        fact_summary = ', '.join(f'{k}="{v}"' for k, v in action.facts.items())
        self.logger.debug(
            '%s [%s/%s] %s batch updating facts for project %d (%s): %s',
            self.context.imbi_project.slug,
            self.context.current_action_index,
            self.context.total_actions,
            action.name,
            self.context.imbi_project.id,
            self.context.imbi_project.name,
            fact_summary,
        )

        try:
            await client.update_project_facts(
                project_id=self.context.imbi_project.id, facts=facts_to_update
            )
        except httpx.HTTPError as exc:
            self.logger.error(
                '%s [%s/%s] %s failed to batch update facts for '
                'project %d: %s',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                self.context.imbi_project.id,
                exc,
            )
            raise
        else:
            self.logger.info(
                '%s [%s/%s] %s batch updated %d facts for project %d',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                len(action.facts),
                self.context.imbi_project.id,
            )
