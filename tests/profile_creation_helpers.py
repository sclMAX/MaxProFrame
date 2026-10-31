"""Shared builders that create profiles through the production Create Profile panel."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from freecad.maxproframe import create_profiles_tool
from freecad.maxproframe.create_profiles_tool import CreateProfileTaskPanel

CUSTOM_FAMILY = "Custom Profile"
CUSTOM_SIZE = "CUSTOM-1"


def creation_panel(
    family="Flat Sections",
    size="20x10",
    material="Steel",
    width=20.0,
    height=10.0,
    length=100.0,
    weight=0.0,
    unitprice=0.0,
):
    """Return a CreateProfileTaskPanel whose form reports fixed values, without building Qt widgets."""
    panel = CreateProfileTaskPanel.__new__(CreateProfileTaskPanel)
    values = {
        "width": width,
        "height": height,
        "main_thickness": 1,
        "flange_thickness": 1,
        "radius1": 0,
        "radius2": 0,
        "length": length,
        "weight": weight,
        "unitprice": unitprice,
        "offset_x": 0,
        "offset_y": 0,
    }
    fields = {"sb_" + key: Mock(value=Mock(return_value=value)) for key, value in values.items()}
    for key in ("pre_extend", "mirror_h", "mirror_v", "make_fillet", "combined_bevel"):
        fields["cb_" + key] = Mock(isChecked=Mock(return_value=False))
    for key, value in (("material", material), ("family", family), ("size", size)):
        fields["combo_" + key] = Mock(currentText=Mock(return_value=value))
    panel.form_proxy = SimpleNamespace(**fields)
    panel.get_anchor = lambda: (1, 1)
    panel.get_rotation = lambda: 0.0
    panel.profiles = {}
    panel._mutation_depth = 0
    panel._selection_pending = False
    panel._selection_signature = lambda: ()
    return panel


def make_custom_profile(
    path,
    edge,
    name,
    section,
    length=100.0,
    material="Steel",
    weight=0.0,
    unitprice=0.0,
):
    """Create a Custom Profile through the panel; only the library import returns ``section``."""
    panel = creation_panel(
        family=CUSTOM_FAMILY,
        size=CUSTOM_SIZE,
        material=material,
        width=0.0,
        height=0.0,
        length=length,
        weight=weight,
        unitprice=unitprice,
    )
    panel.profiles = {material: {CUSTOM_FAMILY: {"sizes": {CUSTOM_SIZE: {"asset_path": "section.FCStd"}}}}}
    panel.library_manager = Mock()
    panel.library_manager._get_registered_folder.return_value = "unused"
    with patch.object(create_profiles_tool, "get_or_import_section_sketch", return_value=section):
        return panel.make_profile(path, edge, name)
