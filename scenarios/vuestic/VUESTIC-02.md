# VUESTIC-02 — Create and read a user

Use the supplied unique full name, username, email, and 100-character notes. Keep Role at User and Active on. Leave Projects empty and do not upload an avatar.

1. Click Add User and verify that the creation dialog opens.
2. Fill Full name, Username, Email, and Notes. **form_values_match** — The form values match the supplied parameters.
3. Click Add once and wait for the result. **own_user_created** — The UI shows the attempt's own record, and there is no confirmed saving error.
4. Reload Users and complete a search by the attempt's full-name marker. **persisted_identity_matches** — Exactly one owned record matches the supplied Full name, Username, and Email.
5. Open Edit for that exact row. **persisted_notes_match** — Notes match all 100 supplied characters exactly, Role is User, and Active is on.
6. Close Edit without changes and verify that the table is available.

Run cleanup separately for the uniquely identified record. A toast or closed dialog alone cannot establish persistence.
