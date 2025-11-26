"""Tests for MCP server configuration models."""

import os
import unittest

import pydantic

from imbi_automations import claude, models


class McpStdioServerTestCase(unittest.TestCase):
    """Test cases for McpStdioServer model."""

    def test_minimal_config(self) -> None:
        """Test minimal stdio server configuration with just command."""
        server = models.McpStdioServer(command='uvx')
        self.assertEqual(server.type, 'stdio')
        self.assertEqual(server.command, 'uvx')
        self.assertEqual(server.args, [])
        self.assertEqual(server.env, {})

    def test_full_config(self) -> None:
        """Test full stdio server configuration with all fields."""
        server = models.McpStdioServer(
            command='uvx',
            args=['mcp-server-postgres', 'postgresql://host/db'],
            env={'DATABASE_URL': 'postgresql://host/db'},
        )
        self.assertEqual(server.type, 'stdio')
        self.assertEqual(server.command, 'uvx')
        self.assertEqual(
            server.args, ['mcp-server-postgres', 'postgresql://host/db']
        )
        self.assertEqual(server.env, {'DATABASE_URL': 'postgresql://host/db'})

    def test_model_dump(self) -> None:
        """Test model_dump returns SDK-compatible dict."""
        server = models.McpStdioServer(
            command='uvx', args=['mcp-server-postgres']
        )
        dumped = server.model_dump()
        self.assertEqual(dumped['type'], 'stdio')
        self.assertEqual(dumped['command'], 'uvx')
        self.assertEqual(dumped['args'], ['mcp-server-postgres'])
        self.assertEqual(dumped['env'], {})


class McpSSEServerTestCase(unittest.TestCase):
    """Test cases for McpSSEServer model."""

    def test_minimal_config(self) -> None:
        """Test minimal SSE server configuration."""
        server = models.McpSSEServer(
            type='sse', url='https://api.example.com/mcp'
        )
        self.assertEqual(server.type, 'sse')
        self.assertEqual(server.url, 'https://api.example.com/mcp')
        self.assertEqual(server.headers, {})

    def test_with_headers(self) -> None:
        """Test SSE server configuration with headers."""
        server = models.McpSSEServer(
            type='sse',
            url='https://api.example.com/mcp',
            headers={'Authorization': 'Bearer token123'},
        )
        self.assertEqual(server.url, 'https://api.example.com/mcp')
        self.assertEqual(server.headers, {'Authorization': 'Bearer token123'})

    def test_model_dump(self) -> None:
        """Test model_dump returns SDK-compatible dict."""
        server = models.McpSSEServer(
            type='sse',
            url='https://api.example.com/mcp',
            headers={'X-Api-Key': 'secret'},
        )
        dumped = server.model_dump()
        self.assertEqual(dumped['type'], 'sse')
        self.assertEqual(dumped['url'], 'https://api.example.com/mcp')
        self.assertEqual(dumped['headers'], {'X-Api-Key': 'secret'})


class McpHttpServerTestCase(unittest.TestCase):
    """Test cases for McpHttpServer model."""

    def test_minimal_config(self) -> None:
        """Test minimal HTTP server configuration."""
        server = models.McpHttpServer(
            type='http', url='https://api.example.com/mcp'
        )
        self.assertEqual(server.type, 'http')
        self.assertEqual(server.url, 'https://api.example.com/mcp')
        self.assertEqual(server.headers, {})

    def test_with_headers(self) -> None:
        """Test HTTP server configuration with headers."""
        server = models.McpHttpServer(
            type='http',
            url='https://api.example.com/mcp',
            headers={'Authorization': 'Bearer token123'},
        )
        self.assertEqual(server.url, 'https://api.example.com/mcp')
        self.assertEqual(server.headers, {'Authorization': 'Bearer token123'})


class McpServerConfigDiscriminatorTestCase(unittest.TestCase):
    """Test cases for McpServerConfig discriminated union."""

    def test_parse_stdio_config(self) -> None:
        """Test parsing stdio server from dict."""
        data = {
            'type': 'stdio',
            'command': 'uvx',
            'args': ['mcp-server-postgres'],
        }
        adapter = pydantic.TypeAdapter(models.McpServerConfig)
        server = adapter.validate_python(data)
        self.assertIsInstance(server, models.McpStdioServer)
        self.assertEqual(server.command, 'uvx')

    def test_parse_sse_config(self) -> None:
        """Test parsing SSE server from dict."""
        data = {'type': 'sse', 'url': 'https://api.example.com/mcp'}
        adapter = pydantic.TypeAdapter(models.McpServerConfig)
        server = adapter.validate_python(data)
        self.assertIsInstance(server, models.McpSSEServer)
        self.assertEqual(server.url, 'https://api.example.com/mcp')

    def test_parse_http_config(self) -> None:
        """Test parsing HTTP server from dict."""
        data = {'type': 'http', 'url': 'https://api.example.com/mcp'}
        adapter = pydantic.TypeAdapter(models.McpServerConfig)
        server = adapter.validate_python(data)
        self.assertIsInstance(server, models.McpHttpServer)
        self.assertEqual(server.url, 'https://api.example.com/mcp')


