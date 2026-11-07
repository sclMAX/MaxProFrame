# Extend / Cut and Notch: Apply and continue
Cut profiles between two others without running the command again: cut one end against a target, apply,
pick the other target and cut the other end of the same profiles. Notch, which shares the panel, gets it too.

## Specs
- S1 Apply and continue: "podriamos analizar incorporar aplizar y seguir en Extender" (agreed after the analysis) ->
  while creating (not editing), the task dialog's button row has Apply and continue, enabled once the panel has a
  target and at least one profile. It creates the trims as OK does, in their own Undo step, and keeps the panel
  open. OK then creates only the newer trims (none: no Undo step); Cancel removes only the newer ones.
- S2 What stays: "No, lo mas comun es querer cortar los perfiles entre otros 2 ... elijo un cara corto los 3,
  aplico elijo la cara del otro tubo y corto el otro extremo de los 3." -> after Apply and continue the target is
  cleared and the profiles stay, each one now the trim just created (the next cut is built on it), with the same
  Gap; flipped sides go back to Auto; the next click sets the new target.
- S3 Notch: "si" -> the Notch panel has the same Apply and continue.
- S4 Guard: "SI" -> a profile whose trim chain already has a trim of the same kind against the same target is not
  cut again: a profile clicked while that target is set is not added, and that target clicked while such a
  profile is listed is not taken; the panel says "{profile} is already cut against this target".
- S5 Compatibility: OK, Cancel, editing and the existing clicks keep their behavior.

## Tasks
- T1 S1-S5 Apply and continue in the Extend / Cut panel (and Notch through it), guard, translations,
  tutorial — inline — commit: 3326648 (done, 32 extend-cut panel tests pass)

## Log
- L1 (user): "En inglete solo arreglemos lo de la seleccion, pero podriamos analizar incorporar aplizar y seguir en
  Extender"
- L2 (agent analysis): proposed keeping the target and clearing the profiles, Notch included, double-cut guard.
- L3 (user): "1. No, lo mas comun es querer cortar los perfiles entre otros 2 [image]. elijo un cara corto los 3,
  aplico elijo la cara del otro tubo y corto el otro extremo de los 3. 2. si 3. SI"
- L4 (evidence): RED observed (7 tests: no Apply button, no guard), then test_extend_cut_panel 32/32,
  test_notch_panel 30/30, test_keep_end_panel 22/22, test_extend_cut_polish 31/31, test_extend_cut_preview 22/22.
- L5 (evidence): full native suite 1313 tests, exit 0 (job-10 on 3326648). Native review review-a7d0b26cbb82d815
  (risk + reliability) approved and acknowledged; advisory only, later work: R3-001 create_extend_cut_tool.py:964-971
  (apply error path), R3-002 test_extend_cut_panel.py:399, R3-003 create_extend_cut_tool.py:124-133 (guard compares
  face names; a whole-profile target and a face of it are different targets), R3-004 :128, R3-005 :979-980 (preview
  looked up by profile name without a guard).
