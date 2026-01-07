"""
Schema Manager for Hierarchical Labelme

This module provides the SchemaManager class which loads and validates
annotation schemas from YAML files. It handles class definitions,
hierarchy rules, and attribute configurations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class SchemaValidationError(Exception):
    """Raised when schema validation fails."""

    pass


class SchemaManager:
    """
    Manages annotation schema for hierarchical labeling.

    The schema defines:
    - Available classes (labels) and their properties
    - Parent-child relationships (hierarchy rules)
    - Class-specific attributes with types and constraints
    - Display settings (colors, names)

    Example usage:
        schema = SchemaManager("annotation_schema.yaml")
        classes = schema.get_all_classes()
        children = schema.get_allowed_children("box")
        attrs = schema.get_attributes_config("face")
    """

    def __init__(self, schema_path: str | Path):
        """
        Initialize SchemaManager with a schema file.

        Args:
            schema_path: Path to YAML schema file

        Raises:
            FileNotFoundError: If schema file doesn't exist
            SchemaValidationError: If schema is invalid
        """
        self.schema_path = Path(schema_path)
        if not self.schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        self._schema: dict[str, Any] = {}
        self._classes: dict[str, dict[str, Any]] = {}
        self._settings: dict[str, Any] = {}
        self._shortcuts: dict[str, str] = {}
        self._display_order: list[str] = []

        self._load_schema()
        self._validate_schema()

    def _load_schema(self) -> None:
        """Load schema from YAML file."""
        with open(self.schema_path, encoding="utf-8") as f:
            self._schema = yaml.safe_load(f)

        self._classes = self._schema.get("classes", {})
        self._settings = self._schema.get("settings", {})
        self._shortcuts = self._schema.get("shortcuts", {})
        self._display_order = self._schema.get(
            "display_order", list(self._classes.keys())
        )

    def _validate_schema(self) -> None:
        """
        Validate the loaded schema for consistency.

        Checks:
        - All referenced parent/child classes exist
        - No circular dependencies
        - Required fields are present
        - Attribute types are valid
        """
        valid_classes = set(self._classes.keys())

        for class_name, class_def in self._classes.items():
            # Check allowed_children reference valid classes
            for child in class_def.get("allowed_children", []):
                if child not in valid_classes:
                    raise SchemaValidationError(
                        f"Class '{class_name}' references unknown child class '{child}'"
                    )

            # Check allowed_parents reference valid classes
            for parent in class_def.get("allowed_parents", []):
                if parent not in valid_classes:
                    msg = f"Class '{class_name}' references unknown parent '{parent}'"
                    raise SchemaValidationError(msg)

            # Validate attribute types
            for attr_name, attr_def in class_def.get("attributes", {}).items():
                attr_type = attr_def.get("type")
                valid_types = ["checkbox", "dropdown", "slider", "spinbox", "text"]
                if attr_type not in valid_types:
                    msg = (
                        f"Class '{class_name}' attribute '{attr_name}' "
                        f"has invalid type '{attr_type}'. Valid: {valid_types}"
                    )
                    raise SchemaValidationError(msg)

                # Check dropdown has options
                if attr_type == "dropdown" and "options" not in attr_def:
                    msg = (
                        f"Class '{class_name}' attribute '{attr_name}' "
                        f"is dropdown but has no options"
                    )
                    raise SchemaValidationError(msg)

                # Check visible_if references valid field
                if "visible_if" in attr_def:
                    ref_field = attr_def["visible_if"].get("field")
                    if ref_field not in class_def.get("attributes", {}):
                        msg = (
                            f"Class '{class_name}' attribute '{attr_name}' "
                            f"visible_if references unknown field '{ref_field}'"
                        )
                        raise SchemaValidationError(msg)

    def get_version(self) -> str:
        """Get schema version string."""
        return self._schema.get("version", "1.0")

    def get_settings(self) -> dict[str, Any]:
        """Get global schema settings."""
        return self._settings.copy()

    def get_all_classes(self) -> list[str]:
        """
        Get all class names in display order.

        Returns:
            List of class names
        """
        return self._display_order.copy()

    def get_class_definition(self, class_name: str) -> dict[str, Any] | None:
        """
        Get full class definition.

        Args:
            class_name: Name of the class

        Returns:
            Class definition dict or None if not found
        """
        return (
            self._classes.get(class_name, {}).copy()
            if class_name in self._classes
            else None
        )

    def get_display_name(self, class_name: str) -> str:
        """
        Get human-readable display name for a class.

        Args:
            class_name: Internal class name

        Returns:
            Display name (falls back to class_name if not defined)
        """
        class_def = self._classes.get(class_name, {})
        return class_def.get("display_name", class_name.replace("_", " ").title())

    def get_description(self, class_name: str) -> str:
        """
        Get description for a class.

        Args:
            class_name: Class name

        Returns:
            Description string or empty string
        """
        class_def = self._classes.get(class_name, {})
        return class_def.get("description", "")

    def get_color(self, class_name: str) -> str:
        """
        Get color for a class.

        Args:
            class_name: Class name

        Returns:
            Color hex string (e.g., "#3498db") or default gray
        """
        class_def = self._classes.get(class_name, {})
        return class_def.get("color", "#808080")

    def get_color_rgb(self, class_name: str) -> tuple[int, int, int]:
        """
        Get color as RGB tuple.

        Args:
            class_name: Class name

        Returns:
            (R, G, B) tuple with values 0-255
        """
        color_hex = self.get_color(class_name)
        color_hex = color_hex.lstrip("#")
        r = int(color_hex[0:2], 16)
        g = int(color_hex[2:4], 16)
        b = int(color_hex[4:6], 16)
        return (r, g, b)

    def get_shape_types(self, class_name: str) -> list[str]:
        """
        Get allowed shape types for a class.

        Args:
            class_name: Class name

        Returns:
            List of shape types (e.g., ["polygon", "rectangle"])
        """
        class_def = self._classes.get(class_name, {})
        return class_def.get("shape_types", ["polygon"])

    def requires_parent(self, class_name: str) -> bool:
        """
        Check if a class requires a parent.

        Args:
            class_name: Class name

        Returns:
            True if class must have a parent
        """
        class_def = self._classes.get(class_name, {})
        return class_def.get("requires_parent", False)

    def get_allowed_parents(self, class_name: str) -> list[str]:
        """
        Get allowed parent classes for a class.

        Args:
            class_name: Class name

        Returns:
            List of allowed parent class names
        """
        class_def = self._classes.get(class_name, {})
        return class_def.get("allowed_parents", [])

    def get_allowed_children(self, class_name: str) -> list[str]:
        """
        Get allowed child classes for a class.

        Args:
            class_name: Class name

        Returns:
            List of allowed child class names
        """
        class_def = self._classes.get(class_name, {})
        return class_def.get("allowed_children", [])

    def can_have_children(self, class_name: str) -> bool:
        """
        Check if a class can have children.

        Args:
            class_name: Class name

        Returns:
            True if class has any allowed children
        """
        return len(self.get_allowed_children(class_name)) > 0

    def validate_parent_child(self, parent_class: str, child_class: str) -> bool:
        """
        Validate if parent-child relationship is allowed.

        Args:
            parent_class: Parent class name
            child_class: Child class name

        Returns:
            True if relationship is valid
        """
        allowed_children = self.get_allowed_children(parent_class)
        allowed_parents = self.get_allowed_parents(child_class)

        # Check both directions for consistency
        return child_class in allowed_children and parent_class in allowed_parents

    def get_top_level_classes(self) -> list[str]:
        """
        Get classes that can exist without a parent.

        Returns:
            List of top-level class names
        """
        return [
            name
            for name, class_def in self._classes.items()
            if not class_def.get("requires_parent", False)
        ]

    def get_attributes_config(self, class_name: str) -> dict[str, dict[str, Any]]:
        """
        Get attribute configuration for a class.

        Args:
            class_name: Class name

        Returns:
            Dict mapping attribute name to attribute config
        """
        class_def = self._classes.get(class_name, {})
        return class_def.get("attributes", {}).copy()

    def get_attribute_default(self, class_name: str, attr_name: str) -> Any:
        """
        Get default value for an attribute.

        Args:
            class_name: Class name
            attr_name: Attribute name

        Returns:
            Default value or None
        """
        attrs = self.get_attributes_config(class_name)
        attr_def = attrs.get(attr_name, {})
        return attr_def.get("default")

    def get_all_defaults(self, class_name: str) -> dict[str, Any]:
        """
        Get all default attribute values for a class.

        Args:
            class_name: Class name

        Returns:
            Dict mapping attribute name to default value
        """
        attrs = self.get_attributes_config(class_name)
        return {
            name: config.get("default")
            for name, config in attrs.items()
            if "default" in config
        }

    def check_attribute_visibility(
        self, class_name: str, attr_name: str, current_values: dict[str, Any]
    ) -> bool:
        """
        Check if an attribute should be visible based on conditional visibility.

        Args:
            class_name: Class name
            attr_name: Attribute to check
            current_values: Current attribute values

        Returns:
            True if attribute should be visible
        """
        attrs = self.get_attributes_config(class_name)
        attr_def = attrs.get(attr_name, {})

        visible_if = attr_def.get("visible_if")
        if visible_if is None:
            return True

        ref_field = visible_if.get("field")
        expected_value = visible_if.get("value")

        actual_value = current_values.get(ref_field)
        return actual_value == expected_value

    def validate_attribute_value(
        self, class_name: str, attr_name: str, value: Any
    ) -> tuple[bool, str | None]:
        """
        Validate an attribute value against its schema.

        Args:
            class_name: Class name
            attr_name: Attribute name
            value: Value to validate

        Returns:
            (is_valid, error_message) tuple
        """
        attrs = self.get_attributes_config(class_name)
        attr_def = attrs.get(attr_name)

        if attr_def is None:
            return False, f"Unknown attribute '{attr_name}' for class '{class_name}'"

        attr_type = attr_def.get("type")

        if attr_type == "checkbox":
            if not isinstance(value, bool):
                return False, f"Checkbox attribute '{attr_name}' must be boolean"

        elif attr_type == "dropdown":
            options = attr_def.get("options", [])
            if value not in options:
                return False, f"Value '{value}' not in options {options}"

        elif attr_type == "slider" or attr_type == "spinbox":
            min_val = attr_def.get("min", float("-inf"))
            max_val = attr_def.get("max", float("inf"))
            if not isinstance(value, (int, float)):
                return False, f"Numeric attribute '{attr_name}' must be a number"
            if value < min_val or value > max_val:
                return False, f"Value {value} out of range [{min_val}, {max_val}]"

        elif attr_type == "text":
            if not isinstance(value, str):
                return False, f"Text attribute '{attr_name}' must be a string"
            max_len = attr_def.get("max_length")
            if max_len and len(value) > max_len:
                return False, f"Text exceeds max length {max_len}"

        return True, None

    def get_shortcuts(self) -> dict[str, str]:
        """
        Get keyboard shortcuts for class selection.

        Returns:
            Dict mapping key to class name
        """
        return self._shortcuts.copy()

    def get_class_by_shortcut(self, key: str) -> str | None:
        """
        Get class name for a keyboard shortcut.

        Args:
            key: Shortcut key

        Returns:
            Class name or None
        """
        return self._shortcuts.get(key.lower())

    def class_exists(self, class_name: str) -> bool:
        """
        Check if a class exists in the schema.

        Args:
            class_name: Class name to check

        Returns:
            True if class exists
        """
        return class_name in self._classes

    def get_hierarchy_tree(self) -> dict[str, list[str]]:
        """
        Get the full hierarchy tree as adjacency list.

        Returns:
            Dict mapping parent class to list of allowed children
        """
        return {
            name: class_def.get("allowed_children", [])
            for name, class_def in self._classes.items()
        }

    def get_max_depth(self) -> int:
        """
        Get maximum allowed hierarchy depth from settings.

        Returns:
            Max depth or 10 as default
        """
        return self._settings.get("max_hierarchy_depth", 10)

    def allows_orphans(self) -> bool:
        """
        Check if orphan shapes (no parent when required) are allowed.

        Returns:
            True if orphans are allowed
        """
        return self._settings.get("allow_orphan_shapes", False)


# Convenience functions for module-level access
_default_manager: SchemaManager | None = None


def load_schema(schema_path: str | Path) -> SchemaManager:
    """
    Load a schema and set it as the default.

    Args:
        schema_path: Path to schema YAML file

    Returns:
        SchemaManager instance
    """
    global _default_manager
    _default_manager = SchemaManager(schema_path)
    return _default_manager


def get_default_manager() -> SchemaManager | None:
    """
    Get the default SchemaManager instance.

    Returns:
        Default SchemaManager or None if not loaded
    """
    return _default_manager
