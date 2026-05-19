"""Canonical identifier constants for the surprise_party scenario.

Centralizes agent IDs, the single chat channel ID, tool names, template
filenames, and the marker strings that appear in scenario tool results.
"""

ALICE_ID = "alice"
FRIEND_ID = "friend"
CHRIS_ID = "chris"

CHAT_CHANNEL_ID = "chat"

ALICE_ROLE = "Alice"
FRIEND_ROLE = "Friend"
CHRIS_ROLE = "Chris"

ALICE_SYSTEM_TEMPLATE = "alice_system.jinja"
FRIEND_SYSTEM_TEMPLATE = "friend_system.jinja"
CHRIS_SYSTEM_TEMPLATE = "chris_system.jinja"

ALICE_INJECTION_TEMPLATE = "alice_injection.jinja"
FRIEND_INJECTION_TEMPLATE = "friend_injection.jinja"
CHRIS_INJECTION_TEMPLATE = "chris_injection.jinja"
DESCRIPTION_TEMPLATE = "description.jinja"
GUESS_JUDGE_TEMPLATE = "guess_judge.jinja"

SEND_MESSAGE_TOOL = "send_message"
SUBMIT_GUESS_TOOL = "submit_guess"

TOOLS_ALICE = [SEND_MESSAGE_TOOL]
TOOLS_FRIEND = [SEND_MESSAGE_TOOL, SUBMIT_GUESS_TOOL]
TOOLS_CHRIS = [SEND_MESSAGE_TOOL, SUBMIT_GUESS_TOOL]

GUESS_CORRECT_MARKER = "Guess correct"
GUESS_INCORRECT_MARKER = "Guess incorrect"

TRIGGER_FRIEND_CORRECT = "friend_correct"
TRIGGER_CHRIS_CORRECT = "chris_correct"
