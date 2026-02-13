----------------------------------------------------------------
PROJECT: Mapmylease — Lease Management & Renewal Assistant
----------------------------------------------------------------
AUTHORITATIVE REFERENCE — READ THIS FILE FIRST

This file describes what the app IS and what it GUARANTEES.
It does not contain history, roadmaps, or speculative features.

For historical decisions and fixes, see PROJECT_FIXES_AND_DECISIONS.md.
For planned but unbuilt features, see ACTIVE_ROADMAP.md.

----------------------------------------------------------------
BRANDING NOTE
----------------------------------------------------------------

The user-facing product name is Mapmylease (previously Easemylease).
Internal references, file names, and repository name may still use
older terminology. Treat "Mapmylease" as authoritative for any
new user-facing text. No branding overhaul has been performed.

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
                                        | "reminder" | "acknowledge" | "nudge"
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
    Landlord acknowledges           → status = "resolved", waiting_on = null
    System auto-resolves            → status = "resolved", waiting_on = null

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
    Tenant-visible message types: submission, flag, reply, reminder.
    Tenant does NOT see: nudge, acknowledge, internal-only system
    messages.

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
  _needs_attention, _is_terminated, _is_expired, _can_renew,
  _termination_date_display, _termination_days_elapsed,
  _expiry_date_display).
- Helper functions must NEVER reload JSON — always accept
  pre-loaded data as arguments.

Dashboard caching:
- The dashboard route uses a versions_cache dict to call
  get_lease_versions at most ONCE per unique lease_group_id.

----------------------------------------------------------------
UX PRINCIPLES
----------------------------------------------------------------

Dashboard cards are calm summaries:
- Show: nickname, earliest start date, tenant name + continuity
  duration, days until/past expiry, monthly rent, View Lease button
- No urgency colour accents on cards
- No delete buttons on cards
- Expiry is informational (days + date), not alarming
- Lifecycle ribbons: TERMINATED or EXPIRED (amber, full-width)
  appear only when the CURRENT version qualifies
- Primary Renew button appears when _can_renew is True
- Lifecycle priority: TERMINATED > EXPIRED > ACTIVE

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

  Dashboard cards show a 🙋🏻 badge with a count when the landlord's
  attention is needed. The badge is a calm human nudge, not an alert.

  Attention badge counts:
    Threads where status == "open" AND waiting_on == "landlord"

  It does NOT count:
    - Threads where waiting_on == "tenant"
    - 7-day nudge suggestions
    - Coverage indicators (informational layer)

  The badge answers: "What requires MY action right now?"

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
    Resolves when: landlord acknowledges

  missing_payment:
    Created when: expected category not submitted past threshold
    - Rent: X days after rent_due_day (X to be configured)
    - Maintenance/utilities: end of month
    - NOT created if rent_due_day is null
    - First lease month respects lease_start_date
    - Future months never evaluated
    waiting_on at creation: "landlord"
    Resolves when: matching payment submitted (auto-resolution)

  renewal:
    Created when: lease expiry within configured window
    (e.g. 90/60/30/15 days) and no open renewal thread exists
    waiting_on at creation: "landlord"
    Resolves when: renewal lease version created (auto-resolution)

  general:
    Created manually by landlord.

Idempotency Rule:
  Before creating a thread, check if an OPEN thread exists for
  the same (lease_group_id, topic_type, topic_ref).
  If yes → reuse the existing open thread (append message if needed).
  If no → create a new thread.
  Resolved threads NEVER block new thread creation.

Auto-Resolution:
  The system automatically resolves threads when user actions make
  them obsolete:
  - Tenant submits matching payment → missing_payment thread resolves
  - Landlord acknowledges → payment_review thread resolves
  - Renewal lease created → renewal thread resolves
  Resolution sets status = "resolved", waiting_on = null,
  resolved_at = current timestamp.

Thread Materialisation:
  All thread types (payment_review, missing_payment, renewal) are
  created centrally by materialise_system_threads(), called from
  the dashboard route during per-lease enrichment.
  - The tenant submission route writes ONLY to payment_data.json.
    It does NOT create threads directly.
  - This avoids multi-file write coupling and orphan states.
  - materialise_system_threads() is idempotent, fast, and
    purely data-driven. No background workers required.

7-Day Nudge:
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

Implemented (thread model, locked 2026-02-13):
- Unified thread-based communication engine (threads.json)
  payment_review threads are fully operational: materialisation,
  landlord flag/reply/acknowledge, tenant reply, attention badges,
  thread timelines, smart redirect. All legacy event-based code
  removed. Legacy landlord_review_data.json architecture deleted.

Designed but not yet implemented:
- Missing payment threads (replaces standalone reminder system)
- Renewal threads (replaces standalone renewal intent prompts)
- 7-day nudge display (computed, not stored)
- Auto-resolution hooks for missing_payment and renewal threads
  (deferred until those thread types are created)

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
END OF AUTHORITATIVE CONTEXT
----------------------------------------------------------------
