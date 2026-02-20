----------------------------------------------------------------
PROJECT: Mapmylease — Lease Management & Renewal Assistant
----------------------------------------------------------------
AUTHORITATIVE REFERENCE — READ THIS FILE FIRST

This file describes what the app IS and what it GUARANTEES.
It does not contain history, roadmaps, or speculative features.

For historical decisions and fixes, see PROJECT_FIXES_AND_DECISIONS.md.
For planned but unbuilt features, see ACTIVE_ROADMAP.md.
For active implementation work, see ACTIVE_BUILD.md.

----------------------------------------------------------------
BRANDING NOTE
----------------------------------------------------------------

The user-facing product name is MapMyLease (previously Easemylease).
The page header and <title> now display "MapMyLease".
Internal references, file names, and repository name may still use
older terminology. Treat "MapMyLease" as authoritative for any
new user-facing text.

----------------------------------------------------------------
PRODUCT DEFINITION
----------------------------------------------------------------

Mapmylease is a local, single-user Flask web app for managing
property lease documents.

The app allows:
- Uploading lease PDFs/images and extracting text via OCR
- Using AI (currently Claude via the Anthropic API) to suggest
  structured lease details from extracted text
- Manually editing and saving lease details
- Managing lease renewals as explicit versions
- Comparing changes across renewal versions
- Tracking lease expiry and rent due dates
- Tenant payment confirmation via token-based links (no logins)
- Landlord review of tenant submissions with conversation threads
- Tracking expected vs submitted payment categories per month

The app prioritises:
- Auditability (what AI suggested vs what user saved)
- Persistence (no in-memory-only critical data)
- Safety (confirmations before destructive actions)
- Beginner-friendly UI (clear flows, no hidden state)
- Transparency across lease versions (explicit change history)

----------------------------------------------------------------
DEVELOPMENT RULES (MANDATORY)
----------------------------------------------------------------

The user is a complete beginner.

For ALL future work on this project:

1. Claude MUST explain changes in plain English.
2. Claude MUST show BEFORE / AFTER diffs for every change.
3. Claude MUST ask for explicit approval before modifying ANY file.
4. Claude MUST make ONE logical change at a time.
5. Claude MUST NOT automatically implement changes.
6. Claude MUST pause immediately if the user says "pause" or "stop".

Violating these rules is a critical error.

----------------------------------------------------------------
CORE CONCEPTS
----------------------------------------------------------------

Lease Groups and Versions
- Every lease belongs to a lease_group_id.
- lease_group_id is the durable identity. lease_id is per-version.
- Renewals create a NEW lease record with the same lease_group_id
  and an incremented version number.
- Only one version per group has is_current = true.
- Older versions are immutable historical records.
- If the current version is deleted, the previous version
  becomes current.
- A renewal is treated as a fresh contract, not a delta.

Tenant vs Landlord
- The landlord is the single local user of the app.
- Tenants access the app via unguessable token-based URLs.
- Tenants can submit payment confirmations and reply to flags.
- Tenants cannot see other leases, edit lease data, or access
  the landlord dashboard.
- There is no authentication system. Access is token-controlled.

Current Values vs AI Extraction vs Source Document
- current_values = what is legally in force (editable by landlord)
- ai_extraction = suggestions + evidence only (audit trail)
- source_document = immutable reference text from upload
- AI never applies business logic or overwrites current_values
  automatically. The user explicitly applies AI suggestions.

Expected Payments
- Each lease defines which payment categories are expected monthly
  (rent, maintenance, utilities).
- The system compares expected categories against submitted
  categories to determine monthly coverage.
- Coverage and conversation status are two independent signals.
  Neither replaces the other.

----------------------------------------------------------------
DATA ARCHITECTURE
----------------------------------------------------------------

The app uses five JSON data files. All are independent.
All save operations use atomic writes (tmp + fsync + rename).

  lease_data.json
  - Lease records with versioning
  - Load: _load_all_leases()  /  Save: _save_lease_file()
  - Auto-migrates old formats on load (idempotent)

  payment_data.json
  - Tenant payment confirmations (append-only, immutable)
  - Load: _load_all_payments()  /  Save: _save_payment_file()

  tenant_access.json
  - Tenant access tokens (revocable by landlord)
  - Load: _load_all_tenant_access()  /  Save: _save_tenant_access_file()

  threads.json
  - Unified conversation threads and messages
  - Load: _load_all_threads()  /  Save: _save_threads_file()
  - Replaces landlord_review_data.json (superseded 2026-02-13)
  - No migration was performed — clean cut on test data
  - All legacy event-based code removed (2026-02-13)
  - IMPORTANT: _load_all_threads() is NOT a pure read. It
    performs an idempotent inline schema backfill: if any thread
    lacks escalation fields (needs_landlord_attention,
    escalation_started_at, last_reminder_at,
    auto_reminders_suppressed), it adds them with safe defaults
    and writes the file back to disk. This runs once per
    thread that lacks the fields, then never again.
 
  termination_data.json                                                                                               
  - Early lease termination events                                                                                    
  - Load: _load_all_terminations()  /  Save: _save_termination_file()

All runtime data files are gitignored.

Separation rules:
- Payment records must NEVER be mixed with access control data.
- Presentation preferences must NEVER live inside lease_data.json.
- Lease data must NEVER be modified by the payment system.
- Thread and conversation data must live in threads.json only.
  No separate reminder, communication, or notification files.

----------------------------------------------------------------
AUTHORITATIVE DATA MODEL
----------------------------------------------------------------

