"""Bend configurations of folded miters: how a tube wall bends and how much length each bend develops.

A configuration names a material, a wall thickness, an inside bend radius and a K-factor (where the neutral axis
sits inside the wall, 0 at the inside face, 1 at the outside face). Configurations persist between sessions in a
versioned JSON file in a hidden folder next to the profile libraries, so the library list never shows it; every
save replaces the file atomically. The last used configuration is kept in the MaxProFrame FreeCAD parameters.
"""

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass

from freecad.maxproframe.library_manager import get_default_user_profiles_dir

FILE_VERSION = 1
FOLDER_NAME = ".bend"
FILE_NAME = "configurations.json"
LAST_USED_PARAM = "LastBendConfiguration"


@dataclass(frozen=True)
class BendConfiguration:
    name: str
    material: str
    thickness: float
    inside_radius: float
    k_factor: float


def translate(context, text):
    """FreeCAD's translate, imported when a message is shown: this module loads without the GUI."""
    from freecad.maxproframe.ff_tools import translate as qt_translate

    return qt_translate(context, text)


def _number(value):
    """``value`` as a finite float, or None."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _format_mm(value):
    return f"{value:g}"


def validated(configuration):
    """``configuration`` with trimmed texts and float values; raises ValueError naming the first invalid field."""
    name = configuration.name.strip() if isinstance(configuration.name, str) else ""
    if not name:
        raise ValueError(translate("MaxProFrame", "The configuration name must not be empty."))
    material = configuration.material.strip() if isinstance(configuration.material, str) else ""
    if not material:
        raise ValueError(translate("MaxProFrame", "The material must not be empty."))
    thickness = _number(configuration.thickness)
    if thickness is None or thickness <= 0:
        raise ValueError(translate("MaxProFrame", "The wall thickness must be greater than 0 mm."))
    radius = _number(configuration.inside_radius)
    if radius is None or radius < thickness:
        raise ValueError(
            translate("MaxProFrame", "The inside bend radius must be at least the wall thickness ({} mm).").format(
                _format_mm(thickness)
            )
        )
    k_factor = _number(configuration.k_factor)
    if k_factor is None or not 0 <= k_factor <= 1:
        raise ValueError(translate("MaxProFrame", "The K-factor must be between 0 and 1."))
    return BendConfiguration(name, material, thickness, radius, k_factor)


class BendConfigurationStore:
    """Named bend configurations stored in ``<user profiles dir>/.bend/configurations.json``."""

    def __init__(self, user_dir=None):
        self.path = os.path.join(user_dir or get_default_user_profiles_dir(), FOLDER_NAME, FILE_NAME)

    def configurations(self):
        """Every stored configuration, sorted by name (case-insensitive)."""
        return sorted(self._load().values(), key=lambda configuration: configuration.name.casefold())

    def get(self, name):
        """The configuration called ``name``, or None."""
        return self._load().get(name)

    def save(self, configuration):
        """Add ``configuration`` or replace the one with the same name; returns the stored value."""
        configuration = validated(configuration)
        stored = self._load()
        stored[configuration.name] = configuration
        self._write(stored)
        return configuration

    def delete(self, name):
        stored = self._load()
        if name not in stored:
            raise KeyError(translate("MaxProFrame", 'Bend configuration "{}" does not exist.').format(name))
        del stored[name]
        self._write(stored)

    def _load(self):
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            raise ValueError(self._corrupt(err)) from err
        if not isinstance(data, dict) or not isinstance(data.get("configurations"), list):
            raise ValueError(self._corrupt(translate("MaxProFrame", "'configurations' must be a list.")))
        version = data.get("version")
        if version != FILE_VERSION:
            raise ValueError(
                translate(
                    "MaxProFrame", "Bend configurations file '{}' has version {}; this MaxProFrame reads version {}."
                ).format(self.path, version, FILE_VERSION)
            )
        stored = {}
        for entry in data["configurations"]:
            try:
                configuration = validated(
                    BendConfiguration(
                        entry.get("name"),
                        entry.get("material"),
                        entry.get("thickness"),
                        entry.get("inside_radius"),
                        entry.get("k_factor"),
                    )
                )
            except (AttributeError, ValueError) as err:
                message = (
                    str(err)
                    if isinstance(err, ValueError)
                    else translate("MaxProFrame", "each configuration must be an object.")
                )
                raise ValueError(self._corrupt(message)) from err
            stored[configuration.name] = configuration
        return stored

    def _corrupt(self, detail):
        return translate("MaxProFrame", "Corrupt bend configurations file '{}': {}").format(self.path, detail)

    def _write(self, stored):
        folder = os.path.dirname(self.path)
        os.makedirs(folder, exist_ok=True)
        data = {
            "version": FILE_VERSION,
            "configurations": [
                asdict(configuration)
                for configuration in sorted(stored.values(), key=lambda configuration: configuration.name.casefold())
            ],
        }
        fd, temp_path = tempfile.mkstemp(prefix="tmp_bend_", dir=folder)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=4)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        except BaseException:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise


def get_last_used_configuration():
    """Name of the last used bend configuration, or an empty string."""
    from freecad.maxproframe.ff_tools import get_param_group

    return get_param_group().GetString(LAST_USED_PARAM, "")


def set_last_used_configuration(name):
    from freecad.maxproframe.ff_tools import get_param_group

    get_param_group().SetString(LAST_USED_PARAM, name)
