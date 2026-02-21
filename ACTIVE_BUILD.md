----------------------------------------------------------------
ACTIVE BUILD — Rent Obligation & Missing Payment Engine
----------------------------------------------------------------
Status: IN PROGRESS
Started: 2026-02-14

This file captures the active implementation project.
On completion, relevant sections will be folded into:
  - PROJECT_CONTEXT.md (authoritative state)
  - ACTIVE_ROADMAP.md (update status)
  - PROJECT_FIXES_AND_DECISIONS.md (decisions log)

Then this file will be cleared for the next project.

================================================================
WHAT ARE WE BUILDING? (PLAIN ENGLISH)
================================================================

Right now, Mapmylease can track rent payments AFTER a tenant
submits them. But it has no way to notice when a tenant has
NOT submitted — it can't send reminders, flag overdue rent,
or alert the landlord.

We are building a "missing payment engine" that:

1. Notices when rent hasn't been submitted after the due date
2. Creates a thread (a conversation record) to track it
3. Sends automatic reminders to the tenant
4. Escalates (makes it more visible) if the tenant doesn't pay
5. Automatically closes the thread when the tenant finally pays

We're also handling a tricky edge case: when a lease starts
in the MIDDLE of a month (e.g. January 15), the first month's
rent is different — it might be prorated (a partial amount).
We need to model that properly before the reminder engine
can work correctly.

================================================================
SECTION 1 — FIRST MONTH RENT MODEL (DATA LAYER)
================================================================

WHY THIS MATTERS:
Imagine a lease starts on January 15 and rent is due on the
5th of each month. January 5th has already passed — so when
is January's rent due? How much should it be? It's not a full
month, so it might be a smaller (prorated) amount.

We need to store this information so the reminder engine
knows the correct due date and amount for that first month.

---

Add to lease["current_values"]:

    first_month_mode              (string | null)
        allowed:
            "prorated_immediate"
                = Pay prorated amount right away
                  (due date = lease start date)

            "prorated_next_due_day"
                = Pay prorated amount on the next regular
                  due date (e.g. February 5)

            "custom"
                = Landlord enters their own date and amount

    first_month_due_date          (YYYY-MM-DD | null)
    first_month_amount            (number | null)

Required only if:
    lease_start_date.day > rent_due_day
    (meaning the lease started AFTER the due date had passed)

Otherwise:
    all three fields = null
    (normal monthly rent applies — no special handling needed)

---

PRORATION RULE (if mode is "prorated_immediate" or
"prorated_next_due_day"):

    HOW PRORATION WORKS:
    If you move in on January 15, you only lived there for
    17 days out of 31. So you pay 17/31 of the full rent.

    days_in_month = total days in lease_start_date month
    days_occupied = days from lease_start_date to month-end
                    (inclusive)
    prorated_amount = monthly_rent * (days_occupied / days_in_month)

    Round to nearest integer (same as existing money handling).
    Landlord must explicitly confirm the calculated amount
    before saving.

If mode is "custom":
    Landlord manually enters both due_date and amount.
    No automatic calculation.

IMPORTANT RULE:
The first month ALWAYS exists as its own separate obligation.
Never merge it into the next month.
Never add the prorated amount onto the next month's rent.

RENEWALS:
When creating a renewal lease version:
    first_month_* fields MUST initialise to null.
    Do NOT copy from previous version.
    (Each version has its own start date, so the first-month
    situation may be completely different.)

AI:
AI must NOT populate first_month_* fields.
These are landlord decisions, not document facts.

---

HELPER FUNCTION (NEW, PURE, NO I/O):

    get_rent_due_info_for_month(lease, year, month)

    WHAT THIS DOES:
    Given a lease and a specific month, it returns the correct
    rent due date and expected amount. For the first month
    (if prorated), it uses the special first_month values.
    For all other months, it uses the standard rent_due_day
    and monthly_rent.

    Returns:
        {
            "due_date": date,
            "expected_amount": number | null,
            "is_first_month": boolean
        }

    "Pure" means this function only does math — it doesn't
    read or write any files.

================================================================
SECTION 2 — MISSING RENT THREAD ENGINE
================================================================

