import math
import os
import re
from collections import Counter, defaultdict

import FreeCAD as App
import FreeCADGui as Gui

from freecad.maxproframe._utils import (
    get_profile_from_extrudedcutout,
    get_profile_from_trimmedbody,
    is_extrudedcutout,
    is_trimmedbody,
)
from freecad.maxproframe.ff_tools import ICONPATH, PROFILEIMAGES_PATH, PROFILESPATH, UIPATH, translate

# The optional count populate_ids appends to an ID: "12 x3".
COUNT_SUFFIX = re.compile(r" x[1-9][0-9]*\Z")
# Relative tolerance on the measures of two finished solids that are the same piece. Float noise between copies
# of one piece, moved or turned, is about 1e-14; a hole moved 0.05 mm along a 400 mm tube changes them by 1e-6.
SHAPE_TOLERANCE = 1e-6
# Numbering mode of the profiles and of the links for each numbering type.
NUMBERING_MODES = {
    "all_numbers": ("number", "number"),
    "all_letters": ("letter", "letter"),
    "number_for_profiles_letters_for_links": ("number", "letter"),
    "letters_for_profiles_number_for_links": ("letter", "number"),
}


def ambiguous_prefix(prefix, mode):
    """True when ``prefix`` ends in a character of the ``mode`` numbering: "P" + "A" reads back as "PA"."""
    return bool(re.search(r"[A-Za-z]\Z" if mode == "letter" else r"[0-9]\Z", prefix))


def letters_to_int(s: str) -> int:
    """
    'A' -> 1
    'Z' -> 26
    'AA' -> 27
    """
    s = s.strip().upper()
    value = 0
    for c in s:
        if not ("A" <= c <= "Z"):
            raise ValueError(f"Invalid letter ID: {s}")
        value = value * 26 + (ord(c) - ord("A") + 1)
    return value


def int_to_letters(n: int) -> str:
    """
    1 -> 'A'
    26 -> 'Z'
    27 -> 'AA'
    """
    if n <= 0:
        raise ValueError("Letter IDs must be >= 1")

    result = []
    while n > 0:
        n -= 1
        n, r = divmod(n, 26)
        result.append(chr(ord("A") + r))
    return "".join(reversed(result))


def number_str_to_int(s: str) -> int:
    return int(s)


def int_to_number_str(n: int) -> str:
    if n <= 0:
        raise ValueError("Numeric IDs must be >= 1")
    return str(n)


class IdGenerator:
    def __init__(self, used_ids: set[str], mode: str, strategy: str, start_value: str | None = None, prefix: str = ""):
        """
        mode: "number" or "letter"
        strategy: "start_at", "continue", "fill_gaps"
        start_value: string, e.g. "1" or "A"
        prefix: put before every ID; only the used IDs that carry it are reserved
        """
        self.mode = mode
        self.strategy = strategy
        self.prefix = prefix

        # Choose converters
        if mode == "number":
            self.to_int = number_str_to_int
            self.from_int = int_to_number_str
        elif mode == "letter":
            self.to_int = letters_to_int
            self.from_int = int_to_letters
        else:
            raise ValueError("mode must be 'number' or 'letter'")

        # Convert used ids to ints
        self.used = set()
        for s in used_ids:
            # Reserve the ID, not the optional count appended by populate_ids.
            s = COUNT_SUFFIX.sub("", s)
            if not s.startswith(prefix):
                continue  # another prefix: another numbering
            try:
                self.used.add(self.to_int(s[len(prefix) :]))
            except Exception:
                pass  # ignore invalid IDs if needed

        # Initialize cursor
        if strategy == "start_at":
            if start_value is None:
                raise ValueError("start_value required for start_at")
            self.cursor = self.to_int(start_value)

        elif strategy == "continue":
            self.cursor = max(self.used) + 1 if self.used else 1

        elif strategy == "fill_gaps":
            self.cursor = 1

        else:
            raise ValueError("Unknown strategy")

    def next(self) -> str:
        n = self.cursor

        if self.strategy == "fill_gaps":
            while n in self.used:
                n += 1
        else:
            while n in self.used:
                n += 1

        # Reserve it
        self.used.add(n)

        # Move cursor forward for next call
        self.cursor = n + 1

        return self.prefix + self.from_int(n)


