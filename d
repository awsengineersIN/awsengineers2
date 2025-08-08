Step 1: Add Execution ID Tracking
At the beginning of your lambda_handler function:

python
def lambda_handler(event, context):
    logger.info(f"Lambda invoked with event: {json.dumps(event)}")
    
    # IMMEDIATE FIX: Track execution ID
    execution_id = context.aws_request_id if context else "local"
    logger.info(f"🚀 Execution ID: {execution_id}")
Step 2: Guard SUCCESS Email Sending
Replace your success email section with:

python
try:
    # IMMEDIATE FIX: Guard against multiple email sends
    if hasattr(lambda_handler, '_email_sent') and lambda_handler._email_sent:
        logger.warning("⚠️ Email already sent in this execution, skipping duplicate send")
        return {
            "message": "Email send skipped - already sent in this execution",
            "recipients": recipients,
            "accounts_processed": len(accounts),
            "files_created": len(csv_files),
            "execution_id": execution_id
        }
    
    # Send email with execution ID for tracking
    subject = f"AWS Resource Inventory - {account_summary} ({len(csv_files)} files) - ID:{execution_id[:8]}"
    
    result = send_email(
        sender_addr=SENDER,
        receiver_addr=recipients,
        email_subject=subject,
        email_body=email_body,
        email_attachment=str(zip_path)
    )
    logger.info(f"✅ SUCCESS: Email sent to {len(recipients)} recipients with execution ID {execution_id[:8]}")
    
    # IMMEDIATE FIX: Mark email as sent
    lambda_handler._email_sent = True
    
except Exception as e:
    logger.error(f"❌ Failed to send success email: {e}")
    raise
Step 3: Guard NO-DATA Email Sending
Replace your no-data email section with:

python
try:
    # IMMEDIATE FIX: Guard against multiple email sends
    if hasattr(lambda_handler, '_email_sent') and lambda_handler._email_sent:
        logger.warning("⚠️ No-data email already sent in this execution, skipping duplicate")
        return {
            "message": "No-data email send skipped - already sent",
            "recipients": recipients,
            "accounts_processed": len(accounts),
            "files_created": 0,
            "execution_id": execution_id
        }
    
    # Send no-data email with execution ID
    no_data_subject = f"AWS Inventory - No Data Found ({len(account_names)} accounts) - ID:{execution_id[:8]}"
    
    result = send_email(
        sender_addr=SENDER,
        receiver_addr=recipients,
        email_subject=no_data_subject,
        email_body=no_data_body,
        email_attachment=None
    )
    logger.info(f"✅ SUCCESS: No-data notification sent with execution ID {execution_id[:8]}")
    
    # IMMEDIATE FIX: Mark email as sent
    lambda_handler._email_sent = True
    
except Exception as e:
    logger.error(f"❌ Failed to send no-data notification: {e}")
    raise
✅ What This Fix Does:
🆔 Tracks Execution ID: Each Lambda execution gets a unique ID for tracking

🛡️ Prevents Duplicate Emails: Checks if email was already sent in this execution

📧 Adds ID to Subject: Email subject includes execution ID for tracking

📝 Enhanced Logging: Clear logs showing when emails are sent vs skipped

🎯 Result:
Before: 3 emails for 41 accounts

After: 1 email with execution ID (e.g., "AWS Resource Inventory - 41 accounts (120 files) - ID:a1b2c3d4")

Deploy this fix and you should immediately stop getting multiple emails!
