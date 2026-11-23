# SAKAI-02 — Create, find, and read a product

Start with a reset CRUD table and an empty search field. Use the supplied `name`, `description`, and `price_cents`.

`price_cents` is an integer in minor units. Enter and verify the corresponding dollar amount in the UI. For example, 1234 cents is $12.34.

1. Click **New**. **dialog_open** — Product Details opens.
2. Fill Name, Description, and Price. **entered_fields** — The current field values equal the supplied parameters.
3. Click **Save**. **saved** — The dialog closes.
4. Search for the supplied name. **exact_row_and_price** — Exactly one row has that name and its numeric price matches.
5. Open the edit dialog from that row. **saved_fields** — The dialog shows the exact name, description, and numeric price.
6. Click **Cancel**. **record_remains** — The dialog closes and the row remains in the search results.
