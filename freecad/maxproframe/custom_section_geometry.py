import Part


def build_custom_section_face(source):
    """
    Validates that source (a Part.Face, Part.Wire, or Sketch/Compound) produces
    exactly one connected material region with valid closed contours and positive area,
    and returns the resulting Part.Face.

    Supports holes and curves via Part::FaceMakerBullseye.
    Ignores construction geometry via the Sketch.Shape path.
    Rejects invalid, open, intersecting, crossing, disconnected, or non-coplanar geometry.
    """
    if source is None:
        raise ValueError("Custom profile source is missing")

    if not hasattr(source, "Shape") or source.Shape is None:
        raise ValueError("Custom profile source has no geometry")

    shape = source.Shape
    if shape.isNull():
        raise ValueError("Custom profile source is empty or contains only construction geometry")

    # Direct prebuilt Part.Face input
    if isinstance(shape, Part.Face):
        if not shape.isValid():
            raise ValueError("Custom profile face is invalid")
        if shape.Area <= 0.0:
            raise ValueError("Custom profile face has zero or negative area")
        if len(shape.Faces) != 1:
            raise ValueError("Custom profile must contain exactly one connected material region, got multiple disconnected regions")
        return shape

    # Restrict source topology to Wire and Sketch multi-wire Compound
    if not isinstance(shape, (Part.Wire, Part.Compound)):
        raise ValueError("Custom profile must be a Face or Sketch")

    if shape.Solids or shape.Shells:
        raise ValueError("Custom profile must be a Face or Sketch")

    # Collect wires (excludes construction geometry via Sketch.Shape path)
    wires = list(shape.Wires)
    if not wires:
        raise ValueError("Custom profile source is empty or contains only construction geometry")

    # Ensure no stray open edges exist outside closed wires
    wire_edges = sum(len(w.Edges) for w in wires)
    if len(shape.Edges) != wire_edges:
        raise ValueError("Custom profile contains open contours; all contours must be closed")

    # Check for open contours
    for w in wires:
        if not w.isClosed():
            raise ValueError("Custom profile contains open contours; all contours must be closed")

    # Check for intersecting/crossing contours between distinct wires
    if len(wires) > 1:
        for i in range(len(wires)):
            for j in range(i + 1, len(wires)):
                sec = wires[i].section(wires[j])
                if not sec.isNull() and (len(sec.Vertexes) > 0 or len(sec.Edges) > 0):
                    raise ValueError("Custom profile contours must not intersect or cross each other")

    # Build face using native Part::FaceMakerBullseye
    try:
        face = Part.makeFace(wires, "Part::FaceMakerBullseye")
    except ValueError as e:
        err_msg = str(e).lower()
        if "coplanar" in err_msg:
            raise ValueError("Custom profile contours are not coplanar")
        if "not closed" in err_msg:
            raise ValueError("Custom profile contains open contours; all contours must be closed")
        raise ValueError(f"Custom profile face creation failed: {e}")
    except Exception as e:
        err_msg = str(e).lower()
        if "coplanar" in err_msg:
            raise ValueError("Custom profile contours are not coplanar")
        raise ValueError(f"Custom profile face creation failed: {e}")

    # Check connected region and face validity
    faces = getattr(face, "Faces", [])
    if len(faces) == 0:
        raise ValueError("Custom profile produces no valid face geometry")
    if len(faces) > 1:
        if len(wires) == 1:
            raise ValueError("Custom profile contours must not self-intersect")
        raise ValueError("Custom profile must contain exactly one connected material region, got multiple disconnected regions")

    single_face = faces[0]
    # Ensure all wire content was consumed into this single face without stray omissions
    if len(single_face.Wires) != len(wires):
        raise ValueError("Custom profile must contain exactly one connected material region, got multiple disconnected regions")

    if not single_face.isValid():
        raise ValueError("Custom profile face is invalid")
    if single_face.Area <= 0.0:
        raise ValueError("Custom profile face has zero or negative area")

    return single_face
