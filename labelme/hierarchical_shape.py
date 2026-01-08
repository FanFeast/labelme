"""
Hierarchical Shape Module for Labelme

This module provides enhanced Shape and ShapeCollection classes
that support parent-child relationships, UUID-based IDs, and
schema-driven attributes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timezone
from typing import Any

# Qt is optional - only needed for get_qpoints()
try:
    from qtpy import QtCore

    HAS_QT = True
except ImportError:
    HAS_QT = False
    QtCore = None  # type: ignore[assignment]


def generate_uuid() -> str:
    """Generate a UUID string (32 hex characters, no dashes)."""
    return uuid.uuid4().hex


@dataclass
class HierarchicalShape:
    """
    A shape with hierarchical relationships and custom attributes.

    This extends the concept of a shape to support:
    - UUID-based identification
    - Parent-child relationships
    - Schema-driven attributes
    - Creation/modification metadata

    Attributes:
        shape_id: Unique identifier (UUID hex string)
        label: Class name (e.g., "box", "face")
        points: List of (x, y) coordinate tuples
        shape_type: Type of shape ("polygon", "rectangle", etc.)
        parent_id: ID of parent shape (None if top-level)
        children_ids: List of child shape IDs
        attributes: Dict of class-specific attribute values
        flags: Dict of boolean flags
        description: Optional description text
        group_id: Optional group identifier
        created_at: ISO timestamp of creation
        modified_at: ISO timestamp of last modification
        other_data: Extensible custom data
    """

    # Required fields
    label: str
    points: list[list[float]] = field(default_factory=list)

    # Identity
    shape_id: str = field(default_factory=generate_uuid)
    shape_type: str = "polygon"

    # Hierarchy
    parent_id: str | None = None
    children_ids: list[str] = field(default_factory=list)

    # Attributes and metadata
    attributes: dict[str, Any] = field(default_factory=dict)
    flags: dict[str, bool] = field(default_factory=dict)
    description: str = ""
    group_id: int | None = None

    # Timestamps
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    modified_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Extensible data
    other_data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Ensure mutable defaults are properly initialized."""
        if self.points is None:
            self.points = []
        if self.children_ids is None:
            self.children_ids = []
        if self.attributes is None:
            self.attributes = {}
        if self.flags is None:
            self.flags = {}
        if self.other_data is None:
            self.other_data = {}

    def set_parent(self, parent: HierarchicalShape | None) -> None:
        """
        Set the parent of this shape.

        Args:
            parent: Parent shape or None to remove parent

        Note:
            This only updates this shape's parent_id. The caller should also
            update the parent's children_ids using add_child/remove_child.
        """
        if parent is None:
            self.parent_id = None
        else:
            self.parent_id = parent.shape_id
        self.update_metadata()

    def add_child(self, child: HierarchicalShape) -> None:
        """
        Add a child to this shape.

        Args:
            child: Child shape to add

        Note:
            This updates both this shape's children_ids and the child's parent_id.
        """
        if child.shape_id not in self.children_ids:
            self.children_ids.append(child.shape_id)
        child.parent_id = self.shape_id
        self.update_metadata()

    def remove_child(self, child: HierarchicalShape) -> None:
        """
        Remove a child from this shape.

        Args:
            child: Child shape to remove

        Note:
            This only updates this shape's children_ids.
            The child's parent_id is NOT changed.
        """
        if child.shape_id in self.children_ids:
            self.children_ids.remove(child.shape_id)
        self.update_metadata()

    def has_children(self) -> bool:
        """Check if this shape has any children."""
        return len(self.children_ids) > 0

    def has_parent(self) -> bool:
        """Check if this shape has a parent."""
        return self.parent_id is not None

    def set_attribute(self, name: str, value: Any) -> None:
        """
        Set an attribute value.

        Args:
            name: Attribute name
            value: Attribute value
        """
        self.attributes[name] = value
        self.update_metadata()

    def get_attribute(self, name: str, default: Any = None) -> Any:
        """
        Get an attribute value.

        Args:
            name: Attribute name
            default: Default value if not set

        Returns:
            Attribute value or default
        """
        return self.attributes.get(name, default)

    def update_metadata(self) -> None:
        """Update the modified_at timestamp."""
        self.modified_at = datetime.now(timezone.utc).isoformat()

    def add_point(self, x: float, y: float) -> None:
        """Add a point to the shape."""
        self.points.append([x, y])
        self.update_metadata()

    def remove_point(self, index: int) -> None:
        """Remove a point by index."""
        if 0 <= index < len(self.points):
            self.points.pop(index)
            self.update_metadata()

    def move_by(self, dx: float, dy: float) -> None:
        """Move all points by offset."""
        self.points = [[p[0] + dx, p[1] + dy] for p in self.points]
        self.update_metadata()

    def move_point(self, index: int, x: float, y: float) -> None:
        """Move a specific point to new coordinates."""
        if 0 <= index < len(self.points):
            self.points[index] = [x, y]
            self.update_metadata()

    def get_qpoints(self) -> list:
        """Get points as QPointF list for Qt rendering."""
        if not HAS_QT:
            raise RuntimeError("Qt is not available. Install qtpy to use this method.")
        return [QtCore.QPointF(p[0], p[1]) for p in self.points]

    def to_dict(self) -> dict[str, Any]:
        """
        Convert shape to dictionary for serialization.

        Returns:
            Dict representation of the shape
        """
        return {
            "shape_id": self.shape_id,
            "label": self.label,
            "points": self.points,
            "shape_type": self.shape_type,
            "parent_id": self.parent_id,
            "children_ids": self.children_ids.copy(),
            "attributes": self.attributes.copy(),
            "flags": self.flags.copy(),
            "description": self.description,
            "group_id": self.group_id,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "other_data": self.other_data.copy(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HierarchicalShape:
        """
        Create shape from dictionary.

        Args:
            data: Dictionary with shape data

        Returns:
            HierarchicalShape instance
        """
        return cls(
            shape_id=data.get("shape_id", generate_uuid()),
            label=data["label"],
            points=data.get("points", []),
            shape_type=data.get("shape_type", "polygon"),
            parent_id=data.get("parent_id"),
            children_ids=data.get("children_ids", []),
            attributes=data.get("attributes", {}),
            flags=data.get("flags", {}),
            description=data.get("description", ""),
            group_id=data.get("group_id"),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            modified_at=data.get("modified_at", datetime.now(timezone.utc).isoformat()),
            other_data=data.get("other_data", {}),
        )

    @classmethod
    def from_legacy_shape(
        cls, label: str, points: list[list[float]], **kwargs
    ) -> HierarchicalShape:
        """
        Create from legacy labelme shape format.

        Args:
            label: Shape label
            points: List of point coordinates
            **kwargs: Additional shape properties

        Returns:
            HierarchicalShape instance
        """
        return cls(
            label=label,
            points=points,
            shape_type=kwargs.get("shape_type", "polygon"),
            flags=kwargs.get("flags", {}),
            description=kwargs.get("description", ""),
            group_id=kwargs.get("group_id"),
        )

    def copy(self) -> HierarchicalShape:
        """Create a deep copy of this shape with a new ID."""
        new_shape = HierarchicalShape.from_dict(self.to_dict())
        new_shape.shape_id = generate_uuid()
        new_shape.children_ids = []  # Don't copy children references
        new_shape.parent_id = None  # Don't copy parent reference
        new_shape.created_at = datetime.now(timezone.utc).isoformat()
        new_shape.modified_at = new_shape.created_at
        return new_shape


class ShapeCollection:
    """
    Collection of hierarchical shapes with efficient lookup and management.

    Provides:
    - Shape storage with UUID lookup
    - Parent-child relationship management
    - Validation helpers
    - Batch operations

    Example:
        collection = ShapeCollection()
        box = collection.add_shape(HierarchicalShape(label="box", points=...))
        face = collection.create_child(box, "face", points=...)
        collection.remove_shape(face.shape_id)
    """

    def __init__(self):
        """Initialize empty shape collection."""
        self._shapes: dict[str, HierarchicalShape] = {}
        self._root_shapes: set[str] = set()  # Shapes without parents

    def __len__(self) -> int:
        """Return number of shapes."""
        return len(self._shapes)

    def __iter__(self):
        """Iterate over all shapes."""
        return iter(self._shapes.values())

    def __contains__(self, shape_id: str) -> bool:
        """Check if shape ID exists."""
        return shape_id in self._shapes

    def add_shape(self, shape: HierarchicalShape) -> HierarchicalShape:
        """
        Add a shape to the collection.

        Args:
            shape: Shape to add

        Returns:
            The added shape (with guaranteed unique ID)

        Raises:
            ValueError: If shape with same ID already exists
        """
        # Ensure unique ID
        while shape.shape_id in self._shapes:
            shape.shape_id = generate_uuid()

        self._shapes[shape.shape_id] = shape

        # Track root shapes
        if shape.parent_id is None:
            self._root_shapes.add(shape.shape_id)
        else:
            # Verify parent exists and update its children
            parent = self._shapes.get(shape.parent_id)
            if parent:
                if shape.shape_id not in parent.children_ids:
                    parent.children_ids.append(shape.shape_id)
            else:
                # Parent doesn't exist (yet), mark as root for now
                self._root_shapes.add(shape.shape_id)

        return shape

    def create_shape(
        self,
        label: str,
        points: list[list[float]],
        shape_type: str = "polygon",
        parent_id: str | None = None,
        attributes: dict[str, Any] | None = None,
        **kwargs,
    ) -> HierarchicalShape:
        """
        Create and add a new shape.

        Args:
            label: Shape label/class
            points: List of [x, y] coordinates
            shape_type: Type of shape
            parent_id: Optional parent shape ID
            attributes: Optional initial attributes
            **kwargs: Additional shape properties

        Returns:
            The created shape
        """
        shape = HierarchicalShape(
            label=label,
            points=points,
            shape_type=shape_type,
            parent_id=parent_id,
            attributes=attributes or {},
            **kwargs,
        )
        return self.add_shape(shape)

    def create_child(
        self,
        parent: HierarchicalShape,
        label: str,
        points: list[list[float]],
        shape_type: str = "polygon",
        attributes: dict[str, Any] | None = None,
    ) -> HierarchicalShape:
        """
        Create a child shape under a parent.

        Args:
            parent: Parent shape
            label: Child label/class
            points: Child shape points
            shape_type: Shape type
            attributes: Initial attributes

        Returns:
            The created child shape
        """
        child = self.create_shape(
            label=label,
            points=points,
            shape_type=shape_type,
            parent_id=parent.shape_id,
            attributes=attributes,
        )
        # Update parent's children list
        if child.shape_id not in parent.children_ids:
            parent.children_ids.append(child.shape_id)

        # Child is not a root
        self._root_shapes.discard(child.shape_id)

        return child

    def get_shape(self, shape_id: str) -> HierarchicalShape | None:
        """
        Get shape by ID.

        Args:
            shape_id: Shape UUID

        Returns:
            Shape or None if not found
        """
        return self._shapes.get(shape_id)

    def get_all_shapes(self) -> list[HierarchicalShape]:
        """Get all shapes as a list."""
        return list(self._shapes.values())

    def get_root_shapes(self) -> list[HierarchicalShape]:
        """Get shapes that have no parent."""
        return [self._shapes[sid] for sid in self._root_shapes if sid in self._shapes]

    def get_children(self, shape: HierarchicalShape) -> list[HierarchicalShape]:
        """
        Get all children of a shape.

        Args:
            shape: Parent shape

        Returns:
            List of child shapes
        """
        return [self._shapes[cid] for cid in shape.children_ids if cid in self._shapes]

    def get_parent(self, shape: HierarchicalShape) -> HierarchicalShape | None:
        """
        Get parent of a shape.

        Args:
            shape: Child shape

        Returns:
            Parent shape or None
        """
        if shape.parent_id:
            return self._shapes.get(shape.parent_id)
        return None

    def get_ancestors(self, shape: HierarchicalShape) -> list[HierarchicalShape]:
        """
        Get all ancestors (parent, grandparent, etc.) of a shape.

        Args:
            shape: Shape to get ancestors for

        Returns:
            List of ancestors from immediate parent to root
        """
        ancestors = []
        current = shape
        while current.parent_id:
            parent = self._shapes.get(current.parent_id)
            if parent:
                ancestors.append(parent)
                current = parent
            else:
                break
        return ancestors

    def get_descendants(self, shape: HierarchicalShape) -> list[HierarchicalShape]:
        """
        Get all descendants (children, grandchildren, etc.) of a shape.

        Args:
            shape: Shape to get descendants for

        Returns:
            List of all descendants (depth-first order)
        """
        descendants = []
        stack = list(shape.children_ids)
        while stack:
            child_id = stack.pop(0)
            child = self._shapes.get(child_id)
            if child:
                descendants.append(child)
                stack.extend(child.children_ids)
        return descendants

    def remove_shape(
        self, shape_id: str, remove_children: bool = True
    ) -> list[HierarchicalShape]:
        """
        Remove a shape from the collection.

        Args:
            shape_id: ID of shape to remove
            remove_children: If True, recursively remove all children

        Returns:
            List of removed shapes
        """
        shape = self._shapes.get(shape_id)
        if not shape:
            return []

        removed = []

        # Handle children
        if remove_children:
            for child_id in shape.children_ids.copy():
                removed.extend(self.remove_shape(child_id, remove_children=True))
        else:
            # Orphan children (make them root shapes)
            for child_id in shape.children_ids:
                child = self._shapes.get(child_id)
                if child:
                    child.parent_id = None
                    self._root_shapes.add(child_id)

        # Remove from parent's children list
        if shape.parent_id:
            parent = self._shapes.get(shape.parent_id)
            if parent and shape_id in parent.children_ids:
                parent.children_ids.remove(shape_id)

        # Remove from collection
        del self._shapes[shape_id]
        self._root_shapes.discard(shape_id)
        removed.append(shape)

        return removed

    def reparent(
        self, shape: HierarchicalShape, new_parent: HierarchicalShape | None
    ) -> bool:
        """
        Change the parent of a shape.

        Args:
            shape: Shape to reparent
            new_parent: New parent shape or None for root

        Returns:
            True if reparenting succeeded
        """
        # Remove from old parent
        if shape.parent_id:
            old_parent = self._shapes.get(shape.parent_id)
            if old_parent and shape.shape_id in old_parent.children_ids:
                old_parent.children_ids.remove(shape.shape_id)

        # Set new parent
        if new_parent:
            shape.parent_id = new_parent.shape_id
            if shape.shape_id not in new_parent.children_ids:
                new_parent.children_ids.append(shape.shape_id)
            self._root_shapes.discard(shape.shape_id)
        else:
            shape.parent_id = None
            self._root_shapes.add(shape.shape_id)

        shape.update_metadata()
        return True

    def get_shapes_by_label(self, label: str) -> list[HierarchicalShape]:
        """
        Get all shapes with a specific label.

        Args:
            label: Label to filter by

        Returns:
            List of shapes with that label
        """
        return [s for s in self._shapes.values() if s.label == label]

    def get_shapes_by_parent(self, parent_id: str | None) -> list[HierarchicalShape]:
        """
        Get all shapes with a specific parent.

        Args:
            parent_id: Parent ID or None for root shapes

        Returns:
            List of shapes with that parent
        """
        if parent_id is None:
            return self.get_root_shapes()
        return [s for s in self._shapes.values() if s.parent_id == parent_id]

    def clear(self) -> None:
        """Remove all shapes."""
        self._shapes.clear()
        self._root_shapes.clear()

    def to_dict_list(self) -> list[dict[str, Any]]:
        """
        Convert all shapes to list of dicts for serialization.

        Returns:
            List of shape dictionaries
        """
        return [shape.to_dict() for shape in self._shapes.values()]

    def from_dict_list(self, shapes_data: list[dict[str, Any]]) -> None:
        """
        Load shapes from list of dicts.

        Args:
            shapes_data: List of shape dictionaries
        """
        self.clear()
        for data in shapes_data:
            shape = HierarchicalShape.from_dict(data)
            self._shapes[shape.shape_id] = shape
            if shape.parent_id is None:
                self._root_shapes.add(shape.shape_id)

    def validate_hierarchy(self) -> list[str]:
        """
        Validate hierarchy consistency.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        for shape in self._shapes.values():
            # Check parent reference
            if shape.parent_id and shape.parent_id not in self._shapes:
                sid = shape.shape_id[:8]
                pid = shape.parent_id[:8]
                errors.append(f"Shape {sid} references non-existent parent {pid}")

            # Check children references
            for child_id in shape.children_ids:
                if child_id not in self._shapes:
                    sid = shape.shape_id[:8]
                    cid = child_id[:8]
                    errors.append(f"Shape {sid} references non-existent child {cid}")
                else:
                    child = self._shapes[child_id]
                    if child.parent_id != shape.shape_id:
                        cid = child_id[:8]
                        pid = shape.shape_id[:8]
                        errors.append(f"Child {cid} parent_id doesn't match {pid}")

        return errors

    def fix_hierarchy(self) -> int:
        """
        Fix inconsistent hierarchy references.

        Returns:
            Number of fixes applied
        """
        fixes = 0

        # Fix broken parent references
        for shape in self._shapes.values():
            if shape.parent_id and shape.parent_id not in self._shapes:
                shape.parent_id = None
                self._root_shapes.add(shape.shape_id)
                fixes += 1

        # Fix broken child references
        for shape in self._shapes.values():
            valid_children = [cid for cid in shape.children_ids if cid in self._shapes]
            if len(valid_children) != len(shape.children_ids):
                fixes += len(shape.children_ids) - len(valid_children)
                shape.children_ids = valid_children

        # Ensure bidirectional consistency
        for shape in self._shapes.values():
            if shape.parent_id:
                parent = self._shapes.get(shape.parent_id)
                if parent and shape.shape_id not in parent.children_ids:
                    parent.children_ids.append(shape.shape_id)
                    fixes += 1

        # Update root shapes set
        self._root_shapes = {
            sid for sid, shape in self._shapes.items() if shape.parent_id is None
        }

        return fixes
