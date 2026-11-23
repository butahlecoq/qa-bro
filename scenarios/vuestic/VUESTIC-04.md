# VUESTIC-04 — Cancel and then confirm deletion

Prepare an independent owned record as in VUESTIC-02 and confirm it through a fresh UI read.

1. Click Delete user in the exact matching row. **delete_targets_own_user** — The confirmation names the exact owned record.
2. Click Cancel and reload Users. **cancel_preserves_user** — A completed search finds the same record.
3. Click Delete user again in the same exact matching row. Verify that the confirmation again names the owned record.
4. Click Delete once. Observe the outcome and whether the dialog closes.
5. Reload Users and complete searches for the full-name marker in both Active and Inactive. **confirmed_delete_persisted** — The owned record is absent in both completed searches.

An immediate disappearance from the current table does not establish deletion. If the record returns on a fresh read, retain that failed check and track cleanup separately.
