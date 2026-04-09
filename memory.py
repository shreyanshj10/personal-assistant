from datetime import datetime

class Memory:
    def __init__(self):
        self.conversation = []       # Full conversation history
        self.session = {}            # Current active session state
        self.actions_taken = []      # Actions completed in current session

    def add_message(self, role: str, content: str):
        self.conversation.append({"role": role, "content": content})
        # Keep last 30 messages
        if len(self.conversation) > 30:
            self.conversation = self.conversation[-30:]

    def get_history(self) -> list:
        return self.conversation.copy()

    # Session management
    def start_session(self, session_type: str, data: dict = {}):
        self.session = {"type": session_type, "data": data}
        self.actions_taken = []

    def has_session(self) -> bool:
        return bool(self.session)

    def get_session(self) -> dict:
        return self.session

    def update_session(self, key: str, value):
        self.session["data"][key] = value

    def get_session_data(self, key: str):
        return self.session.get("data", {}).get(key)

    def end_session(self):
        self.session = {}
        self.actions_taken = []

    # Action tracking
    def log_action(self, action: str):
        self.actions_taken.append(action)

    def get_actions(self) -> list:
        return self.actions_taken.copy()

    def get_session_context(self) -> str:
        if not self.session:
            return ""
        actions = self.actions_taken
        data = self.session.get("data", {})
        ctx = f"\n[Active session: {self.session.get('type', 'unknown')}"
        if actions:
            ctx += f"\nCompleted actions: {', '.join(actions)}"
        if data.get("extra_recipients"):
            ctx += f"\nExtra recipients for this send: {', '.join(data['extra_recipients'])}"
        ctx += "]"
        return ctx

memory = Memory()
