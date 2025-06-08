# MCP Tools Reference

Below is a list of available MCP tools and their arguments (input parameters).

---

## 1. send_email
- **to**: array of string — List of recipient email addresses (required)
- **subject**: string — Email subject (required)
- **body**: string — Email body content (required)
- **htmlBody**: string — HTML version of the email body
- **mimeType**: string (enum: text/plain, text/html, multipart/alternative, default: text/plain) — Email content type
- **cc**: array of string — List of CC recipients
- **bcc**: array of string — List of BCC recipients
- **threadId**: string — Thread ID to reply to
- **inReplyTo**: string — Message ID being replied to

## 2. draft_email
- **to**: array of string — List of recipient email addresses (required)
- **subject**: string — Email subject (required)
- **body**: string — Email body content (required)
- **htmlBody**: string — HTML version of the email body
- **mimeType**: string (enum: text/plain, text/html, multipart/alternative, default: text/plain) — Email content type
- **cc**: array of string — List of CC recipients
- **bcc**: array of string — List of BCC recipients
- **threadId**: string — Thread ID to reply to
- **inReplyTo**: string — Message ID being replied to

## 3.  a
- **messageId**: string — ID of the email message to retrieve (required)

## 4. search_emails
- **query**: string — Gmail search query (e.g., 'from:example@gmail.com') (required)
- **maxResults**: number — Maximum number of results to return

## 5. modify_email
- **messageId**: string — ID of the email message to modify (required)
- **labelIds**: array of string — List of label IDs to apply
- **addLabelIds**: array of string — List of label IDs to add to the message
- **removeLabelIds**: array of string — List of label IDs to remove from the message

## 6. delete_email
- **messageId**: string — ID of the email message to delete (required)

## 7. list_email_labels
- *(no arguments)*

## 8. batch_modify_emails
- **messageIds**: array of string — List of message IDs to modify (required)
- **addLabelIds**: array of string — List of label IDs to add to all messages
- **removeLabelIds**: array of string — List of label IDs to remove from all messages
- **batchSize**: number (default: 50) — Number of messages to process in each batch

## 9. batch_delete_emails
- **messageIds**: array of string — List of message IDs to delete (required)
- **batchSize**: number (default: 50) — Number of messages to process in each batch

## 10. create_label
- **name**: string — Name for the new label (required)
- **messageListVisibility**: string (enum: show, hide) — Whether to show or hide the label in the message list
- **labelListVisibility**: string (enum: labelShow, labelShowIfUnread, labelHide) — Visibility of the label in the label list

## 11. update_label
- **id**: string — ID of the label to update (required)
- **name**: string — New name for the label
- **messageListVisibility**: string (enum: show, hide) — Whether to show or hide the label in the message list
- **labelListVisibility**: string (enum: labelShow, labelShowIfUnread, labelHide) — Visibility of the label in the label list

## 12. delete_label
- **id**: string — ID of the label to delete (required)

## 13. get_or_create_label
- **name**: string — Name of the label to get or create (required)
- **messageListVisibility**: string (enum: show, hide) — Whether to show or hide the label in the message list
- **labelListVisibility**: string (enum: labelShow, labelShowIfUnread, labelHide) — Visibility of the label in the label list
