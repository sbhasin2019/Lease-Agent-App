----------------------------------------------------------------
ACTIVE ROADMAP — PLANNED AND DEFERRED WORK
----------------------------------------------------------------

This file captures what is NOT yet built but is intentionally
planned or deferred. Nothing here is a commitment. Priorities
may change.

For the authoritative current state, see PROJECT_CONTEXT.md.
For historical decisions and fixes, see PROJECT_FIXES_AND_DECISIONS.md.

Status labels:
  COMPLETE         — Fully implemented and tested
  NOT STARTED      — No code exists for this feature
  PARTIALLY BUILT  — Data layer or backend exists, but no UI
  DEFERRED         — Considered and intentionally postponed

----------------------------------------------------------------

Unified Thread Engine (payment_review)
Status: COMPLETE (2026-02-13)

  The thread-based communication engine is fully implemented for
  payment_review threads. All legacy event-based code has been
  removed (9 functions deleted, templates cleaned).

  What is operational:
  - threads.json with threads[] and messages[]
  - Thread I/O: _load_all_threads(), _save_threads_file()
  - Read helpers: get_threads_for_lease_group(),
    get_messages_for_thread(), count_landlord_attention_threads(),
    get_attention_summary_for_lease(), find_open_thread(),
    build_thread_timeline()
  - Write helpers: ensure_thread_exists(), add_message_to_thread(),
    resolve_thread()
  - Materialisation: materialise_system_threads() creates
    payment_review threads for unthreaded payments on dashboard load
  - Write routes: submit_payment_review, tenant_payment_response
  - Read paths: dashboard badges, attention modal, lease detail
    monthly summary + thread timeline, tenant page
  - Smart redirect after review actions

  What is NOT yet operational:
  - missing_payment threads (creation logic not built)
  - renewal threads (creation logic not built)
  - 7-day nudge display (not built)
  - Auto-resolution hooks (deferred until thread types exist)

  See PROJECT_FIXES_AND_DECISIONS.md for implementation details.

----------------------------------------------------------------

LV-7.2 Step 7: Missing Payment Threads
Status: DESIGNED — NOT YET IMPLEMENTED

  Intent: Targeted reminders for missing payment categories.
  Proactive nudges when expected submissions are overdue.

  Context: Steps 1–6 of LV-7.2 (data model, edit UI, coverage
  computation, landlord summary, tenant summary, modal notices)
  are all complete.

  Design locked (2026-02-13): This feature is now part of the
  unified thread model. Missing payments create threads of type
  "missing_payment" in threads.json, not a separate reminder
  system. See PROJECT_CONTEXT.md → UNIFIED THREAD MODEL.

  Previous open questions — now resolved:
  - Storage: threads.json (no separate reminder file)
  - Trigger: calendar-based, materialised on dashboard load
    - Rent: X days after rent_due_day
    - Maintenance/utilities: end of month
    - NOT created if rent_due_day is null
    - First lease month respects lease_start_date
    - Future months never evaluated
  - Where do they surface: attention badge + attention modal
    (threads where waiting_on == "landlord")
  - In-app first; external delivery (WhatsApp/email) deferred
    but schema-ready
  - Auto-resolves when matching payment submitted

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

Renewal Threads
Status: DESIGNED — NOT YET IMPLEMENTED

  Intent: When a lease approaches expiry, prompt the landlord
  about their renewal intention.

  Design locked (2026-02-13): This feature is now part of the
  unified thread model. Renewal prompts create threads of type
  "renewal" in threads.json, not a separate prompt/suppression
  system. See PROJECT_CONTEXT.md → UNIFIED THREAD MODEL.

  Previous design (now superseded):
  - Was planned as standalone renewal intent prompts with
    suppression storage in dashboard_prefs.json.
  - No longer depends on Dashboard Preferences.

  Current design:
  - Created lazily on dashboard load when lease expiry is
    within configured window and no open renewal thread exists
  - waiting_on = "landlord"
  - Auto-resolves when renewal lease version created
  - No separate suppression mechanism needed — resolving the
    thread is the suppression

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
  Status: DESIGNED — NOT YET IMPLEMENTED

    Intent: When a conversation is awaiting tenant response for
    7+ days, show a soft, optional "Send follow-up?" nudge to
    the landlord.

    Design locked (2026-02-13): This feature is now part of the
    unified thread model. Nudges are computed display prompts,
    not stored messages. See PROJECT_CONTEXT.md → UNIFIED THREAD
    MODEL → 7-Day Nudge.

    Previous open questions — now resolved:
    - Display location: primary in thread view (per-category
      modal, at top of thread); secondary in Attention Overview
      modal under "Follow-ups (Optional)" section
    - Dismissal: session-only (no persistence needed for now)
    - Badge: does NOT inflate attention badge count

    Locked behaviour:
    - Condition: status == "open" AND waiting_on == "tenant"
      AND last landlord message >= 7 days ago
    - Does NOT create threads or messages automatically
    - Does NOT change waiting_on
    - If landlord sends reminder: message_type = "reminder",
      waiting_on remains "tenant"
    - Race-condition guard: re-check thread state before sending

----------------------------------------------------------------

DEFERRED ITEMS (No Current Plans)
----------------------------------------------------------------

The following have been explicitly considered and deferred.
They must not be partially or implicitly implemented without
explicit scope approval.

  - User authentication or accounts
  - Tenant identity verification
  - External channel delivery (WhatsApp, email, SMS) — message
    schema is ready (channel, delivered_via, external_ref fields),
    adapters not built. Previously listed as "Email / SMS / push
    notifications".
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