A. Lease Record (lease_data.json)

  Top-level fields:
    id                                  str (uuid4)
    lease_group_id                      str (uuid4, shared across renewals)
    version                             int (1, 2, 3, ...)
    is_current                          bool
    status                              "active" | "draft"
    needs_expected_payment_confirmation bool
    created_at                          str (ISO timestamp)
    updated_at                          str (ISO timestamp)

  lease["source_document"]:
    filename                            str | null
    mimetype                            str | null
    extracted_text                      str | null (full OCR/PDF text)
    extracted_at                        str (ISO timestamp) | null

  lease["current_values"]:
    lease_nickname                      str | null
    lessor_name                         str | null
    lessee_name                         str | null
    lease_start_date                    str (YYYY-MM-DD) | null
    lease_end_date                      str (YYYY-MM-DD) | null
    monthly_rent                        number | null
    security_deposit                    number | null
    rent_due_day                        number (1-31) | null

    lock_in_period:
      duration_months                   number | null

    renewal_terms:
      rent_escalation_percent           number | null

    expected_payments:                  list of objects
      Each: { type, expected, typical_amount }
      - type: "rent" | "maintenance" | "utilities"
      - expected: bool (mandatory)
      - typical_amount: number | null
      - If expected == false, typical_amount MUST be null
      - Rent is always expected and is not toggleable in the UI

  lease["ai_extraction"] (present only when AI has been run):
    ran_at                              str (ISO timestamp)
    fields:
      <field_name>:
        value                           extracted value
        page                            int | null
        evidence                        str | null

  needs_expected_payment_confirmation behaviour:
    - Existing leases (migration): false
    - New lease uploads: false
    - Renewal uploads: true
    - Renewals via "Renew" button: true
    - Any Edit Mode save: resets to false

B. Payment Confirmation (payment_data.json)

  Structure: { "confirmations": [...] }

  Each record:
    id                                  str (uuid4)
    lease_group_id                      str (uuid4)
    confirmation_type                   "rent" | "maintenance" | "utilities"
    period_month                        int (1-12)
    period_year                         int (YYYY)
    amount_agreed                       number | null (set for rent only)
    amount_declared                     number (required, positive)
    tds_deducted                        number | null
    date_paid                           str (YYYY-MM-DD) | null
    proof_files                         list of str (relative file paths)
    verification_status                 "unverified" (ALWAYS)
    disclaimer_acknowledged             str (ISO timestamp, required)
    submitted_at                        str (ISO timestamp, server-set)
    submitted_via                       "tenant_link" | "landlord_manual"
    notes                               str | null

  Immutability rules:
  - The confirmations list is append-only.
  - Every record is frozen at creation — no field is ever changed.
  - Corrections or missing proof: submit a NEW record.
  - verification_status is always "unverified".
  - Multiple submissions per month are allowed.
  - Period is determined solely by (period_month, period_year).

C. Tenant Access Token (tenant_access.json)

  Structure: { "tenant_tokens": [...] }

  Each record:
    token                               str (secrets.token_urlsafe(32))
    lease_group_id                      str (uuid4)
    is_active                           bool (mutable)
    issued_at                           str (ISO timestamp)
    revoked_at                          str (ISO timestamp) | null
    revoked_reason                      str | null
    last_used_at                        str (ISO timestamp) | null

  Rules:
  - The token string IS the identifier (no separate id field).
  - Bound to lease_group_id (survives renewals).
  - At most ONE active token per lease_group_id at any time.
  - Revoking a token NEVER deletes payment history.
  - Token validity: is_active == true. Lease expiry does NOT
    affect validity. Access control is landlord-controlled.
  - Only is_active and last_used_at are mutable after creation.
  - revoked_at and revoked_reason are write-once (set at revocation).

D. Thread (threads.json)

  Structure: { "threads": [...], "messages": [...] }

  Each thread:
    id                                  str (uuid4)
    lease_group_id                      str (uuid4)
    topic_type                          "payment_review" | "missing_payment"
                                        | "renewal" | "general"
    topic_ref                           str | null (query key, e.g. "rent:2026-01")
    status                              "open" | "resolved"
    waiting_on                          "landlord" | "tenant" | null
    created_at                          str (ISO timestamp)
    resolved_at                         str (ISO timestamp) | null
    needs_landlord_attention            bool (controls attention badge)
    escalation_started_at               str (ISO timestamp) | null
    last_reminder_at                    str (ISO timestamp) | null
    auto_reminders_suppressed           bool (default false)

  Additional fields (present on missing_payment threads):
    expected_due_date                   str (YYYY-MM-DD) | absent
    expected_amount                     number | absent
    is_first_month                      bool | absent

  topic_ref is a query key, not a foreign key. For payment-related
  threads it identifies the category and period (e.g. "rent:2026-01").
  For renewal or general threads it may be null.

  Thread status and waiting_on are explicitly stored, never inferred
  from message patterns.

E. Message (threads.json)

  Each message:
    id                                  str (uuid4)
    thread_id                           str (references thread.id)
    created_at                          str (ISO timestamp)
    actor                               "landlord" | "tenant" | "system"
    message_type                        "submission" | "flag" | "reply"
                                        | "reminder" | "auto_reminder"
                                        | "acknowledge" | "nudge"
    body                                str | null
    payment_id                          str | null (required for submission messages,
                                        references payment_data.json)
    attachments                         list of str (relative file paths)
    channel                             "internal" (default; future: "whatsapp"
                                        | "email" | "sms")
    delivered_via                       list of str (default: ["internal"])
    external_ref                        str | null (for future external channel
                                        message matching)

  Superseded model (pre-2026-02-13, fully removed):
  - landlord_review_data.json stored flat event records with fields:
    id, payment_id, lease_group_id, created_at, event_type, actor,
    message, attachments. Conversation state was implicit, computed
    by get_conversation_state() from the latest "flagged" event.
  - Legacy field names (reviewed_at, review_type, internal_note) and
    the "noted" event type were normalised on read via _normalize_event().
  - All code supporting this model has been deleted. No migration
    was needed — all data was test data at time of switchover.
    landlord_review_data.json is no longer referenced in code or
    .gitignore.

