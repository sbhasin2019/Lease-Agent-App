----------------------------------------------------------------
PROJECT FIXES AND DECISIONS — HISTORICAL LOG
----------------------------------------------------------------

This file records important bugs, fixes, and architectural
decisions AFTER the fact. It explains WHY certain rules exist
so they are not accidentally undone later.

This file is NOT authoritative for current behaviour.
For the authoritative current state, see PROJECT_CONTEXT.md.
For planned future work, see ACTIVE_ROADMAP.md.

----------------------------------------------------------------

  2026-02-13  Legacy Event System Removal (Phase 5)

    Completed the migration from landlord_review_data.json to
    threads.json by removing ALL legacy event-based code.

    Functions deleted (9 total):
    - _load_all_landlord_reviews — I/O for landlord_review_data.json
    - _save_landlord_review_file — atomic write for old file
    - _normalize_event — schema migration shim (reviewed_at→created_at,
      review_type→event_type, internal_note→message)
    - get_events_for_lease_group — query events by lease group
    - get_events_for_payment — query events by payment ID
    - get_conversation_state — derive open/closed from event sequence
    - compute_lease_attention_count — count attention months from events
    - get_lease_attention_items — list attention items from events
    - build_payment_threads — build ephemeral thread display from events

    Template cleanup:
    - Removed legacy review/conversation block from index.html
      (landlord per-payment view): event timeline, reply form,
      acknowledge button, review form — all based on payment_events
      and payment_conversation variables
    - Removed legacy conversation block from tenant_confirm.html:
      payment_conversation lookup, event_type filtering, reply form
    - Removed payment_events={} and payment_conversation={} from
      both render_template calls

    Other cleanup:
    - Removed landlord_review_data.json from .gitignore
    - Added architecture comment at top of thread helper section
    - landlord_review_data.json file did not exist (no deletion needed)

    No migration was performed. All data at switchover time was
    test data. materialise_system_threads() creates threads for
    existing unthreaded payments on first dashboard load.

    Edge case found during cleanup: tenant_confirm.html still
    referenced payment_conversation and event_type in a hidden
    storage section. This would have crashed after removing the
    empty dict pass-throughs. Caught by global search verification.

    Verified: dashboard, lease detail, tenant page all return 200.
    Full flow tested: flag → tenant reply → acknowledge. Attention
    badges update correctly. No landlord_review_data.json created.

----------------------------------------------------------------

  2026-02-13  Unified Thread-Based Communication Model (Architecture + Implementation)

    Replaced fragmented attention/review/reminder logic with a
    single thread-based communication engine. Design locked
    2026-02-13. Implementation completed same day for
    payment_review threads. Legacy event system fully removed.

    What was replaced:
    - landlord_review_data.json (flat event records, implicit
      conversation state via get_conversation_state())
    - Event-based attention badge (compute_lease_attention_count,
      get_lease_attention_items — counted months, not threads)
    - Ephemeral thread computation (build_payment_threads —
      grouped payments by category with computed status)
    - Planned-but-unbuilt separate systems: reminder_data.json,
      renewal intent prompts with dashboard_prefs.json suppression

    What replaces it:
    - Single file: threads.json containing threads[] and messages[]
    - Explicit thread objects with stored status (open/resolved)
      and waiting_on (landlord/tenant/null) — never inferred
    - Four thread types: payment_review, missing_payment,
      renewal, general
    - Lazy thread creation via materialise_system_threads()
      called from dashboard route — no background workers
    - Auto-resolution (e.g. payment submitted → missing_payment
      thread resolves)
    - External channel fields (channel, delivered_via, external_ref)
      built into schema from day one, defaulting to "internal"

    Implementation phases completed:
    - Phase 1: Foundation (load/save, query helpers, write helpers,
      materialise_system_threads)
    - Phase 2: Write path switchover (submit_payment_review,
      tenant_payment_response)
    - Phase 3: Read path switchover (dashboard, attention modal,
      lease detail, tenant page)
    - Phase 4: Skipped — auto-resolution hooks for missing_payment
      and renewal threads deferred until those thread types exist
    - Phase 5: Legacy removal (9 functions deleted, templates
      cleaned, render_template calls cleaned, .gitignore updated)

    Architectural constraints enforced during implementation:
    - Single Load / Single Save: each write helper loads once at
      top, saves once at end
    - Write helpers are independent: none calls another write helper
    - Read helpers are strictly read-only: never call _save_threads_file
    - Read helpers accept optional thread_data to avoid repeated
      disk reads
    - No new builder/abstraction functions for lease detail —
      thread data used directly inline
    - Explicit waiting_on transitions, never inferred from
      message order

    Key design decisions locked:
    - Coverage (monthly summary) is informational only — never
      creates threads, never triggers attention badge
    - Threads are the actionable layer — only open threads where
      waiting_on == "landlord" are counted in attention badge
    - payment_review threads created only on tenant submission
      (landlord flagging is a message inside existing thread)
    - Idempotency checks open threads only — resolved threads
      never block new thread creation
    - Tenant submission route writes ONLY to payment_data.json;
      thread creation happens lazily on dashboard load
    - 7-day nudge is a computed display prompt, not a stored
      message; does not change waiting_on or inflate badge
    - Nudge display: primary in thread view (per-category modal),
      secondary in attention modal under "Follow-ups (Optional)"
    - Tenant visibility: sees payment_review, missing_payment,
      general threads; sees submission, flag, reply, reminder
      messages; does NOT see nudge or acknowledge messages
    - No migration from landlord_review_data.json — clean cut
      on test data; materialisation handles existing payments

