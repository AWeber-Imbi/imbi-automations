"""Tests for Imbi models."""

import unittest

from imbi_automations import models


class ImbiEnvironmentTestCase(unittest.TestCase):
    """Test cases for ImbiEnvironment model."""

    def test_slug_auto_generation_from_name(self) -> None:
        """Test slug is auto-generated from name when not provided."""
        env = models.ImbiEnvironment(name='Production', icon_class='fa-cloud')
        self.assertEqual(env.slug, 'production')

    def test_slug_auto_generation_with_spaces(self) -> None:
        """Test slug generation replaces spaces with hyphens."""
        env = models.ImbiEnvironment(
            name='Staging Environment', icon_class='fa-server'
        )
        self.assertEqual(env.slug, 'staging-environment')

    def test_slug_auto_generation_mixed_case(self) -> None:
        """Test slug generation converts to lowercase."""
        env = models.ImbiEnvironment(name='QA Testing', icon_class='fa-test')
        self.assertEqual(env.slug, 'qa-testing')

    def test_slug_preserved_when_provided(self) -> None:
        """Test explicit slug is preserved and not overwritten."""
        env = models.ImbiEnvironment(
            name='Development', slug='dev', icon_class='fa-laptop'
        )
        self.assertEqual(env.slug, 'dev')

    def test_slug_from_api_without_slug_field(self) -> None:
        """Test parsing API response that doesn't include slug field."""
        api_response = {
            'name': 'Production',
            'icon_class': 'fa-cloud',
            'description': 'Production environment',
        }
        env = models.ImbiEnvironment.model_validate(api_response)
        self.assertEqual(env.name, 'Production')
        self.assertEqual(env.slug, 'production')

    def test_slug_from_api_with_slug_field(self) -> None:
        """Test parsing API response that includes slug field."""
        api_response = {
            'name': 'Production',
            'slug': 'prod',
            'icon_class': 'fa-cloud',
            'description': 'Production environment',
        }
        env = models.ImbiEnvironment.model_validate(api_response)
        self.assertEqual(env.name, 'Production')
        self.assertEqual(env.slug, 'prod')

    def test_slug_with_multiple_spaces(self) -> None:
        """Test slug generation handles multiple consecutive spaces."""
        env = models.ImbiEnvironment(
            name='Test  Multiple   Spaces', icon_class='fa-test'
        )
        # Multiple spaces normalized to single hyphen
        self.assertEqual(env.slug, 'test-multiple-spaces')

    def test_slug_with_special_characters(self) -> None:
        """Test slug generation sanitizes special characters."""
        env = models.ImbiEnvironment(
            name='Prod (US/East)', icon_class='fa-test'
        )
        self.assertEqual(env.slug, 'prod-us-east')