F. Termination Event (termination_data.json)

  Structure: { "terminations": [...] }

  Each record:
    id                                  str (uuid4)
    lease_id                            str (references a specific lease version)
    termination_date                    str (YYYY-MM-DD)
    terminated_at                       str (ISO timestamp)
    terminated_by                       "landlord"
    note                                str | null

  Creation: create_termination_event() validates 5 checks and
  appends to the file. POST /lease/<lease_id>/terminate route
  with confirmation modal. The governing lease function consumes
  this data when determining which version covers a given month.

----------------------------------------------------------------
STATE MACHINES
----------------------------------------------------------------

Thread lifecycle (unified model, from 2026-02-13):

  Thread states:
    status: "open" | "resolved"
    waiting_on: "landlord" | "tenant" | null

  waiting_on transitions (explicit, never inferred):
    Tenant submits or replies       → waiting_on = "landlord"
    Landlord flags or replies       → waiting_on = "tenant"
    Landlord acknowledges           → status = "resolved", waiting_on = null,
                                      needs_landlord_attention = false
    System auto-resolves            → status = "resolved",
                                      needs_landlord_attention = false
                                      (waiting_on is NOT changed)
    reminder / auto_reminder / nudge → no change to waiting_on

  needs_landlord_attention sync (payment_review threads only):
    add_message_to_thread() synchronises needs_landlord_attention
    after every message, scoped to payment_review threads only:
      status == "open" AND waiting_on == "landlord" → true
      status == "open" AND waiting_on == "tenant"   → false
      status == "resolved"                          → false
    missing_payment threads are NOT affected — they manage
    needs_landlord_attention via the escalation pipeline.

  Allowed landlord actions: Acknowledge or Raise a flag (binary).
  "Noted" does not exist as an active UI action.

  Conversation lifecycle:
    1. Thread created (e.g. tenant submits payment)
    2. Landlord reviews → may acknowledge (resolves) or flag (message
       required, waiting_on flips to "tenant")
    3. Tenant sees thread + reply form
    4. Either party can send replies (message_type: "reply")
    5. Landlord closes by submitting "acknowledge" message
    6. Tenant sees "Acknowledged — no further action required"
       and the reply form disappears

  Tenant visibility:
    Tenant sees threads of type: payment_review, missing_payment,
    general. Renewal threads are visible but tenant cannot resolve.
    Tenant-visible message types: submission, flag, reply, reminder,
    auto_reminder.
    Tenant does NOT see: nudge, acknowledge, internal-only system
    messages.

Missing payment thread lifecycle (rent):

  Stage 1 — CREATED (materialised on dashboard load)
    status = "open"
    waiting_on = "tenant"
    needs_landlord_attention = false
    last_reminder_at = null
    escalation_started_at = null
    auto_reminders_suppressed = false
    Thread is NOT visible in attention badge.

  Stage 2 — GRACE PERIOD (days 1–2 after due date)
    One automatic reminder sent (max 1 per thread ever).
    message_type = "auto_reminder", actor = "system".
    last_reminder_at set to current timestamp.
    needs_landlord_attention remains false.
    Thread is still NOT visible in attention badge.
    Manual landlord reminders also set last_reminder_at,
    permanently blocking automatic reminders for that thread.

  Stage 3 — ESCALATED (day 3+ after due date)
    needs_landlord_attention = true (one-time flip).
    escalation_started_at = current timestamp (set once).
    No system message appended (silent escalation).
    Thread now visible in attention badge + Action Console.
    Reminder window and escalation threshold are mutually
    exclusive by timing.

  Stage 4 — RESOLVED (two paths)
    Auto-resolve (matching payment submitted):
      status = "resolved", resolved_at = now
      needs_landlord_attention = false
    Manual acknowledge (via add_message_to_thread):
      status = "resolved", waiting_on = null
      resolved_at = now

  Key invariants:
  - waiting_on remains "tenant" throughout (never flips)
  - Max automatic reminders per thread = 1
  - Escalation is silent (no system message appended)
  - Attention visibility controlled solely by
    needs_landlord_attention, NOT by waiting_on
  - Grace period = 2 days (hardcoded timedelta(days=2))
  - Auto-resolution evaluated BEFORE escalation and
    reminders in the pipeline — a paid month never
    escalates or receives a reminder

  Prior model (pre-2026-02-13, fully removed):
    Conversation state was implicit, computed on read by
    get_conversation_state(). This function has been deleted.
    It found the latest "flagged" event and checked whether any
    subsequent event closed the conversation. Category states were
    computed per payment per month:
      Landlord-facing: tenant_replied, flagged, pending_review,
        acknowledged (priority 1–4).
      Tenant-facing: action_required, you_responded, submitted,
        acknowledged (priority 1–4).
    These computed states are superseded by explicit thread status
    and waiting_on fields. All event-based functions
    (_normalize_event, get_events_for_lease_group,
    get_events_for_payment, get_conversation_state) have been
    deleted.

----------------------------------------------------------------
MONTHLY COVERAGE MODEL
----------------------------------------------------------------

Each month within a lease period is evaluated for payment coverage.

  compute_monthly_coverage(expected_payments, month_payments)
  Returns:
    expected_categories   list of expected category type strings
    covered_categories    list of submitted category types
    missing_categories    list of expected but not submitted types
    coverage_summary      "X / Y" string
    is_complete           bool

