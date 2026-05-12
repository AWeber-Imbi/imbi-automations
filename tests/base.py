import http
import json
import logging
import os
import pathlib
import sys
import typing
import unittest

import httpx
import yarl

from imbi_automations.clients import http as ia_http

LOGGER = logging.getLogger(__name__)

HTTP_HEADERS = {'Content-Type': 'application/json'}


class AsyncTestCase(unittest.IsolatedAsyncioTestCase):
    TEST_DATA = pathlib.Path(__file__).parent / 'data'

    def setUp(self) -> None:
        super().setUp()
        # Some tests reassign ``_instances`` on subclasses (notably
        # ``BaseURLHTTPClient``); that shadows the parent's dict so a
        # plain ``HTTPClient._instances.clear()`` no longer reaches the
        # leaked Imbi/GitHub singletons. Drop any shadowing override.
        for cls in (ia_http.BaseURLHTTPClient, ia_http.HTTPClient):
            if '_instances' in cls.__dict__:
                cls._instances = {}
        self.http_client_transport = httpx.MockTransport(
            self._handle_mock_request
        )
        self.http_mock_transport_alt_file: pathlib.Path | None = None
        self.http_client_side_effect: httpx.Response | None = None
        self.instance: ia_http.HTTPClient | None = None

    async def asyncTearDown(self) -> None:
        # Ensure no residual mock behaviour leaks into the next test.
        self.http_client_side_effect = None
        self.http_mock_transport_alt_file = None
        await super().asyncTearDown()

    def _handle_mock_request(self, request: httpx.Request) -> httpx.Response:
        if self.http_client_side_effect is not None:
            if isinstance(self.http_client_side_effect, httpx.Response):
                return self.http_client_side_effect
            raise self.http_client_side_effect
        url = request.url
        if isinstance(self.instance, ia_http.HTTPClient):
            url = yarl.URL(self.instance.base_url)
        new_request = httpx.Request(
            method=request.method,
            url=httpx.URL(
                scheme=url.scheme,
                host=url.host,
                port=url.port,
                path=request.url.path,
                query=request.url.query,
                fragment=request.url.fragment,
            ),
            headers=request.headers,
            content=request.content,
            stream=request.stream,
            extensions=request.extensions,
        )
        if (
            self.http_mock_transport_alt_file
            and self.http_mock_transport_alt_file.exists()
        ):
            path = self.http_mock_transport_alt_file
        else:
            path = f'{request.url.path[1:].rstrip("/")}.json'
        file = self.TEST_DATA.joinpath(path)
        if not file.exists():
            LOGGER.debug('No mock data for %s', request.url.path[1:])
            return httpx.Response(
                http.HTTPStatus.NOT_FOUND,
                request=new_request,
                content='',
                headers=HTTP_HEADERS,
            )
        with self.TEST_DATA.joinpath(file).open() as f:
            return httpx.Response(
                http.HTTPStatus.OK,
                content=f.read(),
                request=new_request,
                headers=HTTP_HEADERS,
            )

    def _load_test_data(self, path: str) -> dict[str, typing.Any]:
        with self.TEST_DATA.joinpath(path).open() as f:
            return json.load(f)


class TestEnvMixin:
    @classmethod
    def setUpClass(cls) -> None:
        path = pathlib.Path(__file__).parent / '../build/test.env'
        if not path.exists():
            sys.stderr.write('Failed to find test.env file\n')
            return
        with path.open('r') as f:
            for line in f:
                if line.startswith('export '):
                    line = line[7:]
                name, _, value = line.strip().partition('=')
                os.environ[name.upper()] = value
