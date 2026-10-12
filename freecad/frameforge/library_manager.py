import json
import math
import os
import re

# Standard densities in g/cm3 (equivalent to kg/dm3)
STANDARD_DENSITIES = {
    "Aluminium": 2.70,
    "Steel": 7.85,
    "Stainless Steel": 7.93,
    "Copper": 8.96,
    "Brass": 8.50,
    "Wood (Soft)": 0.55,
    "Wood (Hard)": 0.75,
}

KNOWN_FAMILIES = [
    "Square Hollow",
    "Rectangular Hollow",
    "Pipe",
    "Equal Leg Angles",
    "Unequal Leg Angles",
    "Channels",
    "Square",
    "Round Bar",
    "Flat Sections",
    "T-Slot",
    "V-Slot",
    "Custom Profile",
]


def sanitize_library_name(name):
    """
    Sanitizes a user-provided library name into a safe identifier for filenames.
    Removes path traversal components and replaces non-alphanumeric chars.
    """
    if not name:
        return "unnamed_library"
    # Remove path separators and parent references
    clean = re.sub(r"[\\/]+", "_", name)
    clean = re.sub(r"\.\.+", "", clean)
    # Replace any character that is not alphanumeric or underscore with underscore
    clean = re.sub(r"[^a-zA-Z0-9_\-]", "_", clean)
    # Collapse consecutive underscores and strip leading/trailing underscores
    clean = re.sub(r"_+", "_", clean).strip("_").lower()
    return clean or "unnamed_library"


def calculate_linear_weight(family, width, height, thickness, density_g_cm3=7.85, flange_thickness=None):
    """
    Calculates the theoretical linear mass (weight in kg/m) of a profile
    based on its dimensions (in mm) and material density (in g/cm3).

    1 meter = 1000 mm.
    Volume (cm3) for 1 m = Section Area (mm2) * 1000 / 1000 = Section Area (mm2).
    Weight (kg) = Section Area (mm2) * Density (g/cm3) / 1000.
    """
    w = float(width)
    h = float(height)
    t = float(thickness) if thickness else 0.0
    tf = float(flange_thickness) if flange_thickness else t
    density = float(density_g_cm3)

    area_mm2 = 0.0

    if family in ("Square Hollow", "Rectangular Hollow"):
        # Outer rectangle minus inner rectangle
        if t > 0 and 2 * t < w and 2 * t < h:
            area_mm2 = (w * h) - ((w - 2 * t) * (h - 2 * t))
        else:
            area_mm2 = w * h
    elif family in ("Pipe", "Round Tube"):
        # w is outer diameter (OD)
        if t > 0 and 2 * t < w:
            od = w
            id_ = w - 2 * t
            area_mm2 = (math.pi / 4.0) * (od**2 - id_**2)
        else:
            area_mm2 = (math.pi / 4.0) * (w**2)
    elif family in ("Square", "Flat Sections"):
        area_mm2 = w * h
    elif family in ("Round Bar",):
        area_mm2 = (math.pi / 4.0) * (w**2)
    elif family in ("Equal Leg Angles", "Unequal Leg Angles"):
        # L-shape: Two legs with shared corner of thickness t
        if t > 0:
            area_mm2 = t * (w + h - t)
        else:
            area_mm2 = w * h
    elif family in ("Channels", "C-Channel"):
        # Web (h - 2*tf) of thickness t + 2 flanges of (w * tf)
        if t > 0 and tf > 0:
            area_mm2 = (t * (h - 2 * tf)) + (2 * w * tf)
        else:
            area_mm2 = w * h
    elif family in ("HEA", "HEB", "HEM", "IPE", "IPN", "UPE", "UPN"):
        # Preserve the existing approximation for standard sections.
        area_mm2 = w * h
    else:
        raise ValueError(
            f"Theoretical weight calculation is not supported for complex or slotted geometry '{family}'. Please enter weight manually."
        )

    # Section area in mm2 equals volume in cm3 for 1000 mm length
    weight_kg_m = (area_mm2 * density) / 1000.0
    return round(weight_kg_m, 3)


def get_known_families():
    return list(KNOWN_FAMILIES)


def get_default_stock_profiles_dir():
    """Returns the bundled profiles directory inside FrameForge resources."""
    base_dir = os.path.dirname(__file__)
    return os.path.join(base_dir, "resources", "profiles")


def get_default_user_profiles_dir():
    """
    Returns the user application data directory for FrameForge custom profiles.
    Falls back gracefully when FreeCAD is not running.
    """
    env_dir = os.environ.get("FRAMEFORGE_USER_PROFILES_DIR")
    if env_dir:
        return env_dir

    try:
        import FreeCAD

        app_data = FreeCAD.getUserAppDataDir()
        return os.path.join(app_data, "FrameForge", "profiles")
    except Exception:
        # Fallback for CLI or headless testing outside FreeCAD
        xdg_data = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        return os.path.join(xdg_data, "FreeCAD", "FrameForge", "profiles")


