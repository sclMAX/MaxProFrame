"""What a whole Folded Bar selected in the tree stands for in End Miter and Extend Cut: the tubes at its free ends.

odd/tasks/pending-followups.md, S4d. A click on the bar stands for the tube under the point (``folded_bar.segment_at``);
the whole bar, with no face and no point, stands for the tubes at its two free ends, the ones a miter or a cut is
made on. A closed frame has no free end: it stands for no tube and says so (``free_end_tubes``). As an Extend Cut
target the whole bar is refused: a target is a face of one tube (``whole_bar_target_message``).
"""

from freecad.maxproframe._utils import is_foldedbar
from freecad.maxproframe.ff_tools import translate
from freecad.maxproframe.folded_bar import bar_chain, pick_point
from freecad.maxproframe.profile_pattern import newest_piece


def is_whole_bar(obj, sub="", point=None):
    """Whether a pick of ``sub`` of ``obj`` at ``point`` is a whole Folded Bar: no sub-element and no point."""
    return obj is not None and is_foldedbar(obj) and not sub and pick_point(obj, "", point) is None


def whole_bar_target_message():
    """What a tool needing a target face says about a whole Folded Bar."""
    return translate("frameforge", "Click a face of the folded bar.")


def free_end_tubes(bar):
    """(tubes, problem): the current pieces of the tubes at the two free ends of ``bar``, from its start.

    A closed bar has none: ``problem`` then says so; else it is None. A bar whose chain cannot be built (a tube
    removed) gives no tube and no problem.
    """
    try:
        chain = bar_chain(bar)
    except Exception:
        return [], None
    if chain.closed:
        return [], translate("frameforge", "{} is closed: click its tubes to add them.").format(bar.Label)
    tubes = []
    for segment in (chain.segments[0], chain.segments[-1]):
        tube = newest_piece(segment.profile)
        if tube not in tubes:
            tubes.append(tube)
    return tubes, None
