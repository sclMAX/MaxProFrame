"""The faces an Interlock links stay named right, without FreeCAD reporting them missing.

A Tabs Interlock links the crossbar wall and the rail face it was made on (``CrossbarFace``, ``RailFace``) and its
pieces link the same face of the piece under them (``baseObject``); the fingers of an End Miter corner link the inner
wall of each tube (``FaceA``, ``FaceB``). Each one is found again on the plane it remembers. When the piece under is
itself an Interlock piece whose faces FreeCAD cannot follow (fingers flipped or recounted, tabs recounted: the piece is
fused and refined again), the report view said "<piece>.baseObject missing element reference" and
"<Interlock>.RailFace missing element reference" for every piece and Interlock stacked on it. The piece under now names
the face found again in those links as its shape changes: nothing is reported, the links name the face on the plane
they remember, and nothing is recomputed twice or left touched.
"""

import unittest

import FreeCAD as App
import Part
from PySide import QtGui
from test_custom_profile_link_scope import report_view
from test_miter_finger_interlock import MiterFingersFixture
from test_tab_interlock import TabInterlockFixture

from freecad.maxproframe.create_extend_cut_tool import make_extend_cut_profile
from freecad.maxproframe.interlock import is_miter_interlock
from freecad.maxproframe.miter_finger_interlock import miter_pieces
from freecad.maxproframe.tab_interlock import found_face, make_tab_interlock, tab_pieces

X, Y = App.Vector(1, 0, 0), App.Vector(0, 1, 0)
MISSING = "missing element reference"
VOLUME_TOLERANCE = 1e-3


def reported(action):
    """What the Report view shows while ``action`` runs."""
    view = report_view()
    QtGui.QApplication.processEvents()
    before = len(view.toPlainText())
    action()
    QtGui.QApplication.processEvents()
    return view.toPlainText()[before:]


class Recomputed:
    """The names of the objects of a document recomputed while it observes."""

    def __init__(self):
        self.names = []

    def slotObjectRecomputed(self, obj):
        self.names.append(obj.Name)


class FaceLinksMixin:
    def face_links(self, interlock):
        """[(link property, piece, face name, (point, normal, anchor), piece built on it)] of ``interlock``."""
        if is_miter_interlock(interlock):
            sides = [
                (f"Face{side}", tuple(getattr(interlock, f"{name}{side}") for name in ("Point", "Normal", "Anchor")))
                for side in ("A", "B")
            ]
            built = miter_pieces(interlock)
        else:
            sides = [
                (f"{side}Face", tuple(getattr(interlock, f"{side}{name}") for name in ("Point", "Normal", "Anchor")))
                for side in ("Crossbar", "Rail")
            ]
            built = tab_pieces(interlock)
        links = []
        for (prop, snapshot), piece in zip(sides, built):
            target, subs = getattr(interlock, prop)
            links.append((prop, target, subs[0] if subs else "", snapshot, piece))
        return links

    def assertLinksRight(self, interlock):
        """Each face link of ``interlock`` and of the piece built on it names the face on the plane it remembers."""
        for prop, target, sub, snapshot, piece in self.face_links(interlock):
            with self.subTest(interlock=interlock.Name, link=prop):
                found = found_face(target, sub, *snapshot)
                self.assertIsNotNone(found)
                self.assertEqual(found[0], sub)
                self.assertEqual((target, [sub]), (piece.baseObject[0], list(piece.baseObject[1])))

    def assertQuietRecompute(self, change, interlocks):
        """``change`` then a recompute: nothing reported missing, the links right, every object recomputed once at
        most, nothing left to recompute."""
        observer = Recomputed()
        App.addDocumentObserver(observer)
        try:

            def act():
                change()
                self.doc.recompute()

            report = reported(act)
        finally:
            App.removeDocumentObserver(observer)
        self.assertNotIn(MISSING, report)
        self.assertNotIn("still touched", report)
        for interlock in interlocks:
            self.assertLinksRight(interlock)
        self.assertEqual(sorted(set(observer.names)), sorted(observer.names))
        self.assertEqual([], [obj.Name for obj in self.doc.Objects if "Touched" in obj.State])
        self.assertEqual([], [obj.Name for obj in self.doc.Objects if obj.getStatusString() != "Valid"])
        self.assertEqual(0, self.doc.recompute())


