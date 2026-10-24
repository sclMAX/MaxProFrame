# Capture a sketch section

In a writable folder library, choose **Capture Section**. The library hides while a modeless capture window stays beside FreeCAD.

Select an open sketch in the list, or click its geometry in the viewport or its entry in the tree. Clicking an edge selects its owning sketch. A single selected sketch is preselected; no selection or multiple selected objects requires an explicit choice. Other objects cannot be captured.

Enter a unique, non-empty **Code** (initially the sketch label), and optionally a description. Your edited code is retained when changing sketches. **Add as Custom** validates the current sketch and stages an independent asset, selecting its new Custom row. Use **Save Changes** in the library to publish it.

**Cancel** restores the library without staging anything. Capture never closes source documents or modifies source geometry or visibility. Closing the library or switching libraries cancels capture and disconnects mouse selection. Deleted sketches cannot be added.
