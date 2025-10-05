import collections
import logging
import sys
import typing

from claude_agent_sdk import types

LOGGER = logging.getLogger(__name__)


class Tracker:
    _instance: typing.Self

    def __init__(self) -> None:
        self.counter = collections.Counter()
        self.claude = collections.Counter()

    @classmethod
    def get_instance(cls) -> typing.Self:
        if not hasattr(cls, '_instance') or not cls._instance:
            cls._instance = cls()
        return cls._instance

    def add_claude_run(self, result: types.ResultMessage) -> None:
        if hasattr(result, 'subtype'):
            self.claude[f'subtype_{result.subtype}'] += 1
        self.claude['duration_ms'] += result.duration_ms
        self.claude['duration_api_ms'] += result.duration_api_ms
        self.claude['num_turns'] += result.num_turns
        self.claude['total_cost_usd'] += result.total_cost_usd
        for key in result.usage['cache_creation']:
            self.claude[f'cache_creation_{key}'] += result.usage[
                'cache_creation'
            ][key]
        self.claude['cache_creation_input_tokens'] += result.usage[
            'cache_creation_input_tokens'
        ]
        self.claude['cache_read_input_tokens'] += result.usage[
            'cache_read_input_tokens'
        ]
        self.claude['input_tokens'] += result.usage['input_tokens']
        self.claude['output_tokens'] += result.usage['output_tokens']
        self.claude[f'service_tier_{result.usage["service_tier"]}'] += 1
        for key in result.usage['server_tool_use']:
            self.claude[f'cserver_tool_use_{key}'] += result.usage[
                'server_tool_use'
            ][key]

    def incr(self, key: str, value: int = 1) -> None:
        self.counter[key] += value


def report() -> None:
    obj = Tracker.get_instance()
    sys.stdout.write('Automation Engine Run Details:\n')
    for key in sorted(obj.counter):
        name = key.replace('_', ' ').title()
        sys.stdout.write(f'{name}: {obj.counter[key]}\n')

    if obj.claude:
        sys.stdout.write('\nClaude Usage Details:\n')
        for key in sorted(obj.claude):
            name = key.replace('_', ' ').title()
            sys.stdout.write(f'{name}: {obj.claude[key]}\n')
