"""ZIP exchange contracts through the public manager API; no sketch execution."""
import copy
import errno
import hashlib
import json
import ntpath
import os
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

    def cloud_source(self):
        source = self.root / 'source'
        self.manager.create_folder_library(str(source), 'Portable', material='Alloy', density=4.3, data=self.data)
        (source / 'sections').mkdir()
        (source / 'sections/a.FCStd').write_bytes(b'opaque native asset')
        return self.root / 'out.zip'

    def test_cross_drive_and_unc_export_boundaries(self):
        output = self.cloud_source()
        before = self.snapshot()
        libraries = self.manager.list_libraries()
        commonpath = os.path.commonpath
        for destination in ('D:\\share\\out.zip', r'\\server\share\out.zip'):
            with self.subTest(destination=destination):
                paths = [r'C:\libraries\source', destination]
                with self.assertRaisesRegex(ValueError, "Paths don't have the same drive"):
                    ntpath.commonpath(paths)
                # Simulate only confinement; all archive IO uses real local paths.
                with patch('freecad.maxproframe.library_archive.os.path.commonpath',
                           side_effect=lambda local: ntpath.commonpath(paths) if str(local[1]) == str(output)
                           else commonpath(local)) as boundary:
                    self.assertEqual(self.manager.export_library_zip('Portable', str(output)), str(output))
                self.assertIn(unittest.mock.call([str(self.root / 'source'), str(output)]), boundary.call_args_list)
                with zipfile.ZipFile(output) as bundle:
                    self.assertEqual(bundle.namelist(), ['library.json', 'sections/a.FCStd'])
                    self.assertEqual(bundle.read('sections/a.FCStd'), b'opaque native asset')
                self.assertEqual({k: v for k, v in self.snapshot().items() if k != output.name}, before)
                self.assertEqual(self.manager.list_libraries(), libraries)
                # A second export must still refuse an existing destination.
                with patch('freecad.maxproframe.library_archive.os.path.commonpath',
                           side_effect=ValueError("Paths don't have the same drive")):
                    with self.assertRaises(FileExistsError):
                        self.manager.export_library_zip('Portable', str(output))
                output.unlink()
        with self.assertRaisesRegex(ValueError, '^Export output must be outside the source library\\.$'):
            self.manager.export_library_zip('Portable', str(self.root / 'source/inside.zip'))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.manager.list_libraries(), libraries)

    def test_unsupported_link_roundtrip(self):
        output = self.cloud_source()
        before = self.snapshot()
        for code in {errno.EPERM, errno.EOPNOTSUPP, errno.ENOTSUP, errno.ENOSYS}:
            with self.subTest(errno=code):
                target = output.with_name(str(code) + '.zip')
                with patch('freecad.maxproframe.library_archive.os.link', side_effect=OSError(code, 'unsupported')):
                    self.assertEqual(self.manager.export_library_zip('Portable', str(target)), str(target))
                other = LibraryManager(user_dir=str(self.root / ('other' + str(code))), stock_dir=str(self.root / 'stock'))
                result = other.import_library_zip(str(target))
                self.assertEqual(other.get_library('Portable'), self.manager.get_library('Portable'))
                self.assertEqual((Path(result['folder_path']) / 'sections/a.FCStd').read_bytes(), b'opaque native asset')
        self.assertEqual({key: self.snapshot()[key] for key in before}, before)
        self.assertFalse(list(self.root.glob('.library-zip-*')))

    def test_cloud_existing_racing_and_symlink_outputs(self):
        output = self.cloud_source()
        for kind in ('existing', 'race', 'symlink'):
            target = output.with_name(kind + '.zip')
            if kind == 'existing':
                target.write_bytes(b'keep')
            elif kind == 'symlink':
                target.symlink_to(self.root / 'missing')
            before = self.snapshot()
            def unsupported(*args):
                if kind == 'race':
                    target.write_bytes(b'keep')
                raise OSError(errno.EPERM, 'unsupported')
            with patch('freecad.maxproframe.library_archive.os.link', side_effect=unsupported):
                with self.assertRaises(FileExistsError):
                    self.manager.export_library_zip('Portable', str(target))
            expected = dict(before)
            if kind == 'race':
                expected[target.name] = b'keep'
            self.assertEqual(self.snapshot(), expected)
            if kind == 'symlink':
                self.assertTrue(target.is_symlink())
            self.assertFalse(list(self.root.glob('.library-zip-*')))

    def test_cloud_failure_preserves_replacement_after_stale_stat(self):
        from freecad.maxproframe import library_archive
        output = self.cloud_source()
        before = self.snapshot()
        libraries = self.manager.list_libraries()
        owned_partial = self.root / 'owned-partial'
        original_lstat = Path.lstat
        original_stream = library_archive._stream

        def replace_after_stat(path, *args, **kwargs):
            result = original_lstat(path, *args, **kwargs)
            if path == output:
                path.rename(owned_partial)
                output.write_bytes(b'unrelated replacement')
            return result

        def fail_publication(source, target, total, *limits):
            if getattr(target, 'name', None) == str(output):
                target.write(b'partial')
                raise OSError(errno.EIO, 'copy failed')
            return original_stream(source, target, total, *limits)

        with patch.object(library_archive.os, 'link', side_effect=OSError(errno.EPERM, 'unsupported')):
            with patch.object(library_archive, '_stream', side_effect=fail_publication):
                with patch.object(Path, 'lstat', replace_after_stat):
                    with self.assertRaises(OSError) as raised:
                        self.manager.export_library_zip('Portable', str(output))
        self.assertEqual(raised.exception.errno, errno.EIO)
        self.assertEqual(str(raised.exception), '[Errno 5] copy failed')
        after = self.snapshot()
        self.assertEqual({key: after[key] for key in before}, before)
        self.assertEqual(self.manager.list_libraries(), libraries)
        if owned_partial.exists():
            self.assertTrue(output.exists())
            self.assertEqual(output.read_bytes(), b'unrelated replacement')
            self.assertEqual(owned_partial.read_bytes(), b'partial')
        else:
            self.assertEqual(output.read_bytes(), b'partial')
        self.assertFalse(list(self.root.glob('.library-zip-*')))

    def test_cloud_copy_failure_and_other_link_errors_preserve_state(self):
        from freecad.maxproframe import library_archive
        output = self.cloud_source()
        before = self.snapshot()
        libraries = self.manager.list_libraries()
        original = library_archive._stream
        def fail_publication(source, target, total, *limits):
            if str(getattr(target, 'name', '')).endswith('out.zip'):
                target.write(b'partial')
                raise OSError(errno.EIO, 'copy failed')
            return original(source, target, total, *limits)
        with patch.object(library_archive.os, 'link', side_effect=OSError(errno.EPERM, 'unsupported')):
            with patch.object(library_archive, '_stream', side_effect=fail_publication):
                with self.assertRaisesRegex(OSError, 'copy failed'):
                    self.manager.export_library_zip('Portable', str(output))
        expected = dict(before, **{'out.zip': b'partial'})
        self.assertEqual(self.snapshot(), expected)
        self.assertEqual(self.manager.list_libraries(), libraries)
        self.assertFalse(list(self.root.glob('.library-zip-*')))
        with self.assertRaises(FileExistsError):
            self.manager.export_library_zip('Portable', str(output))
        self.assertEqual(self.snapshot(), expected)
        for code in (errno.EIO, errno.ENOSPC, errno.EACCES, errno.ENOENT):
            with patch.object(library_archive.os, 'link', side_effect=OSError(code, 'link failed')):
                with self.assertRaises(OSError) as raised:
                    self.manager.export_library_zip('Portable', str(self.root / 'other.zip'))
            self.assertEqual(raised.exception.errno, code)
            self.assertEqual(self.snapshot(), expected)
            self.assertFalse(list(self.root.glob('.library-zip-*')))

    def test_folder_duplicate_export_import_omits_provenance_only(self):
        for with_assets in (False, True):
            with self.subTest(with_assets=with_assets):
                root = self.root / ('assets' if with_assets else 'parametric')
                manager = LibraryManager(user_dir=str(root / 'user'), stock_dir=str(root / 'stock'))
                if with_assets:
                    manager.create_folder_library(str(root / 'source'), 'Source', material='Alloy',
                                                  density=4.3, data=self.data)
                    sections = root / 'source/sections'
                    sections.mkdir()
                    (sections / 'a.FCStd').write_bytes(b'opaque native asset')
                else:
                    manager.create_folder_library(str(root / 'source'), 'Source')
                # This public wrapper passes the canonical source path as provenance.
                manager.duplicate_folder_library('Source', str(root / 'duplicate'), target_name='Copy')
                expected = manager.get_library('Copy')
                self.assertEqual(expected['_metadata']['cloned_from'], str(root / 'source'))
                expected['_metadata'].pop('cloned_from')
                immutable = {path: hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in root.rglob('*') if path.is_file()}
                archive = root / 'out.zip'
                self.assertEqual(manager.export_library_zip('Copy', str(archive)), str(archive))
                with zipfile.ZipFile(archive) as bundle:
                    catalog_bytes = bundle.read('library.json')
                    self.assertNotIn(str(root / 'source').encode(), catalog_bytes)
                    self.assertEqual(json.loads(catalog_bytes), expected)
                    self.assertNotIn('cloned_from', json.loads(catalog_bytes)['_metadata'])
                other = LibraryManager(user_dir=str(root / 'other'), stock_dir=str(root / 'stock'))
                result = other.import_library_zip(str(archive))
                self.assertEqual(result['folder_path'], other.get_default_library_folder('Copy'))
                self.assertEqual(other.get_library('Copy'), expected)
                if with_assets:
                    self.assertEqual((Path(result['folder_path']) / 'sections/a.FCStd').read_bytes(),
                                     b'opaque native asset')
                self.assertEqual({path: hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in immutable}, immutable)

    def test_unicode_collision_preserves_existing_registry(self):
        self.manager.create_folder_library(str(self.root / 'existing'), 'Existing')
        archive = self.archive(members=[('sections/a.FCStd', b'a'),
                                        ('sections/caf\u00e9.FCStd', b'b'),
                                        ('sections/cafe\u0301.FCStd', b'c')])
        before = self.snapshot()
        libraries = self.manager.list_libraries()
        with self.assertRaisesRegex(ValueError,
                                    '^Duplicate, special, encrypted or unsupported ZIP member\\.$'):
            self.manager.import_library_zip(str(archive))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.manager.list_libraries(), libraries)

    def test_internal_asset_symlink_export_rejected(self):
        source = self.root / 'source'
        self.manager.create_folder_library(str(source), 'Portable', data=self.data)
        (source / 'sections').mkdir()
        (source / 'sections/real.FCStd').write_bytes(b'opaque native asset')
        (source / 'sections/a.FCStd').symlink_to('real.FCStd')
        before = self.snapshot()
        libraries = self.manager.list_libraries()
        with self.assertRaisesRegex(ValueError, '^Symlink section assets cannot be exported\\.$'):
            self.manager.export_library_zip('Portable', str(self.root / 'out.zip'))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.manager.list_libraries(), libraries)
        self.assertTrue((source / 'sections/a.FCStd').is_symlink())

    def test_registry_failure_preserves_existing_parent_and_registry(self):
        self.manager.create_folder_library(str(self.root / 'existing'), 'Existing')
        parent = self.root / 'parent'
        parent.mkdir()
        (parent / 'keep').write_bytes(b'pre-existing content')
        archive = self.archive()
        before = self.snapshot()
        libraries = self.manager.list_libraries()
        with patch.object(self.manager, '_save_registry', side_effect=OSError('registry denied')):
            with self.assertRaisesRegex(OSError, '^registry denied$'):
                self.manager.import_library_zip(str(archive), target_folder_path=str(parent / 'imported'))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.manager.list_libraries(), libraries)
        self.assertTrue(parent.is_dir())
        self.assertFalse((parent / 'imported').exists())

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
