"""
Attribute Panel Widget for Hierarchical Labelme

This widget dynamically generates form fields based on the selected shape's
class attributes as defined in the schema. It supports various input types
and conditional visibility.
"""

from __future__ import annotations

from typing import Any

from qtpy import QtWidgets
from qtpy.QtCore import Qt
from qtpy.QtCore import Signal

from labelme.hierarchical_shape import HierarchicalShape
from labelme.schema_manager import SchemaManager


class AttributePanel(QtWidgets.QWidget):
    """
    Panel for editing shape-specific attributes.

    Features:
    - Dynamically generates form based on schema
    - Supports checkbox, dropdown, slider, spinbox, text inputs
    - Handles conditional visibility (visible_if)
    - Auto-saves on value change
    - Shows shape info header

    Signals:
        attribute_changed(str, str, Any): Emitted when an attribute changes
            (shape_id, attr_name, value)
    """

    attribute_changed = Signal(str, str, object)  # shape_id, attr_name, value

    def __init__(
        self, schema_manager: SchemaManager, parent: QtWidgets.QWidget | None = None
    ):
        """
        Initialize attribute panel.

        Args:
            schema_manager: SchemaManager for attribute definitions
            parent: Parent widget
        """
        super().__init__(parent)

        self.schema_manager = schema_manager
        self.current_shape: HierarchicalShape | None = None
        self._widgets: dict[str, QtWidgets.QWidget] = {}
        self._labels: dict[str, QtWidgets.QLabel] = {}
        self._updating: bool = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the panel UI."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        # Header section
        self.header_widget = QtWidgets.QWidget()
        header_layout = QtWidgets.QVBoxLayout(self.header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(2)

        self.title_label = QtWidgets.QLabel("No Shape Selected")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(self.title_label)

        self.id_label = QtWidgets.QLabel("")
        self.id_label.setStyleSheet("color: gray; font-size: 10px;")
        header_layout.addWidget(self.id_label)

        layout.addWidget(self.header_widget)

        # Separator
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(line)

        # Scroll area for attributes
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)

        self.form_widget = QtWidgets.QWidget()
        self.form_layout = QtWidgets.QFormLayout(self.form_widget)
        self.form_layout.setContentsMargins(0, 0, 0, 0)
        self.form_layout.setSpacing(8)
        self.form_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        scroll_area.setWidget(self.form_widget)
        layout.addWidget(scroll_area, 1)

        # Info section at bottom
        self.info_label = QtWidgets.QLabel("")
        self.info_label.setStyleSheet("color: gray; font-size: 10px;")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

    def set_shape(self, shape: HierarchicalShape | None) -> None:
        """
        Set the shape to edit.

        Args:
            shape: Shape to display/edit, or None to clear
        """
        self.current_shape = shape
        self._rebuild_form()

    def _rebuild_form(self) -> None:
        """Rebuild the form for the current shape."""
        # Clear existing widgets
        self._clear_form()

        if not self.current_shape:
            self.title_label.setText("No Shape Selected")
            self.id_label.setText("")
            self.info_label.setText("")
            return

        shape = self.current_shape

        # Update header
        display_name = self.schema_manager.get_display_name(shape.label)
        self.title_label.setText(f"{display_name} Properties")
        self.id_label.setText(f"ID: {shape.shape_id[:16]}...")

        # Get attribute config
        attrs_config = self.schema_manager.get_attributes_config(shape.label)

        if not attrs_config:
            self.info_label.setText("No attributes defined for this class")
            return

        # Build form fields
        for attr_name, attr_config in attrs_config.items():
            self._create_field(attr_name, attr_config)

        # Update visibility
        self._update_visibility()

        # Show info
        description = self.schema_manager.get_description(shape.label)
        if description:
            self.info_label.setText(description)
        else:
            self.info_label.setText("")

    def _clear_form(self) -> None:
        """Clear all form fields."""
        # Remove all widgets from form layout
        while self.form_layout.count() > 0:
            item = self.form_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._widgets.clear()
        self._labels.clear()

    def _create_field(self, attr_name: str, attr_config: dict[str, Any]) -> None:
        """
        Create a form field for an attribute.

        Args:
            attr_name: Attribute name
            attr_config: Attribute configuration from schema
        """
        attr_type = attr_config.get("type", "text")
        label_text = attr_config.get("label", attr_name.replace("_", " ").title())
        required = attr_config.get("required", False)

        if required:
            label_text += " *"

        # Create label
        label = QtWidgets.QLabel(label_text)
        self._labels[attr_name] = label

        # Create widget based on type
        widget: QtWidgets.QWidget

        if attr_type == "checkbox":
            widget = self._create_checkbox(attr_name, attr_config)
        elif attr_type == "dropdown":
            widget = self._create_dropdown(attr_name, attr_config)
        elif attr_type == "slider":
            widget = self._create_slider(attr_name, attr_config)
        elif attr_type == "spinbox":
            widget = self._create_spinbox(attr_name, attr_config)
        elif attr_type == "text":
            widget = self._create_text(attr_name, attr_config)
        else:
            # Fallback to text
            widget = self._create_text(attr_name, attr_config)

        self._widgets[attr_name] = widget
        self.form_layout.addRow(label, widget)

    def _create_checkbox(
        self, attr_name: str, config: dict[str, Any]
    ) -> QtWidgets.QCheckBox:
        """Create a checkbox widget."""
        checkbox = QtWidgets.QCheckBox()

        # Set initial value
        if self.current_shape:
            value = self.current_shape.get_attribute(
                attr_name, config.get("default", False)
            )
            checkbox.setChecked(bool(value))

        # Connect signal
        checkbox.stateChanged.connect(
            lambda state: self._on_value_changed(attr_name, state == Qt.Checked)
        )

        return checkbox

    def _create_dropdown(
        self, attr_name: str, config: dict[str, Any]
    ) -> QtWidgets.QComboBox:
        """Create a dropdown widget."""
        combo = QtWidgets.QComboBox()

        options = config.get("options", [])
        combo.addItems(options)

        # Set initial value
        if self.current_shape:
            value = self.current_shape.get_attribute(attr_name, config.get("default"))
            if value in options:
                combo.setCurrentText(value)

        # Connect signal
        combo.currentTextChanged.connect(
            lambda text: self._on_value_changed(attr_name, text)
        )

        return combo

    def _create_slider(
        self, attr_name: str, config: dict[str, Any]
    ) -> QtWidgets.QWidget:
        """Create a slider widget with value label."""
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        min_val = config.get("min", 0)
        max_val = config.get("max", 100)
        step = config.get("step", 1)

        slider = QtWidgets.QSlider(Qt.Horizontal)
        slider.setMinimum(min_val)
        slider.setMaximum(max_val)
        slider.setSingleStep(step)
        slider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        slider.setTickInterval(max((max_val - min_val) // 10, 1))

        value_label = QtWidgets.QLabel(str(min_val))
        value_label.setMinimumWidth(40)
        value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # Set initial value
        if self.current_shape:
            value = self.current_shape.get_attribute(
                attr_name, config.get("default", min_val)
            )
            slider.setValue(int(value))
            value_label.setText(str(int(value)))

        # Connect signals
        def on_slider_changed(val):
            value_label.setText(str(val))
            self._on_value_changed(attr_name, val)

        slider.valueChanged.connect(on_slider_changed)

        layout.addWidget(slider, 1)
        layout.addWidget(value_label)

        # Store slider reference for value updates
        container.slider = slider
        container.value_label = value_label

        return container

    def _create_spinbox(
        self, attr_name: str, config: dict[str, Any]
    ) -> QtWidgets.QSpinBox:
        """Create a spinbox widget."""
        spinbox = QtWidgets.QSpinBox()

        min_val = config.get("min", 0)
        max_val = config.get("max", 999999)
        step = config.get("step", 1)

        spinbox.setMinimum(min_val)
        spinbox.setMaximum(max_val)
        spinbox.setSingleStep(step)

        # Set initial value
        if self.current_shape:
            value = self.current_shape.get_attribute(
                attr_name, config.get("default", min_val)
            )
            spinbox.setValue(int(value))

        # Connect signal
        spinbox.valueChanged.connect(lambda val: self._on_value_changed(attr_name, val))

        return spinbox

    def _create_text(
        self, attr_name: str, config: dict[str, Any]
    ) -> QtWidgets.QLineEdit:
        """Create a text input widget."""
        line_edit = QtWidgets.QLineEdit()

        max_length = config.get("max_length")
        if max_length:
            line_edit.setMaxLength(max_length)

        placeholder = config.get("placeholder", "")
        if placeholder:
            line_edit.setPlaceholderText(placeholder)

        # Set initial value
        if self.current_shape:
            value = self.current_shape.get_attribute(
                attr_name, config.get("default", "")
            )
            line_edit.setText(str(value))

        # Connect signal
        line_edit.textChanged.connect(
            lambda text: self._on_value_changed(attr_name, text)
        )

        return line_edit

    def _on_value_changed(self, attr_name: str, value: Any) -> None:
        """Handle attribute value change."""
        if self._updating:
            return

        if not self.current_shape:
            return

        # Update shape
        self.current_shape.set_attribute(attr_name, value)

        # Update visibility
        self._update_visibility()

        # Emit signal
        self.attribute_changed.emit(self.current_shape.shape_id, attr_name, value)

    def _update_visibility(self) -> None:
        """Update visibility of fields based on visible_if conditions."""
        if not self.current_shape:
            return

        self.schema_manager.get_attributes_config(self.current_shape.label)
        current_values = self.current_shape.attributes

        for attr_name, widget in self._widgets.items():
            visible = self.schema_manager.check_attribute_visibility(
                self.current_shape.label, attr_name, current_values
            )

            widget.setVisible(visible)

            # Also hide label
            if attr_name in self._labels:
                self._labels[attr_name].setVisible(visible)

    def get_values(self) -> dict[str, Any]:
        """
        Get all current attribute values.

        Returns:
            Dict mapping attribute name to value
        """
        if not self.current_shape:
            return {}

        return self.current_shape.attributes.copy()

    def set_values(self, values: dict[str, Any]) -> None:
        """
        Set multiple attribute values.

        Args:
            values: Dict of attribute name to value
        """
        if not self.current_shape:
            return

        self._updating = True
        try:
            for attr_name, value in values.items():
                self.current_shape.set_attribute(attr_name, value)
                self._update_widget_value(attr_name, value)

            self._update_visibility()
        finally:
            self._updating = False

    def _update_widget_value(self, attr_name: str, value: Any) -> None:
        """
        Update a widget's displayed value.

        Args:
            attr_name: Attribute name
            value: New value
        """
        widget = self._widgets.get(attr_name)
        if not widget:
            return

        if isinstance(widget, QtWidgets.QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, QtWidgets.QComboBox):
            widget.setCurrentText(str(value))
        elif isinstance(widget, QtWidgets.QSpinBox):
            widget.setValue(int(value))
        elif isinstance(widget, QtWidgets.QLineEdit):
            widget.setText(str(value))
        elif hasattr(widget, "slider"):
            # Slider container
            widget.slider.setValue(int(value))
            widget.value_label.setText(str(int(value)))

    def refresh(self) -> None:
        """Refresh the form with current shape values."""
        if self.current_shape:
            self._rebuild_form()

    def clear(self) -> None:
        """Clear the panel."""
        self.set_shape(None)

    def is_valid(self) -> bool:
        """
        Check if all required fields are filled.

        Returns:
            True if all required fields have values
        """
        if not self.current_shape:
            return True

        attrs_config = self.schema_manager.get_attributes_config(
            self.current_shape.label
        )

        for attr_name, config in attrs_config.items():
            if config.get("required", False):
                value = self.current_shape.get_attribute(attr_name)
                if value is None or value == "":
                    return False

        return True

    def get_validation_errors(self) -> list[str]:
        """
        Get list of validation errors.

        Returns:
            List of error messages
        """
        errors: list[str] = []

        if not self.current_shape:
            return errors

        attrs_config = self.schema_manager.get_attributes_config(
            self.current_shape.label
        )

        for attr_name, config in attrs_config.items():
            # Check required
            if config.get("required", False):
                value = self.current_shape.get_attribute(attr_name)
                if value is None or value == "":
                    label = config.get("label", attr_name)
                    errors.append(f"{label} is required")

            # Validate value
            value = self.current_shape.get_attribute(attr_name)
            if value is not None:
                valid, error = self.schema_manager.validate_attribute_value(
                    self.current_shape.label, attr_name, value
                )
                if not valid and error is not None:
                    errors.append(error)

        return errors


class AttributePanelDock(QtWidgets.QDockWidget):
    """Dock widget wrapper for AttributePanel."""

    def __init__(
        self, schema_manager: SchemaManager, parent: QtWidgets.QWidget | None = None
    ):
        """
        Initialize dock widget.

        Args:
            schema_manager: SchemaManager for attributes
            parent: Parent widget
        """
        super().__init__("Properties", parent)

        self.panel = AttributePanel(schema_manager)
        self.setWidget(self.panel)

        # Dock settings
        self.setFeatures(
            QtWidgets.QDockWidget.DockWidgetMovable
            | QtWidgets.QDockWidget.DockWidgetFloatable
        )
        self.setMinimumWidth(200)

    def set_shape(self, shape: HierarchicalShape | None) -> None:
        """Set shape for the panel."""
        self.panel.set_shape(shape)
