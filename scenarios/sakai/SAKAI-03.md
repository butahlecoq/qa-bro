# SAKAI-03 — Change the price of a product

Start with a reset CRUD table and an empty search field. Create and verify your own synthetic product using SAKAI-02 without resetting again.

1. Open the edit dialog from the exact matching row. **original_price** — The dialog shows the supplied name and original price.
2. Change only Price. **entered_price** — The current numeric field value equals `updated_price_cents`.
3. Click **Save**. **updated_row** — The dialog closes and the matching row shows the updated price.
4. Reopen the edit dialog from that row. **persisted_update** — The updated price is present and the name and description equal the original values.
5. Close the dialog. **table_ready** — The table is available.
