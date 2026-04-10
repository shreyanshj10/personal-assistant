import anthropic
import json
from soul import get_soul
from config import config
from memory import memory

client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

async def think(user_message: str) -> dict:
    """
    Claude reads the full context and decides what to do.
    Returns a structured decision dict.
    """
    soul = get_soul(config)
    session_context = memory.get_session_context()
    current_step = memory.get_session_data("step") or "none"

    # Build the decision prompt
    decision_prompt = f"""
{soul}

## Current Session Context
{session_context if session_context else "No active session."}
Current session step: {current_step}

## Your Task
The user sent: "{user_message}"

Based on everything above, decide what to do. Return ONLY a valid JSON object:

{{
    "intent": "one of: new_eod | edit_eod | confirm_yes | confirm_no | slack_now | slack_schedule | slack_time | email_now | email_schedule | email_time | email_skip | add_recipient | general_chat | cancel",
    "jarvis_response": "what Jarvis says back to the user — conversational, in character",
    "action": "one of: format_eod | confirm_yes | send_slack_now | schedule_slack | send_email_now | email_schedule | email_time | skip_email | add_recipient | reply_only | cancel_session",
    "action_data": {{}}
}}

## Intent Detection Rules
- "new_eod": message starts with EOD: or eod: with actual content after it
- "edit_eod": user wants to change the formatted EOD (e.g. "add feature 2", "change the project name")
- "confirm_yes": user is confirming/approving current step (yes, yeah, yep, sure, ok, 1, send, looks good)
- "confirm_no": user is cancelling (no, nope, cancel, skip for slack choice)
- "slack_now": user wants to send Slack now (1, now, send now) — only during slack choice step
- "slack_schedule": user wants to schedule Slack (2, schedule, later) — only during slack choice step
- "slack_time": user is providing a time for Slack scheduling (e.g. "6:30 PM", "7pm", "18:00")
- "email_now": user wants to send email now (1, now, send now) — only during email choice step
- "email_schedule": user wants to schedule email for later (2, schedule, later) — only during email choice step
- "email_time": user is providing a time for email scheduling (e.g. "7:00 PM", "8pm")
- "email_skip": user wants to skip email (3, skip, no) — only during email choice step
- "add_recipient": user wants to add an email recipient for this send
- "cancel": user wants to cancel everything
- "general_chat": anything else — questions, requests, general conversation

## Action Data Rules
- For format_eod: {{"raw_update": "the raw EOD text after EOD:"}}
- For edit_eod: {{"instruction": "what to change"}}
- For schedule_slack: {{"time_str": "the time user mentioned"}}
- For email_time: {{"time_str": "the time user mentioned"}}
- For add_recipient: {{"email": "extracted email address"}}
- For reply_only: {{}} (just respond conversationally)
- For cancel_session: {{}}

## CRITICAL TIME DETECTION RULE (HIGHEST PRIORITY)
If current session step is "awaiting_slack_time" OR "awaiting_email_time":
- ANY message that looks like a time (contains numbers + am/pm, or HH:MM format) MUST be classified as slack_time or email_time intent
- Examples that MUST be detected: "3:02 pm", "2:32 pm", "6:30 PM", "18:00", "7pm", "9:30am", "3 pm", "7:00 PM"
- Extract the time string and put it in action_data.time_str
- Do NOT ask for confirmation — just set the intent and schedule immediately
- This overrides ALL other intent detection — time messages are NEVER general_chat

## STEP-BASED INTENT RULES (OVERRIDE everything else when a session is active)
- If step is "awaiting_confirmation" and user says yes/y/sure/ok/looks good → intent "confirm_yes", action "confirm_yes"
- If step is "awaiting_slack_choice" and user says 1/now/send/send now → intent "slack_now", action "send_slack_now"
- If step is "awaiting_slack_choice" and user says 2/schedule/later → intent "slack_schedule", action "schedule_slack"
- If step is "awaiting_slack_time" and user provides a time → intent "slack_time", action "send_slack_scheduled"
- If step is "awaiting_email_choice" and user says 1/now/send/send now → intent "email_now", action "send_email_now"
- If step is "awaiting_email_choice" and user says 2/schedule/later → intent "email_schedule", action "email_schedule"
- If step is "awaiting_email_choice" and user says 3/skip/no → intent "email_skip", action "skip_email"
- If step is "awaiting_email_time" and user provides a time → intent "email_time", action "email_time"
- These rules OVERRIDE everything else when a session is active. NEVER skip steps.

## CRITICAL: jarvis_response Rules
Set jarvis_response to EMPTY STRING "" for these intents (executor handles ALL messaging):
- new_eod (executor shows formatted preview)
- edit_eod (executor shows updated preview)
- confirm_yes (executor asks slack choice)
- slack_now (executor sends slack + asks email)
- slack_schedule (executor asks for time)
- slack_time (executor handles scheduling)
- email_now (executor confirms done)
- email_schedule (executor asks for time)
- email_time (executor schedules and confirms)
- email_skip (executor confirms done)

ONLY set jarvis_response for:
- general_chat (your actual conversational reply)
- reply_only (your actual answer)
- add_recipient (brief confirmation)
- confirm_no / cancel (brief cancellation message)

## CRITICAL: Scheduling Response Rules
For slack_time and email_time intents:
- jarvis_response MUST be EMPTY STRING "" — the executor handles the confirmation message
- NEVER ask "do you want me to" or "shall I" — just schedule immediately
- The executor will send the confirmation like "Scheduled for 2:32 PM IST"

## Jarvis Response Rules
- Always respond in character as Jarvis
- Be concise and natural
- If sending/scheduling something, confirm what you're doing
- If answering a question mid-session, answer it then naturally transition back to what needs to be done next
- Never break character
- Never say you cannot do something
"""

    history = memory.get_history()
    messages = history + [{"role": "user", "content": decision_prompt}]

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=messages
    )

    text = response.content[0].text.strip()
    text = text.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fallback to general chat if JSON parsing fails
        return {
            "intent": "general_chat",
            "jarvis_response": text,
            "action": "reply_only",
            "action_data": {}
        }