Coverage and review status are independent signals.

Submission Status indicators (both landlord and tenant views):
  ✅  Category covered (submitted and acknowledged)
  ❗  Category expected but missing
  ❓  Category covered but flagged or awaiting action
  —   No expected categories defined for this month

Monthly summary visibility:
- Last 6 months are always shown.
- Older months appear only if they have missing categories or
  any category state that is not "acknowledged".

Coverage vs Threads (critical distinction):
- Coverage is the INFORMATIONAL layer. It shows expected vs
  submitted payments. It is always visible in monthly summaries.
  It does NOT create threads. It does NOT trigger the attention
  badge. It does NOT represent actionable work.
- Threads are the ACTIONABLE layer. They represent items that
  require someone's attention. They are created by explicit
  triggers (see UNIFIED THREAD MODEL below), not by coverage
  state. They drive the attention badge.
- These two layers coexist and must never be conflated.

----------------------------------------------------------------
GOVERNING LEASE LOGIC
----------------------------------------------------------------

get_governing_lease_for_month(lease_group_id, target_year, target_month)

Determines which lease version governs any given calendar month:
- Skips drafts and leases with missing dates
- Checks for early termination to compute effective end date
- Compares at month level: start_month <= target <= effective_end_month
- Tiebreaker: latest start date, then highest version number
- The termination month itself is still IN_LEASE;
  months after it are OUT_OF_LEASE

Returns:
  IN_LEASE with lease data, lease_id, and version number
  OR
  OUT_OF_LEASE with reason: pre_lease | post_lease | gap | terminated

----------------------------------------------------------------
NAME NORMALISATION
----------------------------------------------------------------

_normalize_name(name) is the SINGLE source of truth for name
comparison across the entire app. Used by both landlord grouping
and tenant continuity duration calculation.

- Strips titles: Prof, Mr, Mrs, Ms, Dr (case-insensitive)
- Returns (display_name, normalised_key) tuple
- Returns (None, None) for empty/null input

----------------------------------------------------------------
SECURITY AND SAFETY INVARIANTS
----------------------------------------------------------------

Data protection:
- All JSON saves use atomic writes (tmp + fsync + rename).
- Payment confirmations are append-only and immutable.
- Revoking a token never deletes payment history.
- Proof files are append-only (never overwritten or deleted).
- Proof files are namespaced: uploads/proofs/{lease_group_id}/

Destructive action gates:
- Single version deletion: requires typing "DELETE"
- Lease group deletion: requires typing the lease nickname
- Both are case-insensitive
- Delete confirmation modals clearly explain consequences

Verification discipline:
- "Submitted" and "Declared" are the only permitted concepts.
- Nothing is ever treated as verified.
- verification_status is always "unverified".
- Landlords must independently verify payments via bank records.
- All payment-related UI carries explicit disclaimers.

Access control:
- No authentication system exists.
- Tenant access is via unguessable token URLs (256 bits entropy).
- Tokens are landlord-controlled (generate / revoke).
- app.secret_key is hardcoded ("dev-secret-key") — used only
  for Flask flash messages, not for security.
- Two people with the same token link are indistinguishable.

Template safety:
- Templates must NOT compute business logic.
- All derived values are attached in routes via underscore-prefixed
  keys (e.g. _earliest_start_date, _tenant_continuity,
  _needs_attention, _attention_count, _attention_items,
  _is_terminated, _is_expired, _can_renew,
  _termination_date_display, _termination_days_elapsed,
  _expiry_date_display).
- Helper functions must NEVER reload JSON — always accept
  pre-loaded data as arguments.

Dashboard caching:
- The dashboard route uses a versions_cache dict to call
  get_lease_versions at most ONCE per unique lease_group_id.
- The dashboard route has TWO loops over leases. The first loop
  computes version history and materialises threads. The second
  loop computes attention and lifecycle state. Both loops must
  independently read cv = lease.get("current_values", lease) —
  the variable does NOT carry across loops.

Upload state cleanup:
- The global uploads={} dict holds in-memory upload state during
  file processing. It is cleared at two points:
  1. At the end of upload_file() before redirect (data is persisted)
  2. At the start of index() when new_lease=True (clean upload page)
- cleanup_draft_leases() runs at the start of the dashboard branch
  to restore previous versions when abandoned renewal drafts exist.

----------------------------------------------------------------
UX PRINCIPLES
----------------------------------------------------------------

Dashboard cards are calm summaries:
- Show: nickname, tenant name + continuity duration, days until/past
  expiry, monthly rent, View Lease button
- No urgency colour accents on cards
- No delete buttons on cards
- No "Needs Attention" button on dashboard cards (removed 2026-02-20;
  lease detail view button preserved)
- Expiry is informational (days + date), not alarming
- Lifecycle stamps: diagonal EXPIRED or TERMINATED overlays
  (bold red border, no background, vertically positioned to avoid
  overlapping primary CTAs) replace the old full-width amber ribbons
- Lifecycle priority remains TERMINATED > EXPIRED > ACTIVE; only the
  highest applicable state renders a stamp.
