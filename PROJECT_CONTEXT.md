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

-----------------------------------------------------------------
NEW FEATURE - STARTED ON 7 FEB 2026
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