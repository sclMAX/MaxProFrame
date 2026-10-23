"""ZIP exchange contracts through the public manager API; no sketch execution."""
import copy
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from freecad.maxproframe.library_manager import LibraryManager


class TestLibraryZip(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mpf-zip-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manager = LibraryManager(user_dir=str(self.root / 'user'), stock_dir=str(self.root / 'stock'))
        self.data = {'_metadata': {'name': 'Portable', 'material': 'Alloy', 'density': 4.3},
                     'Square': {'sizes': {'10': {'Width': '10', 'Weight': '1.2'}}},
                     'Custom Profile': {'sizes': {key: {'asset_path': 'sections/a.FCStd', 'Weight': '2.3'}
                                                  for key in ('A', 'B')}}}

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def archive(self, data=None, members=None):
        path = self.root / 'input.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('library.json', json.dumps(self.data if data is None else data))
            for name, value in (members if members is not None else [('sections/a.FCStd', b'opaque native asset')]):
                archive.writestr(name, value)
        return path

    def reject(self, archive, **kwargs):
        before = self.snapshot()
        with self.assertRaises((ValueError, FileExistsError, OSError, zipfile.BadZipFile)):
            self.manager.import_library_zip(str(archive), **kwargs)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.manager.list_libraries(), [])

    def test_export_roundtrip_and_shared_references(self):
        source = self.root / 'source'
        self.manager.create_folder_library(str(source), 'Portable', material='Alloy', density=4.3, data=self.data)
        (source / 'sections').mkdir()
        (source / 'sections/a.FCStd').write_bytes(b'opaque native asset')
        (source / 'original.dxf').write_bytes(b'excluded')
        archive = self.root / 'export.zip'
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.manager.export_library_zip('Portable', str(source / 'inside.zip'))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.manager.export_library_zip('Portable', str(archive)), str(archive))
        self.assertEqual({k: v for k, v in self.snapshot().items() if k != 'export.zip'}, before)
        with zipfile.ZipFile(archive) as bundle:
            self.assertEqual(bundle.namelist(), ['library.json', 'sections/a.FCStd'])
        other = LibraryManager(user_dir=str(self.root / 'other'), stock_dir=str(self.root / 'stock'))
        result = other.import_library_zip(str(archive))
        self.assertEqual(result['folder_path'], other.get_default_library_folder('Portable'))
        self.assertEqual(other.get_library('Portable'), self.manager.get_library('Portable'))
        self.assertEqual((Path(result['folder_path']) / 'sections/a.FCStd').read_bytes(), b'opaque native asset')
        before = self.snapshot()
        with self.assertRaises(FileExistsError):
            self.manager.export_library_zip('Portable', str(archive))
        self.assertEqual(self.snapshot(), before)

    def test_only_parametric(self):
        data = copy.deepcopy(self.data)
        del data['Custom Profile']
        result = self.manager.import_library_zip(str(self.archive(data, [])))
        self.assertEqual(self.manager.get_library('Portable'), data)
        self.assertEqual(result['name'], 'Portable')

    def test_bad_member_paths_and_types(self):
        for name in ('../escape', '/absolute', 'C:/drive', 'sections\\escape',
                     'sections/../escape', './library.json', 'sections//a.FCStd',
                     'sections/A.FCStd', 'library.json/child', 'C:relative',
                     '\\\\server\\share', 'sections/../../outside', 'sections/a.FCStd/child'):
            with self.subTest(name=name):
                self.reject(self.archive(members=[('sections/a.FCStd', b'a'), (name, b'b')]))
        for mode in (stat.S_IFLNK, stat.S_IFIFO):
            info = zipfile.ZipInfo('sections/a.FCStd')
            info.create_system = 3
            info.external_attr = (mode | 0o644) << 16
            self.reject(self.archive(members=[(info, b'link')]))
        self.reject(self.archive(members=[('sections/a.FCStd', b'a'), ('sections/a.FCStd', b'b')]))

    def test_unsupported_encrypted_and_corrupt_content(self):
        archive = self.root / 'input.zip'
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_BZIP2) as bundle:
            bundle.writestr('library.json', json.dumps(self.data))
        self.reject(archive)
        self.archive()
        raw = bytearray(archive.read_bytes())
        # Mark both the local and central entries encrypted without using a password.
        for signature, offset in ((b'PK\x03\x04', 6), (b'PK\x01\x02', 8)):
            start = 0
            while True:
                position = raw.find(signature, start)
                if position < 0:
                    break
                raw[position + offset] |= 1
                start = position + 4
        archive.write_bytes(raw)
        self.reject(archive)
        with zipfile.ZipFile(archive, 'w') as bundle:
            bundle.writestr('library.json', '{invalid json')
        self.reject(archive)
        with zipfile.ZipFile(archive, 'w') as bundle:
            bundle.writestr('other.json', '{}')
        self.reject(archive)

    def test_copy_failure_rolls_back_owned_destination(self):
        archive = self.archive()
        before = self.snapshot()
        with patch('freecad.maxproframe.library_archive.shutil.copyfile', side_effect=OSError('copy denied')):
            with self.assertRaisesRegex(OSError, 'copy denied'):
                self.manager.import_library_zip(str(archive))
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(Path(self.manager.get_default_library_folder('Portable')).exists())

    def test_bad_catalog_and_assets(self):
        for update in ({'_metadata': []}, {'_metadata': {'name': 'Bad', 'density': -1}},
                       {'Square': {'sizes': []}}, {'Square': {'sizes': {'a': []}}},
                       {'Custom Profile': {'sizes': {'a': {'asset_path': '../a'}}}},
                       {'Custom Profile': {'sizes': {'a': {'asset_path': 5}}}}):
            data = copy.deepcopy(self.data)
            data.update(update)
            with self.subTest(update=update):
                self.reject(self.archive(data))
        self.reject(self.archive(members=[]))
        self.reject(self.archive(members=[('sections/a.FCStd', b'a'), ('original.dxf', b'dxf')]))
        archive = self.root / 'input.zip'
        archive.write_bytes(b'not a zip')
        self.reject(archive)

    def test_limits_and_registry_failure(self):
        from freecad.maxproframe import library_archive
        archive = self.archive()
        for constant, value in (('MAX_MEMBERS', 1), ('MAX_EXPANDED_BYTES', 5), ('MAX_MEMBER_BYTES', 5)):
            with patch.object(library_archive, constant, value):
                self.reject(archive)
        before = self.snapshot()
        with patch.object(self.manager, '_save_registry', side_effect=OSError('registry denied')):
            with self.assertRaisesRegex(OSError, 'registry denied'):
                self.manager.import_library_zip(str(archive))
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(Path(self.manager.get_default_library_folder('Portable')).exists())

    def test_destination_and_name_conflicts(self):
        archive = self.archive()
        destination = self.root / 'existing'
        destination.mkdir()
        (destination / 'keep').write_bytes(b'untouched')
        self.reject(archive, target_folder_path=str(destination))
        self.manager.create_folder_library(str(self.root / 'existing-library'), 'Portable')
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.manager.import_library_zip(str(archive))
        self.assertEqual(self.snapshot(), before)

    def test_export_missing_escaped_and_symlink_assets(self):
        source = self.root / 'source'
        manifest = Path(self.manager.create_folder_library(str(source), 'Portable', data=self.data))
        for asset in ('sections/missing.FCStd', '../outside.FCStd', '/absolute', 'C:/drive', 'sections\\a.FCStd'):
            data = json.loads(manifest.read_text())
            for props in data['Custom Profile']['sizes'].values():
                props['asset_path'] = asset
            manifest.write_text(json.dumps(data))
            before = self.snapshot()
            with self.assertRaises((ValueError, FileNotFoundError)):
                self.manager.export_library_zip('Portable', str(self.root / 'export.zip'))
            self.assertEqual(self.snapshot(), before)
        (source / 'sections').mkdir()
        (self.root / 'outside.FCStd').write_bytes(b'outside')
        (source / 'sections/link.FCStd').symlink_to(self.root / 'outside.FCStd')
        data['Custom Profile']['sizes'] = {'a': {'asset_path': 'sections/link.FCStd'}}
        manifest.write_text(json.dumps(data))
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.manager.export_library_zip('Portable', str(self.root / 'export.zip'))
        self.assertEqual(self.snapshot(), before)
        with self.assertRaises(ValueError):
            self.manager.export_library_zip('Unknown stock', str(self.root / 'export.zip'))
