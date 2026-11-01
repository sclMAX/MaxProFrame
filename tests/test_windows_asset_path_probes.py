"""Regression probes for section asset paths written on Windows (S2, S3).

MaxProFrame 1.0.0 on Windows stored captured sections as 'sections\\<file>'. These tests pin, through the
public library functions, that every escape form stays rejected without side effects, that the portable
forms resolve to the real file, and that save, duplicate, purge and ZIP exchange only ever change the
asset_path separator. Card thumbnails must not leave temporary files behind on BREP failures.
"""

import copy
import hashlib
import json
import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from freecad.maxproframe.library_manager import LibraryManager
from freecad.maxproframe.section_library import (
    purge_unreferenced_assets,
    resolve_and_validate_asset_path,
)

ESCAPES = (
    "..\\x",
    "sections\\..\\..\\x",
    "sections\\..\\x",
    "\\x",
    "C:\\x",
    "C:x",
    "c:/x",
    "\\\\host\\share\\x",
    "//host/share/x",
    "/abs/x",
    "sections/..\\..\\x",
    "sections\\/..\\/..\\x",
    ".\\..\\x",
    "x\\..\\sections\\a",
    "sections\\.\\..\\..\\x",
    "other\\a",
    "sections\\..",
)


def _file_hash(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _tree(root):
    """Every entry below root with its bytes or link target, to prove nothing was created or changed."""
    entries = {}
    for current, dirs, files in os.walk(root):
        for name in dirs + files:
            path = os.path.join(current, name)
            rel = os.path.relpath(path, root)
            if os.path.islink(path):
                entries[rel] = ("link", os.readlink(path))
            elif os.path.isdir(path):
                entries[rel] = ("dir",)
            else:
                with open(path, "rb") as f:
                    entries[rel] = ("file", f.read())
    return entries


def _asset_paths(data):
    return {
        size: props["asset_path"]
        for family, fam in data.items()
        if not family.startswith("_")
        for size, props in fam.get("sizes", {}).items()
        if "asset_path" in props
    }


class TestWindowsAssetPathProbes(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="ff_test_win_paths_")
        self.addCleanup(self.workspace.cleanup)
        self.root = os.path.realpath(self.workspace.name)
        self.user_dir = os.path.join(self.root, "user")
        self.registry_path = os.path.join(self.user_dir, ".registry", "folders.json")
        self.manager = LibraryManager(
            user_dir=self.user_dir, stock_dir=os.path.join(self.root, "stock"), registry_path=self.registry_path
        )
        with open(os.path.join(self.root, "x"), "wb") as f:
            f.write(b"outside the library")

    def _write_assets(self, library_root, contents=None):
        contents = contents or {"a.FCStd": b"asset a", "sub/b.FCStd": b"asset b"}
        for rel, value in contents.items():
            path = os.path.join(library_root, "sections", *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(value)

    def _create_library(self, name, data):
        folder = os.path.join(self.root, name)
        manifest = self.manager.create_folder_library(folder, name, material="Steel", density=7.85, data=data)
        self._write_assets(folder)
        return folder, manifest

    def test_escapes_rejected_and_valid_forms_resolve(self):
        library = os.path.join(self.root, "lib")
        self._write_assets(library)
        # The literal escape targets exist next to the library root.
        os.makedirs(os.path.join(library, "other"))
        with open(os.path.join(library, "other", "a"), "wb") as f:
            f.write(b"not a section")
        before = _tree(self.root)

        for escape in ESCAPES:
            with self.subTest(escape=escape):
                with self.assertRaises(ValueError):
                    resolve_and_validate_asset_path(library, escape)
        self.assertEqual(_tree(self.root), before)

        expected_a = os.path.realpath(os.path.join(library, "sections", "a.FCStd"))
        expected_b = os.path.realpath(os.path.join(library, "sections", "sub", "b.FCStd"))
        for valid, expected in (
            ("sections/a.FCStd", expected_a),
            ("sections\\a.FCStd", expected_a),
            ("./sections/a.FCStd", expected_a),
            ("sections//a.FCStd", expected_a),
            ("sections/sub/b.FCStd", expected_b),
            ("sections\\sub\\b.FCStd", expected_b),
        ):
            with self.subTest(valid=valid):
                resolved = resolve_and_validate_asset_path(library, valid)
                self.assertEqual(resolved, expected)
                self.assertTrue(os.path.isfile(resolved))
        self.assertEqual(_tree(self.root), before)

        with self.subTest(escape="symlink inside sections"):
            try:
                os.symlink(os.path.join(self.root, "x"), os.path.join(library, "sections", "link.FCStd"))
                os.symlink(self.root, os.path.join(library, "sections", "linkdir"), target_is_directory=True)
            except (OSError, NotImplementedError) as err:
                self.skipTest(f"Symlinks cannot be created here: {err}")
            before = _tree(self.root)
            for escape in (
                "sections\\link.FCStd",
                "sections/link.FCStd",
                "sections\\linkdir\\x",
                "sections/linkdir/x",
            ):
                with self.assertRaises(ValueError, msg=escape):
                    resolve_and_validate_asset_path(library, escape)
            self.assertEqual(_tree(self.root), before)

    def test_save_only_changes_asset_path_separator(self):
        data = {
            "_metadata": {"notes": "kept\\as\\typed", "asset_path": "sections\\meta.FCStd"},
            "_private": {"sizes": {"P": {"asset_path": "sections\\private.FCStd"}}},
            "Custom Profile": {
                "canonical_family": "Custom Profile",
                "asset_path": "sections\\family.FCStd",
                "sizes": {
                    "CP-1": {
                        "asset_path": "sections\\a.FCStd",
                        "object_name": "Section\\One",
                        "asset_id": "a",
                        "Weight": "1.5",
                        "Description": "Drawn in C:\\work\\a.dxf",
                    },
                    "CP-2": {"asset_path": "sections\\sub\\b.FCStd", "Weight": "2.5", "Height": "20"},
                    "CP-3": {"asset_path": "sections/a.FCStd", "Description": "already portable"},
                },
            },
            "Square Hollow": {"sizes": {"20x20x2": {"Height": "20", "Width": "20", "Thickness": "2"}}},
        }
        folder, manifest = self._create_library("SaveLib", data)
        with open(manifest, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        caller_copy = copy.deepcopy(loaded)

        self.assertEqual(self.manager.save_folder_library("SaveLib", loaded), manifest)

        self.assertEqual(loaded, caller_copy, "The caller's catalog must not be mutated.")
        with open(manifest, "r", encoding="utf-8") as f:
            saved = json.load(f)
        expected = copy.deepcopy(caller_copy)
        sizes = expected["Custom Profile"]["sizes"]
        sizes["CP-1"]["asset_path"] = "sections/a.FCStd"
        sizes["CP-2"]["asset_path"] = "sections/sub/b.FCStd"
        self.assertEqual(saved, expected)
        self.assertEqual(saved["_metadata"]["asset_path"], "sections\\meta.FCStd")
        self.assertEqual(saved["_private"]["sizes"]["P"]["asset_path"], "sections\\private.FCStd")
        self.assertEqual(saved["Custom Profile"]["asset_path"], "sections\\family.FCStd")

        # Rejected saves leave the stored manifest byte-identical and create no other file.
        with open(manifest, "rb") as f:
            stored = f.read()
        entries = sorted(os.listdir(folder))
        rejected = copy.deepcopy(caller_copy)
        rejected["Custom Profile"]["sizes"]["CP-1"]["asset_path"] = "sections\\a.FCStd"
        for case, kwargs, payload in (
            ("material change", {"material": "Aluminium"}, rejected),
            ("invalid family", {}, dict(rejected, Broken="not a family")),
        ):
            with self.subTest(case=case):
                with self.assertRaises(ValueError):
                    self.manager.save_folder_library("SaveLib", payload, **kwargs)
                with open(manifest, "rb") as f:
                    self.assertEqual(f.read(), stored)
                self.assertEqual(sorted(os.listdir(folder)), entries)

    def test_duplicate_mixed_forms_and_escapes(self):
        data = {
            "Custom Profile": {
                "sizes": {
                    "A1": {"asset_path": "sections\\a.FCStd", "object_name": "Section", "Weight": "1.0"},
                    "A2": {"asset_path": "sections/a.FCStd", "object_name": "Section", "Weight": "1.0"},
                    "B": {"asset_path": "sections\\sub\\b.FCStd", "object_name": "Section", "Weight": "2.0"},
                }
            }
        }
        source, manifest = self._create_library("MixedLib", data)
        source_hash = _file_hash(manifest)
        destination = os.path.join(self.root, "MixedCopy")
        real_copyfile = shutil.copyfile
        copied = []

        def record_copy(src, dst, *args, **kwargs):
            copied.append(os.path.relpath(dst, destination))
            return real_copyfile(src, dst, *args, **kwargs)

        with patch("freecad.maxproframe.library_manager.shutil.copyfile", side_effect=record_copy):
            result = self.manager.duplicate_library("MixedLib", "MixedCopy", target_folder_path=destination)

        self.assertEqual(result, os.path.join(destination, "library.json"))
        self.assertEqual(
            sorted(copied), sorted([os.path.join("sections", "a.FCStd"), os.path.join("sections", "sub", "b.FCStd")])
        )
        self.assertEqual(
            _tree(os.path.join(destination, "sections")),
            {"a.FCStd": ("file", b"asset a"), "sub": ("dir",), os.path.join("sub", "b.FCStd"): ("file", b"asset b")},
        )
        with open(result, "r", encoding="utf-8") as f:
            copy_data = json.load(f)
        self.assertEqual(
            _asset_paths(copy_data),
            {"A1": "sections/a.FCStd", "A2": "sections/a.FCStd", "B": "sections/sub/b.FCStd"},
        )
        self.assertEqual(_file_hash(manifest), source_hash)
        self.assertEqual(self.manager.get_folder_library_path("MixedCopy"), os.path.realpath(destination))

        for escape in ("..\\x", "sections\\..\\..\\x", "\\x", "C:\\x", "\\\\host\\share\\x", "sections/..\\..\\x"):
            with self.subTest(escape=escape):
                escaped = copy.deepcopy(data)
                escaped["Custom Profile"]["sizes"]["B"]["asset_path"] = escape
                with open(manifest, "w", encoding="utf-8") as f:
                    json.dump(dict(escaped, _metadata={"name": "MixedLib", "material": "Steel"}), f)
                escaped_hash = _file_hash(manifest)
                registry_hash = _file_hash(self.registry_path)
                target = os.path.join(self.root, "EscapeCopy")
                os.makedirs(target, exist_ok=True)
                with self.assertRaises(ValueError):
                    self.manager.duplicate_library("MixedLib", "EscapeCopy", target_folder_path=target)
                self.assertEqual(os.listdir(target), [])
                self.assertEqual(_file_hash(self.registry_path), registry_hash)
                self.assertEqual(_file_hash(manifest), escaped_hash)

    def test_purge_cross_forms(self):
        library = os.path.join(self.root, "PurgeLib")
        self._write_assets(
            library,
            {"a.FCStd": b"a", "b.FCStd": b"b", "c.FCStd": b"c", "sub/d.FCStd": b"d", "sub/e.FCStd": b"e"},
        )
        catalog = {
            "Custom Profile": {
                "sizes": {
                    "A": {"asset_path": "sections\\a.FCStd"},
                    "B": {"asset_path": "sections/b.FCStd"},
                    "D": {"asset_path": "sections\\sub\\d.FCStd"},
                }
            }
        }
        catalog_copy = copy.deepcopy(catalog)

        deleted = purge_unreferenced_assets(
            library,
            [
                "sections/a.FCStd",
                "sections\\b.FCStd",
                "sections\\c.FCStd",
                "sections/sub/d.FCStd",
                "sections/sub\\e.FCStd",
            ],
            catalog,
        )

        self.assertEqual(sorted(deleted), ["sections/sub\\e.FCStd", "sections\\c.FCStd"])
        self.assertEqual(
            _tree(os.path.join(library, "sections")),
            {
                "a.FCStd": ("file", b"a"),
                "b.FCStd": ("file", b"b"),
                "sub": ("dir",),
                os.path.join("sub", "d.FCStd"): ("file", b"d"),
            },
        )
        self.assertEqual(catalog, catalog_copy)

        before = _tree(self.root)
        for escape in ("sections\\..\\..\\x", "..\\x", "\\x", "C:\\x", "other\\a"):
            with self.subTest(staged=escape):
                with self.assertRaises(ValueError):
                    purge_unreferenced_assets(library, [escape], catalog)
                self.assertEqual(_tree(self.root), before)
            with self.subTest(referenced=escape):
                bad_catalog = copy.deepcopy(catalog)
                bad_catalog["Custom Profile"]["sizes"]["X"] = {"asset_path": escape}
                with self.assertRaises(ValueError):
                    purge_unreferenced_assets(library, ["sections/a.FCStd"], bad_catalog)
                self.assertEqual(_tree(self.root), before)

    def test_zip_export_portable_import_strict(self):
        data = {
            "Custom Profile": {
                "sizes": {
                    "A": {"asset_path": "sections\\a.FCStd", "Weight": "1.0"},
                    "B": {"asset_path": "sections\\sub\\b.FCStd", "Weight": "2.0"},
                }
            }
        }
        source, manifest = self._create_library("ZipLib", data)
        with open(manifest, "rb") as f:
            stored = f.read()
        archive = os.path.join(self.root, "export.zip")

        self.assertEqual(self.manager.export_library_zip("ZipLib", archive), archive)

        with open(manifest, "rb") as f:
            self.assertEqual(f.read(), stored)
        with zipfile.ZipFile(archive) as bundle:
            self.assertEqual(sorted(bundle.namelist()), ["library.json", "sections/a.FCStd", "sections/sub/b.FCStd"])
            exported = json.loads(bundle.read("library.json"))
            self.assertEqual(bundle.read("sections/a.FCStd"), b"asset a")
        self.assertEqual(_asset_paths(exported), {"A": "sections/a.FCStd", "B": "sections/sub/b.FCStd"})
        self.assertNotIn("\\", json.dumps(_asset_paths(exported)))

        # Archives stay strict: a catalog inside the ZIP must already use '/'.
        windows_archive = os.path.join(self.root, "windows.zip")
        with zipfile.ZipFile(windows_archive, "w") as bundle:
            bundle.writestr(
                "library.json",
                json.dumps(
                    {
                        "_metadata": {"name": "Imported", "material": "Steel", "density": 7.85},
                        "Custom Profile": {"sizes": {"A": {"asset_path": "sections\\a.FCStd"}}},
                    }
                ),
            )
            bundle.writestr("sections/a.FCStd", b"asset a")
        importer = LibraryManager(
            user_dir=os.path.join(self.root, "importer"), stock_dir=os.path.join(self.root, "stock")
        )
        explicit = os.path.join(self.root, "ImportedHere")
        for target in (None, explicit):
            with self.subTest(target=target):
                before = _tree(self.root)
                with self.assertRaisesRegex(ValueError, "Unsafe archive path"):
                    importer.import_library_zip(windows_archive, target_folder_path=target)
                self.assertEqual(_tree(self.root), before)
                self.assertFalse(os.path.lexists(explicit))
                self.assertFalse(os.path.lexists(importer.get_default_library_folder("Imported")))
                self.assertEqual(importer.list_libraries(), [])

    def test_brep_failure_returns_none_without_temp_files(self):
        from freecad.maxproframe.custom_profile_cards import _extract_custom_section_face_from_fcstd

        document = (
            '<?xml version="1.0" encoding="utf-8"?><Document><Objects>'
            '<Object type="Sketcher::SketchObject" name="Section"/></Objects><ObjectData><Object name="Section">'
            '<Properties><Property name="Shape" type="Part::PropertyPartShape"><Part file="Section.Shape.brp"/>'
            "</Property></Properties></Object></ObjectData></Document>"
        )
        scratch = tempfile.mkdtemp(prefix="ff_test_brep_tmp_")
        self.addCleanup(shutil.rmtree, scratch, True)
        for case, brep in (
            ("garbage", b"this is not a BREP shape\n"),
            ("non-UTF-8", b"\xff\xfe\x00\x80 DBRep_DrawableShape \xc3\x28"),
        ):
            with self.subTest(case=case):
                asset = os.path.join(self.root, f"{case}.FCStd")
                with zipfile.ZipFile(asset, "w") as bundle:
                    bundle.writestr("Document.xml", document)
                    bundle.writestr("Section.Shape.brp", brep)
                with patch.object(tempfile, "tempdir", scratch):
                    self.assertIsNone(_extract_custom_section_face_from_fcstd(asset, "Section"))
                self.assertEqual(os.listdir(scratch), [])


if __name__ == "__main__":
    unittest.main()
