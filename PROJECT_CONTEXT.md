 ----------------------------------------------------------------
PROJECT: Lease Management & Renewal Assistant (Single-User MVP)
----------------------------------------------------------------

------------------------------------------------------------------
NOTE ON NAMING:
------------------------------------------------------------------

The user-facing product name is **Easemylease**.
This Project Context may continue to refer to the app descriptively
as a “Lease Management & Renewal Assistant” to focus on behavior
and architecture rather than branding.

UPDATE - NAME Changed from **Easemyleasd** to **Mapmylease**.
This Project Context may continue to refer to the app descriptively
as a “Lease Management & Renewal Assistant” to focus on behavior
and architecture rather than branding.


OVERVIEW
This is a local, single-user Flask web app for managing property lease documents.

The app allows uploading lease PDFs/images, extracting text via OCR, using AI
to suggest structured lease details, manually editing those details, managing
lease renewals (versions), comparing changes across renewals, and tracking
lease expiry and rent reminders.

The app prioritizes:
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

Violating these rules is considered a critical error.

                                                                                  
  ----------------------------------------------------------------
  UPDATED — 8 FEBRUARY 2026                                                                                             
  ----------------------------------------------------------------    

  Lease View & Submission UI Overhaul (LV Series)

  All changes below are presentational and interaction improvements.
  No data model, schema, or backend logic changes unless noted.

  ----------------------------------------------------------------

  LV-2: Lease Comparison Field Ordering
  Status: IMPLEMENTED

  Reordered fields_to_compare in compare_lease_versions() to:
  1. Tenant Name
  2. Monthly Rent
  3. Security Deposit
  4. Rent Due Day
  5. Start Date
  6. End Date
  7. Lock-in Period
  8. Rent Escalation

  Both simple and nested field sections updated.
  No schema or data changes.

  ----------------------------------------------------------------

  LV-3: Monthly Summary Ordering + Tenant Access Collapse
  Status: IMPLEMENTED

  Part A — Monthly summary reverse ordering:
  - Added monthly_summary.reverse() after list construction
  - Latest month now appears first in both landlord and tenant views

  Part B — Tenant Access section collapse:
  - Collapsed by default on page load
  - "View tenant access" button reveals section (one-way expand)

  ----------------------------------------------------------------

  LV-4: Lease Comparison Modal + Unchanged Fields
  Status: IMPLEMENTED

  Backend (app.py):
  - compare_lease_versions() now includes ALL 8 fields, even if
    unchanged between versions
  - Unchanged fields tagged with change_type = "unchanged" and
    display "(No change from previous lease)"

  Template (index.html):
  - Inline toggle replaced with modal (#changesModal)
  - Modal shows all 8 fields with change status
  - Print button added to modal header
  - @media print CSS scopes printable content to modal only
  - Click-outside and Escape key close handlers

  ----------------------------------------------------------------

  LV-5: Monthly Submission Summary Visual Refinement
  Status: IMPLEMENTED

  Template (index.html):
  - Table reduced from 4 columns to 3 (removed Status column)
  - Remaining columns: Month, Submissions, Review
  - Status badges with priority-based styling:
    - tenant_replied / flagged: bold, prominent
    - reviewed: muted green
  - Empty months shown as neutral grey

  ----------------------------------------------------------------

  Lease Version History Collapse + Rename
  Status: IMPLEMENTED

  Template (index.html):
  - Heading renamed to "Lease Version History"
  - Section collapsed by default
  - "View lease history" / "Hide lease history" toggle buttons

  ----------------------------------------------------------------

  LV-6: Per-Month Submission Modal (Landlord)
  Status: IMPLEMENTED

  Architecture:
  - Submission cards tagged with data-period-month and
    data-period-year attributes
  - Hidden storage container holds all server-rendered cards
  - Modal populated via DOM node movement (appendChild) — cards
    are MOVED, never cloned, preserving forms/handlers/state
  - Defensive cleanup: always move existing children back to
    storage before populating modal

  Template (index.html):
  - #submissionsModal with header buttons:
    - Back (context-dependent label)
    - Print
    - View full history
    - Close
  - All buttons use text-modal-close class for consistent styling
  - IDs: submissionsBackBtn, submissionsPrintBtn,
    submissionsHistoryBtn

  JS state management:
  - submissionsState object tracks: month, year, monthName,
    viewMode ('month'|'history'), origin ('month'|'page')
  - Functions: openSubmissionsModal(), openFullHistoryModal(),
    viewFullHistory(), backToMonthView(), closeSubmissionsModal()

  Monthly summary table rows:
  - Clickable only when submission count > 0
  - Empty months are not interactive

  ----------------------------------------------------------------

  Monthly Submission Summary Collapse (Landlord)
  Status: IMPLEMENTED

  - Collapsed by default with "Show monthly summary" /
    "Hide monthly summary" toggle buttons

  ----------------------------------------------------------------

  LV-7: Tenant UI Overhaul
  Status: IMPLEMENTED

  Backend (app.py — tenant_page route):
  - Extracts lease_start_date / lease_end_date from current lease
  - Computes full monthly_summary with tenant-specific status logic:
    - reply_from_landlord (priority 1)
    - flagged (priority 2)
    - submitted (priority 3)
    - resolved (priority 4)
  - Passes monthly_summary to template

  Template (tenant_confirm.html):
  - Page <title> changed to "Tenant Interface"
  - Monthly summary table added as primary view (NOT collapsed)
    - Heading: "Your Monthly Submissions"
    - 3 columns matching landlord layout
    - Rows clickable only when count > 0
  - Submission form hidden by default
    - "+ Add new submission" link reveals form and scrolls to it
  - Past submissions hidden in storage container
    - Cards tagged with data-period-month / data-period-year
    - Used by modal via DOM movement (same pattern as landlord)

  Tenant modal (#tenantSubmissionsModal):
  - Same structure and behavior as landlord modal
  - tenantState object mirrors submissionsState
  - Functions: openTenantSubmissionsModal(),
    openTenantFullHistoryModal(), tenantViewFullHistory(),
    tenantBackToMonthView(), closeTenantSubmissionsModal()
  - Click-outside and Escape key close handlers
  - @media print CSS for tenant modal

  ----------------------------------------------------------------

  Full History Mode (Landlord + Tenant)
  Status: IMPLEMENTED

  Adds a read-only audit view of ALL submissions across all months,
  accessible from two entry points:

  1. From within a per-month modal:
     - "View full history" button switches to history mode
     - Back button shows "Back to [Month Year]"
     - origin tracked as 'month'

  2. From page level:
     - "View full submission history" link below summary table
     - Opens directly in history mode
     - Back button hidden (origin tracked as 'page')
     - Link wrapped in {% if payment_confirmations %} conditional

  History mode behavior:
  - CSS class 'history-view' added to modal body
  - Hides all form and details elements with display: none !important
  - Cards shown in chronological order (all months)
  - Strictly read-only — no ability to respond or review
  - Print button visible in history mode

  Implemented identically for both landlord and tenant UIs.

  ----------------------------------------------------------------

  Attention Badges (Landlord + Tenant)
  Status: IMPLEMENTED

  Landlord heading (index.html):
  - Blue pill badge on "Monthly Submission Summary" heading
  - Counts months with review_status of 'tenant_replied' or
    'pending'
  - Uses Jinja2 namespace pattern for counting across loops
  - Text: "N needs attention" / "N need attention"

  Tenant heading (tenant_confirm.html):
  - Amber pill badge on "Your Monthly Submissions" heading
  - Counts months with review_status of 'reply_from_landlord'
    or 'flagged'
  - Same namespace counting pattern
  - Same text format

  Badges hidden when count is 0.

  ----------------------------------------------------------------

  Key Technical Patterns Established (8 Feb)

  1. DOM Node Movement: Server-rendered submission cards are moved
     (not cloned) between a hidden storage container and modals
     using appendChild. This preserves form state, event handlers,
     and avoids duplication bugs.

  2. Modal State Objects: JS objects (submissionsState, tenantState)
     track current month, viewMode, and origin to manage button
     visibility and navigation behavior.

  3. History View CSS: A single CSS class ('history-view') on the
     modal body hides all interactive elements (form, details)
     with !important, making the view read-only without DOM changes.

  4. Defensive Cleanup: Modal close functions always move ALL cards
     back to storage, remove history-view class, and reset state —
     regardless of current view mode.

  5. Jinja2 Namespace Counting: {% set ns = namespace(count=0) %}
     pattern used to accumulate counts across for-loop iterations
     for attention badges.

  ----------------------------------------------------------------

                                                          
  ---                                                                                                                   
    ----------------------------------------------------------------
                                                                                                                        
    LV-7.1: Empty States & Helper Guidance                                                                              
    Status: IMPLEMENTED
    Date: 8 February 2026

    Presentational only. No backend or logic changes.

    Landlord UI (index.html):
    - Helper text below "Monthly Submission Summary" heading:
      "Click a month to review submissions or respond to tenant messages."
    - Empty state when all months have zero submissions:
      "No submissions yet. Tenant payment confirmations will appear
      here once submitted."
    - Month modal empty state (defensive):
      "No submissions were made for this month."
    - Full history modal empty state (defensive):
      "No submissions exist for this lease yet."

    Tenant UI (tenant_confirm.html):
    - Helper text below "Your Monthly Submissions" heading:
      "Click a month to view or respond to messages from your landlord."
    - Empty state when zero submissions:
      "You haven't submitted any payment confirmations yet.
      Use 'Add new submission' to get started."
    - Month modal empty state:
      "No submissions were made for this month."
    - Full history modal empty state:
      "No submissions exist for this lease yet."

    Technical notes:
    - Empty states in modals use .modal-empty-state CSS class
    - Cleanup runs in defensive section of each modal open function
    - Empty state elements are removed from storage on next open
    - Jinja2 namespace counting (ns_total) used for zero-submission
      detection in monthly summary tables
    - All 8 JS modal functions updated (4 landlord, 4 tenant):
      openSubmissionsModal, openFullHistoryModal, viewFullHistory,
      backToMonthView, and their tenant equivalents

    ----------------------------------------------------------------

    LV-7.2: Expected Monthly Payment Coverage
    Status: IN PROGRESS (Step 1 of 7 complete)
    Date: 8 February 2026

    Goal:
    Track whether tenants have submitted ALL required payment categories
    for a month, not just the number of submissions.

    Key concept:
    Each lease defines which payment categories are expected monthly
    (rent, maintenance, utilities). The system compares expected
    categories against submitted categories to determine coverage.

    Two INDEPENDENT signals per month:
    1. Coverage: X / Y expected categories submitted (NEW)
    2. Conversation status: flagged / replied / resolved (EXISTING)
    Neither replaces the other.

    Decisions (locked):
    - Categories are mandatory to choose; amounts are optional
    - Amounts are informational only (no verification or comparison)
    - Coverage is per CATEGORY, not per submission count
    - Use current lease version's expectations for all months
    - Only past months within lease period are evaluated
    - Existing leases default to rent-only expected
    - Reminders (future) will NOT use the existing event model;
      storage design deferred to Step 7

    ----------------------------------------------------------------

    LV-7.2 Step 1: Data Model Foundation
    Status: IMPLEMENTED
    Date: 8 February 2026

    Backend only. No UI changes. No behavioural changes.

    A. New field: expected_payments (inside current_values)
    Structure:
    [
      { type: "rent",        expected: true,  typical_amount: <number|null> },
      { type: "maintenance", expected: false, typical_amount: null },
      { type: "utilities",   expected: false, typical_amount: null }
    ]

    Rules:
    - type is limited to: rent, maintenance, utilities
    - expected is boolean (mandatory)
    - typical_amount is optional, informational only
    - If expected == false, typical_amount MUST be null
    - If expected == true, typical_amount may be null

    B. New field: needs_expected_payment_confirmation (top-level)
    - Boolean flag on the lease object (NOT inside current_values)
    - Tracks whether landlord has confirmed expected payments
      after a renewal

    Flag behaviour:
    - Existing leases (migration): false
    - New lease uploads: false
    - Renewal uploads: true
    - Renewals via "Renew" button: true
    - Any Edit Mode save: set to false

    C. Migration
    - _default_expected_payments(monthly_rent) helper added
    - _migrate_lease_add_expected_payments() — adds expected_payments
      to existing leases if missing, using monthly_rent for rent
      typical_amount
    - _migrate_lease_add_confirmation_flag() — adds
      needs_expected_payment_confirmation = false to existing leases

    D. Save/load/renewal paths updated
    - save_lease(): preserves expected_payments from existing lease
      (not editable via form yet), sets confirmation flag to false
    - Upload (new): default expected_payments, flag = false
    - Upload (renewal): copies expected_payments from original, flag = true
    - create_lease_renewal(): copies expected_payments from original,
      flag = true
    - All paths fall back to _default_expected_payments() if original
      lease lacks the field

    Files changed: app.py only
    No template changes. No tenant-facing changes. No coverage logic.

    ----------------------------------------------------------------

    LV-7.2 Implementation Plan (Remaining Steps)

    Step 2: Edit Mode UI — checkboxes for expected categories,
            optional amount fields, confirmation messaging for renewals
    Step 3: Coverage computation helper (backend)
    Step 4: Landlord monthly summary — X/Y column + missing badges
    Step 5: Tenant monthly summary — same pattern
    Step 6: Modal notices — list missing categories in per-month modals
    Step 7: Reminder system — targeted reminders for missing categories

    ---------------------------------------------------------------


-----------------------------------------------------------------
UPDATE - 7 FEB 2026
-----------------------------------------------------------------

                                                                                         
⏺ I now have a thorough understanding of the entire codebase. Let me complete the audit and write up the full design
  review.                                                                                                               
                                                            
⏺ ---                                                                                                                   
  Phase 1 Design Review: Tenant Rent & Charges Confirmation                                                             
                                                                                                                        
  ---                                                                                                                   
  STEP 1 — CODEBASE AUDIT                                                                                               
                                                                                                                        
  I have read the full codebase: app.py (1717 lines), templates/index.html (3998 lines), lease_data.json (live data),   
  PROJECT_CONTEXT.md, .gitignore, and requirements.txt.                                                                 
                                                                                                                        
  1.1 Is the current JSON lease model compatible?                                                                       

  Append-only payment confirmations — Mostly compatible, with one structural concern.

  The current model stores everything in a flat lease_data.json file with structure {"leases": [...]}. Each lease is a
  self-contained JSON object. Payment confirmations could be added as a new array inside each lease (e.g.
  lease["payment_confirmations"]), or as a separate top-level collection (e.g. data["payments"]). The JSON file format
  supports both approaches.

  However, there is a scaling concern: every load/save cycle reads and writes the entire lease_data.json file via
  _load_all_leases() → _save_lease_file(). The current file is ~170 lines with 2 leases. Adding monthly payment records
  with proof metadata will cause this file to grow significantly over time (12+ records per lease per year, each with
  sub-objects). This is manageable for a single-user MVP but worth noting.

  The atomic write pattern (write to .tmp → os.replace) is good and will continue to protect data integrity.

  Proof uploads — Compatible, with a namespace concern.

  Uploads currently go into a single flat uploads/ directory, named via secure_filename(). All lease PDFs live in this
  same folder. Payment proof screenshots would go to the same place unless we create a subdirectory structure. Currently
   there is no namespacing (no per-lease folders, no file-type separation). Two tenants uploading screenshot.png for
  different leases would collide.

  Future tenant access — Not currently supported, but not blocked.

  There is no authentication, no session management, no user concept. The app.secret_key = "dev-secret-key" is only used
   for Flask flash messages, not for security. All routes are public. There is nothing that would prevent adding
  token-based access later, but there is also nothing to build on. This is a clean slate.

  1.2 Which existing mechanisms can be safely reused?
  Mechanism: _load_all_leases() / _save_lease_file()
  Current Use: Load/save JSON with atomic writes
  Reusable For Phase 1?: Yes — can extend the data structure it reads/writes
  ────────────────────────────────────────
  Mechanism: uploads/ folder + secure_filename()
  Current Use: Lease PDF storage
  Reusable For Phase 1?: Yes — proof uploads can use same folder (with namespacing)
  ────────────────────────────────────────
  Mechanism: ALLOWED_EXTENSIONS check
  Current Use: PDF/image validation
  Reusable For Phase 1?: Yes — screenshots are already valid types (png, jpg, jpeg)
  ────────────────────────────────────────
  Mechanism: view_pdf/<filename> route
  Current Use: Serve PDFs for browser viewing
  Reusable For Phase 1?: Partially — only serves PDFs, would need extension for images
  ────────────────────────────────────────
  Mechanism: uuid.uuid4() for IDs
  Current Use: Lease and version IDs
  Reusable For Phase 1?: Yes — can generate payment confirmation IDs the same way
  ────────────────────────────────────────
  Mechanism: datetime.now().isoformat() timestamps
  Current Use: created_at, updated_at
  Reusable For Phase 1?: Yes — consistent timestamp format
  ────────────────────────────────────────
  Mechanism: calculate_rent_payment_status()
  Current Use: Rent due date urgency on dashboard
  Reusable For Phase 1?: Yes — this already computes "days until rent due", can be extended for "was rent confirmed this

    month?"
  ────────────────────────────────────────
  Mechanism: Flash message system
  Current Use: User feedback
  Reusable For Phase 1?: Yes
  ────────────────────────────────────────
  Mechanism: Delete confirmation pattern (type "DELETE")
  Current Use: Lease deletion safety
  Reusable For Phase 1?: Could inspire payment dispute/correction safety patterns
  ────────────────────────────────────────
  Mechanism: format_money / format_date Jinja filters
  Current Use: Display formatting
  Reusable For Phase 1?: Yes — directly reusable for payment amounts and dates
  ────────────────────────────────────────
  Mechanism: Version comparison logic (compare_lease_versions)
  Current Use: Shows what changed between renewals
  Reusable For Phase 1?: Not directly reusable, but the pattern (compute diffs server-side, render in template) is a
  good
     model
  1.3 Risks and Constraints

  Risks that could make Phase 1 fragile:

  1. Single-file JSON grows unbounded. Payment confirmations accumulate monthly. With proof file references, metadata,
  and optional charges (maintenance, utilities), the JSON file will grow much faster than leases alone. There is no
  archival or pagination mechanism.
  2. Single-template architecture. The entire app is one route (/) with conditional Jinja blocks (show_dashboard,
  edit_mode, view mode). Adding payment confirmation UI (tenant form, landlord review, payment history) to this same
  template could push it past maintainability. It's already ~4000 lines.
  3. No route protection. Every route is world-accessible. If we add tenant-facing confirmation pages, they share the
  exact same access as the landlord dashboard. There is currently no way to distinguish who is viewing what.
  4. Upload filename collisions. secure_filename("screenshot.png") produces the same filename regardless of which lease
  or which month. A second upload with the same name would overwrite the first. Lease PDFs are somewhat unique by
  filename convention, but screenshots will not be.
  5. In-memory uploads dict. There is a global uploads = {} used temporarily during the upload flow. It is cleared on
  deletion. This pattern is fragile for a feature that needs to reference proof files long-term — the proof file
  references must be in the persisted JSON, not in memory.
  6. app.secret_key = "dev-secret-key" is hardcoded. If we later use Flask sessions or token signing, this is insecure.
  For Phase 1 with token-based links, this would need to change.

  Risks that could block Phase 2:

  1. No user identity model. Phase 2 envisions landlord/tenant logins. If Phase 1 embeds payment data deep inside lease
  objects, migrating to a user-centric model later will require restructuring.
  2. No notification infrastructure. Phase 1 wants reminders and notifications. The current app has no background
  workers, no email sending, no external services. The only "notifications" are the dashboard urgency badges computed at
   page-load time. Real reminders (before rent due date, after missed confirmation) would need either a polling
  mechanism on the frontend or an external trigger, neither of which exists.
  3. JSON storage doesn't support concurrent writes. If Phase 2 has both landlord and tenant writing simultaneously
  (even from separate browsers), the current load-modify-save pattern could lose writes. This is not a Phase 1 blocker
  (single user), but the architecture needs awareness.

  ---
  STEP 2 — DATA MODEL STRATEGY

  Where should payment confirmations live?

  Option A: Inside the lease object (e.g. lease["payment_confirmations"])

  - Pros: Keeps all data for a lease together. Easy to load — one _load_all_leases() call gives you everything. Matches
  the existing pattern (lease is the unit of data). Simple to implement.
  - Cons: The lease JSON object becomes very large over time. Loading the dashboard (which loads all leases) now loads
  all payment history for every lease. No way to query "show me just December's payments" without loading everything.
  Harder to migrate to a separate user model later.

  Option B: Separate top-level collection (e.g. data["payment_confirmations"] alongside data["leases"])

  - Pros: Keeps lease objects clean. Payment data can grow independently. Easier to paginate or archive later. Cleaner
  separation of concerns. Easier to migrate to a database or separate file later.
  - Cons: Requires joining data (look up lease by ID to get context for a payment). Two things to keep in sync. Slightly
   more complex queries.

  Option C: Separate JSON file (e.g. payment_data.json)

  - Pros: Lease data file stays untouched (zero risk to existing functionality). Can grow independently. Could be loaded
   only when needed (not on every dashboard load). Cleanest separation.
  - Cons: Two files to manage. Need a second load/save function. Must ensure cross-file consistency (e.g. payment
  references a lease_id that actually exists).

  My assessment:

  Option C (separate file) is the safest for your situation. Here's why:

  - It completely protects lease_data.json from any Phase 1 bugs. If payment code has a bug, your lease data is
  untouched.
  - It matches the "one logical change at a time" development rule — you can build and test the payment system without
  touching lease save/load logic.
  - It naturally separates concerns for Phase 2 (payments are a different domain than lease terms).
  - The cost (a second load/save function) is small — you can reuse the same atomic write pattern.

  The payment file would reference leases by lease_id, which is stable and immutable.

  How should proof uploads be referenced?

  Proof files (screenshots, photos) should be:
  - Stored in a subdirectory of uploads, e.g. uploads/proofs/{lease_id}/{payment_id}_filename.ext
  - This prevents filename collisions across leases and months
  - Referenced in the payment confirmation record by relative path (e.g. "proof_files":
  ["proofs/abc123/def456_receipt.png"])
  - Append-only: once uploaded, a proof file is never modified or deleted (audit trail requirement)
  - The existing ALLOWED_EXTENSIONS check (pdf, png, jpg, jpeg) already covers common proof formats

  The view_pdf/<filename> route currently only serves PDFs. For image proofs, you would need a parallel route or a
  generalized file-serving route (with path traversal protection).

  How should disclaimers be enforced structurally?

  Disclaimers should not rely on UI text alone. They should be enforced at the data level:

  1. Every payment confirmation record should include a field like "verification_status": "unverified" — this is set at
  creation time and never changes in Phase 1. This makes it structurally impossible to confuse a declared payment with a
   verified one.
  2. The data model should distinguish amount_agreed (from lease) vs amount_declared (from tenant) vs amount_verified
  (future Phase 2). In Phase 1, amount_verified is always null. This forces the UI to always show "declared" rather than
   "paid" language.
  3. A disclaimer_acknowledged boolean or timestamp could record that the person submitting the confirmation saw the
  disclaimer before submitting. This creates an audit trail.

  This approach means even if someone forgets to add disclaimer text in a new UI, the data itself signals that nothing
  is verified.

  ---
  STEP 3 — ACCESS WITHOUT LOGINS

  Token-based tenant links: Feasibility

  Approach: Generate a unique, unguessable URL token per lease (e.g. /tenant/{token}) that gives the tenant limited
  access to submit payment confirmations for that specific lease.

  Feasibility: High. This is a well-established pattern (similar to shared Google Docs links or Doodle polls). Python's
  secrets.token_urlsafe(32) can generate cryptographically secure tokens.

  Key considerations:
  Aspect: Token generation
  Assessment: Easy. secrets.token_urlsafe(32) produces a 43-character URL-safe token. Store it alongside the lease.
  ────────────────────────────────────────
  Aspect: Token-to-lease mapping
  Assessment: Store in the payment data file or a small tenant_tokens.json. Maps token → lease_id + permissions +
  expiry.
  ────────────────────────────────────────
  Aspect: Brute-force resistance
  Assessment: A 32-byte token has 256 bits of entropy. Practically unguessable.
  ────────────────────────────────────────
  Aspect: Token revocation
  Assessment: Landlord can regenerate or delete the token. Simple boolean is_active flag.
  Time-bound vs lease-bound access

  - Lease-bound (token is valid as long as the lease is active): Simplest. Token becomes invalid when the lease expires
  or is deleted. Natural lifecycle.
  - Time-bound (token expires after N days): More secure, but requires the landlord to regenerate links periodically.
  Adds friction.
  - Recommended for Phase 1: Lease-bound. Validity tied to lease_end_date. No need for background expiry checks — just
  compare dates at access time.

  Read/write vs read-only access

  For Phase 1, the tenant link should allow:
  - Write: Submit payment confirmations and upload proofs for their specific lease only
  - Read: See their own payment history for that lease, see the agreed rent/due date
  - No access to: Other leases, landlord dashboard, lease editing, deletion, AI features

  This is a very narrow permission scope. The token simply unlocks a single-purpose page.

  What this does NOT solve

  - No tenant identity (two people with the link are indistinguishable)
  - No protection if the link is shared/leaked (anyone with the URL can submit)
  - No email verification of the tenant
  - These are all acceptable limitations for a Phase 1 "non-verified" system, and should be stated in the disclaimers

  ---
  STEP 4 — PROPOSED SAFE PHASE 1 PLAN

  Below is a conservative plan, broken into small steps. Each step is independently reviewable and deployable.

  Step 1: Create payment data file and load/save infrastructure

  - What: Create payment_data.json with structure {"confirmations": []}. Write _load_all_payments() and
  _save_payment_file() functions using the same atomic-write pattern as leases.
  - Files affected: app.py (new functions only, ~40 lines), new file payment_data.json
  - Type: Data / backend infrastructure
  - Must NOT touch: lease_data.json, any existing lease functions, any templates

  Step 2: Define the payment confirmation data model

  - What: Define the JSON schema for a single payment confirmation record. Fields: id, lease_id, confirmation_type
  (rent/maintenance/utility), period_month, period_year, amount_agreed, amount_declared, tds_deducted, date_paid,
  proof_files[], verification_status ("unverified"), disclaimer_acknowledged, submitted_at, submitted_via
  ("tenant_link"/"landlord_manual"), notes.
  - Files affected: PROJECT_CONTEXT.md (document the schema), potentially a comment block in app.py
  - Type: Documentation / data model decision
  - Must NOT touch: Any running code, any templates

  Step 3: Create proof upload subdirectory structure and route

  - What: Add uploads/proofs/ directory. Create a route to handle proof file uploads (POST) with proper filename
  namespacing ({lease_id}_{uuid}_{original_name}). Create a route to serve proof files (GET) with path-traversal
  protection.
  - Files affected: app.py (new routes, ~50 lines)
  - Type: Backend routing
  - Must NOT touch: Existing /upload route, existing view_pdf route, templates

  Step 4: Create tenant token generation and storage

  - What: Add a tenant_tokens section to payment_data.json (or a small separate file). Add a function to generate a
  token for a lease. Add a function to look up a lease by token (with expiry check against lease_end_date).
  - Files affected: app.py (new functions, ~30 lines), payment_data.json structure
  - Type: Backend infrastructure
  - Must NOT touch: Lease data, templates, existing routes

  Step 5: Create the tenant-facing confirmation page (new template)

  - What: A new template (e.g. templates/tenant_confirm.html) accessible via /tenant/{token}. Shows: lease nickname,
  agreed rent, due date, a form to submit payment confirmation with proof upload, and prominent disclaimers. Completely
  separate from index.html.
  - Files affected: New file templates/tenant_confirm.html, app.py (new route, ~40 lines)
  - Type: UI + routing
  - Must NOT touch: index.html, any existing routes

  Step 6: Create backend route to accept payment confirmations

  - What: POST route (e.g. /tenant/{token}/confirm) that validates the form, saves the confirmation to
  payment_data.json, and saves any uploaded proof files.
  - Files affected: app.py (new route, ~60 lines)
  - Type: Backend routing / data persistence
  - Must NOT touch: Lease save logic, existing routes

  Step 7: Add landlord payment history view

  - What: A section on the existing lease View Mode that shows payment confirmations for that lease. Shows: month,
  declared amount, TDS, proof file links, submission date, and a clear "UNVERIFIED — Landlord must independently check
  bank account" disclaimer. Read-only.
  - Files affected: templates/index.html (new section in view mode block), app.py (pass payment data to template in
  index route)
  - Type: UI + minor backend change
  - Must NOT touch: Edit mode, dashboard, AI logic, lease save logic

  Step 8: Add "Generate Tenant Link" button to landlord view

  - What: On the lease View Mode page, add a button that generates (or shows existing) tenant link. With a
  copy-to-clipboard action. Shows disclaimer that anyone with the link can submit confirmations.
  - Files affected: templates/index.html (new button in view mode), app.py (new route to generate token)
  - Type: UI + routing
  - Must NOT touch: Edit mode, dashboard, AI logic

  Step 9: Add basic reminder indicators to dashboard

  - What: Extend calculate_rent_payment_status() to also check whether a confirmation exists for the current month. Add
  a visual indicator on the dashboard: "Confirmed" / "Not yet confirmed" / "Overdue — no confirmation". This is computed
   at page-load time (no background jobs).
  - Files affected: app.py (extend existing function), templates/index.html (dashboard card section)
  - Type: Backend logic + UI
  - Must NOT touch: Lease data model, AI logic, edit mode

  Step 10: Add landlord-initiated reminder (in-app only)

  - What: A button on the lease view page: "Send Reminder". In Phase 1, this simply creates a flag/record in
  payment_data.json (e.g. "reminders": [...]). The tenant sees "Your landlord sent a reminder on [date]" when they visit
   their confirmation page. No email, no push notifications.
  - Files affected: app.py (new route), templates/index.html (button), templates/tenant_confirm.html (display reminder)
  - Type: Backend + UI
  - Must NOT touch: Lease data, AI logic

  ---
  What each step explicitly must NOT touch:
  ┌───────────────────────────┬───────────────────────────────────────────────────────────────────────────────────────┐
  │          Concern          │                                 Protected Throughout                                  │
  ├───────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤
  │ lease_data.json structure │ No fields added, no migration needed                                                  │
  ├───────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤
  │ Existing lease CRUD logic │ _load_all_leases, save_lease, reset_lease — untouched                                 │
  ├───────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤
  │ AI extraction flow        │ ai_prefill, ai_extract_lease_fields — untouched                                       │
  ├───────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤
  │ Edit mode UI              │ Entire edit mode Jinja block — untouched                                              │
  ├───────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤
  │ Dashboard lease cards     │ Existing card rendering — untouched (Step 9 only adds an indicator)                   │
  ├───────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤
  │ Existing upload flow      │ /upload route — untouched                                                             │
  ├───────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤
  │ app.secret_key            │ Left as-is for Phase 1 (token security comes from secrets module, not Flask sessions) │
  └───────────────────────────┴───────────────────────────────────────────────────────────────────────────────────────┘
  ---
  That completes the four-step design review. Want me to go deeper on any specific step, or do you have questions about
  any of the tradeoffs?

BUT NOTE
	•	“Append-only records”
	•	“Records, not payments”
	•	“Manual reminders only in Phase 1”
Ss

----------------------------------------------------------------
PAYMENT CONFIRMATION & TENANT ACCESS (PHASE 1 — AUTHORITATIVE)
----------------------------------------------------------------

The app uses separate data files for payments and tenant access.

payment_data.json
Stores payment confirmation records only.
	•	Append-only (no edits or deletes)
	•	Linked via lease_group_id
	•	Records are always marked verification_status = "unverified"
	•	Multiple submissions per month are allowed
	•	“Submitted” does NOT mean “verified”

Purpose:
Audit trail of tenant-declared payments with proof attachments.

⸻

tenant_access.json
Stores tenant access metadata only.
	•	Contains access tokens
	•	Tokens map to lease_group_id
	•	Tokens can be revoked or regenerated by the landlord
	•	Used to grant limited tenant access without logins

Purpose:
Access control is kept separate from transactional data.

⸻

Design Principles (Locked)
	•	Payment records must NEVER be mixed with access control data
	•	Tokens persist across renewals unless explicitly revoked
	•	If tenant changes:
	•	Landlord decides whether token continues or is replaced
	•	Schema defines future capability, not immediate UI scope

These rules must be respected in all future development.

------------------------------------------------------------
PHASE 1 — CONFIRMED DECISIONS & DEFERRED ITEMS
------------------------------------------------------------

CONFIRMED DECISIONS (AUTHORITATIVE)

1. Data separation
- Tenant payment confirmations and tenant access tokens are stored in
  separate JSON files:
  - payment_data.json
  - tenant_access.json
- These files are completely independent of lease_data.json.
- Lease data must never be modified by the payment system.

2. Token model
- Tenant access uses unguessable, token-based links.
- Tokens are bound to lease_group_id (not lease_id) and therefore
  survive renewals by default.
- Tokens have no separate id field in Phase 1.
- The token string itself is the identifier.

3. Tenant change handling
- On lease renewal, if tenant details change, the landlord will later
  be explicitly asked whether this is a new tenant.
- If the landlord confirms it is a new tenant, the existing token
  will be revoked and a new token generated.
- No automatic revocation logic exists in Phase 1.

4. Payment confirmations
- All payment confirmations are append-only.
- Records cannot be edited or deleted.
- Corrections are submitted as new records.
- Multiple submissions per month are allowed.
- Any submission for a given month counts as “submitted”.

5. Language & verification discipline
- “Submitted” and “Declared” are the only permitted concepts.
- Nothing is ever treated as verified in Phase 1.
- verification_status is always “unverified”.
- Landlords must independently verify payments via their own bank
  accounts.

6. Period determination
- Whether a payment applies to a given month is determined solely by:
  - period_month + period_year selected by the tenant.
- Submission date and payment date are informational only.

------------------------------------------------------------
DEFERRED (INTENTIONALLY NOT IMPLEMENTED IN PHASE 1)
------------------------------------------------------------

- Product renaming / branding cleanup (e.g. MapMyLease vs Easemylease)
- Tenant authentication or user accounts
- Editing or deleting payment confirmations
- Token expiration policies beyond manual revocation
- Aggregation or reconciliation of multiple submissions
- Automatic payment verification
- Notifications (email, SMS, push)
- Mobile app implementation

These items are deferred by design and must not be partially or
implicitly implemented without explicit scope approval.

----------------------------------------------------------------
PHASE 1 — IMPLEMENTATION STATUS
----------------------------------------------------------------

Step 1: Payment & Tenant Access Infrastructure
Status: IMPLEMENTED
Date: 7 February 2026

What was added:
- payment_data.json
  - Stores append-only tenant payment confirmations
- tenant_access.json
  - Stores tenant access tokens and access metadata
- Both files are gitignored (local user data only)

Backend helpers added to app.py (NOT called anywhere yet):
- _load_all_payments()
- _save_payment_file(data)
- _load_all_tenant_access()
- _save_tenant_access_file(data)

Additional notes:
- Schema documentation for both payment confirmations and tenant tokens
  has been added as comments in app.py
- All save operations use the same atomic write pattern as lease saving
- No routes were added
- No UI was added or modified
- No authentication or verification logic was added
- lease_data.json and all existing lease logic remain untouched

This step establishes infrastructure only.
No user-visible behaviour has changed.

-----------------------------------------------------------------------

  Step 2: Define and Lock Payment Confirmation Data Model
  Status: LOCKED & AUTHORITATIVE
  Date: 7 February 2026

  This step finalizes the data model for tenant payment confirmations
  and tenant access tokens. These schemas are authoritative and MUST
  NOT be modified, extended, or partially implemented without explicit
  scope approval.

  NO UI, routes, validation logic, or business logic implemented.

  A. Payment Confirmation Schema (payment_data.json["confirmations"])

  Each record:
  {
    "id":                       str (uuid4)
    "lease_group_id":           str (uuid4, links to lease group)
    "confirmation_type":        "rent" | "maintenance" | "utilities"
    "period_month":             int (1-12)
    "period_year":              int (YYYY)
    "amount_agreed":            number | null (rent only; null for others)
    "amount_declared":          number (required, positive)
    "tds_deducted":             number | null (null ≠ 0)
    "date_paid":                str (ISO date YYYY-MM-DD) | null
    "proof_files":              list of str (relative file paths)
    "verification_status":      "unverified" (ALWAYS in Phase 1)
    "disclaimer_acknowledged":  str (ISO timestamp, required)
    "submitted_at":             str (ISO timestamp, server-generated)
    "submitted_via":            "tenant_link" | "landlord_manual"
    "notes":                    str | null
  }

  Immutability rule:
  - The confirmations list is append-only
  - Every record is frozen at creation — no field is ever changed
    after writing, including proof_files
  - Corrections or missing proof: submit a NEW record

  Key rules:
  - verification_status is always "unverified" in Phase 1
  - Only "rent" uses amount_agreed (copied from lease at submission)
  - Maintenance and utilities are declaration-only
  - Multiple submissions per month are allowed
  - Period determined solely by (period_month, period_year)
  - "Submitted" or "declared" never means "verified"
  - tds_deducted: null = not provided; 0 = explicitly no TDS

  B. Tenant Token Schema (tenant_access.json["tenant_tokens"])

  Each record:
  {
    "token":                    str (secrets.token_urlsafe(32), ~43 chars)
    "lease_group_id":           str (uuid4, links to lease group)
    "is_active":                bool (mutable)
    "issued_at":                str (ISO timestamp)
    "revoked_at":               str (ISO timestamp) | null (write-once)
    "revoked_reason":           str | null (write-once)
    "last_used_at":             str (ISO timestamp) | null (mutable)
  }

  Rules:
  - token string IS the identifier (no separate id field)
  - Bound to lease_group_id (survives renewals)
  - At most ONE active token per lease_group_id at any time
  - Revoking a token NEVER deletes payment history
  - Token validity: is_active AND lease has unexpired current version
  - Only is_active and last_used_at are mutable after creation
  - revoked_at and revoked_reason are write-once (set at revocation)

  C. What changed from Step 1 schema comments:
  - disclaimer_acknowledged narrowed from "bool or ISO timestamp"
    to "str (ISO timestamp)" only — stronger audit trail
  - Immutability rule clarified: "append-only" applies to the
    collection, not to arrays within a record
  - All other fields unchanged from Step 1 documentation

----------------------------------------------------------------

  Step 3: Proof File Storage & Serving Infrastructure
  Status: IMPLEMENTED
  Date: 7 February 2026

  What was added:
  - PROOF_UPLOAD_FOLDER constant (uploads/proofs/)
    - Directory created at startup if missing
    - Already covered by existing uploads/ gitignore rule
  - PROOF_ALLOWED_EXTENSIONS set (png, jpg, jpeg, pdf)
    - Deliberately separate from ALLOWED_EXTENSIONS
    - Controls what can be SERVED, independent of upload rules
  - save_proof_file(lease_group_id, payment_id, file) helper
    - Validates file extension via existing allowed_file()
    - Creates uploads/proofs/{lease_group_id}/ if missing
    - Names files as {payment_id}_{secure_filename}
    - Never overwrites existing files (immutability rule)
    - Returns relative path for JSON storage
    - NOT called anywhere yet
  - /view_proof/<lease_group_id>/<filename> GET route
    - Serves proof files (images and PDFs)
    - Validates extension against PROOF_ALLOWED_EXTENSIONS
    - Path traversal protected by send_from_directory
    - No authentication or token checks (Phase 1)

  What was NOT changed:
  - No templates modified
  - No existing routes modified
  - No schema changes
  - No lease logic touched
  - No payment submission logic added

  This step establishes proof file infrastructure only.
  No user-visible behaviour has changed.

  ----------------------------------------------------------------                                                
                                                          
    Step 4: Tenant Access Token Infrastructure                                                                    
    Status: IMPLEMENTED                                                                                           
    Date: 7 February 2026

    What was added:
    - import secrets (for cryptographically secure token generation)
    - generate_tenant_token(lease_group_id)
      - Verifies lease_group_id exists in lease_data.json
      - Refuses if an active token already exists (does NOT auto-revoke)
      - Creates token using secrets.token_urlsafe(32)
      - Saves to tenant_access.json
    - validate_token(token)
      - Pure read-only function, no side effects
      - Token is valid if and only if is_active == true
      - Does NOT check lease expiry or load lease data
      - Returns structured result with lease_group_id on success
      - Returns failure reason (not_found / revoked / inactive) on failure
    - revoke_tenant_token(token, reason=None)
      - Sets is_active = false, writes revoked_at timestamp
      - revoked_reason is optional (may be null)
      - NEVER deletes or alters payment history
    - get_active_token_for_lease_group(lease_group_id)
      - Read-only helper for future UI
      - Returns active token record or None

    Schema comment updated:
    - Token validity rule changed from
      "is_active AND lease has unexpired current version" to
      "is_active == true (lease expiry does NOT affect validity in Phase 1)"

    Locked decisions:
    - last_used_at remains in schema but is NOT updated in Phase 1
    - validate_token() is strictly read-only (no disk writes)
    - Lease expiry does not affect token validity
    - Access control is explicitly landlord-controlled

    What was NOT changed:
    - No templates modified
    - No routes added
    - No lease_data.json modified
    - No payment_data.json modified
    - No schema changes (only comment clarification)
    - No UI added

    None of these functions are called anywhere yet.
    This step establishes token infrastructure only.
    No user-visible behaviour has changed.

  ----------------------------------------------------------------

-------

    Step 5: Tenant Submission Route (Backend + Template)
    Status: IMPLEMENTED
    Date: 7 February 2026

    What was added:
    - Jinja global: now() registered for template year dropdowns
    - GET /tenant/<token> route
      - Validates token via validate_token()
      - Loads current lease for context (read-only)
      - Shows error page for invalid/revoked/inactive tokens
      - Passes lease nickname and agreed rent to template
      - Still allows access when no current lease exists
    - POST /tenant/<token>/confirm route
      - Re-validates token on every submission
      - Server-side validation:
        - confirmation_type must be rent/maintenance/utilities
        - period_month 1-12
        - period_year 2020 to current year + 1
        - amount_declared > 0
        - tds_deducted >= 0 and <= amount_declared (if provided)
        - Disclaimer checkbox required
      - amount_agreed: server-set for rent (copied from lease), null otherwise
      - Single proof file per submission (proof_files list of 0 or 1)
      - Proof upload failure rejects entire submission
      - Appends record to payment_data.json (append-only)
      - verification_status always "unverified"
      - submitted_via always "tenant_link"
    - New template: templates/tenant_confirm.html
      - Completely separate from index.html
      - Three states: invalid token, form, success
      - Form preserves values on validation error
      - Prominent disclaimer with required acknowledgement
      - Success message reinforces "declaration only" language

    What was NOT changed:
    - No modifications to index.html
    - No modifications to existing routes
    - No lease_data.json writes
    - No schema changes
    - No authentication added
    - No dashboard changes

----------------------------------------------------------------
                                                                                                                  
    Step 6: Backend Route to Accept Payment Confirmations  
    Status: MERGED INTO STEP 5
    Date: 7 February 2026

    The POST /tenant/<token>/confirm route was implemented as part
    of Step 5. This step has no separate deliverable.

    The original plan (Step 6) envisioned this as a separate step,
    but in practice the submission route was built alongside the
    tenant confirmation page and template in Step 5.

    No additional code was written for Step 6.

    ----------------------------------------------------------------

    Step 7: Tenant Access Token Management (Landlord UI)
    Status: IMPLEMENTED
    Date: 7 February 2026

    What was added:

    Backend (app.py):
    - get_all_tokens_for_lease_group(lease_group_id) helper
      - Returns ALL tokens (active + revoked) for a lease group
      - Sorted by issued_at DESC (newest first)
      - Read-only
    - POST /lease/<lease_group_id>/generate-token route
      - Calls existing generate_tenant_token()
      - Fails if active token already exists (no auto-revoke)
      - Redirects back to lease view with flash message
    - POST /lease/<lease_group_id>/revoke-token route
      - Calls existing revoke_tenant_token()
      - Accepts optional revoke_reason from form
      - Redirects back to lease view with flash message
    - Index route now passes tenant_tokens and active_tenant_token
      to template when viewing a lease (view mode only)

    Template (index.html):
    - "Tenant Access" section added to lease view mode
      - Placed after the view action buttons, before version history
      - Three states handled:
        1. No token exists:
           - Message: "No tenant access link has been generated yet."
           - "Generate Tenant Link" button
        2. Active token:
           - Green "Active" badge with issued date
           - Masked token display (****abcd) with Reveal/Hide toggle
           - Full tenant URL in copyable input field
           - "Copy link" button
           - Warning: "Anyone with this link can submit payment
             confirmations for this lease."
           - Collapsible "Revoke Tenant Access" section with optional
             reason field
        3. Revoked token(s):
           - Shown in a collapsible "Previous access links" section
           - Visually muted (opacity)
           - Displays: issued date, revoked date, revoked reason

    Decisions locked:
    - Tokens are landlord-controlled (no auto-revocation)
    - At most ONE active token per lease_group_id
    - Revoked tokens are never deleted (audit trail)
    - Token records shown muted, not hidden

    What was NOT changed:
    - No schema changes
    - No payment_data.json access
    - No tenant-facing routes or template modified
    - No lease data modified
    - No authentication added

    ----------------------------------------------------------------

    Step 8: Landlord Payment Audit View (Read-Only)
    Status: IMPLEMENTED
    Date: 7 February 2026

    What was added:

    Backend (app.py):
    - get_payments_for_lease_group(lease_group_id) helper
      - Loads payment_data.json via _load_all_payments()
      - Filters confirmations by lease_group_id
      - Sorted by submitted_at DESC (newest first)
      - Strictly read-only — never modifies data
    - Index route now passes payment_confirmations to template
      when viewing a lease (view mode only)

    Template (index.html):
    - "Payment Submissions (Unverified)" section added to lease view
      - Placed after the Tenant Access section
      - Prominent disclaimer: "These are tenant-declared submissions.
        The app does not verify payments. Landlords must independently
        confirm receipts via bank records."

    Per-record display:
    - Confirmation type (Rent / Maintenance / Utilities)
    - Period (Month + Year)
    - Amount paid (from amount_declared field)
    - Agreed rent (only for type == rent, if amount_agreed exists)
    - TDS deducted (only if provided; null vs 0 distinguished)
    - Date paid (if provided)
    - Submitted at (timestamp)
    - Submitted via (tenant_link / landlord_manual)
    - Notes (if provided)
    - Proof file links (using existing /view_proof route)
    - Grey "Unverified" badge on every record

    Empty state:
    - "No payment submissions have been recorded yet."

    Audit readability enhancements (presentational only):
    - Month grouping dividers: muted small-caps divider inserted
      when (period_month, period_year) changes between records
      (e.g. "— February 2026 —")
    - Duplicate submission indicator: amber badge reading
      "Multiple submissions this period" shown on each record
      where more than one submission exists for the same
      (confirmation_type, period_month, period_year)

    Rules enforced:
    - No verification or approval controls
    - No status computation (paid / unpaid / overdue)
    - No aggregation or totals
    - No deduplication — all records shown individually
    - No editing or deleting submissions
    - Multiple submissions per month all displayed

    What was NOT changed:
    - No schema changes
    - No writes to payment_data.json
    - No tenant routes or template modified
    - No new validation or business logic
    - No existing routes modified

    ----------------------------------------------------------------

    UI Copy Change (Non-Step, Presentational Only)
    Status: APPLIED
    Date: 7 February 2026

    File: templates/tenant_confirm.html

    - Field label changed from "Amount Declared (₹)" to "Amount Paid (₹)"
    - Helper text added: "The amount you actually paid (before any
      TDS deduction)"
    - The form field name remains name="amount_declared" (unchanged)
    - No backend, schema, or validation changes

    ----------------------------------------------------------------                                              
                                                                                                                  
    Step 9: Landlord Dashboard Summary (Read-Only)                                                                
    Status: IMPLEMENTED                                                                                           
    Date: 7 February 2026

    What was added:

    Backend (app.py):
    - Monthly submission summary computed inline in the index route
      - No new helper functions added
      - Uses existing get_payments_for_lease_group() data
      - Groups by (period_year, period_month), all confirmation types
        counted together
      - Month range:
        - Start: lease start date month (priority 1)
          OR earliest submission period (fallback)
        - End: current month
      - Each entry: { year, month, month_name, count }
      - Passed to template as monthly_summary (list)
      - Read-only — no data writes

    Template (index.html):
    - "Monthly Submission Summary" table added to lease view
      - Placed above the Payment Submissions (Unverified) section
      - Informational disclaimer: "This summary reflects whether
        the tenant submitted any declarations for a given month.
        It does not verify payment or completeness."
      - Compact table with columns: Month, Status, Submissions
      - Status badges:
        - "Submitted" (muted green) — at least 1 record exists
        - "Not submitted" (neutral grey) — no records
      - Submission count links to #payment-submissions anchor
      - id="payment-submissions" added to Payment Submissions section
      - Hidden entirely if no monthly_summary data exists
        (no lease start date AND no submissions)

    Rules enforced:
    - No verification or correctness logic
    - No amount comparison or totals
    - No "paid" / "unpaid" / "late" language
    - No deduplication — all submissions counted
    - All confirmation types (rent, maintenance, utilities)
      counted together per month
    - tenant_link and landlord_manual treated equally

    What was NOT changed:
    - No schema changes
    - No data writes
    - No new helper functions
    - No tenant routes or template modified
    - No existing routes modified
    - No verification logic added

      ----------------------------------------------------------------

      Step 10: Landlord Review & Internal Notes
      Status: IMPLEMENTED
      Date: 7 February 2026

      What was added:

      New data file: landlord_review_data.json
      - Stores landlord review/note records only
      - Append-only (no edits or deletes)
      - Linked via payment_id and lease_group_id
      - NEVER visible to tenants
      - Added to .gitignore

      Structure: {"reviews": [...]}
      Each record:
      {
        "id":              str (uuid4)
        "payment_id":      str (references payment_data.json)
        "lease_group_id":  str (uuid4)
        "reviewed_at":     str (ISO timestamp)
        "review_type":     "acknowledged" | "flagged" | "noted"
        "internal_note":   str | null
      }

      Backend (app.py):
      - _load_all_landlord_reviews()
      - _save_landlord_review_file(data)
      - get_reviews_for_lease_group(lease_group_id)
        - Primary loader — returns all reviews for a lease group
        - Used to build per-payment dicts in the index route
      - get_reviews_for_payment(payment_id)
        - Convenience function for single-payment lookups
      - POST /lease/<lease_group_id>/payment/<payment_id>/review
        - Validates payment_id exists and belongs to lease_group_id
        - Accepts review_type (required) and internal_note (optional)
        - Appends review record — never modifies payment data
        - Flashes feedback, redirects to lease view
      - Index route (view mode) now loads reviews and passes:
        - payment_reviews: {payment_id: [reviews, newest first]}
        - latest_payment_review: {payment_id: most_recent_review}

      Template (index.html):
      - "Landlord review" block added inside each payment card
        - Shows latest review badge + note + timestamp
        - Badge colours:
          - Acknowledged: muted green (#d1fae5)
          - Flagged: amber (#fef3c7)
          - Noted: blue (#dbeafe)
        - Collapsible history if multiple reviews exist
      - "Add review / note" form (collapsed by default)
        - Dropdown: Acknowledged / Flagged / Noted
        - Optional internal note textarea
        - Helper text: "Once a note is saved, it can't be changed
          or removed. If you need to add more context later, just
          add another note — the most recent one will appear first."

      Rules enforced:
      - Reviews are append-only — no edits, no deletes
      - Reviews are landlord-only — never shown to tenants
      - No "verified" or "approved" language used
      - Multiple reviews per payment allowed (latest shown prominently)
      - payment_data.json is never modified by review logic

      What was NOT changed:
      - No schema changes to payment_data.json
      - No tenant_access.json changes
      - No lease_data.json changes
      - No tenant-facing routes or template modified
      - No dashboard changes
      - No authentication added

      ----------------------------------------------------------------

      Step 5 (Revision): Tenant Confirmation Form — Option B
      Status: IMPLEMENTED
      Date: 7 February 2026

      What changed:

      The tenant confirmation form was revised from a single-type
      submission (one dropdown) to a multi-type submission (three
      checkbox sections). This is a UI + route-handling change only.

      Template (tenant_confirm.html):
      - Single "Payment Type" dropdown REMOVED
      - Three independent checkbox sections added:
        - Rent (with TDS field, rent-only)
        - Maintenance
        - Utilities
      - Each section has its own:
        - Amount paid (required if section is checked)
        - Date paid (optional)
        - Proof upload (optional, per-section)
      - Month and Year are shared across all sections
      - Notes field is shared across all sections
      - Disclaimer is acknowledged once per submission
      - Section visibility toggled by checkbox (small JS helper)

      Microcopy added:
      - Near checkboxes: "Select all that apply. Each selected item
        will be recorded separately."
      - Near proof uploads: "Upload proof related to this payment
        (optional)."
      - Near disclaimer: "If you forget something or need to add
        more details later, you can submit another confirmation.
        Previous entries cannot be changed."

      Backend (app.py — POST /tenant/<token>/confirm):
      - Determines which sections are selected
      - Validates each selected section independently
      - If ANY section fails validation → entire submission rejected
      - No partial saves — all records saved in a single write
      - Each selected section produces its own:
        - payment_id (uuid4)
        - Payment confirmation record (locked schema)
        - Proof file (if uploaded)
      - amount_agreed set only for rent (from lease)
      - TDS processed only for rent
      - "Amount paid" used consistently in validation messages

      Data model: UNCHANGED
      - Still one payment record per confirmation type
      - Still append-only, immutable after creation
      - No new fields, no schema changes

      What was NOT changed:
      - No payment_data.json structure changes
      - No landlord UI changes
      - No dashboard changes
      - No verification or approval logic
      - No tenant_access.json changes
      - No lease_data.json changes

      ----------------------------------------------------------------

                                                               
  ---                                                                                                             
        ----------------------------------------------------------------                                          
                                                                                                                  
        Tenant-Visible Flagged Reviews                                                                            
        Status: IMPLEMENTED → SUPERSEDED BY PHASE 2                                                               
        Date: 7 February 2026

        What changed:

        Flagged reviews (from Step 10) were made visible to tenants.
        Acknowledged and Noted reviews remain landlord-internal only.

        Backend (app.py):
        - Flagging now requires a message (internal_note is mandatory
          when review_type == "flagged")
        - Tenant page route loads reviews and builds a flagged_payments
          dict — only the latest review per payment is checked, and
          only if it is "flagged"
        - A later non-flagged review (acknowledged/noted) clears the
          flag from the tenant's view

        Landlord UI (index.html):
        - "Add review / note" renamed to "Review this submission"
        - Per-type explanations added below dropdown:
          - Acknowledged — for your records only
          - Noted — private internal note
          - Flagged — shown to the tenant (comment required)
        - Dynamic warning when "Flagged" is selected:
          "This message will be shown to the tenant."
        - toggleFlagWarning() JS function added

        Tenant UI (tenant_confirm.html):
        - "Your past submissions" section added showing all previous
          payment confirmations for this lease
        - Each card shows: type, month/year, amount paid, date
        - "Needs attention" amber badge shown when latest review is
          flagged
        - Landlord's flag message displayed below the payment card
        - Helper text: "You can submit another confirmation or upload
          additional proof. Previous submissions cannot be changed."

        Rules enforced:
        - Only "flagged" reviews are tenant-visible
        - Acknowledged and Noted are never shown to tenants
        - A non-flagged review after a flag clears the tenant-visible
          badge
        - Flagging requires a message (enforced server-side)
        - payment_data.json is never modified

        Note: This change is now superseded by Phase 2, which replaced
        the static flag display with full conversation threads.

        ----------------------------------------------------------------

        Phase 2: Flagged Payment Conversations (Landlord ↔ Tenant)
        Status: IMPLEMENTED
        Date: 7 February 2026

        What changed:

        The landlord review system (Step 10) was extended into a
        structured, append-only conversation system. Landlords can
        flag a payment with a message, tenants can reply, landlords
        can reply back or close the conversation. All events are
        stored in landlord_review_data.json.

        Schema changes (landlord_review_data.json):

        The record schema was extended from Step 10. Old records are
        normalized on read via _normalize_event() — no data migration
        required.

        Field renames (old → new):
        - reviewed_at → created_at
        - review_type → event_type
        - internal_note → message

        New fields:
        - actor: "landlord" | "tenant"
        - attachments: list of str (relative file paths)

        Event types: "acknowledged" | "flagged" | "noted" | "response"

        Current record schema:
        {
          "id":              str (uuid4)
          "payment_id":      str (references payment_data.json)
          "lease_group_id":  str (uuid4)
          "created_at":      str (ISO timestamp)
          "event_type":      "acknowledged" | "flagged" | "noted" | "response"
          "actor":           "landlord" | "tenant"
          "message":         str | null
          "attachments":     list of str (relative file paths)
        }

        Backend (app.py):

        Helpers:
        - _normalize_event(record)
          - Maps old field names to new on read
          - Adds defaults: actor = "landlord", attachments = []
          - Passes new-format records through unchanged
        - get_events_for_lease_group(lease_group_id)
          - Returns all normalized events, newest first
          - Replaces get_reviews_for_lease_group()
        - get_events_for_payment(payment_id)
          - Returns all normalized events for one payment
          - Replaces get_reviews_for_payment()
        - get_conversation_state(events)
          - Computes conversation state from event list
          - Finds the latest "flagged" event
          - If no flag: {"open": False, "thread": []}
          - If flag exists: checks if any subsequent event is
            "acknowledged" or "noted" (which closes the conversation)
          - Returns {"open": bool, "thread": [events from flag onward]}
          - State is computed, never stored

        Routes:
        - POST /lease/<gid>/payment/<pid>/review (updated)
          - Now accepts 4 event types: acknowledged, flagged, noted,
            response
          - Writes new schema (created_at, event_type, actor, message,
            attachments)
          - For "response": validates conversation is open
          - For "flagged": message required
          - Supports optional file upload (attachment field)
          - Form field names unchanged: review_type, internal_note
            (backend maps to new schema)
        - POST /tenant/<token>/payment/<pid>/response (new)
          - Token-authenticated tenant reply route
          - Validates token, payment ownership, conversation is open
          - Message required, optional file attachment
          - Writes event with actor = "tenant"
          - Redirects to tenant page

        Data loading:
        - Index route (view mode) now passes:
          - payment_events: {payment_id: [events, oldest first]}
          - payment_conversation: {payment_id: conversation_state}
        - Tenant page route passes the same two dicts
        - Old variables removed: payment_reviews, latest_payment_review,
          flagged_payments

        Landlord UI (index.html):

        The flat review display and single review form were replaced
        with a conversation-aware block per payment card:

        1. Event timeline (when events exist):
           - All events shown chronologically, oldest first
           - Each event: actor badge (Landlord/Tenant), type badge
             (Acknowledged/Flagged/Noted/Reply), timestamp, message,
             attachment links
           - Acknowledged/Noted events shown with muted opacity (0.75)

        2. When conversation is open (convo.open):
           - Reply form: textarea + optional attachment + "Send reply"
           - Close actions:
             - "Acknowledge & close" single-click button
             - "Note & close..." expandable with optional note

        3. When no conversation is open:
           - Standard review form (collapsed by default):
             - Dropdown: Acknowledged / Flagged / Noted
             - Note textarea
             - Optional file attachment (new)
             - Flag warning preserved

        Tenant UI (tenant_confirm.html):

        The static "Needs attention" badge and flag message were
        replaced with a conversation thread per payment card:

        1. Conversation thread (when convo.thread exists):
           - Shows only tenant-visible events: flagged + response
           - Acknowledged/Noted events are never shown to tenants
           - Each event: "Landlord" or "You" label, date, message,
             attachment links
           - Landlord messages: amber background
           - Tenant messages: blue background

        2. When conversation is open:
           - Reply form: textarea + optional attachment + "Send reply"
           - Helper text: "Your reply will be saved and shared with
             your landlord. Previous entries cannot be changed."

        3. When conversation is closed:
           - Thread shown read-only
           - Green indicator: "This issue has been resolved."

        Conversation lifecycle:
        1. Landlord flags a payment (event_type: "flagged") → opens
        2. Tenant sees thread + reply form
        3. Either party can send responses (event_type: "response")
        4. Landlord closes by submitting "acknowledged" or "noted"
        5. Tenant sees "This issue has been resolved." — no reply form

        Attachments:
        - Reuses save_proof_file(lease_group_id, event_id, file)
        - Files go to uploads/proofs/{lease_group_id}/
        - Served via existing /view_proof route
        - Single file per reply

        Data model: EXTENDED (backward compatible)
        - landlord_review_data.json structure unchanged: {"reviews": []}
        - Old records normalized on read — no migration needed
        - New records use extended schema exclusively
        - payment_data.json: NEVER modified
        - tenant_access.json: UNCHANGED
        - lease_data.json: UNCHANGED

        What was NOT changed:
        - No new data files created
        - No payment record schema changes
        - No authentication changes beyond existing token model
        - No dashboard changes
        - No AI logic changes
        - No edit mode changes

        ----------------------------------------------------------------

----------------------------------------------------------------
UPDATED - 6 FEBRUARY 2026
-----------------------------------------------------------------

Major Changes & Fixes Implemented

1. AI Autofill Flow (Stabilised & Clarified)
	•	AI autofill can only be run once per lease
	•	After AI is applied:
	•	The AI button is disabled
	•	A “Return to AI Preview” button is shown instead
	•	Returning to preview does not re-run AI and does not incur extra AI cost

⸻

2. AI Preview Behaviour (Correct & Persistent)
	•	Preview correctly handles:
	•	AI-filled fields
	•	User-edited fields
	•	Fields AI did not find
	•	When reopening preview:
	•	User-edited values remain intact
	•	AI values are shown only as reference (never overwrite user input)
	•	If a user:
	•	Accepts AI → marked as AI-filled
	•	Edits AI value → marked as user-edited
	•	Reverts back to AI value → explicitly shown as “reverted to AI suggestion”

⸻

3. Inline Field Explanations (Post-Apply)
After applying AI suggestions:
	•	Each field shows a clear inline explanation:
	•	“Suggested by AI”
	•	“AI suggested ‘X’, changed by you”
	•	“Entered by you”
	•	“AI did not find a value — ”
	•	“You reverted to the AI-suggested value (previously ‘Y’)”
	•	These explanations help users understand what AI did vs what they changed

⸻

4. Special Handling: Lease Nickname
	•	AI can suggest a nickname
	•	User can edit it
	•	Nickname:
	•	Never shows “AI did not find a value”
	•	Never shows explanation text under the field
	•	Always respects the user’s final value
	•	In preview and return-to-preview:
	•	The user’s value is shown
	•	AI value is only shown as reference (never restored automatically)

⸻

5. Lease Deletion (Safety + Correctness)
	•	Dashboard delete now deletes the entire lease group (including renewals)
	•	User is clearly warned:
	•	That all versions will be deleted
	•	That individual versions should be deleted from inside the lease
	•	Deletion confirmation:
	•	Requires typing DELETE
	•	Is case-insensitive
	•	Works with keyboard Enter
	•	Backend now supports explicit group deletion
	•	All associated uploaded files are deleted correctly

⸻

6. Lease “Added Date”
	•	Added date is now shown:
	•	On the dashboard card
	•	Inside the lease view/edit page
	•	Uses a reusable format_date Jinja filter
	•	Displays human-readable dates (e.g. “5 Feb 2026”)

⸻

7. Loading UX Improvements
	•	Global loading overlay no longer dims the entire page
	•	Spinner and message are wrapped in a centered loading card
	•	Only the card is opaque; background remains visible but non-intrusive
	•	Prevents visual overlap and improves perceived responsiveness

⸻

Explicit Non-Changes (Important)
	•	❌ App name has NOT been renamed
	•	❌ No branding updates applied
	•	❌ No database schema changes
	•	❌ No backend AI prompt changes
	•	❌ No refactors beyond targeted fixes

----------------------------------------------------------------
UPDATED - 5 February 2026
----------------------------------------------------------------

RECENTLY IMPLEMENTED FIXES & POLISH (AUTHORITATIVE)

Implementation date: 5 February 2026

The following fixes and UX improvements were completed and verified on the above date.
They are considered stable, intentional behavior and should be treated as baseline functionality going forward.

⸻

A. Monetary Amount Formatting (Display Consistency)

Implemented: 5 February 2026

All monetary amounts shown to the user are now formatted with thousands separators for readability
(e.g. ₹185,000 instead of ₹185000).

This applies consistently across:
	•	Dashboard lease cards (monthly rent)
	•	View Mode financials (monthly rent, security deposit)
	•	Lease version comparison (old → new values)
	•	Edit Mode unified change list (“Previous values replaced”)

Rules:
	•	Stored values remain raw numbers (no formatting in persisted data)
	•	Formatting is display-only
	•	Non-monetary values (dates, names, text) are never affected
	•	Missing values continue to display as —

⸻

B. Renewal Creation Consistency (Data Integrity)

Implemented: 5 February 2026

All renewal leases are now created with fully initialized nested structures, regardless of how the renewal is created.

Specifically, every renewal includes:
	•	lock_in_period.duration_months
	•	renewal_terms.rent_escalation_percent

These fields:
	•	Always exist at creation time
	•	Default to null
	•	No longer rely on migration logic to appear later

This ensures:
	•	Consistent data shape across all renewal leases
	•	No divergence between different renewal creation flows
	•	Safer version comparison and UI rendering

⸻

C. Legacy Lease Handling — Missing Document UX

Implemented: 5 February 2026

Some very early (pre-migration) leases may not have their original PDF stored and therefore cannot run AI Autofill.

This scenario is now handled explicitly and clearly.

Backend behavior
	•	Detects when:
	•	No extracted text exists and
	•	No original document file exists on disk
	•	Returns a specific error code indicating a missing document (not a generic failure)

Frontend behavior
	•	Suppresses the generic red “AI extraction failed” error
	•	Displays an informational modal instead

User-facing messaging
	•	Clearly explains why AI cannot run
	•	Reassures the user that nothing is broken
	•	Guides the user to re-upload the lease document
	•	Uses calm, informational language (not danger/error styling)

Scope:
	•	This is a legacy-only scenario
	•	All newly uploaded leases automatically store both PDF and extracted text
	•	New users should never encounter this issue under normal usage

----------------------------------------------------------------
CORE CONCEPTS & DATA MODEL (AUTHORITATIVE)
----------------------------------------------------------------

Each lease is stored as a JSON object using a NESTED STRUCTURE.

TOP-LEVEL LEASE OBJECT
- id (uuid)
- lease_group_id (shared across renewals of the same lease)
- version (integer, increasing with each renewal)
- is_current (boolean)
- created_at (ISO timestamp)
- updated_at (ISO timestamp)

SOURCE DOCUMENT (persisted permanently)
lease["source_document"] = {
    filename: string | null
    mimetype: string | null
    extracted_text: string | null   # FULL OCR / PDF text
    extracted_at: ISO timestamp | null
}

CURRENT VALUES (what the app actually uses)
lease["current_values"] = {
    lease_nickname
    lessor_name
    lessee_name
    lease_start_date
    lease_end_date
    monthly_rent
    security_deposit
    rent_due_day

    lock_in_period: {
        duration_months: number | null
    }

    renewal_terms: {
        rent_escalation_percent: number | null
    }
}

AI EXTRACTION (audit trail — NEVER overwrites automatically)
lease["ai_extraction"] = {
    ran_at: ISO timestamp
    fields: {
        field_name: {
            value: extracted_value
            page: page_number | null
            evidence: quoted_text | null
        }
    }
}

Key principles:
- current_values = what is legally in force
- ai_extraction = suggestions + evidence only
- source_document = immutable reference text
- AI never applies business logic (no calculations, no rent changes)

----------------------------------------------------------------
LEASE VERSIONING / RENEWALS
----------------------------------------------------------------

- Renewals ALWAYS create a NEW lease record
- All versions share the same lease_group_id
- Only one version has is_current = true
- Older versions are immutable historical records
- If the current version is deleted, the previous version becomes current

Each renewal:
- Copies current_values from the previous version
- Uses a NEW uploaded document (new source_document)
- May change ANY field (dates, rent, parties, lock-in, escalation, etc.)

IMPORTANT:
A renewal is treated as a **fresh contract**, not a delta.
All changes must be explicit and inspectable.

----------------------------------------------------------------
LEASE VERSION COMPARISON (NEW)
----------------------------------------------------------------

For renewal leases (version > 1):

- The backend compares current_values of the current version
  against the immediately previous version
- Differences are computed server-side (deterministic, auditable)

Each change is classified as:
- added
- removed
- changed

Compared fields include:
- Start / End dates
- Monthly rent
- Security deposit
- Rent due day
- Tenant name
- Lock-in period (months)
- Rent escalation (%)

These version-to-version differences are exposed to the UI.

----------------------------------------------------------------
UPLOAD & EXTRACTION FLOW
----------------------------------------------------------------

1. User uploads PDF / image
2. App extracts text:
   - Embedded text if available
   - OCR fallback if scanned
3. Extracted text is saved into:
   lease.source_document.extracted_text
4. Lease record is immediately created
5. User is redirected to Edit Mode for that lease

NO critical data is stored only in memory.

----------------------------------------------------------------
EDIT MODE
----------------------------------------------------------------

Edit Mode shows:
- Editable form bound to current_values
- Scrollable, read-only Extracted Text panel (full document text)
- AI Autofill button
- Unified "Previous values replaced" section (see below)

AI Autofill:
- Reads from lease.source_document.extracted_text
- Saves results to lease.ai_extraction
- Does NOT overwrite current_values automatically
- User explicitly applies AI suggestions

AI may suggest values even if:
- Field was previously manually edited
- Field existed in a prior lease version

----------------------------------------------------------------
UNIFIED CHANGE TRACKING (NEW)
----------------------------------------------------------------

There is ONE unified section in Edit Mode:

"Previous values replaced"

This list includes:
1. Changes that already existed when the renewal was created
   (version-to-version differences)
2. Changes made by AI autofill during the current edit session

Each entry is tagged with its source:
- "Changed from previous version"
- "Updated by AI"

Rules:
- If AI updates a field already changed in the renewal,
  the entry is updated (not duplicated)
- Original old values from the previous version are preserved
- This section is initialized on page load for renewals
- AI changes are appended dynamically

This ensures:
- Full transparency
- No hidden overwrites
- Clear audit trail

----------------------------------------------------------------
VIEW MODE
----------------------------------------------------------------

View Mode shows:
- Final saved lease terms
- Metadata
- Optional change history for renewals

For renewal leases:
- A button: "View changes from previous version (N)"
- Clicking toggles visibility of the change list
- Changes are hidden by default to reduce clutter
- No recomputation occurs in View Mode

----------------------------------------------------------------
DASHBOARD
----------------------------------------------------------------

- Landing page shows a dashboard (not a single lease)
- Leases are grouped by landlord (lessor_name)
- Each group shows cards for leases
- Visual urgency indicators based on:
  - Lease expiry
  - Rent payment status
- A global alert/ticker summarizes urgent issues
  across all landlords at page load

----------------------------------------------------------------
DELETION RULES (SAFETY)
----------------------------------------------------------------

Any destructive action requires explicit confirmation:
- Deleting a lease
- Deleting a lease version
- Deleting a lease group

Deletion confirmations must:
- Require re-typing the lease nickname
- Clearly explain consequences

----------------------------------------------------------------
MIGRATION & BACKWARD COMPATIBILITY
----------------------------------------------------------------

- Existing flat leases are auto-migrated on load
- Migration moves flat fields into current_values
- Nested structures (lock_in_period, renewal_terms)
  default safely if missing
- source_document is created even if extracted_text is missing
- No data is silently dropped

Templates and backend must always read:
    lease.current_values (preferred)
    fallback to flat structure ONLY for legacy migrated data

----------------------------------------------------------------
TECH STACK
----------------------------------------------------------------

- Python (Flask)
- Jinja2 templates
- JSON file storage (single-user)
- OCR: Tesseract
- PDF parsing + OCR fallback
- AI: Claude (Anthropic API)

----------------------------------------------------------------
OPERATING RULES FOR CLAUDE (CRITICAL)
----------------------------------------------------------------

From this point forward:
- NEVER apply code changes without explicit approval
- ALWAYS show BEFORE / AFTER diffs
- ALWAYS explain in plain English
- Treat this as a production codebase
- One logical change per step
- If uncertain, ASK before acting

----------------------------------------------------------------
VERSION CONTROL & WORKFLOW (GitHub + CLI)
----------------------------------------------------------------

Repository:
https://github.com/sbhasin2019/Lease-Agent-App

- Default branch: main
- Local development on macOS (Terminal + Python venv)
- Claude used via CLI to read and modify files

Standard Git Workflow:
1. Make changes locally
2. Check status:
   git status
3. Stage files:
   git add <files>
4. Commit with descriptive message
5. Push to main

----------------------------------------------------------------
END OF PROJECT CONTEXT
----------------------------------------------------------------