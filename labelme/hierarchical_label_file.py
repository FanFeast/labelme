"""
Hierarchical Label File Module for Labelme

This module provides the HierarchicalAnnotationFile class for loading,
saving, and exporting hierarchical annotations. It supports:
- Hierarchical JSON format
- Legacy labelme format migration
- COCO export
- YOLO export
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

# Optional dependencies for image handling
try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore[assignment]
    HAS_NUMPY = False

try:
    from PIL import Image

    HAS_PIL = True
except ImportError:
    Image = None  # type: ignore[assignment]
    HAS_PIL = False

from labelme.hierarchical_shape import HierarchicalShape
from labelme.hierarchical_shape import ShapeCollection
from labelme.hierarchical_shape import generate_uuid


class HierarchicalAnnotationFile:
    """
    Handles loading, saving, and exporting hierarchical annotations.

    File format:
    {
        "version": "1.0",
        "imagePath": "image.jpg",
        "imageData": "<base64 or null>",
        "imageHeight": 480,
        "imageWidth": 640,
        "shapes": [...],
        "flags": {},
        "schemaVersion": "1.0"
    }

    Each shape:
    {
        "shape_id": "uuid",
        "label": "box",
        "points": [[x1, y1], [x2, y2], ...],
        "shape_type": "polygon",
        "parent_id": null,
        "children_ids": [...],
        "attributes": {...},
        "flags": {},
        "description": "",
        "group_id": null,
        "created_at": "...",
        "modified_at": "..."
    }
    """

    VERSION = "1.0"

    def __init__(self, filename: str | None = None):
        """
        Initialize annotation file.

        Args:
            filename: Optional path to load from
        """
        self.filename: str | None = filename
        self.image_path: str | None = None
        self.image_data: bytes | None = None
        self.image_height: int | None = None
        self.image_width: int | None = None
        self.flags: dict[str, bool] = {}
        self.shapes: ShapeCollection = ShapeCollection()
        self.schema_version: str = "1.0"

        if filename:
            self.load(filename)

    def load(self, filename: str) -> None:
        """
        Load annotation from JSON file.

        Args:
            filename: Path to JSON file

        Raises:
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If file is invalid JSON
        """
        self.filename = filename

        with open(filename, encoding="utf-8") as f:
            data = json.load(f)

        self._load_from_dict(data)

    def _load_from_dict(self, data: dict[str, Any]) -> None:
        """
        Load from dictionary.

        Args:
            data: Annotation data dict
        """
        self.image_path = data.get("imagePath")
        self.image_height = data.get("imageHeight")
        self.image_width = data.get("imageWidth")
        self.flags = data.get("flags", {})
        self.schema_version = data.get("schemaVersion", "1.0")

        # Decode image data if present
        image_data_str = data.get("imageData")
        if image_data_str:
            self.image_data = base64.b64decode(image_data_str)
        else:
            self.image_data = None

        # Load shapes
        self.shapes.clear()
        shapes_data = data.get("shapes", [])

        # Check if this is legacy format (no shape_id)
        is_legacy = shapes_data and "shape_id" not in shapes_data[0]

        if is_legacy:
            self._load_legacy_shapes(shapes_data)
        else:
            self.shapes.from_dict_list(shapes_data)

    def _load_legacy_shapes(self, shapes_data: list[dict[str, Any]]) -> None:
        """
        Load shapes from legacy labelme format.

        Legacy format has no hierarchy info, so all shapes become root shapes.

        Args:
            shapes_data: List of legacy shape dicts
        """
        for shape_dict in shapes_data:
            shape = HierarchicalShape(
                shape_id=generate_uuid(),
                label=shape_dict.get("label", "unknown"),
                points=shape_dict.get("points", []),
                shape_type=shape_dict.get("shape_type", "polygon"),
                flags=shape_dict.get("flags", {}),
                description=shape_dict.get("description", ""),
                group_id=shape_dict.get("group_id"),
            )
            # Migrate any other_data or custom fields
            for key, value in shape_dict.items():
                if key not in [
                    "label",
                    "points",
                    "shape_type",
                    "flags",
                    "description",
                    "group_id",
                ]:
                    shape.other_data[key] = value

            self.shapes.add_shape(shape)

    def save(
        self, filename: str | None = None, include_image_data: bool = True
    ) -> None:
        """
        Save annotation to JSON file.

        Args:
            filename: Path to save to (uses self.filename if not provided)
            include_image_data: Whether to include base64 image data
        """
        if filename:
            self.filename = filename

        if not self.filename:
            raise ValueError("No filename specified")

        data = self.to_dict(include_image_data=include_image_data)

        with open(self.filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def to_dict(self, include_image_data: bool = True) -> dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Args:
            include_image_data: Whether to include base64 image data

        Returns:
            Dict representation
        """
        image_data_str = None
        if include_image_data and self.image_data:
            image_data_str = base64.b64encode(self.image_data).decode("utf-8")

        return {
            "version": self.VERSION,
            "imagePath": self.image_path,
            "imageData": image_data_str,
            "imageHeight": self.image_height,
            "imageWidth": self.image_width,
            "shapes": self.shapes.to_dict_list(),
            "flags": self.flags,
            "schemaVersion": self.schema_version,
        }

    def load_image(self, image_path: str) -> None:
        """
        Load image file and update metadata.

        Args:
            image_path: Path to image file
        """
        with open(image_path, "rb") as f:
            self.image_data = f.read()

        # Get image dimensions (requires PIL)
        if HAS_PIL:
            img = Image.open(image_path)
            self.image_width, self.image_height = img.size
        else:
            self.image_width = None
            self.image_height = None
        self.image_path = os.path.basename(image_path)

    def set_image_from_data(self, image_data: bytes, filename: str) -> None:
        """
        Set image from raw bytes.

        Args:
            image_data: Image file bytes
            filename: Image filename
        """
        self.image_data = image_data
        self.image_path = filename

        # Get dimensions from data (requires PIL)
        if HAS_PIL:
            from io import BytesIO

            img = Image.open(BytesIO(image_data))
            self.image_width, self.image_height = img.size
        else:
            self.image_width = None
            self.image_height = None

    def add_shape(self, shape: HierarchicalShape) -> HierarchicalShape:
        """
        Add a shape to the annotation.

        Args:
            shape: Shape to add

        Returns:
            The added shape
        """
        return self.shapes.add_shape(shape)

    def remove_shape(
        self, shape_id: str, remove_children: bool = True
    ) -> list[HierarchicalShape]:
        """
        Remove a shape from the annotation.

        Args:
            shape_id: ID of shape to remove
            remove_children: Whether to remove children too

        Returns:
            List of removed shapes
        """
        return self.shapes.remove_shape(shape_id, remove_children=remove_children)

    def get_shape(self, shape_id: str) -> HierarchicalShape | None:
        """
        Get shape by ID.

        Args:
            shape_id: Shape UUID

        Returns:
            Shape or None
        """
        return self.shapes.get_shape(shape_id)

    def export_coco(
        self, output_path: str, category_mapping: dict[str, int] | None = None
    ) -> None:
        """
        Export annotations to COCO format.

        Args:
            output_path: Path to save COCO JSON
            category_mapping: Optional mapping from label to category_id
        """
        # Build categories
        if category_mapping is None:
            labels = set(s.label for s in self.shapes)
            category_mapping = {
                label: idx + 1 for idx, label in enumerate(sorted(labels))
            }

        categories = [
            {"id": cat_id, "name": label} for label, cat_id in category_mapping.items()
        ]

        # Build images
        images = [
            {
                "id": 1,
                "file_name": self.image_path or "image.jpg",
                "width": self.image_width or 0,
                "height": self.image_height or 0,
            }
        ]

        # Build annotations
        annotations = []
        for idx, shape in enumerate(self.shapes, start=1):
            if shape.label not in category_mapping:
                continue

            # Convert points to COCO segmentation format
            points = shape.points
            if len(points) < 3:
                continue

            # Flatten points for segmentation
            segmentation = [[coord for point in points for coord in point]]

            # Calculate bbox
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)
            bbox = [x_min, y_min, x_max - x_min, y_max - y_min]

            # Calculate area (polygon area using shoelace formula)
            n = len(points)
            area = (
                abs(
                    sum(
                        points[i][0] * points[(i + 1) % n][1]
                        - points[(i + 1) % n][0] * points[i][1]
                        for i in range(n)
                    )
                )
                / 2
            )

            ann = {
                "id": idx,
                "image_id": 1,
                "category_id": category_mapping[shape.label],
                "segmentation": segmentation,
                "bbox": bbox,
                "area": area,
                "iscrowd": 0,
            }

            # Add hierarchical metadata
            if shape.parent_id:
                ann["parent_id"] = shape.parent_id
            if shape.children_ids:
                ann["children_ids"] = shape.children_ids
            if shape.attributes:
                ann["attributes"] = shape.attributes

            annotations.append(ann)

        coco_data = {
            "images": images,
            "annotations": annotations,
            "categories": categories,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(coco_data, f, indent=2)

    def export_yolo(
        self,
        output_dir: str,
        category_mapping: dict[str, int] | None = None,
        format_type: str = "segment",
    ) -> None:
        """
        Export annotations to YOLO format.

        Args:
            output_dir: Directory to save YOLO txt file
            category_mapping: Mapping from label to class_id (0-indexed)
            format_type: 'segment' for polygon, 'detect' for bbox
        """
        os.makedirs(output_dir, exist_ok=True)

        # Build category mapping
        if category_mapping is None:
            labels = set(s.label for s in self.shapes)
            category_mapping = {label: idx for idx, label in enumerate(sorted(labels))}

        # Get image dimensions for normalization
        img_w = self.image_width or 1
        img_h = self.image_height or 1

        lines = []
        for shape in self.shapes:
            if shape.label not in category_mapping:
                continue

            class_id = category_mapping[shape.label]
            points = shape.points

            if format_type == "segment" and len(points) >= 3:
                # YOLO segment format: class_id x1 y1 x2 y2 ... (normalized)
                coords = []
                for x, y in points:
                    coords.extend([x / img_w, y / img_h])
                line = f"{class_id} " + " ".join(f"{c:.6f}" for c in coords)
                lines.append(line)

            elif format_type == "detect" and len(points) >= 2:
                # YOLO detect: class_id x_center y_center width height
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                x_min, x_max = min(xs), max(xs)
                y_min, y_max = min(ys), max(ys)

                x_center = (x_min + x_max) / 2 / img_w
                y_center = (y_min + y_max) / 2 / img_h
                width = (x_max - x_min) / img_w
                height = (y_max - y_min) / img_h

                line = (
                    f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"
                )
                lines.append(line)

        # Save to txt file
        base_name = os.path.splitext(self.image_path or "image")[0]
        txt_path = os.path.join(output_dir, f"{base_name}.txt")
        with open(txt_path, "w") as f:
            f.write("\n".join(lines))

    def get_statistics(self) -> dict[str, Any]:
        """
        Get annotation statistics.

        Returns:
            Dict with shape counts, hierarchy info, etc.
        """
        shapes_by_label: dict[str, int] = {}
        max_depth = 0
        shapes_with_attributes = 0

        def get_depth(shape: HierarchicalShape, depth: int = 1) -> int:
            max_child_depth = depth
            for child_id in shape.children_ids:
                child = self.shapes.get_shape(child_id)
                if child:
                    max_child_depth = max(max_child_depth, get_depth(child, depth + 1))
            return max_child_depth

        for shape in self.shapes:
            # Count by label
            label = shape.label
            shapes_by_label[label] = shapes_by_label.get(label, 0) + 1

            # Check attributes
            if shape.attributes:
                shapes_with_attributes += 1

            # Calculate max depth for root shapes
            if shape.parent_id is None:
                depth = get_depth(shape)
                max_depth = max(max_depth, depth)

        return {
            "total_shapes": len(self.shapes),
            "root_shapes": len(self.shapes.get_root_shapes()),
            "shapes_by_label": shapes_by_label,
            "max_depth": max_depth,
            "shapes_with_attributes": shapes_with_attributes,
        }

    @classmethod
    def from_labelme_file(cls, labelme_path: str) -> HierarchicalAnnotationFile:
        """
        Create from legacy labelme JSON file.

        Args:
            labelme_path: Path to labelme JSON file

        Returns:
            HierarchicalAnnotationFile instance
        """
        instance = cls()
        instance.load(labelme_path)
        return instance

    def validate(self) -> list[str]:
        """
        Validate the annotation file.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Check image info
        if not self.image_path:
            errors.append("No image path specified")

        if not self.image_width or not self.image_height:
            errors.append("Image dimensions not set")

        # Validate hierarchy
        hierarchy_errors = self.shapes.validate_hierarchy()
        errors.extend(hierarchy_errors)

        # Validate shape points
        for shape in self.shapes:
            if len(shape.points) < 2:
                errors.append(f"Shape {shape.shape_id[:8]} has fewer than 2 points")

            if shape.shape_type == "polygon" and len(shape.points) < 3:
                errors.append(
                    f"Polygon shape {shape.shape_id[:8]} has fewer than 3 points"
                )

        return errors


def load_annotation(filename: str) -> HierarchicalAnnotationFile:
    """
    Convenience function to load an annotation file.

    Args:
        filename: Path to JSON file

    Returns:
        HierarchicalAnnotationFile instance
    """
    return HierarchicalAnnotationFile(filename)


def save_annotation(
    annotation: HierarchicalAnnotationFile,
    filename: str,
    include_image_data: bool = True,
) -> None:
    """
    Convenience function to save an annotation file.

    Args:
        annotation: Annotation to save
        filename: Path to save to
        include_image_data: Whether to include base64 image data
    """
    annotation.save(filename, include_image_data=include_image_data)
