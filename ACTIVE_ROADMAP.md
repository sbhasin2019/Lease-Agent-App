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
  - missing_payment threads for maintenance/utilities
    (rent missing_payment threads are now operational —
    see ACTIVE_BUILD.md Phases 6-9)
  - renewal threads (creation logic not built)
  - 7-day nudge display (not built)
  - Auto-resolution hooks for renewal threads (deferred)

  See PROJECT_FIXES_AND_DECISIONS.md for implementation details.

----------------------------------------------------------------

LV-7.2 Step 7: Missing Payment Threads
Status: PARTIALLY COMPLETE — rent is operational; maintenance/utilities not started

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
    - Rent: day after rent_due_day (grace period = 2 days)
    - Maintenance/utilities: end of month
    - NOT created if rent_due_day is null
    - First lease month respects lease_start_date
    - Future months never evaluated
  - Where do they surface: attention badge + attention modal
    + Action Console (threads where needs_landlord_attention
    == true, set after 2-day grace period)
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
  - NOT created if lease has an effective termination date
    before expiry
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

Action Console — Landlord Dashboard
Status: PHASE 10F + VISUAL REFINEMENTS COMPLETE

  Intent: Replace the modal-driven attention model with a
  persistent Action Console panel on the landlord dashboard.

  The dashboard becomes a two-column layout:
  - Left: lease cards grid (existing, with colour indicators)
  - Right: persistent Action Console (all attention items)

  Phase 10A: COMPLETE — topic_type + missing_payment info in modal
  Phase 10B: COMPLETE — two-column layout, read-only console
  Phase 10C: COMPLETE — inline expansion + automated reminder
  Phase 10D: COMPLETE — landlord-authored reminder modal
  Phase 10E: COMPLETE — payment review actions (acknowledge + flag)
    Acknowledge resolves thread. Flag requests tenant clarification.
    Both use modal-based flows with editable messages. Action
    buttons moved to collapsed item row for immediate visibility.
  Phase 10F: COMPLETE — reminder safeguards (24h cooldown,
    follow-up detection, follow-up wording)
  Dashboard Visual Refinements: COMPLETE — layout rebalance,
    landlord filter, lease card typography, state stamps,
    console accent bars
  Phase 10G: NOT STARTED — tenant page alignment

  See PROJECT_CONTEXT.md → UI ARCHITECTURE — CONTROL CENTRE
  MODEL for the full architectural specification.

----------------------------------------------------------------

Attention Modal Deprecation
Status: ACTIVE — PLANNED FOR REMOVAL

  The attention modal (opened via 🙋🏻 badge on lease cards)
  remains temporarily for backward compatibility.

  It will:
  - Continue functioning as-is
  - NOT receive new action buttons
  - NOT gain new responsibilities
  - Be removed in a future refactor once the Action Console
    supports all decision workflows

  Redirect flows (return_attention_for, return_to=attention)
  remain functional during the transition period.

  Decision date: 2026-02-20.
  See PROJECT_FIXES_AND_DECISIONS.md for rationale.

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
  - Full professional UI redesign — once core features are
    complete, rework the entire visual design to look like a
    polished, professionally-built app. Covers typography,
    colour system, spacing, component design, and overall
    visual consistency across all views (dashboard, detail,
    edit, tenant). This is a comprehensive visual overhaul,
    not incremental CSS tweaks.

----------------------------------------------------------------

Future Feature — External-Origin Payment Confirmations
Status: DEFERRED — DOCUMENTATION ONLY

  Intent: Allow rent confirmations to originate from sources
  other than tenant submission — initially landlord manual
  confirmation, eventually external communication channels
  (WhatsApp forwarding, SMS parsing, email ingestion).

  Why deferred (decision 2026-02-18):
  Implementing a standalone landlord confirmation route now
  would introduce payment logic, thread resolution logic,
  duplicate blocking, and tenant submission constraints that
  will likely need rework once external communications are
  introduced. The landlord-manual case is a subset of the
  broader "external-origin confirmation" problem.

  Planned architecture (when implemented):
  1. External message ingestion layer (WhatsApp/SMS/email)
  2. Message classification engine
  3. Proposed payment confirmation action
  4. Landlord confirmation step (approval before record creation)
  5. Payment record creation (submitted_via identifies origin)
  6. Automatic resolution of matching missing_payment threads
  7. Clear audit trail indicating external-origin event

  Current state (not a gap):
  - submitted_via field already exists in payment schema
    with documented values: "tenant_link" | "landlord_manual"
  - Thread message schema has channel, delivered_via,
    external_ref fields ready for external sources
  - Auto-resolution logic is origin-agnostic (resolves when
    any matching payment exists, regardless of submitted_via)
  - No code hard-codes "tenant_link" as the only valid source

  What must NOT be done until this feature is scoped:
  - No landlord confirmation routes
  - No duplicate blocking between tenant and landlord records
  - No tenant submission blocking based on landlord actions
  - No modifications to materialise_system_threads() filtering
  All rent confirmations must originate from tenant submissions.
  Landlord review remains limited to acknowledge or flag.

----------------------------------------------------------------

Future Enhancement — Compliance-Grade Audit Logging
Status: DEFERRED — DOCUMENTATION ONLY

  Intent: If the product ever needs to serve regulatory,
  legal, or enterprise environments, the thread system may
  need a formal audit trail of every system-triggered action.

  When this would be necessary:
  - Regulatory compliance (e.g. rent control authorities
    requiring proof that reminders were sent on time)
  - Legal disputes (landlord or tenant contesting whether
    a reminder was issued or when escalation occurred)
  - Enterprise clients requiring tamper-evident records

  Current state (not a gap):
  The system already records key timestamps on each thread:
  created_at, resolved_at, escalation_started_at,
  last_reminder_at. Messages between landlord and tenant are
  stored with timestamps, actor, and message_type. This is
  sufficient for current use. The enhancement below would
  add a richer, more granular history if justified.

  Two possible approaches:

  OPTION A — Per-Thread System Event Log

    Add a system_events list inside each thread object.
    This list would record system-triggered events such as:
    - missing_payment thread auto-created
    - reminder automatically sent
    - escalation triggered
    - auto-resolution triggered
    - reminder suppression toggled

    Each event would store:
    - event_type (string, e.g. "escalation_triggered")
    - timestamp (ISO format)
    - optional metadata (e.g. reason, days overdue)

    Messages between users remain in the messages array;
    system_events is strictly for automated actions.

    Advantage: self-contained lifecycle history inside each
    thread. Easy to display a thread's full history in the UI.

    Disadvantage: event data is scattered across threads.
    Harder to query globally (e.g. "show all escalations
    across all leases last month").

  OPTION B — Append-Only Global Audit File

    Create a separate audit_log.json (or similar).
    Every system-triggered action appends a new record.
    Records are NEVER modified or deleted (append-only).

    Each record would include:
    - thread_id
    - lease_group_id
    - event_type
    - timestamp
    - relevant metadata

    Advantage: stronger for compliance because it is
    tamper-evident and centralised. Easy to query, export,
    or submit as evidence. Natural fit for future migration
    to a database with write-once semantics.

    Disadvantage: separate file to maintain. Requires
    cross-referencing with threads.json to reconstruct
    per-thread history.

  Recommendation:
  Do not implement either option unless regulatory or
  enterprise requirements explicitly justify the added
  complexity. The current timestamp fields are sufficient
  for normal landlord-tenant operations. If this becomes
  necessary, Option B is likely the better choice for
  compliance scenarios.

----------------------------------------------------------------
END OF ROADMAP
----------------------------------------------------------------