HOW THREADS WORK (RECAP):
A "thread" is like a conversation record stored in
threads.json. It tracks a specific topic (like "rent for
January 2026 is missing") and contains messages back and
forth between the system, landlord, and tenant.

Each thread has:
  - A status: "open" (active) or "resolved" (done)
  - A waiting_on field: who needs to act next
  - Messages: the history of what happened

---

Thread type for missing rent:
    topic_type = "missing_payment"
    topic_ref = "rent:YYYY-MM"  (e.g. "rent:2026-01")

---

4 NEW FIELDS added to ALL threads (with safe defaults):

    last_reminder_at             (timestamp | null)
        WHAT: When was the last reminder sent for this thread?
        WHY: Prevents sending duplicate reminders. If we sent
             one 3 days ago, we know to wait 4 more days.

    auto_reminders_suppressed    (boolean, default false)
        WHAT: Has the landlord clicked "Stop further reminders"?
        WHY: Lets the landlord silence automatic reminders for
             a specific month without hiding the overdue status.

    escalation_started_at        (timestamp | null)
        WHAT: When did this thread become "escalated" (overdue
              past the grace period)?
        WHY: Controls when the attention badge lights up.
             Stores the current timestamp when escalation
             is detected (i.e. when the dashboard is loaded
             and the grace period has passed).

    needs_landlord_attention     (boolean)
        WHAT: Should this thread appear in the landlord's
              attention badge?
        WHY: This is the ONE field the badge checks. Simpler
             and more reliable than computing badge status
             from multiple fields.

---

BACKFILL STRATEGY:

    WHAT THIS MEANS:
    Existing threads (created before this feature) don't have
    the needs_landlord_attention field. The first time the
    dashboard loads after deployment, the system adds the
    field to every existing thread with a safe default of false.

    This is "idempotent" — running it multiple times produces
    the same result. Safe to repeat.

    Note: The backfill sets false as a safe default.
    materialise_system_threads() and add_message_to_thread()
    handle correct values for payment_review threads going
    forward.

---

BADGE RULE (SIMPLIFIED):

    OLD RULE: Count threads where waiting_on == "landlord"
    NEW RULE: Count threads where needs_landlord_attention == true

    WHY CHANGE:
    Missing payment threads keep waiting_on = "tenant" (because
    the tenant owes the payment). But after the grace period,
    the landlord still needs to know about it. The new field
    lets us show it in the badge without pretending the
    landlord is responsible for the action.

================================================================
SECTION 3 — THREAD CREATION RULE
================================================================

WHEN IS A THREAD CREATED?

    The day AFTER the rent due date, if rent hasn't been paid.

    Example: Rent due January 5.
    On January 6, if no rent submission exists, the system
    creates a missing_payment thread for "rent:2026-01".

    Before January 6: no thread. The due date is just
    informational (shown in the lease detail view).

ELIGIBILITY RULES (all must be true):

    - Month is within the lease start/end dates
    - Rent is listed as expected in the lease settings
    - The due date for that month has passed
    - No rent submission exists for that month
    - No OPEN thread already exists for that month
      (resolved threads do NOT block re-creation)
    - The lease is not a draft
    - The due date is on or after the tracking start date
      (see Section 9 — prevents false threads for old months)

INITIAL STATE of new thread:

    waiting_on = "tenant"
        (tenant needs to submit the payment)
    needs_landlord_attention = false
        (not yet escalated — within grace period)
    escalation_started_at = null
        (grace period hasn't passed yet)
    last_reminder_at = null
        (no reminder sent yet)
    auto_reminders_suppressed = false
        (automatic reminders are enabled)

================================================================
SECTION 4 — ESCALATION RULE
================================================================

WHAT IS ESCALATION?
After the due date, the tenant gets a 2-day grace period.
If they still haven't paid after those 2 days, the thread
"escalates" — it becomes more visible to the landlord
(appears in the attention badge).

Grace period = 2 days after due_date

If:
    needs_landlord_attention is false
        (hasn't already been escalated)
AND today > due_date + 2 days
        (grace period has passed)

Then:
    needs_landlord_attention = true
    escalation_started_at = now (current timestamp,
        only if escalation_started_at is still null)

KEY RULES:
    - This is a ONE-TIME flip. Once set, never changed.
    - No system message is appended (silent escalation).
    - waiting_on stays "tenant" — responsibility never
      shifts to the landlord.
    - The thread remains escalated until the tenant pays.

================================================================
SECTION 5 — AUTOMATIC REMINDERS
================================================================

WHAT ARE AUTOMATIC REMINDERS?
The system can send reminder messages to the tenant inside
the thread. These appear as "Automatic reminder" messages
in the conversation history.

WHEN IS AN AUTOMATIC REMINDER SENT?

All of these must be true:

    today > due_date
        (rent is overdue)
    AND today <= due_date + 2 days
        (still within 2-day grace period)
    AND needs_landlord_attention == false
        (not yet escalated)
    AND auto_reminders_suppressed == false
        (landlord hasn't stopped reminders)
    AND last_reminder_at is null
        (no reminder has ever been sent for this thread)

If all true:
    Add a message to the thread:
        actor = "system"
        message_type = "auto_reminder"
        body = calm, neutral reminder text (month-specific)
    Set last_reminder_at = now

MAX REMINDERS PER THREAD = 1:
Each missing_payment thread receives at most one automatic
reminder. The last_reminder_at guard ensures no repeats.
There is no "every 7 days" repeat cadence — the reminder
fires once during the grace window (days 1–2) and then
stops permanently for that thread.

IMPORTANT — NO REPLAY:
If the landlord doesn't log in for 3 weeks, the system
does NOT send any reminder on login (the grace window
has already passed). Only current state is evaluated.

---

MANUAL LANDLORD REMINDER (FUTURE — NOT YET IMPLEMENTED):
The landlord will be able to send reminders manually. These:
    - Use add_message_to_thread() function
    - Are marked as actor = "landlord"
    - Also update last_reminder_at
    - Because automatic reminders are gated by
      last_reminder_at == null, any manual reminder
      permanently blocks automatic reminders for that
      thread. This is intentional — the landlord has
      already taken action.

---

TECHNICAL NOTE — FUNCTION-LEVEL LOAD/SAVE:
Each engine function loads threads.json at its own entry
point and saves once at the end (if it mutated state).
send_missing_payment_reminders() loads once, appends all
messages in memory, and saves once. This is per-function
discipline, not pipeline-wide.

Manual landlord reminders will go through
add_message_to_thread() via a separate web request —
so they will have their own load/save cycle. No conflict.

================================================================
SECTION 6 — GROUPED REMINDER DISPLAY (UI ONLY)
================================================================

WHY GROUPING?
Sometimes two months share the same due date. This happens
when the first month is prorated and due on the next regular
due date. For example:

    January (prorated) due February 5
    February (full rent) due February 5

Both are due on the same date. The UI groups them together
so the landlord sees one combined view instead of two
separate items.

GROUPING RULE:
    Group open missing_payment rent threads by identical
    due_date.

IMPORTANT: This is display only. The threads remain
completely separate in the backend. No merging.

For each group, display:

    Due <date>
    Total payable: SUM(amounts)

    Includes:
        - Month — amount
        - Month — amount

    [ Send Reminder ]

================================================================
SECTION 7 — GROUPED REMINDER ACTION
================================================================

When landlord clicks grouped "Send Reminder":

1) Generate ONE message body listing all months in the group.
2) For EACH thread in the group:
       Add the same message to each thread
       Update last_reminder_at on each thread
3) Skip any thread where auto_reminders_suppressed is true.

SUPPRESSION:
If landlord clicks "Stop further reminders" on a group:
    Set auto_reminders_suppressed = true on EACH thread
    in the group.

    This stops automatic reminders but does NOT:
    - Hide the overdue status
    - Stop escalation
    - Delete the thread
    - Affect other months

================================================================
SECTION 8 — AUTO-RESOLUTION
================================================================

WHAT IS AUTO-RESOLUTION?
When the tenant finally submits a rent payment, the system
automatically closes the missing_payment thread. The
landlord doesn't have to manually acknowledge it.

On dashboard load:

If:
    An open missing_payment thread exists for rent:YYYY-MM
AND a rent payment submission exists for that month
    (in payment_data.json)

Then:
    Resolve the thread (status = "resolved")
    Set needs_landlord_attention = false
    Thread stays in the system as a historical record

The landlord sees "Resolved — tenant submitted rent payment"
in their attention overview.

================================================================
SECTION 9 — TRACKING BOUNDARY RULE
================================================================

THE PROBLEM:
Imagine a landlord uploads a lease that started 18 months
ago. The app has no payment records for those 18 months.
Without a boundary, the engine would create 18 "missing
rent" threads — even though rent was actually paid in person.

THE SOLUTION:
Only track months starting from when the lease became active
in the app.

    tracking_start_date = max(lease_start_date, lease.created_at)

    The system picks whichever date is LATER:
    - When the lease officially started, OR
    - When the lease was uploaded to the app

    Any month with a due date BEFORE this boundary is ignored.

EXAMPLES:

    Lease start: 1 Jan 2026, Uploaded: 28 Dec 2025
    tracking_start = 1 Jan 2026
    Result: All months from January onward are tracked.

    Lease start: 1 Jan 2026, Uploaded: 20 Jul 2026
    tracking_start = 20 Jul 2026
    Result: Jan-June ignored. July onward tracked.

No new stored fields. Uses existing lease.created_at.
Also explicitly skip draft leases (status == "draft").

================================================================
SECTION 10 — IDENTITY & SAFETY GUARANTEES
================================================================

These rules prevent bugs and data corruption:

THREAD CREATION IS IDEMPOTENT:
    "Idempotent" means doing the same thing twice produces
    the same result. Before creating a thread, the system
    checks if one already exists for that month. If yes, it
    skips. Loading the dashboard 10 times in a row creates
    exactly one thread, not 10.
    Note: payment_review checks ALL statuses (open + resolved).
    missing_payment checks OPEN threads only (resolved ones
    allow re-creation).

ESCALATION IS ONE-TIME:
    The system checks: "Is escalation_started_at still null?"
    If it's already set, escalation is skipped. No duplicate
    escalation.

REMINDERS ARE ONE-PER-THREAD:
    The system checks last_reminder_at. If any reminder has
    been sent (last_reminder_at is not null), it skips.
    Max one automatic reminder per thread ever. Refreshing
    the dashboard 50 times sends zero extra reminders.
    Manual landlord reminders also update last_reminder_at,
    permanently blocking automatic reminders for that thread.

GROUPING IS UI-ONLY:
    Threads are never merged or combined in storage. Grouping
    happens only when displaying data to the landlord.

FUNCTION-LEVEL LOAD / SAVE:
    Each engine function loads threads.json independently
    at its own entry point, makes changes in memory, and
    saves once at the end (only if it mutated state).
    The pipeline does NOT use a single-load/single-save
    model across the full cycle — each function operates
    on its own load/save cycle.
    Exception: materialise_missing_payment_threads()
    delegates to ensure_thread_exists(), which loads and
    saves per-thread (N loads/saves for N new threads).
    A pipeline-wide single-load model is a future
    optimisation, not current behaviour.

NO NEW JSON FILES:
    Everything uses existing files (threads.json, lease_data.json,
    payment_data.json). No new data files created.

================================================================
IMPLEMENTATION FRAMEWORK
================================================================

Each phase is one self-contained piece of work.
We implement ONE phase at a time, test it, then move on.

----------------------------------------------------------------

Phase 1 — Lease Data Model                          [COMPLETE]

    WHAT WE'RE DOING:
    Adding three new fields (first_month_mode,
    first_month_due_date, first_month_amount) to the lease
    data structure. This is like adding new columns to a
    spreadsheet — the columns exist but are empty (null)
    until someone fills them in.

    We also make sure that:
    - Old leases get these fields added automatically (null)
    - New leases start with these fields as null
    - Renewal leases get fresh null values (not copied)
    - AI extraction ignores these fields

    WHAT CHANGES:
    - app.py: new migration function, updated lease creation
      paths (4 places)

    WHAT DOES NOT CHANGE:
    - templates, threads, payments, badge, dashboard display

    DEPENDS ON: nothing
    RISK: low — adding null fields is non-destructive

----------------------------------------------------------------

Phase 2 — Rent Due Helper                           [COMPLETE]

    WHAT WE'RE DOING:
    Creating a small function that answers the question:
    "For this lease, in this month, when is rent due and
    how much should it be?"

    It checks whether the month is the first lease month
    with special proration rules, and returns the correct
    due date and amount. For all other months, it returns
    the standard rent_due_day and monthly_rent.

    We also create a proration calculator that computes
    the partial rent amount for a partial first month.

    WHAT CHANGES:
    - app.py: two new functions (no other changes)

    WHAT DOES NOT CHANGE:
    - Everything else — these functions aren't called yet

    DEPENDS ON: Phase 1 (fields must exist)
    RISK: zero — nobody calls these functions until Phase 6

----------------------------------------------------------------

Phase 3 — First Month Edit Mode UI                  [COMPLETE]

    WHAT WE'RE DOING:
    Adding form fields to the lease Edit Mode so the landlord
    can set first-month options. When the landlord enters a
    lease_start_date and rent_due_day where start > due, a
    new section appears asking:

    "How should first month rent be handled?"
    A) Prorated and due immediately
    B) Prorated and due on next rent day
    C) Custom amount and date

    The system calculates the prorated amount and shows the
    math. The landlord confirms before saving.

    WHAT CHANGES:
    - app.py: save route validation for first_month fields
    - app.py: save_lease() must add first_month_* to its
      current_values whitelist — currently save_lease()
      does a FULL REPLACEMENT of current_values (line ~3191),
      not a merge. Any field not in the whitelist is wiped
      on save. Until Phase 3 adds them, the fields stay null
      and nothing is lost. But Phase 3 MUST add them before
      any UI allows setting non-null values.
    - templates/index.html: new form section in Edit Mode

    WHAT DOES NOT CHANGE:
    - threads, payments, badge, dashboard cards

    DEPENDS ON: Phase 1 (fields exist), Phase 2 (proration calc)
    RISK: medium — template changes need careful testing.
    CRITICAL: save_lease() whitelist update is mandatory.

