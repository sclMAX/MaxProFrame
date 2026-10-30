"""Helpers that keep PySide wrappers consistent with the lifetime of the Qt objects they wrap."""

import weakref

from PySide import QtWidgets

_pinned = {}


def _invalidate(wrapper):
    try:
        from shiboken6 import invalidate
    except ImportError:
        return
    invalidate(wrapper)


def invalidate_wrapper_on_destroy(widget):
    # A widget built by the UI loader and later deleted by Qt (the task view deletes the panel
    # form when its dialog closes) keeps a registered PySide wrapper: it still looks valid, and a
    # new QObject allocated at the same address resolves to it (SIGSEGV in QWidget::toolTip).
    wrapper = weakref.ref(widget)

    def release(*_):
        stale = wrapper()
        if stale is not None:
            _invalidate(stale)

    widget.destroyed.connect(release)


def keep_alive_until_destroyed(widget):
    """Leave the C++ lifetime of a Python-owned top-level widget to Qt.

    A parentless dialog owned by Python is deleted whenever its last reference disappears, and a
    reference cycle makes that moment the cyclic garbage collector. That can run inside any call
    that is converting Qt objects to Python (``QApplication.topLevelWidgets()``), where the C++
    widget is then deleted behind a list of pointers that was already built (SIGSEGV in
    PySide::getWrapperForQObject). The registry holds the wrapper until Qt emits ``destroyed``
    (``deleteLater``, WA_DeleteOnClose, a deleted parent) and then invalidates it before the
    reference is dropped, so the wrapper never deletes an object that is already gone.
    """
    key = id(widget)
    _pinned[key] = widget

    def release(*_):
        stale = _pinned.pop(key, None)
        if stale is not None:
            _invalidate(stale)

    widget.destroyed.connect(release)
    return widget


def release_layout_item_wrappers(forms):
    # PySide wraps the QWidgetItem/QSpacerItem objects the layouts own, but the wrappers are not
    # QObjects, so they stay registered after Qt deletes the form with the closed task dialog.
    # A later widget allocated at the same address then resolves to the stale wrapper and
    # SIGSEGVs in PySide::getWrapperForQObject. Drop them while the C++ items are still alive.
    for form in forms:
        if form is None:
            continue
        try:
            for layout in form.findChildren(QtWidgets.QLayout):
                for index in range(layout.count()):
                    item = layout.itemAt(index)
                    if item is not None and not isinstance(item, QtWidgets.QLayout):
                        _invalidate(item)
        except RuntimeError:
            continue
