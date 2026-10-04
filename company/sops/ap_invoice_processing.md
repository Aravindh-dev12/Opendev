# AP SOP: Supplier invoice processing

Owner: Accounts Payable. Applies to every supplier invoice that lands in the inbox folder.

## 1. Read the invoice
Extract vendor name, invoice number, PO number, invoice date, currency and the total amount.
Invoices without a PO number cannot be processed. Escalate them to the requester.

## 2. Check the vendor
Look the vendor up in the ERP vendors page. The vendor must exist and have status Active.
If the vendor is missing or Blocked, do not create or edit vendors. Escalate to Procurement and stop work on that invoice.

## 3. Check for duplicates
Open the ERP invoices page. If the same vendor and invoice number already exist, the invoice is a duplicate.
Do not enter it again. Record it as a duplicate and tell the requester.

## 4. Three way match
Open the purchase order in the ERP. The invoice total must be within 2 percent of the PO total and the PO must be Open.
If the amount differs by more than 2 percent, enter the invoice, then put it On Hold with a comment that states the PO total, the invoice total and the difference. Escalate to the buyer.

## 5. Enter and route
Use the New invoice form in the ERP: vendor, invoice number, PO number, amount, date.
After saving, open the invoice detail page.
- Total at or below 2,500.00 and match passed: click Approve invoice with the comment "Auto approved per AP SOP".
- Total above 2,500.00 and match passed: click Submit for manager approval. Never click Approve invoice for these.
- Match failed: click Put on hold and give the reason in the comment.

## 6. Prohibited actions
Never create vendors, change bank details, delete records, or use the admin and api pages.
When unsure, ask a human with a specific question, do not guess.

## 7. Evidence
Every disposition needs a screenshot of the ERP invoice page after the action (taken automatically on each write action) and a one line reason.
