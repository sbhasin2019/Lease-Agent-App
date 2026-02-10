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

  Backward compatibility: Historical "noted" events are
  normalised to "acknowledged" on read via _normalize_event().
  The backend still recognises "noted" in the close-conversation
  check for old data, but the UI never offers it as an action.

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

  Landlord review system: landlord_review_data.json with
  append-only event records.

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

  Schema extended (backward compatible via _normalize_event):
  - reviewed_at → created_at
  - review_type → event_type
  - internal_note → message
  - Added: actor ("landlord" | "tenant"), attachments (list)

  Conversation state is computed on read, never stored.

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
