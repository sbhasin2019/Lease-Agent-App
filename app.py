"""
Easemylease - Main Application
A simple local web app to extract and display lease information.
"""

import os
import json
from datetime import datetime
import re
import calendar
import uuid
import secrets
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from werkzeug.utils import secure_filename

# Text extraction imports
from pypdf import PdfReader
import pytesseract
from pdf2image import convert_from_path
from PIL import Image

# AI extraction (optional)
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

app = Flask(__name__)
app.secret_key = "dev-secret-key"  # Required for flash messages


@app.template_filter('days_until')
def days_until_filter(date_str):
    """Calculate days remaining until a date."""
    if not date_str:
        return None
    try:
        end_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        today = datetime.now().date()
        return (end_date - today).days
    except ValueError:
        return None

@app.template_filter('format_money')
def format_money_filter(value):
    """Format a numeric value with commas for display (e.g. 185000 → 185,000)."""
    if value is None:
        return '—'
    try:
        num = float(value)
        if num == int(num):
            return f"{int(num):,}"
        return f"{num:,.2f}"
    except (ValueError, TypeError):
        return str(value)

@app.template_filter('format_date')
def format_date_filter(date_str):
    """Format an ISO date/datetime string to human-readable (e.g. '5 Feb 2026')."""
    if not date_str:
        return '—'
    try:
        dt = datetime.fromisoformat(date_str)
        return dt.strftime("%-d %b %Y")
    except (ValueError, TypeError):
        return str(date_str)

# Make datetime.now available in templates (used for year dropdowns)
app.jinja_env.globals["now"] = datetime.now

# Upload configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Create uploads directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# In-memory storage for uploads
uploads = {}


def allowed_file(filename):
    """Check if file has an allowed extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ----------------------------------------------------------------
# Proof file upload infrastructure (Phase 1 Step 3)
# ----------------------------------------------------------------
PROOF_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "proofs")
os.makedirs(PROOF_UPLOAD_FOLDER, exist_ok=True)

# Explicit allowed extensions for SERVING proof files.
# Kept separate from ALLOWED_EXTENSIONS so upload and serving
# rules remain independent.
PROOF_ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}


def save_proof_file(lease_group_id, payment_id, file):
    """Save a proof file to uploads/proofs/{lease_group_id}/.

    Files are immutable once written — never overwritten or deleted.

    Args:
        lease_group_id: UUID string of the lease group
        payment_id: UUID string of the payment confirmation
        file: Werkzeug FileStorage object from form upload

    Returns:
        tuple: (relative_path, None) on success,
               (None, error_message) on failure
    """
    if not file or not file.filename:
        return None, "No file provided"

    if not allowed_file(file.filename):
        return None, "File type not allowed"

    original_name = secure_filename(file.filename)
    if not original_name:
        return None, "Invalid filename"

    # Build directory: uploads/proofs/{lease_group_id}/
    lease_proof_dir = os.path.join(PROOF_UPLOAD_FOLDER, lease_group_id)
    os.makedirs(lease_proof_dir, exist_ok=True)

    # Build filename: {payment_id}_{original_name}
    safe_name = f"{payment_id}_{original_name}"
    full_path = os.path.join(lease_proof_dir, safe_name)

    # Never overwrite existing files (immutability rule)
    if os.path.exists(full_path):
        return None, "File already exists"

    file.save(full_path)

    # Return relative path for JSON storage (relative to uploads/)
    relative_path = os.path.join("proofs", lease_group_id, safe_name)
    return relative_path, None


def extract_text_from_image(file_path):
    """Extract text from image using OCR."""
    try:
        image = Image.open(file_path)
        text = pytesseract.image_to_string(image)
        result = text.strip() if text.strip() else None
        print(f"[DIAG] Image OCR extraction: {len(result) if result else 0} chars")
        if result:
            print(f"[DIAG] First 500 chars (image): {result[:500]}")
        return result
    except Exception as e:
        print(f"Image OCR error: {e}")
        return None


def select_preview_page(page_texts):
    """Select the best page for preview, avoiding stamp/cover pages."""
    if not page_texts:
        return None

    # Keywords indicating actual lease content
    lease_keywords = [
        "parties", "lease", "agreement", "between",
        "lessor", "lessee", "tenant", "landlord"
    ]

    # Keywords indicating stamp/cover pages to skip
    skip_keywords = [
        "stamp duty", "e-stamp", "stamp", "certificate",
        "government", "registration"
    ]

    for page_text in page_texts:
        if not page_text:
            continue

        text_lower = page_text.lower()

        # Check for lease keywords
        has_lease_keyword = any(kw in text_lower for kw in lease_keywords)

        # Check for skip keywords
        has_skip_keyword = any(kw in text_lower for kw in skip_keywords)

        # Select this page if it has lease content and isn't a stamp page
        if has_lease_keyword and not has_skip_keyword:
            return page_text

    # Fallback to first page
    return page_texts[0] if page_texts else None


def extract_text_from_pdf(file_path):
    """Extract text from PDF, with OCR fallback for scanned documents.

    Returns:
        tuple: (full_text, page_texts) where page_texts is a list of per-page strings
    """
    print(f"[DIAG] extract_text_from_pdf called for: {file_path}", flush=True)
    try:
        # First try direct text extraction
        reader = PdfReader(file_path)
        page_texts = []
        for page in reader.pages:
            page_text = page.extract_text()
            page_texts.append(page_text.strip() if page_text else "")

        full_text = "\n".join(page_texts)

        # If we got meaningful text, return it
        if full_text.strip():
            print(f"[DIAG] PDF direct extraction: {len(page_texts)} pages", flush=True)
            for i, pt in enumerate(page_texts):
                print(f"[DIAG]   Page {i+1}: {len(pt)} chars", flush=True)
            print(f"[DIAG] Total extracted: {len(full_text.strip())} chars", flush=True)
            print(f"[DIAG] First 500 chars: {full_text.strip()[:500]}", flush=True)
            return full_text.strip(), page_texts

        # Fallback: OCR for scanned PDFs
        print("No embedded text found, attempting OCR...")
        images = convert_from_path(file_path)
        page_texts = []
        for image in images:
            page_text = pytesseract.image_to_string(image)
            page_texts.append(page_text.strip() if page_text else "")

        full_text = "\n".join(page_texts)
        print(f"[DIAG] OCR extraction: {len(page_texts)} pages", flush=True)
        for i, pt in enumerate(page_texts):
            print(f"[DIAG]   Page {i+1}: {len(pt)} chars", flush=True)
        total_chars = len(full_text.strip()) if full_text.strip() else 0
        print(f"[DIAG] Total OCR extracted: {total_chars} chars", flush=True)
        if full_text.strip():
            print(f"[DIAG] First 500 chars (OCR): {full_text.strip()[:500]}", flush=True)
        return (full_text.strip() if full_text.strip() else None, page_texts)

    except Exception as e:
        print(f"PDF extraction error: {e}")
        return None, []


def extract_text(file_path, mimetype):
    """Extract text based on file type.

    Returns:
        tuple: (full_text, page_texts) for preview selection
    """
    if mimetype == "application/pdf":
        return extract_text_from_pdf(file_path)
    elif mimetype in ["image/png", "image/jpeg"]:
        text = extract_text_from_image(file_path)
        # Single-page image: return as one-element list
        return text, [text] if text else []
    return None, []


def create_preview(text, max_length=300):
    """Create a truncated preview of extracted text."""
    if not text:
        return None
    # Normalize whitespace
    text = " ".join(text.split())
    if len(text) <= max_length:
        return text
    # Truncate at word boundary
    return text[:max_length].rsplit(" ", 1)[0] + "..."


def ai_extract_lease_fields(full_text):
    """Use Claude AI to extract lease fields from text.

    Returns:
        dict with extracted fields, or None on any failure
    """
    if not ANTHROPIC_AVAILABLE:
        print("AI extraction skipped: anthropic package not installed")
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("AI extraction skipped: ANTHROPIC_API_KEY not set")
        return None

    if not full_text or not full_text.strip():
        print("AI extraction skipped: no text provided")
        return None

    try:
        client = anthropic.Anthropic(api_key=api_key)

        prompt = f"""You are a lease document analyzer. Extract the following fields from this lease document text.

IMPORTANT RULES:
- Be conservative: only extract values you are confident about
- If a field is unclear, ambiguous, or not found, use null
- For dates, use YYYY-MM-DD format
- For monetary values, extract the number only (no currency symbols)
- Provide evidence (a short quote from the text) for each extracted value
- The "page" field should be null unless you can determine it from context
- For rent_due_day: extract the day of month (1-31) when rent is due. Look for phrases like "due on the 1st", "payable by the 15th", "on or before the first day", etc.

LOCK-IN PERIOD RULES:
- Extract the lock-in period as a number of MONTHS only
- Look for phrases like "lock-in period", "minimum term", "cannot terminate before", "committed for"
- Convert years to months if needed (e.g., "1 year lock-in" = 12)
- If not explicitly mentioned, use null — do NOT infer or guess

RENT ESCALATION RULES:
- Extract the rent escalation percentage ONLY if explicitly stated
- Look for phrases like "rent shall increase by X%", "escalation of X%", "annual increment of X%", "X% increase upon renewal"
- Extract ONLY the percentage number (e.g., 5 for "5%")
- This is informational only — do NOT calculate or apply it
- If not explicitly mentioned, use null — do NOT infer or guess

LEASE NICKNAME RULES:
- Generate a short, human-friendly nickname (2-6 words)
- Prefer format: "[Location/Building] – [Type] [Unit#]" when unit number is available
- Include flat/unit/apartment number if clearly stated in the document (e.g., "Flat 401", "Unit 12B")
- Good examples: "Bandra West – Flat 302", "DLF Phase 3 – Office 5A", "Prestige Tower – Apartment 1201"
- If no unit number found, omit it: "Bandra West – Apartment", "Prestige Tower – Commercial"
- If location is unclear, use generic fallback: "Residential Lease" or "Commercial Lease"
- Only include unit numbers explicitly mentioned in the document — NEVER guess or hallucinate
- If you cannot determine ANY useful identifying info, use null

Return ONLY valid JSON matching this exact schema (no other text):

{{
  "lease_nickname": null,
  "lessor_name": {{ "value": null, "page": null, "evidence": null }},
  "lessee_name": {{ "value": null, "page": null, "evidence": null }},
  "start_date": {{ "value": null, "page": null, "evidence": null }},
  "end_date": {{ "value": null, "page": null, "evidence": null }},
  "monthly_rent": {{ "value": null, "page": null, "evidence": null }},
  "rent_due_day": {{ "value": null, "page": null, "evidence": null }},
  "security_deposit": {{ "value": null, "page": null, "evidence": null }},
  "lock_in_duration_months": {{ "value": null, "page": null, "evidence": null }},
  "rent_escalation_percent": {{ "value": null, "page": null, "evidence": null }},
  "confidence_notes": null
}}

