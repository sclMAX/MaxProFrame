"""Font-aware expectations for text elided by Qt."""

try:
    from PySide import QtCore
except ImportError:
    from PySide2 import QtCore


def font_ellipsis(metrics):
    """Return the ellipsis Qt elides with for this font.

    Qt uses "…" when the primary font has the glyph and "..." otherwise
    (for example some Windows fonts), so tests must not assume either.
    """
    probe = "W" * 40
    elided = metrics.elidedText(probe, QtCore.Qt.ElideRight, metrics.horizontalAdvance("W" * 10))
    return "…" if elided.endswith("…") else "..."
