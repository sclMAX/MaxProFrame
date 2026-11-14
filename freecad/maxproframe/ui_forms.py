"""Loading of the task panel forms made in Qt Designer."""

import FreeCADGui as Gui


def load_form(ui_file):
    """The form of ``ui_file``, loaded like ``Gui.PySideUic.loadUi`` but with texts only the panel sets.

    Left on, the loader puts back the texts of the form file on every LanguageChange (a language applied in the
    Preferences, or a switch delivered late): the panel would show its English form texts over the translated ones
    and over what it set at runtime (a target, a hint, an edit title). The panels translate their forms themselves.
    """
    loader = Gui.UiLoader()
    loader.setLanguageChangeEnabled(False)
    return loader.load(ui_file)
