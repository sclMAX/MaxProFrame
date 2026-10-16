"""Public T1 regressions: S1/S3/S6/S8; no FreeCAD runtime required."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from freecad.frameforge.library_manager import LibraryManager

class FolderLibrarySafety(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.counter = 0

    def state(self):
        self.counter += 1
        p = self.root / str(self.counter)
        p.mkdir()
        m = LibraryManager(str(p / 'user'), str(p / 'stock'))
        a = p / 'a'
        f = Path(m.create_folder_library(str(a), 'A'))
        return p, m, a, f

    def test_temporary_symlinks_cannot_write_outside_root(self):  # S3/S6
        for kind in ('manifest', 'registry'):
            with self.subTest(kind=kind):
                p, m, a, f = self.state()
                outside = p / 'outside'
                outside.write_bytes(b'KEEP')
                target = f if kind == 'manifest' else Path(m.registry_path)
                Path(str(target) + '.tmp.' + str(os.getpid())).symlink_to(outside)
                try:
                    if kind == 'manifest':
                        m.save_folder_library(str(a), {'Pipe': {'sizes': {}}})
                    else:
                        m.unregister_folder_library(str(a))
                except (OSError, ValueError):
                    pass
                self.assertEqual(outside.read_bytes(), b'KEEP')

    def test_registry_read_failures_never_become_empty_registry(self):  # S3/S6
        for damage in ('json', 'decode', 'schema', 'permission'):
            for operation in ('register', 'create', 'unregister'):
                with self.subTest(damage=damage, operation=operation):
                    p, m, a, f = self.state()
                    r = Path(m.registry_path)
                    b = p / 'b'
                    b.mkdir()
                    bf = b / 'library.json'
                    bf.write_text(json.dumps({'_metadata': {'name': 'B'}}))
                    if damage != 'permission':
                        r.write_bytes({'json': b'{bad', 'decode': b'\xff',
                                       'schema': b'{"folders":42}'}[damage])
                    before, catalog, other = r.read_bytes(), f.read_bytes(), bf.read_bytes()
                    if damage == 'permission':
                        r.chmod(0)
                    try:
                        with self.assertRaises((ValueError, OSError)):
                            if operation == 'register':
                                m.register_folder_library(str(b))
                            elif operation == 'create':
                                m.create_folder_library(str(p / 'new'), 'New')
                            else:
                                m.unregister_folder_library(str(a))
                    finally:
                        r.chmod(0o600)
                        self.assertEqual(r.read_bytes(), before)
                        self.assertEqual(f.read_bytes(), catalog)
                        self.assertEqual(bf.read_bytes(), other)
                        self.assertFalse((p / 'new/library.json').exists())

    def test_failed_creation_does_not_leave_manifest_blocking_retry(self):  # S6
        p = self.root
        (p / 'blocked').write_bytes(b'KEEP')
        m = LibraryManager(str(p / 'user'), str(p / 'stock'),
                           registry_path=str(p / 'blocked/folders.json'))
        with self.assertRaises(OSError):
            m.create_folder_library(str(p / 'a'), 'A')
        self.assertFalse((p / 'a/library.json').exists())
        self.assertEqual((p / 'blocked').read_bytes(), b'KEEP')
        self.assertEqual(m.list_libraries(), [])

    def test_invalid_folder_writes_are_rejected_without_data_loss(self):  # S3/S6/S8
        cases = [([], {}), ({'Pipe': []}, {}), ({}, {'density': 0}),
                 ({}, {'density': -1}), ({}, {'density': float('nan')}),
                 ({}, {'density': float('inf')})]
        for operation in ('create', 'save'):
            for data, kwargs in cases:
                with self.subTest(operation=operation, data=data, kwargs=kwargs):
                    p, m, a, f = self.state()
                    before, registry = f.read_bytes(), Path(m.registry_path).read_bytes()
                    with self.assertRaises((ValueError, TypeError)):
                        if operation == 'create':
                            m.create_folder_library(str(p / 'new'), 'New', data=data, **kwargs)
                        else:
                            m.save_folder_library(str(a), data, **kwargs)
                    self.assertEqual(f.read_bytes(), before)
                    self.assertEqual(Path(m.registry_path).read_bytes(), registry)
                    self.assertFalse((p / 'new/library.json').exists())

    def test_invalid_registration_metadata_never_changes_registry(self):  # S3/S6/S8
        for material, density in [({'bad': 'value'}, None), ('Steel', float('nan')),
                                  ('Steel', float('inf')), ('', 7.85)]:
            with self.subTest(material=material, density=density):
                p, m, a, f = self.state()
                b = p / 'b'
                b.mkdir()
                bf = b / 'library.json'
                meta = {'name': 'B', 'material': material}
                if density is not None:
                    meta['density'] = density
                bf.write_text(json.dumps({'_metadata': meta}))
                before, registry = bf.read_bytes(), Path(m.registry_path).read_bytes()
                with self.assertRaises(ValueError):
                    m.register_folder_library(str(b))
                self.assertEqual(bf.read_bytes(), before)
                self.assertEqual(Path(m.registry_path).read_bytes(), registry)

    def test_rename_collision_preserves_legacy_identity(self):  # S1/S3/S8
        p, m, a, f = self.state()
        m.save_user_library('Legacy', {'LegacyFamily': {}})
        before, registry = f.read_bytes(), Path(m.registry_path).read_bytes()
        with self.assertRaises(ValueError):
            m.save_folder_library(str(a), {'_metadata': {'name': 'Legacy'}, 'FolderFamily': {}})
        self.assertEqual(f.read_bytes(), before)
        self.assertEqual(Path(m.registry_path).read_bytes(), registry)
        self.assertIn('LegacyFamily', m.get_library('Legacy'))

if __name__ == '__main__':
    unittest.main()
