"""Shared set-up for the End Miter panel tests: GUI language and the remembered preview check box."""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

from freecad.maxproframe.create_end_miter_tool import AUTO_PREVIEW_PARAM
from freecad.maxproframe.ff_tools import TRANSLATIONSPATH, get_param_group


def use_language(test, language, qt_locale):
    """Switch the GUI language and the Qt default locale for one test, restoring both afterwards."""
    prefs = App.ParamGet("User parameter:BaseApp/Preferences/General")
    previous, locale, qt_default = prefs.GetString("Language", ""), Gui.getLocale(), QtCore.QLocale()

    def restore():
        prefs.SetString("Language", previous)
        Gui.setLocale(locale)
        Gui.updateLocale()
        QtCore.QLocale.setDefault(qt_default)

    test.addCleanup(restore)
    Gui.addLanguagePath(TRANSLATIONSPATH)
    prefs.SetString("Language", language)
    Gui.setLocale(language)
    Gui.updateLocale()
    QtCore.QLocale.setDefault(QtCore.QLocale(qt_locale))


def keep_auto_preview(test, value=None):
    """Restore the remembered check box state after ``test``; ``value`` None starts from the default."""
    param = get_param_group(writable=True)
    stored = AUTO_PREVIEW_PARAM in param.GetBools()
    previous = param.GetBool(AUTO_PREVIEW_PARAM, True)

    def restore():
        if stored:
            param.SetBool(AUTO_PREVIEW_PARAM, previous)
        else:
            param.RemBool(AUTO_PREVIEW_PARAM)

    test.addCleanup(restore)
    if value is None:
        param.RemBool(AUTO_PREVIEW_PARAM)
    else:
        param.SetBool(AUTO_PREVIEW_PARAM, value)
