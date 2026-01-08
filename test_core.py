#!/usr/bin/env python3
"""
Simple test script for hierarchical labelme core modules.
Run with: python test_core.py
"""

import importlib.util
import os
import sys
import tempfile

# Get directory containing labelme
base_dir = os.path.dirname(os.path.abspath(__file__))


def load_module(name, filepath):
    """Load a module directly without triggering package __init__.py."""
    spec = importlib.util.spec_from_file_location(name, filepath)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Load modules directly to avoid onnxruntime dependency
schema_module = load_module(
    "labelme.schema_manager", os.path.join(base_dir, "labelme", "schema_manager.py")
)
SchemaManager = schema_module.SchemaManager

shape_module = load_module(
    "labelme.hierarchical_shape",
    os.path.join(base_dir, "labelme", "hierarchical_shape.py"),
)
HierarchicalShape = shape_module.HierarchicalShape
ShapeCollection = shape_module.ShapeCollection

label_file_module = load_module(
    "labelme.hierarchical_label_file",
    os.path.join(base_dir, "labelme", "hierarchical_label_file.py"),
)
HierarchicalAnnotationFile = label_file_module.HierarchicalAnnotationFile


def test_schema_manager():
    """Test SchemaManager."""
    print("=== Schema Manager Tests ===")

    schema = SchemaManager("annotation_schema.yaml")
    print("Schema loaded: OK")
    print(f"  Version: {schema.get_version()}")
    print(f"  Classes: {schema.get_all_classes()[:5]}...")
    print(f"  Box display: {schema.get_display_name('box')}")
    print(f"  Box color: {schema.get_color('box')}")
    print(f"  Box children: {schema.get_allowed_children('box')}")

    # Test validation
    assert schema.validate_parent_child("box", "face")
    assert not schema.validate_parent_child("face", "box")
    print("  Validation: OK")

    # Test parent requirements
    assert not schema.requires_parent("box")
    assert schema.requires_parent("face")
    print("  Parent requirements: OK")

    # Test attributes
    attrs = schema.get_attributes_config("box")
    assert "box_type" in attrs
    print("  Attributes: OK")

    # Test shortcuts
    shortcuts = schema.get_shortcuts()
    assert shortcuts.get("b") == "box"
    print("  Shortcuts: OK")

    return schema


def test_hierarchical_shape():
    """Test HierarchicalShape."""
    print("\n=== HierarchicalShape Tests ===")

    # Create shape
    shape = HierarchicalShape(
        label="box", points=[[0, 0], [100, 0], [100, 100], [0, 100]]
    )

    assert shape.label == "box"
    assert len(shape.points) == 4
    assert len(shape.shape_id) == 32
    print("Shape created: OK")
    print(f"  ID: {shape.shape_id[:16]}...")

    # Test attributes
    shape.set_attribute("box_type", "cardboard")
    assert shape.get_attribute("box_type") == "cardboard"
    print("  Attributes: OK")

    # Test serialization
    data = shape.to_dict()
    assert "shape_id" in data
    assert data["label"] == "box"
    print("  Serialization: OK")

    # Test deserialization
    restored = HierarchicalShape.from_dict(data)
    assert restored.shape_id == shape.shape_id
    assert restored.label == shape.label
    print("  Deserialization: OK")

    # Test copy
    copy = shape.copy()
    assert copy.shape_id != shape.shape_id
    assert copy.label == shape.label
    print("  Copy: OK")

    return shape


