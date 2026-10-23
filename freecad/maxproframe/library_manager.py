import copy
import json
import math
import os
import re
import shutil
import tempfile

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
    "C",
    "HEA",
    "HEB",
    "HEM",
    "IPE",
    "IPN",
    "UPE",
    "UPN",
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
        "C",
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


def calculate_linear_weight(
    family,
    width,
    height,
    thickness,
    density_g_cm3=7.85,
    flange_thickness=None,
    lip_length=None,
    radius=None,
    make_fillet=False,
):
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
    elif family in ("C",):
        from freecad.maxproframe.c_profile import calculate_c_area
        area_mm2 = calculate_c_area(
            height=h,
            width=w,
            thickness=t,
            lip_length=lip_length,
            radius=radius,
            make_fillet=make_fillet,
        )
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
    Returns the user application data directory for MaxProFrame custom profiles,
    falling back to legacy FrameForge directories if they exist.
    """
    env_dir = os.environ.get("MAXPROFRAME_USER_PROFILES_DIR") or os.environ.get("FRAMEFORGE_USER_PROFILES_DIR")
    if env_dir:
        return env_dir

    try:
        import FreeCAD

        app_data = FreeCAD.getUserAppDataDir()
        max_path = os.path.join(app_data, "MaxProFrame", "profiles")
        if os.path.isdir(max_path):
            return max_path
        legacy_path = os.path.join(app_data, "FrameForge", "profiles")
        if os.path.isdir(legacy_path):
            return legacy_path
        return max_path
    except Exception:
        # Fallback for CLI or headless testing outside FreeCAD
        xdg_data = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        max_path = os.path.join(xdg_data, "FreeCAD", "MaxProFrame", "profiles")
        if os.path.isdir(max_path):
            return max_path
        legacy_path = os.path.join(xdg_data, "FreeCAD", "FrameForge", "profiles")
        if os.path.isdir(legacy_path):
            return legacy_path
        return max_path


class LibraryManager:
    """
    Central manager for FrameForge profile libraries.
    Discovers stock (bundled) and user-defined libraries, handles persistence,
    validation, cloning, and formatting for FreeCAD UI tools.
    """

    def __init__(self, user_dir=None, stock_dir=None, registry_path=None):
        self.stock_dir = stock_dir or get_default_stock_profiles_dir()
        self.user_dir = user_dir or get_default_user_profiles_dir()
        self.registry_path = registry_path or os.path.join(self.user_dir, ".registry", "folders.json")

    @staticmethod
    def _validate_not_symlink_escape(canonical_root, file_path):
        """
        Validates that file_path (or its symlink target) does not escape canonical_root.
        Raises ValueError if file_path is a symlink escaping canonical_root.
        """
        if os.path.islink(file_path):
            target = os.path.realpath(file_path)
            try:
                common = os.path.commonpath([canonical_root, target])
            except ValueError:
                common = None
            if common != canonical_root:
                raise ValueError(
                    f"Manifest '{file_path}' is a symlink escaping folder root '{canonical_root}'."
                )

    @staticmethod
    def _validate_folder_catalog_data(data, material=None, density=None, require_name=True):
        """
        Validates catalog data, material, and density for folder libraries.
        Ensures dictionary root, valid family dictionaries, string material,
        and finite positive density.
        """
        if not isinstance(data, dict):
            raise ValueError(f"Catalog data must be a dictionary, got {type(data).__name__}.")

        # Validate families (all non-underscore keys)
        for k, v in data.items():
            if not k.startswith("_"):
                if not isinstance(v, dict):
                    raise ValueError(f"Family '{k}' must be a dictionary, got {type(v).__name__}.")

        # Validate _metadata if present
        meta = data.get("_metadata")
        if meta is not None:
            if not isinstance(meta, dict):
                raise ValueError("'_metadata' must be a dictionary.")
            if require_name:
                name = meta.get("name")
                if not name or not isinstance(name, str) or not name.strip():
                    raise ValueError("Manifest '_metadata.name' display name must be a non-empty string.")
            elif "name" in meta:
                name = meta.get("name")
                if not isinstance(name, str) or not name.strip():
                    raise ValueError("Manifest '_metadata.name' display name must be a non-empty string.")

            meta_mat = meta.get("material")
            if meta_mat is not None:
                if not isinstance(meta_mat, str) or not meta_mat.strip():
                    raise ValueError("Manifest '_metadata.material' must be a non-empty string.")

            meta_dens = meta.get("density")
            if meta_dens is not None:
                try:
                    d_val = float(meta_dens)
                except (TypeError, ValueError) as err:
                    raise ValueError(f"Manifest density must be a valid number: {err}")
                if not math.isfinite(d_val) or d_val <= 0:
                    raise ValueError(f"Manifest density must be a finite positive number, got {meta_dens}.")

        # Validate explicit material argument if provided
        if material is not None:
            if not isinstance(material, str) or not material.strip():
                raise ValueError("Material must be a non-empty string.")

        # Validate explicit density argument if provided
        if density is not None:
            try:
                d_val = float(density)
            except (TypeError, ValueError) as err:
                raise ValueError(f"Density must be a valid number: {err}")
            if not math.isfinite(d_val) or d_val <= 0:
                raise ValueError(f"Density must be a finite positive number, got {density}.")

    def _load_registry(self):
        """
        Loads list of canonical registered folder paths from self.registry_path.
        Fails closed on permission errors, decode errors, or schema corruption.
        Returns empty list only when self.registry_path does not exist.
        """
        if not os.path.exists(self.registry_path):
            return []
        try:
            with open(self.registry_path, "r", encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            raise

        try:
            data = json.loads(content)
        except json.JSONDecodeError as err:
            raise ValueError(f"Corrupt registry JSON at '{self.registry_path}': {err}")

        if isinstance(data, dict):
            raw_folders = data.get("folders")
            if not isinstance(raw_folders, list):
                raise ValueError(
                    f"Corrupt registry schema at '{self.registry_path}': 'folders' must be a list."
                )
        elif isinstance(data, list):
            raw_folders = data
        else:
            raise ValueError(
                f"Corrupt registry schema at '{self.registry_path}': root must be a dict or list."
            )

        canonical_folders = []
        seen = set()
        for p in raw_folders:
            if not isinstance(p, str):
                raise ValueError(
                    f"Corrupt registry schema at '{self.registry_path}': folder entry must be a string."
                )
            p_strip = p.strip()
            if p_strip:
                canon = os.path.realpath(p_strip)
                if canon not in seen:
                    seen.add(canon)
                    canonical_folders.append(canon)
        return canonical_folders

    def _save_registry(self, folder_paths):
        """
        Atomically saves the list of canonical registered folder paths using
        an unpredictable temporary file in the registry directory.
        """
        reg_dir = os.path.dirname(self.registry_path)
        if reg_dir:
            os.makedirs(reg_dir, exist_ok=True)
        seen = set()
        unique_paths = []
        for p in folder_paths:
            if isinstance(p, str) and p.strip():
                canon = os.path.realpath(p.strip())
                if canon not in seen:
                    seen.add(canon)
                    unique_paths.append(canon)

        data = {"version": 1, "folders": unique_paths}
        fd, temp_path = tempfile.mkstemp(prefix="tmp_reg_", dir=reg_dir or ".")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.registry_path)
        except Exception:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise

    def _get_registered_folder(self, name_or_path):
        """
        Finds registered canonical folder path matching display name or path.
        Returns canonical_path or None.
        """
        folders = self._load_registry()
        if not folders:
            return None

        # 1. Direct path match
        canon_input = os.path.realpath(os.path.abspath(name_or_path))
        if canon_input in folders:
            return canon_input

        # 2. Display name match
        target_name = name_or_path.strip().lower()
        for fpath in folders:
            if os.path.isdir(fpath):
                mpath = os.path.join(fpath, "library.json")
                if os.path.isfile(mpath):
                    try:
                        self._validate_not_symlink_escape(fpath, mpath)
                        with open(mpath, "r", encoding="utf-8") as f:
                            d = json.load(f)
                            if isinstance(d, dict) and "_metadata" in d:
                                name = d["_metadata"].get("name")
                                if isinstance(name, str) and name.strip().lower() == target_name:
                                    return fpath
                    except Exception:
                        continue
        return None

    def get_folder_library_path(self, name_or_path):
        """Finds registered canonical folder path matching display name or path.

        Returns None if not registered as a folder library.
        """
        return self._get_registered_folder(name_or_path)

    def _check_name_collision(self, name, current_canonical_root=None):
        """
        Checks whether name collides with existing stock, user, or registered folder libraries.
        """
        target_name = name.strip().lower()

        # Check stock libraries
        if os.path.exists(self.stock_dir):
            for fname in os.listdir(self.stock_dir):
                if fname.endswith(".json"):
                    fpath = os.path.join(self.stock_dir, fname)
                    s_name = self._extract_library_name(fname, fpath)
                    if s_name.lower() == target_name:
                        raise ValueError(f"Library name '{name}' collides with an existing library.")

        # Check legacy user libraries
        if os.path.exists(self.user_dir):
            for fname in os.listdir(self.user_dir):
                if fname.endswith(".json"):
                    fpath = os.path.join(self.user_dir, fname)
                    u_name = self._extract_library_name(fname, fpath)
                    if u_name.lower() == target_name:
                        raise ValueError(f"Library name '{name}' collides with an existing library.")

        # Check registered folder libraries
        folders = self._load_registry()
        for fpath in folders:
            if current_canonical_root and fpath == current_canonical_root:
                continue
            if os.path.isdir(fpath):
                mpath = os.path.join(fpath, "library.json")
                if os.path.isfile(mpath):
                    try:
                        self._validate_not_symlink_escape(fpath, mpath)
                        with open(mpath, "r", encoding="utf-8") as f:
                            d = json.load(f)
                            if isinstance(d, dict) and "_metadata" in d:
                                reg_name = d["_metadata"].get("name")
                                if isinstance(reg_name, str) and reg_name.strip().lower() == target_name:
                                    raise ValueError(f"Library name '{name}' collides with an existing library.")
                    except ValueError:
                        raise
                    except Exception:
                        pass

    def list_libraries(self):
        """
        Discovers all available libraries across stock, user, and registered folder directories.
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

        # 2. Discover registered folder libraries
        folders = self._load_registry()
        for fpath in folders:
            if not os.path.isdir(fpath):
                continue
            mpath = os.path.join(fpath, "library.json")
            if not os.path.isfile(mpath):
                continue
            try:
                self._validate_not_symlink_escape(fpath, mpath)
                name, mat, dens = self._extract_library_metadata("library.json", mpath)
                if name.lower() not in seen_names:
                    seen_names.add(name.lower())
                    libraries.append(
                        {
                            "name": name,
                            "filename": "library.json",
                            "path": mpath,
                            "is_user": True,
                            "can_delete": False,
                            "is_folder": True,
                            "folder_path": fpath,
                            "can_unregister": True,
                            "material": mat,
                            "density": dens,
                        }
                    )
            except Exception:
                continue

        # 3. Discover stock libraries
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
        if material and isinstance(material, str):
            if density is None and material in STANDARD_DENSITIES:
                density = float(STANDARD_DENSITIES[material])

        # If still missing, infer from library name
        if not material or not isinstance(material, str) or density is None:
            lname = name.lower()
            if "alumin" in lname:
                material = material if isinstance(material, str) and material else "Aluminium"
                density = density if density is not None else 2.70
            elif "wood" in lname or "mader" in lname:
                material = material if isinstance(material, str) and material else "Wood (Soft)"
                density = density if density is not None else 0.55
            else:
                material = material if isinstance(material, str) and material else "Steel"
                density = density if density is not None else 7.85

        try:
            density = float(density)
            if not math.isfinite(density) or density <= 0:
                density = 7.85
        except (ValueError, TypeError):
            density = 7.85

        return name, str(material) if isinstance(material, str) and material else "Steel", float(density)

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
        # Pass 0: registered folder library match
        folder_match = self._get_registered_folder(name)
        if folder_match:
            mpath = os.path.join(folder_match, "library.json")
            self._validate_not_symlink_escape(folder_match, mpath)
            with open(mpath, "r", encoding="utf-8") as f:
                return json.load(f)

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

    def create_folder_library(self, folder_path, name, material=None, density=None, data=None):
        """
        Creates a new folder library with an initialized library.json manifest and registers it.
        Refuses to overwrite an existing manifest or populate an unrelated non-empty directory.
        Fails atomically without leaking unmanaged manifests on registry error.
        """
        # Preflight registry load and directory access to fail closed before any file creation
        folders = self._load_registry()
        reg_dir = os.path.dirname(self.registry_path)
        if reg_dir:
            os.makedirs(reg_dir, exist_ok=True)

        if not name or not isinstance(name, str) or not name.strip():
            raise ValueError("A valid non-empty library name is required.")
        display_name = name.strip()

        # Validate supplied data and arguments before any file operations
        catalog_input = data if data is not None else {}
        self._validate_folder_catalog_data(
            catalog_input, material=material, density=density, require_name=False
        )

        canonical_root = os.path.realpath(os.path.abspath(folder_path))
        manifest_path = os.path.join(canonical_root, "library.json")

        # Symlink escape check
        self._validate_not_symlink_escape(canonical_root, manifest_path)

        if os.path.islink(manifest_path) or os.path.exists(manifest_path):
            raise FileExistsError(f"A library manifest already exists in '{canonical_root}'.")

        if os.path.exists(canonical_root):
            if not os.path.isdir(canonical_root):
                raise ValueError(f"Path '{canonical_root}' is not a directory.")
            existing_entries = os.listdir(canonical_root)
            if existing_entries:
                raise ValueError(
                    f"Directory '{canonical_root}' is not empty. Cannot create library in folder with existing content."
                )

        # Check name collision against stock, legacy user, and folder libraries
        self._check_name_collision(display_name, current_canonical_root=canonical_root)

        # Material and density resolution
        if material is None:
            material = "Steel"
        if density is None:
            density = STANDARD_DENSITIES.get(material, 7.85)
        else:
            density = float(density)

        # Deep copy data to avoid mutating caller's input
        manifest_data = copy.deepcopy(catalog_input)
        if "_metadata" not in manifest_data or not isinstance(manifest_data["_metadata"], dict):
            manifest_data["_metadata"] = {}
        manifest_data["_metadata"]["name"] = display_name
        manifest_data["_metadata"]["material"] = str(material)
        manifest_data["_metadata"]["density"] = float(density)
        manifest_data["_metadata"]["is_folder"] = True

        os.makedirs(canonical_root, exist_ok=True)

        # Write manifest using unpredictable mkstemp in canonical_root
        fd, temp_path = tempfile.mkstemp(prefix="tmp_manifest_", dir=canonical_root)
        created_manifest = False
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(manifest_data, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, manifest_path)
            created_manifest = True

            if canonical_root not in folders:
                folders.append(canonical_root)
                self._save_registry(folders)
        except Exception:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            if created_manifest and os.path.isfile(manifest_path):
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        check_data = json.load(f)
                    if check_data.get("_metadata", {}).get("name") == display_name:
                        os.remove(manifest_path)
                except Exception:
                    pass
            raise

        return manifest_path

    def register_folder_library(self, folder_path):
        """
        Registers an existing folder library in the local registry.
        Validates manifest shape, metadata, and root confinement.
        Never modifies or writes to the registered folder.
        Canonical path registration is idempotent.
        """
        # Preflight registry load to fail closed if registry is damaged
        folders = self._load_registry()

        if not os.path.exists(folder_path):
            raise FileNotFoundError(f"Folder '{folder_path}' does not exist.")
        if not os.path.isdir(folder_path):
            raise ValueError(f"Path '{folder_path}' is not a directory.")

        canonical_root = os.path.realpath(os.path.abspath(folder_path))
        manifest_path = os.path.join(canonical_root, "library.json")

        self._validate_not_symlink_escape(canonical_root, manifest_path)

        if not os.path.isfile(manifest_path):
            raise FileNotFoundError(f"Folder '{canonical_root}' does not contain 'library.json'.")

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as err:
            raise ValueError(f"Invalid JSON in manifest '{manifest_path}': {err}")
        except Exception as err:
            raise ValueError(f"Cannot read manifest '{manifest_path}': {err}")

        # Validate entire catalog data shape, families, and metadata
        self._validate_folder_catalog_data(data, require_name=True)

        meta = data["_metadata"]
        display_name = meta["name"].strip()

        # Idempotent registration: update registry ONLY if not already present
        if canonical_root not in folders:
            self._check_name_collision(display_name, current_canonical_root=canonical_root)
            folders.append(canonical_root)
            self._save_registry(folders)

        _lib_name, mat_name, dens_val = self._extract_library_metadata("library.json", manifest_path)
        return {
            "name": display_name,
            "path": manifest_path,
            "folder_path": canonical_root,
            "is_user": True,
            "can_delete": False,
            "is_folder": True,
            "can_unregister": True,
            "material": mat_name,
            "density": dens_val,
        }

    register_existing = register_folder_library

    def unregister_folder_library(self, folder_path_or_name):
        """
        Removes folder library from local registry only.
        Keeps folder contents and manifest intact.
        Fails closed if registry is damaged.
        """
        # Load registry first to validate registry integrity; fails closed if corrupt/inaccessible
        folders = self._load_registry()

        canonical_path = self._get_registered_folder(folder_path_or_name)
        if not canonical_path or canonical_path not in folders:
            raise FileNotFoundError(f"Folder library '{folder_path_or_name}' is not registered.")

        updated = [p for p in folders if p != canonical_path]
        self._save_registry(updated)
        return True

    def save_folder_library(self, folder_path_or_name, data, overwrite=True, material=None, density=None):
        """
        Saves or updates catalog data in a registered folder library.
        Preserves material immutability, prevents name collisions with other libraries,
        and uses unpredictable temporary files for atomic replacement.
        """
        # Preflight registry load to ensure registry is healthy
        self._load_registry()

        folder_match = self._get_registered_folder(folder_path_or_name)
        if not folder_match:
            raise FileNotFoundError(f"Folder library '{folder_path_or_name}' is not registered.")

        manifest_path = os.path.join(folder_match, "library.json")
        self._validate_not_symlink_escape(folder_match, manifest_path)

        if not overwrite and os.path.exists(manifest_path):
            raise FileExistsError(f"A library manifest already exists in '{folder_match}'.")

        # Validate input data, material, and density before any mutation or writes
        self._validate_folder_catalog_data(
            data, material=material, density=density, require_name=False
        )

        # Material immutability check
        existing_name = None
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                if isinstance(existing_data, dict) and "_metadata" in existing_data:
                    existing_meta = existing_data["_metadata"]
                    existing_name = existing_meta.get("name")
                    existing_mat = existing_meta.get("material")
                    existing_dens = existing_meta.get("density")

                    lib_name = existing_name or os.path.basename(folder_match)
                    if not existing_mat:
                        existing_mat, inferred_dens = self.get_library_material_info(lib_name)
                        if existing_dens is None:
                            existing_dens = inferred_dens

                    requested_mat = material or (
                        data.get("_metadata", {}).get("material")
                        if isinstance(data, dict)
                        else None
                    )
                    if existing_mat and requested_mat and requested_mat != existing_mat:
                        raise ValueError(
                            f"Library material is immutable. Cannot change material of '{lib_name}' from '{existing_mat}' to '{requested_mat}'. Use duplicate_library instead."
                        )
                    if existing_mat and material is None:
                        material = existing_mat
                    if existing_dens is not None and density is None:
                        density = existing_dens
            except ValueError:
                raise
            except Exception:
                pass

        # Determine proposed display name
        manifest_data = copy.deepcopy(data)
        if "_metadata" not in manifest_data or not isinstance(manifest_data["_metadata"], dict):
            manifest_data["_metadata"] = {}

        proposed_name = manifest_data["_metadata"].get("name")
        if not proposed_name or not isinstance(proposed_name, str) or not proposed_name.strip():
            proposed_name = existing_name or os.path.basename(folder_match)
        proposed_name = proposed_name.strip()

        # B5: Validate proposed name collision across all namespaces excluding only current folder root
        self._check_name_collision(proposed_name, current_canonical_root=folder_match)

        manifest_data["_metadata"]["name"] = proposed_name
        manifest_data["_metadata"]["is_folder"] = True

        if material is not None:
            manifest_data["_metadata"]["material"] = str(material)
            if density is not None:
                manifest_data["_metadata"]["density"] = float(density)
            elif material in STANDARD_DENSITIES:
                manifest_data["_metadata"]["density"] = float(STANDARD_DENSITIES[material])
        elif "material" not in manifest_data["_metadata"]:
            inferred_mat, inferred_dens = self.get_library_material_info(proposed_name)
            manifest_data["_metadata"]["material"] = inferred_mat
            manifest_data["_metadata"]["density"] = inferred_dens

        # Write manifest using unpredictable mkstemp in folder_match
        fd, temp_path = tempfile.mkstemp(prefix="tmp_manifest_", dir=folder_match)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(manifest_data, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, manifest_path)
        except Exception:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise

        return manifest_path

    def save_user_library(self, name, data, overwrite=True, material=None, density=None):
        """
        Saves or updates a user library JSON in user_dir, or routes to registered folder library
        if name matches a registered folder library.
        If overwrite is False, raises FileExistsError if target file already exists.
        Enforces S4 immutability: once created, existing user library material cannot be mutated.
        """
        # If name matches a registered folder library, route save to that folder
        folder_match = self._get_registered_folder(name)
        if folder_match:
            return self.save_folder_library(
                folder_match,
                data,
                overwrite=overwrite,
                material=material,
                density=density,
            )

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

        # Check collision with registered folder libraries
        folders = self._load_registry()
        for fpath in folders:
            if os.path.isdir(fpath):
                mpath = os.path.join(fpath, "library.json")
                if os.path.isfile(mpath):
                    try:
                        self._validate_not_symlink_escape(fpath, mpath)
                        with open(mpath, "r", encoding="utf-8") as f:
                            d = json.load(f)
                            if isinstance(d, dict) and "_metadata" in d:
                                reg_name = d["_metadata"].get("name")
                                if isinstance(reg_name, str) and reg_name.strip().lower() == name.strip().lower():
                                    raise ValueError(
                                        f"Cannot create user library with name '{name}' which collides with registered folder library."
                                    )
                    except ValueError:
                        raise
                    except Exception:
                        pass

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
        Deletes a user-defined library. Raises ValueError if library is stock or a registered folder library.
        """
        folder_match = self._get_registered_folder(name)
        if folder_match:
            raise ValueError(
                f"'{name}' is a registered folder library and cannot be deleted via delete_user_library. Use unregister_folder_library instead."
            )

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

    def get_default_library_folder(self, name):
        """Return a dedicated safe child destination without creating it."""
        return os.path.join(os.path.abspath(self.user_dir), sanitize_library_name(name))

    def duplicate_library(
        self,
        source_name,
        target_name,
        overwrite=False,
        target_material=None,
        target_density=None,
        recalculate_weights=False,
        target_folder_path=None,
    ):
        """
        Clone stock, user, or folder libraries into a dedicated registered folder.
        Never overwrite existing destination contents, even when overwrite is True.
        Optional target material and density control requested weight recalculation.
        Only declared, confined assets are copied; omitted destination uses user_dir.
        """
        source_folder = self._get_registered_folder(source_name)
        if source_folder is None:
            libraries = self.list_libraries()
            source = next(
                (lib for lib in libraries if lib["name"].lower() == source_name.strip().lower()),
                None,
            )
            if source is None:
                source = next(
                    (lib for lib in libraries
                     if os.path.splitext(lib["filename"])[0].lower() == source_name.strip().lower()),
                    None,
                )
            if source is None:
                raise FileNotFoundError(f"Library '{source_name}' not found.")
            source_root = os.path.dirname(source["path"])
        else:
            source_root = source_folder
        target_folder_path = target_folder_path or self.get_default_library_folder(target_name)

        if target_folder_path:
            canon_src = os.path.realpath(os.path.abspath(source_root))
            canon_dest = os.path.realpath(os.path.abspath(target_folder_path))

            if canon_src == canon_dest:
                raise ValueError("Source and target folder library paths cannot be identical.")

            src_with_sep = canon_src if canon_src.endswith(os.sep) else canon_src + os.sep
            dest_with_sep = canon_dest if canon_dest.endswith(os.sep) else canon_dest + os.sep
            if source_folder and (canon_dest.startswith(src_with_sep) or canon_src.startswith(dest_with_sep)):
                raise ValueError("Nested source and target directories are not allowed.")

            dest_preexisted = False
            if os.path.exists(canon_dest):
                if not os.path.isdir(canon_dest):
                    raise FileExistsError(f"Target path '{target_folder_path}' is a file.")
                if os.listdir(canon_dest):
                    raise FileExistsError(f"Target directory '{target_folder_path}' is not empty.")
                dest_preexisted = True

            # Collision checks before writes
            self._check_name_collision(target_name)
            if self._get_registered_folder(canon_dest):
                raise FileExistsError(f"Target folder path '{target_folder_path}' is already registered.")

            src_manifest_path = (
                os.path.join(canon_src, "library.json") if source_folder else source["path"]
            )
            if not os.path.isfile(src_manifest_path):
                raise FileNotFoundError(f"Source folder library manifest '{src_manifest_path}' not found.")

            self._validate_not_symlink_escape(canon_src, src_manifest_path)
            try:
                with open(src_manifest_path, "r", encoding="utf-8") as f:
                    source_data = json.load(f)
            except Exception as err:
                raise ValueError(f"Cannot read source manifest '{src_manifest_path}': {err}")

            cloned_data = copy.deepcopy(source_data)
            self._validate_folder_catalog_data(
                cloned_data, material=target_material, density=target_density, require_name=False
            )

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

            if "_metadata" not in cloned_data:
                cloned_data["_metadata"] = {}
            cloned_data["_metadata"]["name"] = target_name
            cloned_data["_metadata"]["cloned_from"] = source_name
            cloned_data["_metadata"]["material"] = target_material
            cloned_data["_metadata"]["density"] = float(target_density)
            cloned_data["_metadata"]["is_folder"] = True

            # Validate all declared assets across all families BEFORE writing
            from freecad.maxproframe.section_library import (
                recalculate_custom_profile_weight,
                resolve_and_validate_asset_path,
            )

            declared_assets = {}  # rel_path -> src_canonical_file_path
            for fam_name, fam_data in cloned_data.items():
                if fam_name.startswith("_") or not isinstance(fam_data, dict):
                    continue
                sizes = fam_data.get("sizes", {})
                if not isinstance(sizes, dict):
                    continue
                for size_key, size_props in sizes.items():
                    if not isinstance(size_props, dict):
                        continue
                    asset_rel = size_props.get("asset_path")
                    if asset_rel:
                        canon_asset = resolve_and_validate_asset_path(canon_src, asset_rel)
                        if not os.path.isfile(canon_asset):
                            raise FileNotFoundError(
                                f"Referenced asset '{asset_rel}' does not exist on disk in '{canon_src}'."
                            )
                        declared_assets[asset_rel] = canon_asset

            # Staged creation and owned rollback tracking
            created_dest_root = False
            created_files = []
            created_dirs = []

            if not dest_preexisted:
                os.makedirs(canon_dest, exist_ok=True)
                created_dest_root = True

            def rollback():
                for fpath in reversed(created_files):
                    try:
                        if os.path.isfile(fpath) or os.path.islink(fpath):
                            os.remove(fpath)
                    except OSError:
                        pass
                for dpath in sorted(set(created_dirs), key=lambda p: len(os.path.abspath(p)), reverse=True):
                    try:
                        if os.path.isdir(dpath) and not os.listdir(dpath):
                            os.rmdir(dpath)
                    except OSError:
                        pass
                if created_dest_root:
                    try:
                        if os.path.isdir(canon_dest) and not os.listdir(canon_dest):
                            os.rmdir(canon_dest)
                    except OSError:
                        pass

            canon_dest_sections = os.path.realpath(os.path.join(canon_dest, "sections"))
            try:
                # Copy declared assets exclusively (materializing internal symlinks as regular files)
                copied_targets = set()
                for rel_path, src_canonical_path in declared_assets.items():
                    target_asset_path = os.path.join(canon_dest, os.path.normpath(rel_path))
                    target_asset_real = os.path.realpath(target_asset_path)
                    try:
                        common_target = os.path.commonpath([canon_dest_sections, target_asset_real])
                    except ValueError:
                        common_target = None
                    if common_target != canon_dest_sections:
                        raise ValueError(
                            f"Target asset path '{target_asset_path}' escapes destination sections directory."
                        )

                    if target_asset_path in copied_targets:
                        continue
                    target_dir = os.path.dirname(target_asset_path)
                    if not os.path.exists(target_dir):
                        os.makedirs(target_dir, exist_ok=True)
                        cur = target_dir
                        while cur != canon_dest and cur not in created_dirs:
                            created_dirs.append(cur)
                            cur = os.path.dirname(cur)

                    created_files.append(target_asset_path)
                    copied_targets.add(target_asset_path)
                    shutil.copyfile(src_canonical_path, target_asset_path)

                # Weight recalculation if requested
                if recalculate_weights:
                    unrecalculated = []
                    for fam_name, fam_data in cloned_data.items():
                        if fam_name.startswith("_") or not isinstance(fam_data, dict):
                            continue
                        sizes = fam_data.get("sizes", {})
                        if not isinstance(sizes, dict):
                            continue
                        canonical = get_canonical_family(fam_name, fam_data)

                        if canonical == "Custom Profile":
                            for size_key, size_props in sizes.items():
                                if not isinstance(size_props, dict):
                                    continue
                                asset_rel = size_props.get("asset_path")
                                if not asset_rel:
                                    continue
                                dest_asset_path = os.path.join(canon_dest, os.path.normpath(asset_rel))
                                obj_name = size_props.get("object_name")
                                try:
                                    new_weight = recalculate_custom_profile_weight(
                                        dest_asset_path, obj_name, target_density
                                    )
                                    size_props["Weight"] = f"{new_weight:.2f}"
                                except Exception as err:
                                    unrecalculated.append(f"{fam_name}/{size_key}")
                        else:
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
                                    if canonical == "C":
                                        lip = (
                                            float(size_props.get("Lip Length", 0))
                                            if "Lip Length" in size_props
                                            else None
                                        )
                                        r1 = (
                                            float(size_props.get("Radius1", 0))
                                            if "Radius1" in size_props
                                            else None
                                        )
                                        make_fillet = bool(fam_data.get("fillet", False))
                                        new_weight = calculate_linear_weight(
                                            family=canonical,
                                            width=w,
                                            height=h,
                                            thickness=t,
                                            density_g_cm3=target_density,
                                            flange_thickness=tf,
                                            lip_length=lip,
                                            radius=r1,
                                            make_fillet=make_fillet,
                                        )
                                    else:
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
                        prefix = (
                            "Cannot recalculate weights for"
                            if source_folder else
                            "Cannot recalculate weights for unsupported complex families"
                        )
                        raise ValueError(
                            f"{prefix}: {', '.join(unrecalculated[:3])}. Duplicate without weight recalculation to preserve nominal weights."
                        )

                # Write manifest atomically in destination folder
                manifest_path = os.path.join(canon_dest, "library.json")
                temp_fd, temp_path = tempfile.mkstemp(
                    prefix=".library_", suffix=".tmp", dir=canon_dest
                )
                try:
                    with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                        json.dump(cloned_data, f, indent=2)
                    os.replace(temp_path, manifest_path)
                    created_files.append(manifest_path)
                except Exception:
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass
                    raise

                # Register in local registry
                self.register_folder_library(canon_dest)
                return manifest_path
            except Exception:
                rollback()
                raise

    def duplicate_folder_library(
        self,
        source_name_or_path,
        target_folder_path,
        target_name=None,
        overwrite=False,
        target_material=None,
        target_density=None,
        recalculate_weights=False,
    ):
        """Duplicates an existing folder library into a new target folder."""
        source_folder = self._get_registered_folder(source_name_or_path)
        if not source_folder:
            raise FileNotFoundError(f"Folder library '{source_name_or_path}' not found in registry.")

        if not target_name:
            target_name = os.path.basename(os.path.normpath(target_folder_path))

        return self.duplicate_library(
            source_folder,
            target_name,
            overwrite=overwrite,
            target_material=target_material,
            target_density=target_density,
            recalculate_weights=recalculate_weights,
            target_folder_path=target_folder_path,
        )

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
