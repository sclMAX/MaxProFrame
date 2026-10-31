"""Bundled, translated user guide shown inside FreeCAD, with topic deep links."""

import os

try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

from freecad.maxproframe.ff_tools import RESSOURCESPATH, translate

HELP_PATH = os.path.join(RESSOURCESPATH, "help")
GUIDE_FILE = "library-manager.md"


def topic_headings():
    """Map each topic to its guide heading in the current language.

    The guides are matched by heading text, so each translated guide heading
    must equal the catalog translation of its English source.
    """
    return {
        "overview": translate("frameforge", "Profile Library Manager"),
        "libraries": translate("frameforge", "Libraries"),
        "new-library": translate("frameforge", "Create a library"),
        "duplicate": translate("frameforge", "Duplicate a system library"),
        "share": translate("frameforge", "Share a library"),
        "families": translate("frameforge", "Families"),
        "sizes": translate("frameforge", "Profiles and sizes"),
        "custom-profiles": translate("frameforge", "Custom profiles"),
        "saving": translate("frameforge", "Save your changes"),
        "use": translate("frameforge", "Use your profiles in a model"),
    }


def guide_path():
    """Return the guide for the loaded catalog language, falling back to English."""
    path = os.path.join(HELP_PATH, os.path.basename(translate("frameforge", "library-manager.md")))
    return path if os.path.isfile(path) else os.path.join(HELP_PATH, GUIDE_FILE)


class HelpDialog(QtWidgets.QDialog):
    """Non-modal window showing the user guide."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            (self.windowFlags() & ~QtCore.Qt.WindowType_Mask)
            | QtCore.Qt.Window
            | QtCore.Qt.WindowMaximizeButtonHint
            | QtCore.Qt.WindowMinimizeButtonHint
        )
        self.setModal(False)
        self.setWindowTitle(translate("frameforge", "MaxProFrame Help"))
        self.resize(640, 720)

        layout = QtWidgets.QVBoxLayout(self)
        self.browser = QtWidgets.QTextBrowser()
        self.browser.setReadOnly(True)
        self.browser.setOpenExternalLinks(True)
        self.browser.setSearchPaths([HELP_PATH])
        layout.addWidget(self.browser)

        with open(guide_path(), encoding="utf-8") as guide:
            self.browser.setMarkdown(guide.read())

    def show_topic(self, topic):
        """Scroll the topic heading to the top; an unknown topic shows the start of the guide."""
        heading = topic_headings().get(topic)
        document = self.browser.document()
        # Room below the last section lets every heading reach the top of the view.
        frame_format = document.rootFrame().frameFormat()
        frame_format.setBottomMargin(self.browser.viewport().height())
        document.rootFrame().setFrameFormat(frame_format)
        top = 0
        block = document.begin()
        while heading and block.isValid():
            if block.blockFormat().headingLevel() and block.text() == heading:
                top = document.documentLayout().blockBoundingRect(block).top()
                break
            block = block.next()
        self.browser.verticalScrollBar().setValue(round(top))


class _HelpKeyFilter(QtCore.QObject):
    """Run a callback for F1 pressed anywhere in a window."""

    def __init__(self, window, callback):
        super().__init__(window)
        self._callback = callback

    def eventFilter(self, watched, event):
        # Children pass unhandled key presses up to the window; a QShortcut would
        # miss F1 while a line edit has focus.
        if event.type() == QtCore.QEvent.KeyPress and event.matches(QtGui.QKeySequence.HelpContents):
            self._callback()
            return True
        return False


def install_help_shortcut(window, callback):
    """Bind F1 (the platform help key) anywhere in ``window`` to ``callback``."""
    key_filter = _HelpKeyFilter(window, callback)
    window.installEventFilter(key_filter)
    return key_filter


def show_help(parent, topic):
    """Open the guide at ``topic``, reusing one help window per parent."""
    dialog = next(iter(parent.findChildren(HelpDialog, options=QtCore.Qt.FindDirectChildrenOnly)), None)
    if dialog is None:
        dialog = HelpDialog(parent)
        # A help window must not outlive the dialog that opened it.
        if isinstance(parent, QtWidgets.QDialog):
            parent.finished.connect(dialog.close)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    dialog.show_topic(topic)
    return dialog
