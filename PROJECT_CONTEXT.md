 ----------------------------------------------------------------
PROJECT: Lease Management & Renewal Assistant (Single-User MVP)
----------------------------------------------------------------

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
LAST UPDATED - 6 FEBRUARY 2026
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
LAST UPDATED - 5 February 2026
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