----------------------------------------------------------------

Phase 4 — Thread Schema & Function Updates          [COMPLETE]

    WHAT WE'RE DOING:
    Adding four new fields to the thread data model and
    updating three existing functions that create/modify
    threads.

    This is like Phase 1 but for threads instead of leases.
    The four fields (last_reminder_at, auto_reminders_suppressed,
    escalation_started_at, needs_landlord_attention) are added
    with safe defaults so nothing breaks.

    The key change: the needs_landlord_attention field is added
    to all threads with a safe default (false). For missing_payment
    threads, escalation logic sets it to true after the grace
    period. For payment_review threads, needs_landlord_attention
    is set to true at creation by materialise_system_threads()
    and synced by add_message_to_thread() on every message
    action (scoped to payment_review only).

    WHAT CHANGES:
    - app.py: ensure_thread_exists(), add_message_to_thread(),
      resolve_thread(), materialise_system_threads() (backfill)

    WHAT DOES NOT CHANGE:
    - badge functions (Phase 5), templates, lease data

    DEPENDS ON: nothing (independent of Phases 1-3)
    RISK: HIGH — these functions handle all existing
    payment_review threads. Must test the full
    flag/reply/acknowledge cycle after this phase.

----------------------------------------------------------------

Phase 5 — Badge Simplification                      [COMPLETE]

    WHAT WE'RE DOING:
    Changing how the attention badge counts threads.

    OLD: Count threads where waiting_on == "landlord"
    NEW: Count threads where needs_landlord_attention == true

    For existing payment_review threads, the result is
    identical (because Phase 4's backfill sets
    needs_landlord_attention = true when waiting_on is
    "landlord"). But the new rule also works for
    missing_payment threads, where waiting_on stays "tenant"
    but the badge should still show after escalation.

    WHAT CHANGES:
    - app.py: count_landlord_attention_threads(),
      get_attention_summary_for_lease()

    WHAT DOES NOT CHANGE:
    - thread creation, templates, lease data

    DEPENDS ON: Phase 4 (needs_landlord_attention must exist)
    RISK: medium — badge is highly visible. Must verify
    counts match before and after.

    *** CHECKPOINT A ***
    After Phase 5, verify ALL existing behaviour:
    - Dashboard loads normally
    - Badge counts are correct
    - Flag/reply/acknowledge cycle works
    - Attention modal shows correct items
    - Smart redirect works
    - Tenant page works
    If anything is broken, fix before continuing.

----------------------------------------------------------------