----------------------------------------------------------------

    2026-02-12  Termination UI + Lifecycle Extension

      Built the full termination creation UI and extended the
      lifecycle model across both dashboard and lease detail views.

      What was built:
      - create_termination_event() function with 5 validations
        (lease exists, is current, not already terminated, valid date,
        date within lease period)
      - POST /lease/<lease_id>/terminate route
      - Confirmation modal with date picker and optional note
      - Dashboard: TERMINATED and EXPIRED amber ribbons (full-width)
      - Dashboard: running ticker (days elapsed) for both states
      - Dashboard: primary Renew button when _can_renew is True
      - Lease detail: Reminders ticker as sole lifecycle indicator
        (amber urgency-lifecycle styling for terminated/expired)
      - Lease detail: Renew button replaces Rent Payment section
        when _can_renew is True; reverts to normal after renewal
      - Route enrichment (full parity between dashboard and detail):
        _is_terminated, _termination_date_display,
        _termination_days_elapsed, _is_expired,
        _expiry_date_display, _can_renew

      Locked design decisions:
      - Version-level only (tied to lease_id, not lease_group_id)
      - Permanent and append-only — no undo, no edit
      - Effective date chosen by landlord (not assumed to be today)
      - lease_data.json is never modified
      - get_governing_lease_for_month() unchanged
      - Templates never compute lifecycle logic — routes attach
        pre-computed underscore-prefixed values
      - Lifecycle priority: TERMINATED > EXPIRED > ACTIVE
      - Dashboard ribbon + ticker apply only when CURRENT version
        qualifies; disappear after renewal
      - Amber colour scheme (warm, not alarming) for all lifecycle UI
      - Dead CSS removed: .termination-banner, .termination-banner-title,
        .termination-banner-detail, .lease-card-expiry-terminated


