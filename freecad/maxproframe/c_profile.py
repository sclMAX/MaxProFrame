import math

try:
    import Part
    from FreeCAD import Vector as vec
except ImportError:
    Part = None
    vec = None


def validate_c_dimensions(height, width, thickness, lip_length, radius=None, make_fillet=False):
    """
    Validates dimensions for a lipped C profile.
    Raises ValueError with unambiguous message on degenerate or impossible inputs.
    Does not clamp or silently modify dimensions.
    """
    h = float(height)
    w = float(width)
    t = float(thickness)

    if lip_length is None:
        raise ValueError("Lip length (lip_length) must be specified for C profile.")
    lip = float(lip_length)

    if h <= 0:
        raise ValueError(f"Height must be positive, got {h}")
    if w <= 0:
        raise ValueError(f"Width must be positive, got {w}")
    if t <= 0:
        raise ValueError(f"Thickness must be positive, got {t}")
    if lip <= 0:
        raise ValueError(f"Lip length must be positive, got {lip}")

    if w <= 2 * t:
        raise ValueError(f"Profile width ({w}) must be greater than 2 * thickness ({2 * t})")
    if lip <= t:
        raise ValueError(f"Lip length ({lip}) must be greater than thickness ({t})")
    if h <= 2 * lip:
        raise ValueError(f"Profile height ({h}) must be greater than 2 * lip length ({2 * lip}) to leave open channel")

    if make_fillet:
        if radius is None:
            raise ValueError("Exterior radius must be specified when make_fillet is True for C profile.")
        r_ext = float(radius)
        if r_ext <= 0:
            raise ValueError(f"Exterior radius must be positive, got {r_ext}")
        if r_ext <= t:
            raise ValueError(
                f"Exterior radius ({r_ext}) must be greater than thickness ({t}) so interior radius is positive"
            )
        if r_ext > lip:
            raise ValueError(f"Exterior radius ({r_ext}) cannot exceed lip length ({lip})")
        if 2 * r_ext > w:
            raise ValueError(f"2 * exterior radius ({2 * r_ext}) cannot exceed width ({w})")
        if 2 * r_ext > h:
            raise ValueError(f"2 * exterior radius ({2 * r_ext}) cannot exceed height ({h})")

    return True


def calculate_c_area(height, width, thickness, lip_length, radius=None, make_fillet=False):
    """
    Calculates cross-sectional area (mm2) for a lipped C profile.
    Plain: e * (H + 2*B + 2*L - 4*e).
    Filleted: Plain area - (4 - pi) * (R_ext^2 - (R_ext - e)^2).
    """
    validate_c_dimensions(height, width, thickness, lip_length, radius, make_fillet)

    h = float(height)
    w = float(width)
    t = float(thickness)
    lip = float(lip_length)

    plain_area = t * (h + 2.0 * w + 2.0 * lip - 4.0 * t)

    if not make_fillet:
        return plain_area

    r_ext = float(radius)
    r_int = r_ext - t
    fillet_delta = (4.0 - math.pi) * (r_ext**2 - r_int**2)
    return plain_area - fillet_delta


