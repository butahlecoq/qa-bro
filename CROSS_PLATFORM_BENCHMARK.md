# Single-worker cross-platform benchmark

The Explorer-generated projection reduced the descriptive median wall time by 12.5% across three SAKAI-02 pairs that compared it with individual reads. Two VUESTIC-01 pairs verified substitution of three field reads with one projection, with an approximately 1.2% lower descriptive median wall time. Using the Sakai comparison that offered batching in both arms, the two-scenario average was 59.500 seconds baseline and 59.262 seconds assisted, approximately 1.004×. The full-suite 2× target and statistical significance remain unverified.

## Current matched results

Each cell shows baseline → assisted. Rows with multiple pairs report per-arm medians. Token medians are rounded to a whole token.

| Comparison | Pairs | Wall time (s) | Model calls | Worker requests | Native browser calls | Combined tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SAKAI-02 projection versus individual reads | 3 | 62.162 → 54.398 | 21 → 19 | 22 → 19 | 38 → 31 | 43,289 → 39,354 |
| SAKAI-02 serial batching versus individual reads | 1 | 57.592 → 47.654 | 21 → 17 | 20 → 16 | 35 → 35 | 43,025 → 36,205 |
| SAKAI-02 projection with batching available to both arms | 2 | 54.561 → 54.856 | 18.5 → 15.5 | 19.5 → 17.5 | 37 → 28 | 39,501 → 34,447 |
| SAKAI-02 projection with CLI-first startup in both arms | 2 | 83.251 → 68.156 | 20 → 17 | 22 → 20 | 38 → 33 | 43,632 → 39,074 |
| SAKAI-02 standard named plans for draft, commit and owned Edit | 2 | 60.557 → 51.648 | 22 → 15.5 | 22 → 14 | 38 → 38.5 | 47,076 → 41,749 |
| SAKAI-03 held-out update projection, main phase | 2 | 51.285 → 45.089 | 16.5 → 15.5 | 19 → 15.5 | 26 → 23.5 | 32,810 → 30,757 |
| VUESTIC-01 projection versus individual reads | 2 | 64.440 → 63.668 | 18 → 16.5 | 18.5 → 16.5 | 75 → 71 | 82,835 → 78,243 |
| VUESTIC-02 named draft plan versus ordinary requests | 1 | 56.026 → 60.555 | 14 → 16 | 23 → 16 | 80 → 89 | 45,061 → 52,572 |
| VUESTIC-02 named draft plan with combined read checks versus ordinary requests | 2 | 60.551 → 59.836 | 14.5 → 15.5 | 22.5 → 17 | 79.5 → 86 | 47,158 → 61,689 |
| VUESTIC-02 combined draft and guarded Add plans versus ordinary requests | 1 | 56.297 → 59.000 | 14 → 15 | 23 → 14 | 80 → 93 | 45,259 → 49,544 |

Three scenarios have qualifying projection pairs. The serial batching row measures a harness feature with the projection disabled for both arms. Mutation dispatch counts and evidence are available in the individual results below.

## Scenario coverage

| Scenario | Best verified scenario outcome | Skill comparison |
| --- | --- | --- |
| [SAKAI-01](scenarios/sakai/SAKAI-01.md) | Pass | No eligible matched comparison |
| [SAKAI-02](scenarios/sakai/SAKAI-02.md) | Matched pass with verified generated tool use | Three projection pairs against individual reads and two pairs with batching offered to both arms |
| [SAKAI-03](scenarios/sakai/SAKAI-03.md) | Two held-out matched passes with two verified grouped reads per assisted run | Lower main-phase time in both pairs |
| [SAKAI-04](scenarios/sakai/SAKAI-04.md) | Matched pass | Worker did not use the candidate |
| [VUESTIC-01](scenarios/vuestic/VUESTIC-01.md) | Matched pass with verified projection use | Two qualifying pairs with repeatable call substitution |
| [VUESTIC-02](scenarios/vuestic/VUESTIC-02.md) | Matched pass with an eight-step named plan and verified cleanup | Fewer worker requests and higher wall time in one matched plan pair. Separate projection validation passed |
| [VUESTIC-03](scenarios/vuestic/VUESTIC-03.md) | Fresh baseline pass, including final table return | Unpaired baseline |
| [VUESTIC-04](scenarios/vuestic/VUESTIC-04.md) | Full baseline pass and live validation of both grouped openers | Matched timing pending |

## Sakai dismissal pilot

The worker used OpenCode with `openai/gpt-6-luna` through subscription OAuth and drove a dedicated Chromium profile through browse. Both arms used the same scenario, synthetic inputs within each pair, browser tools, and bounded-wait instructions. The assisted arm received a frozen candidate produced by a browser-free explorer from an earlier successful Sakai trace. The candidate describes dismissing a currently identified dialog and waiting for it to become hidden. The worker still verifies the scenario's outcome separately.

The run order alternated within each scenario. The measurements include OpenCode startup and execution through process exit. Model steps and dispatcher calls come from OpenCode events. Browse calls count attempted native tool invocations, including failed calls, and exclude tool discovery. Input, output, reasoning, and cache reads are listed separately as reported by OpenCode.

Each cell shows baseline / candidate exposed.

| Pair | Scenario | Order | Evidence | Wall time (s) | Model steps | Dispatches | Browse calls | Input tokens | Output tokens | Reasoning tokens | Cache-read tokens |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | SAKAI-01 | Baseline first | Incomplete / Pass | 42.525 / 50.709 | 7 / 7 | 6 / 6 | 12 / 14 | 13,359 / 34,134 | 1,028 / 1,361 | 0 / 169 | 58,368 / 62,080 |
| 1 | SAKAI-02 | Candidate first | Incomplete / Pass with protocol deviation | 69.542 / 89.485 | 13 / 13 | 12 / 12 | 19 / 27 | 16,381 / 19,613 | 1,864 / 2,343 | 36 / 153 | 139,648 / 167,424 |
| 2 | SAKAI-01 | Candidate first | Incomplete / Pass | 72.368 / 46.187 | 10 / 7 | 9 / 6 | 13 / 15 | 19,142 / 13,457 | 1,688 / 1,232 | 0 / 0 | 92,288 / 58,624 |
| 3 | SAKAI-02 | Baseline first | Pass / Incomplete | 96.822 / 78.832 | 14 / 13 | 13 / 12 | 24 / 25 | 17,681 / 16,567 | 2,287 / 2,031 | 201 / 141 | 161,664 / 138,112 |

Both SAKAI-01 baselines and the last assisted SAKAI-02 attempt lacked direct evidence of the Product Details title. The first baseline also omitted the final period in its exact validation-message check. In pair 1, the baseline compared the owned name with the selection column and therefore missed the row, edit readback, and final Cancel check. Its assisted run returned unrelated seeded rows from the local fixture, contrary to the shared observation protocol.

In pair 3, the assisted run explicitly reported using the skill. The baseline and assisted Cancel waits took 2.238 and 2.237 seconds, respectively. The baseline also spent 10 seconds on a failed form fill before the candidate could apply. The wall-time difference cannot be attributed to the dismissal skill.

The candidate's SHA-256 is `563860effb691bdf417545f305910ca0369f4addd0e48fa5ddac021dd8548b5e`. Raw attempt logs are kept in the local state directory.

The fresh SAKAI-01 baseline retry captured the exact title and validation message. Its immediate read after Cancel found the dialog still visible. It closed the tab without a bounded wait and left the last check inconclusive. This 45.596-second attempt has no assisted match and is excluded from the comparison.

The fresh SAKAI-02 baseline retry captured the title and exact entered values. After Save, an immediate read still showed the dialog, and a separate read showed the creation toast. The worker waited for toast text and never checked the required hidden state again. It skipped the downstream row and edit checks and also returned unrelated seeded rows from the local fixture. This 74.150-second attempt is excluded.

The same fresh panel reached only part of the required preparation for SAKAI-03 and SAKAI-04. SAKAI-03 stopped before verifying a saved row. SAKAI-04 found the exact owned row and price but did not complete the edit readback and final Cancel. Neither attempt reached its primary update or deletion steps.

A second fresh SAKAI-01 run with an explicit native state wait captured the exact title, the validation text while the dialog was open, and an independent table check after the dialog became hidden. It took 51.339 seconds, 12 model steps, and 11 dispatcher calls. It is an unpaired baseline.

Under the same wait instructions, a fresh SAKAI-02 run captured the exact title and values, verified the settled Save result, found the exact owned row and price, reopened the form for readback, and verified that the row remained after Cancel. It took 92.841 seconds, 16 model steps, and 15 dispatcher calls. A failed field locator consumed 10 seconds before Save. This run has no assisted match.

The SAKAI-03 worker reported a pass after verifying the main price update. The audit found missing evidence of the exact description before the preparation Save. The trace also included unrelated seeded content and a page-state change through an evaluation tool that was restricted to reads. The 163.192-second run is ineligible for the comparison.

An independent audit verified the SAKAI-04 baseline preparation, both exact-record confirmation dialogs, the preserved row after No, and the empty owned search after Yes. It took 111.880 seconds, 19 model steps, 18 dispatcher calls, and 37 native browser calls. It is an unpaired baseline.

## Vuestic readiness

A live worker used the guarded browser tools on the public Users page. It verified there was no visible dialog, opened Add User, observed the visible dialog, clicked Cancel, and waited until the dialog was hidden. It entered no values and submitted nothing. This covers the dialog lifecycle only. The four Vuestic scenarios still need guarded field and owned-record evidence before they can produce comparable measurements.

The first field attempt exposed a tool schema issue. The worker omitted the field label from every fill and read request, and the guard rejected all six requests before invoking native field tools. The worker canceled and verified that the dialog closed. After the schema was corrected, a fresh worker filled and separately read back two synthetic Notes values. The exact Email label still failed native control resolution, including after the guard added associated-label and placeholder lookup.

On a dirty form, Cancel opened a second DOM dialog. The live guard reported two visible dialogs and no browser-native prompt. Both dialogs exposed a Cancel button, so the worker could not select a unique confirmation action from the approved labels. It closed its dedicated tab without submitting. The email validation scenario remains incomplete.

The live batching smoke verified that the worker can send one request per click and wait. It took two worker requests, three model steps, 3,758 tokens, and 16.667 seconds. Those requests produced two native clicks and 23 browser evaluations, plus the host's initial navigation. The counts describe the smoke only. It had no baseline arm and did not execute a complete scenario.

