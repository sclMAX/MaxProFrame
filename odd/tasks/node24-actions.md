# Node 24 GitHub Actions
Update pinned CI JavaScript actions to Node 24 without changing FreeCAD or Python targets. Branch: `ci/node24-actions`; base: `7b63d90`.
Delivery: one local CI work unit, forecast <200 authored lines including tests/docs; no push/merge/hosted dispatch authorized. Checks: host policy tests, exact workflow-preservation checks and independent CI verification.

## Specs

- **S1 — Node 24 actions.** User asked "explicame lo de node" and then authorized "ok actualicemos" after the recommendation: "**Lo recomendable:** actualizar esas acciones a versiones preparadas para Node 24, manteniendo sus commits SHA fijados y verificar nuevamente el CI." Replace the pinned Node 20 actions with official stable Node 24 releases, using full verified commit SHAs, not moving tags. Cover checkout/setup-python and the workflow's upload-artifact failure-report path so a failing job does not reintroduce Node 20.
- **S2 — Preserve CI behavior.** Accepted explanation: "**No afecta a FreeCAD ni agrega Node como requisito de MaxProFrame.** Es una advertencia de la infraestructura de GitHub." Preserve FreeCAD stable/RC pins, embedded/runtime Python choices, host Python3.11, job conditions/triggers, permissions, checkout fetch-depth/persist-credentials, planner/test commands and artifact names/paths/retention. No Node installation or workbench/runtime/dependency changes beyond pinned Actions. Verify existing host policy tests and new exact pin regressions; record hosted validation unavailable without new publication authorization.
- **S3 — Preservation and delivery.** Carry forward user constraint "preservá los lanzadores y la biblioteca original." Leave unrelated `.gitignore`, `docs/local-freecad-testing.md`, `tests/test_freecad_test_launcher.py` and `tools/**` untouched/uncommitted. No original library/profile access. Existing prior "merge commit y push" applied to the completed stable/RC feature, not new publication authority. Local work-unit commit only; no push/PR/merge until user decides.

## Tasks

- **T1 [S1-S3] delegated (active context backstop), done; commit: d9ba511.** Test-first exact Node24 action pins, minimal workflow substitutions and documentation of Node24 infrastructure requirements. Host RED/GREEN, format and structural/differential preservation checks. Risk: item5 (CI/dependencies/execution environment).
- **T2 [S1-S3] delegated independent verifier + parent spot-check, done; commit: d9ba511; verification evidence in this closeout.** Confirm official tag-to-SHA/runtime evidence and preserved workflow contracts, host test results and no unrequested changes; no hosted CI verdict invented.
- **T3 [S1-S3] inline delivery, done; commit: d9ba511 plus passive tracking closeout.** Assess/review if due and available, commit feature-only local CI unit and tracking evidence. No publishing.

## Log

### L1 — Original authorization
ok actualicemos

### L2 — Accepted recommendation and scope
Parent: "**Lo recomendable:** actualizar esas acciones a versiones preparadas para Node 24, manteniendo sus commits SHA fijados y verificar nuevamente el CI. No hace falta instalar Node en tu máquina ni cambiar el código del banco de trabajo."
Existing hosted run39333298411 on main7b63d90 passed all jobs but warned checkoutv4.2.2/setup-pythonv5.4.0 declare Node20 and were forced to Node24. Failure-report upload-artifactv4.6.1 was skipped in green run; update it too within the same infrastructure behavior.

### L3 — Verified official pins and routing
Read-only official API latest release metadata and exact tag refs verified:
- actions/checkout v7.0.1 -> `3d3c42e5aac5ba805825da76410c181273ba90b1`; https://api.github.com/repos/actions/checkout/git/ref/tags/v7.0.1; exact commit action.yml declares `using: node24`.
- actions/setup-python v7.0.0 -> `5fda3b95a4ea91299a34e894583c3862153e4b97`; https://api.github.com/repos/actions/setup-python/git/ref/tags/v7.0.0; exact commit action.yml declares `using: 'node24'`.
- actions/upload-artifact v7.0.2 -> `cf430e030ddbb5b0abf93d22962f4752f3646cd9`; https://api.github.com/repos/actions/upload-artifact/git/ref/tags/v7.0.2; exact commit action.yml declares `using: 'node24'`.
README at each exact commit reviewed for migration. Node24 actions require Actions Runner >=v2.327.1; authenticated Git inside Docker container actions may require v2.329.0 (not used by this workflow). Ubuntu24.04 GitHub-hosted runners remain target. setup-python7 internal ESM migration does not affect our python-version input; removed pip-install input is not used. New action releases retain required checkout/artifact inputs. Preserve read-only contents permission, persist-credentials false and all existing commands. Parent context backstop active; one bounded writer for this coherent unit. Working tree contains only unrelated launcher changes before new feature; new branch created from currentmain7b63d90.

### L4 — T1 implemented and locally verified
Writer `mvftms9b-7-xdp2` completed the six exact SHA/version-comment substitutions only; normalized workflow byte-equals base outside those substitutions. Host RED38tests/1failure on missing new pins, GREEN38 then39tests/0failures with docs assertion. PinnedBlack/isort, syntax and diff checks passed. Parent read full diff and corrected one documentation phrase: offscreen describes CI tests, not normal workbench usage. Parent host spot-check39/39 passed. Feature-only diff81lines before wording tweak; no app/runtime/launcher edits, no native rerun needed for SHA-only workflow update. ASSESS nativeRisk unassessable (untracked scope), item5 plan requires independent verifier; no reviewDue/nativeapproval invented. T1done/T2starts. Historical hostedgreen run is explicitly not proof of this new candidate.

### L5 — Independent verification passed
Verifier `mvfttqld-8-pjta` reports PASS S1-S3, no blockers/advisories. Exactnormalized workflow byteequality against7b63d90 confirms onlysixapprovedSHA/commentsubstitutions. ASTcomparison proves37existingtestsunchanged plus2newtests; focused2/2exit0. Negativeinmemoryprobes rejectbaselinepins/movingtag/legacyartifactpin/extraaction. Parenthost39/39 reused, no redundantfullnative/hostruns. Threeauthorizedfileoverlaysonly, no workspacechanges. OfficialprovenancereusedfromparentL3, no inventednetworkrecheck. LocalcheckdoesnotprovehostedNode24execution; no publishinggrant. Scratch retained withoutcleanup at `/tmp/gpzPdBgC/gatv0YCK/tmp.t0WhGb7eIe`. T2done; T3localcommitproceeds.

### L6 — Local delivery complete
Commit `d9ba511c85d946a111820d71bd3148491cbf1008` (`ci: pin official Node 24 actions`) contains only workflow, policy tests and CI docs: 81 authored diff lines (73 additions, 8 deletions). Staged whitespace checks and commit succeeded. This separate passive closeout records task completion and the feature commit without altering reviewed functional bytes. All tasks complete locally; no push, merge, PR, dispatch or cleanup performed. Existing dirty/untracked launcher files remain outside commits. Host39/39 and independentS1-S3 pass; hostedNode24candidateexecution remains unavailable/unclaimed. Native assessment unavailability is not approval. Risk:item5CI/environment.
