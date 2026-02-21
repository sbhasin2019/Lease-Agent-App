----------------------------------------------------------------
POST-REFINEMENT REVIEW — Dashboard Visual Overhaul
----------------------------------------------------------------
Review date: 2026-02-20
Scope: Full architectural + CSS + UX audit after dashboard
       visual refinement and lifecycle system overhaul

This file captures findings from the post-refinement review.
It is a snapshot, not a living document. Findings here should
be actioned and then marked DONE or moved to ACTIVE_ROADMAP.md.

================================================================
SECTION 1 — ARCHITECTURAL INTEGRITY
================================================================

Status: NO REGRESSIONS FOUND

All code paths were verified against PROJECT_CONTEXT.md and
ACTIVE_BUILD.md. The implementation matches the documented
design.

1.1  Engine Pipeline Order — CORRECT

  The dashboard route executes in the documented order:

  Per-lease loop:
    materialise_system_threads(lease_group_id)
    materialise_missing_payment_threads(lease_group_id, lease)

  Global steps (after all leases processed):
    auto_resolve_missing_payment_threads()
    send_missing_payment_reminders()
    escalate_missing_payment_threads()

  Each step conditionally reloads thread_data if the previous
  step mutated state. This is correct — each function operates
  on fresh data.

1.2  needs_landlord_attention — CORRECT ACROSS ALL PATHS

  Traced every code path that reads or writes this field:

  payment_review threads:
    - Set true at creation (materialise_system_threads)
    - Synced after every message (add_message_to_thread):
        open + waiting_on=landlord -> true
        open + waiting_on=tenant  -> false
        resolved                  -> false

  missing_payment threads:
    - Set false at creation (ensure_thread_exists)
    - Set true after 2-day grace period (escalate function)
    - Set false on auto-resolution

  Action routes (acknowledge, flag, reminder):
    All handle the field correctly.

1.3  Landlord Filter — CORRECT

  - Filters both grouped_leases (cards) and console_leases
    (Action Console data) from the same filter criteria
  - Dropdown shows full landlord list regardless of active filter
  - Invalid landlord names safely fall back to "all"

1.4  Dead Code — get_global_alerts()

  Status: DONE (2026-02-21)

  get_global_alerts() runs on every dashboard load, computes
  expiry and payment status for every lease, passes the result
  to the template — but the template never renders it.

  This is wasted computation. The function itself is still used
  in the lease detail view (via calculate_reminder_status()), so
  only the dashboard call and template parameter should be removed.

  Additionally, global_alerts is computed from the UNFILTERED
  leases list. If the alerts were ever re-enabled, they would
  show alerts from all landlords even when a filter is active.
  This is a secondary bug in dead code.

  Action: Remove get_global_alerts() call and global_alerts=
  parameter from the dashboard route. Preserve the function
  itself until confirmed unused by all routes.

1.5  Redundant Double-Save in Action Routes

  Status: DONE (2026-02-21)

  thread_review_acknowledge() and thread_review_flag() both
  perform a second load-save after add_message_to_thread() to
  explicitly clear needs_landlord_attention. This is unnecessary
  because add_message_to_thread() already handles it for
  payment_review threads.

  The second pass adds two extra file I/O operations per action.
  It is documented as intentional ("belt-and-suspenders safety")
  in the route docstrings. Not a bug, but could be removed for
  cleaner code.

1.6  resolve_thread() Latent Risk

  Status: DONE (2026-02-21)

  resolve_thread() does NOT clear needs_landlord_attention.
  Currently safe because:
    - payment_review threads resolve via add_message_to_thread()
      (which does clear it)
    - missing_payment threads resolve via
      auto_resolve_missing_payment_threads() (which clears it
      directly on the thread dict)

  If resolve_thread() were ever called directly on a
  payment_review thread, needs_landlord_attention would not be
  cleared. This is a latent risk, not a current bug.

================================================================
SECTION 2 — UI/UX INCONSISTENCIES
================================================================

2.1  Lease Card Title Gets Lifecycle Classes With No Effect

  Status: DONE (2026-02-21)

  The HTML applies "terminated" or "expired" as a CSS class on
  .lease-card-title, but no CSS rule exists for
  .lease-card-title.terminated or .lease-card-title.expired.

  The stamp overlay (.lease-card-stamp) handles the visual
  indication instead. These classes are applied but do nothing.

  Action: Either give these classes a purpose (e.g. muted text
  colour for expired leases) or remove them from the template.