class MiterFingersUnderTabsTest(FaceLinksMixin, MiterFingersFixture):
    """The user's corner: two Tabs Interlocks whose slots go through the inner wall of a tube with fingers."""

    @staticmethod
    def inner_wall(obj):
        """Name of the largest face of ``obj`` on the inner wall of tube B (x = -40, looking along -X)."""
        faces = [
            (face.Area, f"Face{index}")
            for index, face in enumerate(obj.Shape.Faces, 1)
            if isinstance(face.Surface, Part.Plane)
            and face.normalAt(0, 0).getAngle(-X) < 1e-6
            and abs(face.CenterOfMass.x + 40.0) < 1e-6
        ]
        return max(faces)[1]

    def setUp(self):
        super().setUp()
        self.corner, self.fingers_interlock, _, piece_b = self.fingers()
        self.piece_b = piece_b
        self.tabs = []
        rail = piece_b
        for y, label in ((150.0, "Crossbar"), (250.0, "Crossbar2")):
            _, trim = self.crossbar(self.corner.b, edge=((-400, y, 0), (-100, y, 0)), towards=-X, label=label)
            interlock = make_tab_interlock(trim, self.wall(trim, Y), rail, self.inner_wall(rail))
            self.doc.recompute()
            self.tabs.append(interlock)
            rail = tab_pieces(interlock)[1]
        self.slots = rail
        self.removed = piece_b.Shape.Volume - rail.Shape.Volume
        self.assertGreater(self.removed, 1.0)
        for interlock in self.tabs:
            self.assertLinksRight(interlock)

    def assertSlotsKept(self):
        self.assertAlmostEqual(
            self.removed, self.piece_b.Shape.Volume - self.slots.Shape.Volume, delta=VOLUME_TOLERANCE
        )

    def test_flipping_the_fingers_reports_no_missing_face(self):
        interlocks = [self.fingers_interlock, *self.tabs]
        for flip in (True, False, True):
            with self.subTest(flip=flip):
                self.assertQuietRecompute(lambda flip=flip: setattr(self.fingers_interlock, "Flip", flip), interlocks)
                self.assertSlotsKept()

    def test_changing_the_count_of_the_fingers_reports_no_missing_face(self):
        interlocks = [self.fingers_interlock, *self.tabs]
        for count in (2, 4, 3):
            with self.subTest(count=count):
                self.assertQuietRecompute(
                    lambda count=count: setattr(self.fingers_interlock, "Count", count), interlocks
                )
                self.assertSlotsKept()

    def test_editing_the_end_miter_gap_reports_no_missing_face(self):
        def gap(value):
            for trim in (self.corner.miter_a, self.corner.miter_b):
                trim.MiterGap = value

        for value in (0.5, 0.0):
            with self.subTest(gap=value):
                self.assertQuietRecompute(lambda value=value: gap(value), [self.fingers_interlock, *self.tabs])
                self.assertSlotsKept()


class TabsFaceLinksTest(FaceLinksMixin, TabInterlockFixture):
    def test_recounting_the_tabs_under_tabs_at_the_other_end_reports_no_missing_face(self):
        # Tabs at both ends of a crossbar: the second Interlock links the wall of the first one's tabs piece.
        near_rail = self.rail(((0, -300, 0), (0, 300, 0)), "Left")
        far_rail = self.rail()
        _, first_trim = self.crossbar(near_rail, ((60, 0, 0), (340, 0, 0)), X)
        trim = make_extend_cut_profile(first_trim, (far_rail, (self.face_towards(far_rail, -X),)))
        self.doc.recompute()
        far = make_tab_interlock(trim, self.wall(trim, Y), far_rail, self.face_towards(far_rail, -X))
        self.doc.recompute()
        far_tabs, _ = tab_pieces(far)
        near = make_tab_interlock(far_tabs, self.wall(far_tabs, Y), near_rail, self.face_towards(near_rail, X))
        self.doc.recompute()
        near_tabs, _ = tab_pieces(near)
        self.assertLinksRight(near)
        added = near_tabs.Shape.Volume - far_tabs.Shape.Volume

        for count in (2, 4, 3):
            with self.subTest(count=count):
                self.assertQuietRecompute(lambda count=count: setattr(far, "Count", count), [far, near])
                # The near tabs still add the same tabs on the far tabs piece.
                self.assertAlmostEqual(added, near_tabs.Shape.Volume - far_tabs.Shape.Volume, delta=VOLUME_TOLERANCE)

    def test_editing_a_trim_under_a_slots_piece_reports_no_missing_face(self):
        target = self.tube(((300, 400, 0), (500, 400, 0)), "Target")
        rail = self.rail(((400, -300, 0), (400, 200, 0)))
        rail_trim = make_extend_cut_profile(rail, (target, (self.face_towards(target, -Y),)))
        self.doc.recompute()
        _, trim = self.crossbar(rail)
        interlock = make_tab_interlock(trim, self.wall(trim, Y), rail_trim, self.face_towards(rail_trim, -X))
        self.doc.recompute()
        _, slots = tab_pieces(interlock)
        removed = rail_trim.Shape.Volume - slots.Shape.Volume

        sketch = target.AttachmentSupport[0][0]
        for name, change in (
            ("gap", lambda: setattr(rail_trim, "TrimGap", 2.0)),
            ("target moved", lambda: setattr(sketch, "Placement", App.Placement(App.Vector(0, 30, 0), App.Rotation()))),
        ):
            with self.subTest(name):
                self.assertQuietRecompute(change, [interlock])
                self.assertAlmostEqual(removed, rail_trim.Shape.Volume - slots.Shape.Volume, delta=VOLUME_TOLERANCE)


if __name__ == "__main__":
    unittest.main()
