"""Tests for Grafana dashboard templates."""

import pytest

from devctl.dashboards import list_templates, get_template, get_template_info


class TestDashboardTemplates:
    """Tests for dashboard template loading and validation."""

    def test_list_templates(self):
        """Test that dashboard templates are available."""
        templates = list_templates()
        assert len(templates) >= 4
        assert "deployment-overview" in templates
        assert "incident-response" in templates
        assert "cost-overview" in templates
        assert "oncall-overview" in templates
        assert "predictive-scaling" in templates

    def test_get_template(self):
        """Test that dashboard templates can be loaded."""
        template = get_template("deployment-overview")
        assert "title" in template
        assert "panels" in template
        assert template["title"] == "Deployment Overview"

    def test_get_template_has_required_fields(self):
        """Test that templates have required Grafana fields."""
        for name in list_templates():
            template = get_template(name)
            assert "title" in template, f"{name} missing title"
            assert "panels" in template, f"{name} missing panels"
            assert isinstance(template["panels"], list), f"{name} panels not a list"

    def test_get_template_info(self):
        """Test dashboard template info."""
        info = get_template_info("incident-response")
        assert info["name"] == "incident-response"
        assert info["title"] == "Incident Response"
        assert "incident" in info["tags"]

    def test_get_template_not_found(self):
        """Test error on non-existent template."""
        with pytest.raises(ValueError) as exc_info:
            get_template("non-existent-template")
        assert "not found" in str(exc_info.value)

    def test_all_templates_have_tags(self):
        """Test that all templates have tags for organization."""
        for name in list_templates():
            template = get_template(name)
            assert "tags" in template, f"{name} missing tags"
            assert len(template["tags"]) > 0, f"{name} has no tags"

    def test_all_templates_have_description(self):
        """Test that all templates have descriptions."""
        for name in list_templates():
            template = get_template(name)
            assert "description" in template, f"{name} missing description"
            assert len(template["description"]) > 0, f"{name} has empty description"
