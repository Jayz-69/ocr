// Copyright (c) 2025, Jay Anjarlekar and contributors
// For license information, please see license.txt

frappe.ui.form.on("Invoice Ocr", {
    refresh(frm) {

        // Extract button
        if (!frm.is_new() && frm.doc.upload_file) {
            if (!frm.custom_extract_button_added) {
                frm.add_custom_button("Extract Data", () => {
                    frappe.call({
                        method: "ocr.invoice_ocr_utils.extract_data",
                        args: { docname: frm.doc.name },
                        freeze: true,
                        freeze_message: "Extracting invoice...",
                        callback() {
                            frappe.msgprint("OCR started. Refresh after some time.");
                        }
                    });
                });
                frm.custom_extract_button_added = true;
            }
        }

        // ---------- Supplier missing ----------
        if (frm.doc.supplier_status === "Missing") {
            frm.add_custom_button("Create Supplier", () => {
                frappe.new_doc("Supplier", {
                    supplier_name: frm.doc.vendor_name
                });
            }, "Actions");
        }

        // ---------- Item missing ----------
        (frm.doc.item || []).forEach(row => {
            if (row.item_status === "Missing") {
                frm.add_custom_button("Create Item: " + row.description, () => {
                    frappe.new_doc("Item", {
                        item_name: row.description,
                        stock_uom: row.uom || "Nos",
                        is_stock_item: 0
                    });
                }, "Actions");
            }
        });

        // ---------- Create Purchase Invoice ----------
        if (can_create_purchase_invoice(frm)) {
            frm.add_custom_button("Create Purchase Invoice", () => {
                frappe.call({
                    method: "ocr.invoice_ocr_utils.create_purchase_invoice",
                    args: { docname: frm.doc.name },
                    freeze: true,
                    freeze_message: "Creating Purchase Invoice...",
                    callback(r) {
                        if (r.message) {
                            frappe.set_route("Form", "Purchase Invoice", r.message);
                        }
                    }
                });
            }, "Actions");
        }
    }
});

function can_create_purchase_invoice(frm) {
    if (frm.doc.supplier_status !== "Found") return false;

    for (let row of frm.doc.item || []) {
        if (row.item_status !== "Found" || row.uom_status !== "Found") {
            return false;
        }
    }
    return true;
}