Phase 6 — Engine: Creation & Tracking Boundary      [COMPLETE]

    WHAT WE'RE DOING:
    This is the core of the new engine. We expand
    materialise_system_threads() to also create
    missing_payment threads for overdue rent.

    A new function materialise_missing_payment_threads() is
    created as a sibling to materialise_system_threads().
    It calls evaluate_missing_payment_status() (the pure
    evaluator from Phase 4 Step 2) for each month, and
    calls ensure_thread_exists() to create threads.

    It also applies the tracking boundary (Section 9) so
    old months before the lease was uploaded are ignored.

    WHAT CHANGES:
    - app.py: new materialise_missing_payment_threads()
      function, new evaluate_missing_payment_status()
      function, dashboard route (call both materialisers)

    WHAT DOES NOT CHANGE:
    - escalation, reminders, auto-resolution (Phases 7-9)
    - templates, badge functions

    DEPENDS ON: Phase 2 (helper), Phase 4 (thread schema),
                Phase 5 (badge working)
    RISK: medium — changes dashboard load logic. Must verify
    performance with multi-year leases.

----------------------------------------------------------------

Phase 7 — Engine: Escalation                        [COMPLETE]

    WHAT WE'RE DOING:
    Adding the grace period check to the evaluation function.
    For each open missing_payment thread, if 2 days have
    passed since the due date and escalation hasn't already
    been set, flip needs_landlord_attention to true and set
    escalation_started_at.

    Implemented as a standalone function
    escalate_missing_payment_threads() called from the
    dashboard pipeline after auto-resolution.

    WHAT CHANGES:
    - app.py: new escalate_missing_payment_threads() function

    WHAT DOES NOT CHANGE:
    - reminders, auto-resolution, templates

    DEPENDS ON: Phase 6
    RISK: low — isolated logic, one-time flip

----------------------------------------------------------------

Phase 8 — Engine: Automatic Reminders               [COMPLETE]

    WHAT WE'RE DOING:
    Adding the automatic reminder check as a separate pipeline
    step. For each open missing_payment thread in the grace
    period (days 1–2 after due date), if no reminder has been
    sent yet and reminders are not suppressed, append one
    auto_reminder message to the thread.

    WHAT CHANGES:
    - app.py: new send_missing_payment_reminders() function

    WHAT DOES NOT CHANGE:
    - auto-resolution, templates

    DEPENDS ON: Phase 6
    RISK: medium — must verify no duplicate reminders on
    repeated dashboard loads

----------------------------------------------------------------

Phase 9 — Engine: Auto-Resolution                   [COMPLETE]

    WHAT WE'RE DOING:
    Adding the auto-resolution check. For each open
    missing_payment thread, if a matching rent payment now
    exists in payment_data.json, resolve the thread.

    This check runs FIRST in the evaluation (before
    escalation or reminders) so we don't escalate or remind
    for months that have already been paid.

    WHAT CHANGES:
    - app.py: new auto_resolve_missing_payment_threads() function

    WHAT DOES NOT CHANGE:
    - templates

    DEPENDS ON: Phase 6

    *** CHECKPOINT B ***
    After Phase 9, verify the complete engine:
    - Thread created for overdue month
    - Escalation activates after grace period
    - Badge shows escalated threads
    - Automatic reminder appears
    - No duplicate reminders on reload
    - Thread resolves when payment submitted
    - Existing payment_review threads unaffected

    RISK: low — resolution logic is straightforward

----------------------------------------------------------------

