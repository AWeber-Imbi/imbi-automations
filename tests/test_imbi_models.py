"""Tests for Imbi models."""

import unittest

from imbi_automations import models


class ImbiEnvironmentTestCase(unittest.TestCase):
    """Test cases for ImbiEnvironment model."""

    def test_slug_required_field(self) -> None:
        """Test slug is a required field."""
        env = models.ImbiEnvironment(
            name='Production', slug='production', icon_class='fa-cloud'
        )
        self.assertEqual(env.slug, 'production')

    def test_slug_with_spaces(self) -> None:
        """Test slug can contain hyphens for multi-word names."""
        env = models.ImbiEnvironment(
            name='Staging Environment',
            slug='staging-environment',
            icon_class='fa-server',
        )
        self.assertEqual(env.slug, 'staging-environment')

    def test_slug_lowercase(self) -> None:
        """Test slug can be lowercase."""
        env = models.ImbiEnvironment(
            name='QA Testing', slug='qa-testing', icon_class='fa-test'
        )
        self.assertEqual(env.slug, 'qa-testing')

    def test_slug_preserved_when_provided(self) -> None:
        """Test explicit slug is preserved and not overwritten."""
        env = models.ImbiEnvironment(
            name='Development', slug='dev', icon_class='fa-laptop'
        )
        self.assertEqual(env.slug, 'dev')

    def test_slug_from_api_standard_slug(self) -> None:
        """Test parsing API response with standard slug field."""
        api_response = {
            'name': 'Production',
            'slug': 'production',
            'icon_class': 'fa-cloud',
            'description': 'Production environment',
        }
        env = models.ImbiEnvironment.model_validate(api_response)
        self.assertEqual(env.name, 'Production')
        self.assertEqual(env.slug, 'production')

    def test_slug_custom_value(self) -> None:
        """Test parsing API response with custom slug value."""
        api_response = {
            'name': 'Production',
            'slug': 'prod',
            'icon_class': 'fa-cloud',
            'description': 'Production environment',
        }
        env = models.ImbiEnvironment.model_validate(api_response)
        self.assertEqual(env.name, 'Production')
        self.assertEqual(env.slug, 'prod')

    def test_slug_with_normalized_spaces(self) -> None:
        """Test slug can have normalized spacing."""
        env = models.ImbiEnvironment(
            name='Test  Multiple   Spaces',
            slug='test-multiple-spaces',
            icon_class='fa-test',
        )
        # Multiple spaces normalized to single hyphen in slug
        self.assertEqual(env.slug, 'test-multiple-spaces')

    def test_slug_with_sanitized_characters(self) -> None:
        """Test slug can be sanitized version of name."""
        env = models.ImbiEnvironment(
            name='Prod (US/East)', slug='prod-us-east', icon_class='fa-test'
        )
        self.assertEqual(env.slug, 'prod-us-east')


class ImbiProjectServicesTestCase(unittest.TestCase):
    """Test cases for ImbiProject integration services."""

    def make_project(self, services: list[dict]) -> models.ImbiProject:
        return models.ImbiProject.model_validate(
            {
                'id': 'proj_1',
                'name': 'Example',
                'slug': 'example',
                'team': {'name': 'Platform', 'slug': 'platform'},
                'services': services,
            }
        )

    def test_parses_api_services(self) -> None:
        project = self.make_project(
            [
                {
                    'integration_slug': 'ghec',
                    'integration_name': 'GitHub Enterprise Cloud',
                    'identifier': '123456',
                    'canonical_url': (
                        'https://api.github.example.com/repositories/123456'
                    ),
                    'dashboard_url': 'https://github.example.com/org/repo',
                }
            ]
        )
        self.assertEqual(project.services[0].integration_slug, 'ghec')
        self.assertEqual(project.service_identifier('ghec'), '123456')

    def test_service_identifier_missing_integration(self) -> None:
        project = self.make_project(
            [{'integration_slug': 'sonarqube', 'identifier': 'key'}]
        )
        self.assertIsNone(project.service_identifier('ghec'))

    def test_service_identifier_empty(self) -> None:
        project = self.make_project(
            [{'integration_slug': 'ghec', 'identifier': ''}]
        )
        self.assertIsNone(project.service_identifier('ghec'))
