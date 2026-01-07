"""
Hierarchical Labelme Application

Main application window for hierarchical annotation. Combines the hierarchy panel,
attribute panel, and canvas into a complete annotation tool.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from qtpy import QtCore
from qtpy import QtGui
from qtpy import QtWidgets
from qtpy.QtCore import Qt
from qtpy.QtCore import Slot

from labelme.hierarchical_label_file import HierarchicalAnnotationFile
from labelme.hierarchical_shape import HierarchicalShape
from labelme.hierarchical_shape import ShapeCollection
from labelme.schema_manager import SchemaManager
from labelme.widgets.attribute_panel import AttributePanelDock
from labelme.widgets.hierarchical_canvas import DrawingMode
from labelme.widgets.hierarchical_canvas import HierarchicalCanvas
from labelme.widgets.hierarchy_panel import HierarchyPanel


class HierarchicalLabelmeApp(QtWidgets.QMainWindow):
    """
    Main application window for hierarchical annotation.

    Features:
    - Three-panel layout: Hierarchy, Canvas, Attributes
    - Schema-driven class and attribute definitions
    - Parent-child shape relationships
    - COCO/YOLO export support
    - Undo/redo support
    """

    def __init__(
        self, schema_path: str | None = None, parent: QtWidgets.QWidget | None = None
    ):
        """
        Initialize the application.

        Args:
            schema_path: Path to annotation schema YAML (optional)
            parent: Parent widget
        """
        super().__init__(parent)

        # Find schema path
        if schema_path is None:
            # Look in common locations
            candidates = [
                "annotation_schema.yaml",
                os.path.join(os.path.dirname(__file__), "..", "annotation_schema.yaml"),
                os.path.expanduser("~/.labelme/annotation_schema.yaml"),
            ]
            for path in candidates:
                if os.path.exists(path):
                    schema_path = path
                    break

        if schema_path is None or not os.path.exists(schema_path):
            raise FileNotFoundError(
                "Schema file not found. Please provide annotation_schema.yaml"
            )

        # Load schema
        self.schema_manager = SchemaManager(schema_path)

        # Initialize data
        self.shapes = ShapeCollection()
        self.annotation_file: HierarchicalAnnotationFile | None = None
        self.current_file: str | None = None
        self.image_path: str | None = None
        self.is_dirty: bool = False

        # Undo/Redo stacks
        self.undo_stack: list[list[dict[str, Any]]] = []
        self.redo_stack: list[list[dict[str, Any]]] = []
        self.max_undo: int = 50

        # Setup UI
        self._setup_ui()
        self._create_actions()
        self._create_menus()
        self._create_toolbar()
        self._connect_signals()

        # Apply settings
        self._load_settings()

    def _setup_ui(self) -> None:
        """Set up the main UI layout."""
        self.setWindowTitle("Hierarchical Labelme")
        self.resize(1400, 900)

        # Central widget with canvas
        self.canvas = HierarchicalCanvas(self.schema_manager)
        self.canvas.set_shapes(self.shapes)

        # Wrap canvas in scroll area
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidget(self.canvas)
        scroll_area.setWidgetResizable(True)
        self.setCentralWidget(scroll_area)

        # Left dock: Hierarchy Panel
        self.hierarchy_dock = QtWidgets.QDockWidget("Hierarchy", self)
        self.hierarchy_panel = HierarchyPanel(self.schema_manager)
        self.hierarchy_panel.set_shapes(self.shapes)
        self.hierarchy_dock.setWidget(self.hierarchy_panel)
        self.hierarchy_dock.setFeatures(
            QtWidgets.QDockWidget.DockWidgetMovable
            | QtWidgets.QDockWidget.DockWidgetFloatable
        )
        self.hierarchy_dock.setMinimumWidth(200)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.hierarchy_dock)

        # Right dock: Attribute Panel
        self.attribute_dock = AttributePanelDock(self.schema_manager)
        self.attribute_panel = self.attribute_dock.panel
        self.addDockWidget(Qt.RightDockWidgetArea, self.attribute_dock)

        # Status bar
        self.status_bar = self.statusBar()
        self.mode_label = QtWidgets.QLabel("Ready")
        self.status_bar.addWidget(self.mode_label)

        # Class selector in status bar
        self.class_combo = QtWidgets.QComboBox()
        self.class_combo.setMinimumWidth(150)
        self._populate_class_combo()
        self.status_bar.addPermanentWidget(QtWidgets.QLabel("Class:"))
        self.status_bar.addPermanentWidget(self.class_combo)

        # Shape counter
        self.shape_count_label = QtWidgets.QLabel("Shapes: 0")
        self.status_bar.addPermanentWidget(self.shape_count_label)

    def _populate_class_combo(self) -> None:
        """Populate the class selection combo box."""
        self.class_combo.clear()
        for class_name in self.schema_manager.get_all_classes():
            display_name = self.schema_manager.get_display_name(class_name)
            color = self.schema_manager.get_color(class_name)
            self.class_combo.addItem(display_name, class_name)
            # Set item color
            idx = self.class_combo.count() - 1
            self.class_combo.setItemData(idx, QtGui.QColor(color), Qt.ForegroundRole)

    def _create_actions(self) -> None:
        """Create menu and toolbar actions."""
        # File actions
        self.action_open_image = QtWidgets.QAction("Open Image...", self)
        self.action_open_image.setShortcut("Ctrl+O")
        self.action_open_image.triggered.connect(self.open_image)

        self.action_open_annotation = QtWidgets.QAction("Open Annotation...", self)
        self.action_open_annotation.setShortcut("Ctrl+Shift+O")
        self.action_open_annotation.triggered.connect(self.open_annotation)

        self.action_save = QtWidgets.QAction("Save", self)
        self.action_save.setShortcut("Ctrl+S")
        self.action_save.triggered.connect(self.save)

        self.action_save_as = QtWidgets.QAction("Save As...", self)
        self.action_save_as.setShortcut("Ctrl+Shift+S")
        self.action_save_as.triggered.connect(self.save_as)

        self.action_export_coco = QtWidgets.QAction("Export COCO...", self)
        self.action_export_coco.triggered.connect(self.export_coco)

        self.action_export_yolo = QtWidgets.QAction("Export YOLO...", self)
        self.action_export_yolo.triggered.connect(self.export_yolo)

        self.action_exit = QtWidgets.QAction("Exit", self)
        self.action_exit.setShortcut("Ctrl+Q")
        self.action_exit.triggered.connect(self.close)

        # Edit actions
        self.action_undo = QtWidgets.QAction("Undo", self)
        self.action_undo.setShortcut("Ctrl+Z")
        self.action_undo.triggered.connect(self.undo)

        self.action_redo = QtWidgets.QAction("Redo", self)
        self.action_redo.setShortcut("Ctrl+Shift+Z")
        self.action_redo.triggered.connect(self.redo)

        self.action_delete = QtWidgets.QAction("Delete", self)
        self.action_delete.setShortcut("Delete")
        self.action_delete.triggered.connect(self.delete_selected)

        # View actions
        self.action_zoom_in = QtWidgets.QAction("Zoom In", self)
        self.action_zoom_in.setShortcut("Ctrl+=")
        self.action_zoom_in.triggered.connect(self.canvas.zoom_in)

        self.action_zoom_out = QtWidgets.QAction("Zoom Out", self)
        self.action_zoom_out.setShortcut("Ctrl+-")
        self.action_zoom_out.triggered.connect(self.canvas.zoom_out)

        self.action_fit_window = QtWidgets.QAction("Fit Window", self)
        self.action_fit_window.setShortcut("Ctrl+0")
        self.action_fit_window.triggered.connect(self.canvas.fit_window)

        self.action_toggle_hierarchy = QtWidgets.QAction("Toggle Hierarchy Panel", self)
        self.action_toggle_hierarchy.setCheckable(True)
        self.action_toggle_hierarchy.setChecked(True)
        self.action_toggle_hierarchy.triggered.connect(
            lambda checked: self.hierarchy_dock.setVisible(checked)
        )

        self.action_toggle_attributes = QtWidgets.QAction(
            "Toggle Attribute Panel", self
        )
        self.action_toggle_attributes.setCheckable(True)
        self.action_toggle_attributes.setChecked(True)
        self.action_toggle_attributes.triggered.connect(
            lambda checked: self.attribute_dock.setVisible(checked)
        )

        # Mode actions
        self.action_edit_mode = QtWidgets.QAction("Edit Mode", self)
        self.action_edit_mode.setShortcut("E")
        self.action_edit_mode.triggered.connect(self.canvas.enter_edit_mode)

        self.action_create_mode = QtWidgets.QAction("Create Mode", self)
        self.action_create_mode.setShortcut("N")
        self.action_create_mode.triggered.connect(self._enter_create_mode)

    def _create_menus(self) -> None:
        """Create menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")
        file_menu.addAction(self.action_open_image)
        file_menu.addAction(self.action_open_annotation)
        file_menu.addSeparator()
        file_menu.addAction(self.action_save)
        file_menu.addAction(self.action_save_as)
        file_menu.addSeparator()

        export_menu = file_menu.addMenu("Export")
        export_menu.addAction(self.action_export_coco)
        export_menu.addAction(self.action_export_yolo)

        file_menu.addSeparator()
        file_menu.addAction(self.action_exit)

        # Edit menu
        edit_menu = menubar.addMenu("Edit")
        edit_menu.addAction(self.action_undo)
        edit_menu.addAction(self.action_redo)
        edit_menu.addSeparator()
        edit_menu.addAction(self.action_delete)

        # View menu
        view_menu = menubar.addMenu("View")
        view_menu.addAction(self.action_zoom_in)
        view_menu.addAction(self.action_zoom_out)
        view_menu.addAction(self.action_fit_window)
        view_menu.addSeparator()
        view_menu.addAction(self.action_toggle_hierarchy)
        view_menu.addAction(self.action_toggle_attributes)

        # Mode menu
        mode_menu = menubar.addMenu("Mode")
        mode_menu.addAction(self.action_edit_mode)
        mode_menu.addAction(self.action_create_mode)

    def _create_toolbar(self) -> None:
        """Create toolbar."""
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)

        toolbar.addAction(self.action_open_image)
        toolbar.addAction(self.action_save)
        toolbar.addSeparator()
        toolbar.addAction(self.action_undo)
        toolbar.addAction(self.action_redo)
        toolbar.addSeparator()
        toolbar.addAction(self.action_zoom_in)
        toolbar.addAction(self.action_zoom_out)
        toolbar.addAction(self.action_fit_window)
        toolbar.addSeparator()
        toolbar.addAction(self.action_edit_mode)
        toolbar.addAction(self.action_create_mode)

    def _connect_signals(self) -> None:
        """Connect widget signals."""
        # Hierarchy panel signals
        self.hierarchy_panel.shape_selected.connect(self.on_shape_selected)
        self.hierarchy_panel.add_child_requested.connect(self.on_add_child_requested)
        self.hierarchy_panel.delete_requested.connect(self.on_delete_requested)
        self.hierarchy_panel.reparent_requested.connect(self.on_reparent_requested)

        # Canvas signals
        self.canvas.shape_created.connect(self.on_shape_created)
        self.canvas.child_created.connect(self.on_child_created)
        self.canvas.shape_selected.connect(self.on_shape_selected)
        self.canvas.status_message.connect(self._update_status)

        # Attribute panel signals
        self.attribute_panel.attribute_changed.connect(self.on_attribute_changed)

        # Class combo
        self.class_combo.currentIndexChanged.connect(self._on_class_changed)

    def _load_settings(self) -> None:
        """Load application settings."""
        settings = QtCore.QSettings("Labelme", "HierarchicalLabelme")
        geometry = settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        state = settings.value("windowState")
        if state:
            self.restoreState(state)

    def _save_settings(self) -> None:
        """Save application settings."""
        settings = QtCore.QSettings("Labelme", "HierarchicalLabelme")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """Handle close event."""
        if self.is_dirty:
            reply = QtWidgets.QMessageBox.question(
                self,
                "Save Changes?",
                "There are unsaved changes. Save before closing?",
                QtWidgets.QMessageBox.Save
                | QtWidgets.QMessageBox.Discard
                | QtWidgets.QMessageBox.Cancel,
                QtWidgets.QMessageBox.Save,
            )

            if reply == QtWidgets.QMessageBox.Save:
                if not self.save():
                    event.ignore()
                    return
            elif reply == QtWidgets.QMessageBox.Cancel:
                event.ignore()
                return

        self._save_settings()
        event.accept()

    # File operations

    @Slot()
    def open_image(self) -> None:
        """Open an image file."""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tiff);;All Files (*)",
        )

        if file_path:
            self._load_image(file_path)

    def _load_image(self, file_path: str) -> bool:
        """
        Load an image file.

        Args:
            file_path: Path to image

        Returns:
            True if successful
        """
        if not self.canvas.load_image(file_path):
            QtWidgets.QMessageBox.warning(
                self, "Error", f"Could not load image: {file_path}"
            )
            return False

        self.image_path = file_path
        self.setWindowTitle(f"Hierarchical Labelme - {os.path.basename(file_path)}")

        # Check for existing annotation
        json_path = os.path.splitext(file_path)[0] + ".json"
        if os.path.exists(json_path):
            reply = QtWidgets.QMessageBox.question(
                self,
                "Load Annotation?",
                f"Found existing annotation: {os.path.basename(json_path)}\n\nLoad it?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.Yes,
            )
            if reply == QtWidgets.QMessageBox.Yes:
                self._load_annotation(json_path)

        self.canvas.fit_window()
        return True

    @Slot()
    def open_annotation(self) -> None:
        """Open an annotation file."""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Annotation", "", "JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            self._load_annotation(file_path)

    def _load_annotation(self, file_path: str) -> bool:
        """
        Load an annotation file.

        Args:
            file_path: Path to JSON

        Returns:
            True if successful
        """
        try:
            self.annotation_file = HierarchicalAnnotationFile(file_path)
            self.shapes = self.annotation_file.shapes
            self.current_file = file_path

            # Update widgets
            self.canvas.set_shapes(self.shapes)
            self.hierarchy_panel.set_shapes(self.shapes)

            # Load image if available
            if self.annotation_file.image_path and not self.image_path:
                img_dir = os.path.dirname(file_path)
                img_path = os.path.join(img_dir, self.annotation_file.image_path)
                if os.path.exists(img_path):
                    self.canvas.load_image(img_path)
                    self.image_path = img_path

            self._update_shape_count()
            self.is_dirty = False
            self._update_status("Annotation loaded")
            return True

        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self, "Error", f"Could not load annotation: {e}"
            )
            return False

    @Slot()
    def save(self) -> bool:
        """
        Save the current annotation.

        Returns:
            True if successful
        """
        if self.current_file:
            return self._save_to_file(self.current_file)
        else:
            return self.save_as()

    @Slot()
    def save_as(self) -> bool:
        """
        Save annotation to a new file.

        Returns:
            True if successful
        """
        default_path = ""
        if self.image_path:
            default_path = os.path.splitext(self.image_path)[0] + ".json"

        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Annotation", default_path, "JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            return self._save_to_file(file_path)
        return False

    def _save_to_file(self, file_path: str) -> bool:
        """
        Save annotation to file.

        Args:
            file_path: Path to save to

        Returns:
            True if successful
        """
        try:
            if self.annotation_file is None:
                self.annotation_file = HierarchicalAnnotationFile()

            self.annotation_file.shapes = self.shapes

            if self.image_path:
                self.annotation_file.image_path = os.path.basename(self.image_path)
                size = self.canvas.get_image_size()
                if size:
                    self.annotation_file.image_width = size[0]
                    self.annotation_file.image_height = size[1]

            self.annotation_file.save(file_path, include_image_data=False)
            self.current_file = file_path
            self.is_dirty = False
            self._update_status(f"Saved to {os.path.basename(file_path)}")
            return True

        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self, "Error", f"Could not save annotation: {e}"
            )
            return False

    @Slot()
    def export_coco(self) -> None:
        """Export annotations to COCO format."""
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export COCO", "", "JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            try:
                if self.annotation_file is None:
                    self.annotation_file = HierarchicalAnnotationFile()
                    self.annotation_file.shapes = self.shapes
                    if self.image_path:
                        self.annotation_file.image_path = os.path.basename(
                            self.image_path
                        )
                        size = self.canvas.get_image_size()
                        if size:
                            self.annotation_file.image_width = size[0]
                            self.annotation_file.image_height = size[1]

                self.annotation_file.export_coco(file_path)
                self._update_status(f"Exported to {os.path.basename(file_path)}")
            except Exception as e:
                QtWidgets.QMessageBox.warning(self, "Error", f"Export failed: {e}")

    @Slot()
    def export_yolo(self) -> None:
        """Export annotations to YOLO format."""
        dir_path = QtWidgets.QFileDialog.getExistingDirectory(self, "Export YOLO", "")

        if dir_path:
            try:
                if self.annotation_file is None:
                    self.annotation_file = HierarchicalAnnotationFile()
                    self.annotation_file.shapes = self.shapes
                    if self.image_path:
                        self.annotation_file.image_path = os.path.basename(
                            self.image_path
                        )
                        size = self.canvas.get_image_size()
                        if size:
                            self.annotation_file.image_width = size[0]
                            self.annotation_file.image_height = size[1]

                self.annotation_file.export_yolo(dir_path)
                self._update_status(f"Exported to {dir_path}")
            except Exception as e:
                QtWidgets.QMessageBox.warning(self, "Error", f"Export failed: {e}")

    # Edit operations

    def _save_undo_state(self) -> None:
        """Save current state for undo."""
        state = self.shapes.to_dict_list()
        self.undo_stack.append(state)
        if len(self.undo_stack) > self.max_undo:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    @Slot()
    def undo(self) -> None:
        """Undo last action."""
        if not self.undo_stack:
            return

        # Save current state for redo
        current = self.shapes.to_dict_list()
        self.redo_stack.append(current)

        # Restore previous state
        state = self.undo_stack.pop()
        self.shapes.from_dict_list(state)

        # Update UI
        self._refresh_all()
        self.is_dirty = True

    @Slot()
    def redo(self) -> None:
        """Redo last undone action."""
        if not self.redo_stack:
            return

        # Save current state for undo
        current = self.shapes.to_dict_list()
        self.undo_stack.append(current)

        # Restore next state
        state = self.redo_stack.pop()
        self.shapes.from_dict_list(state)

        # Update UI
        self._refresh_all()
        self.is_dirty = True

    @Slot()
    def delete_selected(self) -> None:
        """Delete selected shapes."""
        selected = self.canvas.get_selected_shapes()
        if not selected:
            return

        for shape in selected:
            self.on_delete_requested(shape.shape_id)

    # Signal handlers

    @Slot(str)
    def on_shape_selected(self, shape_id: str) -> None:
        """Handle shape selection."""
        shape = self.shapes.get_shape(shape_id)
        if shape:
            # Update attribute panel
            self.attribute_panel.set_shape(shape)

            # Update hierarchy selection
            self.hierarchy_panel.select_shape(shape_id)

            # Update canvas selection
            self.canvas.select_shape(shape_id)

            # Update status
            display_name = self.schema_manager.get_display_name(shape.label)
            self._update_status(f"Selected: {display_name}")

    @Slot(str, str)
    def on_add_child_requested(self, parent_id: str, child_class: str) -> None:
        """Handle request to add a child shape."""
        parent = self.shapes.get_shape(parent_id)
        if not parent:
            return

        # Validate
        if not self.schema_manager.validate_parent_child(parent.label, child_class):
            QtWidgets.QMessageBox.warning(
                self,
                "Invalid Relationship",
                f"Cannot add {child_class} as child of {parent.label}",
            )
            return

        # Enter child drawing mode
        self.canvas.enter_child_mode(parent, child_class)

        parent_name = self.schema_manager.get_display_name(parent.label)
        child_name = self.schema_manager.get_display_name(child_class)
        self._update_status(f"Drawing {child_name} for {parent_name}")

    @Slot(str)
    def on_delete_requested(self, shape_id: str) -> None:
        """Handle request to delete a shape."""
        shape = self.shapes.get_shape(shape_id)
        if not shape:
            return

        # Check for children
        if shape.has_children():
            reply = QtWidgets.QMessageBox.question(
                self,
                "Delete Shape",
                "This shape has children. Delete children too?",
                QtWidgets.QMessageBox.Yes
                | QtWidgets.QMessageBox.No
                | QtWidgets.QMessageBox.Cancel,
                QtWidgets.QMessageBox.Yes,
            )

            if reply == QtWidgets.QMessageBox.Cancel:
                return

            remove_children = reply == QtWidgets.QMessageBox.Yes
        else:
            remove_children = True

        # Save undo state
        self._save_undo_state()

        # Remove shape
        self.shapes.remove_shape(shape_id, remove_children=remove_children)

        # Update UI
        self._refresh_all()
        self.is_dirty = True
        self._update_status("Shape deleted")

    @Slot(str, str)
    def on_reparent_requested(self, shape_id: str, new_parent_id: str) -> None:
        """Handle request to reparent a shape."""
        shape = self.shapes.get_shape(shape_id)
        if not shape:
            return

        new_parent = None
        if new_parent_id:
            new_parent = self.shapes.get_shape(new_parent_id)
            if not new_parent:
                return

            # Validate
            if not self.schema_manager.validate_parent_child(
                new_parent.label, shape.label
            ):
                QtWidgets.QMessageBox.warning(
                    self,
                    "Invalid Relationship",
                    f"Cannot move {shape.label} under {new_parent.label}",
                )
                return
        else:
            # Moving to root - check if allowed
            if self.schema_manager.requires_parent(shape.label):
                QtWidgets.QMessageBox.warning(
                    self, "Invalid Operation", f"{shape.label} requires a parent"
                )
                return

        # Save undo state
        self._save_undo_state()

        # Reparent
        self.shapes.reparent(shape, new_parent)

        # Update UI
        self._refresh_all()
        self.is_dirty = True
        self._update_status("Shape reparented")

    @Slot(object)
    def on_shape_created(self, shape: HierarchicalShape) -> None:
        """Handle new shape creation."""
        self._save_undo_state()

        # Update UI
        self.hierarchy_panel.add_shape(shape)
        self._update_shape_count()
        self.is_dirty = True

        display_name = self.schema_manager.get_display_name(shape.label)
        self._update_status(f"Created {display_name}")

    @Slot(object)
    def on_child_created(self, shape: HierarchicalShape) -> None:
        """Handle child shape creation."""
        self._save_undo_state()

        # Update UI
        self.hierarchy_panel.refresh()
        self._update_shape_count()
        self.is_dirty = True

        display_name = self.schema_manager.get_display_name(shape.label)
        self._update_status(f"Created child {display_name}")

    @Slot(str, str, object)
    def on_attribute_changed(self, shape_id: str, attr_name: str, value: Any) -> None:
        """Handle attribute change."""
        self._save_undo_state()
        self.is_dirty = True

    # Helpers

    def _enter_create_mode(self) -> None:
        """Enter create mode with current class."""
        class_name = self.class_combo.currentData()
        if class_name:
            self.canvas.enter_create_mode(class_name)

    def _on_class_changed(self, index: int) -> None:
        """Handle class selection change."""
        class_name = self.class_combo.currentData()
        if class_name and self.canvas.mode == DrawingMode.CREATE:
            self.canvas.enter_create_mode(class_name)

    def _refresh_all(self) -> None:
        """Refresh all UI components."""
        self.canvas.set_shapes(self.shapes)
        self.hierarchy_panel.set_shapes(self.shapes)
        self.attribute_panel.clear()
        self.canvas.clear_selection()
        self._update_shape_count()

    def _update_shape_count(self) -> None:
        """Update shape count display."""
        count = len(self.shapes)
        self.shape_count_label.setText(f"Shapes: {count}")

    def _update_status(self, message: str) -> None:
        """Update status bar message."""
        self.mode_label.setText(message)

    # Keyboard shortcuts

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        """Handle global keyboard shortcuts."""
        key = event.key()

        # Check schema shortcuts
        shortcuts = self.schema_manager.get_shortcuts()
        key_char = event.text().lower()

        if key_char in shortcuts:
            class_name = shortcuts[key_char]
            # Find and select in combo
            for i in range(self.class_combo.count()):
                if self.class_combo.itemData(i) == class_name:
                    self.class_combo.setCurrentIndex(i)
                    break
            self.canvas.enter_create_mode(class_name)
            return

        # Other shortcuts
        if key == Qt.Key_Tab:
            # Cycle through shapes
            selected = self.canvas.get_selected_shapes()
            all_shapes = list(self.shapes)
            if all_shapes:
                if selected:
                    idx = next(
                        (
                            i
                            for i, s in enumerate(all_shapes)
                            if s.shape_id == selected[0].shape_id
                        ),
                        -1,
                    )
                    next_idx = (idx + 1) % len(all_shapes)
                else:
                    next_idx = 0
                self.canvas.select_shape(all_shapes[next_idx].shape_id)
            return

        super().keyPressEvent(event)


def main():
    """Main entry point."""
    app = QtWidgets.QApplication(sys.argv)

    # Find schema
    schema_path = None
    if len(sys.argv) > 1:
        if sys.argv[1].endswith(".yaml") or sys.argv[1].endswith(".yml"):
            schema_path = sys.argv[1]

    try:
        window = HierarchicalLabelmeApp(schema_path=schema_path)
        window.show()

        # Load image if provided
        for arg in sys.argv[1:]:
            if not arg.endswith((".yaml", ".yml")):
                if arg.endswith(".json"):
                    window._load_annotation(arg)
                else:
                    window._load_image(arg)
                break

        sys.exit(app.exec_())
    except FileNotFoundError as e:
        QtWidgets.QMessageBox.critical(None, "Error", str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
