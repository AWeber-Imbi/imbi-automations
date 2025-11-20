"""Claude Code action implementation for AI-powered transformations.

Executes Claude Code actions using agent-based workflows (task/validation) with
prompt templating, failure detection, and restart capabilities for reliable
AI-powered code transformations.
"""

import pathlib
import typing
from email import utils as email_utils

from imbi_automations import claude, mixins, models, prompts


class ClaudeAction(mixins.WorkflowLoggerMixin):
    """Executes AI-powered code transformations using Claude Code SDK.

    Manages agent-based workflows with task/validation cycles, prompt
    templating, and automatic restart on failure detection.
    """

    def __init__(
        self,
        configuration: models.Configuration,
        context: models.WorkflowContext,
        verbose: bool,
    ) -> None:
        super().__init__(verbose)
        self._set_workflow_logger(context.workflow)
        self.claude = claude.Claude(configuration, context, verbose)
        self.configuration = configuration
        self.context = context
        self.has_planning_prompt: bool = False
        self.last_error: models.ClaudeAgentValidationResult | None = None
        self.task_plan: models.ClaudeAgentPlanningResult | None = None
        commit_author = email_utils.parseaddr(self.configuration.commit_author)
        self.prompt_kwargs = {
            'commit_author': self.configuration.commit_author,
            'commit_author_name': commit_author[0],
            'commit_author_address': commit_author[1],
            'workflow_name': context.workflow.configuration.name,
            'working_directory': self.context.working_directory,
        }

    async def execute(self, action: models.WorkflowClaudeAction) -> None:
        """Execute the Claude Code action."""
        success = False
        self.last_error = None
        warning_threshold = int(action.max_cycles * 0.6)

        for cycle in range(1, action.max_cycles + 1):
            self.logger.debug(
                '%s [%s/%s] %s Claude Code cycle %d/%d',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                cycle,
                action.max_cycles,
            )

            # Warn when approaching max cycles
            if (
                warning_threshold <= cycle < action.max_cycles
                and action.max_cycles > 5
            ):
                self.logger.warning(
                    '%s [%s/%s] %s has used %d/%d cycles - approaching limit',
                    self.context.imbi_project.slug,
                    self.context.current_action_index,
                    self.context.total_actions,
                    action.name,
                    cycle,
                    action.max_cycles,
                )

            if await self._execute_cycle(action, cycle):
                self.logger.debug(
                    '%s %s Claude Code cycle %d successful',
                    self.context.imbi_project.slug,
                    action.name,
                    cycle,
                )
                success = True
                break

        if not success:  # Categorize failure for better diagnostics
            failure_category = self._categorize_failure()
            error_msg = (
                f'Claude Code action {action.name} failed after '
                f'{action.max_cycles} cycles'
            )
            if failure_category:
                error_msg += f' (category: {failure_category})'
                self.logger.error(
                    '%s %s failure categorized as: %s - consider adjusting '
                    'workflow constraints',
                    self.context.imbi_project.slug,
                    action.name,
                    failure_category,
                )
            raise RuntimeError(error_msg)

    async def _execute_cycle(
        self, action: models.WorkflowClaudeAction, cycle: int
    ) -> bool:
        # Reset task_plan at the start of each cycle
        self.has_planning_prompt = False
        self.task_plan = None

        # Build agent execution sequence
        agents = []
        if action.planning_prompt:
            agents.append(models.ClaudeAgentType.planning)
            self.has_planning_prompt = True
        agents.append(models.ClaudeAgentType.task)
        if action.validation_prompt:
            agents.append(models.ClaudeAgentType.validation)

        for agent in agents:
            self._log_verbose_info(
                '%s [%s/%s] %s executing Claude Code %s agent in cycle %d',
                self.context.imbi_project.slug,
                self.context.current_action_index,
                self.context.total_actions,
                action.name,
                agent,
                cycle,
            )
            prompt = self._get_prompt(action, agent)
            self.logger.debug(
                '%s %s execute agent prompt: %s',
                self.context.imbi_project.slug,
                action.name,
                prompt,
            )

            run = await self.claude.agent_query(prompt)
            self.logger.debug(
                '%s %s %s agent result: %r',
                self.context.imbi_project.slug,
                action.name,
                agent.name,
                run,
            )

            if isinstance(run, models.ClaudeAgentPlanningResult):
                self.task_plan = run
                self.logger.debug(
                    '%s %s planning agent created plan with %d tasks',
                    self.context.imbi_project.slug,
                    action.name,
                    len(self.task_plan.plan),
                )
                # Continue to task agent - don't return yet
            elif isinstance(run, models.ClaudeAgentTaskResult):
                self.logger.debug(
                    '%s %s task result: %s',
                    self.context.imbi_project.slug,
                    action.name,
                    run.message,
                )
            elif isinstance(run, models.ClaudeAgentValidationResult):
                self.logger.debug(
                    '%s %s validation result: %r',
                    self.context.imbi_project.slug,
                    action.name,
                    run,
                )
                self.task_plan = None
                self.last_error = run if not run.validated else None
                return run.validated

        return True

    def _get_prompt(
        self,
        action: models.WorkflowClaudeAction,
        agent: models.ClaudeAgentType,
    ) -> str:
        """Return the rendered prompt for the given agent."""
        prompt = f'Use the "{agent}" agent to complete the following task:\n\n'

        if agent == models.ClaudeAgentType.planning:
            prompt_file = (
                self.context.working_directory
                / 'workflow'
                / action.planning_prompt
            )
        elif agent == models.ClaudeAgentType.task:
            prompt_file = (
                self.context.working_directory
                / 'workflow'
                / action.task_prompt
            )
        elif agent == models.ClaudeAgentType.validation:
            prompt_file = (
                self.context.working_directory
                / 'workflow'
                / action.validation_prompt
            )
        else:
            raise RuntimeError(f'Unknown agent: {agent}')

        if prompt_file.suffix == '.j2':
            data: dict[str, typing.Any] = dict(self.prompt_kwargs)
            data.update(self.context.model_dump())
            data.update({'action': action.model_dump()})
            for key in {'source', 'destination', 'template'}:
                if key in data:
                    del data[key]
            prompt += prompts.render(self.context, prompt_file, **data)
        else:
            prompt += prompt_file.read_text(encoding='utf-8')

        if agent == models.ClaudeAgentType.planning and self.last_error:
            # Planning agent with errors: create a new plan, don't fix directly
            prompt_file = (
                pathlib.Path(__file__).parent
                / 'prompts'
                / 'planning-with-errors.md.j2'
            )
            return prompts.render(
                self.context,
                prompt_file,
                last_error=self.last_error.model_dump_json(indent=2),
                original_prompt=prompt,
            )
        elif (
            agent == models.ClaudeAgentType.task
            and not self.has_planning_prompt
            and self.last_error
        ):
            # Task agent with errors (no planning): fix directly
            prompt_file = (
                pathlib.Path(__file__).parent / 'prompts' / 'last-error.md.j2'
            )
            return prompts.render(
                self.context,
                prompt_file,
                last_error=self.last_error.model_dump_json(indent=2),
                original_prompt=prompt,
            )
        elif agent == models.ClaudeAgentType.task and self.task_plan:
            prompt_file = (
                pathlib.Path(__file__).parent / 'prompts' / 'with-plan.md.j2'
            )
            return prompts.render(
                self.context,
                prompt_file,
                plan=self.task_plan.model_dump(),
                original_prompt=prompt,
            )

        return prompt

    def _categorize_failure(self) -> str | None:
        """Categorize the failure type based on last error messages.

        Returns:
            Failure category string or None if no clear category

        """
        if not self.last_error or not self.last_error.errors:
            return None

        # Combine all error messages for pattern matching
        error_msg = ' '.join(self.last_error.errors).lower()

        # Define failure patterns and categories
        failure_patterns = {
            'dependency_unavailable': [
                'not found',
                'could not find',
                'no matching distribution',
                'no version found',
                'not available',
            ],
            'constraint_conflict': [
                'conflict',
                'incompatible',
                'requires',
                'resolution impossible',
                'cannot install',
            ],
            'prohibited_action': [
                'prohibited',
                'do not modify',
                'not allowed',
                'cannot complete',
                'constraints prohibit',
            ],
            'test_failure': [
                'test failed',
                'assertion error',
                'tests are failing',
                'exit code',
            ],
        }

        # Check each category for matches
        for category, keywords in failure_patterns.items():
            if any(keyword in error_msg for keyword in keywords):
                return category

        return 'unknown'
