"""
Lease Reminder App - Main Application
A simple local web app to extract and display lease information.
"""

import os
import json
from datetime import datetime
import calendar
import uuid
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
        },
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


def group_leases_by_lessor(leases):
    """Group leases by lessor_name for dashboard display.

    Returns:
        OrderedDict: {display_name: [leases]} sorted alphabetically,
                     with "Unknown Landlord" at the end if present.
    """
    from collections import OrderedDict
    import re

    def remove_titles(name):
        """Remove common titles from name and title-case the result."""
        if not name:
            return None
        # Remove common titles - order from longest to shortest to avoid partial matches
        cleaned = re.sub(r'^(prof\.?|mrs\.?|mr\.?|ms\.?|dr\.?)\s*', '', name.strip(), flags=re.IGNORECASE)
        # Collapse multiple spaces and strip
        cleaned = ' '.join(cleaned.split())
        # Title case: first letter of each word capitalized
        return cleaned.title() if cleaned else None

    def normalize_key(name):
        """Normalize name for grouping: lowercase version of cleaned name."""
        cleaned = remove_titles(name)
        return cleaned.lower() if cleaned else None

    groups = {}  # lessor_key -> {"display_name": str, "leases": []}

    for lease in leases:
        # Handle both old (flat) and new (nested) structure
        cv = lease.get("current_values") or lease
        raw_lessor = cv.get("lessor_name")
        if not raw_lessor or not raw_lessor.strip():
            lessor_key = "Unknown Landlord"
            display_name = "Unknown Landlord"
        else:
            display_name = remove_titles(raw_lessor) or "Unknown Landlord"
            lessor_key = display_name.lower()

        if lessor_key not in groups:
            groups[lessor_key] = {"display_name": display_name, "leases": []}
        groups[lessor_key]["leases"].append(lease)

    # Sort groups alphabetically, but put "Unknown Landlord" at the end
    sorted_keys = sorted(
        [k for k in groups.keys() if k != "Unknown Landlord"]
    )
    if "Unknown Landlord" in groups:
        sorted_keys.append("Unknown Landlord")

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
        ("lease_start_date", "Start Date"),
        ("lease_end_date", "End Date"),
        ("monthly_rent", "Monthly Rent"),
        ("security_deposit", "Security Deposit"),
        ("rent_due_day", "Rent Due Day"),
        ("lessee_name", "Tenant Name"),
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

        # Skip if equal
        if str(old_normalized) == str(new_normalized):
            continue

        # Determine change type
        if old_normalized is None:
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

        # Skip if equal
        if str(old_normalized) == str(new_normalized):
            continue

        # Determine change type
        if old_normalized is None:
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

    # Dashboard-first: if no lease_id specified, show dashboard
    # Unless ?new=true is specified (show upload form)
    if not lease_id and not new_lease:
        # Dashboard shows only current versions (not old renewals)
        leases = get_all_leases(current_only=True)
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
                               renew_from_lease=None)

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
                           version_changes=version_changes)


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
            },
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
            },
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


if __name__ == "__main__":
    # Run locally on port 5000
    # debug=True auto-reloads when you change code
    app.run(debug=True, port=5000)