Phase 10 — Action Console Architecture               [IN PROGRESS]

    WHAT WE'RE DOING:
    Replacing the modal-driven attention model with a persistent
    Action Console on the landlord dashboard.

    This is a structural UI refactor, not a cosmetic tweak.
    The Action Console becomes the primary interface for
    landlord decisions. The attention modal remains temporarily
    but will not receive new functionality.

    Phase 10A (COMPLETE):
    - Added topic_type to get_attention_summary_for_lease() items
    - Exposed missing_payment thread info (expected_amount,
      expected_due_date, suppression status) in attention modal

    Phase 10B — Dashboard Action Console (COMPLETE):
    - New helper: get_global_attention_summary(thread_data, leases)
      Aggregates all attention items, groups by lease, sorts by
      urgency. Returns structured data for console rendering.
    - Dashboard route passes console data to template
    - Two-column dashboard layout:
        Left: lease cards grid (existing)
        Right: persistent Action Console panel (new)
    - Lease card colour indicators:
        Amber = has open attention items
        Green = zero open attention items
    - Card click filters console to that lease
    - Click outside lease cards and console resets to global view
    - Console is read-only (no action buttons yet)
    - Global alerts box removed (replaced by console)
    - Responsive: stacks vertically below 1024px

    Phase 10C — Action Console Inline Operational Mode (COMPLETE):

      Step 1: Backend enrichment (COMPLETE)
        - get_attention_summary_for_lease() extended with:
            last_action (summary of most recent message)
            recent_messages (last 1-3 messages, oldest first)
            overdue_days (escalated missing_payment only,
              gated by escalation_started_at)
            status_display (pre-computed human-readable status)
            status_css (pre-computed CSS class)
            Plus thread state fields: open_month, topic_ref,
            escalation_started_at, last_reminder_at
        - add_message_to_thread() extended: sets last_reminder_at
          when message_type == "reminder" and topic_type ==
          "missing_payment". Permanently blocks auto-reminders.
        - New fields pass through get_global_attention_summary()
          automatically via dict spread (no changes needed).

      Step 2: Inline expansion — read-only (COMPLETE)
        - Console items expand inline (one-at-a-time accordion)
        - Expanded panel shows: status, due date, expected amount,
          escalation date, suppression status, recent activity
        - Chevron indicator (▸ / rotates on expand)
        - Lease card click filters console to that lease
        - Click outside resets to global view
        - Event-delegated JS in IIFE (no inline handlers)
        - Templates render pre-computed fields only (no
          business logic in Jinja)

      Step 3: Inline reminder — missing_payment only (COMPLETE)
        - POST /thread/<thread_id>/reminder route
        - Validates: thread exists, topic_type == missing_payment,
          status == open
        - Calls add_message_to_thread() with message_type="reminder"
          and system-generated body ("Payment reminder sent.")
        - last_reminder_at set automatically (blocks auto-reminders)
        - Redirects to dashboard (POST + redirect pattern)
        - Send Reminder button in .console-panel-actions, gated by
          topic_type == "missing_payment" in template
        - Communication modal deferred to Phase 10D.

      Originally planned Steps 3-5 (payment_review actions,
      suppress toggle, full history modal) descoped from 10C.
      Payment review actions and full history modal will be
      addressed in future phases as needed.

    Phase 10D — Landlord-Authored Communication Layer (COMPLETE):

      Step 1: Replace POST form with modal trigger (COMPLETE)
        - Send Reminder button changed from <form> submit to
          <button> with data attributes (thread-id, lessee-name,
          lessor-name, open-month)
        - No POST on click, no JS wiring yet

      Step 2: Add reminder modal HTML structure (COMPLETE)
        - Hidden modal overlay with form, textarea, hidden input
        - CSS for modal-overlay, modal-container, modal-header,
          modal-textarea, modal-footer, btn-primary, btn-secondary
        - No JS behavior yet

      Step 3: Wire modal open/close + draft injection (COMPLETE)
        - Lazy DOM lookups (modal HTML is after script in DOM)
        - Click .btn-open-reminder-modal opens modal
        - Draft text: "Dear {lessee_name}, ... {open_month} ...
          Many thanks, {lessor_name}"
        - Form action set dynamically to /thread/{id}/reminder
        - Close on: X button, Cancel, overlay click, ESC key
        - closeReminderModal() clears textarea and form state

      Step 4: Backend accepts landlord-authored body (COMPLETE)
        - thread_send_reminder() reads request.form["body"]
        - Strips whitespace, aborts 400 if empty
        - Passes landlord-authored body to add_message_to_thread()
        - add_message_to_thread() unchanged
        - last_reminder_at invariant preserved

      Step 5: Backend enrichment — lease names (COMPLETE)
        - get_attention_summary_for_lease() loads current lease
          to get lessee_name and lessor_name from current_values
        - Names added to each item dict (empty string fallback)
        - Modal draft text now shows actual tenant/landlord names
        - Company names render exactly as stored (no parsing)

    Phase 10E — Payment Review Actions (COMPLETE):

      Step 1: Backend routes (COMPLETE)
        - POST /thread/<thread_id>/review/acknowledge
          Validates payment_review + open. Calls add_message_to_thread()
          with message_type="acknowledge". Second load-save sets
          needs_landlord_attention=False. Thread becomes resolved.
        - POST /thread/<thread_id>/review/flag
          Validates payment_review + open. Calls add_message_to_thread()
          with message_type="flag". Second load-save sets
          needs_landlord_attention=False. Thread remains open,
          waiting_on="tenant".
        - Both validate non-empty body from request.form.

      Step 2: Template buttons (COMPLETE)
        - Acknowledge button (class="btn-review-ack", green)
        - Flag button (class="btn-review-flag", red)
        - Gated by topic_type == "payment_review" in template

      Step 3: Acknowledge modal (COMPLETE)
        - id="review-ack-modal"
        - Explanation text + editable textarea
        - Prefilled draft: "Dear {name}, I confirm that I have
          reviewed your recent payment submission..."
        - Form action set dynamically to /review/acknowledge
        - Close on: X, Cancel, overlay, ESC

      Step 4: Flag modal (COMPLETE)
        - id="review-flag-modal"
        - Explanation text + empty textarea (no prefill)
        - Title: "Request Clarification"
        - Form action set dynamically to /review/flag
        - Close on: X, Cancel, overlay, ESC

      UX improvement: Buttons moved to collapsed item row (COMPLETE)
        - Primary action buttons (Send Reminder, Acknowledge, Flag)
          now render in .console-item-actions within the collapsed
          row, visible without expanding the panel.
        - Expanded panel contains only thread history, secondary
          details, and View Full History button.
        - JS toggle guard: clicks on .console-item-actions skip
          the panel toggle handler.

    Phase 10F — Reminder Safeguards (COMPLETE):
      - 24h backend cooldown in thread_send_reminder()
        Uses datetime.utcnow() for UTC consistency.
      - Frontend follow-up detection: modal JS reads
        data-last-reminder-at, blocks if <1 day, warns if 1-5 days
        with follow-up wording, standard draft if >5 days
      - data-last-reminder-at attribute on Send Reminder button

    Dashboard Visual Refinements (COMPLETE):
      - Column ratio: 1fr 1fr → 1.6fr 0.9fr (lease-dominant)
      - Lease cards: 2-column grid, max-width 520px, 900px fallback
      - Server-side landlord filter (dropdown, filters cards + console)
      - Landlord section headers: 16px/600/#111827, count "(2)", border
      - Removed "Needs Attention" button from dashboard cards
      - Removed "Lease started on" subtitle from cards
      - Removed dashboard compact card overrides (scale 0.8, 13px, etc.)
      - Typography rebalanced: title 18px/700, rent 14px/600,
        expiry 12px/700, tenant 11px, padding 12px, gap 5px
      - Upload button restyled (outline), header restructured
      - Console: accent bars, urgency dots removed, visual hierarchy
      - Lease state stamps: diagonal EXPIRED/TERMINATED overlays
        (23px/900, 3px red border, no background, vertically positioned
        to avoid overlapping primary CTAs)
      - Old lifecycle ribbons replaced by stamp overlays
      - Nickname background fill: grey default, no color for
        expired/terminated (stamp is sole lifecycle indicator)
      - Header upgraded: "MapMyLease" branding with premium banner
        (border-bottom, 3px top accent bar, 24px/700 title)
      - Subtitle: "We help you track your lease."

    Phase 10G — Tenant Page (FUTURE, not this step):
    - Overdue rent notice with reminder messages
    - Tenant Action Console (mirrors landlord model)

    WHAT CHANGES:
    - app.py: get_global_attention_summary() helper,
      get_attention_summary_for_lease() enrichment,
      add_message_to_thread() last_reminder_at extension,
      dashboard route enrichment, thread_review_acknowledge(),
      thread_review_flag(), thread_send_reminder()
    - templates/index.html: two-column layout, Action Console
      panel with inline expansion + action buttons in collapsed
      row, three modals (reminder, acknowledge, flag), lease card
      colour indicators, responsive CSS, event-delegated JS

    WHAT DOES NOT CHANGE:
    - Engine evaluation logic (Phases 6-9)
    - Attention modal (kept for backward compatibility)
    - Lease detail view
    - Edit mode
    - Tenant page
    - Thread state machine
    - Badge logic

    DEPENDS ON: all previous phases
    RISK: medium — dashboard layout restructure needs careful
    testing across screen sizes

    See PROJECT_CONTEXT.md → UI ARCHITECTURE — CONTROL CENTRE
    MODEL for the authoritative architectural specification.

    Phase 10H — Hardening (2026-02-21)

    Supporting technical-debt passes executed in parallel with
    Phase 10 build:

    - PASS 5B — z-index standardisation (.modal-overlay 9999 → 1000)
    - PASS 5C — Urgency selector consolidation (duplicate CSS merged)
    - PASS 5D — Modal pattern audit (13 modals catalogued; refactor deferred)

    No functional rent-engine logic was modified.
    No behavioural changes introduced.

================================================================
KEY DECISIONS LOG
================================================================

2026-02-14  waiting_on stays "tenant" for missing_payment threads
    Escalation affects badge via needs_landlord_attention,
    NOT by flipping waiting_on. Tenant always holds
    responsibility for submission.

2026-02-14  needs_landlord_attention as uniform badge field
    Replaces waiting_on-based badge logic. All thread types
    use the same badge rule. payment_review threads mirror
    waiting_on transitions automatically.

2026-02-14  escalation_started_at stores current timestamp
    Stores the current timestamp when the system detects
    that the grace period has passed, not a calculated date.
    This is the actual detection time. If the landlord logs
    in on the 20th for a due date of the 5th, the escalation
    timestamp is the 20th (when detected), not the 7th
    (when it would have been detected with daily runs).

2026-02-14  No fortnightly escalation ticking
    Escalation is a one-time state transition. No recurring
    ticks, no last_escalation_at field, no periodic logging.

2026-02-14  Tracking boundary uses existing created_at
    tracking_start_date = max(lease_start_date, lease.created_at)
    No new stored field. Prevents false threads for months
    before the landlord started using the app.

2026-02-14  Reminder text is month-specific per thread
    Each thread logs its own month-specific reminder.
    Delivery consolidation deferred to external channel layer.
    No cross-thread message merging.

