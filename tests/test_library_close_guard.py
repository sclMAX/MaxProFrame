"""Public dialog close paths must respect unsaved catalog edits."""
import copy
import os
import tempfile
import unittest
from unittest.mock import patch

from PySide import QtWidgets
from freecad.maxproframe.library_manager import LibraryManager
from freecad.maxproframe.library_manager_dialog import ProfileLibraryManagerDialog


class TestLibraryCloseGuard(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = LibraryManager(user_dir=os.path.join(self.temp.name, 'user'),
                                      stock_dir=os.path.join(self.temp.name, 'stock'),
                                      registry_path=os.path.join(self.temp.name, 'registry.json'))
        self.manager.create_folder_library(os.path.join(self.temp.name, 'catalog'), 'Catalog', data={
            'Square': {'norm': 'Original', 'fillet': False,
                       'sizes': {'S1': {'Height': '20', 'Width': '20'}}}})
        self.dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(self.discard)
        self.dialog.refresh_libraries(select_name='Catalog')
        self.dialog.show()
        self.app.processEvents()
        self.stored = copy.deepcopy(self.manager.get_library('Catalog'))

    def discard(self):
        with patch.object(QtWidgets.QMessageBox, 'question', return_value=QtWidgets.QMessageBox.Discard):
            self.dialog.close()

    def invoke(self, path):
        if path == 'button':
            self.dialog.btn_close.click()
        elif path == 'done':
            self.dialog.done(QtWidgets.QDialog.Rejected)
        else:
            getattr(self.dialog, path)()

    def test_cancel_all_entrypoints_preserves_raw_edits(self):
        self.dialog.table_sizes.item(0, 1).setText('33')
        before = copy.deepcopy(self.dialog.current_lib_data)
        for path in ('close', 'button', 'reject', 'done'):
            with self.subTest(path=path), patch.object(QtWidgets.QMessageBox, 'question',
                    return_value=QtWidgets.QMessageBox.Cancel) as question:
                self.invoke(path)
                question.assert_called_once()
                self.assertTrue(self.dialog.isVisible())
                self.assertFalse(self.dialog._is_closed)
                self.assertTrue(self.dialog.is_dirty)
                self.assertEqual(self.dialog.current_lib_data, before)
                self.assertEqual(self.dialog.table_sizes.item(0, 1).text(), '33')
                self.assertEqual(self.manager.get_library('Catalog'), self.stored)

    def test_save_persists_and_closes_once(self):
        self.dialog.table_sizes.item(0, 1).setText('33')
        with patch.object(QtWidgets.QMessageBox, 'question', return_value=QtWidgets.QMessageBox.Save) as question, \
                patch.object(self.dialog, '_cleanup_edit_session_and_staged_assets',
                             wraps=self.dialog._cleanup_edit_session_and_staged_assets) as cleanup:
            self.dialog.btn_close.click()
            question.assert_called_once()
            cleanup.assert_called_once()
        self.assertFalse(self.dialog.isVisible())
        expected = copy.deepcopy(self.stored)
        expected['Square']['sizes']['S1'] = {
            'Height': '33', 'Width': '20', 'Thickness': '0',
            'Flange Thickness': '0', 'Radius1': '0', 'Radius2': '0', 'Weight': '5.181'}
        self.assertEqual(self.manager.get_library('Catalog'), expected)

    def test_discard_does_not_publish(self):
        self.dialog.table_sizes.item(0, 1).setText('33')
        with patch.object(QtWidgets.QMessageBox, 'question', return_value=QtWidgets.QMessageBox.Discard) as question, \
                patch.object(self.dialog, '_cleanup_edit_session_and_staged_assets',
                             wraps=self.dialog._cleanup_edit_session_and_staged_assets) as cleanup:
            self.dialog.reject()
            question.assert_called_once()
            cleanup.assert_called_once()
        self.assertFalse(self.dialog.isVisible())
        self.assertEqual(self.manager.get_library('Catalog'), self.stored)

    def test_failed_save_stays_open(self):
        self.dialog.table_sizes.item(0, 1).setText('33')
        with patch.object(QtWidgets.QMessageBox, 'question', return_value=QtWidgets.QMessageBox.Save), \
                patch.object(QtWidgets.QMessageBox, 'warning'), \
                patch.object(self.manager, 'save_folder_library', side_effect=ValueError('Save failed')):
            self.dialog.close()
        self.assertTrue(self.dialog.isVisible())
        self.assertTrue(self.dialog.is_dirty)
        self.assertFalse(self.dialog._is_closed)
        self.assertEqual(self.manager.get_library('Catalog'), self.stored)

    def test_close_translation_in_sources_and_runtime_aliases(self):
        import xml.etree.ElementTree as ET
        from PySide import QtCore
        from freecad.maxproframe.ff_tools import TRANSLATIONSPATH
        source = 'You have unsaved changes. Do you want to save them before closing?'
        expected = 'Tenés cambios sin guardar. ¿Querés guardarlos antes de cerrar?'
        for name in ('frameforge_es.ts', 'maxproframe_es.ts'):
            tree = ET.parse(os.path.join(TRANSLATIONSPATH, name))
            self.assertIn((source, expected), [(m.findtext('source'), m.findtext('translation'))
                          for c in tree.findall('context') if c.findtext('name') == 'frameforge'
                          for m in c.findall('message')])
        for prefix in ('frameforge', 'FrameForge', 'maxproframe', 'MaxProFrame'):
            for locale in ('es', 'es-ES', 'es-CO', 'es-AR'):
                translator = QtCore.QTranslator()
                self.assertTrue(translator.load(os.path.join(TRANSLATIONSPATH, f'{prefix}_{locale}.qm')))
                self.assertEqual(translator.translate('frameforge', source), expected)

    def test_clean_close_has_no_prompt(self):
        with patch.object(QtWidgets.QMessageBox, 'question') as question:
            self.dialog.close()
        question.assert_not_called()
        self.assertFalse(self.dialog.isVisible())
