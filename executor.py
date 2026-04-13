from telegram import Update
from memory import memory
from actions.eod_action import eod_action
from actions.slack_action import slack_action
from actions.email_action import email_action
from services.email_service import email_service
from services.mention_handler import mention_handler
from config import config
import brain

async def execute(decision: dict, update: Update):
    """Execute the action brain decided on."""
    intent = decision.get("intent")
    action = decision.get("action")
    action_data = decision.get("action_data", {})
    jarvis_response = decision.get("jarvis_response", "")

    # Always send Jarvis's response first
    if jarvis_response:
        await update.message.reply_text(jarvis_response)

    # Execute the action
    if action == "format_eod":
        raw = action_data.get("raw_update", "")
        await update.message.reply_text("⏳ Formatting your EOD...")
        try:
            formatted = await brain.format_eod(raw)
            memory.start_session("eod", {
                "raw_update": raw,
                "slack": formatted["slack"],
                "email": formatted["email"],
                "email_subject": formatted["email_subject"],
                "extra_recipients": [],
                "step": "awaiting_confirmation"
            })
            await update.message.reply_text(f"📋 *Slack Preview:*\n\n{formatted['slack']}", parse_mode="Markdown")
            await update.message.reply_text(f"📧 *Email Preview:*\n\nSubject: {formatted['email_subject']}\n\n{formatted['email']}", parse_mode="Markdown")
            await update.message.reply_text("Looks good? Reply *yes* to send, *no* to cancel, or tell me what to change.", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Error formatting EOD: {str(e)}")

    elif action == "edit_eod":
        instruction = action_data.get("instruction", "")
        original_raw = memory.get_session_data("raw_update")
        await update.message.reply_text("✏️ Updating...")
        try:
            current_slack = memory.get_session_data("slack") or ""
            current_email = memory.get_session_data("email") or ""
            formatted = await brain.reformat_eod(original_raw, instruction, current_slack, current_email)
            memory.update_session("slack", formatted["slack"])
            memory.update_session("email", formatted["email"])
            memory.update_session("email_subject", formatted["email_subject"])
            await update.message.reply_text(f"📋 *Updated Slack:*\n\n{formatted['slack']}", parse_mode="Markdown")
            await update.message.reply_text(f"📧 *Updated Email:*\n\nSubject: {formatted['email_subject']}\n\n{formatted['email']}", parse_mode="Markdown")
            await update.message.reply_text("Looks good? Reply *yes*, *no*, or tell me what else to change.", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Error updating: {str(e)}")

    elif action == "confirm_yes":
        # Move to slack choice — don't send anything yet
        memory.update_session("step", "awaiting_slack_choice")
        await update.message.reply_text(
            "*When should I post to Slack?*\n1. Send now\n2. Schedule for later",
            parse_mode="Markdown"
        )

    elif action == "send_slack_now":
        slack_text = memory.get_session_data("slack")
        await update.message.reply_text("📤 Posting to Slack...")
        try:
            await slack_action.send_now(slack_text)
            memory.log_action("✅ Slack message sent successfully")
            memory.update_session("step", "awaiting_email_choice")
            await update.message.reply_text("✅ Slack message sent!")
            await update.message.reply_text("*What about the email?*\n1. Send now\n2. Schedule for later\n3. Skip", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Slack failed: {str(e)}\nTry again?")

    elif action == "schedule_slack":
        time_str = action_data.get("time_str", "")
        await update.message.reply_text("What time should I post to Slack? (e.g. 6:30 PM)")
        memory.update_session("step", "awaiting_slack_time")

    elif action == "send_slack_scheduled":
        time_str = action_data.get("time_str", "")
        slack_text = memory.get_session_data("slack")
        try:
            unix_ts = await slack_action.schedule(slack_text, time_str)
            from datetime import datetime
            import pytz
            ist = pytz.timezone('Asia/Kolkata')
            scheduled_dt = datetime.fromtimestamp(unix_ts, tz=ist)
            time_formatted = scheduled_dt.strftime('%I:%M %p')
            memory.log_action(f"✅ Slack scheduled for {time_formatted} IST")
            memory.update_session("step", "awaiting_email_choice")
            await update.message.reply_text(f"✅ Slack scheduled for {time_formatted} IST!")
            await update.message.reply_text("*What about the email?*\n1. Send now\n2. Schedule for later\n3. Skip", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Could not schedule Slack: {str(e)}\nTry again with format like '6:30 PM'")

    elif action == "send_email_now":
        email_body = memory.get_session_data("email")
        email_subject = memory.get_session_data("email_subject")
        extra = memory.get_session_data("extra_recipients") or []
        try:
            await email_action.send(email_body, email_subject, extra)
            memory.log_action(f"✅ Email sent to {config.ZOHO_RECIPIENT}" + (f" and {', '.join(extra)}" if extra else ""))
            memory.end_session()
            await update.message.reply_text("🎉 All done! EOD delivered successfully.")
        except Exception as e:
            await update.message.reply_text(f"❌ Email failed: {str(e)}")

    elif action == "email_schedule":
        memory.update_session("step", "awaiting_email_time")
        await update.message.reply_text("What time should I send the email? (e.g. 7:00 PM)")

    elif action == "email_time":
        time_str = action_data.get("time_str", "")
        email_body = memory.get_session_data("email")
        email_subject = memory.get_session_data("email_subject")
        extra = memory.get_session_data("extra_recipients") or []

        try:
            from utils.scheduler import parse_time_to_unix
            unix_ts = parse_time_to_unix(time_str)

            from datetime import datetime
            import pytz
            ist = pytz.timezone('Asia/Kolkata')
            scheduled_dt = datetime.fromtimestamp(unix_ts, tz=ist)
            time_formatted = scheduled_dt.strftime('%I:%M %p')

            email_service.schedule_email(
                body=email_body,
                subject=email_subject,
                unix_timestamp=unix_ts,
                extra_recipients=extra
            )

            memory.log_action(f"✅ Email scheduled for {time_formatted} IST")
            memory.end_session()
            await update.message.reply_text(f"✅ Email scheduled for {time_formatted} IST! All done 🎉")

        except Exception as e:
            await update.message.reply_text(f"❌ Could not schedule email: {str(e)}\nTry again with format like '7:00 PM'")

    elif action == "skip_email":
        memory.log_action("⏭️ Email skipped")
        memory.end_session()
        await update.message.reply_text("👍 Done! Slack posted, email skipped.")

    elif action == "add_recipient":
        email = action_data.get("email", "")
        if email:
            extras = memory.get_session_data("extra_recipients") or []
            extras.append(email)
            memory.update_session("extra_recipients", extras)
            all_recipients = [config.ZOHO_RECIPIENT] + extras
            await update.message.reply_text(f"✅ Added! Email will go to: {', '.join(all_recipients)}")
            # Re-ask current step question
            step = memory.get_session_data("step")
            await _reask_current_step(update, step)

    elif action == "send_ack":
        reply_text = memory.get_session_data("reply_text")
        channel_id = memory.get_session_data("channel_id")
        thread_ts = memory.get_session_data("thread_ts")
        mention_num = memory.get_session_data("mention_num")

        success = await mention_handler.send_ack(channel_id, thread_ts, reply_text)
        if success:
            mention_handler.remove_mention(mention_num)
            memory.end_session()
            await update.message.reply_text("\u2705 Sent!")
        else:
            await update.message.reply_text("\u274c Failed to send. Try again.")

    elif action == "update_ack_reply":
        current_reply = memory.get_session_data("reply_text")
        instruction = action_data.get("instruction", "")
        username = memory.get_session_data("username") or "them"

        await update.message.chat.send_action("typing")
        new_reply = await brain.update_ack_reply(current_reply, instruction)
        memory.update_session("reply_text", new_reply)

        await update.message.reply_text(
            f"\U0001f4dd Updated reply to {username}:\n\n"
            f"\"{new_reply}\"\n\n"
            f"Reply *yes* to send, or tell me what to change.",
            parse_mode="Markdown"
        )

    elif action == "cancel_session":
        memory.end_session()
        await update.message.reply_text("❌ Cancelled. Let me know when you're ready.")

    elif action == "reply_only":
        # Jarvis already replied above, just re-ask current step if in session
        if memory.has_session():
            step = memory.get_session_data("step")
            await _reask_current_step(update, step)


async def _reask_current_step(update: Update, step: str):
    """Re-ask the current step question after answering something."""
    prompts = {
        "awaiting_confirmation": "Looks good? Reply *yes*, *no*, or tell me what to change.",
        "awaiting_slack_choice": "*When should I post to Slack?*\n1. Send now\n2. Schedule for later",
        "awaiting_slack_time": "What time should I post to Slack? (e.g. 6:30 PM)",
        "awaiting_email_choice": "*What about the email?*\n1. Send now\n2. Schedule for later\n3. Skip",
        "awaiting_email_time": "What time should I send the email? (e.g. 7:00 PM)",
    }
    if step in prompts:
        await update.message.reply_text(prompts[step], parse_mode="Markdown")
