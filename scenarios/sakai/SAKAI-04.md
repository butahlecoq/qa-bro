# SAKAI-04 — Cancel and confirm deletion

Start with a reset CRUD table and an empty search field. Create and find your own synthetic product using SAKAI-02 without resetting again.

1. Click the delete action in that exact matching row. **confirm_open** — The Confirm dialog names your product.
2. Click **No**. **cancel_preserves_row** — The dialog closes and the product remains.
3. Click delete again in the same exact matching row. **confirm_reopened** — The Confirm dialog names your product.
4. Click **Yes**. **confirm_closed** — The dialog closes.
5. Read the search results after the UI updates. **record_absent** — No row has the exact synthetic product name.
