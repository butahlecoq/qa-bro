# VUESTIC-01 — Validate email and cancel creation

Precondition: the Add user form is available. Use the supplied unique full name, username, and email.

1. Open Add User. Fill Full name and Username with the supplied values and enter an email without `@`. Observe that the fields contain the entered values.
2. Leave the email field to trigger validation. If Add is enabled, attempt to submit. **invalid_email_rejected** — The email is rejected, the form stays open, and saving is not confirmed. A disabled Add button is allowed.
3. Replace the email with the valid parameter and leave the field again. **valid_email_accepted** — The email error disappears and Add is enabled when the other fields are valid.
4. Click Cancel. Confirm discarding changes if prompted. Observe that the form closes.
5. Reload the Users page and complete searches for the attempt's exact full-name marker in both Active and Inactive. **cancel_did_not_create** — The record is absent in both completed searches.

Expected English validation message: `Please enter a valid email address`. Capture the observable message if the deployment uses another locale.