LEASE DOCUMENT TEXT:
{full_text}"""

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        # Extract the text response
        response_text = message.content[0].text.strip()

        # Handle potential markdown code blocks
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            # Remove first line (```json) and last line (```)
            response_text = "\n".join(lines[1:-1])

        result = json.loads(response_text)
        return result

    except anthropic.APIError as e:
        print(f"AI extraction API error: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"AI extraction JSON parse error: {e}")
        return None
    except Exception as e:
        print(f"AI extraction unexpected error: {e}")
        return None


def _save_lease_file(data):
    """Atomically save lease data to JSON file.

    Returns:
        bool: True on success, False on failure
    """
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lease_data.json")
    tmp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lease_data.tmp")

    try:
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, json_path)
        return True
    except (IOError, OSError) as e:
        print(f"[WARNING] Failed to save lease_data.json: {e}")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return False


# ----------------------------------------------------------------
# PAYMENT CONFIRMATION SCHEMA (Phase 1 — LOCKED & AUTHORITATIVE)
# ----------------------------------------------------------------
# Each record in payment_data.json["confirmations"] follows this
# structure. This schema is locked. Do NOT add, remove, or rename
# fields without explicit scope approval.
#
# {
#   "id":                       str (uuid4),
#   "lease_group_id":           str (uuid4, links to lease group),
#   "confirmation_type":        "rent" | "maintenance" | "utilities",
#   "period_month":             int (1–12),
#   "period_year":              int (YYYY),
#   "amount_agreed":            number | null (rent only; null for others),
#   "amount_declared":          number (required, positive),
#   "tds_deducted":             number | null (null ≠ 0),
#   "date_paid":                str (ISO date YYYY-MM-DD) | null,
#   "proof_files":              list of str (relative file paths),
#   "verification_status":      "unverified" (ALWAYS in Phase 1),
#   "disclaimer_acknowledged":  str (ISO timestamp, required),
#   "submitted_at":             str (ISO timestamp, server-generated),
#   "submitted_via":            "tenant_link" | "landlord_manual",
#   "notes":                    str | null
# }
#
# Rules:
# - The confirmations list is append-only: new records are added,
#   existing records are NEVER modified or deleted
# - Every record is frozen at creation — no field is changed after
#   writing, including proof_files
# - Corrections or missing proof: submit a NEW record
# - Multiple submissions per month are allowed
# - verification_status is always "unverified" in Phase 1
# - amount_agreed comes from the lease; amount_declared from tenant
# - Only "rent" type uses amount_agreed; others are declaration-only
# - "Submitted" or "declared" never means "verified"
# - tds_deducted: null = not provided; 0 = explicitly no TDS
# - Period is determined solely by (period_month, period_year),
#   NOT by date_paid or submitted_at
# ----------------------------------------------------------------

# ----------------------------------------------------------------
# TENANT TOKEN SCHEMA (Phase 1 — LOCKED & AUTHORITATIVE)
# ----------------------------------------------------------------
# Each record in tenant_access.json["tenant_tokens"] follows this
# structure. This schema is locked. Do NOT add, remove, or rename
# fields without explicit scope approval.
#
# {
#   "token":                    str (secrets.token_urlsafe(32), ~43 chars),
#   "lease_group_id":           str (uuid4, links to lease group),
#   "is_active":                bool (mutable — only access control field),
#   "issued_at":                str (ISO timestamp),
#   "revoked_at":               str (ISO timestamp) | null (write-once),
#   "revoked_reason":           str | null (write-once),
#   "last_used_at":             str (ISO timestamp) | null (mutable)
# }
#
# Rules:
# - token string IS the identifier (no separate id field)
# - Tokens are bound to lease_group_id (survive renewals)
# - At most ONE active token per lease_group_id at any time
# - Landlord can revoke and regenerate tokens
# - If tenant changes on renewal, landlord is prompted to decide
# - Revoking a token NEVER deletes payment history
# - Token validity: is_active == true (lease expiry does NOT affect validity in Phase 1)
# - Anyone with the token can submit (no identity verification)
# - Only is_active and last_used_at are mutable after creation
# - revoked_at and revoked_reason are write-once (set at revocation)
# ----------------------------------------------------------------


def _load_all_payments():
    """Load the full payment confirmation collection from JSON file.

    Returns:
        dict: {"confirmations": [...]} structure,
              or {"confirmations": []} if file is missing or invalid
    """
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "payment_data.json")

    if not os.path.exists(json_path):
        return {"confirmations": []}

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            content = f.read()

        if not content.strip():
            return {"confirmations": []}

        data = json.loads(content)
        return data

    except json.JSONDecodeError:
        return {"confirmations": []}
    except IOError:
        return {"confirmations": []}


def _save_payment_file(data):
    """Atomically save payment data to JSON file.

    Returns:
        bool: True on success, False on failure
    """
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "payment_data.json")
    tmp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "payment_data.tmp")

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, json_path)
        return True
    except (IOError, OSError):
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return False


def _load_all_tenant_access():
    """Load the full tenant access token collection from JSON file.

    Returns:
        dict: {"tenant_tokens": [...]} structure,
              or {"tenant_tokens": []} if file is missing or invalid
    """
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tenant_access.json")

    if not os.path.exists(json_path):
        return {"tenant_tokens": []}

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            content = f.read()

        if not content.strip():
            return {"tenant_tokens": []}

        data = json.loads(content)
        return data

    except json.JSONDecodeError:
        return {"tenant_tokens": []}
    except IOError:
        return {"tenant_tokens": []}


def _save_tenant_access_file(data):
    """Atomically save tenant access data to JSON file.

    Returns:
        bool: True on success, False on failure
    """
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tenant_access.json")
    tmp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tenant_access.tmp")

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, json_path)
        return True
    except (IOError, OSError):
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return False


def _load_all_landlord_reviews():
    """Load the full landlord review collection from JSON file.

    Returns:
        dict: {"reviews": [...]} structure,
              or {"reviews": []} if file is missing or invalid
    """
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "landlord_review_data.json")

    if not os.path.exists(json_path):
        return {"reviews": []}

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            content = f.read()

        if not content.strip():
            return {"reviews": []}

        data = json.loads(content)
        return data

    except json.JSONDecodeError:
        return {"reviews": []}
    except IOError:
        return {"reviews": []}


def _save_landlord_review_file(data):
    """Atomically save landlord review data to JSON file.

    Returns:
        bool: True on success, False on failure
    """
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "landlord_review_data.json")
    tmp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "landlord_review_data.tmp")

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, json_path)
        return True
    except (IOError, OSError):
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return False


def _load_all_terminations():
    """Load the full termination event collection from JSON file.

    Returns:
        dict: {"terminations": [...]} structure,
              or {"terminations": []} if file is missing or invalid
    """
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "termination_data.json")

    if not os.path.exists(json_path):
        return {"terminations": []}

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            content = f.read()

        if not content.strip():
            return {"terminations": []}

        data = json.loads(content)
        return data

    except json.JSONDecodeError:
        return {"terminations": []}
    except IOError:
        return {"terminations": []}


def _save_termination_file(data):
    """Atomically save termination data to JSON file.

    Returns:
        bool: True on success, False on failure
    """
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "termination_data.json")
    tmp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "termination_data.tmp")

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, json_path)
        return True
    except (IOError, OSError):
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return False


def get_termination_for_lease(lease_id):
    """Look up whether a specific lease version has been terminated.

    Args:
        lease_id: The UUID string of a specific lease version (not group)

    Returns:
        dict: The termination event record if found, or None
              At most one termination event exists per lease version.
    """
    if not lease_id:
        return None
    data = _load_all_terminations()
    for t in data.get("terminations", []):
        if t.get("lease_id") == lease_id:
            return t
    return None


def generate_tenant_token(lease_group_id):
    """Generate a new tenant access token for a lease group.

    Rules:
    - lease_group_id must exist in lease_data.json
    - At most ONE active token per lease_group_id
    - If an active token already exists, FAILS (does not auto-revoke)

    Returns:
        dict: {"success": True, "token_record": {...}} or
              {"success": False, "error": "..."}
    """
    # Verify lease_group_id exists
    lease_data = _load_all_leases()
    lease_exists = any(
        lease.get("lease_group_id") == lease_group_id
        for lease in lease_data.get("leases", [])
    )
    if not lease_exists:
        return {"success": False, "error": "lease_group_not_found"}

    # Check for existing active token
    access_data = _load_all_tenant_access()
    tokens = access_data.get("tenant_tokens", [])
    for t in tokens:
        if t.get("lease_group_id") == lease_group_id and t.get("is_active"):
            return {"success": False, "error": "active_token_exists"}

    # Create new token record (matches locked schema exactly)
    token_record = {
        "token": secrets.token_urlsafe(32),
        "lease_group_id": lease_group_id,
        "is_active": True,
        "issued_at": datetime.now().isoformat(),
        "revoked_at": None,
        "revoked_reason": None,
        "last_used_at": None,
    }

    tokens.append(token_record)
    access_data["tenant_tokens"] = tokens
    saved = _save_tenant_access_file(access_data)

    if not saved:
        return {"success": False, "error": "save_failed"}

    return {"success": True, "token_record": token_record}


def validate_token(token):
    """Validate a tenant access token. Read-only, no side effects.

    A token is valid if and only if is_active == true.
    Does NOT check lease data or lease expiry.

    Returns:
        dict: {"valid": True, "lease_group_id": "...", "token_record": {...}} or
              {"valid": False, "reason": "not_found" | "revoked" | "inactive"}
    """
    access_data = _load_all_tenant_access()
    tokens = access_data.get("tenant_tokens", [])

    for t in tokens:
        if t.get("token") == token:
            if t.get("is_active"):
                return {
                    "valid": True,
                    "lease_group_id": t["lease_group_id"],
                    "token_record": t,
                }
            # Inactive — determine reason
            if t.get("revoked_at") is not None:
                return {"valid": False, "reason": "revoked"}
            return {"valid": False, "reason": "inactive"}

    return {"valid": False, "reason": "not_found"}


def revoke_tenant_token(token, reason=None):
    """Revoke a tenant access token. Landlord-initiated only.

    Rules:
    - Sets is_active = false
    - Sets revoked_at (write-once)
    - revoked_reason is optional (may be null)
    - NEVER deletes or alters payment history

    Returns:
        dict: {"success": True, "token_record": {...}} or
              {"success": False, "error": "..."}
    """
    access_data = _load_all_tenant_access()
    tokens = access_data.get("tenant_tokens", [])

    for t in tokens:
        if t.get("token") == token:
            if not t.get("is_active"):
                return {"success": False, "error": "already_revoked"}

            t["is_active"] = False
            t["revoked_at"] = datetime.now().isoformat()
            t["revoked_reason"] = reason

            saved = _save_tenant_access_file(access_data)
            if not saved:
                return {"success": False, "error": "save_failed"}

            return {"success": True, "token_record": t}

    return {"success": False, "error": "token_not_found"}


def get_active_token_for_lease_group(lease_group_id):
    """Fetch the active token for a lease group, if one exists.

    Returns:
        dict: The token record, or None if no active token exists.
    """
    access_data = _load_all_tenant_access()
    tokens = access_data.get("tenant_tokens", [])

    for t in tokens:
        if t.get("lease_group_id") == lease_group_id and t.get("is_active"):
            return t

    return None


def get_all_tokens_for_lease_group(lease_group_id):
    """Fetch all tokens (active and revoked) for a lease group.

    Returns:
        list: All token records for this lease group, newest first.
    """
    access_data = _load_all_tenant_access()
    tokens = access_data.get("tenant_tokens", [])
    matching = [t for t in tokens if t.get("lease_group_id") == lease_group_id]
    matching.sort(key=lambda t: t.get("issued_at", ""), reverse=True)
    return matching


def get_payments_for_lease_group(lease_group_id):
    """Fetch all payment confirmations for a lease group. Read-only.

    Returns:
        list: Confirmation records, newest first.
    """
    payment_data = _load_all_payments()
    confirmations = payment_data.get("confirmations", [])
    matching = [c for c in confirmations if c.get("lease_group_id") == lease_group_id]
    matching.sort(key=lambda c: c.get("submitted_at", ""), reverse=True)
    return matching


def _normalize_event(record):
    """Normalize a review/event record to the Phase 2 schema.

    Maps old field names to new:
      reviewed_at → created_at
      review_type → event_type
      internal_note → message
    Adds defaults for missing fields:
      actor = "landlord"
      attachments = []
    Passes through new-format records unchanged.
    """
    normalized = dict(record)
    if "reviewed_at" in normalized and "created_at" not in normalized:
        normalized["created_at"] = normalized.pop("reviewed_at")
    if "review_type" in normalized and "event_type" not in normalized:
        normalized["event_type"] = normalized.pop("review_type")
    if "internal_note" in normalized and "message" not in normalized:
        normalized["message"] = normalized.pop("internal_note")
    if "actor" not in normalized:
        normalized["actor"] = "landlord"
    if "attachments" not in normalized:
        normalized["attachments"] = []
    return normalized


def get_events_for_lease_group(lease_group_id):
    """Fetch all events for a lease group, normalized. Read-only.

    Returns:
        list: Event records, newest first.
    """
    review_data = _load_all_landlord_reviews()
    reviews = review_data.get("reviews", [])
    matching = [_normalize_event(r) for r in reviews
                if r.get("lease_group_id") == lease_group_id]
    matching.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return matching


def get_events_for_payment(payment_id):
    """Fetch all events for a specific payment, normalized. Read-only.

    Returns:
        list: Event records, newest first.
    """
    review_data = _load_all_landlord_reviews()
    reviews = review_data.get("reviews", [])
    matching = [_normalize_event(r) for r in reviews
                if r.get("payment_id") == payment_id]
    matching.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return matching


def get_conversation_state(events):
    """Compute conversation state from a list of events for one payment.

    Args:
        events: List of normalized event records (any sort order).

    Returns:
        dict: {
            "open": bool,
            "thread": [events in the active/latest conversation, oldest first]
        }
    """
    if not events:
        return {"open": False, "thread": []}

    # Sort oldest first to walk chronologically
    chronological = sorted(events, key=lambda e: e.get("created_at", ""))

    # Find the latest "flagged" event
    latest_flag_idx = None
    for i in range(len(chronological) - 1, -1, -1):
        if chronological[i].get("event_type") == "flagged":
            latest_flag_idx = i
            break

    if latest_flag_idx is None:
        return {"open": False, "thread": []}

    # Thread = everything from the latest flag onward
    thread = chronological[latest_flag_idx:]

    # Conversation is open unless a closing event exists after the flag
    is_open = True
    for event in thread[1:]:
        if event.get("event_type") in ("acknowledged", "noted"):
            is_open = False
            break

    return {"open": is_open, "thread": thread}


def _load_all_leases():
    """Load the full lease collection from JSON file.

    Returns:
        dict: {"leases": [...]} structure, or {"leases": []} if none
    """
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lease_data.json")

    if not os.path.exists(json_path):
        return {"leases": []}

    try:
        with open(json_path, "r") as f:
            content = f.read()

        if not content.strip():
            return {"leases": []}

        data = json.loads(content)

        # Check if this is old single-lease format (no "leases" key)
        if "leases" not in data:
            # Migrate old format to new structure
            print("[INFO] Migrating single-lease data to multi-lease format...")
            old_lease = data
            old_lease["id"] = str(uuid.uuid4())
            old_lease["created_at"] = old_lease.get("saved_at", datetime.now().isoformat())
            old_lease["updated_at"] = old_lease.get("saved_at", datetime.now().isoformat())
            new_data = {"leases": [old_lease]}
            data = new_data

        # Migrate any leases missing versioning fields or new structure
        migrated = False
        for lease in data.get("leases", []):
            # Migrate versioning fields (existing migration)
            if _migrate_lease_versioning(lease):
                migrated = True
            # Migrate to new nested structure
            if _migrate_lease_to_new_structure(lease):
                migrated = True
            # Add lock-in and renewal fields to existing leases
            if _migrate_lease_add_lock_in_and_renewal_fields(lease):
                migrated = True
            # Add expected payment categories
            if _migrate_lease_add_expected_payments(lease):
                migrated = True
            # Add expected payment confirmation flag
            if _migrate_lease_add_confirmation_flag(lease):
                migrated = True

        # Save if any migrations occurred
        if migrated:
            print("[INFO] Migrated leases to new structure...")
            _save_lease_file(data)

        return data

    except json.JSONDecodeError as e:
        print(f"[WARNING] lease_data.json contains invalid JSON: {e}")
        return {"leases": []}
    except IOError as e:
        print(f"[WARNING] Could not read lease_data.json: {e}")
        return {"leases": []}


def _migrate_lease_versioning(lease):
    """Add versioning fields to a lease if missing.

    Migration rules:
    - lease_group_id = lease.id (each existing lease becomes its own group)
    - version = 1
    - is_current = True

    Returns:
        bool: True if migration was applied, False if already versioned
    """
    if "lease_group_id" in lease:
        return False  # Already has versioning

    lease["lease_group_id"] = lease.get("id")
    lease["version"] = 1
    lease["is_current"] = True
    return True


def _migrate_lease_to_new_structure(lease):
    """Migrate a lease from flat structure to nested structure.

    Returns True if migration was performed, False if already migrated.
    """
    # Check if already migrated (has 'current_values' key)
    if "current_values" in lease:
        return False

    # Extract existing values
    field_names = [
        "lease_nickname", "lessor_name", "lessee_name",
        "lease_start_date", "lease_end_date",
        "monthly_rent", "security_deposit", "rent_due_day"
    ]

    # Build current_values from flat fields
    current_values = {}
    for field in field_names:
        current_values[field] = lease.pop(field, None)

    # Add lock-in period (new field)
    current_values["lock_in_period"] = {
        "duration_months": None
    }

    # Add renewal terms (new field)
    current_values["renewal_terms"] = {
        "rent_escalation_percent": None
    }

    # Build source_document from source_filename
    source_filename = lease.pop("source_filename", None)
    lease["source_document"] = {
        "filename": source_filename,
        "mimetype": None,
        "extracted_text": None,
        "extracted_at": None
    }

    # Initialize empty ai_extraction
    lease["ai_extraction"] = None

    # Set current_values
    lease["current_values"] = current_values

    return True


def _migrate_lease_add_lock_in_and_renewal_fields(lease):
    """Add lock_in_period and renewal_terms to existing leases if missing.

    This migration is idempotent - safe to run multiple times.

    Returns True if migration was performed, False if already has fields.
    """
    # Skip if no current_values (will be handled by _migrate_lease_to_new_structure)
    if "current_values" not in lease:
        return False

    current_values = lease["current_values"]
    migrated = False

    # Add lock_in_period if missing
    if "lock_in_period" not in current_values:
        current_values["lock_in_period"] = {
            "duration_months": None
        }
        migrated = True

    # Add renewal_terms if missing
    if "renewal_terms" not in current_values:
        current_values["renewal_terms"] = {
            "rent_escalation_percent": None
        }
        migrated = True

    return migrated


def _default_expected_payments(monthly_rent=None):
    """Return default expected_payments list for a lease.

    Rent is always expected. Maintenance and utilities default to not expected.
    If monthly_rent is provided, it becomes the typical_amount for rent.
    """
    return [
        {"type": "rent", "expected": True, "typical_amount": monthly_rent},
        {"type": "maintenance", "expected": False, "typical_amount": None},
        {"type": "utilities", "expected": False, "typical_amount": None},
    ]


def _migrate_lease_add_expected_payments(lease):
    """Add expected_payments to existing leases if missing.

    Default: rent expected (with monthly_rent as typical_amount),
    maintenance and utilities not expected.
    """
    if "current_values" not in lease:
        return False

    current_values = lease["current_values"]

    if "expected_payments" in current_values:
        return False

    monthly_rent = current_values.get("monthly_rent")
    current_values["expected_payments"] = _default_expected_payments(monthly_rent)
    return True


def _migrate_lease_add_confirmation_flag(lease):
    """Add needs_expected_payment_confirmation flag if missing.

    Existing leases default to false (no confirmation needed).
    """
    if "needs_expected_payment_confirmation" in lease:
        return False

    lease["needs_expected_payment_confirmation"] = False
    return True


def compute_monthly_coverage(expected_payments, month_payments):
    """Compute payment category coverage for a single month.

    Args:
        expected_payments: list of dicts with 'type' and 'expected' keys
                           (from lease.current_values.expected_payments)
        month_payments: list of payment confirmation dicts for this month

    Returns:
        dict with expected, covered, missing categories and summary
    """
    expected_categories = [
        ep["type"] for ep in (expected_payments or [])
        if ep.get("expected")
    ]

    covered_set = set(
        pc.get("confirmation_type")
        for pc in month_payments
        if pc.get("confirmation_type") in expected_categories
    )
    covered_categories = [cat for cat in expected_categories if cat in covered_set]

    missing_categories = [cat for cat in expected_categories if cat not in covered_set]

    total = len(expected_categories)
    covered = len(covered_categories)

    return {
        "expected_categories": expected_categories,
        "covered_categories": covered_categories,
        "missing_categories": missing_categories,
        "coverage_summary": f"{covered} / {total}" if total > 0 else None,
        "is_complete": total == 0 or covered >= total,
    }


def compute_lease_attention_count(lease_group_id, all_confirmations, all_events):
    """Count months needing landlord attention for a lease group.

    A month needs attention if ANY payment in that month has:
      - tenant_replied: open conversation, tenant spoke last
      - pending_review: submission with no landlord events at all
      - flagged: open conversation (landlord spoke last)

    Args:
        lease_group_id: str
        all_confirmations: list (pre-loaded from payment_data.json)
        all_events: list (pre-loaded from landlord_review_data.json)

    Returns:
        int: number of months needing attention (0 = no attention needed)
    """
    # Filter confirmations for this lease group
    confirmations = [c for c in all_confirmations
                     if c.get("lease_group_id") == lease_group_id]
    if not confirmations:
        return 0

    # Filter and normalize events for this lease group
    events = [_normalize_event(e) for e in all_events
              if e.get("lease_group_id") == lease_group_id]

    # Group events by payment_id and compute conversation state
    payment_events = {}
    for event in events:
        pid = event.get("payment_id")
        if pid:
            if pid not in payment_events:
                payment_events[pid] = []
            payment_events[pid].append(event)

    payment_conversations = {}
    for pid, evts in payment_events.items():
        evts.sort(key=lambda e: e.get("created_at", ""))
        payment_conversations[pid] = get_conversation_state(evts)

    # Group confirmations by (year, month)
    months = {}
    for c in confirmations:
        key = (c.get("period_year"), c.get("period_month"))
        if key not in months:
            months[key] = []
        months[key].append(c)

    # Count months needing attention (category-aware)
    attention_count = 0
    for month_key, month_payments in months.items():
        month_needs_attention = False

        # Group by category for cat_has_any_review check
        cat_payments = {}
        for pc in month_payments:
            ctype = pc.get("confirmation_type")
            if ctype not in cat_payments:
                cat_payments[ctype] = []
            cat_payments[ctype].append(pc)

        for cat, cat_pcs in cat_payments.items():
            # Check if ANY payment in this category has landlord events
            cat_has_any_review = any(
                any(e.get("actor") == "landlord"
                    for e in payment_events.get(pc.get("id"), []))
                for pc in cat_pcs
            )

            # Check for tenant_replied (per-payment, always triggers attention)
            for pc in cat_pcs:
                pid = pc.get("id")
                convo = payment_conversations.get(pid, {"open": False, "thread": []})
                if convo["open"] and convo["thread"]:
                    last_event = convo["thread"][-1]
                    if last_event.get("actor") == "tenant":
                        month_needs_attention = True
                        break

            if month_needs_attention:
                break

            # pending_review: only if NO submission in this category was reviewed
            if not cat_has_any_review:
                month_needs_attention = True
                break

        if month_needs_attention:
            attention_count += 1

    return attention_count


def get_lease_attention_items(lease_group_id, all_confirmations, all_events):
    """List months needing landlord attention for a lease group.

    For each month with at least one payment requiring attention,
    returns the month and a human-readable reason based on the
    worst-case status across all payments in that month.

    Args:
        lease_group_id: str
        all_confirmations: list (pre-loaded from payment_data.json)
        all_events: list (pre-loaded from landlord_review_data.json)

    Returns:
        list of dicts, newest month first. Each dict:
            year: int
            month: int
            month_name: str
            reason: str (human-readable)
    """
    month_names = ["January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November",
                   "December"]

    # Filter confirmations for this lease group
    confirmations = [c for c in all_confirmations
                     if c.get("lease_group_id") == lease_group_id]
    if not confirmations:
        return []

    # Filter and normalize events for this lease group
    events = [_normalize_event(e) for e in all_events
              if e.get("lease_group_id") == lease_group_id]

    # Group events by payment_id and compute conversation state
    payment_events = {}
    for event in events:
        pid = event.get("payment_id")
        if pid:
            if pid not in payment_events:
                payment_events[pid] = []
            payment_events[pid].append(event)

    payment_conversations = {}
    for pid, evts in payment_events.items():
        evts.sort(key=lambda e: e.get("created_at", ""))
        payment_conversations[pid] = get_conversation_state(evts)

    # Group confirmations by (year, month)
    months = {}
    for c in confirmations:
        key = (c.get("period_year"), c.get("period_month"))
        if key not in months:
            months[key] = []
        months[key].append(c)

    # Collect months needing attention with worst-case reason (category-aware)
    items = []
    for (year, month), month_payments in months.items():
        worst_priority = 999
        worst_reason = None

        # Group by category for cat_has_any_review check
        cat_payments = {}
        for pc in month_payments:
            ctype = pc.get("confirmation_type")
            if ctype not in cat_payments:
                cat_payments[ctype] = []
            cat_payments[ctype].append(pc)

        for cat, cat_pcs in cat_payments.items():
            cat_has_any_review = any(
                any(e.get("actor") == "landlord"
                    for e in payment_events.get(pc.get("id"), []))
                for pc in cat_pcs
            )

            # tenant_replied (per-payment, always triggers attention)
            for pc in cat_pcs:
                pid = pc.get("id")
                convo = payment_conversations.get(pid, {"open": False, "thread": []})
                if convo["open"] and convo["thread"]:
                    last_event = convo["thread"][-1]
                    if last_event.get("actor") == "tenant":
                        if worst_priority > 1:
                            worst_priority = 1
                            worst_reason = "Tenant replied"

            # pending_review (category-aware: only if entire category is unreviewed)
            if not cat_has_any_review:
                if worst_priority > 2:
                    worst_priority = 2
                    worst_reason = "Awaiting your review"

        if worst_reason:
            items.append({
                "year": year,
                "month": month,
                "month_name": month_names[month - 1] if month and 1 <= month <= 12 else "Unknown",
                "reason": worst_reason,
            })

    items.sort(key=lambda x: (x["year"], x["month"]), reverse=True)
    return items


def build_payment_threads(month_payments, payment_events):
    """Build payment threads grouped by confirmation type for a single month.

    Groups submissions by category, merges with review/reply events into
    a chronological timeline, derives status, and computes action targeting.

    Action targeting rule (per category):
        latest_submission_payment_id: most recent submission by submitted_at
        active_conversation_payment_id: payment with open conversation
            (if multiple, the one with the most recent event)
        action_payment_id:
            active_conversation_payment_id if it exists,
            else latest_submission_payment_id

    All landlord actions (acknowledge / flag / reply) MUST target
    action_payment_id. Templates and JS must never infer which
    payment_id to use.

    Args:
        month_payments: list of payment confirmation dicts for this month
        payment_events: dict {payment_id: [normalized events, oldest first]}

    Returns:
        list of thread dicts, ordered: rent -> maintenance -> utilities.
        Empty list if no payments.
    """
    CATEGORY_ORDER = ["rent", "maintenance", "utilities"]
    CATEGORY_DISPLAY = {
        "rent": "Rent", "maintenance": "Maintenance",
        "utilities": "Utilities",
    }
    STATUS_DISPLAY = {
        "awaiting_landlord": "Needs your action",
        "awaiting_tenant": "Awaiting tenant response",
        "resolved": "Resolved",
    }

    # Group payments by category
    cat_buckets = {}
    for pc in month_payments:
        ctype = pc.get("confirmation_type")
        if ctype not in cat_buckets:
            cat_buckets[ctype] = []
        cat_buckets[ctype].append(pc)

    threads = []
    for cat in CATEGORY_ORDER:
        cat_pcs = cat_buckets.get(cat)
        if not cat_pcs:
            continue

        # Sort submissions oldest first for timeline
        cat_pcs_sorted = sorted(
            cat_pcs, key=lambda c: c.get("submitted_at", ""))

        # Compute conversation state once per payment (cached)
        cat_conversations = {}
        for pc in cat_pcs:
            pid = pc.get("id")
            cat_conversations[pid] = get_conversation_state(
                payment_events.get(pid, []))

        # --- Action targeting (CRITICAL — single source of truth) ---

        # latest_submission_payment_id: most recent by submitted_at
        latest_sub = cat_pcs_sorted[-1]
        latest_submission_payment_id = latest_sub.get("id")

        # active_conversation_payment_id: open conversation with most
        # recent event as tiebreaker
        active_conversation_payment_id = None
        active_latest_event_time = ""
        for pc in cat_pcs:
            pid = pc.get("id")
            convo = cat_conversations[pid]
            if convo["open"] and convo["thread"]:
                last_event_time = convo["thread"][-1].get("created_at", "")
                if (active_conversation_payment_id is None
                        or last_event_time > active_latest_event_time):
                    active_conversation_payment_id = pid
                    active_latest_event_time = last_event_time

        # action_payment_id: active conversation wins, else latest submission
        action_payment_id = (active_conversation_payment_id
                             if active_conversation_payment_id
                             else latest_submission_payment_id)

        # --- Category status (cat_has_any_review pattern) ---

        cat_has_any_review = any(
            any(e.get("actor") == "landlord"
                for e in payment_events.get(pc.get("id"), []))
            for pc in cat_pcs
        )

        worst = 4  # 4 = acknowledged/resolved (best)
        for pc in cat_pcs:
            pid = pc.get("id")
            convo = cat_conversations[pid]
            if convo["open"] and convo["thread"]:
                last_event = convo["thread"][-1]
                if last_event.get("actor") == "tenant":
                    worst = min(worst, 1)  # tenant replied
                else:
                    worst = min(worst, 2)  # landlord spoke last
            elif (not any(e.get("actor") == "landlord"
                          for e in payment_events.get(pid, []))
                  and not cat_has_any_review):
                worst = min(worst, 3)  # pending review

        # Map to thread-level status names
        WORST_TO_STATUS = {1: "awaiting_landlord", 2: "awaiting_tenant",
                           3: "awaiting_landlord", 4: "resolved"}
        status = WORST_TO_STATUS.get(worst, "resolved")

        # --- Build merged timeline (oldest first) ---

        timeline = []

        # Add all submissions
        for pc in cat_pcs_sorted:
            timeline.append({
                "entry_type": "submission",
                "payment_id": pc.get("id"),
                "timestamp": pc.get("submitted_at", ""),
                "is_latest": pc.get("id") == latest_submission_payment_id,
                "amount_declared": pc.get("amount_declared"),
                "amount_agreed": pc.get("amount_agreed"),
                "tds_deducted": pc.get("tds_deducted"),
                "date_paid": pc.get("date_paid"),
                "submitted_via": pc.get("submitted_via"),
                "notes": pc.get("notes"),
                "proof_files": pc.get("proof_files", []),
            })

        # Add all review/reply events across all submissions in category
        for pc in cat_pcs:
            pid = pc.get("id")
            for event in payment_events.get(pid, []):
                timeline.append({
                    "entry_type": "event",
                    "event_type": event.get("event_type"),
                    "actor": event.get("actor"),
                    "message": event.get("message"),
                    "attachments": event.get("attachments", []),
                    "timestamp": event.get("created_at", ""),
                    "payment_id": pid,
                })

        # Sort everything chronologically
        timeline.sort(key=lambda e: e.get("timestamp", ""))

        threads.append({
            "payment_type": cat,
            "payment_type_display": CATEGORY_DISPLAY.get(cat, cat.title()),
            "status": status,
            "status_display": STATUS_DISPLAY.get(status, status),
            "submission_count": len(cat_pcs),
            "latest_submission": latest_sub,
            "latest_submission_payment_id": latest_submission_payment_id,
            "active_conversation_payment_id": active_conversation_payment_id,
            "action_payment_id": action_payment_id,
            "conversation_open": active_conversation_payment_id is not None,
            "timeline": timeline,
        })

    return threads


def load_lease_data():
    """Load saved lease data from JSON file if it exists.

    For backward compatibility, returns the first lease or None.
    Use _load_all_leases() to get the full collection.
    """
    all_data = _load_all_leases()
    leases = all_data.get("leases", [])
    return leases[0] if leases else None


def get_all_leases(current_only=False):
    """Get all leases as a list.

    Args:
        current_only: If True, only return leases where is_current=True
                      (filters out old versions for dashboard display)

    Returns:
        list: List of lease objects, sorted by updated_at (most recent first)
    """
    all_data = _load_all_leases()
    leases = all_data.get("leases", [])

    if current_only:
        leases = [l for l in leases if l.get("is_current", True) and l.get("status", "active") != "draft"]

    # Sort by updated_at (most recent first)
    return sorted(
        leases,
        key=lambda x: x.get("updated_at") or x.get("created_at") or "",
        reverse=True
    )


def get_lease_by_id(lease_id):
    """Get a specific lease by its ID.

    Args:
        lease_id: The UUID string of the lease

    Returns:
        dict: The lease object, or None if not found
    """
    if not lease_id:
        return None
    all_data = _load_all_leases()
    for lease in all_data.get("leases", []):
        if lease.get("id") == lease_id:
            return lease
    return None


def get_lease_versions(lease_group_id):
    """Get all versions of a lease group, sorted by version (newest first).

    Args:
        lease_group_id: The UUID string of the lease group

    Returns:
        list: List of lease objects in the group, sorted by version descending
    """
    if not lease_group_id:
        return []
    all_data = _load_all_leases()
    versions = [l for l in all_data.get("leases", [])
                if l.get("lease_group_id") == lease_group_id]
    return sorted(versions, key=lambda x: x.get("version", 1), reverse=True)


def get_earliest_start_date(versions):
    """Get the earliest lease_start_date across all versions in a lease group.

    Args:
        versions: List of lease version dicts (pre-loaded, not re-fetched).

    Returns:
        str: ISO date string (YYYY-MM-DD) of the earliest start, or None.
    """
    earliest = None
    for v in versions:
        cv = v.get("current_values", v)
        start_str = cv.get("lease_start_date")
        if start_str:
            try:
                d = datetime.strptime(start_str, "%Y-%m-%d").date()
                if earliest is None or d < earliest:
                    earliest = d
            except (ValueError, TypeError):
                pass
    return earliest.isoformat() if earliest else None


def get_tenant_continuity_duration(versions, current_tenant_name):
    """Compute how long the current tenant has continuously held the lease.

    Walks versions from newest to oldest. Finds the earliest contiguous
    version where the tenant name matches (after title normalization via
    _normalize_name). Duration is from that version's start date to today.

    Args:
        versions: List of lease version dicts (pre-loaded, not re-fetched).
                  Will be defensively sorted newest-first by version number.
        current_tenant_name: The current tenant's name string.

    Returns:
        str: Formatted duration like "1y 5m", "1y", "5m", or "< 1m".
             None if tenant name is empty or continuity cannot be determined.
    """
    if not current_tenant_name:
        return None
    _, current_key = _normalize_name(current_tenant_name)
    if not current_key:
        return None
    # Defensive sort: newest first by version number
    sorted_versions = sorted(versions, key=lambda x: x.get("version", 1), reverse=True)
    continuity_start = None
    for v in sorted_versions:
        cv = v.get("current_values", v)
        _, tenant_key = _normalize_name(cv.get("lessee_name"))
        if tenant_key == current_key:
            start_str = cv.get("lease_start_date")
            if start_str:
                continuity_start = start_str
        else:
            break
    if not continuity_start:
        return None
    try:
        start = datetime.strptime(continuity_start, "%Y-%m-%d").date()
        today = datetime.now().date()
        years = today.year - start.year
        months = today.month - start.month
        if today.day < start.day:
            months -= 1
        if months < 0:
            years -= 1
            months += 12
        if years > 0 and months > 0:
            return f"{years}y {months}m"
        elif years > 0:
            return f"{years}y"
        elif months > 0:
            return f"{months}m"
        else:
            return "< 1m"
    except (ValueError, TypeError):
        return None


def _parse_month_tuple(date_str):
    """Parse 'YYYY-MM-DD' string to (year, month) tuple.

    Args:
        date_str: A date string in YYYY-MM-DD format

    Returns:
        tuple: (year, month) as integers, or None if invalid/missing
    """
    if not date_str:
        return None
    try:
        parts = date_str.split("-")
        return (int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return None


def get_governing_lease_for_month(lease_group_id, target_year, target_month):
    """Find the single governing lease for a specific month in a lease group.

    Uses date-based selection (NOT is_current). For a given (year, month),
    finds which lease version's term covers that month, accounting for
    early termination events.

    Args:
        lease_group_id: UUID string of the lease group
        target_year: int, e.g. 2025
        target_month: int, 1-12

    Returns:
        dict with one of two structures:
        - {"status": "IN_LEASE", "lease": <dict>, "lease_id": <str>, "version": <int>}
        - {"status": "OUT_OF_LEASE", "reason": <str>, "lease": None}
          where reason is one of:
            "pre_lease"  — target month is before any lease in this group started
            "post_lease" — target month is after all leases in this group have ended
            "gap"        — target month falls between lease versions with no coverage
            "terminated" — target month falls after the effective termination date
                           of a lease version, and no other lease version governs
                           that month
    """
    all_versions = get_lease_versions(lease_group_id)

    if not all_versions:
        return {"status": "OUT_OF_LEASE", "reason": "pre_lease", "lease": None}

    target = (target_year, target_month)

    eligible = []
    terminated_would_match = False

    for lease in all_versions:
        if lease.get("status") == "draft":
            continue

        cv = lease.get("current_values") or {}
        start_tuple = _parse_month_tuple(cv.get("lease_start_date"))
        end_tuple = _parse_month_tuple(cv.get("lease_end_date"))

        if start_tuple is None or end_tuple is None:
            continue

        # Determine effective end: termination overrides lease_end_date
        effective_end = end_tuple
        termination = get_termination_for_lease(lease.get("id"))
        if termination:
            term_tuple = _parse_month_tuple(termination.get("termination_date"))
            if term_tuple is not None:
                effective_end = term_tuple

        # Check date eligibility
        if start_tuple <= target <= effective_end:
            eligible.append({
                "lease": lease,
                "start_tuple": start_tuple,
                "version": lease.get("version", 1),
            })
        elif termination and start_tuple <= target <= end_tuple:
            # Would have been eligible without termination
            terminated_would_match = True

    # Pick the best eligible lease
    if eligible:
        eligible.sort(
            key=lambda x: (x["start_tuple"], x["version"]),
            reverse=True
        )
        best = eligible[0]["lease"]
        return {
            "status": "IN_LEASE",
            "lease": best,
            "lease_id": best.get("id"),
            "version": best.get("version", 1),
        }

    # No eligible lease — determine OUT_OF_LEASE reason
    if terminated_would_match:
        return {"status": "OUT_OF_LEASE", "reason": "terminated", "lease": None}

    # Collect date ranges from all non-draft versions to determine positional reason
    all_starts = []
    all_ends = []
    for lease in all_versions:
        if lease.get("status") == "draft":
            continue
        cv = lease.get("current_values") or {}
        start_tuple = _parse_month_tuple(cv.get("lease_start_date"))
        end_tuple = _parse_month_tuple(cv.get("lease_end_date"))
        if start_tuple is not None:
            all_starts.append(start_tuple)
        if end_tuple is not None:
            all_ends.append(end_tuple)

    if not all_starts:
        return {"status": "OUT_OF_LEASE", "reason": "pre_lease", "lease": None}

    earliest_start = min(all_starts)
    latest_end = max(all_ends)

    if target < earliest_start:
        return {"status": "OUT_OF_LEASE", "reason": "pre_lease", "lease": None}
    elif target > latest_end:
        return {"status": "OUT_OF_LEASE", "reason": "post_lease", "lease": None}
    else:
        return {"status": "OUT_OF_LEASE", "reason": "gap", "lease": None}


def cleanup_draft_leases(leases):
    """Remove abandoned draft leases and restore previous versions if needed.

    For each draft lease:
    - Deletes the uploaded file from disk (if it exists)
    - If the draft is a renewal (version > 1), restores is_current=True
      on the previous version in the same lease_group_id
    - Removes the draft lease from the list

    Args:
        leases: list of lease dictionaries (already loaded from JSON)

    Returns:
        list: the cleaned leases list with drafts removed
    """
    drafts = [l for l in leases if l.get("status") == "draft"]

    for draft in drafts:
        # 1. Delete uploaded file from disk
        source_doc = draft.get("source_document") or {}
        filename = source_doc.get("filename")
        if filename:
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            try:
                os.remove(file_path)
            except OSError:
                pass

        # 2. If renewal, restore previous version
        if draft.get("version", 1) > 1:
            group_id = draft.get("lease_group_id")
            draft_version = draft.get("version", 1)
            # Find the highest version below this draft in the same group
            previous = [
                l for l in leases
                if l.get("lease_group_id") == group_id
                and l.get("version", 1) < draft_version
            ]
            if previous:
                best = max(previous, key=lambda l: l.get("version", 1))
                best["is_current"] = True

    # 3. Remove all drafts from the list
    leases = [l for l in leases if l.get("status") != "draft"]

    return leases


def create_lease_renewal(original_lease_id):
    """Create a renewal (new version) of an existing lease.

    Rules:
    - New version = max(version) + 1 in the group
    - Previous current lease -> is_current = False
    - New lease -> is_current = True

    Args:
        original_lease_id: ID of any lease in the group

    Returns:
        dict: The new lease version, or None on failure
    """
    original = get_lease_by_id(original_lease_id)
    if not original:
        return None

    lease_group_id = original.get("lease_group_id", original_lease_id)

    # Get all versions to find max version number
    versions = get_lease_versions(lease_group_id)
    max_version = max((v.get("version", 1) for v in versions), default=0)

    # Mark all existing versions as not current
    all_data = _load_all_leases()
    for lease in all_data.get("leases", []):
        if lease.get("lease_group_id") == lease_group_id:
            lease["is_current"] = False

    # Create new version
    now = datetime.now().isoformat()

    # Get current_values from original lease (handles both old and new structure)
    orig_cv = original.get("current_values") or original

    new_lease = {
        "id": str(uuid.uuid4()),
        "lease_group_id": lease_group_id,
        "version": max_version + 1,
        "is_current": True,
        "created_at": now,
        "updated_at": now,
        "source_document": {
            "filename": None,
            "mimetype": None,
            "extracted_text": None,
            "extracted_at": None,
        },
        "ai_extraction": None,
        "current_values": {
            # Copy relevant fields from original
            "lease_nickname": orig_cv.get("lease_nickname"),
            "lessor_name": orig_cv.get("lessor_name"),
            "lessee_name": orig_cv.get("lessee_name"),
            # Dates left empty for user to fill
            "lease_start_date": None,
            "lease_end_date": None,
            "monthly_rent": orig_cv.get("monthly_rent"),
            "security_deposit": orig_cv.get("security_deposit"),
            "rent_due_day": orig_cv.get("rent_due_day"),
            "lock_in_period": {
                "duration_months": None
            },
            "renewal_terms": {
                "rent_escalation_percent": None
            },
            "expected_payments": orig_cv.get(
                "expected_payments",
                _default_expected_payments(orig_cv.get("monthly_rent"))
            ),
        },
        "needs_expected_payment_confirmation": True,
    }

    all_data["leases"].append(new_lease)
    _save_lease_file(all_data)

    return new_lease


def get_active_lease():
    """Get the currently active lease based on request context.

    Selection priority:
    1. ?lease_id query parameter
    2. Most recently updated lease
    3. None if no leases exist

    Returns:
        dict: The active lease object, or None
    """
    leases = get_all_leases()

    if not leases:
        return None

    # Check for explicit lease_id in query params
    lease_id = request.args.get("lease_id")
    if lease_id:
        lease = get_lease_by_id(lease_id)
        if lease:
            return lease

    # Fallback to most recently updated lease (already sorted)
    return leases[0] if leases else None


def _normalize_name(name):
    """Remove common titles from a name and normalize for comparison.

    Returns:
        tuple: (display_name, key) where display_name is title-cased
               and key is lowercased for comparison. Both are None if
               name is empty/whitespace.
    """
    if not name:
        return None, None
    cleaned = re.sub(r'^(prof\.?|mrs\.?|mr\.?|ms\.?|dr\.?)\s*', '', name.strip(), flags=re.IGNORECASE)
    cleaned = ' '.join(cleaned.split())
    if not cleaned:
        return None, None
    return cleaned.title(), cleaned.lower()


def group_leases_by_lessor(leases):
    """Group leases by lessor_name for dashboard display.

    Returns:
        OrderedDict: {display_name: [leases]} sorted alphabetically,
                     with "Unknown Landlord" at the end if present.
    """
    from collections import OrderedDict

    groups = {}  # lessor_key -> {"display_name": str, "leases": []}

    for lease in leases:
        # Handle both old (flat) and new (nested) structure
        cv = lease.get("current_values") or lease
        raw_lessor = cv.get("lessor_name")
        if not raw_lessor or not raw_lessor.strip():
            lessor_key = "unknown landlord"
            display_name = "Unknown Landlord"
        else:
            display_name, lessor_key = _normalize_name(raw_lessor)
            if not display_name:
                display_name = "Unknown Landlord"
                lessor_key = "unknown landlord"

        if lessor_key not in groups:
            groups[lessor_key] = {"display_name": display_name, "leases": []}
        groups[lessor_key]["leases"].append(lease)

    # Sort groups alphabetically, but put "Unknown Landlord" at the end
    sorted_keys = sorted(
        [k for k in groups.keys() if k != "unknown landlord"]
    )
    if "unknown landlord" in groups:
        sorted_keys.append("unknown landlord")

    return OrderedDict(
        (groups[k]["display_name"], groups[k]["leases"]) for k in sorted_keys
    )


def calculate_lease_expiry_status(lease_data):
    """Calculate lease expiry status and urgency level.

    Returns:
        dict with days_remaining, urgency, message - or None if date missing/invalid
    """
    if not lease_data:
        return None

    # Handle both old (flat) and new (nested) structure
    cv = lease_data.get("current_values") or lease_data
    end_date_str = cv.get("lease_end_date")
    if not end_date_str:
        return None

    try:
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    except ValueError:
        return None

    today = datetime.now().date()
    days_remaining = (end_date - today).days

    # Determine urgency level based on thresholds: 60, 30, 10 days
    if days_remaining <= 0:
        urgency = "critical"
        message = "Lease has expired!" if days_remaining == 0 else f"Lease expired {abs(days_remaining)} days ago"
    elif days_remaining <= 10:
        urgency = "urgent"
        message = f"Lease expires in {days_remaining} day{'s' if days_remaining != 1 else ''}!"
    elif days_remaining <= 30:
        urgency = "warning"
        message = f"Lease expires in {days_remaining} days"
    elif days_remaining <= 60:
        urgency = "info"
        message = f"Lease expires in {days_remaining} days"
    else:
        urgency = "none"
        message = f"Lease expires in {days_remaining} days"

    return {
        "days_remaining": days_remaining,
        "urgency": urgency,
        "message": message,
        "end_date": end_date_str
    }


def calculate_rent_payment_status(lease_data):
    """Calculate rent payment status and urgency level.

    Returns:
        dict with days_remaining, urgency, message - or None if rent_due_day missing/invalid
    """
    if not lease_data:
        return None

    # Handle both old (flat) and new (nested) structure
    cv = lease_data.get("current_values") or lease_data
    rent_due_day_str = cv.get("rent_due_day")
    if not rent_due_day_str:
        return None

    try:
        rent_due_day = int(rent_due_day_str)
        if not (1 <= rent_due_day <= 31):
            return None
    except (ValueError, TypeError):
        return None

    today = datetime.now().date()

    # Calculate next rent due date
    if today.day < rent_due_day:
        # Due date is this month
        try:
            next_due = today.replace(day=rent_due_day)
        except ValueError:
            # Handle months with fewer days (e.g., Feb 30 -> Feb 28)
            last_day = calendar.monthrange(today.year, today.month)[1]
            next_due = today.replace(day=min(rent_due_day, last_day))
    elif today.day == rent_due_day:
        # Due today
        next_due = today
    else:
        # Due date is next month
        if today.month == 12:
            next_month = today.replace(year=today.year + 1, month=1, day=1)
        else:
            next_month = today.replace(month=today.month + 1, day=1)
        last_day = calendar.monthrange(next_month.year, next_month.month)[1]
        next_due = next_month.replace(day=min(rent_due_day, last_day))

    days_remaining = (next_due - today).days

    # Determine urgency level
    if days_remaining < 0:
        urgency = "critical"
        message = f"Rent is {abs(days_remaining)} day{'s' if abs(days_remaining) != 1 else ''} overdue!"
    elif days_remaining == 0:
        urgency = "urgent"
        message = "Rent is due today!"
    elif days_remaining == 1:
        urgency = "urgent"
        message = "Rent is due tomorrow!"
    elif days_remaining <= 3:
        urgency = "warning"
        message = f"Rent due in {days_remaining} days"
    elif days_remaining <= 7:
        urgency = "info"
        message = f"Rent due in {days_remaining} days"
    else:
        urgency = "none"
        message = f"Rent due in {days_remaining} days"

    return {
        "days_remaining": days_remaining,
        "urgency": urgency,
        "message": message,
        "due_day": rent_due_day,
        "next_due_date": next_due.isoformat()
    }


def calculate_reminder_status(lease_data):
    """Calculate combined reminder status for lease expiry and rent payment.

    Returns:
        dict with lease_expiry and rent_payment status objects
    """
    return {
        "lease_expiry": calculate_lease_expiry_status(lease_data),
        "rent_payment": calculate_rent_payment_status(lease_data)
    }


def get_global_alerts(leases, max_alerts=5):
    """Aggregate alerts across all leases for dashboard display.

    Args:
        leases: List of lease objects
        max_alerts: Maximum number of alerts to return (default 5)

    Returns:
        List of alert dicts sorted by urgency (most urgent first)
    """
    # Urgency priority for sorting (lower = more urgent)
    urgency_priority = {
        "critical": 0,
        "urgent": 1,
        "warning": 2,
        "info": 3,
    }

    alerts = []

    for lease in leases:
        lease_id = lease.get("id")
        # Handle both old (flat) and new (nested) structure
        cv = lease.get("current_values") or lease
        lease_nickname = cv.get("lease_nickname") or "Untitled Lease"
        lessor_name = cv.get("lessor_name") or "Unknown Landlord"

        # Check lease expiry
        expiry_status = calculate_lease_expiry_status(lease)
        if expiry_status and expiry_status.get("urgency") not in (None, "none"):
            alerts.append({
                "type": "lease_expiry",
                "urgency": expiry_status["urgency"],
                "message": expiry_status["message"],
                "lease_id": lease_id,
                "lease_nickname": lease_nickname,
                "lessor_name": lessor_name,
            })

        # Check rent payment
        rent_status = calculate_rent_payment_status(lease)
        if rent_status and rent_status.get("urgency") not in (None, "none"):
            alerts.append({
                "type": "rent_due",
                "urgency": rent_status["urgency"],
                "message": rent_status["message"],
                "lease_id": lease_id,
                "lease_nickname": lease_nickname,
                "lessor_name": lessor_name,
            })

    # Sort by urgency priority (critical first)
    alerts.sort(key=lambda a: urgency_priority.get(a["urgency"], 99))

    # Limit to max_alerts
    return alerts[:max_alerts]


def compare_lease_versions(current_lease, previous_lease):
    """Compare two lease versions and return list of changes.

    Args:
        current_lease: The current (newer) lease version
        previous_lease: The previous (older) lease version

    Returns:
        list: List of change dicts with {field, label, old_value, new_value, change_type}
    """
    if not current_lease or not previous_lease:
        return []

    # Fields to compare with their display labels
    fields_to_compare = [
        ("lessee_name", "Tenant Name"),
        ("monthly_rent", "Monthly Rent"),
        ("security_deposit", "Security Deposit"),
        ("rent_due_day", "Rent Due Day"),
        ("lease_start_date", "Start Date"),
        ("lease_end_date", "End Date"),
    ]

    # Nested fields
    nested_fields = [
        ("lock_in_period", "duration_months", "Lock-in Period (months)"),
        ("renewal_terms", "rent_escalation_percent", "Rent Escalation (%)"),
    ]

    current_cv = current_lease.get("current_values") or {}
    previous_cv = previous_lease.get("current_values") or {}

    changes = []

    # Compare simple fields
    for field, label in fields_to_compare:
        old_val = previous_cv.get(field)
        new_val = current_cv.get(field)

        # Normalize empty values
        old_normalized = None if (old_val is None or str(old_val).strip() == "") else old_val
        new_normalized = None if (new_val is None or str(new_val).strip() == "") else new_val

        # Skip if both are empty
        if old_normalized is None and new_normalized is None:
            continue

        # Determine change type
        if str(old_normalized) == str(new_normalized):
            change_type = "unchanged"
        elif old_normalized is None:
            change_type = "added"
        elif new_normalized is None:
            change_type = "removed"
        else:
            change_type = "changed"

        changes.append({
            "field": field,
            "label": label,
            "old_value": old_val,
            "new_value": new_val,
            "change_type": change_type
        })

    # Compare nested fields
    for parent, child, label in nested_fields:
        old_parent = previous_cv.get(parent) or {}
        new_parent = current_cv.get(parent) or {}
        old_val = old_parent.get(child) if isinstance(old_parent, dict) else None
        new_val = new_parent.get(child) if isinstance(new_parent, dict) else None

        # Normalize empty values
        old_normalized = None if (old_val is None or str(old_val).strip() == "") else old_val
        new_normalized = None if (new_val is None or str(new_val).strip() == "") else new_val

        # Skip if both are empty
        if old_normalized is None and new_normalized is None:
            continue

        # Determine change type
        if str(old_normalized) == str(new_normalized):
            change_type = "unchanged"
        elif old_normalized is None:
            change_type = "added"
        elif new_normalized is None:
            change_type = "removed"
        else:
            change_type = "changed"

        changes.append({
            "field": f"{parent}.{child}",
            "label": label,
            "old_value": old_val,
            "new_value": new_val,
            "change_type": change_type
        })

    return changes


@app.route("/")
def index():
    """Display the main page or dashboard."""
    lease_id = request.args.get("lease_id")
    edit_mode = request.args.get("edit") == "true"
    new_lease = request.args.get("new") == "true"
    renew_from = request.args.get("renew_from")  # Lease ID to renew from
    focus_monthly_attention = request.args.get("focus") == "monthly_attention"
    open_month = request.args.get("open_month")  # e.g. "2026-01"
    return_to_attention = request.args.get("return_to") == "attention"
    return_attention_for = request.args.get("return_attention_for")

    # Dashboard-first: if no lease_id specified, show dashboard
    # Unless ?new=true is specified (show upload form)
    if not lease_id and not new_lease:
        # Dashboard shows only current versions (not old renewals)
        leases = get_all_leases(current_only=True)

        # Load payment and review data once for attention badge computation.
        all_confirmations = _load_all_payments().get("confirmations", [])
        all_events = _load_all_landlord_reviews().get("reviews", [])

        # Pre-compute card view-model data for each lease.
        # versions_cache ensures get_lease_versions is called at most
        # once per lease_group_id, avoiding repeated JSON file reads.
        versions_cache = {}
        for lease in leases:
            cv = lease.get("current_values", lease)
            lgid = lease.get("lease_group_id", lease.get("id"))
            if lgid not in versions_cache:
                versions_cache[lgid] = get_lease_versions(lgid)
            versions = versions_cache[lgid]
            lease["_earliest_start_date"] = get_earliest_start_date(versions)
            lease["_tenant_continuity"] = get_tenant_continuity_duration(versions, cv.get("lessee_name"))
            attention_count = compute_lease_attention_count(lgid, all_confirmations, all_events)
            lease["_needs_attention"] = attention_count > 0
            lease["_attention_count"] = attention_count
            lease["_attention_items"] = get_lease_attention_items(lgid, all_confirmations, all_events) if attention_count > 0 else []

        grouped_leases = group_leases_by_lessor(leases)
        global_alerts = get_global_alerts(leases)
        return render_template("index.html",
                               uploads=uploads,
                               leases=leases,
                               grouped_leases=grouped_leases,
                               global_alerts=global_alerts,
                               lease_data=None,
                               edit_mode=False,
                               reminder_status=None,
                               show_dashboard=True,
                               renew_from=None,
                               renew_from_lease=None,
                               return_attention_for=return_attention_for,
                               payment_threads_by_month={})

    # Get all leases for sidebar/navigation (current only)
    leases = get_all_leases(current_only=True)

    # Handle renewal context
    renew_from_lease = None
    if renew_from:
        renew_from_lease = get_lease_by_id(renew_from)
        if not renew_from_lease:
            flash("Original lease not found for renewal.", "error")
            renew_from = None

    # Specific lease requested via ?lease_id=
    if lease_id:
        lease_data = get_lease_by_id(lease_id)
        if not lease_data:
            flash("Lease not found.", "error")
            return redirect(url_for("index"))
    else:
        lease_data = None

    reminder_status = calculate_reminder_status(lease_data)

    # Get lease versions for history display
    lease_versions = []
    version_changes = []
    if lease_data:
        lease_group_id = lease_data.get("lease_group_id", lease_data.get("id"))
        lease_versions = get_lease_versions(lease_group_id)

        # Compare with previous version if this is a renewal (version > 1)
        current_version = lease_data.get("version", 1)
        if current_version > 1:
            # Find the previous version
            previous_version = None
            for v in lease_versions:
                if v.get("version") == current_version - 1:
                    previous_version = v
                    break
            if previous_version:
                version_changes = compare_lease_versions(lease_data, previous_version)

    # Load tenant access and payment data for view mode
    tenant_tokens = []
    active_tenant_token = None
    payment_confirmations = []
    payment_events = {}
    payment_conversation = {}
    if lease_data and not edit_mode:
        tenant_tokens = get_all_tokens_for_lease_group(lease_group_id)
        active_tenant_token = next((t for t in tenant_tokens if t.get("is_active")), None)
        payment_confirmations = get_payments_for_lease_group(lease_group_id)

        # Load events for this lease group (Phase 2)
        all_events = get_events_for_lease_group(lease_group_id)
        for event in all_events:
            pid = event.get("payment_id")
            if pid:
                if pid not in payment_events:
                    payment_events[pid] = []
                payment_events[pid].append(event)
        # Reverse to oldest-first (helper returns newest-first)
        for pid in payment_events:
            payment_events[pid].reverse()
        # Compute conversation state per payment
        for pid, events in payment_events.items():
            payment_conversation[pid] = get_conversation_state(events)

    # Compute monthly submission summary (Step 9)
    monthly_summary = []
    if payment_confirmations is not None and lease_data and not edit_mode:
        month_names = ["January", "February", "March", "April", "May", "June",
                       "July", "August", "September", "October", "November", "December"]
        start_year, start_month = None, None

        # Priority 1: lease start date
        cv = lease_data.get("current_values") or {}
        lease_start = cv.get("lease_start_date")
        if lease_start:
            try:
                parts = lease_start.split("-")
                start_year, start_month = int(parts[0]), int(parts[1])
            except (ValueError, IndexError):
                pass

        # Priority 2: earliest submission period
        if start_year is None and payment_confirmations:
            earliest = min(payment_confirmations,
                           key=lambda c: (c.get("period_year", 9999), c.get("period_month", 13)))
            start_year = earliest.get("period_year")
            start_month = earliest.get("period_month")

        if start_year and start_month:
            now = datetime.now()
            end_year, end_month = now.year, now.month
            y, m = start_year, start_month
            while (y, m) <= (end_year, end_month):
                month_payments = [c for c in payment_confirmations
                                  if c.get("period_year") == y and c.get("period_month") == m]
                count = len(month_payments)

                # Derive review status from existing event data
                review_status = "not_submitted"
                review_date = None

                if count > 0:
                    has_any_event = False
                    all_have_events = True
                    worst_priority = 4  # acknowledged (lowest concern)

                    for pc in month_payments:
                        pid = pc.get("id")
                        pc_events = payment_events.get(pid, [])
                        landlord_events = [e for e in pc_events if e.get("actor") == "landlord"]

                        if landlord_events:
                            has_any_event = True
                        else:
                            all_have_events = False

                        convo = payment_conversation.get(pid, {"open": False, "thread": []})
                        if convo["open"] and convo["thread"]:
                            last_event = convo["thread"][-1]
                            if last_event.get("actor") == "tenant":
                                if worst_priority > 1:
                                    worst_priority = 1
                                    review_date = last_event.get("created_at")
                            else:
                                if worst_priority > 2:
                                    worst_priority = 2
                                    review_date = last_event.get("created_at")

                    if worst_priority == 1:
                        review_status = "tenant_replied"
                    elif worst_priority == 2:
                        review_status = "flagged"
                    elif not has_any_event:
                        review_status = "pending"
                        review_date = None
                    else:
                        review_status = "acknowledged"
                        review_date = None

                # Compute coverage (skip current month)
                if (y, m) == (now.year, now.month):
                    coverage = {"expected_categories": None, "covered_categories": None,
                                "missing_categories": None, "coverage_summary": None,
                                "is_complete": None}
                else:
                    coverage = compute_monthly_coverage(
                        cv.get("expected_payments", []), month_payments)

                # Compute per-category review state (only submitted+expected)
                if (y, m) == (now.year, now.month):
                    category_details = None
                elif count == 0:
                    category_details = {}
                else:
                    category_details = {}
                    cat_payments = {}
                    for pc in month_payments:
                        ctype = pc.get("confirmation_type")
                        if ctype not in cat_payments:
                            cat_payments[ctype] = []
                        cat_payments[ctype].append(pc)

                    for cat in (coverage.get("covered_categories") or []):
                        cat_pcs = cat_payments.get(cat, [])
                        if not cat_pcs:
                            continue
                        worst = 4  # acknowledged
                        worst_date = None
                        worst_actor = None
                        worst_flag_date = None
                        # Check if ANY payment in this category has landlord events
                        cat_has_any_review = any(
                            any(e.get("actor") == "landlord"
                                for e in payment_events.get(pc.get("id"), []))
                            for pc in cat_pcs
                        )
                        for pc in cat_pcs:
                            pid = pc.get("id")
                            pc_events = payment_events.get(pid, [])
                            landlord_events = [e for e in pc_events
                                               if e.get("actor") == "landlord"]
                            convo = payment_conversation.get(
                                pid, {"open": False, "thread": []})
                            if convo["open"] and convo["thread"]:
                                last_event = convo["thread"][-1]
                                flag_event = convo["thread"][0]
                                if last_event.get("actor") == "tenant":
                                    if worst > 1:
                                        worst = 1
                                        worst_date = last_event.get("created_at")
                                        worst_actor = "tenant"
                                        worst_flag_date = flag_event.get("created_at")
                                else:
                                    if worst > 2:
                                        worst = 2
                                        worst_date = last_event.get("created_at")
                                        worst_actor = "landlord"
                                        worst_flag_date = flag_event.get("created_at")
                            elif not landlord_events and not cat_has_any_review:
                                if worst > 3:
                                    worst = 3
                                    worst_actor = "tenant"
                                    # Use latest submission date for pending_review
                                    sub_date = pc.get("submitted_at")
                                    if worst_date is None or (sub_date and sub_date > (worst_date or "")):
                                        worst_date = sub_date
                        if worst == 1:
                            state = "tenant_replied"
                        elif worst == 2:
                            state = "flagged"
                        elif worst == 3:
                            state = "pending_review"
                        else:
                            state = "acknowledged"
                        category_details[cat] = {
                            "state": state,
                            "date": worst_date,
                            "actor": worst_actor,
                            "flag_date": worst_flag_date,
                        }

                monthly_summary.append({
                    "year": y, "month": m,
                    "month_name": month_names[m - 1],
                    "count": count,
                    "review_status": review_status,
                    "review_date": review_date,
                    "category_details": category_details,
                    **coverage,
                })
                m += 1
                if m > 12:
                    m = 1
                    y += 1

            monthly_summary.reverse()

            # Mark visibility: last 6 months always visible,
            # older months only if they have unresolved issues
            cutoff_m = now.month - 5
            cutoff_y = now.year
            if cutoff_m <= 0:
                cutoff_m += 12
                cutoff_y -= 1
            for ms in monthly_summary:
                within_window = (ms["year"], ms["month"]) >= (cutoff_y, cutoff_m)
                if within_window:
                    ms["visible"] = True
                else:
                    has_missing = bool(ms.get("missing_categories"))
                    has_unresolved = False
                    cd = ms.get("category_details")
                    if cd and isinstance(cd, dict):
                        for cat_info in cd.values():
                            if isinstance(cat_info, dict) and cat_info.get("state") != "acknowledged":
                                has_unresolved = True
                                break
                    ms["visible"] = has_missing or has_unresolved

    # Build payment threads per month for grouped modal view
    payment_threads_by_month = {}
    if payment_confirmations and lease_data and not edit_mode:
        for ms in monthly_summary:
            y, m = ms["year"], ms["month"]
            if ms["count"] > 0:
                mp = [c for c in payment_confirmations
                      if c.get("period_year") == y and c.get("period_month") == m]
                payment_threads_by_month[(y, m)] = build_payment_threads(
                    mp, payment_events)

    return render_template("index.html",
                           uploads=uploads,
                           lease_data=lease_data,
                           edit_mode=edit_mode,
                           reminder_status=reminder_status,
                           leases=leases,
                           show_dashboard=False,
                           renew_from=renew_from,
                           renew_from_lease=renew_from_lease,
                           lease_versions=lease_versions,
                           version_changes=version_changes,
                           tenant_tokens=tenant_tokens,
                           active_tenant_token=active_tenant_token,
                           payment_confirmations=payment_confirmations,
                           payment_events=payment_events,
                           payment_conversation=payment_conversation,
                           monthly_summary=monthly_summary,
                           payment_threads_by_month=payment_threads_by_month,
                           focus_monthly_attention=focus_monthly_attention,
                           open_month=open_month,
                           return_to_attention=return_to_attention)


@app.route("/upload", methods=["POST"])
def upload_file():
    """Handle file upload."""
    if "file" not in request.files:
        flash("No file selected", "error")
        return redirect(url_for("index"))

    file = request.files["file"]

    if file.filename == "":
        flash("No file selected", "error")
        return redirect(url_for("index"))

    if not allowed_file(file.filename):
        flash("Invalid file type. Please upload PDF, PNG, JPG, or JPEG.", "error")
        return redirect(url_for("index"))

    # Check if this is a renewal upload
    renew_from = request.form.get("renew_from")
    original_lease = None
    if renew_from:
        original_lease = get_lease_by_id(renew_from)
        if not original_lease:
            flash("Original lease not found for renewal.", "error")
            return redirect(url_for("index"))

    # Secure the filename and save
    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(file_path)

    # Extract text (best-effort, non-blocking)
    mimetype = file.mimetype
    extracted_text, page_texts = extract_text(file_path, mimetype)

    # Select best page for preview (avoids stamp/cover pages)
    preview_text = select_preview_page(page_texts)
    preview = create_preview(preview_text)

    # Store upload metadata (in-memory for AI extraction)
    uploads[filename] = {
        "filename": filename,
        "path": file_path,
        "mimetype": mimetype,
        "extracted_text": extracted_text,
        "preview": preview,
    }

    now = datetime.now().isoformat()
    new_lease_id = str(uuid.uuid4())
    all_data = _load_all_leases()

    # Clean up any abandoned draft leases before creating a new one
    all_data["leases"] = cleanup_draft_leases(all_data.get("leases", []))
    _save_lease_file(all_data)

    if original_lease:
        # RENEWAL: Create new version in existing lease group
        lease_group_id = original_lease.get("lease_group_id", original_lease.get("id"))

        # Find max version in group
        versions = [l for l in all_data.get("leases", [])
                    if l.get("lease_group_id") == lease_group_id]
        max_version = max((v.get("version", 1) for v in versions), default=0)

        # Mark all existing versions in group as not current
        for lease in all_data.get("leases", []):
            if lease.get("lease_group_id") == lease_group_id:
                lease["is_current"] = False

        # Get current_values from original lease (handles both old and new structure)
        if "current_values" in original_lease:
            orig_values = original_lease["current_values"]
        else:
            # Fallback for leases not yet migrated
            orig_values = original_lease

        # Create renewal lease with copied fields
        new_lease = {
            "id": new_lease_id,
            "lease_group_id": lease_group_id,
            "version": max_version + 1,
            "is_current": True,
            "status": "draft",
            "created_at": now,
            "updated_at": now,
            "source_document": {
                "filename": filename,
                "mimetype": mimetype,
                "extracted_text": extracted_text,
                "extracted_at": now,
            },
            "ai_extraction": None,
            "current_values": {
                # Convenience defaults only (property/landlord identity)
                "lease_nickname": orig_values.get("lease_nickname"),
                "lessor_name": orig_values.get("lessor_name"),
                # All other fields must come from renewal PDF or manual entry
                "lessee_name": None,
                "lease_start_date": None,
                "lease_end_date": None,
                "monthly_rent": None,
                "security_deposit": None,
                "rent_due_day": None,
                # Lease-specific terms (not inherited)
                "lock_in_period": {
                    "duration_months": None
                },
                "renewal_terms": {
                    "rent_escalation_percent": None
                },
                "expected_payments": orig_values.get(
                    "expected_payments",
                    _default_expected_payments(orig_values.get("monthly_rent"))
                ),
            },
            "needs_expected_payment_confirmation": True,
        }
        flash_msg = "Renewal lease uploaded! Review and update the new lease terms."
    else:
        # NEW LEASE: Create fresh lease entry
        new_lease = {
            "id": new_lease_id,
            "lease_group_id": new_lease_id,
            "version": 1,
            "is_current": True,
            "status": "draft",
            "created_at": now,
            "updated_at": now,
            "source_document": {
                "filename": filename,
                "mimetype": mimetype,
                "extracted_text": extracted_text,
                "extracted_at": now,
            },
            "ai_extraction": None,
            "current_values": {
                "lease_nickname": None,
                "lessor_name": None,
                "lessee_name": None,
                "lease_start_date": None,
                "lease_end_date": None,
                "monthly_rent": None,
                "security_deposit": None,
                "rent_due_day": None,
                "lock_in_period": {
                    "duration_months": None
                },
                "renewal_terms": {
                    "rent_escalation_percent": None
                },
                "expected_payments": _default_expected_payments(),
            },
            "needs_expected_payment_confirmation": False,
        }
        flash_msg = "Lease uploaded! Fill in details manually or use AI extraction."

    # Persist to lease collection
    all_data["leases"].append(new_lease)
    _save_lease_file(all_data)

    # Flash appropriate message
    if extracted_text:
        flash(flash_msg, "success")
    else:
        flash("Lease uploaded. Text extraction failed - please fill in details manually.", "success")

    # Redirect to new lease in edit mode
    return redirect(url_for("index", lease_id=new_lease_id, edit="true"))


def _normalize_string(value):
    """Normalize string: return None if empty/whitespace, otherwise stripped string."""
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped if stripped else None


def _validate_date(value):
    """Validate date in YYYY-MM-DD format. Returns valid string or None."""
    normalized = _normalize_string(value)
    if not normalized:
        return None
    try:
        datetime.strptime(normalized, "%Y-%m-%d")
        return normalized
    except ValueError:
        return None


def _validate_positive_number(value):
    """Validate positive number (int or float as string). Returns string or None."""
    normalized = _normalize_string(value)
    if not normalized:
        return None
    try:
        num = float(normalized)
        return normalized if num >= 0 else None
    except ValueError:
        return None


def _validate_day_of_month(value):
    """Validate day of month (1-31). Returns string or None."""
    normalized = _normalize_string(value)
    if not normalized:
        return None
    try:
        day = int(normalized)
        return normalized if 1 <= day <= 31 else None
    except ValueError:
        return None


@app.route("/save_lease", methods=["POST"])
def save_lease():
    """Save confirmed lease details to JSON file."""
    now = datetime.now().isoformat()
    lease_id = request.form.get("lease_id")  # For editing existing lease

    # Validate and normalize form data into current_values
    current_values = {
        "lease_nickname": _normalize_string(request.form.get("lease_nickname")),
        "lessor_name": _normalize_string(request.form.get("lessor_name")),
        "lessee_name": _normalize_string(request.form.get("lessee_name")),
        "lease_start_date": _validate_date(request.form.get("lease_start_date")),
        "lease_end_date": _validate_date(request.form.get("lease_end_date")),
        "monthly_rent": _validate_positive_number(request.form.get("monthly_rent")),
        "security_deposit": _validate_positive_number(request.form.get("security_deposit")),
        "rent_due_day": _validate_day_of_month(request.form.get("rent_due_day")),
        "lock_in_period": {
            "duration_months": _validate_positive_number(request.form.get("lock_in_months"))
        },
        "renewal_terms": {
            "rent_escalation_percent": _validate_positive_number(request.form.get("rent_escalation_percent"))
        },
    }

    # Build expected_payments from form inputs
    monthly_rent_value = current_values.get("monthly_rent")

    maintenance_checked = request.form.get("expect_maintenance") == "1"
    maintenance_amount = None
    if maintenance_checked:
        maintenance_amount = _validate_positive_number(
            request.form.get("maintenance_amount")
        )

    utilities_checked = request.form.get("expect_utilities") == "1"

    current_values["expected_payments"] = [
        {"type": "rent", "expected": True, "typical_amount": monthly_rent_value},
        {"type": "maintenance", "expected": maintenance_checked, "typical_amount": maintenance_amount},
        {"type": "utilities", "expected": utilities_checked, "typical_amount": None},
    ]

    # Load existing leases
    all_data = _load_all_leases()
    leases = all_data.get("leases", [])

    if lease_id:
        # Update existing lease
        for i, lease in enumerate(leases):
            if lease.get("id") == lease_id:
                # Update current_values
                lease["current_values"] = current_values
                lease["updated_at"] = now
                lease["status"] = "active"
                lease["needs_expected_payment_confirmation"] = False
                # source_document and ai_extraction are preserved automatically
                break
        else:
            # Lease ID not found - this shouldn't happen normally
            flash("Lease not found.", "error")
            return redirect(url_for("index"))
    else:
        # New lease (rare: usually created via upload)
        new_id = str(uuid.uuid4())
        source_filename = _normalize_string(request.form.get("source_filename"))
        new_lease = {
            "id": new_id,
            "lease_group_id": new_id,
            "version": 1,
            "is_current": True,
            "created_at": now,
            "updated_at": now,
            "source_document": {
                "filename": source_filename,
                "mimetype": None,
                "extracted_text": None,
                "extracted_at": None,
            },
            "ai_extraction": None,
            "current_values": current_values,
        }
        leases.append(new_lease)

    all_data["leases"] = leases

    if _save_lease_file(all_data):
        flash("Lease details saved successfully!", "success")
    else:
        flash("Failed to save lease details. Please try again.", "error")

    # Redirect to dashboard to show all leases including the new one
    return redirect(url_for("index"))


@app.route("/reset", methods=["POST"])
def reset_lease():
    """Delete a lease version with proper fallback handling.

    Security: Requires confirmation text to match expected value.
    - Single version deletion: confirm_text must equal "DELETE"
    - Group deletion: confirm_text must equal the lease nickname

    Version Fallback Logic:
    - If deleting a non-current version: just remove it
    - If deleting the current version: promote previous version to current
    - If deleting the only version: delete entire lease group
    """
    global uploads
    uploads = {}  # Clear in-memory uploads

    # Get the lease ID to delete
    lease_id = request.form.get("lease_id") or request.args.get("lease_id")

    # Get confirmation text from form
    confirm_text = request.form.get("confirm_text", "").strip()
    expected_text = request.form.get("expected_text", "DELETE").strip()

    # If no ID provided, get the active lease
    if not lease_id:
        active_lease = get_active_lease()
        lease_id = active_lease.get("id") if active_lease else None

    if not lease_id:
        flash("No lease to delete.", "error")
        return redirect(url_for("index"))

    # Fetch the lease to validate against
    lease_to_delete = get_lease_by_id(lease_id)
    if not lease_to_delete:
        flash("Lease not found.", "error")
        return redirect(url_for("index"))

    # SECURITY: Validate confirmation text on backend
    if expected_text == "DELETE":
        # Standard single version deletion
        if confirm_text.upper() != "DELETE":
            flash("Deletion aborted: confirmation text did not match. Type DELETE to confirm.", "error")
            return redirect(url_for("index", lease_id=lease_id))
    else:
        # Group deletion - expected_text is the lease nickname
        del_cv = lease_to_delete.get("current_values") or lease_to_delete
        lease_nickname = del_cv.get("lease_nickname") or "Untitled Lease"
        if confirm_text != lease_nickname:
            flash("Deletion aborted: confirmation text did not match the lease name.", "error")
            return redirect(url_for("index", lease_id=lease_id))

    # Confirmation validated - proceed with deletion
    all_data = _load_all_leases()
    leases = all_data.get("leases", [])

    # Get lease group info
    lease_group_id = lease_to_delete.get("lease_group_id", lease_id)
    is_current_version = lease_to_delete.get("is_current", True)
    deleted_version = lease_to_delete.get("version", 1)
    delete_group = request.form.get("delete_group") == "true"

    # Find all versions in this lease group
    group_versions = [l for l in leases if l.get("lease_group_id") == lease_group_id]
    group_versions_sorted = sorted(group_versions, key=lambda x: x.get("version", 1), reverse=True)

    # If delete_group flag is set, delete ALL versions in the group
    if delete_group:
        for gl in group_versions:
            gl_doc = gl.get("source_document") or {}
            gl_filename = gl_doc.get("filename")
            if gl_filename:
                try:
                    os.remove(os.path.join(UPLOAD_FOLDER, gl_filename))
                except OSError:
                    pass
        leases = [l for l in leases if l.get("lease_group_id") != lease_group_id]
        all_data["leases"] = leases
        _save_lease_file(all_data)
        flash("Lease and all its versions have been permanently deleted.", "success")
        return redirect(url_for("index"))

    # Determine the action based on version count
    if len(group_versions) <= 1:
        # CASE 1: Only one version - delete entire lease group
        for gl in group_versions:
            gl_doc = gl.get("source_document") or {}
            gl_filename = gl_doc.get("filename")
            if gl_filename:
                try:
                    os.remove(os.path.join(UPLOAD_FOLDER, gl_filename))
                except OSError:
                    pass
        leases = [l for l in leases if l.get("lease_group_id") != lease_group_id]
        all_data["leases"] = leases
        _save_lease_file(all_data)
        flash("Lease deleted as no versions remain.", "success")
        return redirect(url_for("index"))

    elif is_current_version:
        # CASE 2: Deleting the current version - need to promote previous version
        # Delete uploaded file from disk
        del_doc = lease_to_delete.get("source_document") or {}
        del_filename = del_doc.get("filename")
        if del_filename:
            try:
                os.remove(os.path.join(UPLOAD_FOLDER, del_filename))
            except OSError:
                pass
        # Remove the current version
        leases = [l for l in leases if l.get("id") != lease_id]

        # Find the previous version to promote (highest version number after current)
        previous_versions = [v for v in group_versions_sorted if v.get("id") != lease_id]
        if previous_versions:
            # Promote the most recent previous version
            new_current_id = previous_versions[0].get("id")
            for lease in leases:
                if lease.get("id") == new_current_id:
                    lease["is_current"] = True
                    new_current_version = lease.get("version", 1)
                    break

            all_data["leases"] = leases
            _save_lease_file(all_data)
            flash(f"Current lease version deleted. Reverted to version {new_current_version}.", "success")
            # Redirect to the new current version
            return redirect(url_for("index", lease_id=new_current_id))
        else:
            # Edge case: no previous versions found (shouldn't happen, but handle gracefully)
            leases = [l for l in leases if l.get("lease_group_id") != lease_group_id]
            all_data["leases"] = leases
            _save_lease_file(all_data)
            flash("Lease deleted as no versions remain.", "success")
            return redirect(url_for("index"))

    else:
        # CASE 3: Deleting a non-current version - just remove it
        # Delete uploaded file from disk
        del_doc = lease_to_delete.get("source_document") or {}
        del_filename = del_doc.get("filename")
        if del_filename:
            try:
                os.remove(os.path.join(UPLOAD_FOLDER, del_filename))
            except OSError:
                pass
        leases = [l for l in leases if l.get("id") != lease_id]
        all_data["leases"] = leases
        _save_lease_file(all_data)

        # Find the current version to redirect to
        current_version = next(
            (l for l in leases if l.get("lease_group_id") == lease_group_id and l.get("is_current")),
            None
        )
        if current_version:
            flash(f"Version {deleted_version} deleted. Current version unchanged.", "success")
            return redirect(url_for("index", lease_id=current_version.get("id")))
        else:
            flash("Lease version deleted successfully.", "success")
            return redirect(url_for("index"))


@app.route("/ai_prefill", methods=["POST"])
def ai_prefill():
    """AI-assisted pre-fill of lease fields. Saves AI results to lease."""
    # Get lease_id from request
    lease_id = request.json.get("lease_id") if request.is_json else request.form.get("lease_id")

    if not lease_id:
        return jsonify({
            "success": False,
            "error": "No lease specified."
        })

    # Load the lease
    all_data = _load_all_leases()
    lease = None
    lease_index = None
    for i, l in enumerate(all_data.get("leases", [])):
        if l.get("id") == lease_id:
            lease = l
            lease_index = i
            break

    if not lease:
        return jsonify({
            "success": False,
            "error": "Lease not found."
        })

    # Get extracted text from lease's source_document
    source_doc = lease.get("source_document") or {}
    extracted_text = source_doc.get("extracted_text")
    filename = source_doc.get("filename", "unknown")

    print(f"[DIAG] AI prefill called for lease: {lease_id}", flush=True)
    print(f"[DIAG] Source file: {filename}", flush=True)
    print(f"[DIAG] extracted_text exists: {extracted_text is not None}", flush=True)
    if extracted_text:
        print(f"[DIAG] Text length for AI: {len(extracted_text)} chars", flush=True)
        print(f"[DIAG] First 500 chars for AI: {extracted_text[:500]}", flush=True)

    # Check if the original document is missing (legacy lease)
    file_missing = (
        not source_doc.get("filename")
        or not os.path.exists(os.path.join(app.config["UPLOAD_FOLDER"], source_doc.get("filename", "")))
    )
    if not extracted_text and file_missing:
        return jsonify({
            "success": False,
            "error_code": "no_document",
            "error": "This lease was created before document storage was enabled. The original PDF is no longer available."
        })

    if not extracted_text:
        return jsonify({
            "success": False,
            "error": "No extracted text available for this lease. The document may need to be re-uploaded."
        })

    # Check for API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return jsonify({
            "success": False,
            "error": "AI service not configured. Please set ANTHROPIC_API_KEY environment variable."
        })

    # Call AI extraction
    result = ai_extract_lease_fields(extracted_text)

    if result is None:
        return jsonify({
            "success": False,
            "error": "AI extraction failed. Please try again or fill in the fields manually."
        })

    # Save AI extraction results to lease
    now = datetime.now().isoformat()
    lease["ai_extraction"] = {
        "ran_at": now,
        "fields": result
    }
    lease["updated_at"] = now
    all_data["leases"][lease_index] = lease
    _save_lease_file(all_data)

    return jsonify({
        "success": True,
        "data": result
    })


@app.route("/view_pdf/<filename>")
def view_pdf(filename):
    """Serve a PDF file from the uploads folder for viewing."""
    # Security: Only allow PDF files
    if not filename.lower().endswith('.pdf'):
        flash("Invalid file type.", "error")
        return redirect(url_for("index"))

    # Serve the file with inline disposition (displays in browser, not download)
    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename,
        mimetype="application/pdf"
    )


@app.route("/view_proof/<lease_group_id>/<filename>")
def view_proof(lease_group_id, filename):
    """Serve a proof file from uploads/proofs/{lease_group_id}/.

    Read-only. Validates against PROOF_ALLOWED_EXTENSIONS (independent
    of upload rules). Path traversal prevented by send_from_directory.
    """
    # Validate extension against proof-specific serving rules
    if not ("." in filename and
            filename.rsplit(".", 1)[1].lower() in PROOF_ALLOWED_EXTENSIONS):
        flash("Invalid file type.", "error")
        return redirect(url_for("index"))

    proof_dir = os.path.join(PROOF_UPLOAD_FOLDER, secure_filename(lease_group_id))

    return send_from_directory(proof_dir, filename)


# ----------------------------------------------------------------
# LANDLORD TENANT ACCESS MANAGEMENT (Phase 1 — Step 7)
# ----------------------------------------------------------------

@app.route("/lease/<lease_group_id>/generate-token", methods=["POST"])
def generate_token_route(lease_group_id):
    """Landlord action: generate a tenant access link."""
    result = generate_tenant_token(lease_group_id)
    # Find a lease_id in this group to redirect back to
    leases = _load_all_leases().get("leases", [])
    redirect_lease_id = None
    for l in leases:
        if l.get("lease_group_id") == lease_group_id and l.get("is_current"):
            redirect_lease_id = l.get("id")
            break
    if result.get("success"):
        flash("Tenant access link generated.", "success")
    else:
        error = result.get("error", "unknown")
        if error == "active_token_exists":
            flash("An active tenant link already exists for this lease.", "error")
        elif error == "lease_group_not_found":
            flash("Lease not found.", "error")
        else:
            flash("Failed to generate tenant link.", "error")
    return redirect(url_for("index", lease_id=redirect_lease_id or ""))


@app.route("/lease/<lease_group_id>/revoke-token", methods=["POST"])
def revoke_token_route(lease_group_id):
    """Landlord action: revoke a tenant access link."""
    token = request.form.get("token", "").strip()
    reason = request.form.get("revoke_reason", "").strip() or None
    # Find a lease_id in this group to redirect back to
    leases = _load_all_leases().get("leases", [])
    redirect_lease_id = None
    for l in leases:
        if l.get("lease_group_id") == lease_group_id and l.get("is_current"):
            redirect_lease_id = l.get("id")
            break
    if not token:
        flash("No token specified.", "error")
        return redirect(url_for("index", lease_id=redirect_lease_id or ""))
    result = revoke_tenant_token(token, reason=reason)
    if result.get("success"):
        flash("Tenant access has been revoked.", "success")
    else:
        error = result.get("error", "unknown")
        if error == "already_revoked":
            flash("This link was already revoked.", "error")
        else:
            flash("Failed to revoke tenant link.", "error")
    return redirect(url_for("index", lease_id=redirect_lease_id or ""))


@app.route("/lease/<lease_group_id>/payment/<payment_id>/review", methods=["POST"])
def submit_payment_review(lease_group_id, payment_id):
    """Landlord action: add an event for a payment confirmation.

    Supports: flagged, response, acknowledged.
    Append-only — writes to landlord_review_data.json.
    Never modifies payment_data.json.
    """
    # Find a lease_id in this group to redirect back to
    leases = _load_all_leases().get("leases", [])
    redirect_lease_id = None
    for l in leases:
        if l.get("lease_group_id") == lease_group_id and l.get("is_current"):
            redirect_lease_id = l.get("id")
            break

    # Validate payment_id exists and belongs to this lease_group_id
    payment_data = _load_all_payments()
    payment_record = None
    for c in payment_data.get("confirmations", []):
        if c.get("id") == payment_id and c.get("lease_group_id") == lease_group_id:
            payment_record = c
            break

    if not payment_record:
        flash("Payment confirmation not found.", "error")
        return redirect(url_for("index", lease_id=redirect_lease_id or ""))

    # Validate event_type
    event_type = request.form.get("review_type", "").strip()
    if event_type not in ("acknowledged", "flagged", "response"):
        flash("Invalid review type.", "error")
        return redirect(url_for("index", lease_id=redirect_lease_id or ""))

    # Message — required for flagged and response, optional otherwise
    message = request.form.get("internal_note", "").strip() or None

    if event_type == "flagged" and not message:
        flash("Please add a message for the tenant when flagging a submission.", "error")
        return redirect(url_for("index", lease_id=redirect_lease_id or ""))

    if event_type == "response" and not message:
        flash("Please add a message to your reply.", "error")
        return redirect(url_for("index", lease_id=redirect_lease_id or ""))

    # For response: validate conversation is open
    if event_type == "response":
        events = get_events_for_payment(payment_id)
        convo = get_conversation_state(events)
        if not convo["open"]:
            flash("No open conversation to reply to.", "error")
            return redirect(url_for("index", lease_id=redirect_lease_id or ""))

    # Handle optional file upload
    event_id = str(uuid.uuid4())
    attachments = []
    upload_file = request.files.get("attachment")
    if upload_file and upload_file.filename:
        relative_path, error = save_proof_file(lease_group_id, event_id, upload_file)
        if error:
            flash(f"File upload failed: {error}", "error")
            return redirect(url_for("index", lease_id=redirect_lease_id or ""))
        attachments.append(relative_path)

    # Build event record (Phase 2 schema)
    event_record = {
        "id": event_id,
        "payment_id": payment_id,
        "lease_group_id": lease_group_id,
        "created_at": datetime.now().isoformat(),
        "event_type": event_type,
        "actor": "landlord",
        "message": message,
        "attachments": attachments,
    }

    # Append-only save
    review_data = _load_all_landlord_reviews()
    review_data["reviews"].append(event_record)
    saved = _save_landlord_review_file(review_data)

    if saved:
        flash("Review saved.", "success")
    else:
        flash("Failed to save review. Please try again.", "error")

    # Smart redirect: stay on month modal if unresolved threads remain,
    # otherwise return to attention overview.
    period_year = payment_record.get("period_year")
    period_month = payment_record.get("period_month")
    if saved and redirect_lease_id and period_year and period_month:
        # Re-load events after our save, rebuild threads for this month
        all_confs = _load_all_payments().get("confirmations", [])
        month_payments = [
            c for c in all_confs
            if c.get("lease_group_id") == lease_group_id
            and c.get("period_year") == period_year
            and c.get("period_month") == period_month
        ]
        all_evts = _load_all_landlord_reviews().get("reviews", [])
        evt_map = {}
        for e in all_evts:
            evt_map.setdefault(e.get("payment_id"), []).append(_normalize_event(e))
        threads = build_payment_threads(month_payments, evt_map)
        month_has_unresolved = any(t["status"] != "resolved" for t in threads)

        if month_has_unresolved:
            open_month = f"{period_year}-{period_month:02d}"
            return redirect(url_for("index", lease_id=redirect_lease_id,
                                    open_month=open_month, return_to="attention"))
        else:
            return redirect(url_for("index", return_attention_for=redirect_lease_id))

    return redirect(url_for("index", lease_id=redirect_lease_id or ""))


@app.route("/tenant/<token>/payment/<payment_id>/response", methods=["POST"])
def tenant_payment_response(token, payment_id):
    """Tenant action: reply to a flagged payment conversation.

    Token-authenticated. Append-only.
    Allowed only while the conversation is open.
    """
    # Validate token
    result = validate_token(token)
    if not result["valid"]:
        flash("Invalid or expired link.", "error")
        return redirect(url_for("tenant_page", token=token))

    lease_group_id = result["lease_group_id"]

    # Validate payment_id exists and belongs to this lease_group_id
    payment_data = _load_all_payments()
    payment_record = None
    for c in payment_data.get("confirmations", []):
        if c.get("id") == payment_id and c.get("lease_group_id") == lease_group_id:
            payment_record = c
            break

    if not payment_record:
        flash("Payment submission not found.", "error")
        return redirect(url_for("tenant_page", token=token))

    # Validate conversation is open
    events = get_events_for_payment(payment_id)
    convo = get_conversation_state(events)
    if not convo["open"]:
        flash("This conversation is closed.", "error")
        return redirect(url_for("tenant_page", token=token))

    # Message is required
    message = request.form.get("message", "").strip()
    if not message:
        flash("Please enter a message.", "error")
        return redirect(url_for("tenant_page", token=token))

    # Handle optional file upload
    event_id = str(uuid.uuid4())
    attachments = []
    upload_file = request.files.get("attachment")
    if upload_file and upload_file.filename:
        relative_path, error = save_proof_file(lease_group_id, event_id, upload_file)
        if error:
            flash(f"File upload failed: {error}", "error")
            return redirect(url_for("tenant_page", token=token))
        attachments.append(relative_path)

    # Build event record (Phase 2 schema)
    event_record = {
        "id": event_id,
        "payment_id": payment_id,
        "lease_group_id": lease_group_id,
        "created_at": datetime.now().isoformat(),
        "event_type": "response",
        "actor": "tenant",
        "message": message,
        "attachments": attachments,
    }

    # Append-only save
    review_data = _load_all_landlord_reviews()
    review_data["reviews"].append(event_record)
    saved = _save_landlord_review_file(review_data)

    if saved:
        flash("Reply sent.", "success")
    else:
        flash("Failed to send reply. Please try again.", "error")

    return redirect(url_for("tenant_page", token=token))


# ----------------------------------------------------------------
# TENANT ACCESS ROUTES (Phase 1 — Step 5)
# ----------------------------------------------------------------

@app.route("/tenant/<token>")
def tenant_page(token):
    """Tenant-facing payment confirmation page.

    Validates token, loads minimal lease context, renders form.
    Does NOT modify any data.
    """
    result = validate_token(token)

    if not result["valid"]:
        return render_template("tenant_confirm.html",
                               token_valid=False,
                               error_reason=result["reason"])

    lease_group_id = result["lease_group_id"]

    # Read optional month/year prefill from query params
    prefill_month = request.args.get("month", type=int)
    prefill_year = request.args.get("year", type=int)

    # Load current lease for context (read-only)
    lease_data = _load_all_leases()
    current_lease = None
    for lease in lease_data.get("leases", []):
        if (lease.get("lease_group_id") == lease_group_id
                and lease.get("is_current")):
            current_lease = lease
            break

    # Extract display context from current lease (if it exists)
    lease_nickname = None
    agreed_rent = None
    lease_start_date = None
    lease_end_date = None
    if current_lease:
        cv = current_lease.get("current_values", {})
        lease_nickname = cv.get("lease_nickname") or "Untitled Lease"
        agreed_rent = cv.get("monthly_rent")
        lease_start_date = cv.get("lease_start_date")
        lease_end_date = cv.get("lease_end_date")

    # Load past submissions and events for tenant view (Phase 2)
    payment_confirmations = get_payments_for_lease_group(lease_group_id)
    all_events = get_events_for_lease_group(lease_group_id)

    # Build events per payment and conversation state
    payment_events = {}
    payment_conversation = {}
    for event in all_events:
        pid = event.get("payment_id")
        if pid:
            if pid not in payment_events:
                payment_events[pid] = []
            payment_events[pid].append(event)
    for pid in payment_events:
        payment_events[pid].reverse()  # oldest first
    for pid, events in payment_events.items():
        payment_conversation[pid] = get_conversation_state(events)

    # Compute monthly summary for tenant
    month_names = ["January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]
    monthly_summary = []
    if lease_start_date:
        try:
            start_parts = lease_start_date.split("-")
            start_year, start_month = int(start_parts[0]), int(start_parts[1])

            if lease_end_date:
                end_parts = lease_end_date.split("-")
                end_year, end_month = int(end_parts[0]), int(end_parts[1])
            else:
                today = datetime.now()
                end_year, end_month = today.year, today.month

            # Extend to current month if lease is still active
            today = datetime.now()
            if (end_year, end_month) < (today.year, today.month):
                pass  # lease ended, use lease end date
            else:
                end_year, end_month = today.year, today.month

            y, m = start_year, start_month
            while (y, m) <= (end_year, end_month):
                month_payments = [c for c in payment_confirmations
                                  if c.get("period_year") == y and c.get("period_month") == m]
                count = len(month_payments)

                review_status = "not_submitted"
                if count > 0:
                    worst_priority = 4  # acknowledged
                    for pc in month_payments:
                        pid = pc.get("id")
                        convo = payment_conversation.get(pid, {"open": False, "thread": []})

                        # Filter to tenant-visible events (flagged/response only)
                        visible_events = [e for e in convo.get("thread", [])
                                          if e.get("event_type") in ("flagged", "response")]

                        if not visible_events and convo["open"]:
                            # No visible events and conversation still open — just submitted
                            if worst_priority > 3:
                                worst_priority = 3
                        elif not visible_events and not convo["open"]:
                            # No visible events but conversation closed — acknowledged
                            if worst_priority > 4:
                                worst_priority = 4
                        elif convo["open"]:
                            last_visible = visible_events[-1]
                            if last_visible.get("actor") == "landlord":
                                # Landlord replied/flagged, tenant should respond
                                if worst_priority > 1:
                                    worst_priority = 1
                            else:
                                # Tenant replied, waiting for landlord
                                if worst_priority > 2:
                                    worst_priority = 2
                        else:
                            # Closed conversation
                            if worst_priority > 4:
                                worst_priority = 4

                    if worst_priority == 1:
                        review_status = "reply_from_landlord"
                    elif worst_priority == 2:
                        review_status = "flagged"
                    elif worst_priority == 3:
                        review_status = "submitted"
                    else:
                        review_status = "acknowledged"

                # Compute coverage (skip current month)
                if (y, m) == (today.year, today.month):
                    coverage = {"expected_categories": None, "covered_categories": None,
                                "missing_categories": None, "coverage_summary": None,
                                "is_complete": None}
                else:
                    coverage = compute_monthly_coverage(
                        cv.get("expected_payments", []), month_payments)

                # Compute per-category review state (tenant-facing)
                if (y, m) == (today.year, today.month):
                    category_details = None
                elif count == 0:
                    category_details = {}
                else:
                    category_details = {}
                    cat_payments = {}
                    for pc in month_payments:
                        ctype = pc.get("confirmation_type")
                        if ctype not in cat_payments:
                            cat_payments[ctype] = []
                        cat_payments[ctype].append(pc)

                    for cat in (coverage.get("covered_categories") or []):
                        cat_pcs = cat_payments.get(cat, [])
                        if not cat_pcs:
                            continue
                        worst = 4  # acknowledged
                        worst_date = None
                        worst_actor = None
                        worst_flag_date = None
                        for pc in cat_pcs:
                            pid = pc.get("id")
                            convo = payment_conversation.get(
                                pid, {"open": False, "thread": []})

                            # Tenant only sees flagged + response events
                            visible_events = [e for e in convo.get("thread", [])
                                              if e.get("event_type") in ("flagged", "response")]

                            if not visible_events and convo["open"]:
                                # No visible events and conversation still open — just submitted
                                if worst > 3:
                                    worst = 3
                                    worst_actor = "tenant"
                                    sub_date = pc.get("submitted_at")
                                    if worst_date is None or (sub_date and sub_date > (worst_date or "")):
                                        worst_date = sub_date
                            elif not visible_events and not convo["open"]:
                                # No visible events but conversation closed — acknowledged
                                pass  # worst stays at 4
                            elif convo["open"]:
                                last_visible = visible_events[-1]
                                flag_event = visible_events[0]
                                if last_visible.get("actor") == "landlord":
                                    # Landlord spoke last — tenant must respond
                                    if worst > 1:
                                        worst = 1
                                        worst_date = last_visible.get("created_at")
                                        worst_actor = "landlord"
                                        worst_flag_date = flag_event.get("created_at")
                                else:
                                    # Tenant spoke last — waiting for landlord
                                    if worst > 2:
                                        worst = 2
                                        worst_date = last_visible.get("created_at")
                                        worst_actor = "tenant"
                                        worst_flag_date = flag_event.get("created_at")
                            else:
                                # Closed conversation — acknowledged
                                pass  # worst stays at 4

                        if worst == 1:
                            state = "action_required"
                        elif worst == 2:
                            state = "you_responded"
                        elif worst == 3:
                            state = "submitted"
                        else:
                            state = "acknowledged"
                        category_details[cat] = {
                            "state": state,
                            "date": worst_date,
                            "actor": worst_actor,
                            "flag_date": worst_flag_date,
                        }

                    # Add missing expected categories as "not_submitted"
                    for cat in (coverage.get("missing_categories") or []):
                        if cat not in category_details:
                            category_details[cat] = {
                                "state": "not_submitted",
                                "date": None,
                                "actor": None,
                                "flag_date": None,
                            }

                monthly_summary.append({
                    "year": y, "month": m,
                    "month_name": month_names[m - 1],
                    "count": count,
                    "review_status": review_status,
                    "category_details": category_details,
                    **coverage,
                })
                m += 1
                if m > 12:
                    m = 1
                    y += 1

            monthly_summary.reverse()

            # Mark visibility: last 6 months always visible,
            # older months only if they have unresolved issues
            cutoff_m = today.month - 5
            cutoff_y = today.year
            if cutoff_m <= 0:
                cutoff_m += 12
                cutoff_y -= 1
            for ms in monthly_summary:
                within_window = (ms["year"], ms["month"]) >= (cutoff_y, cutoff_m)
                if within_window:
                    ms["visible"] = True
                else:
                    has_missing = bool(ms.get("missing_categories"))
                    has_unresolved = False
                    cd = ms.get("category_details")
                    if cd and isinstance(cd, dict):
                        for cat_info in cd.values():
                            if isinstance(cat_info, dict) and cat_info.get("state") != "acknowledged":
                                has_unresolved = True
                                break
                    ms["visible"] = has_missing or has_unresolved
        except (ValueError, IndexError):
            pass  # If date parsing fails, skip summary

    return render_template("tenant_confirm.html",
                           token_valid=True,
                           token=token,
                           lease_group_id=lease_group_id,
                           lease_nickname=lease_nickname,
                           agreed_rent=agreed_rent,
                           payment_confirmations=payment_confirmations,
                           payment_events=payment_events,
                           payment_conversation=payment_conversation,
                           monthly_summary=monthly_summary,
                           prefill_month=prefill_month,
                           prefill_year=prefill_year,
                           success=False)


@app.route("/tenant/<token>/confirm", methods=["POST"])
def tenant_confirm(token):
    """Accept and persist tenant payment confirmations (one per selected type).

    Validates token again (do NOT trust GET).
    Creates one append-only payment record per selected section.
    Rejects entire submission if any section fails validation.
    Never modifies existing records or proof files.
    """
    # Re-validate token (do not trust prior GET)
    result = validate_token(token)

    if not result["valid"]:
        return render_template("tenant_confirm.html",
                               token_valid=False,
                               error_reason=result["reason"])

    lease_group_id = result["lease_group_id"]

    # Load current lease for amount_agreed (rent only)
    lease_data = _load_all_leases()
    current_lease = None
    for lease in lease_data.get("leases", []):
        if (lease.get("lease_group_id") == lease_group_id
                and lease.get("is_current")):
            current_lease = lease
            break

    lease_nickname = None
    agreed_rent = None
    if current_lease:
        cv = current_lease.get("current_values", {})
        lease_nickname = cv.get("lease_nickname") or "Untitled Lease"
        agreed_rent = cv.get("monthly_rent")

    def render_error(errors):
        return render_template("tenant_confirm.html",
                               token_valid=True,
                               token=token,
                               lease_group_id=lease_group_id,
                               lease_nickname=lease_nickname,
                               agreed_rent=agreed_rent,
                               success=False,
                               errors=errors,
                               form=request.form,
                               monthly_summary=[])

    # --- Shared fields: month, year, disclaimer, notes ---
    errors = []

    try:
        period_month = int(request.form.get("period_month", ""))
        if not (1 <= period_month <= 12):
            errors.append("Month must be between 1 and 12.")
    except (ValueError, TypeError):
        errors.append("Month is required.")
        period_month = None

    current_year = datetime.now().year
    try:
        period_year = int(request.form.get("period_year", ""))
        if not (2020 <= period_year <= current_year + 1):
            errors.append(f"Year must be between 2020 and {current_year + 1}.")
    except (ValueError, TypeError):
        errors.append("Year is required.")
        period_year = None

    disclaimer_checked = request.form.get("disclaimer_acknowledged")
    if not disclaimer_checked:
        errors.append("You must acknowledge the disclaimer to submit.")

    notes = request.form.get("notes", "").strip() or None

    # --- Determine which sections are selected ---
    rent_selected = bool(request.form.get("rent_selected"))
    maintenance_selected = bool(request.form.get("maintenance_selected"))
    utilities_selected = bool(request.form.get("utilities_selected"))

    if not (rent_selected or maintenance_selected or utilities_selected):
        errors.append("Please select at least one payment type.")

    # --- Validate each selected section ---
    sections = []

    if rent_selected:
        try:
            rent_amount = float(request.form.get("rent_amount", ""))
            if rent_amount <= 0:
                errors.append("Rent: Amount paid must be greater than zero.")
        except (ValueError, TypeError):
            errors.append("Rent: Amount paid is required.")
            rent_amount = None

        rent_tds_raw = request.form.get("rent_tds", "").strip()
        rent_tds = None
        if rent_tds_raw:
            try:
                rent_tds = float(rent_tds_raw)
                if rent_tds < 0:
                    errors.append("Rent: TDS deducted cannot be negative.")
                elif rent_amount is not None and rent_tds > rent_amount:
                    errors.append("Rent: TDS deducted cannot exceed amount paid.")
            except (ValueError, TypeError):
                errors.append("Rent: TDS deducted must be a number.")

        rent_amount_agreed = None
        if agreed_rent is not None:
            try:
                rent_amount_agreed = float(agreed_rent)
            except (ValueError, TypeError):
                pass

        sections.append({
            "type": "rent",
            "amount": rent_amount,
            "tds": rent_tds,
            "amount_agreed": rent_amount_agreed,
            "date_paid": request.form.get("rent_date_paid", "").strip() or None,
            "proof_key": "rent_proof",
        })

    if maintenance_selected:
        try:
            maint_amount = float(request.form.get("maintenance_amount", ""))
            if maint_amount <= 0:
                errors.append("Maintenance: Amount paid must be greater than zero.")
        except (ValueError, TypeError):
            errors.append("Maintenance: Amount paid is required.")
            maint_amount = None

        sections.append({
            "type": "maintenance",
            "amount": maint_amount,
            "tds": None,
            "amount_agreed": None,
            "date_paid": request.form.get("maintenance_date_paid", "").strip() or None,
            "proof_key": "maintenance_proof",
        })

    if utilities_selected:
        try:
            util_amount = float(request.form.get("utilities_amount", ""))
            if util_amount <= 0:
                errors.append("Utilities: Amount paid must be greater than zero.")
        except (ValueError, TypeError):
            errors.append("Utilities: Amount paid is required.")
            util_amount = None

        sections.append({
            "type": "utilities",
            "amount": util_amount,
            "tds": None,
            "amount_agreed": None,
            "date_paid": request.form.get("utilities_date_paid", "").strip() or None,
            "proof_key": "utilities_proof",
        })

    # If any validation errors, reject entire submission
    if errors:
        return render_error(errors)

    # --- Handle proof uploads for each section (before creating records) ---
    now = datetime.now().isoformat()
    records = []

    for section in sections:
        payment_id = str(uuid.uuid4())
        proof_files = []

        proof_file = request.files.get(section["proof_key"])
        if proof_file and proof_file.filename:
            relative_path, error = save_proof_file(lease_group_id, payment_id, proof_file)
            if error:
                return render_error([f"{section['type'].capitalize()}: Proof upload failed: {error}"])
            proof_files.append(relative_path)

        records.append({
            "id": payment_id,
            "lease_group_id": lease_group_id,
            "confirmation_type": section["type"],
            "period_month": period_month,
            "period_year": period_year,
            "amount_agreed": section["amount_agreed"],
            "amount_declared": section["amount"],
            "tds_deducted": section["tds"],
            "date_paid": section["date_paid"],
            "proof_files": proof_files,
            "verification_status": "unverified",
            "disclaimer_acknowledged": now,
            "submitted_at": now,
            "submitted_via": "tenant_link",
            "notes": notes,
        })

    # --- Persist all records at once (no partial saves) ---
    payment_data = _load_all_payments()
    for record in records:
        payment_data["confirmations"].append(record)
    saved = _save_payment_file(payment_data)

    if not saved:
        return render_error(["Failed to save. Please try again."])

    return render_template("tenant_confirm.html",
                           token_valid=True,
                           token=token,
                           lease_group_id=lease_group_id,
                           lease_nickname=lease_nickname,
                           agreed_rent=agreed_rent,
                           success=True,
                           monthly_summary=[])


if __name__ == "__main__":
    # Run locally on port 5000
    # debug=True auto-reloads when you change code
    app.run(debug=True, port=5000)
