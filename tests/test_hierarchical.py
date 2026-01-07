#!/usr/bin/env python
"""
Test suite for Hierarchical Labelme components.

Run with: python -m pytest tests/test_hierarchical.py -v
Or: python tests/test_hierarchical.py
"""

import os
import sys
import tempfile
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from labelme.schema_manager import SchemaManager, SchemaValidationError
from labelme.hierarchical_shape import HierarchicalShape, ShapeCollection, generate_uuid
from labelme.hierarchical_label_file import HierarchicalAnnotationFile


# ============================================================================
# Schema Manager Tests
# ============================================================================

class TestSchemaManager:
    """Tests for SchemaManager class."""

    @pytest.fixture
    def schema_path(self):
        """Get path to test schema."""
        return Path(__file__).parent.parent / "annotation_schema.yaml"

    @pytest.fixture
    def schema(self, schema_path):
        """Load schema manager."""
        return SchemaManager(schema_path)

    def test_load_schema(self, schema):
        """Test schema loads successfully."""
        assert schema is not None
        assert schema.get_version() == "1.0"

    def test_get_all_classes(self, schema):
        """Test getting all classes."""
        classes = schema.get_all_classes()
        assert len(classes) > 0
        assert "box" in classes
        assert "face" in classes

    def test_get_display_name(self, schema):
        """Test getting display names."""
        assert schema.get_display_name("box") == "Box"
        assert schema.get_display_name("face") == "Box Face"

    def test_get_color(self, schema):
        """Test getting colors."""
        color = schema.get_color("box")
        assert color.startswith("#")
        assert len(color) == 7

    def test_get_allowed_children(self, schema):
        """Test getting allowed children."""
        children = schema.get_allowed_children("box")
        assert "face" in children
        assert "label" in children

    def test_can_have_children(self, schema):
        """Test checking if class can have children."""
        assert schema.can_have_children("box") is True
        assert schema.can_have_children("barcode") is False

    def test_requires_parent(self, schema):
        """Test checking if class requires parent."""
        assert schema.requires_parent("box") is False
        assert schema.requires_parent("face") is True

    def test_validate_parent_child(self, schema):
        """Test validating parent-child relationships."""
        assert schema.validate_parent_child("box", "face") is True
        assert schema.validate_parent_child("face", "box") is False
        assert schema.validate_parent_child("box", "barcode") is True

    def test_get_top_level_classes(self, schema):
        """Test getting top-level classes."""
        top_level = schema.get_top_level_classes()
        assert "box" in top_level
        assert "wall" in top_level
        assert "face" not in top_level

    def test_get_attributes_config(self, schema):
        """Test getting attribute configuration."""
        attrs = schema.get_attributes_config("box")
        assert "box_type" in attrs
        assert attrs["box_type"]["type"] == "dropdown"

    def test_check_attribute_visibility(self, schema):
        """Test conditional attribute visibility."""
        # length_cm is visible only when dimensions_known is True
        assert schema.check_attribute_visibility(
            "box", "length_cm", {"dimensions_known": True}
        ) is True
        assert schema.check_attribute_visibility(
            "box", "length_cm", {"dimensions_known": False}
        ) is False

    def test_get_shortcuts(self, schema):
        """Test getting keyboard shortcuts."""
        shortcuts = schema.get_shortcuts()
        assert "b" in shortcuts
        assert shortcuts["b"] == "box"

    def test_schema_file_not_found(self):
        """Test error when schema file not found."""
        with pytest.raises(FileNotFoundError):
            SchemaManager("nonexistent.yaml")


# ============================================================================
# HierarchicalShape Tests
# ============================================================================

