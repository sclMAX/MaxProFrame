"""Modeless capture controls for user-owned sketches; never owns a document."""

import FreeCAD as App
import FreeCADGui as Gui

from freecad.maxproframe.dxf_section_dialog import DXFSectionReview, QtWidgets
from freecad.maxproframe.ff_tools import translate


class SketchComboBox(QtWidgets.QComboBox):
    def findData(self, data, *args):
        # Tuple-valued Python user data is not compared reliably by QVariant.
        for index in range(self.count()):
            if self.itemData(index) == data:
                return index
        return -1


class SketchSectionReview(DXFSectionReview):
    def __init__(self, library_name, material, density, add_callback):
        # Build controls without requiring or creating a source sketch.
        self._key = None
        self._observing = False
        self._syncing = False
        self._manual_code = False
        self._cameras = {}
        self._previous_doc = App.ActiveDocument.Name if App.ActiveDocument else None
        # DXF controls need a source only during construction.
        from types import SimpleNamespace
        super().__init__(SimpleNamespace(Document=SimpleNamespace(Name="")),
                         library_name, material, density, add_callback)
        self.add_callback = lambda code: self._add(add_callback, code)
        self.sketch = None
        self.setWindowTitle(translate("frameforge", "Capture Section"))
        self.combo_sketch = SketchComboBox()
        self.layout().insertWidget(1, self.combo_sketch)
        # Replace the DXF-specific instruction, not its publication controls.
        self.layout().itemAt(2).widget().setText(translate(
            "frameforge", "Select a sketch in the list or click it in FreeCAD. Adding stages an independent copy; Save Changes publishes it."))
        # Programmatic edits also count, except our own suggestions.
        self.le_code.textChanged.connect(self._code_edited)
        self.combo_sketch.currentIndexChanged.connect(self._combo_changed)
        self.finished.connect(self._finish)
        self._refresh_candidates()
        Gui.Selection.addObserver(self)
        self._observing = True
        self._selection_changed()

    def _code_edited(self, *_):
        if not self._syncing:
            self._manual_code = True

    def _resolve(self, key):
        try:
            doc = App.listDocuments().get(key[0]) if key else None
            obj = doc.getObject(key[1]) if doc else None
            return obj if obj and obj.isDerivedFrom("Sketcher::SketchObject") else None
        except Exception:
            return None

    def _refresh_candidates(self):
        keys = []
        for doc in App.listDocuments().values():
            for obj in doc.Objects:
                if obj.isDerivedFrom("Sketcher::SketchObject"):
                    keys.append((doc.Name, obj.Name))
        current = [self.combo_sketch.itemData(i) for i in range(1, self.combo_sketch.count())]
        if current == keys:
            return
        self.combo_sketch.blockSignals(True)
        self.combo_sketch.clear()
        self.combo_sketch.addItem(translate("frameforge", "Select a sketch"), None)
        for key in keys:
            self.combo_sketch.addItem("%s#%s" % key, key)
        self.combo_sketch.setCurrentIndex(max(0, self.combo_sketch.findData(self._key)))
        self.combo_sketch.blockSignals(False)

    def _set_source(self, key):
        obj = self._resolve(key)
        self.sketch = obj
        self._key = key if obj else None
        self.document_name = key[0] if obj else ""
        self._syncing = True
        try:
            self.combo_sketch.setCurrentIndex(max(0, self.combo_sketch.findData(self._key)))
            if not self._manual_code:
                self.le_code.setText(obj.Label if obj else "")
            self.btn_add.setEnabled(obj is not None)
        finally:
            self._syncing = False
        if obj:
            try:
                view = Gui.getDocument(key[0]).activeView()
                if key[0] not in self._cameras:
                    self._cameras[key[0]] = view.getCamera()
                App.setActiveDocument(key[0])
                Gui.setActiveDocument(key[0])
                view.viewTop()
                view.fitAll()
            except Exception:
                pass

    def _combo_changed(self, *_):
        if self._syncing:
            return
        key = self.combo_sketch.currentData()
        self._set_source(key)
        self._syncing = True
        try:
            Gui.Selection.clearSelection()
            if self.sketch:
                Gui.Selection.addSelection(*key)
        finally:
            self._syncing = False

    def _selection_changed(self):
        if self._syncing or not self._observing:
            return
        try:
            selected = Gui.Selection.getSelection()
            key = (selected[0].Document.Name, selected[0].Name) if len(selected) == 1 else None
            self._refresh_candidates()
            self._set_source(key)
        except Exception:
            self._set_source(None)

    def addSelection(self, document, obj, *args):
        # FreeCAD can notify observers before getSelection reflects the new edge.
        if not self._syncing and self._observing:
            try:
                self._refresh_candidates()
                self._set_source((document, obj))
            except Exception:
                self._set_source(None)

    def removeSelection(self, *args):
        self._selection_changed()

    def clearSelection(self, *args):
        self._selection_changed()

    def setSelection(self, *args):
        self._selection_changed()

    def check_document(self):
        try:
            self._refresh_candidates()
            if self._key and self._resolve(self._key) is None:
                self._set_source(None)
        except Exception:
            self._set_source(None)

    def _add(self, callback, code):
        # Asset serialization activates a temporary document and clears selection.
        # Those events must not replace the source while the Add callback runs.
        key = self._key
        self._syncing = True
        try:
            callback(code)
        finally:
            self._syncing = False
            if self._observing and self._resolve(key):
                self._syncing = True
                try:
                    Gui.Selection.clearSelection()
                    Gui.Selection.addSelection(*key)
                finally:
                    self._syncing = False

    def _finish(self, *_):
        self.timer.stop()
        if self._observing:
            self._observing = False
            try:
                Gui.Selection.removeObserver(self)
            except Exception:
                pass
        for name, camera in self._cameras.items():
            try:
                Gui.getDocument(name).activeView().setCamera(camera)
            except Exception:
                pass
        if self._previous_doc in App.listDocuments():
            try:
                App.setActiveDocument(self._previous_doc)
                Gui.setActiveDocument(self._previous_doc)
            except Exception:
                pass
