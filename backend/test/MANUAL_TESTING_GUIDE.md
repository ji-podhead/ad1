# Manual End-to-End Testing Guide for Attachment Download

This guide outlines the steps to manually test the email attachment download functionality from email processing by `agent_scheduler.py` to downloading via the frontend.

## Prerequisites

1.  **Test Gmail Account:**
    *   Have access to a Gmail account that can be used for testing.
    *   Ensure this account has at least one email with one or more common attachments (e.g., PDF, TXT, JPG).
    *   For more thorough testing, include emails with multiple attachments.

2.  **Google Cloud Project & OAuth Credentials:**
    *   Ensure you have a Google Cloud Project with the Gmail API enabled.
    *   OAuth 2.0 credentials (client ID, client secret) should be configured.
    *   The redirect URI for your OAuth flow should point to your backend's OAuth callback handler (e.g., `/api/auth/google/callback` if you have one, or as per your setup).

## Setup Steps

### 1. Backend Configuration

*   **Database Setup:**
    *   Ensure your PostgreSQL database is running.
    *   Verify the `users` table exists. Add a test user record corresponding to your test Gmail account:
        *   `email`: The email address of your test Gmail account.
        *   `google_access_token`: A **valid and current** OAuth2 access token for this user with the `https://www.googleapis.com/auth/gmail.modify` scope (or at least `gmail.readonly` for listing/reading, and `gmail.modify` for marking as read). You might need to run an OAuth flow manually (e.g., using Postman or a script with Google's client libraries) to get this token initially and store it in the database.
        *   Ensure other relevant user fields (like `id`) are populated.
    *   The `agent_scheduler.py` script will attempt to add `google_message_id` to `emails` and `google_attachment_id` to `documents` if they don't exist.

*   **Environment Variables (`.env` file for the backend):**
    *   `DATABASE_URL`: Correctly point to your PostgreSQL database.
    *   `DEFAULT_EMAIL_CHECK_USER`: Set this to the email address of your test Gmail account (the one for which you stored the `google_access_token`).
    *   `GEMINI_API_KEY` (if LLM summarization is part of the flow being tested).
    *   Other necessary environment variables for your backend setup.

*   **Run Backend:** Start your FastAPI backend server.

### 2. Frontend Configuration

*   Ensure your frontend development server is configured to proxy API requests to your backend (usually set up in `vite.config.ts` or similar for React/Vite projects).
*   No specific frontend configuration is usually needed for the download itself, as it relies on browser behavior and backend API calls.

*   **Run Frontend:** Start your frontend development server.

## Testing Procedure

1.  **Trigger Email Processing:**
    *   The `agent_scheduler.py`'s `check_new_emails` function is typically run on a schedule. To force an immediate check for testing:
        *   You might have a debug endpoint to trigger it.
        *   Or, temporarily reduce the cron interval in `backend_main.py` where `app.state.scheduler.schedule_cron` is called for `check_new_emails`.
        *   Alternatively, you could call `check_new_emails(app.state.db)` directly in an `async` context if you have a suitable way to do so (e.g., a temporary test script or endpoint).
    *   **Verification:**
        *   Observe backend logs for messages indicating `check_new_emails` is running, fetching emails from Google API, processing them, and storing metadata.
        *   Check the `emails` table in your database: A new record should appear for the test email. Verify that `google_message_id` is populated.
        *   Check the `documents` table: Records should appear for each attachment in the test email. Verify `filename`, `content_type`, and `google_attachment_id` (this should be the Gmail `partId`) are populated. The `email_id` should link to the new record in the `emails` table.
        *   Verify the `emails.document_ids` array is populated with the IDs from the `documents` table.
        *   Check if the email was marked as read in the test Gmail account (if it was unread before).

2.  **Test Attachment Download via Frontend:**
    *   Open the application in your browser.
    *   Log in if required (the placeholder auth in the download endpoint uses a fixed user ID; a real app would require login).
    *   Navigate to the view where emails are listed (e.g., Inbox page).
    *   Find and open the test email that was just processed. This should open the `EmailModal` (or similar detail view).
    *   **Verification (Display):**
        *   The `EmailModal` should display a list of attachments with their correct filenames.
    *   **Verification (Download):**
        *   Click on one of the attachment links.
        *   The browser should initiate a download.
        *   The downloaded file should have the correct filename (as displayed) and its content should be correct.
        *   Repeat for other attachments if present.
        *   Check the browser's developer console for any errors if the download fails.
        *   Check backend logs for any errors related to the download API call.

3.  **Direct API Test (Optional but Recommended for Backend Verification):**
    *   This step helps isolate backend issues from frontend issues.
    *   You'll need the `internal_email_id` (from `emails.id`) and `document_db_id` (from `documents.id`) for the attachment you want to test. Get these from your database after step 1.
    *   Use a tool like `curl` or Postman to make a GET request to the backend endpoint:
        `GET http://localhost:8000/api/emails/{internal_email_id}/attachments/{document_db_id}`
        (Replace port and path if different, and the IDs with actual values).
    *   **Authentication for Direct API Test:**
        *   The endpoint currently uses a placeholder authentication that fetches a token for a fixed user ID (e.g., user ID 1). If your testing tool needs to act as this user:
            *   If the placeholder relies on a session cookie set by a login flow, you might need to log in via the frontend first and then use the same browser session or copy cookies to your API tool.
            *   Alternatively, for isolated testing, you could temporarily modify the placeholder in `backend_main.py` to not require specific auth or to use a fixed test token passed via a header (e.g., `Authorization: Bearer <your_test_token>`), but remember to revert such changes.
    *   **Verification:**
        *   The API should respond with the file content.
        *   Check the `Content-Disposition` header (e.g., `attachment; filename="your_filename.ext"`).
        *   Check the `Content-Type` header.
        *   If using `curl -o output_filename ...`, verify `output_filename` has the correct content.

## Troubleshooting Tips

*   **Token Errors (401 Unauthorized):**
    *   Ensure the `google_access_token` in the `users` table is valid, not expired, and has the correct scopes.
    *   Verify `TARGET_USER_EMAIL_FOR_TOKEN` in `agent_scheduler.py` matches the user for whom the token is valid.
    *   If using the placeholder auth in `backend_main.py`, ensure the hardcoded user ID (e.g., `placeholder_user_id = 1`) exists and has a token.
*   **File Not Found (404 from API):**
    *   Double-check the `google_message_id` and `google_attachment_id` stored in your database. Are they correct for the email in Gmail?
    *   Ensure the IDs in the API request URL (`internal_email_id`, `document_db_id`) are correct.
*   **Download Issues:**
    *   Check backend logs for errors during the call to `tools_wrapper.download_attachment` or during response streaming.
    *   Check browser console for frontend errors.
*   **Data Not Appearing in DB:**
    *   Check `agent_scheduler.py` logs for errors during email fetching, parsing, or database insertion.
    *   Ensure the `check_new_emails` job is actually running.

This guide should help in thoroughly testing the attachment download feature. Remember to adapt specific user IDs, tokens, and email details to your test setup.