class TestHierarchicalShape:
    """Tests for HierarchicalShape class."""

    def test_create_shape(self):
        """Test creating a shape."""
        shape = HierarchicalShape(
            label="box",
            points=[[0, 0], [100, 0], [100, 100], [0, 100]]
        )
        assert shape.label == "box"
        assert len(shape.points) == 4
        assert shape.shape_id is not None
        assert len(shape.shape_id) == 32  # UUID hex

    def test_set_parent(self):
        """Test setting parent."""
        parent = HierarchicalShape(label="box", points=[])
        child = HierarchicalShape(label="face", points=[])

        child.set_parent(parent)

        assert child.parent_id == parent.shape_id
        assert child.has_parent() is True

    def test_add_child(self):
        """Test adding child."""
        parent = HierarchicalShape(label="box", points=[])
        child = HierarchicalShape(label="face", points=[])

        parent.add_child(child)

        assert child.shape_id in parent.children_ids
        assert child.parent_id == parent.shape_id
        assert parent.has_children() is True

    def test_remove_child(self):
        """Test removing child."""
        parent = HierarchicalShape(label="box", points=[])
        child = HierarchicalShape(label="face", points=[])

        parent.add_child(child)
        parent.remove_child(child)

        assert child.shape_id not in parent.children_ids
        assert parent.has_children() is False

    def test_set_attribute(self):
        """Test setting attributes."""
        shape = HierarchicalShape(label="box", points=[])
        shape.set_attribute("box_type", "cardboard")

        assert shape.get_attribute("box_type") == "cardboard"

    def test_to_dict(self):
        """Test serialization."""
        shape = HierarchicalShape(
            label="box",
            points=[[0, 0], [100, 100]],
            attributes={"box_type": "cardboard"}
        )
        data = shape.to_dict()

        assert data["label"] == "box"
        assert data["points"] == [[0, 0], [100, 100]]
        assert data["attributes"]["box_type"] == "cardboard"
        assert "shape_id" in data

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "shape_id": "abc123",
            "label": "box",
            "points": [[0, 0], [100, 100]],
            "shape_type": "polygon",
            "attributes": {"box_type": "plastic"}
        }
        shape = HierarchicalShape.from_dict(data)

        assert shape.shape_id == "abc123"
        assert shape.label == "box"
        assert shape.attributes["box_type"] == "plastic"

    def test_copy(self):
        """Test copying shape."""
        original = HierarchicalShape(
            label="box",
            points=[[0, 0], [100, 100]],
            attributes={"box_type": "cardboard"}
        )
        copy = original.copy()

        assert copy.shape_id != original.shape_id
        assert copy.label == original.label
        assert copy.attributes["box_type"] == "cardboard"
        assert copy.parent_id is None


# ============================================================================
# ShapeCollection Tests
# ============================================================================

class TestShapeCollection:
    """Tests for ShapeCollection class."""

    def test_add_shape(self):
        """Test adding shapes."""
        collection = ShapeCollection()
        shape = HierarchicalShape(label="box", points=[])

        added = collection.add_shape(shape)

        assert len(collection) == 1
        assert shape.shape_id in collection

    def test_create_shape(self):
        """Test creating shapes."""
        collection = ShapeCollection()
        shape = collection.create_shape(
            label="box",
            points=[[0, 0], [100, 100]]
        )

        assert len(collection) == 1
        assert shape.label == "box"

    def test_create_child(self):
        """Test creating child shapes."""
        collection = ShapeCollection()
        parent = collection.create_shape(label="box", points=[])
        child = collection.create_child(
            parent=parent,
            label="face",
            points=[[10, 10], [50, 50]]
        )

        assert len(collection) == 2
        assert child.parent_id == parent.shape_id
        assert child.shape_id in parent.children_ids

    def test_get_root_shapes(self):
        """Test getting root shapes."""
        collection = ShapeCollection()
        box1 = collection.create_shape(label="box", points=[])
        box2 = collection.create_shape(label="box", points=[])
        face = collection.create_child(box1, label="face", points=[])

        roots = collection.get_root_shapes()

        assert len(roots) == 2
        assert box1 in roots
        assert box2 in roots
        assert face not in roots

    def test_get_children(self):
        """Test getting children."""
        collection = ShapeCollection()
        parent = collection.create_shape(label="box", points=[])
        child1 = collection.create_child(parent, label="face", points=[])
        child2 = collection.create_child(parent, label="label", points=[])

        children = collection.get_children(parent)

        assert len(children) == 2
        assert child1 in children
        assert child2 in children

    def test_remove_shape_with_children(self):
        """Test removing shape with children."""
        collection = ShapeCollection()
        parent = collection.create_shape(label="box", points=[])
        child = collection.create_child(parent, label="face", points=[])

        removed = collection.remove_shape(parent.shape_id, remove_children=True)

        assert len(collection) == 0
        assert len(removed) == 2

    def test_remove_shape_orphan_children(self):
        """Test removing shape, orphaning children."""
        collection = ShapeCollection()
        parent = collection.create_shape(label="box", points=[])
        child = collection.create_child(parent, label="face", points=[])

        collection.remove_shape(parent.shape_id, remove_children=False)

        assert len(collection) == 1
        assert child.parent_id is None
        assert child in collection.get_root_shapes()

    def test_reparent(self):
        """Test reparenting shape."""
        collection = ShapeCollection()
        parent1 = collection.create_shape(label="box", points=[])
        parent2 = collection.create_shape(label="box", points=[])
        child = collection.create_child(parent1, label="face", points=[])

        collection.reparent(child, parent2)

        assert child.parent_id == parent2.shape_id
        assert child.shape_id not in parent1.children_ids
        assert child.shape_id in parent2.children_ids

    def test_get_shapes_by_label(self):
        """Test getting shapes by label."""
        collection = ShapeCollection()
        collection.create_shape(label="box", points=[])
        collection.create_shape(label="box", points=[])
        collection.create_shape(label="wall", points=[])

        boxes = collection.get_shapes_by_label("box")

        assert len(boxes) == 2

    def test_validate_hierarchy(self):
        """Test hierarchy validation."""
        collection = ShapeCollection()
        parent = collection.create_shape(label="box", points=[])
        child = collection.create_child(parent, label="face", points=[])

        errors = collection.validate_hierarchy()

        assert len(errors) == 0