def profile_source(profile):
    """The profile a trim or cutout is made from, which holds its ID; a profile is its own source."""
    if is_trimmedbody(profile):
        return get_profile_from_trimmedbody(profile)
    if is_extrudedcutout(profile):
        return get_profile_from_extrudedcutout(profile)
    return profile


def set_profile_pid(profile, pid):
    source = profile_source(profile)
    source.PID = pid
    # Keep the selected object's BOM data current without waiting for recompute.
    if source is not profile:
        profile.PID = pid


def set_piece_pid(source, pid):
    """Write ``pid`` on a profile and on the trims and cutouts made from it, as their recompute copies it."""
    for obj in (source, *getattr(source, "InListRecursive", ())):
        if obj is not source and not (is_trimmedbody(obj) or is_extrudedcutout(obj)):
            continue
        if getattr(obj, "PID", pid) != pid and profile_source(obj) is source:
            obj.PID = pid


def profile_family(obj):
    """The custom profile label, or the family."""
    custom = getattr(obj, "CustomProfile", None)
    if custom:
        return getattr(getattr(custom, "LinkedObject", custom), "Label", "CustomProfile")
    return getattr(obj, "Family", "N/A")


def shape_measures(obj):
    """Measures of the finished solid that its placement does not change, or None when it has no solid.

    Faces, volume, area and principal moments of inertia of each solid: the same piece moved, rotated or turned
    end for end has the same measures. A piece and its mirror image have the same measures too.
    """
    shape = getattr(obj, "Shape", None)
    if shape is None or shape.isNull() or not shape.Solids:
        return None
    return sorted(
        (len(solid.Faces), solid.Volume, solid.Area, *sorted(solid.PrincipalProperties["Moments"]))
        for solid in shape.Solids
    )


def same_measures(a, b):
    return len(a) == len(b) and all(
        x[0] == y[0] and all(math.isclose(u, v, rel_tol=SHAPE_TOLERANCE) for u, v in zip(x[1:], y[1:]))
        for x, y in zip(a, b)
    )


def group_identical_profiles(profiles):
    """Profiles of the same material, family and size whose finished solids are the same shape, wherever placed.

    Objects without a solid are grouped by their length, cutting angles and cutout flag, as before.
    """
    groups = []
    for obj in profiles:
        measures = shape_measures(obj)
        if measures is None:
            key = (
                profile_family(obj), round(float(obj.Length.Value), 1), obj.Material, obj.SizeName,
                obj.CuttingAngleA, obj.CuttingAngleB, obj.Cutout,
            )  # fmt: skip
        else:
            key = (profile_family(obj), obj.Material, obj.SizeName)
        for group_key, group_measures, members in groups:
            if measures and group_measures:
                same_shape = same_measures(measures, group_measures)
            else:
                same_shape = measures is group_measures
            if group_key == key and same_shape:
                members.append(obj)
                break
        else:
            groups.append((key, measures, [obj]))
    return [members for _, _, members in groups]


def update_counts(pieces, assigned, vacated, write):
    """Give every piece left with an ID numbered here the count of the document pieces that carry it.

    ``vacated``: IDs the selection carried before; only the pieces that show a count get it updated.
    """
    unique = list({id(p): p for p in pieces}.values())
    counts = Counter(COUNT_SUFFIX.sub("", getattr(p, "PID", "")) for p in unique)
    for piece in unique:
        pid = getattr(piece, "PID", "")
        base = COUNT_SUFFIX.sub("", pid)
        if base and (base in assigned or base in vacated and pid != base):
            write(piece, f"{base} x{counts[base]}")


def set_link_pid(link, pid):
    if link.PID != pid:
        link.PID = pid