----------------------------------------------------------------

  2026-02-11  Dashboard attention badges (Phase 1)

    Added 🙋🏻 badge to dashboard cards showing count of months
    needing landlord attention. Badge appears inline next to the
    lease card title. Hidden when count is 0.

    Attention triggers (category-aware):
    - pending_review: category has submissions but zero landlord
      events (uses cat_has_any_review pattern to avoid false
      triggers from duplicate submissions)
    - tenant_replied: open conversation where tenant spoke last

    "awaiting_tenant" NEVER triggers attention. This is a locked
    rule — the badge answers "does this need MY action?" not
    "is something happening?"

    Attention Overview modal: clicking the badge opens a modal
    listing affected months with reasons and "View" links.

    Original helper functions (now deleted — replaced by thread model):
    - compute_lease_attention_count() — replaced by
      count_landlord_attention_threads()
    - get_lease_attention_items() — replaced by
      get_attention_summary_for_lease()

    Dashboard route now uses materialise_system_threads() +
    thread-based attention helpers instead of loading review data.

  ----------------------------------------------------------------

  2026-02-11  Payment Threads — grouped per-month modal view

    Replaced the multi-card per-month modal with a narrative-style
    thread view. One thread per payment type (Rent / Maintenance /
    Utilities), each with a merged chronological timeline.

    Original implementation used build_payment_threads() to compute
    ephemeral thread objects (now deleted — replaced by persistent
    threads in threads.json). Action targeting rule:
    action_payment_id is computed per category —
    active_conversation_payment_id if it exists, else
    latest_submission_payment_id. Templates NEVER infer which
    payment_id to target.

    Thread blocks are server-rendered in #payment-thread-view
    (hidden container) and moved into modals alongside legacy
    cards (threads visible, legacy cards hidden). "View full
    history" switches to legacy card view.

    Thread status values (now derived from thread.status and
    thread.waiting_on): "Needs your action", "Awaiting tenant
    response", "Resolved".

  ----------------------------------------------------------------

  2026-02-11  Reply vs Acknowledge — UX clarification

    Added "or" divider between Reply form and Acknowledge button
    in open-conversation action areas (both legacy cards and
    thread blocks). Makes it visually clear these are alternative
    actions, not sequential steps.

    Acknowledge button label changed to:
    "Acknowledge — no further action needed"

  ----------------------------------------------------------------

  2026-02-11  Smart redirect after landlord review action

    submit_payment_review now checks post-save state:
    - If same month still has unresolved threads → redirects with
      open_month=YYYY-MM&return_to=attention (re-opens month modal)
    - If all threads in month resolved → redirects with
      return_attention_for=lease_id (opens attention overview)
    - Fallback: plain lease detail page

    Now uses find_open_thread() to check for remaining open
    threads (previously used build_payment_threads(), now deleted).

  ----------------------------------------------------------------

  2026-02-11  Reply box compact sizing

    All landlord/tenant reply textareas use a dedicated .reply-box
    CSS class with hard pixel heights (26px default, 52px max).
    Inline padding/font-size/height removed from all 4 textareas
    to prevent specificity conflicts.

    Labels above reply boxes reduced to font-size: 0.8em with
    2px margin-bottom. Wrapper divs reduced to 4px margin-bottom.

  ----------------------------------------------------------------

  2026-02-10  Dashboard card redesign (Phase 1)

  Replaced the old dashboard cards with a calmer informational
  design.

  Old design had: urgency colour accents (left border), "Added on"
  row, raw "End Date" row, large urgency blocks
  (positive/warning/critical/expired), delete button, fixed 220px
  min-height.

  New card layout:
  - Lease nickname + earliest start date (across all versions)
  - Tenant name + continuity duration (e.g. "Tenant for 1y 4m")
  - Days until/past expiry with formatted date
  - Monthly rent (deep green, monospace numerals)
  - View Lease button only

  Rationale: The old urgency blocks were visually aggressive and
  unhelpful for a single-user app. The new design treats the
  dashboard as a calm summary, not an alert panel.

  Tenant continuity is computed by walking versions newest-first
  and stopping at the first tenant name mismatch, using
  _normalize_name() for comparison.

  Residual CSS: urgency classes (.lease-card.urgency-*) still
  exist in the stylesheet but are no longer applied to card HTML.
  Safe to remove in a future cleanup.

  Dashboard route enrichment uses a versions_cache dict (keyed by
  lease_group_id) to avoid redundant get_lease_versions calls.
  Attaches computed view-model keys to each lease dict BEFORE
  grouping: _earliest_start_date, _tenant_continuity,
  _needs_attention (placeholder, always False).

----------------------------------------------------------------

2026-02-09  Stage A — Governing lease function

  Added get_governing_lease_for_month() to determine which lease
  version governs any given calendar month. This replaced reliance
  on the is_current flag for month-level queries.

  Key design choices:
  - Operates at month granularity (not day)
  - Accounts for early termination via termination_data.json
  - The termination month itself is still IN_LEASE
  - Tiebreaker: latest start date, then highest version number
  - Skips drafts and leases with missing dates

  Helper: _parse_month_tuple(date_str) parses "YYYY-MM-DD" to
  (year, month) tuple. Located near the governing function.

----------------------------------------------------------------

2026-02-09  Stage B — Termination data layer (partial)

  Added termination_data.json with load/save functions and
  get_termination_for_lease() lookup. Termination never modifies
  the original lease — it is a separate append-only record that
  overrides lease eligibility.

  Decision: Only the storage layer and read functions were built.
  No creation route or UI exists. This was intentional — the data
  layer was needed immediately for Stage A's governing lease logic.
  The creation UI is deferred.

