"""
Hierarchical Canvas Widget for Hierarchical Labelme

This module extends the labelme Canvas to support hierarchical annotations,
including child drawing mode, parent highlighting, and schema-based coloring.
"""

from __future__ import annotations

import enum

from qtpy import QtCore
from qtpy import QtGui
from qtpy import QtWidgets
from qtpy.QtCore import Qt
from qtpy.QtCore import Signal

from labelme.hierarchical_shape import HierarchicalShape
from labelme.hierarchical_shape import ShapeCollection
from labelme.schema_manager import SchemaManager


class DrawingMode(enum.Enum):
    """Canvas drawing modes."""

    EDIT = enum.auto()  # Selecting and editing shapes
    CREATE = enum.auto()  # Creating new top-level shape
    CREATE_CHILD = enum.auto()  # Creating child shape for a parent


class HierarchicalCanvas(QtWidgets.QWidget):
    """
    Canvas widget for hierarchical annotation.

    This is a simplified canvas implementation focused on hierarchical
    annotation. It supports:
    - Polygon drawing for shapes
    - Parent-child relationship tracking
    - Schema-based coloring
    - Child drawing mode with parent highlighting

    Signals:
        shape_created(HierarchicalShape): Emitted when a shape is completed
        child_created(HierarchicalShape): Emitted when a child shape is completed
        shape_selected(str): Emitted when a shape is selected (shape_id)
        selection_changed(list): Emitted when selection changes
        drawing_started(): Emitted when drawing begins
        drawing_finished(): Emitted when drawing ends
        mode_changed(DrawingMode): Emitted when mode changes
        zoom_request(int, QPointF): Emitted for zoom requests
        status_message(str): Emitted for status bar updates
    """

    # Signals
    shape_created = Signal(object)  # HierarchicalShape
    child_created = Signal(object)  # HierarchicalShape
    shape_selected = Signal(str)  # shape_id
    selection_changed = Signal(list)  # list of shape_ids
    drawing_started = Signal()
    drawing_finished = Signal()
    mode_changed = Signal(object)  # DrawingMode
    zoom_request = Signal(int, QtCore.QPointF)
    status_message = Signal(str)

    def __init__(
        self, schema_manager: SchemaManager, parent: QtWidgets.QWidget | None = None
    ):
        """
        Initialize hierarchical canvas.

        Args:
            schema_manager: SchemaManager for class definitions
            parent: Parent widget
        """
        super().__init__(parent)

        self.schema_manager = schema_manager
        self.shapes: ShapeCollection = ShapeCollection()
        self.pixmap: QtGui.QPixmap | None = None
        self.scale: float = 1.0
        self.offset: QtCore.QPointF = QtCore.QPointF(0, 0)

        # Drawing state
        self.mode: DrawingMode = DrawingMode.EDIT
        self.current_class: str | None = None
        self.current_points: list[list[float]] = []
        self.is_drawing: bool = False

        # Child drawing mode
        self.current_parent: HierarchicalShape | None = None
        self.child_class: str | None = None

        # Selection
        self.selected_shapes: list[str] = []
        self.hovered_shape_id: str | None = None

        # Visual settings
        self.point_size: int = 8
        self.line_width: int = 2
        self.vertex_fill_color = QtGui.QColor(0, 255, 0, 255)
        self.hover_vertex_color = QtGui.QColor(255, 255, 255, 255)
        self.selected_color = QtGui.QColor(255, 255, 255, 255)
        self.parent_highlight_color = QtGui.QColor(255, 255, 0, 64)

        # Rendering settings
        self.show_labels: bool = True
        self.debug_mode: bool = False

        # Setup
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up canvas UI."""
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.WheelFocus)
        self.setCursor(Qt.ArrowCursor)

    def set_shapes(self, shapes: ShapeCollection) -> None:
        """
        Set the shape collection.

        Args:
            shapes: ShapeCollection to display
        """
        self.shapes = shapes
        self.update()

    def load_pixmap(self, pixmap: QtGui.QPixmap) -> None:
        """
        Load an image to display.

        Args:
            pixmap: QPixmap to display
        """
        self.pixmap = pixmap
        self.update()

    def load_image(self, image_path: str) -> bool:
        """
        Load image from file.

        Args:
            image_path: Path to image file

        Returns:
            True if successful
        """
        pixmap = QtGui.QPixmap(image_path)
        if pixmap.isNull():
            return False
        self.load_pixmap(pixmap)
        return True

    def set_scale(self, scale: float) -> None:
        """
        Set the zoom scale.

        Args:
            scale: Zoom factor (1.0 = 100%)
        """
        self.scale = max(0.1, min(10.0, scale))
        self.update()

    def zoom_in(self) -> None:
        """Zoom in by 10%."""
        self.set_scale(self.scale * 1.1)

    def zoom_out(self) -> None:
        """Zoom out by 10%."""
        self.set_scale(self.scale / 1.1)

    def fit_window(self) -> None:
        """Fit image to window."""
        if not self.pixmap:
            return

        w = self.width() - 20
        h = self.height() - 20
        scale_w = w / self.pixmap.width()
        scale_h = h / self.pixmap.height()
        self.set_scale(min(scale_w, scale_h))

    # Mode management

    def set_mode(self, mode: DrawingMode) -> None:
        """
        Set the drawing mode.

        Args:
            mode: New drawing mode
        """
        self.mode = mode
        self._update_cursor()
        self.mode_changed.emit(mode)

        if mode == DrawingMode.EDIT:
            self.status_message.emit("Edit mode")
        elif mode == DrawingMode.CREATE:
            class_name = self.schema_manager.get_display_name(self.current_class or "")
            self.status_message.emit(f"Drawing {class_name}")
        elif mode == DrawingMode.CREATE_CHILD:
            parent_name = ""
            child_name = ""
            if self.current_parent:
                parent_name = self.schema_manager.get_display_name(
                    self.current_parent.label
                )
            if self.child_class:
                child_name = self.schema_manager.get_display_name(self.child_class)
            self.status_message.emit(f"Drawing {child_name} for {parent_name}")

    def enter_create_mode(self, class_name: str) -> None:
        """
        Enter shape creation mode.

        Args:
            class_name: Class to create
        """
        self.current_class = class_name
        self.current_parent = None
        self.child_class = None
        self.current_points = []
        self.is_drawing = False
        self.set_mode(DrawingMode.CREATE)

    def enter_child_mode(self, parent: HierarchicalShape, child_class: str) -> None:
        """
        Enter child drawing mode.

        Args:
            parent: Parent shape
            child_class: Class of child to create
        """
        self.current_parent = parent
        self.child_class = child_class
        self.current_class = child_class
        self.current_points = []
        self.is_drawing = False
        self.set_mode(DrawingMode.CREATE_CHILD)

    def enter_edit_mode(self) -> None:
        """Enter edit/selection mode."""
        self.current_parent = None
        self.child_class = None
        self.current_class = None
        self.current_points = []
        self.is_drawing = False
        self.set_mode(DrawingMode.EDIT)

    def cancel_drawing(self) -> None:
        """Cancel current drawing operation."""
        self.current_points = []
        self.is_drawing = False
        self.update()

    def _update_cursor(self) -> None:
        """Update cursor based on mode."""
        if self.mode in (DrawingMode.CREATE, DrawingMode.CREATE_CHILD):
            self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    # Selection

    def select_shape(self, shape_id: str) -> None:
        """
        Select a shape.

        Args:
            shape_id: ID of shape to select
        """
        if shape_id in self.shapes:
            self.selected_shapes = [shape_id]
            self.shape_selected.emit(shape_id)
            self.selection_changed.emit(self.selected_shapes)
            self.update()

    def clear_selection(self) -> None:
        """Clear the current selection."""
        self.selected_shapes = []
        self.selection_changed.emit([])
        self.update()

    def get_selected_shapes(self) -> list[HierarchicalShape]:
        """
        Get currently selected shapes.

        Returns:
            List of selected shapes
        """
        return [
            self.shapes.get_shape(sid)
            for sid in self.selected_shapes
            if sid in self.shapes
        ]

    # Mouse events

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse press."""
        pos = self._map_to_image(event.pos())

        if event.button() == Qt.LeftButton:
            if self.mode in (DrawingMode.CREATE, DrawingMode.CREATE_CHILD):
                self._handle_draw_click(pos)
            elif self.mode == DrawingMode.EDIT:
                self._handle_select_click(pos)

        elif event.button() == Qt.RightButton:
            if self.is_drawing and len(self.current_points) > 0:
                # Complete polygon on right-click
                self._complete_shape()

        self.update()

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle double-click to complete polygon."""
        if self.is_drawing and len(self.current_points) >= 3:
            self._complete_shape()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse move."""
        pos = self._map_to_image(event.pos())

        if self.mode == DrawingMode.EDIT:
            # Update hover state
            self._update_hover(pos)

        self.update()

    def _handle_draw_click(self, pos: QtCore.QPointF) -> None:
        """Handle click in drawing mode."""
        if not self.is_drawing:
            self.is_drawing = True
            self.current_points = []
            self.drawing_started.emit()

        # Add point
        self.current_points.append([pos.x(), pos.y()])

    def _handle_select_click(self, pos: QtCore.QPointF) -> None:
        """Handle click in edit mode for selection."""
        # Find shape at position
        shape_id = self._find_shape_at(pos)

        if shape_id:
            self.select_shape(shape_id)
        else:
            self.clear_selection()

    def _complete_shape(self) -> None:
        """Complete the current shape being drawn."""
        if len(self.current_points) < 3:
            self.cancel_drawing()
            return

        # Determine shape type based on class schema
        shape_type = "polygon"
        if self.current_class:
            types = self.schema_manager.get_shape_types(self.current_class)
            if types:
                shape_type = types[0]

        # Get default attributes
        attributes = {}
        if self.current_class:
            attributes = self.schema_manager.get_all_defaults(self.current_class)

        # Create shape
        if self.mode == DrawingMode.CREATE_CHILD and self.current_parent:
            # Create as child
            shape = self.shapes.create_child(
                parent=self.current_parent,
                label=self.current_class,
                points=self.current_points,
                shape_type=shape_type,
                attributes=attributes,
            )
            self.child_created.emit(shape)
        else:
            # Create as root shape
            shape = self.shapes.create_shape(
                label=self.current_class,
                points=self.current_points,
                shape_type=shape_type,
                attributes=attributes,
            )
            self.shape_created.emit(shape)

        # Reset drawing state
        self.is_drawing = False
        self.current_points = []
        self.drawing_finished.emit()

        # Select the new shape
        self.select_shape(shape.shape_id)

        # Return to edit mode or keep in create mode
        if self.mode == DrawingMode.CREATE_CHILD:
            # Stay in child mode for adding more children
            pass
        else:
            self.enter_edit_mode()

    def _update_hover(self, pos: QtCore.QPointF) -> None:
        """Update hover state."""
        shape_id = self._find_shape_at(pos)
        if shape_id != self.hovered_shape_id:
            self.hovered_shape_id = shape_id

    def _find_shape_at(self, pos: QtCore.QPointF) -> str | None:
        """
        Find shape at position.

        Args:
            pos: Position in image coordinates

        Returns:
            Shape ID or None
        """
        for shape in self.shapes:
            if self._point_in_polygon(pos, shape.points):
                return shape.shape_id
        return None

    def _point_in_polygon(
        self, point: QtCore.QPointF, polygon: list[list[float]]
    ) -> bool:
        """
        Check if point is inside polygon.

        Args:
            point: Point to check
            polygon: Polygon vertices

        Returns:
            True if point is inside
        """
        if len(polygon) < 3:
            return False

        x, y = point.x(), point.y()
        n = len(polygon)
        inside = False

        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y

        return inside

    def _map_to_image(self, pos: QtCore.QPoint) -> QtCore.QPointF:
        """
        Map widget position to image coordinates.

        Args:
            pos: Widget position

        Returns:
            Image coordinates
        """
        x = (pos.x() - self.offset.x()) / self.scale
        y = (pos.y() - self.offset.y()) / self.scale
        return QtCore.QPointF(x, y)

    def _map_from_image(self, pos: QtCore.QPointF) -> QtCore.QPointF:
        """
        Map image coordinates to widget position.

        Args:
            pos: Image coordinates

        Returns:
            Widget position
        """
        x = pos.x() * self.scale + self.offset.x()
        y = pos.y() * self.scale + self.offset.y()
        return QtCore.QPointF(x, y)

    # Keyboard events

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        """Handle key press."""
        key = event.key()

        if key == Qt.Key_Escape:
            if self.is_drawing:
                self.cancel_drawing()
            else:
                self.enter_edit_mode()

        elif key == Qt.Key_Delete:
            # Delete selected shapes
            for shape_id in self.selected_shapes[:]:
                self.shapes.remove_shape(shape_id)
            self.clear_selection()
            self.update()

        elif key == Qt.Key_Space:
            # Toggle between edit and create mode
            if self.mode == DrawingMode.EDIT:
                # Enter create mode with last used class or first class
                classes = self.schema_manager.get_top_level_classes()
                if classes:
                    self.enter_create_mode(classes[0])
            else:
                self.enter_edit_mode()

        else:
            super().keyPressEvent(event)

    # Wheel events

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        """Handle wheel event for zooming."""
        delta = event.angleDelta().y()
        if delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    # Painting

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """Paint the canvas."""
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # Fill background
        painter.fillRect(self.rect(), QtGui.QColor(50, 50, 50))

        if not self.pixmap:
            return

        # Calculate offset to center image
        scaled_width = self.pixmap.width() * self.scale
        scaled_height = self.pixmap.height() * self.scale
        self.offset = QtCore.QPointF(
            (self.width() - scaled_width) / 2, (self.height() - scaled_height) / 2
        )

        # Draw image
        painter.save()
        painter.translate(self.offset)
        painter.scale(self.scale, self.scale)
        painter.drawPixmap(0, 0, self.pixmap)
        painter.restore()

        # Draw shapes
        self._draw_shapes(painter)

        # Draw current drawing
        if self.is_drawing and self.current_points:
            self._draw_current_shape(painter)

    def _draw_shapes(self, painter: QtGui.QPainter) -> None:
        """Draw all shapes."""
        # Draw parent highlight if in child mode
        if self.mode == DrawingMode.CREATE_CHILD and self.current_parent:
            self._draw_shape_highlight(
                painter, self.current_parent, self.parent_highlight_color
            )

        # Draw all shapes
        for shape in self.shapes:
            is_selected = shape.shape_id in self.selected_shapes
            is_hovered = shape.shape_id == self.hovered_shape_id
            self._draw_shape(painter, shape, is_selected, is_hovered)

    def _draw_shape(
        self,
        painter: QtGui.QPainter,
        shape: HierarchicalShape,
        is_selected: bool = False,
        is_hovered: bool = False,
    ) -> None:
        """Draw a single shape."""
        if len(shape.points) < 2:
            return

        # Get color from schema
        color_hex = self.schema_manager.get_color(shape.label)
        color = QtGui.QColor(color_hex)

        # Modify color based on state
        if is_selected:
            pen_color = self.selected_color
            fill_color = QtGui.QColor(color)
            fill_color.setAlpha(100)
        elif is_hovered:
            pen_color = color.lighter(150)
            fill_color = QtGui.QColor(color)
            fill_color.setAlpha(50)
        else:
            pen_color = color
            fill_color = QtGui.QColor(color)
            fill_color.setAlpha(30)

        # Create path
        path = QtGui.QPainterPath()
        first_point = self._map_from_image(
            QtCore.QPointF(shape.points[0][0], shape.points[0][1])
        )
        path.moveTo(first_point)

        for point in shape.points[1:]:
            mapped = self._map_from_image(QtCore.QPointF(point[0], point[1]))
            path.lineTo(mapped)
        path.closeSubpath()

        # Draw fill
        painter.fillPath(path, fill_color)

        # Draw outline
        pen = QtGui.QPen(pen_color, self.line_width)
        painter.setPen(pen)
        painter.drawPath(path)

        # Draw vertices
        for point in shape.points:
            mapped = self._map_from_image(QtCore.QPointF(point[0], point[1]))
            painter.setBrush(self.vertex_fill_color)
            painter.drawEllipse(mapped, self.point_size / 2, self.point_size / 2)

        # Draw label
        if self.show_labels and len(shape.points) > 0:
            label_pos = self._map_from_image(
                QtCore.QPointF(shape.points[0][0], shape.points[0][1] - 10)
            )
            display_name = self.schema_manager.get_display_name(shape.label)

            # Add short ID in debug mode
            if self.debug_mode:
                display_name += f" [{shape.shape_id[:8]}]"

            painter.setPen(Qt.white)
            painter.drawText(label_pos, display_name)

    def _draw_shape_highlight(
        self, painter: QtGui.QPainter, shape: HierarchicalShape, color: QtGui.QColor
    ) -> None:
        """Draw highlight around a shape."""
        if len(shape.points) < 2:
            return

        path = QtGui.QPainterPath()
        first_point = self._map_from_image(
            QtCore.QPointF(shape.points[0][0], shape.points[0][1])
        )
        path.moveTo(first_point)

        for point in shape.points[1:]:
            mapped = self._map_from_image(QtCore.QPointF(point[0], point[1]))
            path.lineTo(mapped)
        path.closeSubpath()

        painter.fillPath(path, color)

    def _draw_current_shape(self, painter: QtGui.QPainter) -> None:
        """Draw the shape currently being drawn."""
        if len(self.current_points) < 1:
            return

        # Get color
        color = QtGui.QColor(255, 255, 0)  # Yellow for drawing
        if self.current_class:
            color_hex = self.schema_manager.get_color(self.current_class)
            color = QtGui.QColor(color_hex)

        # Draw lines
        pen = QtGui.QPen(color, self.line_width)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)

        for i in range(len(self.current_points) - 1):
            p1 = self._map_from_image(
                QtCore.QPointF(self.current_points[i][0], self.current_points[i][1])
            )
            p2 = self._map_from_image(
                QtCore.QPointF(
                    self.current_points[i + 1][0], self.current_points[i + 1][1]
                )
            )
            painter.drawLine(p1, p2)

        # Draw vertices
        painter.setBrush(self.vertex_fill_color)
        for point in self.current_points:
            mapped = self._map_from_image(QtCore.QPointF(point[0], point[1]))
            painter.drawEllipse(mapped, self.point_size / 2, self.point_size / 2)

    # Public API

    def get_image_size(self) -> tuple | None:
        """
        Get the size of the loaded image.

        Returns:
            (width, height) tuple or None
        """
        if self.pixmap:
            return (self.pixmap.width(), self.pixmap.height())
        return None

    def remove_shape(self, shape_id: str) -> None:
        """
        Remove a shape from the canvas.

        Args:
            shape_id: ID of shape to remove
        """
        if shape_id in self.selected_shapes:
            self.selected_shapes.remove(shape_id)
        self.shapes.remove_shape(shape_id)
        self.update()

    def update_shape(self, shape: HierarchicalShape) -> None:
        """
        Update a shape's display.

        Args:
            shape: Shape that was updated
        """
        self.update()

    def highlight_shape(self, shape_id: str) -> None:
        """
        Highlight a shape temporarily.

        Args:
            shape_id: Shape to highlight
        """
        self.select_shape(shape_id)
