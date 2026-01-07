"""
Hierarchy Panel Widget for Hierarchical Labelme

This widget displays shapes in a tree structure showing parent-child
relationships. It supports drag-drop reparenting, context menus for
adding children, and emits signals for shape selection and management.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from qtpy import QtCore, QtGui, QtWidgets
from qtpy.QtCore import Qt, Signal

from labelme.schema_manager import SchemaManager
from labelme.hierarchical_shape import HierarchicalShape, ShapeCollection


class HierarchyPanel(QtWidgets.QTreeWidget):
    """
    Tree widget displaying hierarchical shape structure.

    Features:
    - Displays shapes in tree with parent-child relationships
    - Shows shape labels with schema-defined colors
    - Right-click context menu for add child, delete, etc.
    - Drag-drop support for reparenting (with schema validation)
    - Emits signals for shape operations

    Signals:
        shape_selected(str): Emitted when a shape is selected (emits shape_id)
        add_child_requested(str, str): Emitted when user requests to add child
            (parent_id, child_class)
        delete_requested(str): Emitted when user requests to delete shape
        reparent_requested(str, str): Emitted when user drags shape to new parent
            (shape_id, new_parent_id)
    """

    # Signals
    shape_selected = Signal(str)  # shape_id
    shape_double_clicked = Signal(str)  # shape_id
    add_child_requested = Signal(str, str)  # parent_id, child_class
    delete_requested = Signal(str)  # shape_id
    reparent_requested = Signal(str, str)  # shape_id, new_parent_id (empty string for root)

    def __init__(self, schema_manager: SchemaManager, parent: Optional[QtWidgets.QWidget] = None):
        """
        Initialize hierarchy panel.

        Args:
            schema_manager: SchemaManager for class definitions
            parent: Parent widget
        """
        super().__init__(parent)

        self.schema_manager = schema_manager
        self.shapes: Optional[ShapeCollection] = None
        self._shape_items: Dict[str, QtWidgets.QTreeWidgetItem] = {}
        self._class_counters: Dict[str, int] = {}

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the tree widget UI."""
        self.setHeaderLabel("Shapes")
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

        # Enable drag and drop
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)

        # Visual settings
        self.setIndentation(20)
        self.setAnimated(True)
        self.setExpandsOnDoubleClick(True)

        # Allow expansion even without children
        self.setRootIsDecorated(True)

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        self.itemSelectionChanged.connect(self._on_selection_changed)
        self.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def set_shapes(self, shapes: ShapeCollection) -> None:
        """
        Set the shape collection to display.

        Args:
            shapes: ShapeCollection to display
        """
        self.shapes = shapes
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the tree from the current shape collection."""
        self.clear()
        self._shape_items.clear()
        self._class_counters.clear()

        if not self.shapes:
            return

        # Add root shapes first
        for shape in self.shapes.get_root_shapes():
            self._add_shape_to_tree(shape, None)

        # Expand all items
        self.expandAll()

    def _add_shape_to_tree(
        self,
        shape: HierarchicalShape,
        parent_item: Optional[QtWidgets.QTreeWidgetItem]
    ) -> QtWidgets.QTreeWidgetItem:
        """
        Add a shape and its children to the tree.

        Args:
            shape: Shape to add
            parent_item: Parent tree item or None for root

        Returns:
            Created tree item
        """
        # Get display name with counter
        display_name = self._get_display_name_with_counter(shape)

        # Create tree item
        item = QtWidgets.QTreeWidgetItem([display_name])

        # Store shape_id in item data
        item.setData(0, Qt.UserRole, shape.shape_id)

        # Set color from schema
        color = self.schema_manager.get_color(shape.label)
        qcolor = QtGui.QColor(color)
        item.setForeground(0, QtGui.QBrush(qcolor))

        # Set tooltip with full ID
        full_display = self.schema_manager.get_display_name(shape.label)
        description = self.schema_manager.get_description(shape.label)
        tooltip = f"{full_display}\nID: {shape.shape_id}"
        if description:
            tooltip += f"\n{description}"
        item.setToolTip(0, tooltip)

        # Set icon based on class (using colored square)
        icon = self._create_color_icon(qcolor)
        item.setIcon(0, icon)

        # Add to tree
        if parent_item:
            parent_item.addChild(item)
        else:
            self.addTopLevelItem(item)

        # Track item
        self._shape_items[shape.shape_id] = item

        # Add children recursively
        if self.shapes:
            for child in self.shapes.get_children(shape):
                self._add_shape_to_tree(child, item)

        return item

    def _get_display_name_with_counter(self, shape: HierarchicalShape) -> str:
        """
        Get display name with counter for multiple shapes of same class.

        Args:
            shape: Shape to get name for

        Returns:
            Display name like "Box" or "Box #2"
        """
        # Count shapes of same class under same parent
        parent_id = shape.parent_id or "_root"
        key = f"{parent_id}:{shape.label}"

        count = self._class_counters.get(key, 0) + 1
        self._class_counters[key] = count

        display_name = self.schema_manager.get_display_name(shape.label)
        if count > 1:
            display_name = f"{display_name} #{count}"

        return display_name

    def _create_color_icon(self, color: QtGui.QColor) -> QtGui.QIcon:
        """
        Create a colored square icon.

        Args:
            color: Color for the icon

        Returns:
            QIcon with colored square
        """
        pixmap = QtGui.QPixmap(16, 16)
        pixmap.fill(color)

        # Add border
        painter = QtGui.QPainter(pixmap)
        painter.setPen(QtGui.QPen(Qt.black, 1))
        painter.drawRect(0, 0, 15, 15)
        painter.end()

        return QtGui.QIcon(pixmap)

    def _on_selection_changed(self) -> None:
        """Handle selection change."""
        items = self.selectedItems()
        if items:
            shape_id = items[0].data(0, Qt.UserRole)
            if shape_id:
                self.shape_selected.emit(shape_id)

    def _on_item_double_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        """Handle double-click on item."""
        shape_id = item.data(0, Qt.UserRole)
        if shape_id:
            self.shape_double_clicked.emit(shape_id)

    def _show_context_menu(self, position: QtCore.QPoint) -> None:
        """Show context menu at position."""
        item = self.itemAt(position)
        if not item:
            return

        shape_id = item.data(0, Qt.UserRole)
        if not shape_id or not self.shapes:
            return

        shape = self.shapes.get_shape(shape_id)
        if not shape:
            return

        menu = QtWidgets.QMenu(self)

        # Add Child submenu
        if self.schema_manager.can_have_children(shape.label):
            add_child_menu = menu.addMenu("Add Child")
            allowed_children = self.schema_manager.get_allowed_children(shape.label)

            for child_class in allowed_children:
                child_display = self.schema_manager.get_display_name(child_class)
                action = add_child_menu.addAction(f"Add {child_display}")
                action.setData(child_class)
                action.triggered.connect(
                    lambda checked, c=child_class: self.add_child_requested.emit(shape_id, c)
                )

        menu.addSeparator()

        # Select parent
        if shape.parent_id:
            select_parent_action = menu.addAction("Select Parent")
            select_parent_action.triggered.connect(
                lambda: self.select_shape(shape.parent_id)
            )

        # Expand/Collapse
        if item.childCount() > 0:
            if item.isExpanded():
                collapse_action = menu.addAction("Collapse")
                collapse_action.triggered.connect(lambda: item.setExpanded(False))
            else:
                expand_action = menu.addAction("Expand")
                expand_action.triggered.connect(lambda: item.setExpanded(True))

        menu.addSeparator()

        # Copy ID
        copy_id_action = menu.addAction("Copy ID")
        copy_id_action.triggered.connect(
            lambda: QtWidgets.QApplication.clipboard().setText(shape_id)
        )

        menu.addSeparator()

        # Delete
        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(lambda: self.delete_requested.emit(shape_id))

        # Show menu at global position
        menu.exec_(self.mapToGlobal(position))

    def add_shape(self, shape: HierarchicalShape) -> None:
        """
        Add a shape to the tree.

        Args:
            shape: Shape to add
        """
        # Find parent item
        parent_item = None
        if shape.parent_id:
            parent_item = self._shape_items.get(shape.parent_id)

        self._add_shape_to_tree(shape, parent_item)

        # Expand parent if exists
        if parent_item:
            parent_item.setExpanded(True)

    def remove_shape(self, shape_id: str) -> None:
        """
        Remove a shape from the tree.

        Args:
            shape_id: ID of shape to remove
        """
        item = self._shape_items.get(shape_id)
        if not item:
            return

        # Remove from tree
        parent = item.parent()
        if parent:
            parent.removeChild(item)
        else:
            index = self.indexOfTopLevelItem(item)
            if index >= 0:
                self.takeTopLevelItem(index)

        # Remove from tracking
        del self._shape_items[shape_id]

        # Also remove any children from tracking
        def remove_children_tracking(parent_item):
            for i in range(parent_item.childCount()):
                child_item = parent_item.child(i)
                child_id = child_item.data(0, Qt.UserRole)
                if child_id in self._shape_items:
                    del self._shape_items[child_id]
                remove_children_tracking(child_item)

        remove_children_tracking(item)

    def update_shape(self, shape: HierarchicalShape) -> None:
        """
        Update the display of a shape.

        Args:
            shape: Shape that was updated
        """
        item = self._shape_items.get(shape.shape_id)
        if not item:
            return

        # Update display name
        display_name = self.schema_manager.get_display_name(shape.label)
        item.setText(0, display_name)

        # Update color
        color = self.schema_manager.get_color(shape.label)
        qcolor = QtGui.QColor(color)
        item.setForeground(0, QtGui.QBrush(qcolor))
        item.setIcon(0, self._create_color_icon(qcolor))

    def select_shape(self, shape_id: str) -> None:
        """
        Select a shape in the tree.

        Args:
            shape_id: ID of shape to select
        """
        item = self._shape_items.get(shape_id)
        if item:
            self.clearSelection()
            item.setSelected(True)
            self.scrollToItem(item)

    def get_selected_shape_id(self) -> Optional[str]:
        """
        Get the currently selected shape ID.

        Returns:
            Selected shape ID or None
        """
        items = self.selectedItems()
        if items:
            return items[0].data(0, Qt.UserRole)
        return None

    def clear_selection(self) -> None:
        """Clear the current selection."""
        self.clearSelection()

    # Drag and Drop support

    def startDrag(self, supportedActions: Qt.DropActions) -> None:
        """Start dragging an item."""
        items = self.selectedItems()
        if not items:
            return

        item = items[0]
        shape_id = item.data(0, Qt.UserRole)
        if not shape_id:
            return

        # Create drag with shape_id
        drag = QtGui.QDrag(self)
        mime_data = QtCore.QMimeData()
        mime_data.setText(shape_id)
        drag.setMimeData(mime_data)

        # Execute drag
        drag.exec_(Qt.MoveAction)

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        """Handle drag enter."""
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:
        """Handle drag move."""
        if not event.mimeData().hasText():
            event.ignore()
            return

        # Get shape being dragged
        shape_id = event.mimeData().text()
        if not self.shapes:
            event.ignore()
            return

        shape = self.shapes.get_shape(shape_id)
        if not shape:
            event.ignore()
            return

        # Get target item
        target_item = self.itemAt(event.pos())

        if target_item:
            target_id = target_item.data(0, Qt.UserRole)
            target_shape = self.shapes.get_shape(target_id)

            if target_shape and target_id != shape_id:
                # Validate parent-child relationship
                if self.schema_manager.validate_parent_child(target_shape.label, shape.label):
                    event.acceptProposedAction()
                    return

        # Allow dropping at root level if shape doesn't require parent
        if not self.schema_manager.requires_parent(shape.label):
            event.acceptProposedAction()
            return

        event.ignore()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        """Handle drop."""
        if not event.mimeData().hasText():
            event.ignore()
            return

        shape_id = event.mimeData().text()
        if not self.shapes:
            event.ignore()
            return

        shape = self.shapes.get_shape(shape_id)
        if not shape:
            event.ignore()
            return

        # Get target
        target_item = self.itemAt(event.pos())
        new_parent_id = ""

        if target_item:
            target_id = target_item.data(0, Qt.UserRole)
            target_shape = self.shapes.get_shape(target_id)

            if target_shape and self.schema_manager.validate_parent_child(target_shape.label, shape.label):
                new_parent_id = target_id
            elif self.schema_manager.requires_parent(shape.label):
                event.ignore()
                return
        else:
            # Dropping at root
            if self.schema_manager.requires_parent(shape.label):
                event.ignore()
                return

        # Emit reparent signal
        self.reparent_requested.emit(shape_id, new_parent_id)
        event.acceptProposedAction()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        """Handle key press events."""
        if event.key() == Qt.Key_Delete:
            shape_id = self.get_selected_shape_id()
            if shape_id:
                self.delete_requested.emit(shape_id)
        elif event.key() == Qt.Key_C and self.shapes:
            # Add child shortcut
            shape_id = self.get_selected_shape_id()
            if shape_id:
                shape = self.shapes.get_shape(shape_id)
                if shape and self.schema_manager.can_have_children(shape.label):
                    allowed = self.schema_manager.get_allowed_children(shape.label)
                    if allowed:
                        # Add first allowed child type
                        self.add_child_requested.emit(shape_id, allowed[0])
        elif event.key() == Qt.Key_P and self.shapes:
            # Select parent shortcut
            shape_id = self.get_selected_shape_id()
            if shape_id:
                shape = self.shapes.get_shape(shape_id)
                if shape and shape.parent_id:
                    self.select_shape(shape.parent_id)
        else:
            super().keyPressEvent(event)

    def count_shapes_by_class(self, class_name: str) -> int:
        """
        Count shapes of a specific class.

        Args:
            class_name: Class name to count

        Returns:
            Number of shapes with that class
        """
        count = 0
        if self.shapes:
            for shape in self.shapes:
                if shape.label == class_name:
                    count += 1
        return count

    def get_shapes_at_level(self, level: int) -> List[str]:
        """
        Get shape IDs at a specific depth level.

        Args:
            level: Depth level (0 = root)

        Returns:
            List of shape IDs at that level
        """
        result = []

        def collect_at_level(item: QtWidgets.QTreeWidgetItem, current_level: int):
            if current_level == level:
                shape_id = item.data(0, Qt.UserRole)
                if shape_id:
                    result.append(shape_id)
            else:
                for i in range(item.childCount()):
                    collect_at_level(item.child(i), current_level + 1)

        for i in range(self.topLevelItemCount()):
            collect_at_level(self.topLevelItem(i), 0)

        return result