A later diagnostic used the browser-side wait with the same observation filter. Stable hidden and visible states took two evaluations each, and the dirty-dialog timeout took three. The live form still exposed no approved Email type or autocomplete token. The handoff-linked source configures the three inputs with name attributes, so exact name tokens are a candidate for host-side binding. The deployed UI must confirm each token before it can authorize a field action. [Vuestic form source](https://github.com/epicmaxco/vuestic-admin/blob/9c5b44f3674d4c3e7ad01cc043d5331cee953c49/src/pages/users/widgets/EditUserForm.vue)

The next guarded run verified all four synthetic field values with independent readback. Email, Full name, and Username resolved via exact HTML name bindings observed live. After Cancel, the host verified the exact unsaved-changes message and resolved the single OK button within that dialog. The host confirmed discard, then independently observed zero dialogs and an available table. No form was submitted. This resolves field lookup and discard for the deployed UI. Email validation and both completed absence searches still need evidence. [Vuestic discard handler](https://github.com/epicmaxco/vuestic-admin/blob/9c5b44f3674d4c3e7ad01cc043d5331cee953c49/src/pages/users/UsersPage.vue#L68-L83)

The prototype owned-search projection distinguishes a matching identity, a conflicting identity under the same marker, duplicates, and no visible match. It can prove absence only with trusted evidence that the current query settled and covered all results. The public Vuestic UI has yet to provide that evidence in a guarded run.

The live search probe verified one Search input, one table, exact Active and Inactive controls, and an initial table transition from `aria-busy=true` to `false`. It stopped before entering a query because its approved projection did not find a visible counter that established result coverage. No inference about record absence was made. The pinned source displays a total, but the probe did not establish that this signal was available in the deployed DOM. [Vuestic table source](https://github.com/epicmaxco/vuestic-admin/blob/9c5b44f3674d4c3e7ad01cc043d5331cee953c49/src/pages/users/widgets/UsersTable.vue#L143-L172)

A later read-only probe completed exact synthetic searches in both filters. It tied the input event to the scoped table's busy-to-idle transition. In each filter a fresh read showed one exact empty-state message, zero data rows, and no visible error. This validates a coverage witness without a result counter. VUESTIC-01 still needs the same witness for its own marker after Cancel.

The complete VUESTIC-01 baseline verified the synthetic form values, the exact invalid-email error and disabled Add, and then the corrected value, cleared error, and enabled Add. It submitted nothing. Cancel and scoped discard closed the form. Fresh searches for this attempt's exact marker completed in both Active and Inactive and proved absence. The run took 71.599 seconds including host search verification, with 16 model steps, 21 worker tool calls, and 77 counted native calls. The native count excludes initial navigation and tab lifecycle. The session reported 65,450 combined tokens, including cache usage. This is an unpaired baseline.

The Vuestic explorer produced a 36-word candidate for grouping independent field readbacks. It keeps one evidence result per field and leaves blur and validation as explicit boundaries. Acquisition used one model step and 1,611 tokens for the accepted output. One earlier explorer response failed the provenance check and had no available usage count. The comparison runner gives both arms the same optional batching tool and only the assisted arm receives the frozen candidate text.

| VUESTIC-01 pair | Scenario evidence | Wall time (s) | Model steps | Worker requests | Native calls | Combined tokens |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 0, baseline / assisted | Pass / Pass | 88.617 / 81.993 | 17 / 21 | 21 / 22 | 74 / 76 | 74,745 / 95,794 |
| 1, baseline / assisted | Incomplete / Incomplete | 52.500 / 82.050 | 13 / 22 | 15 / 21 | 33 / 78 | 51,781 / 113,516 |

The original baseline grader required a second read of the corrected email even though the fill tool had already performed a separate native read and returned equality. Reviewing both traces against the source scenario recognizes that native read as evidence and retains the separate blur, cleared error, and enabled Add checks. The original grader output is kept. Neither worker sent a batch request, so this pair provides no evidence of a reduction from the learned batching instruction.

Both pair 1 workers requested one batch. The assisted run recorded the error, its later disappearance, and both completed absence searches, but rejected requests left the Add enabled-state checks unverified. The baseline also left the validation and Cancel checkpoints unverified. This pair is excluded from performance claims.

The explorer generated a second, unvalidated evidence rule in one step and 1,599 tokens. It proposes reusing a tool response only when the tool is documented to include fresh native verification of the required state. Stale or unverified results still require a separate check. It changes no scenario assertions.

The next VUESTIC-01 iteration is staged. Both arms can batch distinct edits to the same host-approved draft form, and each edit still produces a separate native equality check. The scenario grader accepts those observed values without requiring a duplicate read. Only the assisted arm receives the evidence rule. The runner also checks the native tab-close receipt separately from application dialog closure.

| Evidence-reuse VUESTIC-01 pair | Scenario evidence | Wall time (s) | Model steps | Worker requests | Native calls | Combined tokens |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 0, baseline / assisted | Pass / Pass | 72.500 / 75.238 | 20 / 19 | 19 / 18 | 72 / 75 | 91,814 / 89,750 |
| 1, baseline / assisted | Pass / Incomplete | 68.603 / 67.112 | 19 / 18 | 18 / 17 | 74 / 78 | 89,205 / 86,482 |

In pair 0, both workers used two batches and performed the same four separate field read requests. Both recorded native tab closure. The assisted arm made one fewer worker request and used slightly fewer tokens, with higher wall time and more native calls. The trace does not show a read eliminated by the evidence rule.

In pair 1, the assisted worker verified the corrected email value and blur but omitted direct checks of the cleared message and enabled Add before Cancel. Both runs used two batches and recorded native tab closure. Pair 1 is excluded from speed claims.

VUESTIC-02 readiness verified the four synthetic values in the unsaved form and found Add enabled. A second probe confirmed a unique dialog titled Add user, unique native field names, and the exact accessible Edit user and Delete user actions. It did not establish the Role and Projects defaults or the table's identity columns. The probes sent no Add or Delete action and recorded a native tab-close receipt.

A follow-up live probe established Full name, Email, and Username in columns 1–3 and unique native Edit user and Delete user buttons in column 6. The default view displayed seven results for seven rendered rows. That coverage applies to the default view. Exact-query coverage remains a separate observation. Full name appeared as direct text beside avatar markup, which the owned-row locator must handle. Role and Projects remain unresolved.

The empty-form option probe found a custom select displaying exact User text and another with an empty display region and zero tokens. It did not establish either field's identity. Opening the first select invalidated the probe's single-dialog requirement, so it obtained no option or selection evidence. Cancel and native tab closure succeeded, and the probe wrote no records.

The revised option probe kept the original Add user dialog scoped by its exact heading. Opening the User display introduced one popup outside that dialog with three option-like elements. Two ARIA references were visible, but the probe did not establish that either referred to a container owning all three options. It withheld the option and selection claims and closed its tab without writes.

The next probe verified the Role default. The unique ARIA-linked container held exactly one Admin, Owner, and User option, with only User reporting `aria-selected=true`. The other select still showed an empty display and zero tokens. Its Projects label was not visible, so a runner using the two-select form structure and pinned source must disclose that binding as an inference. No form values changed. The Cancel wait timed out, and the browser independently confirmed tab closure. [Pinned Vuestic form source](https://github.com/epicmaxco/vuestic-admin/blob/9c5b44f3674d4c3e7ad01cc043d5331cee953c49/src/pages/users/widgets/EditUserForm.vue)

A targeted table read then confirmed that each displayed Full name cell contains one visible direct child div with direct text, and that the Email and Username cells expose their values in visible leaves. The projection reported structural booleans only. The browser confirmed tab closure. This evidence supports configuring the exact owned-row matcher for the create-and-read attempt.

The first live VUESTIC-02 worker opened the creation dialog and verified that it was visible. It stopped when the exact title check was rejected because the runner had omitted the title from the guard's allowlist. It did not fill or submit the form. The browser confirmed tab closure, and no cleanup was needed. The attempt took 28.143 seconds, seven model steps, and six worker calls. The timing is excluded.

The retry verified the exact creation dialog and read back all four synthetic fields. It stopped before Add because the worker had no create-mode default-state observation and requested the edit-mode observation instead. The following Add state request was out of scope. The browser confirmed tab closure, and no record was created. The attempt took 48.016 seconds, 11 model steps, 15 worker calls, and 37,997 tokens. The next runner needs to expose create-mode evidence separately from edit-mode evidence.

With a create-mode observation available, the worker verified the draft values, selected User, Active, empty avatar, and the empty select inferred to be Projects. It then observed Add enabled and made the scoped request. The strict create preflight returned `not_actionable` before native Add, and the browser confirmed tab closure. No record was created. The attempt took 42.409 seconds, nine model steps, and 30,306 tokens.

A separate read-only audit reproduced the rejection. Closing the Role popup moved focus to the page body. The exact dialog, enabled Add locator, and all five bound native values passed. The remaining failed predicate required focus inside the dialog. The audit dispatched no Add and confirmed tab closure.

The create guard now has an explicit opt-in for body focus when the exact approved dialog is the sole visible semantic dialog. It still verifies the title, approved field values, enabled action, and strict native locator in the same preflight. The opt-in is unavailable to edit actions. Focused regression tests passed. Another VUESTIC-02 attempt is authorized under the existing one-create limit, with the prior non-dispatched evidence preserved.

The first attempt after that fix stopped before it could exercise the create guard. The worker verified the open dialog and exact title, then did not request the live field bindings. It made no fill or Add request. The run took 18.394 seconds, five model steps, and four worker calls. The tab closure was verified. The next runner will expose current approved fields with the dialog visibility evidence.

The fifth VUESTIC-02 attempt received the approved fields with dialog-open evidence, verified the draft, and dispatched Add once. It observed the owned row and verified the full synthetic identity after a fresh, completed search. The owned Edit click returned an uncertain receipt, so persisted Notes and closing Edit remained unverified. The separate cleanup run confirmed the same exact Active record and complete absence in Inactive. Its row action returned an uncertain dialog-opening receipt, and it sent no Delete confirmation. Both tabs closed. The main attempt took 51.028 seconds, 13 model steps, 18 worker calls, and 36,448 tokens. Cleanup for the sole synthetic record remains pending.

A separate recovery read verified the exact owned Edit dialog, identity, Notes, Role, and Active. The native click had returned a nonempty `clicked` field, but the 6,542-character response exceeded the row decoder's 4,096-character limit. Cancel dispatched, but the hidden wait timed out. The browser confirmed tab closure. The recovery verifies persisted Notes outside the timed attempt and leaves the scenario's return-to-table check unverified.

Cleanup recovery matched the exact owned record in a fresh search, found one confirmation displaying its exact name, and sent one scoped Delete confirmation. Although the confirmation's hidden wait timed out, fresh completed Active and Inactive searches both verified absence. The browser confirmed tab closure. There is no pending synthetic record from VUESTIC-02.

A fresh VUESTIC-02 fixture passed the full scenario. The worker verified the draft values, creation, exact persisted identity after a completed search, exact Notes, Role User, Active, and return to a visible table after closing Edit. The sole other select was kept empty under the previously disclosed live-structure and pinned-source Projects inference. The run took 73.866 seconds with 23 model steps, 23 worker calls, 81 native calls, and 72,359 combined tokens. Separate cleanup sent one scoped Delete and proved absence with fresh completed searches in both filters. Both tabs closed. This is an unpaired baseline.

The independent VUESTIC-04 fixture passed the complete create-and-read preparation and closed its preparation tab. The main worker verified both exact owned confirmation messages and that Cancel preserved the record after a fresh search. It dispatched one Delete confirmation, then stopped when the dialog-close wait timed out. Separate read-only recovery completed both fresh filters and verified absence without issuing a second Delete. All tabs closed. The main worker used 11 model steps and 16,122 tokens. The timed run remains partial.

The separate VUESTIC-03 fixture passed the complete create-and-read preparation in 70.410 seconds and closed its preparation tab. The primary worker completed an exact fresh owned search, opened Edit, and verified Role User. The original-form guard then returned `not_actionable` before any Notes fill or Save. The exact failed predicate was not recorded. The primary worker ran for 18.586 seconds and confirmed tab closure. Separate cleanup verified the synthetic record absent after one scoped Delete. This main attempt remains partial.

A fresh diagnostic fixture passed preparation and every original-form predicate, including the exact identity, original Notes, Active, Role, focus, and aggregate native check. The Notes fill then returned `out_of_scope` before a browser action because the ordinary fill tool had not registered the live Notes binding. No Save was attempted. A separate recovery run on the same owned fixture refreshes that binding after a fresh exact search and original-form proof.

A second explorer candidate proposes collecting exact owned-record evidence and structural action information in one scoped read. It was generated from verified Sakai traces in one model step using 2,977 tokens. It remains inactive pending validation on fresh attempts.

The explorer separately assessed the unnamed row controls using one model step and 1,917 tokens. It returned no candidate because the traces never linked a uniquely identified control to Edit before clicking. A tooltip probe remains an untested hypothesis.

Using the newer Sakai trace, the explorer generated a compound-field discovery candidate in one model step and 1,689 tokens. It checks for a unique live label, linked element, and compatible editable descendant before acting, then reads the field value independently. The frozen candidate is staged for fresh SAKAI-02, SAKAI-03, and SAKAI-04 attempts with new synthetic inputs.

The first held-out attempt stopped before any scenario action. Its discovery call tried to use the disabled snapshot tool before reaching the scoped read. The worker closed its tab without testing the candidate. The 26.140-second attempt provides no latency or applicability evidence.

The held-out SAKAI-03 attempt independently passed all preparation and update checks. It took 128.176 seconds, 19 model steps, 18 dispatcher calls, and 43 native browser calls. The worker used a freshly observed field ID directly and reported that it never applied the candidate. The earlier SAKAI-03 baseline is ineligible, and this attempt used different inputs, so the timings do not form a matched comparison.

The held-out SAKAI-04 attempt reported a pass and used the compound-field relationship with exact value readback. It took 150.741 seconds. The trace includes broad screenshots of the seeded table, contrary to the observation protocol, so this attempt cannot validate the candidate or supply a timing comparison.

The four-pair Sakai panel is complete. It alternated order within SAKAI-02 and SAKAI-04 and used identical scenario text and synthetic inputs within each pair. Both arms received the same scoped tool instructions. The assisted arm received the frozen compound-field candidate.

| Pair | Scenario | Baseline / assisted evidence | Wall time (s) | Model steps | Dispatches | Input tokens | Output tokens | Cache-read tokens |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | SAKAI-02 | Pass / Incomplete | 153.396 / 71.231 | 28 / 16 | 27 / 15 | 21,884 / 27,609 | 2,736 / 1,330 | 395,008 / 142,464 |
| 1 | SAKAI-04 | Pass / Pass | 148.935 / 133.436 | 32 / 20 | 31 / 19 | 44,671 / 24,140 | 3,168 / 3,331 | 511,616 / 338,432 |
| 2 | SAKAI-02 | Incomplete / Worker reported pass without candidate use | 75.820 / 130.541 | 17 / 28 | 16 / 27 | 16,739 / 23,169 | 1,632 / 2,687 | 186,368 / 442,112 |

After Save, the assisted worker's scoped read showed a closed dialog. It then supplied `text` to `wait_for`, which waits for appearance even when the call also includes the selector state option. The timeout stopped the run before row verification and edit readback. The worker reported no candidate use. This pair is excluded from the speed comparison. The common instructions for the two unstarted pairs now explain the wait options and allow the worker to proceed when a fresh observation directly verifies the expected state after a tool error.

Both pair 1 runs independently verified the full preparation and deletion scenario. The arm exposed to the candidate was 10.4% faster, with fewer dispatcher calls and 40 native calls compared with 38 at baseline. Its trace filled a directly observed field ID without establishing the candidate's label-to-wrapper relationship. The pair shows a difference between two successful runs, with no verified candidate use to attribute it to.

The pair 2 baseline used benchmark directory names as check labels. The OpenCode sessions shared a working directory, so this is evidence that benchmark metadata reached at least one worker. This panel cannot establish blinded effectiveness. Future Sakai arms will use separate empty working directories, with attempt fixtures and traces stored outside those directories. Pair 3 is also excluded because the local Sakai preview was unavailable before either arm could start its scenario.

The first isolated SAKAI-02 baseline used a fresh directory containing only OpenCode configuration. It still emitted benchmark directory names absent from its prompt and working directory. The source of those labels remains unverified. The 172.287-second trace also lacked the required Cancel click, so it is excluded regardless of the label source.

Its assisted counterpart took 140.695 seconds. The worker reported a failed price check because the edit field displayed `$17.52` rather than an unformatted number. The supplied value was 1,752 cents, and the scenario calls for the corresponding UI dollar amount. The scoped field read is consistent with that value. The incomplete baseline prevents a speed comparison.

An unchanged machine-readable explorer query passed a separate live Sakai smoke. It found a unique Price spinbutton by following the observed label relationship, minted a short-lived host-only handle, and revalidated that relationship before one native fill. An independent read verified `78.41`. Cancel hid the dialog and the browser confirmed tab closure. The value was never saved. The 5.370-second smoke includes cleanup from a prior tab-handle error and is excluded from scenario timing comparisons.

A later read-only Sakai probe verified the exact Product Details title through the dialog's ARIA association and a unique native spinbutton inside its Price wrapper. It opened and canceled an empty draft and confirmed native tab closure. A separate settled-table probe verified Name and Price in columns 3 and 5 and a unique unlabeled native Edit button with a direct visible pencil icon in each action cell. It returned structural counts only and confirmed tab closure. These are the approved bindings for the next guarded Sakai pair.

A matched SAKAI-02 pair tested the full source scenario with the same ordinary Browse tools and synthetic inputs. The assisted arm could invoke the frozen generated query for one Price field through a scope-checked bridge. The 109.476-second baseline verified the saved row and its values but used a wait for the title to appear after Save and never verified the required closure. The 60.233-second assisted run never requested the bridge and stopped after a normal Price locator failed. Neither run is eligible for a speed comparison.

In a follow-up pair, the assisted worker invoked the frozen generated query once. Its receipt recorded successful handle creation, revalidation, fill, and equality, followed by independent ordinary Browse readback. The assisted arm verified all six scenario checks. The baseline lacked direct evidence of the exact Product Details title, and both arms returned unrelated seeded rows from the local fixture. This pair verifies actual tool use and is excluded from performance claims.

| Explicit generated-query SAKAI-02 pair | Wall time (s) | Model steps | Dispatches | Native calls | Input tokens | Output tokens | Reasoning tokens | Cache-read tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline / assisted | 84.602 / 87.749 | 14 / 13 | 13 / 12 | 23 / 30 | 15,716 / 16,419 | 2,091 / 2,051 | 258 / 238 | 143,232 / 136,192 |

The guarded SAKAI-02 pair gives both arms the same approved observations, exact synthetic inputs, and scope-checked actions. Only the assisted arm can invoke the generated field capability. The worker tool has no arbitrary browser evaluation, snapshots, screenshots, or raw row reads. The first launch stopped before the worker started because the adapter passed a keyword-only argument positionally. The tab closed successfully. The adapter was corrected, both arms passed a real-constructor check, and a fresh pair launched.

The guarded retry ended with both arms partial and both tabs closed. The baseline verified the exact owned row and price, then the strict Edit locator rejected the action. The assisted worker successfully used the generated field query and read back all required fields, then the Save guard rejected the action. The readback accepted the exact decimal representation while the staged Save guard required currency formatting. That mismatch and the icon locator are under investigation. The shorter run stopped earlier, so this pair provides no speedup evidence.

| Guarded Sakai retry | Wall time (s) | Model steps | Worker requests | Native calls | Combined tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline / assisted | 53.357 / 29.505 | 17 / 11 | 15 / 10 | 22 / 19 | 30,677 / 18,090 |

The read-only Edit diagnostic verified that the direct pencil icon contributes CSS-generated content to the button's accessible name. The native locator resolved the exact row, price, and action cell and matched the unique pencil button after removing its empty-name predicate. The corrected icon binding retains strict ownership and button uniqueness. Price readback and Save now use the same exact integer-cent comparison across decimal and displayed currency formats. All 32 focused tests passed, along with construction and offline transition checks for both arms. The next guarded pair ran with the assisted arm first.

The corrected guarded pair verified a complete assisted pass with actual generated Price use and all six original checks. The baseline stopped after verifying the exact title and issued no field fill. Both tabs closed. The pair shows that the generated capability works through the restricted surface and is excluded from speed claims.

| Corrected guarded Sakai pair | Wall time (s) | Model steps | Worker requests | Native calls | Combined tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline / assisted | 14.449 / 58.381 | 4 / 21 | 3 / 20 | 4 / 39 | 5,674 / 41,325 |

Returning live field availability with the title did not resolve the early baseline stop. In that iteration the baseline verified the title and received all three scoped field bindings but took no fill action. The assisted worker used the generated query and passed all checks. Both tabs closed. The result remains ineligible for timing comparison. The next iteration supplies the exact synthetic inputs to both workers in the prompt, while still requiring host-bound tool actions and independent evidence. It also records an allowlisted reason code when a worker stops.

| Guarded Sakai pair with field discovery | Wall time (s) | Model steps | Worker requests | Native calls | Combined tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline / assisted | 16.684 / 56.687 | 4 / 18 | 3 / 21 | 5 / 42 | 5,919 / 38,735 |

In the complete assisted run, the 42 timed native calls accounted for 8.464 of 56.687 seconds. The recorded native calls included 5.271 seconds in clicks, 2.664 in browser evaluations, and 0.529 in fills. Holding everything else fixed, even eliminating all measured native-call time would yield about 1.18× for that run. A larger gain needs to reduce time outside those calls, such as worker round trips, while retaining each required observation. This is a descriptive breakdown of one run.

### Helper authorship

The Explorer must generate reusable UI capabilities from browser observations. Manually authored experiment helpers and action sequences do not count as learned capabilities in the comparison. The harness can validate and dispatch model-generated operations. A successful assisted run must record actual use of the generated capability and independently verify the scenario's stated checks.

In the latest VUESTIC-03 recovery, the worker verified the original form and the updated Notes draft, then dispatched Save once. The dialog remained visible through the wait timeout. The tab closed. Save persistence requires a fresh exact-record readback. This recovery supplies no timing comparison.

A fresh reload and exact owned-record search confirmed that the VUESTIC-03 Notes change persisted. Reopening Edit verified the updated Notes, unchanged Full name, Username and Email, Role User, and Active status. Cancel dispatched, but the subsequent table availability check failed. The readback tab closed and the scenario remains partial.

Separate cleanup dispatched one owned-record Delete and verified absence in fresh completed searches of both the Active and Inactive filters. The cleanup tab closed. The next SAKAI-02 pair uses the same scoped runner and explicit synthetic inputs for both arms. The assisted candidate has the same SHA-256 as the original Explorer output.

Both explicit-input SAKAI-02 arms passed all six checks and closed their tabs. The assisted worker used the unchanged Explorer capability and verified the resulting Price. This matched pair shows a 5.1% latency increase with the capability, alongside more worker requests, native calls, and tokens.

| Explicit-input SAKAI-02 | Wall time (s) | LLM calls | Worker requests | Native calls | Combined tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 58.989 | 17 | 21 | 37 | 36,979 |
| Explorer-assisted | 62.015 | 22 | 23 | 45 | 47,517 |

The assisted trace included a successful Price capability receipt with an exact native readback, then an explicit Price read, a blur, and another read. The baseline read Price once before Save. These extra requests account for the net increase of two worker requests. Both arms also read Name, Description, and Price separately after reopening Edit. That group is a candidate for reducing round trips if each field keeps its own live evidence.

A browser-free Explorer run used one model call and 1,698 tokens to propose collecting an exact dialog title and separate keyed field results from one bounded fresh browser observation. Both passing Sakai traces used four worker requests and eight native reads for that block. The proposed single native read remains a hypothesis. The current proposal is an instruction with trace citations, and the existing single-field query compiler cannot execute it as supplied.

The batch wrapper passed all 12 focused tests. It can package individually approved semantic reads into one worker request while preserving each child’s result. An offline construction check against the actual Sakai adapter rejected its `field` argument, so the wrapper cannot run the matched Sakai tool calls unchanged. The existing batch implementation dispatches the child calls separately and does not support a single native observation.

A second browser-free Explorer call produced a declarative proposal in 4,110 tokens. The current harness cannot execute it directly. The proposed operation lacks a numeric field limit and would return raw observed values, so it remains inactive. The Explorer will generate a bounded, boolean-only revision for offline review. An existing serial batch can group approved field requests, but it cannot provide the same exact title and field evidence from one fresh observation.

The existing form preflight already supports one isolated browser evaluation that checks a dialog and multiple bound fields and returns one aggregate boolean. That preflight is useful as a reference for scope and exact comparisons. The proposed observation still needs separate evidence for each requested field. Vuestic’s custom Role control has its own witness and needs to retain it unless the Explorer independently validates equivalent evidence. The current regression suite ran 212 tests with 10 skipped and no failures.

The first implementation-generation attempt returned `NO_CANDIDATE`, citing missing interface definitions for the approved scope and browser outcome parser. Acquisition used 7,119 tokens in two model steps. A retry with the actual definitions is pending. No helper was activated.

The retry generated a private implementation in one model step using 5,537 tokens. It returns booleans for up to four fields, but the reviewer found that the browser code scans the full subtree before applying its limit and fails to verify the visible dialog and nearest-dialog ownership of each match. It also lacks the wrapper and exact decimal matching required by Sakai Price. The implementation was rejected before browser use. The next Explorer pass is constrained to preserving the existing form guard and changing only its read-only output.

The next Explorer output targeted the existing guard, but the proposed diff failed `git apply --check` and would change the return contract of a function used by the Vuestic edit guard. It remains inactive. A corrective generation will preserve that contract and keep per-field projection opt-in.

An offline audit could not identify why the VUESTIC-03 table check failed. The independent readback retained the dispatch receipt and final boolean but omitted the intermediate dialog and table observations. A fresh baseline will retain those observations if the existing runner supports the scenario without a new helper. The source asks the worker to wait for Save’s result and reload. The earlier runner additionally required all visible dialogs to disappear before permitting reload.

The corrected Explorer patch passed application and syntax checks. With the patch loaded in a private test process, 11 existing guard tests passed and a mocked transport confirmed one read-only call. The patch keeps the existing browser scope and value comparisons. It remains inactive because it changes an invalid aggregate read from `False` to `None` and accepts extra keys in projection replies. The retry used 7,816 tokens in one model step. A final generation is addressing those two issues.

The fresh VUESTIC-03 baseline passed all four main checkpoints. After one Save, the bounded wait timed out with one DOM dialog visible and no native prompt pending. The prescribed reload and fresh exact owned-row search verified the updated Notes and all unchanged fields. Cancel then returned to a visible table with no remaining dialogs. The main run took 52.078 seconds, 11 LLM calls, 92 native calls and 15,604 tokens. Fresh preparation took 64.296 seconds separately. The main tab closed. Separate cleanup dispatched one owned Delete and confirmed absence from both filters in fresh completed searches. All three tabs closed.

The final Explorer patch preserves literal `False` for invalid legacy bindings and accepts only the exact projection response shape. It passed the application check, JavaScript syntax check, 11 existing tests and mocked response checks. Total acquisition across the three form guard attempts was 15,716 tokens. The patch remains private pending a generated adapter integration and a matched browser trial.

The held-out review identified a matching use in VUESTIC-01. Two prior successful baselines separately verified Full name, Username and the invalid Email after filling them and before blurring Email. A fresh matched pair can exercise one projected read for those three inputs while retaining the original validation, cancellation and absence checks. The earlier runs establish feasibility of the individual observations. Fresh matched runs are still required to measure the optional projection.

For the projection trial, both Sakai arms will omit the earlier Price capability. The first generated adapter was rejected offline because the new read was missing from the actual worker schema, dispatcher and audit path. The Explorer is regenerating the adapter. The Vuestic trial is being staged separately with the same generated form projection and its own exact live bindings.

Report pass coverage with latency. For each scenario, compare the baseline and assisted medians from matched attempts and report the paired time differences alongside model calls, worker requests, native calls and tokens. Show the mean wall time by mode across the same scenarios, weighting scenarios equally, for the cross-platform 2× target. A faster run that misses checks cannot supply a successful timing. Report learner acquisition separately so its cost is visible.

In the 21-request, 37-native-call Sakai baseline, three separate field reads followed draft entry and three followed reopening Edit. Those six requests issued 12 native evaluations. If the worker uses the projection exactly once per group and the remaining trace is unchanged, the expected counts are 17 worker requests and 27 native calls. The title checks remain independent. This arithmetic describes the call budget for a repeat of the recorded trace and does not predict end-to-end latency.

Offline checks found that the staged Sakai adapter compared live field descriptors with bare field strings, leaving the projected read unreachable. The private runner also had a path expression that would fail before opening a browser. Both were returned to the Explorer. The Vuestic adapter is under offline review in its own private stage.

The generated Sakai adapter passed offline checks for both arm schemas, exact input and manifest digests, read-only dispatch and per-field receipts. Earlier Price assistance is disabled in both arms. Adapter generation and correction used 36,819 tokens in six model steps, separate from guard generation. The first live pair started baseline first on the dedicated single browser.

Both arms of the first live projection trial passed all six SAKAI-02 checks and closed their tabs. The assisted worker never invoked the projection. The trace used individual field reads at both opportunities. This measured exposure to the optional capability and does not measure its effect. The Explorer is auditing live tool exposure and preparing an assisted-first trial that asks the worker to use the capability when it has independently identified eligible reads.

| SAKAI-02 projection offered | Wall time (s) | LLM calls | Worker requests | Native calls | Combined tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 55.369 | 20 | 21 | 36 | 40,372 |
| Assisted, projection unused | 55.943 | 18 | 23 | 39 | 41,037 |

A direct offline JSON-RPC `tools/list` call to the frozen Sakai MCP shim returned the projected read only for the assisted arm. Its schema permits two or three unique approved fields. This verifies the shim’s advertised contract. The saved live trace has no projection request, so it does not establish whether the provider exposed the complete nested schema to the model.

A browser-free probe used the frozen OpenCode component schema and a stub transport. Luna sent `use_read_fields` with two approved field names through MCP. This verifies model-side invocation and rules out loss of that action in schema serialization. The original live worker relied on ordinary reads and skipped the explicit Edit title refresh required by the projection. The next trial will name the operation in the assisted prompt and retain the same live scope checks. The tool probe used 2,187 tokens in two model steps.

The assisted-first Sakai activation pair started with the same frozen scenario, inputs, guard and adapter. Luna generated the revised assisted prompt and tool description in 3,375 tokens across two model steps. Both now name `use_read_fields` and tell the worker to use it for independently required checks in the same live dialog. The baseline prompt is unchanged. This is a capability-activation trial, separate from the earlier optional-adoption pair.

The assisted-first Sakai arm passed all six checks in 62.499 seconds and closed its tab. The worker invoked the projection immediately after opening the exact owned Edit row. The host returned `unverified` before a native call because the worker had not separately refreshed the dialog title. Individual reads then verified all fields. The Explorer is evaluating whether the projection’s existing live title and scope checks can supply that evidence in the same read. The source still requires independently verifying Product Details when opening the create dialog.

The activation pair finished with both arms passing and both tabs closed. The assisted worker attempted the projection once, but the host rejected it before the native read. The pair does not measure successful projection use.

| SAKAI-02 activation trial | Wall time (s) | LLM calls | Worker requests | Native calls | Combined tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 59.104 | 17 | 23 | 40 | 38,639 |
| Assisted, projection unavailable | 62.499 | 21 | 22 | 36 | 46,177 |

The staged Vuestic runner completed mocked baseline and assisted paths with the same validation, cancellation and absence checks. The assisted mock returned three independent booleans in one call and used 17 worker requests versus 19. The original pass evaluator still used fill-native readback as its field witness. The next offline check must verify that ordinary or projected read receipts can satisfy the same explicit field observation gate. The mock is not a browser result.

The Explorer generated an Edit integration that reuses the verified owned-row Edit dispatch and has the projection establish the current title, unique visible dialog, field ownership and value comparisons in one native read. The create title checkpoint is unchanged. Offline checks confirmed the owned Edit path uses one read and refuses reads after an uncertain dispatch or cancellation. Generation used 1,983 tokens in one step. A live matched pair started with the assisted arm first.

The revised assisted Sakai arm passed all six checks in 54.767 seconds and closed its tab. One native call immediately after Edit returned exact true comparisons for Name, Description and Price. Its receipt directly satisfied the saved-fields checkpoint at trace index 16. The arm used 17 LLM calls, 20 worker requests, 33 native calls and 38,233 tokens. The matched baseline is still running.

The revised Sakai pair finished with all six checks passing in both arms and both tabs closed. Verified projection use reduced the signature Edit readback from three separate field requests to one. The assisted run was 11.9% faster (1.14×), with 20.7% fewer tokens. This is one matched pair, so it does not establish a median improvement.

| SAKAI-02 owned Edit projection | Wall time (s) | LLM calls | Worker requests | Native calls | Combined tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 62.162 | 23 | 22 | 38 | 48,194 |
| Explorer-assisted | 54.767 | 17 | 20 | 33 | 38,233 |

The held-out VUESTIC-01 shared evaluator passed the two complete mocked paths and rejected missing, late, mismatched and duplicate evidence. It accepts exact ordinary UI reads or one exact three-field projection receipt. The fresh paired trial was authorized for the same dedicated browser after both Sakai tabs closed.

The successful Sakai traces show where the reduction came from. The baseline made three individual Edit field requests plus a separate refreshed title request. The assisted worker used one projected read there. It also made one additional individual read during creation, leaving a net reduction of two worker requests. Both arms recorded nine browser mutation dispatches. The Explorer is reviewing the remaining trace for larger savings that preserve independent checks.

Sakai’s isolated Edit verification segment fell from eight native evaluations to one. The eight baseline reads totaled 0.124 seconds. Total measured native time increased from 5.572 to 6.734 seconds across the full runs, so these timings do not attribute the observed wall-time improvement to native speed. The Explorer’s next proposal combines one explicitly requested action with separately requested fresh observations where the scenario permits it. A trace review estimates at most three to four fewer worker calls in the examined segment and does not support a 2× latency claim. The proposal remains inactive.

The first held-out live VUESTIC-01 projection pair finished. The baseline passed all checkpoints, including two fresh absence searches. The assisted worker used individual reads, verified the field and validation checks, dispatched Cancel and the follow-up confirmation, then timed out waiting for the dialog to become hidden. It did not complete the required absence searches. Both tab closures were verified. There was no projection receipt, and this pair is excluded from successful latency comparisons.

| VUESTIC-01 held-out attempt | Wall time (s) | LLM calls | Worker requests | Native calls | Combined tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline, pass | 65.879 | 19 | 18 | 77 | 89,470 |
| Assisted, partial | 61.022 | 19 | 18 | 40 | 90,044 |

A separate read-only follow-up verified the VUESTIC-01 synthetic marker absent from both filters and closed its tab. The assisted trace had no Add submission. The follow-up leaves the original pair outcome and timing unchanged. A private prompt-only activation retry is in preparation. The same frozen Sakai owned Edit pair has started a fresh reverse-order repeat with the baseline first.

Preparing the VUESTIC-01 adapter and shared grader used 33,502 tokens across nine browser-free Luna calls, including rejected drafts. This is separate from the shared projection’s acquisition cost and from both workers’ execution tokens. Since the first held-out run produced no verified use, there is no measured Vuestic saving against which to amortize that setup.

A browser-free Vuestic probe verified that OpenCode forwarded the exact projection request with all three approved pairs. The probe used 2,691 tokens in two model steps. The generated assisted prompt and MCP description now name the action and its arguments. That work used 1,766 tokens in one model step. A fresh matched activation pair is staged with the prior source scenario and evaluator, pending the single browser lease.

The reverse-order Sakai repeat passed all six checks in both arms. The assisted projection again verified all three saved fields in one call. Both runs recorded nine mutation dispatches and closed their tabs. Across the two pairs, the descriptive baseline and assisted medians are 59.895 and 53.772 seconds, a 10.2% reduction (1.11×). Two pairs do not establish statistical significance.

| SAKAI-02 owned Edit projection, reverse order | Wall time (s) | LLM calls | Worker requests | Native calls | Combined tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 57.629 | 21 | 22 | 38 | 43,289 |
| Explorer-assisted | 52.777 | 19 | 18 | 30 | 39,354 |

The browser was released to the staged assisted-first VUESTIC-01 activation pair after both Sakai tabs closed.

The two passing Sakai pairs spent 9–15% of measured wall time in native browser calls. Native call time increased in both assisted runs even though call count fell. Current telemetry cannot separate the remaining time into provider, model, client and bridge costs. The existing serial batch can package worker-selected requests without removing native actions, but it does not directly accept the current Sakai adapter schema. The trace audit found no new operation with stronger evidence than the existing one-read projection. The next measurement task is to instrument the dominant residual without changing the benchmark prompts or checks.

The assisted-first Vuestic activation arm passed all checks in 74.770 seconds and closed its tab. It produced no projection receipt. The matched baseline is running. Even if the baseline passes, this activation pair will only show the effect of offering the capability.

Both VUESTIC-01 activation arms passed, verified absence in both filters and closed their assigned tabs. The assisted worker proved the fields using ordinary reads and had no successful projection receipt. The runner does not log early projection rejections, so the receipt alone cannot distinguish a skipped request from rejection before the read. This pair measures exposure only.

| VUESTIC-01 activation | Wall time (s) | LLM calls | Worker requests | Native calls | Combined tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 71.806 | 20 | 19 | 77 | 87,760 |
| Assisted, no verified projection | 74.770 | 20 | 19 | 76 | 100,233 |

The system-generated timing instrumentation passed offline checks for both Sakai arms and launched a new assisted-first pair. It records native and bridge durations and gaps between allowlisted OpenCode events. Prompts, schema, scenario and existing checks are unchanged. Native durations are nested inside bridge time, and event gaps are not direct provider timings. Staging used 11,143 tokens in three model steps.

The receipt-only VUESTIC-01 runner passed ten offline cases. The generated logging records each projection request that reaches the runner, its phase, disposition and number of native reads. It preserves existing responses, pass criteria and browser calls. A new pair with a fresh matched marker is staged. Requests that never reach the runner remain outside this instrumentation.

The instrumented Sakai assisted arm passed with verified projection use. OpenCode elapsed time was 54.199 seconds. Authorized bridge handlers occupied 6.985 seconds, of which 6.976 seconds were measured inside browser calls. The remaining 47.214 seconds were outside those handlers. Gaps ending at a new OpenCode step accounted for 37.297 seconds on the OpenCode event clock. These can include client, orchestration and model latency. The matched baseline is running.

The instrumented Sakai pair passed all six checks in both arms and verified the assisted projection. Both dispatched nine mutations and closed their tabs. Wall time fell by 23.7% in this pair while tokens increased by 5.0%. Both arms recorded 20 model steps. Baseline OpenCode time was 71.104 seconds, including 6.858 seconds in bridge handlers (6.849 seconds in native calls). Assisted OpenCode time was 54.199 seconds, including 6.985 seconds in handlers. Time outside handlers fell from 64.246 to 47.214 seconds, so the difference in this pair cannot be attributed to browser or bridge duration. The instrumentation does not identify the cause of the remaining variation.

| SAKAI-02 instrumented | Wall time (s) | LLM calls | Worker requests | Native calls | Combined tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 71.260 | 20 | 21 | 37 | 40,334 |
| Explorer-assisted | 54.398 | 20 | 19 | 31 | 42,352 |

The browser was released for the next held-out Vuestic pair with projection-attempt logging.

Across all three passing SAKAI-02 owned Edit pairs, including the instrumented one, median paired time saved was 7.395 seconds. All assisted trials used the same generated projection and verified the complete scenario. The table shows descriptive medians. The two uninstrumented pairs alone showed a 10.2% reduction, compared with 12.5% when the instrumented pair is included.

| SAKAI-02 medians, three pairs | Wall time (s) | LLM calls | Worker requests | Native calls | Combined tokens | Mutation dispatches |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 62.162 | 21 | 22 | 38 | 43,289 | 9 |
| Explorer-assisted | 54.398 | 19 | 19 | 31 | 39,354 | 9 |

The receipt-instrumented Vuestic assisted run passed in 63.668 seconds. The runner recorded one three-field projection request at worker request 5. It arrived before the invalid draft had been verified and was rejected with zero native evaluations. The worker then completed using individual reads and verified both absence checks. The baseline is running. The next Explorer iteration will expose when the projection is available under the current guard.

The receipt-only Vuestic pair ended with an assisted pass and a partial baseline. The baseline verified the fields and validation, then timed out waiting for closure after Cancel and the confirmation. The host still saw multiple DOM dialogs, so the baseline did not run its absence checks. Both assigned tabs closed. The assisted projection attempt was rejected before the browser call. This pair is excluded from successful latency comparisons.

The generated Vuestic availability retry preserves the original rejection predicate and native-call behavior. It adds a bounded reason to an early rejection and clarifies that each worker-selected field needs confirmed draft evidence. The prompt and response adjustment used 1,894 tokens. The fresh matched run has been assigned the single browser. A separate offline Sakai design will evaluate explicit harness batching independently of learned projection use.

The availability-assisted Vuestic arm passed in 63.259 seconds and closed its assigned tab. No projection request reached the instrumented dispatcher. The matched baseline is running. A separate component-validation design will check the current browser binding on a synthetic draft, without submitting it or treating a direct capability probe as a benchmark result.

Both arms of the Vuestic availability retry passed, verified absence in both filters and closed their tabs. No projection request reached the assisted dispatcher. This pair measures offering the capability, with no verified projection use.

| VUESTIC-01 availability retry | Wall time (s) | LLM calls | Worker requests | Native calls | Combined tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 66.126 | 20 | 19 | 75 | 93,478 |
| Assisted, projection unused | 63.259 | 17 | 18 | 76 | 83,532 |

The separate Vuestic diagnostic will check whether the generated guard can resolve the exact Add User dialog and its three approved native inputs while the synthetic draft is open. Vuestic may return focus to the document body, which would make the projection unavailable under its active-dialog requirement even if values match. The diagnostic uses the frozen guard, will not submit the draft and is outside paired measurements.

The live unsaved-draft Vuestic diagnostic verified that the same frozen projection returned three exact matches for the scoped Add User dialog. Independent ordinary reads confirmed each field. At projection time, the exact dialog was uniquely visible, focus was inside it, and each approved native HTML name resolved uniquely. The draft was never submitted. A scoped discard closed the dialogs, the table was visible, and the assigned tab closed. This validates live cross-platform applicability of the read primitive, without measuring worker adoption or speed. The Explorer is staging a fresh trial that exposes positive readiness in an assisted tool response while keeping the worker responsible for selecting reads.

The generated Sakai serial-read integration passed offline checks. Its first comparison offers explicit batching only in the assisted arm and disables learned projection in both arms. The second comparison will give both arms identical batching and add projection only in the assisted arm. Batches contain two or three distinct worker-selected field reads with separate evidence. They do not combine native calls or authorize draft mutations. Generation used 22,906 tokens across seven model steps. The first live comparison started baseline first.

The Sakai batching baseline passed in 57.592 seconds and closed its tab. The batching arm is running. The generated Vuestic readiness change passed 15 offline cases. It adds a small assisted response only after all three eligible draft bindings have exact evidence in the current dialog. It adds no native calls, and the worker still chooses the read and its fields. Generation used 4,331 tokens across two model calls.

Both arms of the Sakai harness-batching comparison passed all six checks, dispatched eight mutations, made 35 native browser calls and closed their tabs. The worker used serial batching and sent four fewer requests. Wall time fell 17.3% and tokens fell 15.9% in this pair. It measures the effect of offering the harness’s serial batch independently of a learned projection.

| SAKAI-02 serial-read harness comparison | Wall time (s) | LLM calls | Worker requests | Native calls | Combined tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Ordinary | 57.592 | 21 | 20 | 35 | 43,025 |
| Serial batch | 47.654 | 17 | 16 | 35 | 36,205 |

The browser was released to the staged Vuestic readiness pair.

The readiness-assisted Vuestic arm was partial. It verified closure and fresh absence, but did not establish the initial field and invalid-email checkpoints. No projection request reached the dispatcher. The assigned tab closed and the matched baseline is running. This arm is ineligible for successful timing comparison.

The readiness-assisted trace did contain exact individual reads of all three fields, but the Full name and Username reads were interleaved with the draft fills. The shared evaluator requires evidence after the final fill and before Email blur, so only the Email read counted there. The browser also showed the invalid message. The scenario stayed partial because the evaluator could not verify the complete draft at that checkpoint.

A browser-free Explorer call reviewed batching distinct draft edits. It requires a fresh exact per-field read after each confirmed dispatch before moving on, and read-only reconciliation after ambiguity. The current Sakai fill response only proves dispatch. Preserving the existing grouped draft checkpoint limits the observed opportunity to about one fewer worker request. That may be offset by additional native preflight and readback, so the proposal remains inactive. Generation used 2,506 tokens in one model call.

The Vuestic readiness baseline was also partial. It passed both validation phases, but the scoped discard was rejected and the host still saw multiple DOM dialogs. Both tabs closed without an Add submission. No projection request reached either runner. The pair is excluded from successful timing. The next Sakai pair started with the same serial batching in both arms and the generated projection available only in the assisted arm.

The equal-batch Sakai assisted arm passed in 58.319 seconds and used the projection after opening Edit. It had access to the same serial-read batch as the baseline but did not invoke it. This arm verifies projection use when batching is also available. The matched baseline and its adoption evidence are still pending.

The equal-batch Sakai pair passed in both arms. The baseline used serial batching and the assisted arm used the projection. The assisted run used five fewer native calls and 14.1% fewer tokens but was 3.4% slower. Worker request count was identical. Both passed all six checks, dispatched nine mutations and closed their tabs. This measured the effect of offering the projection alongside batching, with actual selection left to each worker. A reverse-order repeat is running.

| SAKAI-02 with serial batching available in both arms | Wall time (s) | LLM calls | Worker requests | Native calls | Combined tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline, used serial batching | 56.413 | 20 | 19 | 36 | 41,938 |
| Assisted, used projection | 58.319 | 16 | 19 | 31 | 36,038 |

The offline Vuestic audit distinguished two cancellation failures. One request had exact discard text but a missing or unapproved action label, and the dispatcher rejected it before native action. Another dispatched the exact confirmation once and then timed out waiting for closure. A generated shared schema refinement is being staged to improve the first case. It cannot resolve the second and will preserve the existing one-shot dispatch guard and read-only follow-up.

The reverse-order Sakai equal-batch repeat passed all six checks in both arms with exact tab closures. The baseline used serial batching. The assisted worker used the projection in both create and Edit, each returning three exact matches. The baseline additionally blurred Price. The two equal-batch pairs had opposite latency directions. Their descriptive medians were 54.561 seconds at baseline and 54.856 seconds assisted, so this condition has not shown a latency gain even though both assisted runs used fewer native calls and tokens.

| SAKAI-02 with serial batching available, reverse order | Wall time (s) | LLM calls | Worker requests | Native calls | Combined tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline, used serial batching | 52.709 | 17 | 20 | 38 | 37,063 |
| Assisted, used projection | 51.393 | 15 | 16 | 25 | 32,855 |

The shared confirmation schema and draft-window clarification were generated in one Luna call using 1,559 tokens. The source scenario digest matches the preceding readiness trial. The staged assisted-first pair has now started under the single browser lease.

The clean-checkout audit found that the measured projection currently runs from private frozen overlays. The tracked catalog can store and deliver text hints and prior recipe forms, but has no activation path for this typed observation. Its existing validation requires independent journal evidence, which the private JSON receipts do not supply directly. The next staged integration will represent the Explorer output as bounded data referring to a reviewed runtime operation and preserve the catalog’s existing validation requirements.

The confirmation-schema Vuestic assisted arm passed in 70.106 seconds with verified projection use. Worker request 6 reached the eligible draft phase, made one native read, and returned three exact matches. The same three-field receipt satisfied the field evidence gate. The run verified both absence checks and closed its assigned tab. The matched baseline is running.

The confirmation-schema baseline was partial after one exact discard dispatch. Multiple DOM dialogs remained after the wait, so the baseline did not verify absence. The assisted run also performed the same three individual initial field reads, so its projection receipt establishes worker adoption without showing that the worker eliminated those reads. Neither arm submitted Add, both tabs closed, and no cleanup was pending. The pair is excluded from successful latency comparisons. A fresh reverse-order repeat has been requested with the same frozen runner.

The reverse-order Vuestic baseline passed in 64.323 seconds and closed its tab. The assisted arm is running with the same runner and a fresh matched fixture. Separately, the Explorer emitted an unvalidated data-only projection candidate referencing the frozen runtime and sanitized source provenance. That artifact does not meet the existing journal-backed activation criteria.

The reverse-order VUESTIC-01 repeat ended with a passing baseline and a partial assisted run. The assisted worker used individual reads and did not request the projection. Its exact discard confirmation dispatched once, but the wait timed out with multiple DOM dialogs visible and no native prompt pending. There was no assisted absence witness. Both assigned tabs closed without an Add submission. This pair is excluded from successful latency comparisons. An offline audit will distinguish a dispatch acknowledgement from verified dismissal.

Across the retained Vuestic traces, 20 exact discard confirmations dispatched. Sixteen verified closure and four timed out with multiple DOM dialogs and no native prompt. The click receipt proves pointer dispatch to the checked target. The failure traces lack enough exact post-click observation to identify which dialogs remained. A separate diagnostic using only approved text and dialog observations is being staged without changing timing or grading.

The private catalog prototype requires an exact typed manifest, runtime digest, scoped host event and independent boolean evidence. Its offline tests passed in a clean checkout. It still needs a trusted live receipt producer and stronger source independence checks before activation.

The held-out Sakai scenario audit identified two valid transfer points in SAKAI-03. The projection can compare Name and original Price when opening the exact owned Edit, and Name, Description and updated Price after reopening. The single draft Price check still needs its own read. SAKAI-04’s deletion phase has no eligible form-field observation, so using projection in its shared preparation would not establish transfer to deletion. A generated SAKAI-03 adapter is being staged for offline verification.

The Vuestic diagnostic passed ten offline cases and a mocked transport deadline check. It uses the existing scoped browser wrapper with a two-second budget and records sanitized counts in a separate file only after a dispatched exact discard and a hidden-wait timeout. Measured outcomes and timings remain unchanged. The staged pair has been assigned the single browser lease.

The hardened private catalog prototype now requires distinct raw source digests and binds each boolean receipt to its attempt, runtime, manifest and scope. It passed ten legacy tests and eight offline receipt cases, including a copied-receipt rejection. A staged host integration will connect actual successful frozen-runtime reads to the existing live scenario journal. It has not activated the catalog entry. The first generated SAKAI-03 runner compiled but failed offline integration checks, including unreachable persisted readback and Save, and remains inactive.

The Vuestic diagnostic pair produced a passing assisted run and partial baseline. The baseline’s detached read-only evidence confirmed one visible exact discard message, one exact Add User heading, multiple DOM dialogs and no native prompt after the dispatched confirmation timed out. This shows that both expected surfaces were still represented in the visible UI. It does not distinguish a click handler that did not dismiss them from a dismissal followed by reappearance. No mutation was repeated. Neither arm successfully used the projection, so this pair is excluded from performance comparisons.

The generated Vuestic evidence rule is limited to the assisted prompt. A positive exact field projection counts as the corresponding read while the approved scope and field state remain current. The worker chooses the fields, and a missing or stale result still requires observation. Offline validation confirmed the rest of the runner was unchanged. The fresh matched pair has been assigned the browser.

The Vuestic evidence-rule assisted run passed in 65.967 seconds. The worker requested the projection in the eligible phase and obtained three exact comparisons in one native evaluation. It made zero individual initial draft reads. The projection therefore supplied the required field witness in place of those reads. Both absence checks and exact assigned-tab closure passed. The matched baseline is running.

The Vuestic evidence-rule baseline also passed, including both absence checks and exact assigned-tab closure. The matched pair shows 3.7% lower wall time and 27.0% fewer tokens with the projection. Neither arm submitted Add, and no cleanup was needed.

| VUESTIC-01 evidence-rule trial | Wall time (s) | LLM calls | Worker requests | Native calls | Combined tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 68.519 | 20 | 19 | 75 | 94,179 |
| Explorer-assisted | 65.967 | 15 | 16 | 71 | 68,742 |

Using the existing Sakai equal-batch medians and this Vuestic pair, the two-scenario average is 61.540 seconds baseline and 60.412 seconds assisted, about 1.02×. This exploratory aggregate is not the full scenario panel and does not support a 2× claim. A reverse-order Vuestic repeat with a fresh matched fixture has been assigned.

The reverse-order Vuestic evidence-rule baseline passed in 60.360 seconds with both-filter absence and assigned-tab closure. Its assisted arm is running with the same fresh matched fixture and unchanged capability and instructions. The first pair remains the only qualifying Vuestic substitution comparison until this arm has terminal evidence.

The reverse-order Vuestic evidence-rule repeat passed in both arms with exact absence and closure. Again, the assisted worker used one native projection and no individual initial field reads. It was 1.7% slower and used more tokens in this repeat. The two matched Vuestic pairs give descriptive wall-time medians of 64.440 seconds baseline and 63.668 seconds assisted. With the Sakai equal-batch medians, the two-scenario average is 59.500 seconds baseline and 59.262 seconds assisted, approximately 1.004×. Call reductions repeated, while wall-time and token improvements did not.

| VUESTIC-01 evidence rule, reverse order | Wall time (s) | LLM calls | Worker requests | Native calls | Combined tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 60.360 | 16 | 18 | 75 | 71,491 |
| Explorer-assisted | 61.369 | 18 | 17 | 71 | 87,743 |

The generated held-out SAKAI-03 runner passed offline transition and driver mocks. Its manifest pins both original scenario files, the unchanged projection and matched inputs. A fresh baseline-first live pair has started. Both arms prepare and verify the product through the same unassisted SAKAI-02 path. The comparison times the subsequent SAKAI-03 update separately and requires an exact assigned-tab close before the next arm.

The first live SAKAI-03 launch overlapped a final offline runner edit. The baseline output directory was created at 02:41:12 local time, before the runner and manifest were updated at 02:41:19. The shell had already started the baseline Python process. The two arms cannot be credited as a matched performance pair. Their independent scenario evidence may still diagnose the guarded path. A subsequent comparison must launch both arms from a frozen copy.

The first SAKAI-03 diagnostic baseline passed all five update checks and closed its tab. The main update took 49.217 seconds, with 103.440 seconds from setup through closure. The assisted arm is now running. These timings remain outside the matched comparison because the runner revision changed after the baseline started.

The SAKAI-03 diagnostic assisted arm passed preparation and all five update checks. It used the unchanged projection to verify Name and original Price and then Name, Description and updated Price after reopening. The main phase took 45.504 seconds and the exact tab closed. This verifies transfer to SAKAI-03. Its timing remains unmatched because of the runner edit during the original launch. Both diagnostic tabs are now closed, and a new matched pair has started assisted first from one digest-verified frozen copy.

The private journal launcher passed one positive and eight negative offline cases. It uses three fresh serial worker attempts in a shared journal and evaluates eligibility in a disposable database copy. It does not publish a shared catalog entry. A separate harness experiment is being staged to measure whether allowing a worker to submit one guarded action with explicitly selected read-only checks cuts model round trips. That comparison will preserve the original child evidence and keep learned projection disabled while measuring the harness feature.

The first frozen SAKAI-03 assisted arm passed all six preparation checks, found the exact owned row and dispatched Edit. It then skipped the adapter’s explicit title observation, so the two field reads were refused before any price mutation. The arm closed its tab and did not use the projection. The baseline is running. The next offline change will clarify the existing guard in the shared tool contract without adding a source assertion or modifying the permission checks.

The frozen SAKAI-03 baseline passed preparation and verified the original price, updated entry, updated row and reopened persisted fields. It dispatched Cancel, then asked for table visibility before verifying the dialog hidden. The adapter rejected that request on scope, so the table checkpoint remained unverified. Both frozen arms closed their tabs. The shared contract clarification will expose this prerequisite alongside the title prerequisite for editing.

The shared SAKAI-03 contract now describes the existing title and hidden-dialog prerequisites. Offline AST comparison found changes only to the shared prompt literal, with frozen scenarios, guards, timing and projection unchanged. A digest-verified matched pair started assisted first on the single browser.

The shared-contract SAKAI-03 assisted arm passed all six preparation checks and all five update checks. It verified dialog hidden and table visibility independently after Cancel, used the projection for the scoped field comparisons, and closed its tab. The main update took 51.175 seconds. The matched baseline is running.

The SAKAI-03 clarified-contract baseline read the updated Price successfully, then voluntarily blurred Price. The adapter correctly invalidated the earlier read and refused Save until a fresh read was available. The worker stopped without saving. Both tabs closed. The assisted arm's full pass verifies transfer, but this pair cannot supply matched latency. A private shared metadata refinement will explain that any later fill or blur invalidates the prior field witness.

The separate Sakai action-plus-evidence batching pair started baseline first. Both arms have serial read batching and no projection. The assisted worker can optionally pair one explicitly selected guarded click with one explicitly selected read-only check. Offline safety checks confirmed that ambiguous effects block additional writes and never cause automatic replay.

The action-plus-evidence batching baseline passed five checks and verified Cancel dismissal, but omitted the required final exact row read. It closed its tab. Its 46.368-second duration is ineligible for a matched speed comparison. The assisted arm is running. The next SAKAI-03 cohort is staged with only the shared fresh-Price-evidence note changed, as verified offline by AST comparison.

The action-plus-evidence assisted arm passed in 53.479 seconds and closed its tab, but never used the combined action operation or serial reads. Its matched baseline was partial. This pair provides no measured harness effect. The browser was released to the next SAKAI-03 cohort. Both arms in that cohort have an identical shared reminder that fill or blur invalidates prior field evidence. The baseline started first from the digest-verified stage.

The fresh-witness SAKAI-03 baseline passed all five update checks in 47.540 seconds and verified its assigned-tab close. The same-cohort assisted arm is running. The baseline independently verified current price after its last draft change, successful Save, fresh owned row and persisted readback, then dismissal and table visibility.

A browser-free OpenCode probe confirmed that the exact combined-action request can reach the staged Sakai dispatcher. The retry clarifies the required dismissal and final owned-row evidence in both arms, and names the optional combined request in the assisted description. The Explorer changed only prompt and metadata. Probe cost was 2,339 tokens across two steps, and the revised wording cost 1,427 tokens in one step.

Both fresh-witness SAKAI-03 arms passed all five update checks and closed their tabs. Main-phase time was 47.540 seconds baseline and 46.009 seconds assisted. Both made 19 worker requests. The assisted worker never used the projection, so this pair measures offering it only. The separate combined-action activation trial started after exact closure of both SAKAI-03 tabs.

Current latency evidence is inconclusive for a cross-platform gain. Each equal-batch scenario has two qualifying pairs, and the observed within-arm wall-time ranges overlap between modes. The instrumented Sakai run attributed about seven seconds to native browser work, leaving most time outside the bridge. The smaller browser-call counts alone cannot account for a 2× improvement. The current host load was 1.68 over one minute on eight logical CPUs during the combined-action activation run. That is a spot check, not a complete host-load record for the historical trials.

The combined-action activation assisted arm passed all six checks in 59.964 seconds and closed its tab. It made no combined-action request. The matched baseline is still running. This arm does not measure the combined operation.

Both combined-action activation arms passed all six checks and closed their tabs. The baseline took 50.456 seconds and the assisted arm took 59.964 seconds. No combined-action request was recorded, so this is an exposure result. The browser moved to the separate journal-backed live validation. That run uses fresh serial assisted attempts and checks catalog eligibility only in a disposable database copy. Its timings are not included in the benchmark.

The live journal launcher stopped after attempt zero. SAKAI-02 passed all six checks and closed its assigned tab, and each checkpoint had a journal artifact. The worker used only ordinary reads, so the separate candidate verdict was INCONCLUSIVE. The launcher refused to count it or proceed to another attempt. No eligibility decision or publication occurred. The next validation-only prompt will make clear that a positive trial requires fresh use of the candidate in an eligible scope.

A fresh SAKAI-03 activation pair started assisted first from a digest-verified private copy. The sole change is an Explorer-generated assisted note naming the projection arguments and explaining that exact grouped comparisons satisfy the same field witnesses as individual reads. The baseline prompt, scenario, runtime and source grading remain unchanged. The journal-validation activation stage is still separate.

The generated validation-only prompt now asks for one fresh projection invocation when eligible independent field checks are needed. Offline checks verified that ordinary benchmarking prompts, schema, evidence gates and journal code remain unchanged. The retry remains separate from performance measurement and will start after the SAKAI-03 pair releases the browser.

The SAKAI-03 discovery-assisted arm passed all five update checks in 52.708 seconds, used the projection, and closed its tab. The matched baseline is running. Separately, the trace review found at most three adjacent action/read pairs for the existing combined operation. Halving the observed model-step counts would require larger reductions. The Explorer is evaluating a bounded, worker-selected multi-operation request with explicit evidence dependencies. This is an untested hypothesis and does not store or replay scenario workflows.

The SAKAI-03 discovery baseline verified the updated row, but stopped before reopened field verification and final table readiness. Its main phase was 91.614 seconds and the tab closed. This partial result is excluded from matched timing. The catalog validation retry started with a fresh private capture after both SAKAI-03 tabs closed.

The second live catalog run stopped before starting a worker because the local Sakai reset screen failed its readiness check. HTTP navigation succeeded and the assigned tab closed. A separate read-only probe using the unchanged predicate reproduced the failure for the bounded six-second window and closed its tab. The fixture is under diagnosis. No candidate receipt or activation was recorded.

The Explorer generated a data-only contract for a larger worker-selected request and verified its structure. Dependencies reference an earlier operation and a host-approved predicate. The executor must check actual fresh evidence and stop before an unresolved or ambiguous effect. Executable mocks and runtime remain pending, and the 2× target remains a hypothesis.

The local Sakai HTML, main assets and recursively referenced CRUD assets served successfully with correct content types. The read-only fixture diagnosis verified 77 local JavaScript and CSS resources byte-for-byte against the Vite build. The product data is already part of the app bundle. This narrows the reset failure to runtime or readiness conditions rather than a missing static file. The next diagnostic will report only the boolean predicates in the existing readiness check.

The live boolean-only Sakai diagnostic confirmed the expected loopback route and an interactive document. The Vue app did not mount within 16 seconds, and the search field and table were absent. The diagnostic tab closed. This establishes a fixture startup failure before any benchmark worker action. The reason for the failed mount is under investigation.

The larger-operation executor remains inactive. Offline mocks showed that an equivalent mutation with a fresh request ID can reach the existing transport while the first action's effect is unresolved. Existing batch guards reject multi-mutation requests. The next prototype will test a stable host-derived effect identity and an atomic pre-dispatch check while preserving the existing one-shot and scope checks.

A clean headless Chromium profile mounted the same local Sakai build and showed the search field and table. That separates static app health from the readiness failure observed in the existing Browse-driven session. The headless run is a fixture diagnostic only. No benchmark browser profile or application state was changed.

A new scoped Browse-driven tab still failed the same readiness predicate while a clean headless profile mounted the app. The bounded console probe recorded no recognized startup error category and closed its tab. Its empty-category result cannot rule out console errors because the response envelope was not decoded for entry count. The next diagnostic will inspect only resource lifecycle booleans and the documented console response shape.

The Browse resource diagnostic observed completion of the local entry module, the CRUD chunk, the external stylesheet, DOMContentLoaded and window load. The Vue root still had no children. The decoded bounded console result contained zero error entries and no truncation indicator. Resource timing confirms recorded load completion, not successful app execution. The exact diagnostic tab closed.

The generated stable-effect proof passed four new offline tests and 24 existing tests. Under one owned attempt and tab, the journal blocked the same host-approved effect when the worker changed the request ID or used an alias. Two distinct approved effects still dispatched. The next proof will test blocking all further plan writes after an unresolved effect until authorized reconciliation. No multi-operation executor is active.

With no tabs open, the dedicated loopback Browse relay was restarted using its existing settings. The extension reconnected. A new diagnostic tab passed the original, unmodified Sakai readiness predicate in 3.0 seconds and closed. This establishes recovery after relay restart, though it does not identify the original startup cause. The serial catalog validation has restarted from a fresh private capture.

The post-restart catalog trial reached the worker. The click on New was dispatched, the next exact dialog read returned false, and the worker stopped after one further observation. The retained trace cannot distinguish a delayed dialog from a title mismatch. The attempt was partial, used no generated projection, and closed its assigned tab. The candidate remains inconclusive and the attempt is excluded from performance comparisons.

A follow-up diagnostic failed the original readiness check before dispatching New and closed its tab. The dedicated QA browser was restarted with the same profile and scoped extension. A fresh catalog trial then started with one prompt change that permits the worker to repeat the exact read-only title check once after a negative result. The scenario, candidate manifest, browser adapter and runtime are unchanged. This is a validation trial.

The first restart left the dedicated browser process stopped before the launcher could open an assigned tab. A supervised Chromium process then connected its scoped extension to the dedicated relay. Browse reported the extension connected and zero tabs before a fresh validation capture started with a new seed.

The reconnected trial stopped before the worker started. The original reset readiness predicate failed again, and the assigned tab closed. This reproduces the startup issue after restarting both the relay and the dedicated browser. The title recheck guidance was never exercised.

A serial probe compared two Browse tab startup paths in the same dedicated browser. Opening a blank tab and navigating produced one read timeout followed by two completed reads with an empty Vue root. Opening a fresh scoped tab directly at the same local URL passed all three observations, including the search field and populated table. Both assigned tabs closed. This single comparison identifies a fixture startup workaround for validation. Its timing is excluded from the benchmark.

A second comparison reversed the startup order. The direct tab passed both readiness reads. The blank-then-navigate tab timed out on the first read and passed the second. Both tabs closed. Across these probes, direct opening avoided the observed first-read timeout and passed every sample. Blank-then-navigate can eventually mount, so the observations do not establish a permanent failure or its cause.

The Explorer generated a private launcher that opens the exact allowed URL directly. Offline checks covered both arms and rejection of an unexpected route and close ID. The launcher preserves the original readiness predicate, scenario and candidate hashes, and requires closure of the numeric tab ID returned at startup. A fresh serial catalog validation run started from that launcher. Its results are separate from earlier timing cohorts.

The direct-open launcher verified the tab and its exact closure in the live trial, but the unchanged readiness gate failed before the worker began. The successful command-line probes used independent processes and a three-second per-read timeout. The launcher uses a persistent transport and a one-second per-read timeout. Another diagnostic will retain the read statuses to distinguish a timeout from a completed false predicate.

An exact-predicate transport comparison reproduced the persistent MCP failure. The tab opened with the expected scope, the first one-second read was unavailable, and the next reads returned false at both timeout settings. Independent command-line probes on fresh direct tabs returned true for the same predicate at both the three-second and one-second settings. All three assigned tabs closed. The command-line result rules out the one-second setting as the sole explanation and motivates a diagnostic of tab startup and transport handoff.

The startup handoff worked when the command-line client opened the exact scoped tab and performed the first readiness read. The persistent MCP connection then returned true for the same predicate using both the assigned alias and numeric tab ID. When persistent MCP read first on a different fresh tab, it returned unavailable and the following command-line read failed too. An explicit numeric close removed that diagnostic tab. Both probes ended with an empty dedicated relay. These are startup observations only.

The Explorer also generated and tested a private bounded wait for a worker-selected exact UI predicate. Four mocks covered a false-to-true transition, deadline, concurrent generation change and an unresolved preceding effect. Seven earlier scope and recovery tests passed. The wait still needs a trusted live binding and a native deadline per sample. It has no timing credit.

A system-generated persistent-transport diagnostic opened two fresh direct tabs and verified both identities and exact closures. The three-second arm returned one completed false read and one unavailable read. The one-second arm returned seven false reads and one unavailable read. This reproduces the failure at both settings. A successful command-line first read followed by persistent MCP is the observed startup path to carry forward.

A persistent MCP probe added three seconds between exact direct open and its first readiness read. That tab returned true twice. A separate tab read immediately returned false and then unavailable. Both assigned tabs closed. The first successful read took 9.54 seconds end to end despite a one-second evaluation timeout. The checked-out Browse source shows that its timeout recovery can terminate JavaScript in an unresponsive tab. Startup interference is a hypothesis. The probe does not establish that Browse interrupted Vue in these runs.

The Explorer generated a validation-only launcher that verifies scoped tab creation and requires a true result from the first command-line readiness check before persistent MCP rechecks the same tab. Offline mocks verified the call order, rejection of false readiness and rejection of a mismatched close ID. A fresh serial validation trial started after the relay reported zero tabs. This startup variant has no timing credit.

The first trial reached OpenCode and passed all six SAKAI-02 checks. The worker invoked one generated projection in the owned Edit scope and received exact positive booleans for Name, Description and Price. The host recorded all six checkpoint artifacts and a candidate PASS, and the assigned tab closed. Worker time was 62.980 seconds with 20 model calls, 19 worker requests and 31 native calls. The launcher advanced to the second fresh trial. Three qualifying trials are required for the scratch catalog check.

All three fresh CLI-first validation trials passed SAKAI-02 and used the system-generated projection exactly once to verify Name, Description and Price in the owned Edit dialog. Each trial recorded six checkpoint artifacts and an exact tab close. The worker times were 62.980, 54.612 and 58.240 seconds. The journal recorded three finished attempts with no remaining tab lease. The scratch catalog accepted the generated capability. The shared catalog was not activated, and this assisted-only validation series is excluded from speedup calculations.

The three qualifying catalog trials consumed 175.831 worker seconds, 184.191 setup-to-close seconds, 54 model calls, 59 worker requests, 97 native browser calls and 129,644 combined tokens. These are successful validation costs. Candidate generation, failed attempts and fixture diagnosis add further cost. The cohort does not support an acquisition break-even estimate.

A fresh same-boot SAKAI-02 timing pair started baseline first. Both arms use the verified CLI-first startup and the same scenario, synthetic data and mutation authority. Assisted additionally exposes the validated read-only projection. Neither arm receives the validation-only adoption instruction. This is a separate cohort from earlier boot paths.

The first same-boot SAKAI-02 pair passed all six checks in both arms and closed the assigned tabs. The assisted arm used one projection with all three independent matches. Worker time fell 21.7% in this pair, and setup-to-close time fell from 99.904 to 75.857 seconds. Model calls and mutation dispatches were unchanged. The assisted arm used 3.3% more combined tokens. This is a single pair with a changed startup path. A reverse-order repeat with fresh matched inputs started from the same frozen runner.

| SAKAI-02 CLI-first pair | Worker time (s) | Model calls | Worker requests | Native browser calls | Mutation dispatches | Combined tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 89.244 | 17 | 22 | 38 | 9 | 37,574 |
| Assisted | 69.892 | 17 | 20 | 33 | 9 | 38,824 |

The CLI-first reverse-order repeat also passed all six checks in both arms and closed the assigned tabs. The baseline took 77.258 worker seconds and the assisted arm took 66.420. The assisted worker used the projection once for the three independent Edit comparisons. Both trials in this cohort had five fewer native calls and two fewer worker requests with projection. The descriptive wall-time median fell 18.1%. Token use rose in the first pair and fell in the reverse pair.

| SAKAI-02 CLI-first pair, assisted first | Worker time (s) | Model calls | Worker requests | Native browser calls | Mutation dispatches | Combined tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 77.258 | 23 | 22 | 38 | 9 | 49,689 |
| Assisted | 66.420 | 17 | 20 | 33 | 9 | 39,323 |

The browser moved to a fresh matched VUESTIC-02 trial. The Luna-generated adapter makes the unchanged projection available for independent checks of the four native draft fields. Thirteen offline cases covered exact matching and rejected stale or ineligible requests. Both arms retain the original dialog, default, persisted Edit, and table checks. The next arm may begin only after the matching synthetic fixture is verified absent in both filters.

The VUESTIC-02 baseline passed all five original checkpoints and closed its assigned tab. It took 83.996 worker seconds, 15 model calls, 23 worker requests, 76 native calls and 49,051 combined tokens. A separate owned cleanup confirmed absence in both filters and closed its tab before the assisted worker began.

The VUESTIC-02 assisted arm passed the same five checkpoints and closed its assigned tab. It used four ordinary draft reads and made no projection request. Separate cleanup confirmed absence in both filters and the relay returned to zero tabs. These figures measure offering the projection. The arm used one more worker request, one more native call and 23.2% more tokens. The next fresh pair will test whether naming the optional action in the worker instructions changes uptake.

| VUESTIC-02 projection offered | Worker time (s) | Model calls | Worker requests | Native browser calls | Combined tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 83.996 | 15 | 23 | 76 | 49,051 |
| Assisted, projection unused | 83.779 | 15 | 24 | 77 | 60,442 |

The proposed single-draft-action envelope would preserve existing native calls and evidence checks. A trace audit found three eligible adjacent pairs in one passing Sakai trace, up to one in another, and four in the passing Vuestic baseline. These are upper bounds on saved worker requests for the audited traces. The proposal remains inactive and supplies no timing evidence.

A fresh VUESTIC-02 repeat started assisted first. The only assisted runner change is a Luna-generated instruction naming the optional projection action and its field argument, with ordinary fallback. The runner does not require projection use or specify a sequence. The original scenario, baseline runner, evidence gates and cleanup are unchanged.

Both VUESTIC-02 reverse-order arms passed all five checks, closed their assigned tabs, and independently verified cleanup in Active and Inactive. The assisted arm again used zero projection calls. The wall-time difference describes this pair's exposure to the capability. It cannot be attributed to grouped reads.

| VUESTIC-02 projection offered, assisted first | Worker time (s) | Model calls | Worker requests | Native browser calls | Combined tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 112.390 | 24 | 23 | 76 | 75,907 |
| Assisted, projection unused | 84.259 | 15 | 23 | 77 | 50,785 |

A fresh VUESTIC-04 baseline started its independent preparation after the final VUESTIC-02 cleanup. After a confirmed Delete dispatch, the generated runner keeps the actual dialog-close outcome and allows the prescribed reload searches only after a fresh check confirms there is no native prompt. The freshness and ownership gates still apply, and a second Delete is unavailable.

The Explorer generated a private prototype for worker-selected ordered draft operations on the disposable local fixture. Nine offline cases used the original Sakai guards. One successful mock reduced five worker submissions to one while preserving the same eight native calls in the same order and retaining the original check results. Live timing awaits integration under one entry point that also gates ordinary worker requests.

The fresh VUESTIC-04 baseline passed all three original checks. It observed the exact owned confirmation twice, verified Cancel preserved the record, and dispatched one Delete. The dialog-close check timed out. The same worker then completed fresh Active and Inactive searches and verified absence in both. Preparation and scenario tabs closed, and the scenario had no remaining cleanup. The main worker made 12 model calls and 11 worker requests using 18,461 combined tokens. This baseline has no matched timing comparison.

A separate VUESTIC-02 activation validation began after the VUESTIC-04 lease closed. An offline MCP round trip confirmed that the optional action and required fields array are in the exposed schema. This validation asks for one eligible fresh projection call and preserves all original scenario and cleanup checks. It is excluded from performance measurement.

The VUESTIC-02 activation worker passed all five original checkpoints and called the generated projection once. One native evaluation returned exact matches for Full name, Username, Email and Notes. The trace retained only one ordinary field read, for Notes in the independently reopened Edit dialog. Both the scenario and cleanup tabs closed. Fresh Active and Inactive searches verified absence after cleanup. Validation took 85.757 worker seconds, 18 model calls, 20 worker requests, 74 native calls and 72,704 combined tokens. The activation-specific prompt asked the worker to try the capability once, so this run validates real use without supplying a matched time comparison.

A fresh VUESTIC-02 timing pair started baseline first. The generated assisted instructions make the grouped read optional and distinguish successful fill receipts from independent exact equality evidence. The baseline, original scenario, guard implementation and serial owned cleanup match the prior timing stage. This pair tests optional adoption in a fresh fixture.

The VUESTIC-02 optional-use baseline passed all five checks in 67.061 worker seconds and verified owned cleanup. The assisted worker received the same four field handles in a verified Add dialog but reported that fields were unavailable. It issued no fill, projection or Add submission. It dismissed the draft and closed its assigned tab. No assisted cleanup was needed. The 38.243-second partial result is excluded. The next offline audit will test whether keeping the ordinary tool schema flat improves discoverability while preserving the dispatcher checks.

A private SAKAI-02 draft-plan pair started baseline first after the dedicated relay reported zero tabs. The assisted worker can submit an explicit ordered set of existing draft actions and paired observations. Both arms use the same ordinary guards and verification, and the learned read projection is disabled in both arms. The launcher separately counts worker requests, plan invocations, plan steps and native browser calls. Offline tests covered eight gateway cases and both launcher paths. In the mocked scenario segment, worker requests fell from six to three while all ten native calls, the original evidence and exact tab closure were preserved.

The first live SAKAI-02 draft-plan trial verified real adoption. One assisted request ran six existing guarded leaves. Three fills dispatched, and all three independent field comparisons matched. The original draft checkpoint passed without latching the runner. The baseline passed the full scenario in 71.872 worker seconds. The assisted worker stopped before Save at 33.508 seconds. Exact tab closure was verified in both arms. The assisted total included an outer request with no guarded leaf trace. Its purpose and outcome were not retained. The partial result is excluded from end-to-end timing. A repeat will retain bounded outer request status and preserve the ordinary path after the draft plan.

The browser then started the VUESTIC-02 flat-schema trial. The assisted schema adds the optional projection action and fields argument to the existing ordinary shape. Eight offline negatives failed before native access. The earlier partial run does not establish whether the nested schema caused the worker to stop. The fresh live pair retains the original scenario and strict owned cleanup.

An offline transfer audit found that Vuestic can reuse the draft plan decoder and executor once its host binds the original guarded fill and read requests to the active owned dialog. Four explicit fill/read pairs fit within the eight-operation limit. Vuestic's fill callback already checks the entered value, but the original scenario still uses an independent ordinary read for the draft checkpoint. The proposed plan preserves both checks. It could reduce model round trips, while the existing projection saves native reads. No Vuestic planner has been activated.

The VUESTIC-02 flat-schema baseline passed all five checks in 82.819 worker seconds. The assisted worker verified the draft, creation, persisted identity and the Notes value without invoking the projection. The Edit Role and Projects defaults remained unverified after the Role expansion, and Cancel was not actionable. That arm was partial at 73.922 worker seconds. Separate owned cleanup confirmed absence in both filters for both arms. All assigned tabs closed. The pair does not establish that schema shape affected use or speed.

The next SAKAI-02 draft-plan pair started assisted first after the Vuestic cleanup. Both arms record bounded request and outcome classes, with underlying leaf counts. The generated assisted prompt asks the worker to inspect each returned receipt and finish any remaining scenario steps through ordinary guarded actions. The plan still excludes Save.

The reverse-order SAKAI-02 draft-plan pair passed all six checks in both arms. The assisted worker invoked one complete six-leaf plan and continued through Save, persisted Edit readback and table verification. It reread all three successfully verified draft fields without intervening mutations, then blurred Price and reread it. The three immediate rereads added six native calls. The worker made two fewer top-level requests but used the same number of model calls. This pair shows live end-to-end planner use with no speedup.

| SAKAI-02 draft plan, assisted first | Worker time (s) | Model calls | Worker requests | Native browser calls | Mutation dispatches | Combined tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 53.261 | 18 | 23 | 40 | 9 | 40,148 |
| Assisted, one six-leaf plan | 56.018 | 18 | 21 | 46 | 9 | 42,261 |

The Vuestic Edit-defaults audit found identical initial widget evidence and bindings in both flat-schema arms. The assisted Role expansion dispatched, but the final popup sample still matched the initial closed state. The trace cannot distinguish delayed rendering, a popup that never opened, or a transient popup between samples. A bounded read-only diagnostic can sample after one expansion while preserving the requirement for a fresh exact linked popup before collapse.

A fresh baseline-first SAKAI-02 pair started with a generated clarification for the optional draft plan. Positive child reads supply the original exact evidence until the relevant state, scope or scenario timing changes. Dispatch acknowledgements still do not count as equality evidence. Only the assisted prompt changed. The scenario, guards, schema and counters are identical to the previous pair, and the baseline prompt is unchanged.

A trace audit used the passing 23-request Sakai baseline to estimate how much an ordered plan could remove while preserving the original actions and checks. Grouping only an authorized Save and its closure check plus read-only Edit observations gives an estimated floor of 13 worker requests. If the worker could also select verified scope transitions such as search, owned Edit and closure, the arithmetic floor would be six. These are trace-based bounds. The current implementation cannot execute the wider groups, and the prior live pair used 18 model calls in both arms despite different worker request counts. Neither bound estimates latency.

Both arms of the Sakai receipt-clarification pair passed all six checks and closed their tabs. The assisted worker never invoked the plan. Worker time was 61.460 seconds baseline and 59.622 seconds assisted. Both made 21 model calls, 22 worker requests and 38 native calls. Combined tokens were 43,835 baseline and 46,670 assisted. This pair measures offering the plan. It does not test whether accepting fresh child receipts avoids duplicate reads.

A Vuestic draft-plan mock verified the original field callbacks through a fake Browse boundary. Ordinary and planned execution produced the same eight child receipts and the same 17 native call signatures. A successful fill followed by a failed independent read stopped the plan. Runner integration remains unverified, so this result supplies no browser or latency evidence.

The live Vuestic diagnostic opened an empty Add dialog and expanded Role once. The first post-expand sample verified one linked popup with three approved options and exactly one selected User. A fresh matching sample preceded one collapse and a closed-state read. The exact diagnostic tab closed. The first positive sample was 958 milliseconds from diagnostic start, including the initial read and dispatch overhead. This run provides no Edit-specific timing or explanation for the prior failure. It performed no field entry, option selection or Add submission.

The isolated Sakai Save plan passed eight offline cases through the original guard. It preserves the exact worker-selected Save and closure leaves, rejects missing closure or duplicate Save, and blocks replay after uncertain dispatch or failed closure. Integration into the paired runner remains unverified.

The Sakai Save-and-closure gateway passed the original runner mocks in both arms and exposed the expected schema through MCP. The worker-selected plan reduced 12 requests to five in the mocked segment, with identical 18 native calls and the same checkpoints. The original ownership guard still refused Edit until the worker verified the owned row. This is an offline result. A fresh live matched pair will test actual use and timing.

The first live Sakai Save-and-closure plan pair started assisted first with a fresh matched fixture. Both arms retain the original checks, one-shot mutation guard, native-call accounting and exact tab closure. The assisted worker can explicitly select the already authorized Save and its independent closure observation in one plan. The baseline uses the original tool schema. The draft and Save pilot keeps the learned read projection disabled in both arms.

Both arms of the first Sakai Save-and-closure timing pair passed all six checks and closed their assigned tabs. The assisted worker made zero plan calls. Worker time was 58.810 seconds baseline and 56.493 seconds assisted, with 22 model calls and nine mutations per arm. Native calls were 40 and 36, and combined tokens were 46,399 and 50,127. This result measures exposure to the capability and adds no evidence of plan speedup.

The private Vuestic runner passed a focused draft test through its original HTTP bridge and dispatcher. Four guarded fills and four independent reads set the original draft checkpoint in both arms. The assisted mock added nine exact scope evaluations, one at plan admission and one before each leaf. The existing field checks verify the active visible field and value but do not independently verify the dialog title. A live test still needs the established Add and cleanup guards and a successful ordinary continuation after the plan.

A fresh VUESTIC-02 activation pilot started on the dedicated browser. It requests one eligible worker-selected plan and preserves the original create, persisted readback, and exact owned cleanup. The focused offline tests exercised the real runner and original guarded Add path. Both arms could reach the ordinary retrieval path. The planned arm submitted Add once across two requests, and a failed independent field read blocked later submission. Defaults and persisted search responses were mocked, and Edit and table return were outside that mock. The live pilot has no timing credit.

The Vuestic draft-plan activation was partial. The worker received a verified Add dialog, four live field handles and an exact title observation. It attempted two plans, but neither reached the guarded field dispatcher. No fill or Add submission occurred, and the assigned tab closed. Cleanup was unnecessary. The retained counts do not distinguish a rejected plan shape from a scope check failure. The next offline audit will preserve that distinction without recording payloads.

The separate Sakai commit activation started after the Vuestic tab closed. It asks for one eligible use of the worker-selected plan containing the authorized commit and its exact closure observation. The validator requires both original leaves in the same completed plan, all six scenario checks, and the exact tab-close receipt. This single assisted run is excluded from timing.

The Sakai commit activation passed all six checks in 50.774 worker seconds and closed its assigned tab. It made no plan request. The exact-use validator returned false, so live Save-and-closure plan use remains unverified. A separate fresh matched pair started with a prompt that prefers eligible grouped calls while keeping ordinary fallback available.

The Vuestic reject audit accounted for every native evaluation using the four recorded ordinary requests. Neither attempted plan reached the live scope check or a guarded leaf. This points to envelope validation before dispatch. The retained evidence cannot distinguish a missing steps argument from unexpected extra keys. No raw worker payload was retained or inspected.

The preference-timing Sakai pair passed all six checks in both arms and closed both tabs. The assisted worker still made no plan request. Worker time was 54.115 seconds baseline and 51.540 seconds assisted. Model calls were 18 and 20, worker requests 22 and 21, native calls 38 and 37, and combined tokens 39,173 and 46,256. The pair supplies no evidence of planner speedup.

The next transport experiment isolates discovery of the plan from the ordinary tool schema. The proposed assisted-only named plan tool would forward its worker-selected leaves to the same guarded host. The baseline and the assisted ordinary tool keep the original schema. A browser-free selection test will first check whether a worker can see and call that tool through the real MCP bridge. No browser actions are enabled in that test.

A separate offline fixture exercised the original search, owned Edit and close callbacks with fake native I/O, preserving the assigned tab and all six Sakai checks. Integration of those callbacks into the ordered plan is still unverified.

The separate named MCP plan tool passed a browser-free subscription test. OpenCode selected that tool and the real bridge forwarded exactly one worker-selected plan to a fake host. The ordinary descriptor was unchanged, and malformed or unknown routes were rejected before a host call in the transport tests. This proves provider-visible selection and serialization. It supplies no browser timing or evidence of optional adoption during a full scenario.

The Vuestic admission diagnostic records up to eight fixed reason codes without retaining request data. Twelve offline cases preserved the tool schema, worker replies, ordinary dispatches and native callback counts. The diagnostic can distinguish a missing steps argument, extra outer keys, scope rejection and invalid child shape in a future run.

The original Sakai runner mocks passed through the two-tool bridge with exact native-call parity and tab closure. The timeout audit found that the plan checks its ten-second deadline before each child. An admitted Save or field read can still wait on two native calls, so the existing 18-second HTTP wait can end before the host finishes. The separate plan route needs a wait long enough for the bounded native receive path. The ordinary route retains its existing timeout.

Vuestic's staged pilot reuses the same two-tool bridge and keeps its original flat ordinary schema. Offline wire and dispatcher checks verified exact named routing, five malformed-request refusals, original field receipts, one-shot Add, and a blocked Add after a false independent field read. The mock used supplied default and persisted-search responses and did not exercise Edit or table return. Live verification awaits the shared timeout update.

A mock client-disconnect test exercised the original Sakai Save guard. Both positive and uncertain host outcomes blocked a repeated Save and a repeated plan without another native effect. If closure remained uncertain, the host also blocked the next search. If the host independently verified closure, a later explicitly requested search remained available. The host cannot prove that the worker received the final receipt. The Sakai plan route will use a 35-second receive timeout for the bounded native wait path. Vuestic needs a separate host budget because its scope and field guards can exceed that window.

The bounded Sakai bridge passed the offline wire and original-runner checks after the timeout update. A live validation run then started on the disposable local fixture. It uses the separate named plan tool and requires an exact guarded Save and closure receipt in the same completed plan, all original checkpoints, and exact tab closure. It remains separate from matched timing.

The live named-tool Sakai validation passed all six checks and closed the assigned tab. One completed named plan ran six guarded draft leaves, and the worker did not repeat their successful reads. A later plan request was refused after an ordinary Price blur and fresh read. An owned Edit plan request was also refused. The worker completed Save, closure, and Edit through ordinary guards. The validator correctly recorded zero completed commit plans. This proves live named draft-plan use and identifies two scope boundaries to address.

After Sakai closure, a fresh Vuestic named-tool activation started. It uses the shared 35-second plan-route shim and a ten-second host receive budget applied only during a plan. Offline fake-clock and dispatcher checks verified that expired budgets prevent later sends and stop after a failed or uncertain field read. The budget cannot interrupt a blocked OS pipe write. The pilot retains the original one-shot Add and owned cleanup, and has no timing credit.

The Vuestic named-tool activation passed all five original checkpoints. One worker-selected plan performed eight guarded children, covering four draft fills and four independent matching reads. The worker completed Add, persisted identity and Notes checks, and table return through ordinary tools. It made 17 actual worker requests and 91 native calls in 62.503 worker seconds, with 14 model calls and 56,293 combined tokens. Both assigned tabs closed, and cleanup verified absence in Active and Inactive. The validation asked for an eligible plan, so this establishes live cross-platform operation without measuring speedup.

The next Sakai matched pair started baseline first with the separate plan tool available only in the assisted arm. It retains the original checks and reports use of draft and commit leaves separately. A separate Vuestic timing fixture is being prepared.

Both arms of the named-tool Sakai timing pair passed all six checks and closed their assigned tabs. The assisted worker did not invoke the named plan. Worker time was 60.838 seconds baseline and 119.513 seconds assisted. Both used 22 model calls. Combined tokens increased from 46,269 to 58,044. Summed native guard time was 7.926 and 7.351 seconds, so the wall-time difference arose outside those measured native calls. This run cannot attribute the difference to an executed plan or identify its cause.

The scope audit traced the prior refusals to two different conditions. Ordinary Price blur revoked draft-plan eligibility even after a fresh positive Price read. The owned Edit view exposed read-only fields, while the draft gateway expected both fill and read capability. The proposed changes restore only the exact applicable scope while retaining the original field, Save and ownership checks.

The first matched timing pair for the Vuestic named plan started baseline first. Both arms use the same fresh synthetic fixture, original five checkpoints and independently verified cleanup between arms. The assisted worker can choose the named plan without an activation requirement. The runner reports actual forwarded worker requests separately from guarded child calls and native observations.

Both Vuestic arms passed all five checkpoints and verified absence in Active and Inactive after cleanup. All four assigned tabs closed. The assisted worker chose one plan containing eight guarded field operations. Actual worker requests fell from 23 to 16, while model calls rose from 14 to 16 and nine extra native evaluations were recorded. Other native call counts were identical. Wall time rose from 56.026 to 60.555 seconds, and combined tokens rose from 45,061 to 52,572. This matched pair confirms optional plan use and a reduction in worker requests. It shows no latency gain.

The Vuestic native-call audit attributed the nine extra evaluations to one plan admission check plus one fresh scope check before each of the eight children. The current native fill locator can target an editable field in any visible dialog, so dropping its separate exact scope proof would weaken the boundary. A read-only child can potentially return exact dialog and field equality in one isolated native evaluation. The next mock will verify that combination using an explicit host-known child identity and preserve the fill checks.

The Sakai post-blur change passed ten offline tests through the original guard. After blur, only a fresh positive read of the affected field restored eligibility for a commit-and-closure plan. A title read alone, a wrong or false field read, and uncertain blur did not restore it. A harmless same-scope read could precede the required field read. The restored scope did not authorize draft writes or a repeated commit. Live validation remains pending.

A fresh Sakai validation started with only the post-blur scope change. The audit checks for an original blur, a fresh exact Price read, and guarded Save plus closure in the same completed plan. All original scenario checks and exact tab closure still must pass. This run is outside timing.

Sakai's live post-blur validation passed all six checks and closed the assigned tab. After the ordinary blur and a fresh exact Price read, one completed plan contained the original one-shot Save and independent closure check. Both the full-use and post-blur auditors returned true. The run took 71.387 worker seconds with 22 model calls, 20 worker requests, 36 native calls and 58,377 combined tokens. This validates commit use and carries no matched speed credit.

The isolated Vuestic read optimization reduced native calls from 24 to 20 within an eight-child mock, excluding the common admission check. All 16 original field-call signatures and four fill-scope checks were preserved. Each combined read evaluated the exact dialog and field equality together. Wrong scope, duplicate binding, mismatched value and deadline failures still stopped execution. The candidate needs full runner integration and live evidence.

The integrated Vuestic mock passed through the original dispatcher and named MCP route. Assisted evaluations fell from 28 with separate scope probes to 24 with combined reads. The ordinary baseline used 19. All eight original field receipts and four fill preflights remained. A fresh activation run started against the live fixture to test the combined reads, original persistence checks and exact owned cleanup.

The Sakai owned Edit change passed the offline scope tests, including the combined path from authorized post-blur Save to owned Edit. In the positive mock, the original guard first verified the exact row, then recorded the owned Edit open and exact title. Only original read-only field checks became eligible for grouping. Invalid fields, writes and commit requests were refused before dispatch.

The live Vuestic combined-read activation passed all five original checkpoints and used one eight-child plan. It made 17 actual worker requests, 14 model calls, 87 native calls and used 56,070 combined tokens in 61.296 worker seconds. Compared with the earlier activation, it made exactly four fewer native evaluations, with other native call counts unchanged. Both assigned tabs closed and owned cleanup verified absence in both filters. The two activations used separate fixtures and do not supply a matched latency result.

A fresh Sakai combined validation started after Vuestic cleanup. It checks post-blur commit and closure independently from grouped owned Edit reads. Success still requires all original checkpoints and exact closure.

The combined Sakai validation passed all six checks and closed its assigned tab. One completed plan grouped three draft reads and a second grouped guarded Save with exact closure. The worker had verified the Price without blur, so this did not exercise the post-blur branch again. It made no owned Edit plan request and used ordinary guarded reads there. The commit auditor returned true and the two optional-scope auditors returned false. This activation offers no matched timing result.

The live Vuestic combined-read activation cleared all cleanup gates. A fresh matched pair then started with the optimized read path available to the assisted arm. Both arms use the same synthetic fixture and unchanged original checks.

The matched combined-read Vuestic pair passed all five checks in both arms. The assisted worker used one eight-step plan. Separate cleanup verified absence in both filters for each arm, and all four tabs closed. Wall time fell from 63.197 to 56.819 seconds, a 10.1% reduction in this pair. Worker requests fell from 23 to 17 and model calls from 15 to 14. Native calls rose from 81 to 86, with five more evaluations and other counts unchanged. Combined tokens rose from 48,739 to 55,273. A fresh reverse-order repeat is needed to judge repeatability. The earlier plan variant used a different fixture and is a separate comparison.

The Sakai owned Edit audit found that an original exact field read already checks the current title and value within the guarded dialog. After an exact owned-row witness and scoped open, this can support fresh read-only plan admission without a redundant title request. Offline mocks covered positive exact evidence, missing title and mismatched value. The host integration remains pending.

The reverse-order Vuestic combined-read repeat started assisted first. The runner and runtime match the prior pair. Both arms share a fresh synthetic fixture and use the same original scenario. Independent cleanup must verify absence in both filters before the baseline starts.

The reverse-order pair passed all five checks in both arms. The assisted worker used one eight-step plan. Both cleanup runs verified absence in both filters, and all four assigned tabs closed. The assisted run took 62.853 seconds versus 57.905 baseline. It made 17 versus 22 worker requests, 17 versus 14 model calls and 86 versus 78 native calls. Combined tokens were 68,104 versus 45,576. Across the two matched pairs, the descriptive medians were 60.551 seconds baseline and 59.836 seconds assisted, about 1.2% lower. Fewer worker requests repeated, while the latency direction reversed and tokens increased in both pairs.

The Sakai read-only admission prototype passed ten offline cases through the original guards. It uses the first explicitly selected scalar read to verify the current exact title and value after an exact owned-row open, without a separate native title probe. A failed first or later read stops the remaining children. The named-tool runner mocks reduced worker requests from 19 to 10 with the same 34 native calls and original checkpoints. Live confirmation remains pending.

A fresh Sakai owned Edit validation started with the folded scope check. The first worker-selected original read in a guarded read-only plan can supply title and value evidence after an exact owned-row open. The auditor requires actual grouped read receipts, a complete original scenario and exact tab closure. This run is outside matched timing.

The Sakai folded-scope validation passed all six checks and closed the assigned tab. One eight-leaf plan covered worker-selected draft fills, exact field reads, Save and independent closure. The worker used ordinary calls for owned Edit, so the specific grouped Edit auditor returned false. The activation took 45.693 worker seconds with 11 model calls and 13 worker requests. It has no matched timing credit.

A fresh standard-policy Sakai pair started baseline first. It measures the whole run and records which eligible groups the worker actually chose. A passing trial can still use ordinary guarded checks. The report will distinguish observed draft and commit plans from grouped Edit use.

Both arms of the standard-policy Sakai pair passed all six source checks and closed their assigned tabs. The assisted worker completed three explicitly selected plans covering six draft leaves, two commit and closure leaves, and three owned Edit reads. The owned Edit auditor verified one eligible group. Worker time fell from 61.965 to 49.608 seconds, a 19.9% reduction in this pair. Model calls fell from 23 to 15 and worker requests from 22 to 14. Native calls and mutations were identical at 38 and nine per arm. Combined tokens fell from 48,894 to 39,250. A fresh reverse-order repeat started from the same frozen runner and policy.

The reverse-order Sakai pair passed all six checks in both arms and closed both assigned tabs. The assisted worker again selected three plans. Its owned Edit group followed an explicit exact title read, so grouping was verified and the folded-only auditor returned false. Worker time fell from 59.150 to 53.687 seconds. Model calls were 21 and 16, worker requests 22 and 14, native calls 38 and 39, and tokens 45,258 and 44,248. Across the two pairs, descriptive median wall time fell 14.7%, from 60.557 to 51.648 seconds. Both pairs saved eight worker requests. This sample is small and covers one case.

The Sakai cross-phase audit identified an eight-leaf window spanning five observed worker requests. The original guards passed all eight with the same 15 native calls in an offline fixture. A receipt-gated executor still needs to preserve each dependency and original witness before that group can run live. Vuestic's private Add-and-result continuation passed seven focused wire modes. Its ordinary fallback remained available after a definitive no-dispatch refusal without an attempt marker, while dispatched and uncertain outcomes blocked replay. Provider-facing schema handling and live use remain pending.

The Vuestic commit route reached the fake host exactly once in the browser-free provider retry. The first probe reached no host and remains recorded. A fresh live activation then started on the verified fixture. It lets the worker explicitly choose the original one-shot Add and its separate exact owned-result observation. The original persistence checks and exact owned cleanup still apply, and the activation is excluded from timing.

The live Vuestic commit activation passed all five checks. The worker selected one continuation containing the original guarded Add and the independent owned-result observation. Both original leaves ran once, and the worker verified persistence and table return. It made 21 actual worker requests and 19 model calls, with 83 native calls and 67,742 combined tokens in 70.582 worker seconds. Both assigned tabs closed and cleanup confirmed absence in both filters. The separate draft plan was not used. This establishes live commit continuation without measuring speed.

After Vuestic cleanup, a fresh SAKAI-03 baseline started with the frozen held-out runner. The assisted arm can use the unchanged projection for exact original and updated field readback. Both arms share matched synthetic inputs, require six preparation checks and five update checks, and must verify exact tab closure. The runner retains the original boot path. A failed reset will be reported separately from scenario timing.

Both arms of the fresh SAKAI-03 matched pair passed six preparation checks, five update checks and exact tab closure. The assisted worker used two projections. The first verified Name and original Price. The second verified Name, Description and updated Price after reopening. Main-phase time fell from 47.824 to 42.484 seconds, an 11.2% reduction in this pair. Model calls fell from 16 to 14, worker requests from 18 to 15, native calls from 26 to 23 and combined tokens from 30,941 to 27,668. Preparation took 50.311 and 54.804 seconds. Total time including preparation fell from 99.262 to 98.260 seconds. This is the first qualifying matched held-out update pair.

The SAKAI-03 reverse-order repeat started assisted first. The runner, scenario and original boot path match the first pair. Both arms share fresh synthetic inputs with distinct integer-cent prices. The first arm must pass preparation, update and exact tab closure before the baseline starts.

The reverse-order SAKAI-03 pair passed all six preparation checks and five update checks in both arms. Both tabs closed exactly. The assisted worker again used a two-field and a three-field projection. Main-phase time fell from 54.745 to 47.693 seconds. Both arms made 17 model calls. Worker requests fell from 20 to 16, native calls from 26 to 24 and combined tokens from 34,678 to 33,846. Across both pairs, descriptive medians fell from 51.285 to 45.089 seconds in the main phase and from 107.746 to 104.315 seconds including preparation. This is a 12.1% main-phase reduction and a 3.2% end-to-end reduction across two pairs.

After both Sakai tabs closed, the combined VUESTIC-02 timing pair started baseline first. The assisted worker may choose either the folded draft-field plan or the guarded Add-and-result continuation when eligible. Both arms retain the original scenario and exact two-filter owned cleanup. The report will distinguish actual use of each capability.

The combined Vuestic pair passed all five checks in both arms. The assisted worker used one eight-leaf draft plan and one two-leaf guarded Add-and-result continuation. Both cleanup runs verified absence in both filters, and all four assigned tabs closed. Worker requests fell from 23 to 14, but model calls rose from 14 to 15 and native evaluations from 63 to 76. Other native call counts were identical. Wall time rose from 56.297 to 59.000 seconds and combined tokens from 45,259 to 49,544. This pair verifies combined adoption and shows no latency gain.

The private Sakai cross-phase executor passed 17 original-guard mock modes and five identity or generation checks. Tests covered an eight-leaf positive path, no replay, pending witness failure and lease loss during the final native read. The original guard calls and receipts were preserved. Runner wiring and actual model selection remain unverified.

In the Sakai standard-plan pairs, the summed native guard time rose from 8.336 to 9.863 seconds in the first pair and from 7.638 to 8.017 seconds in the reverse pair. Both wall-time reductions occurred outside the measured native calls. The trace does not distinguish model or transport delays within that residual.

For the combined Vuestic pair, the code accounts for six added scope evaluations and one omitted ordinary Add-button observation. Eight of the 13 additional evaluations remain unattributed. Earlier polling after Add is consistent with the difference, but the retained trace contains a final result rather than individual polling counts. A telemetry-only candidate will count calls per guarded action and owned-result polling iterations without adding observations.

A Vuestic deletion-case mock grouped each worker-selected owned-row opener with its exact confirmation read. The original runner and scenario are unchanged. The mock passed all three source checks with identical guarded leaves and native calls, reducing worker requests from 11 to nine. The final Delete remained a separate one-shot operation. The observed outcome timeout stayed visible, and completed absence in both filters was still required. Private runner wiring and a validation run are pending.

The fresh VUESTIC-04 grouped-opener validation started with independent preparation. The original scenario is byte-identical, and the existing grant chain authorizes the main deletion attempt only after genuine preparation receipts. The validation separately records whether both worker-selected opener groups return exact confirmation evidence and whether the original three checks pass. Any final Delete remains separate and one-shot. This run is outside timing.

The live VUESTIC-04 validation passed all three original checks and verified both opener groups. Cancel preserved the owned record. One final Delete dispatched, the original closure observation timed out, and fresh completed Active and Inactive searches both verified absence. Both assigned tabs closed. The main worker made 12 model calls and used 22,971 combined tokens. The validation cohort has no paired latency result.

The private Sakai cross-phase runner passed both full CLI mocks through the actual stdio MCP bridge. Existing ordinary and plan schemas and replies were preserved. The new named route carried an explicitly selected eight-leaf request and reduced worker requests from 21 to 14 with identical native calls, all original checks and exact tab closure. A separate browser-free OpenCode probe selected the exact dependency-bearing route once. That probe verifies tool delivery only. Live validation is pending.

A fresh VUESTIC-04 matched pair started baseline first. Both arms use the same source scenario and synthetic fixture. The assisted arm exposes optional grouping with no validation quota. The second arm requires genuine preparation and main passes, exact tab closures, one final Delete receipt and fresh verified absence in both filters from the first. The launcher records main and total time separately.

The first VUESTIC-04 timing baseline passed all three deletion checks and verified the reset through both filters. Its main phase took 54.536 seconds. The assisted arm's preparation stopped before the main scenario. Its exact Notes comparison matched, but Role and Projects evidence remained unavailable and Cancel was not actionable. The original gate withheld the main Delete grant. Separate cleanup verified absence and closed its assigned tab. The launcher recorded the pair as invalid for timing. A common-preparation diagnostic will investigate this recurring Edit-defaults failure.

After the final Vuestic cleanup, the frozen Sakai cross-phase validation started on the disposable local fixture. It exposes an explicit dependency-bearing route alongside the previous ordinary and named plan tools. Each worker-selected operation still uses the original guard and exact receipts. The auditor requires original scenario PASS, actual cross-phase use and exact tab closure. This run is outside timing.

The Sakai cross-phase activation passed all six original checks and closed its assigned tab. It used the existing draft plan and completed a two-leaf Save-and-closure group. Both plan routes can accept that two-leaf group, and the retained evidence does not identify which route carried it. One later plan request was refused before any child ran. Its route and rejection gate were also unrecorded. The cross-phase auditor recorded zero verified windows. A fresh validation will disclose current-draft eligibility and retain fixed route and rejection codes without request payloads.

The next VUESTIC-04 pair started assisted first with fresh matched synthetic inputs. Both arms use the same bounded Role observation during preparation. It retains the original exact linked Role and Projects predicates, one expansion, and at most one collapse after a fresh linked-popup witness. The prior failed preparation still supplies no timing comparison. The new pair records exact cleanup and original main outcomes separately.

The bounded Role retry verified the exact popup, selected User, collapse and empty Projects. Preparation then stopped before native Add. The generated helper replaced the original nested closure evidence with a telemetry summary, while the unchanged Add gate still requires the original nested popup count. That integration error explains this refusal. Cleanup verified absence without Delete, and neither main deletion arm ran. The next private revision will preserve the original return shape and attach the bounded samples separately.

The private Vuestic preparation fix restored the original nested Role and Projects evidence and put bounded observation samples in a separate telemetry field. The unchanged preparation dispatcher accepted exact delayed popup and closure evidence in both arm mocks, admitted one guarded Add, and refused a repeat. It withheld Add in six negative cases, including incorrect linkage, native prompts, uncertain effects and nonempty Projects. A fresh baseline-first matched pair started with identical preparation code and synthetic inputs in both arms.

The shape repair passed all five baseline preparation checks. In the main phase, Cancel preserved the owned record and one final Delete dispatched. The closure observation timed out, and the worker ended before attempting the source-required fresh searches in both filters. Separate cleanup verified absence in both filters without another Delete. All assigned baseline tabs closed. The assisted arm did not start, so this attempt supplies no matched timing.

A new Sakai validation started with the Luna-generated cross-phase route and fixed route and rejection receipts. It will count adoption only if the original scenario passes, the exact assigned tab closes, and one completed worker-selected group spans the verified draft and commit boundary.

The latest Sakai validation passed the original scenario and closed its assigned tab. Fixed receipts identify one draft plan and 18 ordinary requests. The worker made zero cross-phase requests, so this run establishes no adoption or speedup for the new route.

Luna authored common Vuestic tool guidance for both arms after the closure timeout. The guidance retains the timeout and calls for the source-prescribed guarded searches when the exact dispatch receipt and existing prompt gate permit them. The original scenario and dispatcher passed offline parity checks. A fresh baseline-first matched pair started.

The shared timeout guidance led the VUESTIC-04 baseline worker to complete both required searches after one Delete dispatch and the closure timeout. The Active search still found the owned record, and Inactive found no match. The original persistence check failed on that evidence. Separate cleanup returned pending. The preparation, main and cleanup tabs all closed. The assisted arm did not start, so the pair supplies no latency comparison.

The Sakai route audit identified the existing two-operation plan as Save and verified closure. The worker then made six separate requests through the owned Edit action. The next Luna experiment will test a plain ordered list for that existing plan interface, binding dependencies to exact guarded receipts while retaining the worker's choice of every action.

The Vuestic receipt audit confirmed a complete Active search with one visible row, total one and both owned identity fields matching. The completed Inactive search had zero rows and total zero. Cleanup independently found the same owned Active record and reached its exact confirmation. The prior one-shot reservation blocked another Delete, leaving cleanup pending and preserving the recorded failed persistence check.