----------------------------------------------------------------

2026-02-09  State model cleanup — removed "noted"

  Simplified landlord review actions to binary: Acknowledge or
  Raise a flag. Removed "noted" as an active action.

  Rationale: Three options (acknowledge, note, flag) confused
  the UX. "Noted" had no clear semantic difference from
  "acknowledged" in practice.

  Backward compatibility (now moot): Historical "noted" events
  were normalised to "acknowledged" on read via _normalize_event().
  Both _normalize_event() and the entire landlord_review_data.json
  architecture have been deleted. No historical "noted" events
  exist in the current thread-based system.

  Also unified status language across the app:
  - "reviewed" → "acknowledged"
  - "resolved" → "acknowledged"
  - Tenant-facing: "Acknowledged — no further action required"

  Removed concepts: noted, reviewed, resolved — none of these
  exist as active states or UI actions.

----------------------------------------------------------------

2026-02-09  Tenant monthly summary — per-category states

  Added category_details to tenant monthly summary with
  tenant-specific state names (action_required, you_responded,
  submitted, acknowledged) plus not_submitted for missing
  categories.

  Key difference from landlord: uses visible_events filter
  (only "flagged" and "response" events). Tenant never sees
  internal "acknowledged" events — only flags and responses.

  Visibility: Last 6 months always shown. Older months visible
  only if missing_categories is non-empty or any category state
  is not "acknowledged".

----------------------------------------------------------------

2026-02-09  Modal overview and partial submission notices

  Added Payment Overview section at the top of per-month modals
  and a disclaimer at the bottom. Both landlord and tenant modals.

  Added partial submission notices: "Some expected payments for
  this month have not been submitted."

  These are injected via JavaScript (not server-rendered) because
  modal content is populated dynamically via DOM node movement.
  Helper functions: _buildLandlordOverview / _buildTenantOverview,
  _injectLLPartialNotice / _injectTenantPartialNotice.

----------------------------------------------------------------

2026-02-09  UX copy — second-person language for landlord

  Landlord-facing text switched to second-person "you/your":
  - "pending landlord review" → "pending your review"
  - "flag raised by landlord" → "flag raised by you"
  Tenant-facing text unchanged. Modal disclaimers standardised
  to include ", or landlord approval".

----------------------------------------------------------------

2026-02-09  Bug fix — tojson error on tenant submission

  monthly_summary was not passed to template in POST render
  paths of tenant_confirm route. Caused Jinja tojson error.
  Fixed by adding monthly_summary=[] to both error and success
  render calls.

----------------------------------------------------------------

2026-02-09  Bug fix — tenant dashboard not showing "acknowledged"

  get_conversation_state() returns {"open": False, "thread": []}
  for direct acknowledgments (no "flagged" event). The tenant
  review logic assumed empty visible_events = "submitted".

  Fixed by checking convo["open"] instead of just visible_events,
  in both month-level and per-category detail logic.

----------------------------------------------------------------

2026-02-09  Bug fix — missing categories invisible on tenant dashboard

  category_details was only built for covered_categories. Missing
  categories had no entry and were invisible. Fixed by adding
  "not_submitted" entries for missing categories with display
  text "⏳ [Category] — awaiting submission".

----------------------------------------------------------------

2026-02-09  Bug fix — duplicate submission causing perpetual pending_review

  When tenant submitted same category twice, landlord acknowledged
  one but the unreviewed duplicate dragged category to
  "pending_review". Fixed with cat_has_any_review pre-check in
  landlord per-category detail logic.

----------------------------------------------------------------

2026-02-09  Clickable month rows on tenant dashboard

  Clicking a month name prefills the submission form's month/year
  dropdowns. Uses query params (month, year) + DOMContentLoaded
  script to auto-reveal the hidden form container and scroll to it.

----------------------------------------------------------------