def populate_ids(
    sel_profiles,
    sel_links,
    doc_profiles,
    doc_links,
    numbering_type,
    allow_duplicated,
    group_ids_for_identical,
    include_part_count_in_pid,
    keep_existing,
    numbering_scheme,
    start_number="1",
    start_letter="A",
    profiles_prefix="",
    links_prefix="",
):

    if keep_existing:
        # Pieces that already have an ID keep it: only the others are numbered.
        kept_profiles = {getattr(o, "PID", "") for o in sel_profiles if getattr(o, "PID", "")}
        kept_links = {getattr(o, "PID", "") for o in sel_links if getattr(o, "PID", "")}
        sel_profiles = [o for o in sel_profiles if not getattr(o, "PID", "")]
        sel_links = [o for o in sel_links if not getattr(o, "PID", "")]

    if allow_duplicated:
        profiles_used = set()
        links_used = set()

    else:
        if numbering_scheme == "fill_selection":
            # The selection is numbered again from the start: the rest of the document is ignored,
            # only the IDs kept in the selection are reserved.
            profiles_used = kept_profiles if keep_existing else set()
            links_used = kept_links if keep_existing else set()
        else:
            profiles_used = {getattr(o, "PID", "") for o in doc_profiles if getattr(o, "PID", "")}
            links_used = {getattr(o, "PID", "") for o in doc_links if getattr(o, "PID", "")}
            if not keep_existing:
                # The selection is numbered again: its own IDs are free.
                profiles_used -= {getattr(o, "PID", "") for o in sel_profiles if getattr(o, "PID", "")}
                links_used -= {getattr(o, "PID", "") for o in sel_links if getattr(o, "PID", "")}

    if numbering_scheme in ["fill_selection", "fill_document"]:
        strategy = "fill_gaps"
    elif numbering_scheme == "continue_document":
        strategy = "continue"
    elif numbering_scheme == "start_at":
        strategy = "start_at"
    else:
        raise ValueError("Wrong numbering_scheme")

    if numbering_type not in NUMBERING_MODES:
        raise ValueError("Wrong numbering_type")
    profiles_mode, links_mode = NUMBERING_MODES[numbering_type]
    start_values = {"number": start_number, "letter": start_letter}
    if profiles_mode == links_mode:
        # One numbering for both kinds: an ID is unique among the profiles and links that carry its prefix.
        profiles_used = links_used = profiles_used | links_used
    gen_profiles = IdGenerator(
        profiles_used, profiles_mode, strategy, start_values[profiles_mode], prefix=profiles_prefix
    )
    if (links_mode, links_prefix) == (profiles_mode, profiles_prefix):
        gen_links = gen_profiles
    else:
        # Each numbering reserves only the IDs that carry its prefix: "P-1" and "L-1" do not clash.
        gen_links = IdGenerator(links_used, links_mode, strategy, start_values[links_mode], prefix=links_prefix)

    # group profiles / links if needed
    if group_ids_for_identical:
        group_links_key_func = lambda obj: (
            # obj.Parent, # ???
            obj.LinkedObject.Label,
            getattr(obj.LinkedObject, "Price", "N/A"),
        )

        links_grouped = defaultdict(list)
        # IDs the selection leaves: the pieces still carrying them get their count updated.
        vacated_profiles = {COUNT_SUFFIX.sub("", getattr(o, "PID", "")) for o in sel_profiles}
        vacated_links = {COUNT_SUFFIX.sub("", getattr(o, "PID", "")) for o in sel_links}
        assigned_profiles, assigned_links = set(), set()

        for group in group_identical_profiles(sel_profiles):
            pid = gen_profiles.next()
            assigned_profiles.add(pid)
            for p in group:
                set_profile_pid(p, pid)

        for sl in sel_links:
            links_grouped[group_links_key_func(sl)].append(sl)

        for _, group in links_grouped.items():
            pid = gen_links.next()
            assigned_links.add(pid)
            for l in group:
                l.PID = pid

        if include_part_count_in_pid:
            # The count covers every piece of the document left with the ID, selected or not.
            sources = [s for s in map(profile_source, sel_profiles) if s is not None]
            update_counts([*sources, *doc_profiles], assigned_profiles, vacated_profiles, set_piece_pid)
            update_counts([*sel_links, *doc_links], assigned_links, vacated_links, set_link_pid)

    else:
        for sp in sel_profiles:
            set_profile_pid(sp, gen_profiles.next())
        for sl in sel_links:
            sl.PID = gen_links.next()
