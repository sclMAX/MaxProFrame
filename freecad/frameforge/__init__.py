"""
Backward compatibility bridge from legacy FrameForge to MaxProFrame.
"""
import sys
import freecad.maxproframe as _target

sys.modules[__name__] = _target