2026-02-08  LV-7.2 Steps 1–6 — Expected payment coverage system

  Built the full expected payment coverage system across six steps.

  Step 1 (Data model): Added expected_payments to current_values
  and needs_expected_payment_confirmation flag. Migration functions
  default existing leases to rent-only. Rent typical_amount
  populated from monthly_rent.

  Step 2 (Edit Mode UI): Added checkboxes for maintenance and
  utilities in Edit Mode. Rent shown as always expected (not
  toggleable). Optional typical_amount field for maintenance.
  Utilities have no amount field (varies monthly). Renewal
  confirmation banner shown when needs_expected_payment_confirmation
  is true. Saving clears the flag.

  Step 3 (Coverage computation): Added compute_monthly_coverage()
  helper. Compares expected categories against submitted categories.
  Returns expected, covered, missing, summary, and is_complete.

  Step 4 (Landlord monthly summary): Added Submission Status
  column with per-category indicators (✅ covered, ❗ missing,
  ❓ flagged). Fixed display order: rent → maintenance → utilities.

  Step 5 (Tenant monthly summary): Same coverage display pattern
  as landlord. Per-category indicators in Submission Status column.

  Step 6 (Modal notices): Added JavaScript functions to inject
  missing-category warnings inside per-month modals for both
  landlord and tenant.

  Key decisions locked at this time:
  - Categories are mandatory to choose; amounts are optional
  - Amounts are informational only (no verification or comparison)
  - Coverage is per CATEGORY, not per submission count
  - Use current lease version's expectations for all months
  - Only past months within lease period are evaluated
  - Existing leases default to rent-only expected

----------------------------------------------------------------

2026-02-08  LV series — Lease View & Submission UI Overhaul

  LV-2: Reordered comparison fields (Tenant Name first, then
  financials, then dates, then terms). Both simple and nested
  field sections updated.

  LV-3: Reversed monthly summary ordering (latest month first).
  Collapsed Tenant Access section by default.

  LV-4: Replaced inline comparison toggle with modal
  (#changesModal). Shows all 8 fields including unchanged ones
  (tagged "No change from previous lease"). Added print button.

  LV-5: Reduced monthly summary to 3 columns (removed separate
  Status column). Added priority-based badge styling.

  LV-6: Built per-month submission modal for landlord. Cards
  moved via DOM appendChild (not cloned). Modal state tracked
  via submissionsState JS object with viewMode and origin.
  Monthly summary rows clickable only when submission count > 0.

  Lease Version History: Collapsed by default. "View lease
  history" / "Hide lease history" toggle.

  Monthly Submission Summary: Collapsed by default with toggle.

  LV-7: Tenant UI overhaul — page title "Tenant Interface",
  monthly summary as primary view (NOT collapsed), submission
  form hidden by default with "+ Add new submission" reveal link,
  past submissions in hidden storage container, tenant modal
  with same architecture as landlord.

  LV-7.1: Empty states and helper guidance text for both views.
  Zero-submission detection, modal empty states, defensive cleanup
  in all 8 JS modal functions.

  Full History Mode: Read-only audit view of ALL submissions
  accessible from within a per-month modal or from page level.
  CSS class 'history-view' hides all interactive elements.

  Attention Badges: Landlord (blue pill) counts months with
  tenant_replied or pending_review. Tenant (amber pill) counts
  months with action_required. Hidden when count is 0. Uses
  Jinja2 namespace counting pattern.

----------------------------------------------------------------

2026-02-08  DOM node movement pattern established

  Server-rendered submission cards are moved (not cloned) between
  a hidden storage container and modals using appendChild. This
  preserves form state, event handlers, and avoids duplication.

  Rationale: Cloning would duplicate form IDs and break event
  handlers. Moving is zero-copy and reversible.

  Rule: Modal close functions must ALWAYS move ALL cards back
  to storage, remove history-view class, and reset state —
  regardless of current view mode.

----------------------------------------------------------------

2026-02-07  Phase 1 — Payment confirmation infrastructure

  Built the complete payment confirmation system across multiple
  steps, establishing separate data files for payments and
  tenant access.

  Key architectural decision: payment_data.json is separate from
  lease_data.json to protect lease data from payment bugs.
  tenant_access.json is separate from payment_data.json because
  access control must never be mixed with transactional data.

  Infrastructure: Atomic load/save for both files. Proof file
  storage in uploads/proofs/{lease_group_id}/ with immutable
  files and path traversal protection. Token generation via
  secrets.token_urlsafe(32).

  Tenant form: Multi-type with checkboxes (rent, maintenance,
  utilities). Each selected section produces its own payment
  record. All-or-nothing validation — no partial saves.
  amount_agreed set server-side for rent only (from lease).

  Landlord token management UI: Generate, reveal/mask, copy link,
  revoke with optional reason, history of revoked tokens.

  Landlord payment audit view: Read-only. All submissions with
  month grouping dividers and duplicate submission indicators.
  "Unverified" badge on every record.

  Monthly submission summary: Groups by (year, month), counts
  all confirmation types together.

  Landlord review system: originally landlord_review_data.json
  with append-only event records. Now replaced by threads.json
  (see 2026-02-13 entries above).

  Token validity decision: is_active == true only. Lease expiry
  does NOT affect token validity. Access control is explicitly
  landlord-controlled.

  Schema decision: disclaimer_acknowledged narrowed from
  "bool or ISO timestamp" to "str (ISO timestamp)" only for
  stronger audit trail.

----------------------------------------------------------------

2026-02-07  Phase 2 — Flagged payment conversations

  Extended the landlord review system into structured conversation
  threads. Landlords flag with a message, tenants reply, landlords
  reply back or close.

  Schema extended (backward compatible via _normalize_event,
  now deleted along with entire event-based system):
  - reviewed_at → created_at
  - review_type → event_type
  - internal_note → message
  - Added: actor ("landlord" | "tenant"), attachments (list)

  Conversation state was computed on read, never stored.
  This approach has been superseded by explicit thread status
  and waiting_on fields in threads.json.

  Tenant visibility: Only "flagged" and "response" events shown.
  "Acknowledged" events are never visible to tenants.

  Attachment reuse: save_proof_file() used for both payment proofs
  and conversation attachments. Single file per reply.

----------------------------------------------------------------

2026-02-07  Tenant form label — "Amount Paid"

  Changed field label from "Amount Declared (₹)" to "Amount Paid (₹)"
  with helper text "The amount you actually paid (before any TDS
  deduction)". The form field name remains amount_declared in code.
  No backend or schema changes.

  Rationale: "Declared" is legally precise but confusing for
  tenants. "Paid" is what tenants understand. The backend field
  name was left unchanged to avoid migration.

