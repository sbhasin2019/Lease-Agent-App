----------------------------------------------------------------
ACTIVE ROADMAP — PLANNED AND DEFERRED WORK
----------------------------------------------------------------

This file captures what is NOT yet built but is intentionally
planned or deferred. Nothing here is a commitment. Priorities
may change.

For the authoritative current state, see PROJECT_CONTEXT.md.
For historical decisions and fixes, see PROJECT_FIXES_AND_DECISIONS.md.

Status labels:
  NOT STARTED      — No code exists for this feature
  PARTIALLY BUILT  — Data layer or backend exists, but no UI
  DEFERRED         — Considered and intentionally postponed

----------------------------------------------------------------

LV-7.2 Step 7: Reminder System
Status: NOT STARTED

  Intent: Targeted reminders for missing payment categories.
  Proactive nudges when expected submissions are overdue.

  Context: Steps 1–6 of LV-7.2 (data model, edit UI, coverage
  computation, landlord summary, tenant summary, modal notices)
  are all complete. Only the reminder/nudge mechanism remains.

  Open questions:
  - In-app only, or external notifications?
  - Trigger: calendar-based, manual, or both?
  - Where do reminders surface? Dashboard? Tenant page? Both?
  - Storage: reminders will NOT use the existing review event
    model. A separate storage design is needed.

----------------------------------------------------------------

Dashboard Preferences
Status: NOT STARTED

  Intent: Allow the landlord to customise dashboard layout.

  Planned phases (in order):
  1. Define dashboard_prefs.json schema
  2. Drag-and-drop card reordering (SortableJS via CDN)
     with persistence to dashboard_prefs.json
  3. Card grouping (folder-style group cards) with persistence
  4. Dashboard attention badge — COMPLETE (2026-02-11).
     Moved to PROJECT_FIXES_AND_DECISIONS.md.

  Constraint: Presentation preferences must NEVER live inside
  lease_data.json. A separate preferences file is required.

----------------------------------------------------------------

Renewal Intent Prompts
Status: NOT STARTED

  Intent: When a lease approaches expiry, prompt the landlord
  about their renewal intention. Allow suppression so prompts
  are not repeated.

  Depends on: Dashboard Preferences (for suppression storage
  in dashboard_prefs.json).

----------------------------------------------------------------

Termination UI (Stage B Completion)
Status: PARTIALLY BUILT

  What exists:
  - termination_data.json with load/save functions
  - get_termination_for_lease() lookup
  - get_governing_lease_for_month() consumes termination data

  What remains:
  - create_termination_event() function
  - Landlord UI route and form to record a termination
  - Validation (termination date within lease period, etc.)
  - Visual indication on dashboard or lease view that a lease
    was terminated early

----------------------------------------------------------------

Residual CSS Cleanup
Status: NOT STARTED

  The following CSS exists in index.html but is not applied
  to any HTML element:
  - .lease-card.urgency-* classes (left-border colour accents
    from the old dashboard card design)

  Safe to remove. No functional impact. Low priority.

  ----------------------------------------------------------------

  Follow-up Nudge (7-Day Tenant Non-Response)
  Status: NOT STARTED

    Intent: When a conversation is awaiting tenant response for
    7+ days, show a soft, optional "Send follow-up?" nudge to
    the landlord inside the per-month modal and as a suggestion
    in the attention overview modal.

    Design decisions locked:
    - Nudge only when thread.status == "awaiting_tenant" and
      last landlord event >= 7 days ago
    - NOT a popup, NOT blocking, NOT required
    - Pre-fills editable default message, uses existing
      submit_payment_review endpoint (review_type = "response")
    - Dismiss is per-thread (session-only initially; persistence
      to be evaluated later)
    - Does NOT inflate attention badge count

    Open questions:
    - Should dismissal persist across sessions? If so, where?
      (dashboard_prefs.json is a candidate)
    - Should the nudge appear in the attention overview as a
      separate "Suggestions" section below real attention items?

----------------------------------------------------------------

DEFERRED ITEMS (No Current Plans)
----------------------------------------------------------------

The following have been explicitly considered and deferred.
They must not be partially or implicitly implemented without
explicit scope approval.

  - User authentication or accounts
  - Tenant identity verification
  - Email / SMS / push notifications
  - Payment verification or reconciliation
  - Editing or deleting payment confirmations
  - Token expiration policies beyond manual revocation
  - Aggregation of multiple submissions per month
  - Historical AI extraction preservation across versions
  - Mobile app
  - Product renaming / branding cleanup
  - Automated backup or recovery system

----------------------------------------------------------------
END OF ROADMAP
----------------------------------------------------------------
