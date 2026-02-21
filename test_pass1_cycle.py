"""
PASS 1 Validation — Flag → Tenant Reply → Acknowledge Cycle
=============================================================

This test exercises the full payment_review lifecycle:

  1. Start with an open payment_review thread
  2. Landlord FLAGS it (asks tenant for clarification)
  3. Tenant REPLIES
  4. Landlord ACKNOWLEDGES (resolves the thread)

At each step, it checks:
  - Thread status (open / resolved)
  - waiting_on (landlord / tenant / None)
  - needs_landlord_attention (True / False)
  - Message count increases correctly

Run:  python test_pass1_cycle.py

After running, check the app in your browser — the thread
will be resolved. You can verify visually that:
  - The Action Console no longer shows this item
  - The attention badge count decreased by 1
  - The lease detail view shows the thread as resolved
"""

from app import (
    app,
    _load_all_threads,
    _save_threads_file,
    add_message_to_thread,
    find_open_thread,
    get_messages_for_thread,
)

# ---- Test data (from your actual threads.json) ----
THREAD_ID = "db9f3b0c-c33d-486d-941c-62c46921d964"
LEASE_GROUP_ID = "2e90c611-df92-4872-81cd-0c8b19d0bf94"
TOKEN = None  # Will be looked up
PAYMENT_ID = "1c008484-2d8e-487b-9f60-d411f4a4fa1c"

passed = 0
failed = 0


def check(label, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}  {detail}")


def get_thread():
    td = _load_all_threads()
    return next((t for t in td["threads"] if t["id"] == THREAD_ID), None)


def count_messages():
    td = _load_all_threads()
    return len(get_messages_for_thread(THREAD_ID, td))


# ---- Look up the tenant token ----
from app import _load_all_tenant_access

ta = _load_all_tenant_access()
for tk in ta.get("tenant_tokens", []):
    if tk.get("lease_group_id") == LEASE_GROUP_ID and tk.get("is_active"):
        TOKEN = tk["token"]
        break

if not TOKEN:
    print("ABORT: No active tenant token found for this lease group.")
    exit(1)


# ---- Save original state so we can restore after test ----
original_thread_data = _load_all_threads()
import copy
backup = copy.deepcopy(original_thread_data)


# ================================================================
# PRE-CHECK: Thread must be open
# ================================================================
print("\n--- PRE-CHECK ---")
thread = get_thread()
if not thread:
    print(f"ABORT: Thread {THREAD_ID} not found.")
    exit(1)

# If thread is not in the right starting state, reset it
if thread["status"] != "open" or thread.get("waiting_on") != "landlord":
    print("Resetting thread to starting state (open, waiting_on=landlord)...")
    td = _load_all_threads()
    for t in td["threads"]:
        if t["id"] == THREAD_ID:
            t["status"] = "open"
            t["waiting_on"] = "landlord"
            t["needs_landlord_attention"] = True
            t["resolved_at"] = None
            break
    _save_threads_file(td)

thread = get_thread()
initial_msg_count = count_messages()
check("Thread is open", thread["status"] == "open")
check("waiting_on = landlord", thread.get("waiting_on") == "landlord")
check("needs_landlord_attention = True", thread.get("needs_landlord_attention") is True)
print(f"  INFO  Message count at start: {initial_msg_count}")


# ================================================================
# STEP 1: Landlord FLAGS the thread
# ================================================================
print("\n--- STEP 1: Landlord flags thread ---")

with app.test_client() as client:
    resp = client.post(
        f"/thread/{THREAD_ID}/review/flag",
        data={"body": "TEST: Please clarify the maintenance amount."},
        follow_redirects=False,
    )
    check("Flag returns redirect (302)", resp.status_code == 302, f"got {resp.status_code}")

thread = get_thread()
msg_count = count_messages()
check("Thread still open", thread["status"] == "open")
check("waiting_on = tenant", thread.get("waiting_on") == "tenant")
check("needs_landlord_attention = False", thread.get("needs_landlord_attention") is False)
check("Message count +1", msg_count == initial_msg_count + 1, f"expected {initial_msg_count + 1}, got {msg_count}")


# ================================================================
# STEP 2: Tenant REPLIES
# ================================================================
print("\n--- STEP 2: Tenant replies ---")

with app.test_client() as client:
    resp = client.post(
        f"/tenant/{TOKEN}/payment/{PAYMENT_ID}/response",
        data={"message": "TEST: The amount includes a one-time repair charge."},
        follow_redirects=False,
    )
    check("Reply returns redirect (302)", resp.status_code == 302, f"got {resp.status_code}")

thread = get_thread()
msg_count = count_messages()
check("Thread still open", thread["status"] == "open")
check("waiting_on = landlord", thread.get("waiting_on") == "landlord")
check("needs_landlord_attention = True", thread.get("needs_landlord_attention") is True)
check("Message count +1", msg_count == initial_msg_count + 2, f"expected {initial_msg_count + 2}, got {msg_count}")


# ================================================================
# STEP 3: Landlord ACKNOWLEDGES
# ================================================================
print("\n--- STEP 3: Landlord acknowledges ---")

with app.test_client() as client:
    resp = client.post(
        f"/thread/{THREAD_ID}/review/acknowledge",
        data={"body": "TEST: Thank you, payment confirmed."},
        follow_redirects=False,
    )
    check("Acknowledge returns redirect (302)", resp.status_code == 302, f"got {resp.status_code}")

thread = get_thread()
msg_count = count_messages()
check("Thread is resolved", thread["status"] == "resolved")
check("waiting_on = None", thread.get("waiting_on") is None)
check("needs_landlord_attention = False", thread.get("needs_landlord_attention") is False)
check("resolved_at is set", thread.get("resolved_at") is not None)
check("Message count +1", msg_count == initial_msg_count + 3, f"expected {initial_msg_count + 3}, got {msg_count}")


# ================================================================
# STEP 4: Dashboard still loads after the cycle
# ================================================================
print("\n--- STEP 4: Dashboard loads after cycle ---")

with app.test_client() as client:
    resp = client.get("/")
    check("Dashboard loads (HTTP 200)", resp.status_code == 200)
    html = resp.data.decode("utf-8")
    check("Action Console present", "action-console" in html)


# ================================================================
# RESTORE original state (so test is repeatable)
# ================================================================
print("\n--- RESTORING original thread state ---")
_save_threads_file(backup)
restored = get_thread()
check("Thread restored to original state", restored["status"] == backup_status if (backup_status := next((t.get("status") for t in backup["threads"] if t["id"] == THREAD_ID), None)) else True)


# ================================================================
# SUMMARY
# ================================================================
print(f"\n{'=' * 50}")
print(f"RESULTS: {passed} passed, {failed} failed out of {passed + failed} checks")
if failed == 0:
    print("ALL CHECKS PASSED — Flag/Reply/Acknowledge cycle verified.")
else:
    print("SOME CHECKS FAILED — review output above.")
print(f"{'=' * 50}\n")