- Nickname has light grey background fill (#f3f4f6); no special
  colour for expired/terminated (stamp is sole lifecycle indicator)
- Primary "Add Renewal Lease" button appears when _can_renew is True

Dashboard layout:
- Two-column grid: 1.6fr (leases) / 0.9fr (Action Console), gap 32px
- Lease cards in 2-column grid within lease column (max-width 520px)
- Responsive: single column below 900px (cards), 1024px (dashboard)
- Server-side landlord filter: dropdown next to "Your Leases" header,
  filters both lease cards and Action Console items, only shown when
  >1 landlord exists, defaults to "All Landlords", URL ?landlord=<name>
- Landlord group headers: 16px/600/#111827 with inline count "(2)"
- Upload New Lease button: subtle outline style in header row

Monthly summaries default to collapsed:
- Both landlord and tenant see last 6 months by default
- Older months appear only if they need attention
- Clicking a month opens a modal (not inline expansion)

Modals use DOM node movement:
- Server-rendered payment cards are MOVED (not cloned) between
  a hidden storage container and modals via appendChild
- This preserves form state, event handlers, and avoids duplication
- Modal close always moves ALL cards back to storage

History view is read-only:
- A single CSS class ('history-view') on the modal body hides
  all interactive elements with !important

Monetary formatting:
- All displayed amounts use thousands separators (₹1,85,000)
- Stored values remain raw numbers
- Non-monetary values are never formatted

AI autofill:
- Can only be run once per lease
- After applying, the AI button is disabled; "Return to AI Preview"
  appears instead (does not re-run AI or incur cost)
- Inline field explanations show provenance: "Suggested by AI",
  "Changed by you", "Entered by you", etc.
- Lease nickname AI format: "City - Condo/Locality Name -
  Apartment/House Number" (e.g. "Gurgaon - World Spa - A5-102")

Attention in lease detail view:
- "Needs attention" button appears in the lease detail header
  (right-aligned, same row as "Lease Details" heading)
- Only shown when _attention_count > 0
- Opens the same attention modal as dashboard cards
- Uses openAttentionModal() / closeAttentionModal() JS functions

----------------------------------------------------------------
TECH STACK
----------------------------------------------------------------

- Python (Flask)
- Jinja2 templates
- JSON file storage (single-user, no database)
- OCR: Tesseract (via pytesseract + pdf2image)
- PDF parsing: pypdf (with OCR fallback)
- AI: Currently Claude via the Anthropic API (optional; app
  functions without it)
- Frontend: Vanilla JavaScript (no framework, no build step)

----------------------------------------------------------------
BACKUP AND RECOVERY
----------------------------------------------------------------

There is no automated backup system. All persistent state lives
in JSON files in the project directory and uploaded files in the
uploads/ folder.

To back up: copy the entire project directory.
To recover: restore the directory from backup.

If a JSON file is corrupted, the corresponding load function
returns an empty default structure (e.g. {"leases": []}). This
prevents crashes but means data loss is silent. Users should
maintain manual backups of their data files.

----------------------------------------------------------------
VERSION CONTROL
----------------------------------------------------------------

Repository: https://github.com/sbhasin2019/Lease-Agent-App
Default branch: main
Local development on macOS (Terminal + Python venv)

----------------------------------------------------------------
  DASHBOARD ATTENTION BADGES
 ----------------------------------------------------------------

  Attention badges on dashboard lease cards have been removed
  (2026-02-20). The Action Console is now the sole surface for
  attention items on the dashboard.

  The lease detail view retains its "Needs attention" button
  in the header (right-aligned, same row as "Lease Details").

  Attention badge counts:
    Threads where status == "open" AND needs_landlord_attention == true

  It does NOT count:
    - Threads where needs_landlord_attention == false
    - Threads where waiting_on == "tenant" (unless escalated)
    - 7-day nudge suggestions
    - Coverage indicators (informational layer)

  The badge answers: "What requires MY action right now?"

  Note: waiting_on does NOT control badge visibility.
  needs_landlord_attention is the sole gate for attention.
  These two concepts are independent:
    waiting_on = who needs to act next (responsibility)
    needs_landlord_attention = show in badge (visibility)

  Clicking the badge opens an Attention Overview modal listing
  open threads grouped by lease, each with a topic label, latest
  message summary, and "View Thread" link.

  The Attention Overview modal also includes a separate
  "Follow-ups (Optional)" section for 7-day nudge suggestions.
  These are visually distinct from actionable items and are not
  counted in the badge.

  Prior model (pre-2026-02-13, fully removed):
    Badge counted months (not threads) using two helper functions:
    compute_lease_attention_count() and get_lease_attention_items().
    Both functions have been deleted. Triggers were: pending_review
    (category-aware via cat_has_any_review pattern) and
    tenant_replied (open conversation where tenant spoke last).
    "awaiting_tenant" never triggered attention — this rule
    carries forward in the thread model.

  ----------------------------------------------------------------
  PAYMENT THREADS
  ----------------------------------------------------------------

  Threads are explicit persistent objects stored in threads.json.
  Each thread represents one actionable topic per lease per category.

  Thread types:
    payment_review   — tenant submitted, landlord must review
    missing_payment  — expected payment not submitted past threshold
    renewal          — lease expiry approaching
    general          — manual landlord-tenant communication

  Threads contain messages (see data model section E). The timeline
  for a thread is built by loading its messages from threads.json
  and joining payment details from payment_data.json via
  message.payment_id where applicable.

  Smart redirect after review actions:
    - If same month still has unresolved threads → redirect with
      open_month + return_to=attention (re-opens month modal)
    - If all threads resolved → redirect with return_attention_for
      (opens attention overview modal)

  Prior model (pre-2026-02-13, fully removed):
    build_payment_threads() grouped payments by category and
    computed ephemeral thread objects with merged timelines.
    This function has been deleted. Status was derived from
    conversation state and cat_has_any_review patterns.
    action_payment_id was computed per category
    (active_conversation_payment_id if it existed, else
    latest_submission_payment_id). Thread blocks are now built
    inline in the lease detail route directly from threads.json.

----------------------------------------------------------------
UNIFIED THREAD MODEL (LOCKED 2026-02-13)
----------------------------------------------------------------

This section describes the thread-based communication and attention
system that unifies payment reviews, missing payment reminders,
renewal prompts, and general landlord-tenant communication into
a single model.

Thread Creation Triggers:

  payment_review:
    Created when: tenant submits a payment (lazily materialised
    on dashboard load, not during tenant submission)
    waiting_on at creation: "landlord"
    needs_landlord_attention at creation: true
    Resolves when: landlord acknowledges

  missing_payment:
    Created when: expected category not submitted past due date
    - Rent: day after rent_due_day if no submission exists
    - Maintenance/utilities: end of month
    - NOT created if rent_due_day is null
    - First lease month respects lease_start_date
    - Future months never evaluated
    waiting_on at creation: "tenant"
    needs_landlord_attention at creation: false
    Resolves when: matching payment submitted (auto-resolution)
    Escalates after 2-day grace period (needs_landlord_attention
    flips to true; see Missing Payment Thread Lifecycle below)

  renewal:
    Created when: lease expiry within configured window
    (e.g. 60 days — see ACTIVE_BUILD.md) and no open renewal
    thread exists. Not created if lease has an effective
    termination date before expiry.
    waiting_on at creation: "landlord"
    Resolves when: renewal lease version created (auto-resolution)

  general:
    Created manually by landlord.

Thread Uniqueness Model:
  A thread is uniquely identified by the compound key:
  lease_group_id + topic_type + topic_ref.

  Deduplication scopes differ by thread type:

  - payment_review: materialise_system_threads() deduplicates
    against ALL statuses (open + resolved) using its own inline
    logic. A resolved payment_review thread prevents re-creation.
    This function does NOT call ensure_thread_exists().

  - missing_payment: materialise_missing_payment_threads() calls
    ensure_thread_exists(), which deduplicates against OPEN threads
    only (via find_open_thread()). A resolved missing_payment thread
    allows re-creation if rent becomes missing again. This is
    intentional — a resolved thread means rent was submitted; if
    that payment is later removed, a new thread should appear.

Idempotency Rule:
  Before creating a thread, check if an OPEN thread exists for
  the same (lease_group_id, topic_type, topic_ref).
  If yes → reuse the existing open thread (append message if needed).
  If no → create a new thread.
  Resolved threads NEVER block new thread creation for
  missing_payment threads. Resolved threads DO block creation
  for payment_review threads (different dedup scope).

Auto-Resolution:
  The system automatically resolves threads when user actions make
  them obsolete:
  - Tenant submits matching payment → missing_payment thread resolves
  - Landlord acknowledges → payment_review thread resolves
  - Renewal lease created → renewal thread resolves
  Resolution sets status = "resolved", waiting_on = null,
  resolved_at = current timestamp, needs_landlord_attention = false.

Thread Materialisation:
  Thread types are created by dedicated materialisation functions
  called from the dashboard route during per-lease enrichment:
  - materialise_system_threads() creates payment_review threads
  - materialise_missing_payment_threads() creates missing_payment
    threads
  - The tenant submission route writes ONLY to payment_data.json.
    It does NOT create threads directly.
  - This avoids multi-file write coupling and orphan states.
  - Both materialisation functions are idempotent, fast, and
    purely data-driven. No background workers required.

----------------------------------------------------------------
ENGINE EXECUTION MODEL — DASHBOARD-TRIGGERED
----------------------------------------------------------------

The thread engine runs on every GET / (dashboard load). There is
no background scheduler, cron job, or async task queue.

Pipeline order (deterministic, runs on every dashboard load):

  Per-lease loop (steps 1–2):

  1. materialise_system_threads(lease_group_id)
     Creates payment_review threads for unthreaded payments.

  2. materialise_missing_payment_threads(lease_group_id, lease)
     Creates missing_payment threads for overdue rent.

  Global steps (steps 3–5, run once after all leases processed):

  3. auto_resolve_missing_payment_threads()
     Resolves open missing_payment threads where a matching
     rent payment now exists in payment_data.json.

  4. send_missing_payment_reminders()
     Sends one automatic reminder per thread during days 1–2
     after the due date (grace period window).

  5. escalate_missing_payment_threads()
     Escalates threads past the 2-day grace period by setting
     needs_landlord_attention = true.

Each engine function loads threads.json independently at its
own entry point, makes changes in memory, and saves once
(only if it mutated state). After each mutating step, the
dashboard route reloads thread_data so subsequent steps see
the latest state.

The pipeline does NOT use a single-load/single-save model
across the full cycle — each function operates on its own
load/save cycle. Exception: materialise_missing_payment_threads()
delegates to ensure_thread_exists(), which loads and saves
per-thread. A pipeline-wide single-load model is a future
optimisation, not current behaviour.

GET / is a mutating request:
  The dashboard route reads AND writes threads.json. This is
  architectural — the engine is triggered by UI access, not
  by a background process.

Idempotency guarantees:
  - Duplicate thread prevention via uniqueness checks
  - Reminder limited to one per thread (last_reminder_at guard)
  - Escalation is a one-time flip (needs_landlord_attention guard)
  - Auto-resolution checks status == "open" before resolving
  - All five functions are safe on repeated runs

Backlog-collapse behaviour:
  If no one loads the dashboard for N days, all accumulated
  logic runs in one deterministic pass on next load. Only
  current state is evaluated — there is no replay of missed
  windows. A thread whose grace period has already passed
  will escalate but will NOT receive a retroactive reminder.

Grace window dependence:
  Automatic reminders are only sent if the dashboard is loaded
  during the 2-day grace period window (days 1–2 after due
  date). If no dashboard load occurs during this window, the
  reminder is permanently skipped — no replay occurs on later
  loads. The thread will still escalate on day 3+ regardless.

Future direction:
  The dashboard-triggered model is expected to be replaced by
  a scheduler-based model in a future phase. All engine
  functions are designed to work identically when called by a
  background scheduler. The transition requires adding a "today"
  parameter to pipeline functions (see ACTIVE_BUILD.md invariant
  #10 — NOT YET IMPLEMENTED) and a new trigger mechanism.

7-Day Nudge (DESIGNED — NOT YET IMPLEMENTED):
  Nudges are computed display prompts, NOT stored messages.
  Condition: thread.status == "open" AND waiting_on == "tenant"
  AND last landlord message >= 7 days ago.

  Primary display: inside the thread view (per-category modal),
  at top of thread. Shows "Tenant hasn't responded in 7 days"
  with [Send Reminder] and [Dismiss Suggestion] buttons.

  Secondary display: in Attention Overview modal under a separate
  "Follow-ups (Optional)" section, visually distinct from
  actionable items.

  Nudges do NOT: create threads, create messages automatically,
  change waiting_on, or increase the attention badge count.

  If landlord sends reminder: a "reminder" message is added to
  the thread, waiting_on remains "tenant". Before sending, the
  system re-checks that thread is still open and waiting_on is
  still "tenant" to prevent race-condition reminders.

External Channel Compatibility:
  The message schema includes channel, delivered_via, and
  external_ref fields. These default to "internal" / ["internal"]
  / null. When external channels (WhatsApp, email, SMS) are
  implemented:
  - Outbound: messages are delivered via configured channels.
    delivered_via records which channels received the message.
  - Inbound: webhook creates a message in the correct thread.
    channel records the source. external_ref links to the
    external message ID for threading.
  - No schema redesign required. Adapters only.

Migration from landlord_review_data.json:
  Migration was NOT performed. All data at switchover time was
  test data. Instead, a clean cut was made:
  - threads.json starts empty
  - materialise_system_threads() creates payment_review threads
    for existing unthreaded payments on first dashboard load
  - All legacy event-based code has been deleted (9 functions)
  - landlord_review_data.json is no longer referenced anywhere
  - .gitignore entry for landlord_review_data.json removed

----------------------------------------------------------------
WHAT IS NOT IMPLEMENTED
----------------------------------------------------------------

The following features are explicitly NOT built. They must not
be partially or implicitly implemented without explicit scope
approval. For details on intent and dependencies, see
ACTIVE_ROADMAP.md.

Implemented (thread model):
- Unified thread-based communication engine (threads.json)
  payment_review threads are operational: materialisation,
  landlord flag/reply/acknowledge, tenant reply, thread timelines,
  smart redirect. All legacy event-based code removed. Legacy
  landlord_review_data.json architecture deleted.
  payment_review threads set needs_landlord_attention = true at
  creation and sync it via add_message_to_thread() on every
  message action. They appear in the attention badge and Action
  Console when waiting_on == "landlord".
- Missing payment threads for rent (implemented 2026-02-18):
  materialisation, auto-resolution, automatic reminders (1 max),
  escalation after 2-day grace period, attention badge integration.
  See ACTIVE_BUILD.md Phases 1-9.

Designed but not yet implemented:
- Missing payment threads for maintenance/utilities
- Renewal threads (replaces standalone renewal intent prompts)
- 7-day nudge display (computed, not stored)
- Auto-resolution hooks for renewal threads

Not designed / deferred:
- Dashboard preferences (drag-and-drop ordering, card grouping,
  folder-style groups)
- External channel delivery (WhatsApp, email, SMS) — schema is
  ready, adapters not built
- User authentication or accounts
- Payment verification or reconciliation
- Editing or deleting payment confirmations
- Historical AI extraction preservation across versions
- Mobile app
- Automated backup or recovery

----------------------------------------------------------------
UI ARCHITECTURE — CONTROL CENTRE MODEL (Phase 10+)
----------------------------------------------------------------

[Phase 10 — In Progress]

This section describes the UI architecture transition from a
modal-driven alert model to a persistent Action Console model.

Architectural Principle:

  The app is shifting from:

    "Attention lives inside each lease"
      (landlord opens a lease, sees a modal listing attention items)

  to:

    "Attention lives globally; leases are containers."
      (landlord sees all attention items at a glance without
      opening any lease)

  The Action Console becomes the landlord's operational hub.
  Lease pages remain contextual and informational.

Separation of Concerns:

  Visibility Layer:
    - Lease cards (show urgency indicators)
    - Attention modal (temporary, backward compatibility)
    - Action Console (primary)

  Decision Layer:
    - Action Console ONLY

  No business logic should be tied to the attention modal.
  All decision actions must ultimately live in the Action Console.

------------------------------------------------------------
1. LANDLORD DASHBOARD (NEW STRUCTURE)
------------------------------------------------------------

Purpose:
  Primary operational control centre for landlord.

Desktop Layout (>=1024px):
  Two-column layout.

  LEFT COLUMN (1.6fr):
  - Lease cards in 2-column grid (max-width 520px per card)
  - Grouped by landlord with section headers showing count
  - Server-side landlord filter dropdown (when >1 landlord)
  - Each card:
      - Diagonal lifecycle stamp (EXPIRED/TERMINATED) — red border,
        no background, vertically positioned to avoid overlapping CTAs
      - Nickname with light grey background fill
      - Entire card click filters the Action Console to that lease
        (within the currently selected landlord scope)
      - Explicit "View Lease" link navigates to detail page

  RIGHT COLUMN (0.9fr):
  - Persistent Global Action Console panel
  - Sticky positioning (stays in viewport during scroll)
  - Internally scrollable
  - Shows ALL attention items across all leases by default
    (filtered when landlord dropdown is active)
  - Grouped by lease
  - Sorted by urgency (highest first)
  - Left accent bars: amber (missing_payment), blue (payment_review)
  - Action buttons in collapsed item row:
      missing_payment: Send Reminder (opens modal, 24h cooldown)
      payment_review: Acknowledge + Flag (each opens modal)
  - Expanded panel: thread history + secondary details only

  Global Alerts box:
  Removed from dashboard template (replaced by console).
  get_global_alerts() is still computed and passed to the
  template but the template no longer renders it. This is
  dead code in the dashboard context. The underlying helper
  functions (calculate_lease_expiry_status,
  calculate_rent_payment_status) are still used in the lease
  detail view via calculate_reminder_status().
  get_global_alerts() dashboard integration should be removed
  in a future cleanup.

Responsive Layout (<1024px):
  - Layout stacks vertically: lease cards then Action Console
  - Slide-over mobile console deferred to future phase

------------------------------------------------------------
2. ATTENTION MODAL STATUS
------------------------------------------------------------

The attention modal remains temporarily for backward compatibility.

It will:
- Continue functioning
- Not receive new action buttons
- Not gain new responsibilities
- Be removed in a future refactor once the Action Console
  supports all workflows (reminders, suppression, review actions)

Smart redirect flows (return_attention_for, return_to=attention)
remain functional during the transition period.

------------------------------------------------------------
3. LEASE VIEW (LANDLORD)
------------------------------------------------------------

Purpose:
  Deep inspection, audit history, monthly breakdown,
  payment thread history.

  NOT the primary operational surface.
  Landlord goes here for detail, not for decisions.

Future intent:
  Lease View will later adopt a lease-scoped Action Console,
  but this is not part of the initial Phase 10 implementation.

------------------------------------------------------------
4. TENANT DASHBOARD (FUTURE ALIGNMENT)
------------------------------------------------------------

Tenant UI will conceptually mirror the landlord model:

  Desktop:
    Left:   Lease details
    Right:  Tenant Action Console
              - Overdue rent
              - Submission required
              - Missing confirmations
              - Renewal notices

    Above:
      Ticker:
        - Days remaining in lease
        - Next rent due date

  NOT implemented in Phase 10.
  Backend helpers should be structured for future reuse.
  Mobile behaviour deferred.

------------------------------------------------------------
5. ACTION CONSOLE DATA MODEL
------------------------------------------------------------

The Action Console consumes structured data built by a
backend helper function. The data shape is:

  {
    "lease_groups": [
      {
        "lease_group_id": str,
        "lease_id": str,
        "lease_display_name": str,
        "attention_count": int,
        "items": [
          {
            "thread_id": str,
            "topic_type": str,          // "missing_payment" | "payment_review"
            "topic_ref": str,           // month key e.g. "2026-02"
            "display_label": str,
            "reason": str,
            "urgency_level": str,
            "status": str,              // "open" | "resolved"
            "waiting_on": str,          // "tenant" | "landlord"
            "open_month": str or null,  // same as topic_ref for display
            "expected_amount": int or null,
            "expected_due_date": str or null,
            "auto_reminders_suppressed": bool or null,
            "escalation_started_at": str or null,
            "last_reminder_at": str or null,
            "overdue_days": int or null,     // escalated missing_payment only
            "status_display": str,           // pre-computed for template
            "status_css": str,               // pre-computed CSS class
            "last_action": {                 // null if no messages
              "actor": str,
              "message_type": str,
              "timestamp": str,
              "summary_text": str
            } or null,
            "recent_messages": [             // last 1-3, oldest first
              {
                "id": str,
                "actor": str,
                "message_type": str,
                "body": str or null,
                "created_at": str,
                "attachments": list or null,
                "payment_id": str or null
              }
            ]
          }
        ]
      }
    ],
    "total_open_items": int
  }

Urgency levels (simple string, not numeric):
  "high"   — missing_payment, escalated (overdue past grace)
  "medium" — payment_review, tenant has replied
  "normal" — payment_review, awaiting initial review

Pre-computed display fields (templates must not derive these):
  status_display — human-readable status string
  status_css     — CSS class for styling
  overdue_days   — only present when escalation_started_at is set
                   (gated by escalation state, not numeric truthiness)
  last_action    — summary of most recent message in thread

This function aggregates already-computed thread states.
It does NOT implement escalation or reminder logic.
All state derives from threads.json.

Reminder flow (Phase 10D — operational):
  Send Reminder opens a modal with prefilled, editable draft
  text (greeting uses lessee_name, closing uses lessor_name).
  Landlord edits message and submits. POST /thread/<thread_id>/
  reminder receives body from form, validates non-empty, passes
  to add_message_to_thread(). last_reminder_at set automatically
  (permanently blocks auto-reminders). POST + redirect pattern.
  add_message_to_thread() unchanged.

  Item dict includes lessee_name and lessor_name (loaded from
  lease current_values, empty string fallback if missing).

------------------------------------------------------------
6. STATE SYNCHRONISATION RULE
------------------------------------------------------------

When future actions modify threads (send reminder, suppress,
acknowledge), the Action Console and attention modal must both
reflect updates automatically. This is guaranteed because:

- Both derive state from threads.json
- Page reloads after POST redirects
- No console-specific state exists
- No duplicated logic between console and modal

----------------------------------------------------------------
END OF AUTHORITATIVE CONTEXT
----------------------------------------------------------------