2026-02-14  System reminders built by dedicated function
    send_missing_payment_reminders() loads threads.json once,
    appends auto_reminder messages to qualifying threads, and
    saves once. This is a separate pipeline step from
    materialisation. Manual landlord reminders (future) will
    use add_message_to_thread() via separate route request.

2026-02-14  Phase 3 (First Month UI) moved before thread work
    Allows landlord to populate first_month fields end-to-end
    before any engine logic exists. Engine gets real data.

2026-02-18  Phase 3 Step 4 (prorated suggestion) complete
    Prorated amount suggestion displayed below First Month
    Amount input in Edit Mode. Computed via
    calculate_prorated_amount() only when start_day >
    due_day. Display-only — never saved or auto-filled.
    Uses explicit "is not none" check in template.

2026-02-18  Phase 4 Step 1 (thread schema extension) complete
    Extended ensure_thread_exists() with three optional params:
    expected_due_date, expected_amount, is_first_month.
    All default to None. Only included in thread dict when
    not None. No existing callers changed. No migration.
    Threads without new params remain identical 8-field structure.

2026-02-18  Phase 4 Step 2 (missing payment evaluator) complete
    Added evaluate_missing_payment_status(lease_data, year, month,
    today_date, payment_confirmations=None). Pure evaluator — no
    file writes, no thread creation. Combines
    get_rent_due_info_for_month() with compute_monthly_coverage()
    to decide if a missing_payment thread should exist. Accepts
    optional pre-loaded payment_confirmations to avoid repeated
    file reads in loops.

2026-02-18  Phase 6 (missing rent engine activation) complete
    Created materialise_missing_payment_threads(lease_group_id,
    lease_data) as sibling to materialise_system_threads().
    Called from dashboard loop after payment_review materialisation.
    Applies tracking boundary: max(lease_start_date, created_at).
    Skips drafts. Loads payments once, passes to evaluator.
    Iterates month-by-month, calls ensure_thread_exists() with
    topic_type="missing_payment", waiting_on="tenant", plus
    extended fields (expected_due_date, expected_amount,
    is_first_month). Idempotency via ensure_thread_exists().
    Tested: 5 missing_payment threads created across all leases.

2026-02-18  Phase 4 (thread schema completion) complete
    Added 4 fields to all threads: needs_landlord_attention,
    escalation_started_at, last_reminder_at,
    auto_reminders_suppressed. Defaults: False/None/None/False.
    Three locations updated: ensure_thread_exists() construction,
    materialise_system_threads() construction, _load_all_threads()
    backfill migration. Migration is idempotent, saves once only
    if changes detected. All 15 existing threads backfilled.
    No business logic changed — schema extension only.

2026-02-18  Phase 5 (badge simplification) complete
    Swapped badge filter from waiting_on == "landlord" to
    needs_landlord_attention is True in two functions:
    count_landlord_attention_threads() and
    get_attention_summary_for_lease(). Both still require
    status == "open". Badge shows 0 for all leases (correct —
    no thread has needs_landlord_attention set yet). Badges
    will reappear when escalation logic sets the flag.

2026-02-18  Phase 9 (auto-resolution) complete
    Created auto_resolve_missing_payment_threads(). Loads
    threads.json and payment_data.json once, resolves any open
    missing_payment thread where a matching rent confirmation
    exists (same lease_group_id, confirmation_type=="rent",
    matching period_year/period_month). Sets status="resolved",
    resolved_at=now, needs_landlord_attention=False. Leaves
    escalation_started_at as-is. Saves once if any resolved.
    Runs in dashboard flow after materialisation, before badge
    computation. Tested: confirmation added → thread resolved;
    no duplicates; idempotent on reload.

2026-02-18  Phase 7 (escalation) complete
    Created escalate_missing_payment_threads(). For each open
    missing_payment thread where today > expected_due_date + 2
    days and needs_landlord_attention is False, sets
    needs_landlord_attention=True and escalation_started_at=now.
    Guards: skips already-escalated, resolved, non-missing_payment.
    Never overwrites existing escalation_started_at. Single
    load/save. Added timedelta to module import. Runs in
    dashboard after auto-resolve, before badges. Tested: all 5
    threads escalated, badges show 1 per lease, timestamps
    unchanged on reload (idempotent).

2026-02-18  Phase 8 (automatic reminders) complete
    Created send_missing_payment_reminders(). For each open
    missing_payment thread where today > expected_due_date AND
    today <= expected_due_date + 2 days (grace period) AND
    needs_landlord_attention is False AND auto_reminders_suppressed
    is False AND last_reminder_at is None: appends a system message
    (actor="system", message_type="auto_reminder") with neutral
    reminder text including month/year from topic_ref. Sets
    last_reminder_at=now. Does NOT change needs_landlord_attention
    or escalation_started_at. Single load/save. Runs in dashboard
    flow after auto-resolve, before escalation. MONTH_NAMES lookup
    array added at module level. Deterministic lifecycle test
    (6 scenarios, 54 checks) verified: no action before due date,
    reminder on day 1-2, escalation on day 3, auto-resolve with
    payment during grace and after escalation, no duplicate
    reminders, idempotent on reload.

2026-02-14  Lock-after-due-date deferred
    Date-based field locking for first_month fields deferred
    to a later phase. Fields remain editable in Edit Mode
    for now.

================================================================
ARCHITECTURAL CONTEXT — THREAD ENGINE EXPANSION
(Do Not Implement During Current Build)
================================================================

DO NOT IMPLEMENT ANY OF THIS DURING THE CURRENT BUILD.

This section exists for two reasons:
1. So that future sessions understand the full picture
2. So that current design decisions don't accidentally
   conflict with what comes next

Everything below is ARCHITECTURAL CONTEXT and BEHAVIOURAL
CONTRACT — not implementation scope.

The current build scope remains: Rent Obligation & Missing
Payment Engine (Phases 1-10 above).

----------------------------------------------------------------
WHAT IS THE THREAD ENGINE?
----------------------------------------------------------------

Threads are the core tracking system in Mapmylease. Each
thread tracks one specific issue — like "rent is missing
for January" or "the landlord needs to review a payment."

Think of threads like individual case files. Each one:
- Tracks one issue from start to finish
- Contains a timeline of messages (who said what, when)
- Has a clear status: open (active) or resolved (done)
- Is permanent — never deleted, never edited after the fact

The Rent Engine we're building now is the FIRST automated
thread type. Once it's working and proven, the same
patterns will be reused for other thread types.

----------------------------------------------------------------
THREAD TYPES — FULL TAXONOMY
----------------------------------------------------------------

1) payment_review        — EXISTING, fully implemented
2) missing_payment (rent) — CURRENT BUILD
3) missing_payment (maint/utils) — FUTURE
4) renewal               — FUTURE
5) quarterly_review      — CONCEPTUAL

Only #2 is being implemented now.

----------------------------------------------------------------
HOW DIFFERENT THREAD TYPES COEXIST
----------------------------------------------------------------

Different thread types can exist for the same month.
Each thread is uniquely identified by topic_type + topic_ref.