# ============================================================================
# HierarchicalAnnotationFile Tests
# ============================================================================

class TestHierarchicalAnnotationFile:
    """Tests for HierarchicalAnnotationFile class."""

    def test_create_empty(self):
        """Test creating empty file."""
        file = HierarchicalAnnotationFile()
        assert len(file.shapes) == 0

    def test_add_shapes(self):
        """Test adding shapes to file."""
        file = HierarchicalAnnotationFile()
        shape = HierarchicalShape(label="box", points=[[0, 0], [100, 100]])
        file.add_shape(shape)

        assert len(file.shapes) == 1

    def test_save_and_load(self):
        """Test saving and loading file."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            # Create and save
            file1 = HierarchicalAnnotationFile()
            file1.image_path = "test.jpg"
            file1.image_width = 640
            file1.image_height = 480

            box = file1.shapes.create_shape(
                label="box",
                points=[[0, 0], [100, 0], [100, 100], [0, 100]]
            )
            face = file1.shapes.create_child(
                parent=box,
                label="face",
                points=[[10, 10], [50, 10], [50, 50], [10, 50]]
            )

            file1.save(temp_path, include_image_data=False)

            # Load
            file2 = HierarchicalAnnotationFile(temp_path)

            assert file2.image_path == "test.jpg"
            assert len(file2.shapes) == 2

            # Check hierarchy preserved
            loaded_box = file2.shapes.get_shapes_by_label("box")[0]
            loaded_face = file2.shapes.get_shapes_by_label("face")[0]

            assert loaded_face.parent_id == loaded_box.shape_id
            assert loaded_face.shape_id in loaded_box.children_ids

        finally:
            os.unlink(temp_path)

    def test_load_legacy_format(self):
        """Test loading legacy labelme format."""
        legacy_data = {
            "version": "5.0.0",
            "imagePath": "test.jpg",
            "imageHeight": 480,
            "imageWidth": 640,
            "shapes": [
                {
                    "label": "box",
                    "points": [[0, 0], [100, 100]],
                    "shape_type": "polygon",
                    "flags": {}
                }
            ]
        }

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode='w') as f:
            json.dump(legacy_data, f)
            temp_path = f.name

        try:
            file = HierarchicalAnnotationFile(temp_path)

            assert len(file.shapes) == 1
            shape = list(file.shapes)[0]
            assert shape.label == "box"
            # Legacy shapes get auto-generated IDs
            assert shape.shape_id is not None

        finally:
            os.unlink(temp_path)

    def test_export_coco(self):
        """Test COCO export."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            file = HierarchicalAnnotationFile()
            file.image_path = "test.jpg"
            file.image_width = 640
            file.image_height = 480

            file.shapes.create_shape(
                label="box",
                points=[[0, 0], [100, 0], [100, 100], [0, 100]]
            )

            file.export_coco(temp_path)

            # Verify COCO format
            with open(temp_path) as f:
                coco_data = json.load(f)

            assert "images" in coco_data
            assert "annotations" in coco_data
            assert "categories" in coco_data
            assert len(coco_data["annotations"]) == 1

        finally:
            os.unlink(temp_path)

    def test_export_yolo(self):
        """Test YOLO export."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file = HierarchicalAnnotationFile()
            file.image_path = "test.jpg"
            file.image_width = 640
            file.image_height = 480

            file.shapes.create_shape(
                label="box",
                points=[[0, 0], [100, 0], [100, 100], [0, 100]]
            )

            file.export_yolo(temp_dir)

            txt_path = os.path.join(temp_dir, "test.txt")
            assert os.path.exists(txt_path)

            with open(txt_path) as f:
                content = f.read()
            assert len(content.strip()) > 0

    def test_get_statistics(self):
        """Test getting statistics."""
        file = HierarchicalAnnotationFile()
        box = file.shapes.create_shape(label="box", points=[[0, 0], [100, 100]])
        file.shapes.create_child(box, label="face", points=[[10, 10], [50, 50]])
        file.shapes.create_child(box, label="face", points=[[60, 10], [90, 50]])

        stats = file.get_statistics()

        assert stats["total_shapes"] == 3
        assert stats["root_shapes"] == 1
        assert stats["shapes_by_label"]["box"] == 1
        assert stats["shapes_by_label"]["face"] == 2
        assert stats["max_depth"] == 2


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for hierarchical annotation system."""

    @pytest.fixture
    def schema(self):
        """Load schema."""
        schema_path = Path(__file__).parent.parent / "annotation_schema.yaml"
        return SchemaManager(schema_path)

    def test_full_workflow(self, schema):
        """Test complete annotation workflow."""
        # Create file
        file = HierarchicalAnnotationFile()
        file.image_path = "warehouse.jpg"
        file.image_width = 1920
        file.image_height = 1080

        # Create box
        box = file.shapes.create_shape(
            label="box",
            points=[[100, 100], [300, 100], [300, 300], [100, 300]],
            attributes=schema.get_all_defaults("box")
        )

        # Validate we can add face as child
        assert schema.validate_parent_child("box", "face")

        # Create face as child
        face = file.shapes.create_child(
            parent=box,
            label="face",
            points=[[110, 110], [200, 110], [200, 200], [110, 200]],
            attributes=schema.get_all_defaults("face")
        )

        # Set face attributes
        face.set_attribute("face_type", "front")
        face.set_attribute("occlusion", 10)

        # Create barcode as child of face
        barcode = file.shapes.create_child(
            parent=face,
            label="barcode",
            points=[[120, 120], [180, 120], [180, 140], [120, 140]],
            attributes=schema.get_all_defaults("barcode")
        )

        # Verify hierarchy
        assert box.has_children()
        assert face.parent_id == box.shape_id
        assert barcode.parent_id == face.shape_id

        # Verify hierarchy depth
        ancestors = file.shapes.get_ancestors(barcode)
        assert len(ancestors) == 2
        assert ancestors[0] == face
        assert ancestors[1] == box

        # Save and reload
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            file.save(temp_path)
            loaded = HierarchicalAnnotationFile(temp_path)

            assert len(loaded.shapes) == 3

            # Verify relationships preserved
            loaded_barcode = loaded.shapes.get_shapes_by_label("barcode")[0]
            assert loaded_barcode.get_attribute("barcode_type") is not None

            # Get ancestors of loaded barcode
            loaded_ancestors = loaded.shapes.get_ancestors(loaded_barcode)
            assert len(loaded_ancestors) == 2

        finally:
            os.unlink(temp_path)


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