class LibraryManager:
    """
    Central manager for FrameForge profile libraries.
    Discovers stock (bundled) and user-defined libraries, handles persistence,
    validation, cloning, and formatting for FreeCAD UI tools.
    """

    def __init__(self, user_dir=None, stock_dir=None):
        self.stock_dir = stock_dir or get_default_stock_profiles_dir()
        self.user_dir = user_dir or get_default_user_profiles_dir()

    def list_libraries(self):
        """
        Discovers all available libraries across stock and user directories.
        Returns a list of metadata dictionaries.
        """
        libraries = []
        seen_names = set()

        # 1. Discover user libraries first (user libraries take precedence if shadowing)
        if os.path.exists(self.user_dir):
            for filename in sorted(os.listdir(self.user_dir)):
                if filename.endswith(".json"):
                    filepath = os.path.join(self.user_dir, filename)
                    name = self._extract_library_name(filename, filepath)
                    seen_names.add(name.lower())
                    libraries.append(
                        {
                            "name": name,
                            "filename": filename,
                            "path": filepath,
                            "is_user": True,
                            "can_delete": True,
                        }
                    )

        # 2. Discover stock libraries
        if os.path.exists(self.stock_dir):
            for filename in sorted(os.listdir(self.stock_dir)):
                if filename.endswith(".json"):
                    filepath = os.path.join(self.stock_dir, filename)
                    name = self._extract_library_name(filename, filepath)
                    if name.lower() not in seen_names:
                        libraries.append(
                            {
                                "name": name,
                                "filename": filename,
                                "path": filepath,
                                "is_user": False,
                                "can_delete": False,
                            }
                        )

        return sorted(libraries, key=lambda x: (not x["is_user"], x["name"].lower()))

    def _extract_library_name(self, filename, filepath):
        """Extracts display name from file, formatting appropriately."""
        # Try reading title or name from JSON metadata if present
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "_metadata" in data and "name" in data["_metadata"]:
                    return data["_metadata"]["name"]
        except Exception:
            pass

        base = os.path.splitext(filename)[0]
        # Capitalize words separated by underscores or hyphens
        parts = re.split(r"[_\-]+", base)
        return " ".join(part.capitalize() for part in parts if part) or base.capitalize()

    def get_library(self, name):
        """
        Loads the catalog JSON for the specified library name.
        Prioritizes exact display-name match over filename slug aliases.
        """
        target_name = name.strip().lower()

        # Pass 1: exact display-name match (stock first to guard system libraries, then user)
        candidates = []
        for is_user, directory in [(False, self.stock_dir), (True, self.user_dir)]:
            if os.path.exists(directory):
                for filename in os.listdir(directory):
                    if filename.endswith(".json"):
                        filepath = os.path.join(directory, filename)
                        lib_name = self._extract_library_name(filename, filepath).lower()
                        if lib_name == target_name:
                            with open(filepath, "r", encoding="utf-8") as f:
                                return json.load(f)
                        candidates.append((filename, filepath))

        # Pass 2: filename slug alias fallback
        for filename, filepath in candidates:
            if os.path.splitext(filename)[0].lower() == target_name:
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)

        raise FileNotFoundError(f"Library '{name}' not found.")

    def save_user_library(self, name, data, overwrite=True):
        """
        Saves or updates a user library JSON in user_dir.
        If overwrite is False, raises FileExistsError if target file already exists.
        """
        os.makedirs(self.user_dir, exist_ok=True)
        file_slug = sanitize_library_name(name)
        filename = f"{file_slug}.json"
        filepath = os.path.join(self.user_dir, filename)

        if not overwrite and os.path.exists(filepath):
            raise FileExistsError(f"A library file '{filename}' already exists.")

        # Ensure _metadata preserves exact user display name
        if isinstance(data, dict):
            if "_metadata" not in data:
                data["_metadata"] = {}
            data["_metadata"]["name"] = name

        temp_path = f"{filepath}.tmp.{os.getpid()}"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
                f.flush()
            os.replace(temp_path, filepath)
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

        return filepath

    def delete_user_library(self, name):
        """
        Deletes a user-defined library. Raises ValueError if library is stock.
        """
        target_name = name.strip().lower()

        # Find in user dir
        if os.path.exists(self.user_dir):
            for filename in os.listdir(self.user_dir):
                if filename.endswith(".json"):
                    filepath = os.path.join(self.user_dir, filename)
                    lib_name = self._extract_library_name(filename, filepath).lower()
                    if lib_name == target_name or os.path.splitext(filename)[0].lower() == target_name:
                        os.remove(filepath)
                        return True

        # Check if user tried to delete a stock library
        if os.path.exists(self.stock_dir):
            for filename in os.listdir(self.stock_dir):
                if filename.endswith(".json"):
                    filepath = os.path.join(self.stock_dir, filename)
                    lib_name = self._extract_library_name(filename, filepath).lower()
                    if lib_name == target_name or os.path.splitext(filename)[0].lower() == target_name:
                        raise ValueError(f"Cannot delete bundled stock library '{name}'.")

        raise FileNotFoundError(f"Library '{name}' not found in user libraries.")

    def duplicate_library(self, source_name, target_name, overwrite=False):
        """
        Clones an existing library (stock or user) into a new user library.
        If overwrite is False, raises FileExistsError if target already exists.
        """
        source_data = self.get_library(source_name)
        # Deep copy via serialization
        cloned_data = json.loads(json.dumps(source_data))

        # Update metadata if present
        if "_metadata" in cloned_data:
            cloned_data["_metadata"]["name"] = target_name
            cloned_data["_metadata"]["cloned_from"] = source_name
        else:
            cloned_data["_metadata"] = {
                "name": target_name,
                "cloned_from": source_name,
            }

        return self.save_user_library(target_name, cloned_data, overwrite=overwrite)

    def get_all_profiles(self):
        """
        Returns a dictionary mapping library display names to their profile definitions,
        directly usable by create_profiles_tool.
        """
        profiles = {}
        libs = self.list_libraries()
        for lib in libs:
            try:
                data = self.get_library(lib["name"])
                # Strip internal metadata before handing to create_profiles_tool so it only sees families
                clean_families = {k: v for k, v in data.items() if not k.startswith("_")}
                profiles[lib["name"]] = clean_families
            except Exception:
                continue
        return profiles