Example — January 2026 rent:

  Timeline:
  Jan 6:  missing_payment thread created (rent overdue)
  Jan 20: Tenant submits payment
          → missing_payment thread auto-resolves
          → payment_review thread created (landlord review)

  Result: Two threads exist for "rent:2026-01":
  - missing_payment + rent:2026-01 (resolved)
  - payment_review + rent:2026-01 (open)

  This is correct. They track different stages:
  "rent was missing" then "rent was submitted, please review"

  Uniqueness rule: no duplicate OPEN threads for the same
  topic_type + topic_ref. Resolved threads never block
  new thread creation.

  Cross-thread isolation:
  Thread types are independent. No thread type may mutate,
  auto-resolve, suppress, or otherwise modify another
  thread type, except where explicitly defined (e.g.,
  missing_payment auto-resolves itself when payment exists).

================================================================
THREAD BEHAVIOUR CONTRACT (AUTHORITATIVE)
================================================================

This section defines how each thread type behaves.
It is a behavioural contract, not an implementation plan.

Unless explicitly changed in future, this is authoritative.

----------------------------------------------------------------
1) payment_review — EXISTING
----------------------------------------------------------------

WHAT IT DOES:
When a tenant submits a payment, this thread is created so
the landlord can review it. The landlord can acknowledge it
(closing the thread) or flag a concern (starting a
back-and-forth conversation with the tenant).

There is no automation here — no reminders, no escalation.
It's a simple review workflow.

Trigger:
    Tenant submits rent payment evidence.

Thread identity:
    topic_type = "payment_review"
    topic_ref = "rent:YYYY-MM"

Initial state:
    status = "open"
    waiting_on = "landlord"
    needs_landlord_attention = true
    Appears in attention badge and Action Console.

Behaviour:
    Landlord acknowledges → resolved, needs_landlord_attention = false
    Landlord flags issue  → waiting_on = "tenant", needs_landlord_attention = false
    Tenant replies        → waiting_on = "landlord", needs_landlord_attention = true
    Landlord replies      → waiting_on = "tenant", needs_landlord_attention = false

    add_message_to_thread() syncs needs_landlord_attention
    after every message (scoped to payment_review only).
    No escalation. No automatic reminders. No suppression logic.

Resolution:
    Only via landlord acknowledge action.

Status: Fully implemented. Updated 2026-02-20 to include
    attention integration.

----------------------------------------------------------------
2) missing_payment (rent) — CURRENT BUILD
----------------------------------------------------------------

WHAT IT DOES:
When rent is overdue, this thread tracks the missing payment,
sends reminders, and escalates if needed. It auto-resolves
when the tenant finally submits.

Unlike payment_review, responsibility NEVER shifts to the
landlord. The tenant always owes the action (submitting
payment). The landlord is notified via the badge after the
grace period, but waiting_on stays "tenant".

Trigger:
    Day after rent due date, if no submission exists.

Thread identity:
    topic_type = "missing_payment"
    topic_ref = "rent:YYYY-MM"

Initial state:
    status = "open"
    waiting_on = "tenant"
    needs_landlord_attention = false
    escalation_started_at = null
    last_reminder_at = null
    auto_reminders_suppressed = false

Grace period:
    2 days after due_date (hardcoded timedelta(days=2)).

Escalation rule:
    If today > due_date + 2 days:
        needs_landlord_attention = true
        escalation_started_at = now (current timestamp,
            set once, only if still null)

    One-time flip. Never modified again.
    Silent — no system message appended.

Reminder:
    One automatic reminder during days 1–2 after due date.
    Max 1 per thread (gated by last_reminder_at is null).
    message_type = "auto_reminder", actor = "system".
    Suppressed if auto_reminders_suppressed == true.
    No repeat cadence — single reminder only.

Important:
    waiting_on always remains "tenant"
    Escalation affects badge visibility only

Resolution:
    Auto-resolve when rent payment submission exists.

    Evaluation Order Guarantee:
        Auto-resolution must be evaluated before escalation
        or reminder logic in any evaluation cycle.
        A thread must never escalate or send a reminder
        for a month that has already been paid.

Coexistence:
    After tenant submits:
        missing_payment thread resolves
        payment_review thread opens
    Both threads may exist for the same month.

Status: Being implemented now (Phases 1-10).

----------------------------------------------------------------
3) missing_payment (maintenance & utilities) — FUTURE
----------------------------------------------------------------

WHAT IT DOES:
Same concept as rent, but with a completely different timing
model. Maintenance and utilities aren't due on a specific
day — they're expected sometime during the month.

Instead of the rent model (single reminder during 2-day
grace period), this uses monthly checkpoints: a mid-month
reminder and month-end escalation.

HOW IT DIFFERS FROM RENT:
- No specific due day (expected "during the month")
- No per-due-date grace period or reminder
- Mid-month reminder on the 15th instead
- Escalation at month-end instead of due + 2 days

Trigger:
    If expected monthly submission is missing.

Thread identity:
    topic_type = "missing_payment"
    topic_ref = "maintenance:YYYY-MM" or "utilities:YYYY-MM"

Cadence:
    1st-14th: Informational only. No badge. No escalation.

    15th: ONE consolidated automatic reminder covering ALL
          outstanding months (latest first). Includes visual
          urgency for items > 2 months overdue.

    Last day of month: Escalation activates for THAT
          month's thread. Badge increases. Landlord notified.
          NO automatic reminder sent on this day.

    On the 15th of each subsequent month, a consolidated
    reminder is sent covering all open maintenance threads
    whose months are still unresolved.

    IMPORTANT: Each month has its own independent thread.
    Each thread escalates exactly once at its own month-end.
    Escalation is always a one-time state change per thread.
    The monthly pattern means new threads go through their
    own escalation — not that existing threads re-escalate.

    Escalation field:
    Maintenance threads will use the same
    escalation_started_at field and follow the same
    one-time escalation invariant.

waiting_on:
    Always "tenant"

Reminder model:
    Consolidated per group in UI display.
    Separate backend threads per month.

Suppression:
    Stops automatic reminders only.
    Does not hide thread. Does not stop escalation.

Resolution:
    Auto-resolve on submission.

Status: Designed. Not yet implemented.

----------------------------------------------------------------
4) renewal — FUTURE
----------------------------------------------------------------

WHAT IT DOES:
When a lease is approaching its end date, this thread
prompts the landlord to think about renewal. It's a gentle,
persistent nudge — not an urgent alert.

Previously, renewal prompts were planned as a standalone
system with suppression logic in dashboard_prefs.json.
Making them threads means they use the same attention badge,
the same resolution model, and the same audit trail.
Resolving the thread IS the suppression.

Trigger:
    60 days before lease expiry.
    Exclusion: MUST NOT materialise for leases with an
    effective termination date before the lease end date.

Thread identity:
    topic_type = "renewal"
    topic_ref = lease_group_id

Initial state:
    waiting_on = "landlord"
    needs_landlord_attention = true

Reminder cadence:
    Every 14 days until:
        - Renewal uploaded, OR
        - Landlord confirms intention, OR
        - Landlord suppresses reminders

After expiry:
    Dashboard ribbon shows "Expired"
    Renewal reminders stop
    Thread remains open until explicitly resolved
    needs_landlord_attention remains true
        until the thread is resolved.

