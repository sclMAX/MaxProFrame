"""The cyclic garbage collector must never decide when Qt deletes an addon dialog.

A parentless dialog owned by Python is deleted in C++ as soon as its wrapper is finalized, and a
reference cycle makes that moment the cyclic GC. The GC can run inside QApplication.topLevelWidgets()
while PySide converts the list it just built, so a dialog deleted there leaves a dangling pointer
(SIGSEGV in PySide::getWrapperForQObject). Qt must stay the only owner of that lifetime: a
dialog dropped by Python survives garbage collection and is deleted (and its wrapper
invalidated) only when Qt deletes it.
"""

import gc
import os
import tempfile
import unittest

import FreeCADGui as Gui
import shiboken6
from PySide import QtCore, QtWidgets

from freecad.maxproframe.create_bom_tool import CreateBOMTaskPanel
from freecad.maxproframe.library_manager import LibraryManager
from freecad.maxproframe.library_manager_dialog import ManageProfileLibrariesCommand, ProfileLibraryManagerDialog


def _flush_deferred_deletes():
    for _ in range(3):
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        QtCore.QCoreApplication.processEvents()


def _live_widgets():
    return {shiboken6.getCppPointer(widget)[0]: widget for widget in QtWidgets.QApplication.allWidgets()}


def stale_wrappers():
    """Return (type name, C++ address) of valid QWidget wrappers whose C++ widget is gone."""
    live = _live_widgets()
    stale = []
    for wrapper in shiboken6.getAllValidWrappers():
        if isinstance(wrapper, QtWidgets.QWidget):
            address = shiboken6.getCppPointer(wrapper)[0]
            if address not in live:
                stale.append((type(wrapper).__name__, address))
    return stale


class TestQtWrapperLifetime(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        _flush_deferred_deletes()
        gc.collect()
        self.baseline = set(stale_wrappers())

    def assert_no_new_stale_wrappers(self):
        _flush_deferred_deletes()
        new = sorted(set(stale_wrappers()) - self.baseline)
        self.assertEqual(new, [], "PySide kept wrappers for widgets that C++ deleted")

    def assert_survives_gc_and_dies_with_qt(self, widget):
        address = shiboken6.getCppPointer(widget)[0]
        destroyed = []
        widget.destroyed.connect(lambda *_: destroyed.append(address))
        widget._reference_cycle = widget
        widget = None

        gc.collect()
        self.assertIn(address, _live_widgets(), "the garbage collector deleted the C++ widget")
        self.assertEqual(destroyed, [])

        _live_widgets()[address].deleteLater()
        _flush_deferred_deletes()
        self.assertEqual(destroyed, [address])
        self.assert_no_new_stale_wrappers()

    def test_library_manager_dropped_by_python_is_deleted_only_by_qt(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = LibraryManager(
                user_dir=os.path.join(temp, "user"),
                stock_dir=os.path.join(temp, "stock"),
                registry_path=os.path.join(temp, "registry.json"),
            )
            self.assert_survives_gc_and_dies_with_qt(ProfileLibraryManagerDialog(library_manager=manager))

    def test_loadui_form_dropped_by_python_is_deleted_only_by_qt(self):
        panel = CreateBOMTaskPanel()
        form = panel.form
        panel = None
        self.assert_survives_gc_and_dies_with_qt(form)

    def test_library_manager_command_open_and_close_leaves_no_stale_wrappers(self):
        for _ in range(2):
            ManageProfileLibrariesCommand().Activated()
            dialog = getattr(Gui.getMainWindow(), "_frameforge_library_manager", None)
            self.assertIsNotNone(dialog)
            self.assertTrue(dialog.isVisible())
            dialog.close()
            dialog = None
            _flush_deferred_deletes()
        self.assert_no_new_stale_wrappers()


if __name__ == "__main__":
    unittest.main()