def build_c_face(width, height, thickness, lip_length, radius=0.0, make_fillet=False, w=0.0, h=0.0):
    """
    Builds a 2D FreeCAD Part.Face for the C profile cross section.
    Convention: positive-X opening (web on left, flanges top and bottom, inward lips on right).
    Spans [w, w + width] in X and [h, h + height] in Y.
    """
    validate_c_dimensions(height, width, thickness, lip_length, radius, make_fillet)

    W = float(width)
    H = float(height)
    TW = float(thickness)
    L = float(lip_length)

    if not make_fillet:
        points = [
            vec(W + w, h + L, 0),
            vec(W + w, h, 0),
            vec(w, h, 0),
            vec(w, H + h, 0),
            vec(W + w, H + h, 0),
            vec(W + w, H + h - L, 0),
            vec(W + w - TW, H + h - L, 0),
            vec(W + w - TW, H + h - TW, 0),
            vec(w + TW, H + h - TW, 0),
            vec(w + TW, h + TW, 0),
            vec(W + w - TW, h + TW, 0),
            vec(W + w - TW, h + L, 0),
            vec(W + w, h + L, 0),
        ]
        wire = Part.makePolygon(points)
        return Part.Face(wire)

    R = float(radius)
    r = R - TW
    d = vec(0, 0, 1)

    c1 = vec(W + w - R, h + R, 0)
    c2 = vec(w + R, h + R, 0)
    c3 = vec(w + R, H + h - R, 0)
    c4 = vec(W + w - R, H + h - R, 0)

    edges = []

    # 1. Outer bottom lip (downward to arc)
    p_lip_b_out_tip = vec(W + w, h + L, 0)
    p_lip_b_out_arc = vec(W + w, h + R, 0)
    if L > R:
        edges.append(Part.makeLine(p_lip_b_out_tip, p_lip_b_out_arc))

    # Outer corner 1 (bottom lip / bottom flange)
    edges.append(Part.makeCircle(R, c1, d, 270, 360))

    # Outer bottom flange (leftward to web corner)
    p_flange_b_out_arc = vec(W + w - R, h, 0)
    p_flange_b_out_web = vec(w + R, h, 0)
    if W > 2 * R:
        edges.append(Part.makeLine(p_flange_b_out_arc, p_flange_b_out_web))

    # Outer corner 2 (bottom flange / web)
    edges.append(Part.makeCircle(R, c2, d, 180, 270))

    # Outer web (upward to top flange corner)
    p_web_out_b = vec(w, h + R, 0)
    p_web_out_t = vec(w, H + h - R, 0)
    if H > 2 * R:
        edges.append(Part.makeLine(p_web_out_b, p_web_out_t))

    # Outer corner 3 (web / top flange)
    edges.append(Part.makeCircle(R, c3, d, 90, 180))

    # Outer top flange (rightward to top lip corner)
    p_flange_t_out_web = vec(w + R, H + h, 0)
    p_flange_t_out_lip = vec(W + w - R, H + h, 0)
    if W > 2 * R:
        edges.append(Part.makeLine(p_flange_t_out_web, p_flange_t_out_lip))

    # Outer corner 4 (top flange / top lip)
    edges.append(Part.makeCircle(R, c4, d, 0, 90))

    # Outer top lip (downward to lip tip)
    p_lip_t_out_arc = vec(W + w, H + h - R, 0)
    p_lip_t_out_tip = vec(W + w, H + h - L, 0)
    if L > R:
        edges.append(Part.makeLine(p_lip_t_out_arc, p_lip_t_out_tip))

    # Top lip tip (flat inward edge of thickness TW)
    p_lip_t_in_tip = vec(W + w - TW, H + h - L, 0)
    edges.append(Part.makeLine(p_lip_t_out_tip, p_lip_t_in_tip))

    # Inner top lip (upward to inner arc)
    p_lip_t_in_arc = vec(W + w - TW, H + h - R, 0)
    if L > R:
        edges.append(Part.makeLine(p_lip_t_in_tip, p_lip_t_in_arc))

    # Inner corner 4 (concentric with c4, radius r)
    edges.append(Part.makeCircle(r, c4, d, 0, 90))

    # Inner top flange (leftward to web inner arc)
    p_flange_t_in_lip = vec(W + w - R, H + h - TW, 0)
    p_flange_t_in_web = vec(w + R, H + h - TW, 0)
    if W > 2 * R:
        edges.append(Part.makeLine(p_flange_t_in_lip, p_flange_t_in_web))

    # Inner corner 3 (concentric with c3, radius r)
    edges.append(Part.makeCircle(r, c3, d, 90, 180))

    # Inner web (downward to bottom flange inner arc)
    p_web_in_t = vec(w + TW, H + h - R, 0)
    p_web_in_b = vec(w + TW, h + R, 0)
    if H > 2 * R:
        edges.append(Part.makeLine(p_web_in_t, p_web_in_b))

    # Inner corner 2 (concentric with c2, radius r)
    edges.append(Part.makeCircle(r, c2, d, 180, 270))

    # Inner bottom flange (rightward to lip inner arc)
    p_flange_b_in_web = vec(w + R, h + TW, 0)
    p_flange_b_in_lip = vec(W + w - R, h + TW, 0)
    if W > 2 * R:
        edges.append(Part.makeLine(p_flange_b_in_web, p_flange_b_in_lip))

    # Inner corner 1 (concentric with c1, radius r)
    edges.append(Part.makeCircle(r, c1, d, 270, 360))

    # Inner bottom lip (upward to lip tip)
    p_lip_b_in_arc = vec(W + w - TW, h + R, 0)
    p_lip_b_in_tip = vec(W + w - TW, h + L, 0)
    if L > R:
        edges.append(Part.makeLine(p_lip_b_in_arc, p_lip_b_in_tip))

    # Bottom lip tip (flat outward edge of thickness TW)
    edges.append(Part.makeLine(p_lip_b_in_tip, p_lip_b_out_tip))

    wire = Part.Wire(edges)
    return Part.Face(wire)