2.2  Stamp Comment Says "Amber" But Stamps Are Red

  Status: DONE (2026-02-21)

  A CSS comment near the lifecycle styling section references
  "AMBER to match dashboard ribbons". The old amber ribbons
  were removed and replaced with red-bordered stamps (#dc2626),
  but the comment was not updated.

  Action: Update the comment to reflect the current red colour
  scheme, or remove the outdated comment.

2.3  .lease-card-actions Has No CSS Definition

  Status: DONE (2026-02-21)

  The container holding "View Lease" and "Add Renewal Lease"
  buttons has a class name (lease-card-actions) but no CSS rule.
  Layout works by accident (block-level buttons stack naturally).
  No explicit gap, padding, or alignment control.

  Action: Add a minimal CSS rule for .lease-card-actions to make
  the layout intentional rather than accidental.

================================================================
SECTION 3 — CSS TECHNICAL DEBT
================================================================

3.1  HIGH — 193 Inline style="" Attributes

  Entire template sections are styled with inline style=""
  on every element:
    - Monthly Submission Summary table
    - Payment Submissions section
    - Payment Thread View
    - Tenant Access section
    - Lease Version History toggle buttons

  These were built in earlier phases and never migrated to the
  shared <style> block. They cannot be searched, themed, or
  changed in one place. This is the single biggest CSS debt item.

  Action: Migrate inline styles to CSS classes in the shared
  <style> block during the next template-touching work (likely
  Phase 10G tenant page alignment).

3.2  MEDIUM — ~30 Dead CSS Rules (8 Groups)

  Status: DONE (2026-02-21)

  CSS rules defined in <style> with no matching HTML elements:

  Group                              Approx rules   Was for
  ----------------------------------------------------------------
  .global-alerts (full block)        14 rules       Old alerts ticker
  .lease-card-header/name/badge       3 rules       Old card structure
  .lease-card-footer                  1 rule        Old card bottom
  .lease-card.urgency-* and .active  11 rules       Old urgency-on-card
  .dashboard-actions                  1 rule        Old button area
  .lease-card-subtitle                1 rule        Removed subtitle
  .card, .card-header                 2 rules       Generic card (unused)
  .console-group-visible              1 rule        JS bypasses with
                                                    inline styles

  Action: Remove all dead CSS in a dedicated cleanup pass.
  Low risk — none of these rules match any HTML element.

3.3  MEDIUM — 7 !important on textarea.reply-box

  Status: DONE (2026-02-21)

  A single CSS rule for textarea.reply-box uses 7 !important
  declarations (height, min-height, max-height, line-height,
  font-size, padding, box-sizing). This indicates the rule was
  fighting against inherited or competing styles and the author
  escalated with brute force.

  This is fragile. If any future change needs to override these
  properties, it literally cannot (short of inline styles).

  Action: Identify what the reply-box rule is fighting against
  and resolve the conflict at its source. Then remove !important.

3.4  MEDIUM — 34 Inline onclick Handlers

  Documentation states "event delegation only, no inline
  handlers." The Action Console correctly follows this rule.
  Nearly everything else does not:

  - Modal open/close buttons (openAttentionModal, etc.)
  - Collapse/expand toggles (lease history, monthly summary,
    tenant access)
  - AI button (aiPrefill)
  - Table row clicks (openSubmissionsModal)
  - Copy link button
  - Token reveal button

  Plus 3 inline onchange handlers (landlord filter, review type
  select, maintenance checkbox).

  Action: Not urgent, but new code should follow the delegation
  pattern. Migrating old handlers can happen incrementally.

3.5  MEDIUM — Inline <style> Block in Template Body

  Status: DONE (2026-02-21)

  An inline <style> block is injected inside the monthly summary
  section (not in <head>) defining hover styles and a keyframes
  animation. This creates a specificity island that is hard to
  find and maintain.

  Action: Move to the shared <style> block in <head>.

3.6  LOW — z-index Gap (1000 vs 9999)

  Status: DONE (2026-02-21)

  .modal-overlay normalised from 9999 to 1000.
  Four-tier z-index scale comment added to top of <style> block.

  Original finding:

  Action modals (reminder, acknowledge, flag) use z-index: 9999.
  All other modals (delete, terminate, attention, etc.) use 1000.
  No unified z-index strategy.

  Action: Define a z-index scale in a CSS comment:
    900  = loading overlay
    1000 = standard modals
    9999 = action modals (or normalise to 1100)

3.7  LOW — Console Border-Radius Mismatch

  Status: DONE (2026-02-21)

  .action-console has border-radius: 10px.
  .action-console-header has border-radius: 12px 12px 0 0.
  The parent clips overflow so the mismatch is invisible, but
  the values should match (both 10px or both 12px).

3.8  LOW — Duplicate CSS Selector Pairs

  Status: DONE (2026-02-21)

  Merged 3 duplicate .urgency-* selector pairs into single
  consolidated blocks. No visual changes.

  Original finding:

  Three urgency escalation rules (.urgency-warning,
  .urgency-urgent, .urgency-critical) are each defined twice
  in the stylesheet: once as a base definition, once as an
  enhanced version with box-shadow and animation. Could be
  merged into single declarations.

3.9  LOW — Identical Stamp CSS Blocks

  Status: DONE (2026-02-21)

  .lease-card-stamp.terminated and .lease-card-stamp.expired
  have byte-for-byte identical CSS. Could be combined:
    .lease-card-stamp.terminated,
    .lease-card-stamp.expired { ... }

3.10 LOW — Modal Overlay Pattern Inconsistency

  Status: AUDITED (2026-02-21 — No structural changes applied)

  13 modals catalogued. 6 inconsistencies identified.
  Unification refactor halted by user decision.
  No modal restructuring applied.

  Original finding:

  Three different patterns for showing/hiding modals:
    Pattern A: CSS class toggle (.visible)
    Pattern B: Inline style toggle (style.display)
    Pattern C: Mixed (CSS says display:flex, inline style
               overrides with display:none)

  Not a bug, but makes modal behaviour harder to reason about.
  New modals should pick one pattern.

3.11 LOW — <a href="javascript:void(0)"> Anti-Pattern

  Status: DONE (2026-02-21)

  One instance in the monthly summary section. Should be a
  <button> element for accessibility and semantic correctness.

================================================================
SECTION 4 — NEXT HIGHEST-LEVERAGE PRODUCT MOVE
================================================================

Recommendation: Phase 10G — Tenant Page Alignment

Rationale:

  The landlord experience is now operationally complete. The
  dashboard has a two-column layout, the Action Console surfaces
  all attention items, the engine handles the full lifecycle
  (creation, reminders, escalation, auto-resolution), and all
  review actions work from the console.

  But the tenant experience is frozen in an earlier era. The
  tenant page has no awareness of:
    - Missing payment threads
    - Reminder messages sent by the landlord
    - The escalation state of their obligations

  The engine generates reminders and escalations, but the person
  who needs to act on them (the tenant) cannot see them. The
  landlord is talking into a room where the tenant is not present.

  Phase 10G closes this communication loop:
    - Overdue rent notice with reminder messages visible to tenant
    - Tenant-side Action Console (mirrors landlord model)

  Every feature already built (reminders, escalation, the Action
  Console) becomes more valuable when the tenant can actually
  see and respond to it.

What NOT to do next (and why):

  Maintenance/utilities missing payment threads:
    Same engine, different cadence. Valuable but incremental.
    Does not close an existing gap.

  Renewal threads:
    Important eventually, but renewal is a once-per-lease event.
    Missing payment is monthly across every tenant. Higher
    frequency = higher leverage.

  CSS cleanup:
    Real debt, but not blocking any product capability. Do it
    when already in the template for other reasons (e.g. 10G).

  Dead code removal (global_alerts, dead CSS):
    Maintenance hygiene, not product value.

================================================================
SECTION 5 — STATUS UPDATE (2026-02-21)
================================================================

Architectural clarifications from Phase 10H hardening session.

5.1  normalizeAiFields() — Canonical Normalization Layer

  normalizeAiFields() is now the canonical AI → form
  normalization layer. All AI extraction consumers must pass
  through this function.

  Used by both:
    - Live AI Preview (aiPrefill response handler)
    - Saved AI Preview (openSavedAiPreview, read-only)

  Key remaps (3 of 9 fields):
    start_date             → lease_start_date
    end_date               → lease_end_date
    lock_in_duration_months → lock_in_months

5.2  lease.ai_extraction — First Read-Path Consumer

  Before 2026-02-21:
    lease.ai_extraction was persisted but never read.

  After 2026-02-21:
    Saved AI Preview reads and renders persisted ai_extraction
    via Jinja-injected SAVED_AI_EXTRACTION constant.

  This is the first read-path consumer of stored AI extraction
  data.

5.3  FIELD_LABELS Collision — Full Impact

  A duplicate var FIELD_LABELS declaration (introduced during
  UI refinement) caused a JavaScript parse failure that halted
  all lease-view interactivity: aiPrefill(), openAiPreviewModal(),
  openSavedAiPreview(), and all subsequent JS in the script block.

  Fix: Removed the duplicate declaration. The original const
  FIELD_LABELS is now the sole definition, shared by both the
  live and saved AI preview.

5.4  AI Rerun Guard — Client-Side Only

  Frontend:
    - Disables AI button after Apply
    - Resets on page reload

  Backend:
    - Allows unlimited /ai_prefill calls
    - Overwrites previous lease.ai_extraction
    - No extraction history kept

  This is architectural knowledge, not a bug.

5.5  pendingSuggestions Lifecycle

  pendingSuggestions is NOT cleared on Cancel.
  It persists in JS memory until the next AI run (which resets
  it at the start of the aiPrefill response handler).
  No persistence impact unless Apply is clicked.

5.6  innerHTML Trust Assumption

  AI field values and evidence text are injected via innerHTML
  in both the live and saved AI preview modals. No HTML
  sanitization layer is currently applied.

  System assumes trusted AI output (Claude API responses).

5.7  "View AI Preview" — Edit Mode Only

  The "View AI Preview" button is intentionally scoped to edit
  mode only. It does not appear in the read-only lease view.
  This was a conscious UX scoping decision.

  Saved AI Preview is purely read-only:
    - Does not mutate form fields
    - Does not re-run AI
    - Does not persist data
    - Reads SAVED_AI_EXTRACTION injected via Jinja
    - Uses normalizeAiFields() for key normalization

================================================================
END OF POST-REFINEMENT REVIEW
================================================================