----------------------------------------------------------------

2026-02-06  AI autofill flow stabilised

  AI autofill runs once per lease. After applying, the AI button
  is disabled and "Return to AI Preview" button appears (does not
  re-run AI or incur cost).

  Inline field explanations show provenance after applying:
  "Suggested by AI", "AI suggested X, changed by you",
  "Entered by you", "AI did not find a value",
  "You reverted to the AI-suggested value".

  Special case: Lease nickname never shows "AI did not find a
  value" and never shows explanation text below the field.

----------------------------------------------------------------

2026-02-06  Deletion changed to typing "DELETE"

  Single version deletion requires typing "DELETE"
  (case-insensitive). Group deletion (entire lease with all
  renewals) requires typing the lease nickname.

  Rationale: Typing the lease nickname was error-prone for single
  version deletion. "DELETE" is unambiguous. The nickname
  requirement was kept for group deletion as an extra safety
  measure since it destroys all versions.

  The old deletion rules section (which said "re-type the lease
  nickname" for all deletions) was superseded by this change.

----------------------------------------------------------------

2026-02-06  Loading UX — no full-page dim

  Global loading overlay no longer dims the entire page. Spinner
  and message are wrapped in a centered loading card. Only the
  card is opaque; background remains visible but non-interactive.

----------------------------------------------------------------

2026-02-05  Monetary formatting standardised

  All displayed monetary amounts use thousands separators
  (format_money Jinja filter). Stored values remain raw numbers.
  Applies to dashboard cards, view mode financials, comparison
  modal, and edit mode change lists. Missing values display as —.

----------------------------------------------------------------

2026-02-05  Renewal creation — fully initialised nested structures

  All renewals now include lock_in_period.duration_months and
  renewal_terms.rent_escalation_percent at creation time,
  defaulting to null. No longer relies on migration to fill gaps.

  Ensures consistent data shape across all renewal creation flows.

----------------------------------------------------------------

2026-02-05  Legacy lease — missing document handling

  Early (pre-migration) leases without stored PDFs now show an
  informational modal ("Lease Document Needed") instead of a
  generic AI extraction error. Guides the user to re-upload.
  Uses calm informational language, not error/danger styling.

  This is a legacy-only scenario. All newly uploaded leases
  automatically store both PDF and extracted text.

----------------------------------------------------------------
END OF HISTORICAL LOG
----------------------------------------------------------------