def test_shape_collection():
    """Test ShapeCollection."""
    print("\n=== ShapeCollection Tests ===")

    collection = ShapeCollection()

    # Create shapes
    box = collection.create_shape(
        label="box", points=[[0, 0], [100, 0], [100, 100], [0, 100]]
    )

    face = collection.create_child(
        parent=box, label="face", points=[[10, 10], [50, 10], [50, 50], [10, 50]]
    )

    label = collection.create_child(
        parent=face, label="label", points=[[20, 20], [30, 20], [30, 30], [20, 30]]
    )

    assert len(collection) == 3
    print(f"Created collection: OK ({len(collection)} shapes)")

    # Test root shapes
    roots = collection.get_root_shapes()
    assert len(roots) == 1
    assert box in roots
    print(f"  Root shapes: OK ({len(roots)})")

    # Test children
    children = collection.get_children(box)
    assert len(children) == 1
    assert face in children
    print(f"  Children: OK ({len(children)})")

    # Test parent
    parent = collection.get_parent(face)
    assert parent == box
    print("  Parent: OK")

    # Test ancestors
    ancestors = collection.get_ancestors(label)
    assert len(ancestors) == 2
    assert ancestors[0] == face
    assert ancestors[1] == box
    print(f"  Ancestors: OK ({len(ancestors)})")

    # Test descendants
    descendants = collection.get_descendants(box)
    assert len(descendants) == 2
    print(f"  Descendants: OK ({len(descendants)})")

    # Test hierarchy validation
    errors = collection.validate_hierarchy()
    assert len(errors) == 0
    print("  Validation: OK")

    # Test shapes by label
    boxes = collection.get_shapes_by_label("box")
    assert len(boxes) == 1
    print("  Filter by label: OK")

    return collection


def test_label_file(collection):
    """Test HierarchicalAnnotationFile."""
    print("\n=== HierarchicalAnnotationFile Tests ===")

    # Create file
    file = HierarchicalAnnotationFile()
    file.image_path = "test.jpg"
    file.image_width = 640
    file.image_height = 480
    file.shapes = collection

    # Save to temp file
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        temp_path = f.name

    try:
        file.save(temp_path, include_image_data=False)
        print("Saved: OK")

        # Load
        loaded = HierarchicalAnnotationFile(temp_path)
        assert len(loaded.shapes) == 3
        assert loaded.image_path == "test.jpg"
        print(f"Loaded: OK ({len(loaded.shapes)} shapes)")

        # Verify hierarchy preserved
        loaded_box = list(loaded.shapes.get_shapes_by_label("box"))[0]
        loaded_face = list(loaded.shapes.get_shapes_by_label("face"))[0]
        assert loaded_face.parent_id == loaded_box.shape_id
        print("  Hierarchy preserved: OK")

        # Test stats
        stats = loaded.get_statistics()
        assert stats["total_shapes"] == 3
        assert stats["max_depth"] == 3
        print(f"  Statistics: OK (depth={stats['max_depth']})")

        # Test validation
        loaded.validate()
        # We expect image dimension errors since we don't have actual image
        print("  Validation: OK")

    finally:
        os.unlink(temp_path)

    return file


def test_coco_export(file):
    """Test COCO export."""
    print("\n=== COCO Export Test ===")

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        temp_path = f.name

    try:
        file.export_coco(temp_path)

        import json

        with open(temp_path) as f:
            coco_data = json.load(f)

        assert "images" in coco_data
        assert "annotations" in coco_data
        assert "categories" in coco_data
        assert len(coco_data["annotations"]) == 3
        print(f"COCO export: OK ({len(coco_data['annotations'])} annotations)")

    finally:
        os.unlink(temp_path)


def test_yolo_export(file):
    """Test YOLO export."""
    print("\n=== YOLO Export Test ===")

    with tempfile.TemporaryDirectory() as temp_dir:
        file.export_yolo(temp_dir)

        txt_path = os.path.join(temp_dir, "test.txt")
        assert os.path.exists(txt_path)

        with open(txt_path) as f:
            lines = f.readlines()

        assert len(lines) == 3
        print(f"YOLO export: OK ({len(lines)} lines)")


def main():
    """Run all tests."""
    print("=" * 50)
    print("Hierarchical Labelme Core Module Tests")
    print("=" * 50)

    try:
        test_schema_manager()
        test_hierarchical_shape()
        collection = test_shape_collection()
        file = test_label_file(collection)
        test_coco_export(file)
        test_yolo_export(file)

        print("\n" + "=" * 50)
        print("ALL TESTS PASSED!")
        print("=" * 50)
        return 0

    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