Resolution:
    On renewal upload or landlord confirmation.

Status: Designed. Not yet implemented.

----------------------------------------------------------------
5) quarterly_review — CONCEPTUAL
----------------------------------------------------------------

WHAT IT DOES:
A housekeeping mechanism that periodically surfaces threads
that have been open for a long time. If a missing_payment
thread has been open for 3+ months with no resolution, the
quarterly review would flag it for the landlord's attention.

HOW IT DIFFERS FROM OTHER TYPES:
This is a "meta" thread — it exists because OTHER threads
have been open too long, not because of a lease event. It
watches the health of the thread system itself, like a
periodic audit.

Trigger:
    System surfaces long-running open threads.

Behaviour:
    waiting_on = "landlord"
    needs_landlord_attention = true
    Does NOT auto-resolve other threads
    Does NOT modify or mutate referenced threads in any way
    Exists independently of the threads it references
    Informational only

Status: Conceptual only. Not yet designed in detail.

================================================================
GLOBAL INVARIANTS (ALL THREAD TYPES)
================================================================

These rules are non-negotiable. They apply to every thread
type — existing, current build, and future:

1) APPEND-ONLY
   Threads and messages are never deleted, never edited.
   Corrections are made by adding new messages.

2) NO MERGING
   Threads are never combined in storage. Grouping for
   display purposes is UI-only.

3) ESCALATION IS ONE-TIME
   escalation_started_at is set once and never modified.
   No recurring escalation ticks or periodic re-escalation.
   Each thread escalates independently and exactly once.

4) SUPPRESSION IS LIMITED
   auto_reminders_suppressed = true:
   - Stops automatic reminders ONLY
   - Does NOT hide the thread
   - Does NOT stop escalation
   - Does NOT resolve the thread
   - Does NOT affect the attention badge

5) BADGE = needs_landlord_attention
   Badge counts threads where needs_landlord_attention == true.
   Never derive badge visibility from waiting_on.

6) RESPONSIBILITY AND VISIBILITY ARE SEPARATE
   waiting_on = who needs to act (responsibility)
   needs_landlord_attention = show in badge (visibility)
   These must never be conflated.

7) IDEMPOTENT EVALUATION
   Reloading the dashboard repeatedly must never:
   - Duplicate threads
   - Duplicate reminders
   - Re-trigger escalation
   - Corrupt state

8) TRACKING BOUNDARY
   tracking_start_date = max(lease_start_date, lease.created_at)
   No thread type should create threads for months before
   the landlord started using the app.

9) FUNCTION-LEVEL LOAD / SAVE
   Each engine function loads threads.json independently,
   makes changes in memory, and saves once (only if it
   mutated state). The pipeline does NOT use a single-load
   model across the full cycle. See Section 10 invariants
   above for full description.

10) SCHEDULER-READY (TARGET — NOT YET IMPLEMENTED)
    All evaluation functions should accept a "today" parameter
    so they can be called by a background scheduler. Currently,
    they use datetime.now() internally and are called on
    dashboard load (Option A). Only evaluate_missing_payment_status()
    accepts a today_date parameter. The remaining pipeline
    functions (materialise, auto-resolve, remind, escalate)
    do not yet accept a today parameter. This must be added
    before migrating to a scheduler (Option B).

11) UNIQUENESS RULE
    Only ONE open thread may exist for a given
    lease_group_id + topic_type + topic_ref combination.
    For missing_payment: resolved threads do NOT block
    re-creation (checked via find_open_thread()).
    For payment_review: resolved threads DO block
    re-creation (checked via inline logic in
    materialise_system_threads() against all statuses).
    See PROJECT_CONTEXT.md → Thread Uniqueness Model.

12) QUARTERLY_REVIEW IS NON-MUTATING (CONCEPTUAL — NOT BUILT)
    quarterly_review is a CONCEPTUAL thread type not yet in the
    authoritative schema (see PROJECT_CONTEXT.md topic_type enum).
    If implemented, quarterly_review threads MUST NOT mutate or
    modify the threads they reference. They are informational
    only. They do not auto-resolve, auto-close, or alter
    other threads in any way.

13) THREADS REPRESENT OBLIGATIONS, NOT UI EVENTS
    A thread must be created only because a real-world
    obligation or condition exists (e.g., payment missing,
    renewal due). Threads must never be created purely
    because a user clicked something or because a UI state
    changed. UI actions may add messages to existing
    threads, but they must not create artificial thread
    types. This protects the architecture from UI-driven
    noise and ensures the thread model remains
    domain-driven.

14) REMINDERS DO NOT CREATE THREADS
    Reminders may only append messages to existing threads.
    They must never create new threads.
    Thread creation must always be driven by an underlying
    obligation or condition — never by reminder cadence
    logic.

================================================================
BUILD SEQUENCE AFTER RENT ENGINE
================================================================

Once the Rent Engine (Phases 1-10) is complete and stable:

Step 1: Maintenance & utilities missing_payment threads
        Same thread infrastructure, different cadence rules.
        Mid-month reminders, month-end escalation,
        consolidated reminder model.

Step 2: Renewal threads
        60-day pre-expiry trigger, 14-day reminder cadence.
        Auto-resolves on renewal upload.

Step 3: Extract common evaluation patterns
        Thread creation, escalation, reminders, and
        resolution follow the same shape across all types.
        Extract into reusable handler functions.

Step 4: Notification abstraction layer
        Prepare message delivery for WhatsApp/email/SMS
        without changing thread logic. The thread model
        already has channel, delivered_via, and external_ref
        fields ready for this.

Step 5: Background scheduler (Option B)
        Run evaluations daily without landlord login.
        Requires adding a "today" parameter to pipeline
        functions first (see invariant #10 — NOT YET
        IMPLEMENTED). Only evaluate_missing_payment_status()
        currently accepts today_date.

Each step builds on the previous.
The Rent Engine is the proving ground — if the architecture
works for rent (the most complex case), it works for all.

================================================================
END OF ARCHITECTURAL CONTEXT
================================================================

================================================================
DEPENDENCY MAP
================================================================

    Phase 1 -> Phase 2 -> Phase 3
        (Lease data model -> Helper -> First Month UI)

    Phase 4 -> Phase 5
        (Thread schema -> Badge)

    Both tracks merge at Phase 6

    Phase 6 -> Phase 7  (Escalation)
            -> Phase 8  (Reminders)
            -> Phase 9  (Auto-resolution)

    Phase 10 depends on all above

================================================================
CURRENT STATUS
================================================================

Phase 1 — COMPLETE (2026-02-18)
Phase 2 — COMPLETE (2026-02-18)
Phase 3 — COMPLETE (2026-02-18)
Phase 4 — COMPLETE (2026-02-18)
Phase 5 — COMPLETE (2026-02-18)
Phase 6 — COMPLETE (2026-02-18)
Phase 7 — COMPLETE (2026-02-18)
Phase 8 — COMPLETE (2026-02-18)
Phase 9 — COMPLETE (2026-02-18)
Phase 10 — IN PROGRESS (Action Console Architecture)

================================================================
END OF ACTIVE BUILD
================================================================
