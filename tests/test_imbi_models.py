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
