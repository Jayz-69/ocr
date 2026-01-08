import frappe
import requests
import json
import base64
import os
import tempfile

from frappe.utils.file_manager import get_file
from frappe.utils.background_jobs import enqueue


QWEN_URL = "http://192.168.22.194:11434/api/generate"


# =========================================================
# PUBLIC ENTRY
# =========================================================

@frappe.whitelist()
def extract_data(docname):
    frappe.log_error(docname, "OCR DEBUG - Extract Triggered")

    enqueue(
        "ocr.invoice_ocr_utils.run_ocr_job",
        docname=docname,
        queue="long"
    )

    return "OK"


# =========================================================
# BACKGROUND JOB
# =========================================================

def run_ocr_job(docname):
    frappe.log_error(docname, "OCR DEBUG - Job Started")

    doc = frappe.get_doc("Invoice Ocr", docname)

    if not doc.upload_file:
        frappe.throw("Please upload an invoice image.")

    # ---------- Resolve file ----------
    file_doc = get_file(doc.upload_file)
    file_path = file_doc[1]

    if isinstance(file_path, bytes):
        ext = os.path.splitext(doc.upload_file)[1] or ".jpg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(file_path)
            file_path = tmp.name

    frappe.log_error(file_path, "OCR DEBUG - File Path Resolved")

    # ---------- OCR ----------
    try:
        data = call_qwen_vision(file_path)
    except Exception as e:
        # stop job cleanly
        frappe.log_error(str(e), "OCR DEBUG - OCR FAILED")
        return

    frappe.log_error(
        json.dumps(data, indent=2),
        "OCR DEBUG - OCR JSON Parsed"
    )

    # ---------- Apply ----------
    apply_extracted_data(doc, data)

    frappe.log_error("Applying data completed", "OCR DEBUG - Apply Done")

    # IMPORTANT: ignore link validation
    doc.flags.ignore_links = True
    doc.save(ignore_permissions=True)

    frappe.db.commit()

    frappe.log_error("Document saved successfully", "OCR DEBUG - Save Success")


# =========================================================
# OCR CALL
# =========================================================

def call_qwen_vision(img_path):
    frappe.log_error(img_path, "OCR DEBUG - Sending Image to Model")

    with open(img_path, "rb") as f:
        img_bytes = f.read()

    b64_image = base64.b64encode(img_bytes).decode("utf-8")

    payload = {
        "model": "qwen3-vl",
        "stream": False,
        "prompt": """
        Return ONLY valid JSON.
        No explanation. No markdown. No text.

        Use EXACT keys below.

        {
        "vendor_name": "",
        "invoice_no": "",
        "invoice_date": "",
        "total_amount": 0,
        "items": [
            {
            "description": "",
            "quantity": 0,
            "unit_price": 0,
            "total_price": 0
            }
        ]
        }

        If missing, use "" or 0.
        JSON only.
        """,
                "images": [b64_image]
            }

    frappe.log_error(payload["prompt"], "OCR DEBUG - Prompt Sent")

    try:
        response = requests.post(
            QWEN_URL,
            json=payload,
            timeout=120
        )
        raw = response.json()
    except requests.exceptions.Timeout:
        frappe.throw("OCR timed out. Please retry or upload a smaller image.")
    except Exception as e:
        frappe.throw(f"OCR HTTP error: {str(e)}")

    # log raw response (trim if huge)
    raw_preview = json.dumps(raw, indent=2)
    if len(raw_preview) > 4000:
        raw_preview = raw_preview[:4000] + "\n...TRUNCATED..."

    frappe.log_error(raw_preview, "OCR DEBUG - Raw Model Response")

    text = (raw.get("response") or "").strip()

    if not text.startswith("{"):
        frappe.throw("OCR failed. Model returned invalid (non-JSON) output.")

    try:
        parsed = json.loads(text)
    except Exception as e:
        frappe.throw(f"OCR JSON parse failed: {str(e)}")

    return parsed


# =========================================================
# APPLY DATA (NO LINK FIELDS)
# =========================================================

def apply_extracted_data(doc, data):
    frappe.log_error("Applying extracted fields", "OCR DEBUG - Apply Start")

    doc.extracted_data = json.dumps(data, indent=2)

    # IMPORTANT: vendor_name must be DATA field
    doc.vendor_name = data.get("vendor_name", "")
    doc.invoice_no = data.get("invoice_no", "")
    doc.invoice_date = data.get("invoice_date", "")
    doc.total_amount = data.get("total_amount", 0)

    doc.set("item", [])

    for row in data.get("items", []):
        doc.append("item", {
            "description": row.get("description", ""),
            "quantity": row.get("quantity", 0),
            "unit_price": row.get("unit_price", 0),
            "total_price": row.get("total_price", 0)
        })

    frappe.log_error(
        f"{len(data.get('items', []))} item rows added",
        "OCR DEBUG - Items Applied"
    )
