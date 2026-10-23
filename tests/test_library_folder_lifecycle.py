"""Public T1 lifecycle contracts, using isolated libraries only."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide import QtWidgets
from freecad.maxproframe.library_manager import LibraryManager
from freecad.maxproframe.library_manager_dialog import NewLibraryDialog, ProfileLibraryManagerDialog


class TestFolderLifecycle(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mpf-lifecycle-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stock = self.root / 'stock'
        self.stock.mkdir()
        self.manager = LibraryManager(user_dir=str(self.root / 'user'), stock_dir=str(self.stock))
        self.data = {'_metadata': {'name': 'Stock', 'material': 'Steel', 'density': 7.85},
                     'Square': {'sizes': {'10': {'Height': '10', 'Width': '10', 'Weight': '0.785'}}}}
        (self.stock / 'stock.json').write_text(json.dumps(self.data))

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def test_unified_creation_destination_and_cancel(self):
        dialog = NewLibraryDialog(user_dir=self.manager.user_dir, default_name='First')
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.get_destination(), str(self.root / 'user/first'))
        dialog.le_name.setText('../Second')
        self.assertEqual(dialog.get_destination(), str(self.root / 'user/second'))
        before = self.snapshot()
        with patch.object(QtWidgets.QFileDialog, 'getExistingDirectory', return_value=''):
            dialog.btn_destination.click()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(dialog.get_destination(), str(self.root / 'user/second'))
        destination = str(self.root / 'chosen')
        with patch.object(QtWidgets.QFileDialog, 'getExistingDirectory', return_value=destination):
            dialog.btn_destination.click()
        dialog.le_name.setText('Third')
        self.assertEqual(dialog.get_destination(), destination)
        dialog.reject()
        self.assertEqual(self.snapshot(), before)

    def test_stock_and_folder_duplication_create_owned_folders(self):
        for source, name in [('Stock', 'First'), ('First', 'Second')]:
            with self.subTest(source=source):
                result = self.manager.duplicate_library(source, name, target_material='Aluminium',
                                                        target_density=2.70, recalculate_weights=True)
                self.assertEqual(result, str(self.root / 'user' / name.lower() / 'library.json'))
                self.assertEqual(self.manager.get_folder_library_path(name), str(Path(result).parent))
                data = self.manager.get_library(name)
                self.assertEqual(data['_metadata']['material'], 'Aluminium')
                self.assertEqual(data['_metadata']['density'], 2.70)
                self.assertEqual(data['Square']['sizes']['10']['Weight'], '0.27')
        (self.stock / 'stock.json').rename(self.stock / 'stock_slug.json')
        alias_copy = self.manager.duplicate_library('stock_slug', 'Alias copy')
        self.assertEqual(alias_copy, str(self.root / 'user/alias_copy/library.json'))
        self.assertEqual(self.manager.get_library('Alias copy')['Square'], self.data['Square'])
        before = self.snapshot()
        with self.assertRaises((ValueError, FileExistsError)):
            self.manager.duplicate_library('Stock', 'First')
        self.assertEqual(self.snapshot(), before)

    def test_duplicate_dialog_preserves_source_custom_density(self):
        self.manager.create_folder_library(str(self.root / 'source'), 'Custom material',
                                           material='Workshop alloy', density=4.3, data=self.data)
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name='Custom material')
        with patch.object(NewLibraryDialog, 'exec_', return_value=QtWidgets.QDialog.Accepted):
            dialog.btn_dup_lib.click()
        self.assertEqual(self.manager.get_library_material_info(dialog.current_lib_meta['name']),
                         ('Workshop alloy', 4.3))

    def test_stock_declared_assets_and_rejection_are_transactional(self):
        sections = self.stock / 'sections'
        sections.mkdir()
        (sections / 'declared.FCStd').write_bytes(b'declared section')
        (sections / 'notes.txt').write_text('not an asset')
        self.data['Custom Profile'] = {'sizes': {'Section': {
            'asset_path': 'sections/declared.FCStd', 'Weight': '4.2'}}}
        (self.stock / 'stock.json').write_text(json.dumps(self.data))
        result = Path(self.manager.duplicate_library('Stock', 'Portable'))
        self.assertEqual((result.parent / 'sections/declared.FCStd').read_bytes(), b'declared section')
        self.assertFalse((result.parent / 'sections/notes.txt').exists())
        self.assertEqual(self.manager.get_library('Portable')['Custom Profile'], self.data['Custom Profile'])
        self.data['Custom Profile']['sizes']['Section']['asset_path'] = '../outside.FCStd'
        (self.stock / 'stock.json').write_text(json.dumps(self.data))
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.manager.duplicate_library('Stock', 'Rejected')
        self.assertEqual(self.snapshot(), before)

    def test_stock_duplicate_button_uses_unified_destination(self):
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.current_lib_meta['name'], 'Stock')
        with patch.object(NewLibraryDialog, 'exec_', return_value=QtWidgets.QDialog.Accepted):
            dialog.btn_dup_lib.click()
        self.assertTrue(dialog.current_lib_meta['is_folder'])
        self.assertEqual(dialog.current_lib_meta['folder_path'],
                         self.manager.get_default_library_folder(dialog.current_lib_meta['name']))
        self.assertEqual(dialog.current_lib_data['Square'], self.data['Square'])

    def test_creation_buttons_use_folder_manager_and_reject_conflicts(self):
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        for index, button in enumerate((dialog.btn_new_lib,)):
            name = 'Created' + str(index)
            destination = str(self.root / name)
            with patch.object(NewLibraryDialog, 'exec_', return_value=QtWidgets.QDialog.Accepted), \
                 patch.object(NewLibraryDialog, 'get_values', return_value=(name, 'Steel', 7.85, False)), \
                 patch.object(NewLibraryDialog, 'get_destination', return_value=destination):
                button.click()
            self.assertEqual(self.manager.get_folder_library_path(name), destination)
        before = self.snapshot()
        with patch.object(NewLibraryDialog, 'exec_', return_value=QtWidgets.QDialog.Rejected):
            dialog.btn_new_lib.click()
        self.assertEqual(self.snapshot(), before)
        with patch.object(NewLibraryDialog, 'exec_', return_value=QtWidgets.QDialog.Accepted), \
             patch.object(NewLibraryDialog, 'get_values', return_value=('Conflict', 'Steel', 7.85, False)), \
             patch.object(NewLibraryDialog, 'get_destination', return_value=str(self.root / 'Created0')), \
             patch.object(QtWidgets.QMessageBox, 'warning') as warning:
            dialog.btn_new_lib.click()
        warning.assert_called_once()
        self.assertEqual(self.snapshot(), before)
