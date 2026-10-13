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

FILLET_FAMILIES = frozenset(
    {
        "Square Hollow",
        "Rectangular Hollow",
        "Equal Leg Angles",
        "Unequal Leg Angles",
        "HEA",
        "HEB",
        "HEM",
        "IPE",
        "IPN",
        "UPE",
        "UPN",
    }
)


def get_canonical_family(family_key, family_data=None):
    """
    Returns explicit canonical_family from family metadata when present,
    otherwise returns family_key unchanged.
    Does not guess from suffixes or alter unknown keys.
    """
    if isinstance(family_data, dict):
        canonical = family_data.get("canonical_family")
        if canonical:
            return str(canonical)
    return family_key



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
                    name, mat, dens = self._extract_library_metadata(filename, filepath)
                    seen_names.add(name.lower())
                    libraries.append(
                        {
                            "name": name,
                            "filename": filename,
                            "path": filepath,
                            "is_user": True,
                            "can_delete": True,
                            "material": mat,
                            "density": dens,
                        }
                    )

        # 2. Discover stock libraries
        if os.path.exists(self.stock_dir):
            for filename in sorted(os.listdir(self.stock_dir)):
                if filename.endswith(".json"):
                    filepath = os.path.join(self.stock_dir, filename)
                    name, mat, dens = self._extract_library_metadata(filename, filepath)
                    if name.lower() not in seen_names:
                        libraries.append(
                            {
                                "name": name,
                                "filename": filename,
                                "path": filepath,
                                "is_user": False,
                                "can_delete": False,
                                "material": mat,
                                "density": dens,
                            }
                        )

        return sorted(libraries, key=lambda x: (not x["is_user"], x["name"].lower()))

    def _extract_library_metadata(self, filename, filepath):
        """Extracts display name, material, and density from file."""
        name = None
        material = None
        density = None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "_metadata" in data:
                    meta = data["_metadata"]
                    name = meta.get("name")
                    material = meta.get("material")
                    raw_dens = meta.get("density")
                    if raw_dens is not None:
                        try:
                            density = float(raw_dens)
                        except (ValueError, TypeError):
                            density = None
        except Exception:
            pass

        if not name:
            base = os.path.splitext(filename)[0]
            parts = re.split(r"[_\-]+", base)
            name = " ".join(part.capitalize() for part in parts if part) or base.capitalize()

        # If material is already defined in metadata, lookup its density from STANDARD_DENSITIES first!
        if material:
            if density is None and material in STANDARD_DENSITIES:
                density = float(STANDARD_DENSITIES[material])

        # If still missing, infer from library name
        if not material or density is None:
            lname = name.lower()
            if "alumin" in lname:
                material = material or "Aluminium"
                density = density if density is not None else 2.70
            elif "wood" in lname or "mader" in lname:
                material = material or "Wood (Soft)"
                density = density if density is not None else 0.55
            else:
                material = material or "Steel"
                density = density if density is not None else 7.85

        try:
            density = float(density)
        except (ValueError, TypeError):
            density = 7.85

        return name, str(material), float(density)

    def _extract_library_name(self, filename, filepath):
        """Extracts display name from file, formatting appropriately."""
        name, _, _ = self._extract_library_metadata(filename, filepath)
        return name

    def get_library_material_info(self, name):
        """
        Returns (material_name, density_g_cm3) for a given library name.
        """
        target_name = name.strip().lower()

        # Check discovered libraries first to ensure 100% consistency with list_libraries
        for lib in self.list_libraries():
            if lib["name"].strip().lower() == target_name:
                return lib["material"], lib["density"]

        # Fallback to direct library load
        try:
            data = self.get_library(name)
            meta = data.get("_metadata", {})
            mat = meta.get("material")
            dens = meta.get("density")
            if mat:
                if dens is None and mat in STANDARD_DENSITIES:
                    dens = STANDARD_DENSITIES[mat]
                if dens is not None:
                    return str(mat), float(dens)
        except Exception:
            pass

        lname = name.lower()
        if "alumin" in lname:
            return "Aluminium", 2.70
        elif "wood" in lname or "mader" in lname:
            return "Wood (Soft)", 0.55
        return "Steel", 7.85

    def get_library(self, name):
        """
        Loads the catalog JSON for the specified library name.
        Prioritizes exact display-name match over filename slug aliases.
        """
        target_name = name.strip().lower()

        # Pass 1: exact display-name match (user first, then stock, matching list_libraries precedence)
        candidates = []
        for is_user, directory in [(True, self.user_dir), (False, self.stock_dir)]:
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

    def save_user_library(self, name, data, overwrite=True, material=None, density=None):
        """
        Saves or updates a user library JSON in user_dir.
        If overwrite is False, raises FileExistsError if target file already exists.
        Enforces S4 immutability: once created, existing user library material cannot be mutated.
        """
        os.makedirs(self.user_dir, exist_ok=True)
        file_slug = sanitize_library_name(name)
        filename = f"{file_slug}.json"
        filepath = os.path.join(self.user_dir, filename)

        if not overwrite and os.path.exists(filepath):
            raise FileExistsError(f"A library file '{filename}' already exists.")

        # Check collision with bundled stock libraries to protect reserved identities
        if os.path.exists(self.stock_dir):
            for fname in os.listdir(self.stock_dir):
                if fname.endswith(".json"):
                    fpath = os.path.join(self.stock_dir, fname)
                    s_name = self._extract_library_name(fname, fpath)
                    if s_name.lower() == name.strip().lower():
                        raise ValueError(f"Cannot create user library with reserved system library name '{s_name}'.")

        # S4 Immutability: If file already exists, prevent changing its material
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                if isinstance(existing_data, dict) and "_metadata" in existing_data:
                    existing_meta = existing_data["_metadata"]
                    existing_mat = existing_meta.get("material")
                    existing_dens = existing_meta.get("density")

                    if not existing_mat:
                        existing_mat, inferred_dens = self.get_library_material_info(name)
                        if existing_dens is None:
                            existing_dens = inferred_dens

                    requested_mat = material or (
                        data.get("_metadata", {}).get("material")
                        if isinstance(data, dict)
                        else None
                    )
                    if existing_mat and requested_mat and requested_mat != existing_mat:
                        raise ValueError(
                            f"Library material is immutable. Cannot change material of '{name}' from '{existing_mat}' to '{requested_mat}'. Use duplicate_library instead."
                        )
                    if existing_mat and material is None:
                        material = existing_mat
                    if existing_dens is not None and density is None:
                        density = existing_dens
            except ValueError:
                raise
            except Exception:
                pass

        # Ensure _metadata preserves exact user display name and material
        if isinstance(data, dict):
            if "_metadata" not in data:
                data["_metadata"] = {}
            data["_metadata"]["name"] = name
            if material is not None:
                data["_metadata"]["material"] = str(material)
                if density is not None:
                    data["_metadata"]["density"] = float(density)
                elif material in STANDARD_DENSITIES:
                    data["_metadata"]["density"] = float(STANDARD_DENSITIES[material])
            elif "material" not in data["_metadata"]:
                # Default fallback inferred from name
                inferred_mat, inferred_dens = self.get_library_material_info(name)
                data["_metadata"]["material"] = inferred_mat
                data["_metadata"]["density"] = inferred_dens

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

    def duplicate_library(
        self,
        source_name,
        target_name,
        overwrite=False,
        target_material=None,
        target_density=None,
        recalculate_weights=False,
    ):
        """
        Clones an existing library (stock or user) into a new user library.
        If overwrite is False, raises FileExistsError if target already exists.
        If target_material is provided, assigns it to the clone.
        If recalculate_weights is True, recalculates theoretical weights with target_density.
        """
        source_data = self.get_library(source_name)
        # Deep copy via serialization
        cloned_data = json.loads(json.dumps(source_data))

        # Determine target material and density
        if target_material is None:
            source_mat, source_dens = self.get_library_material_info(source_name)
            target_material = source_mat
            target_density = source_dens if target_density is None else float(target_density)
        else:
            if target_density is None:
                target_density = STANDARD_DENSITIES.get(target_material, 7.85)
            else:
                target_density = float(target_density)

        # Update metadata
        if "_metadata" not in cloned_data:
            cloned_data["_metadata"] = {}
        cloned_data["_metadata"]["name"] = target_name
        cloned_data["_metadata"]["cloned_from"] = source_name
        cloned_data["_metadata"]["material"] = target_material
        cloned_data["_metadata"]["density"] = float(target_density)

        if recalculate_weights:
            unrecalculated = []
            for fam_name, fam_data in cloned_data.items():
                if fam_name.startswith("_") or not isinstance(fam_data, dict):
                    continue
                sizes = fam_data.get("sizes", {})
                for size_key, size_props in sizes.items():
                    if not isinstance(size_props, dict):
                        continue
                    try:
                        h = float(size_props.get("Height", 0))
                        w = float(size_props.get("Width", 0))
                        t = float(size_props.get("Thickness", 0))
                        tf = (
                            float(size_props.get("Flange Thickness", 0))
                            if "Flange Thickness" in size_props
                            else None
                        )
                        canonical = get_canonical_family(fam_name, fam_data)
                        new_weight = calculate_linear_weight(
                            family=canonical,
                            width=w,
                            height=h,
                            thickness=t,
                            density_g_cm3=target_density,
                            flange_thickness=tf,
                        )
                        size_props["Weight"] = str(new_weight)
                    except Exception as err:
                        unrecalculated.append(f"{fam_name}/{size_key}")

            if unrecalculated:
                raise ValueError(
                    f"Cannot recalculate weights for unsupported complex families: {', '.join(unrecalculated[:3])}. Duplicate without weight recalculation to preserve nominal weights."
                )

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
