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

  landlord_review_data.json
  - Landlord review events and conversation threads
  - Load: _load_all_landlord_reviews()  /  Save: _save_landlord_review_file()

  termination_data.json
  - Early lease termination events (data layer only; no UI exists)
  - Load: _load_all_terminations()  /  Save: _save_termination_file()

All runtime data files are gitignored.

Separation rules:
- Payment records must NEVER be mixed with access control data.
- Presentation preferences must NEVER live inside lease_data.json.
- Lease data must NEVER be modified by the payment system.

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

D. Review Event (landlord_review_data.json)

  Structure: { "reviews": [...] }

  Each record:
    id                                  str (uuid4)
    payment_id                          str (references payment_data.json)
    lease_group_id                      str (uuid4)
    created_at                          str (ISO timestamp)
    event_type                          "acknowledged" | "flagged" | "response"
    actor                               "landlord" | "tenant"
    message                             str | null
    attachments                         list of str (relative file paths)

  Legacy compatibility:
  - Historical records may use old field names (reviewed_at,
    review_type, internal_note) and the "noted" event type.
  - _normalize_event() maps old names to current schema on read.
  - Historical "noted" events are treated as "acknowledged".

E. Termination Event (termination_data.json)

  Structure: { "terminations": [...] }

  Each record:
    id                                  str (uuid4)
    lease_id                            str (references a specific lease version)
    termination_date                    str (YYYY-MM-DD)
    terminated_at                       str (ISO timestamp)
    terminated_by                       "landlord"
    note                                str | null

  Note: Only the data layer and read functions exist. There is
  no route or UI to create termination events. The governing
  lease function consumes this data when determining which
  version covers a given month.

----------------------------------------------------------------
STATE MACHINES
----------------------------------------------------------------

Landlord-facing category states (per payment category per month):
  Priority 1 (worst): tenant_replied
    → Tenant responded, pending your review
  Priority 2: flagged
    → Flag raised by you, awaiting tenant response
  Priority 3: pending_review
    → Tenant submitted, pending your review
  Priority 4 (best): acknowledged
    → Acknowledged — no further action required

Tenant-facing category states:
  Priority 1 (worst): action_required
    → Landlord responded, action required
  Priority 2: you_responded
    → You responded, awaiting landlord review
  Priority 3: submitted
    → Submitted, awaiting landlord review
  Priority 4 (best): acknowledged
    → Acknowledged — no further action required

Allowed landlord actions: Acknowledge or Raise a flag (binary).
"Noted" does not exist as an active UI action.

Conversation lifecycle:
  1. Landlord flags a payment (message required) → conversation opens
  2. Tenant sees thread + reply form
  3. Either party can send responses (event_type: "response")
  4. Landlord closes by submitting "acknowledged"
  5. Tenant sees "Acknowledged — no further action required"
     and the reply form disappears

Conversation state is computed on read (get_conversation_state),
never stored. It finds the latest "flagged" event and checks
whether any subsequent event closes the conversation.

Tenant visibility: Only "flagged" and "response" events are
shown to tenants. "Acknowledged" events are never tenant-visible.

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
  _needs_attention).
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
WHAT IS NOT IMPLEMENTED
----------------------------------------------------------------

The following features are explicitly NOT built. They must not
be partially or implicitly implemented without explicit scope
approval. For details on intent and dependencies, see
ACTIVE_ROADMAP.md.

- Reminder / proactive nudge system for missing payment categories
- Dashboard preferences (drag-and-drop ordering, card grouping,
  folder-style groups)
- Dashboard attention badges (_needs_attention is always False)
- Renewal intent prompts and suppression logic
- Termination creation UI and routes (only data layer exists)
- User authentication or accounts
- Email / SMS / push notifications
- Payment verification or reconciliation
- Editing or deleting payment confirmations
- Historical AI extraction preservation across versions
- Mobile app
- Automated backup or recovery

----------------------------------------------------------------
END OF AUTHORITATIVE CONTEXT
----------------------------------------------------------------
