"""Independent S1-S4 shared-contract probes."""

import hashlib
import unittest
from unittest.mock import patch

from PySide import QtCore, QtGui, QtWidgets
from test_unified_custom_profile_editor import TestUnifiedCustomProfileEditor as Fixture

from freecad.maxproframe.custom_profile_cards import render_custom_section_thumbnail


class TestContracts(unittest.TestCase):
    def setUp(self):
        self.f = Fixture("runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.d = self.f.dialog
        self.c = self.f.card

    def hashes(self):
        return {p: hashlib.sha256(b).hexdigest() for p, b in self.f.files().items()}

    def test_raw_signals_table_guards_and_style_are_storage_neutral(self):
        before = self.hashes()
        for field in (self.c.code_edit, self.c.description_edit, self.c.weight_edit):
            seen = []
            field.textChanged.connect(seen.append)
            old = field.text()
            field.setText(old)
            self.assertEqual(seen, [])
            field.blockSignals(True)
            field.setText(old + "!")
            field.setText(old)
            field.blockSignals(False)
            self.assertEqual(seen, [])
        code = "Profile <b>& Ñ"
        self.d.table_sizes.item(0, 0).setText(code)
        self.d.table_sizes.item(0, 7).setText("7.125")
        item = self.d.table_sizes.item(0, 0)
        props = dict(item.data(QtCore.Qt.UserRole))
        props["Description"] = "Line one\nLine two & <tag>"
        item.setData(QtCore.Qt.UserRole, props)
        self.assertEqual(self.c.code_edit.text(), code)
        self.assertEqual(self.c.weight_edit.text(), "7.125")
        self.assertEqual(self.c.description_edit.text(), props["Description"])
        self.d.cards_view.sync_to_table()
        for ink in ("#e3dab2", "#253147"):
            self.d.setStyleSheet("QLabel { color: %s; background: #888888; }" % ink)
            self.d.ensurePolished()
            self.c.grab()
            self.assertEqual(self.c.code_edit.text(), code)
            self.assertEqual(self.c.weight_edit.toolTip(), "7.125 kg/m")
        self.assertEqual(item.data(QtCore.Qt.UserRole)["vendor"], "preserve")
        self.assertEqual(self.hashes(), before)

    def test_actual_pencil_mouse_dispatch_opens_and_selects_once(self):
        self.d.show()
        self.d.layout().activate()
        selected = []
        original = self.d.cards_view.select_card

        def select(row):
            selected.append(row)
            original(row)

        with patch.object(self.d.cards_view, "select_card", side_effect=select), patch(
            "freecad.maxproframe.custom_profile_editor.CustomProfileEditor.run"
        ) as run:
            button = self.c.btn_edit_properties
            for kind, buttons in (
                (QtCore.QEvent.MouseButtonPress, QtCore.Qt.LeftButton),
                (QtCore.QEvent.MouseButtonRelease, QtCore.Qt.NoButton),
            ):
                QtWidgets.QApplication.sendEvent(
                    button,
                    QtGui.QMouseEvent(
                        kind,
                        QtCore.QPointF(button.rect().center()),
                        QtCore.Qt.LeftButton,
                        buttons,
                        QtCore.Qt.NoModifier,
                    ),
                )
            self.assertEqual(run.call_count, 1)
            self.assertEqual(selected, [0])
            self.c.set_editable(False)
            button.click()
            self.assertEqual(run.call_count, 1)
            self.assertEqual(selected, [0])

    def test_cached_geometry_not_recolored_or_invalidated_by_receivers(self):
        cache = self.d.cards_view._thumbnail_cache
        props = self.d.table_sizes.item(0, 0).data(QtCore.Qt.UserRole)
        root = self.d.current_lib_meta["folder_path"]

        def retrieve():
            return render_custom_section_thumbnail(root, props["asset_path"], "Section", cache=cache)

        mask = retrieve()
        original = mask.toImage()
        keys = set(cache)
        colors = []
        for ink in ("#e3dab2", "#253147"):
            self.c.thumbnail_label.setStyleSheet("QLabel { color: %s; background: #888888; }" % ink)
            self.c.thumbnail_label.ensurePolished()
            self.c.update_thumbnail(retrieve())
            image = self.c.thumbnail_label.grab().toImage()
            safe = self.c.thumbnail_label.contentsRect()
            ratio = image.devicePixelRatio()
            colors.append(
                image.pixelColor(round(safe.center().x() * ratio), round(safe.center().y() * ratio)).name()
            )
            self.assertEqual(retrieve().toImage(), original)
            self.assertEqual(set(cache), keys)
        self.assertEqual(colors, ["#e3dab2", "#253147"])