class WorkflowConfigurationMcpServersTestCase(unittest.TestCase):
    """Test cases for mcp_servers field in WorkflowConfiguration."""

    def test_empty_mcp_servers_default(self) -> None:
        """Test mcp_servers defaults to empty dict."""
        config = models.WorkflowConfiguration(name='test-workflow', actions=[])
        self.assertEqual(config.mcp_servers, {})

    def test_parse_mcp_servers_from_dict(self) -> None:
        """Test parsing mcp_servers from configuration dict."""
        data = {
            'name': 'test-workflow',
            'actions': [],
            'mcp_servers': {
                'my-postgres': {
                    'type': 'stdio',
                    'command': 'uvx',
                    'args': ['mcp-server-postgres', 'postgresql://host/db'],
                },
                'my-api': {
                    'type': 'http',
                    'url': 'https://api.example.com/mcp',
                    'headers': {'Authorization': 'Bearer token'},
                },
            },
        }
        config = models.WorkflowConfiguration.model_validate(data)
        self.assertEqual(len(config.mcp_servers), 2)
        self.assertIsInstance(
            config.mcp_servers['my-postgres'], models.McpStdioServer
        )
        self.assertIsInstance(
            config.mcp_servers['my-api'], models.McpHttpServer
        )

    def test_mcp_server_model_dump_for_sdk(self) -> None:
        """Test that mcp_servers can be converted to SDK format."""
        data = {
            'name': 'test-workflow',
            'actions': [],
            'mcp_servers': {
                'my-server': {
                    'type': 'stdio',
                    'command': 'uvx',
                    'args': ['mcp-server'],
                }
            },
        }
        config = models.WorkflowConfiguration.model_validate(data)
        server = config.mcp_servers['my-server']
        sdk_config = server.model_dump()
        # Verify SDK-compatible format
        self.assertEqual(sdk_config['type'], 'stdio')
        self.assertEqual(sdk_config['command'], 'uvx')
        self.assertEqual(sdk_config['args'], ['mcp-server'])
        self.assertIn('env', sdk_config)


class ExpandEnvVarsTestCase(unittest.TestCase):
    """Test cases for _expand_env_vars function."""

    def setUp(self) -> None:
        """Set up test environment variables."""
        os.environ['TEST_MCP_VAR'] = 'test_value'
        os.environ['TEST_MCP_KEY'] = 'key_12345'

    def tearDown(self) -> None:
        """Clean up test environment variables."""
        os.environ.pop('TEST_MCP_VAR', None)
        os.environ.pop('TEST_MCP_KEY', None)

    def test_expand_dollar_var(self) -> None:
        """Test expansion of $VAR syntax."""
        result = claude._expand_env_vars('value=$TEST_MCP_VAR')
        self.assertEqual(result, 'value=test_value')

    def test_expand_braced_var(self) -> None:
        """Test expansion of ${VAR} syntax."""
        result = claude._expand_env_vars('value=${TEST_MCP_VAR}')
        self.assertEqual(result, 'value=test_value')

    def test_expand_multiple_vars(self) -> None:
        """Test expansion of multiple variables."""
        result = claude._expand_env_vars('$TEST_MCP_VAR:${TEST_MCP_KEY}')
        self.assertEqual(result, 'test_value:key_12345')

    def test_no_expansion_needed(self) -> None:
        """Test string without variables passes through unchanged."""
        result = claude._expand_env_vars('plain_string')
        self.assertEqual(result, 'plain_string')

    def test_missing_var_raises(self) -> None:
        """Test that missing environment variable raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            claude._expand_env_vars('$NONEXISTENT_MCP_VAR')
        self.assertIn('NONEXISTENT_MCP_VAR', str(ctx.exception))


class ExpandMcpConfigTestCase(unittest.TestCase):
    """Test cases for _expand_mcp_config function."""

    def setUp(self) -> None:
        """Set up test environment variables."""
        os.environ['TEST_DB_URL'] = 'postgresql://host/db'
        os.environ['TEST_API_KEY'] = 'api_key_12345'

    def tearDown(self) -> None:
        """Clean up test environment variables."""
        os.environ.pop('TEST_DB_URL', None)
        os.environ.pop('TEST_API_KEY', None)

    def test_expand_args_list(self) -> None:
        """Test expansion in args list."""
        config = {
            'type': 'stdio',
            'command': 'uvx',
            'args': ['mcp-server-postgres', '${TEST_DB_URL}'],
            'env': {},
        }
        result = claude._expand_mcp_config(config)
        self.assertEqual(
            result['args'], ['mcp-server-postgres', 'postgresql://host/db']
        )

    def test_expand_headers_dict(self) -> None:
        """Test expansion in headers dict."""
        config = {
            'type': 'http',
            'url': 'https://api.example.com/mcp',
            'headers': {'Authorization': 'Bearer ${TEST_API_KEY}'},
        }
        result = claude._expand_mcp_config(config)
        self.assertEqual(
            result['headers'], {'Authorization': 'Bearer api_key_12345'}
        )

    def test_expand_url_string(self) -> None:
        """Test expansion in url string."""
        config = {
            'type': 'sse',
            'url': 'https://api.example.com/mcp?key=${TEST_API_KEY}',
            'headers': {},
        }
        result = claude._expand_mcp_config(config)
        self.assertEqual(
            result['url'], 'https://api.example.com/mcp?key=api_key_12345'
        )

    def test_expand_env_dict(self) -> None:
        """Test expansion in env dict."""
        config = {
            'type': 'stdio',
            'command': 'uvx',
            'args': [],
            'env': {'DATABASE_URL': '${TEST_DB_URL}'},
        }
        result = claude._expand_mcp_config(config)
        self.assertEqual(
            result['env'], {'DATABASE_URL': 'postgresql://host/db'}
        )

    def test_non_string_values_unchanged(self) -> None:
        """Test that non-string values pass through unchanged."""
        config = {
            'type': 'stdio',
            'command': 'uvx',
            'args': [],
            'env': {},
            'some_number': 42,
            'some_bool': True,
        }
        result = claude._expand_mcp_config(config)
        self.assertEqual(result['some_number'], 42)
        self.assertEqual(result['some_bool'], True)
