from datetime import datetime, timedelta
import pytz

def parse_time_to_unix(time_str: str) -> int:
    """Convert '6:30 PM' or '18:30' to Unix timestamp in IST."""
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)

    # Try multiple formats
    formats = ["%I:%M %p", "%I %p", "%H:%M", "%I:%M%p", "%I%p"]
    parsed = None
    for fmt in formats:
        try:
            parsed = datetime.strptime(time_str.strip().upper(), fmt)
            break
        except ValueError:
            continue

    if not parsed:
        raise ValueError(f"Could not parse time: {time_str}")

    # Combine with today's date
    scheduled = now.replace(hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0)

    # If time has passed, schedule for tomorrow
    if scheduled <= now:
        scheduled += timedelta(days=1)

    return int(scheduled.timestamp())