async def format_eod(raw_update: str) -> dict:
    """Format raw EOD into Slack + Email. Returns dict with slack, email, email_subject."""
    from datetime import datetime
    import pytz
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    today = now.strftime('%d %B %Y')
    soul = get_soul(config)

    prompt = f"""
Format this EOD update into both required formats.

Raw EOD: {raw_update}
Today: {today}

Return ONLY valid JSON, no markdown, no extra text:
{{
    "slack": "full slack message",
    "email": "full email body",
    "email_subject": "Status Update || {today} || {config.YOUR_NAME}"
}}

Slack rules:
- "*Project:*" on its own line (bold with asterisks), then project name(s) on the NEXT line
- Blank line then "*What was done today:*" (bold) then each task as "• task"
- Blank line then "*Blockers:*" (bold) then "• No blockers." or list blockers
- Only these three headers are bold with *asterisks* — task content is plain text

Email rules:
- Start: "Hi Sir," newline "Good Evening." newline "Please have a look at the points below:"
- Each task: "<b>Task N: Title</b>" newline "<b>Status:</b> Done" newline "<b>Details:</b> details"
- Blank line between tasks
- End: "Best Regards," newline "{config.YOUR_NAME}"
- Split every distinct action into a separate numbered task
- Status options: Done / In Progress / Blocked / Not Applicable
"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=soul,
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(text)


async def reformat_eod(original_raw: str, instruction: str, current_slack: str = "", current_email: str = "") -> dict:
    """Re-format EOD after user requests a change."""
    from datetime import datetime
    import pytz
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    today = now.strftime('%d %B %Y')
    soul = get_soul(config)

    prompt = f"""
Here is the CURRENT formatted EOD content:

CURRENT SLACK:
{current_slack}

CURRENT EMAIL:
{current_email}

User's edit instruction: {instruction}

## CRITICAL EDIT RULES
- "Task 2 is in progress" means find the SECOND task and change its Status to "In Progress" — do NOT add new tasks
- "Task N is blocked/in progress/not applicable" means find that numbered task and update ONLY its Status field
- Never add new tasks unless user explicitly says "add a task" or "add another task"
- Never create a new task to represent a status change — just update the existing task's Status field
- Keep task titles, details, and task count exactly the same unless explicitly told to change them
- Only change what the user specifically asked to change
- Everything else stays IDENTICAL

Today: {today}

Return ONLY valid JSON, no markdown:
{{
    "slack": "updated slack message",
    "email": "updated email body",
    "email_subject": "Status Update || {today} || {config.YOUR_NAME}"
}}

Slack format: "*Project:*" (bold) then project name on next line, "*What was done today:*" (bold) then bullet tasks, "*Blockers:*" (bold) then bullets.
Email format: "Hi Sir," then "Good Evening." then tasks with <b>Task N: Title</b>, <b>Status:</b> value, <b>Details:</b> details. End with "Best Regards," and "{config.YOUR_NAME}".
"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=soul,
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(text)
