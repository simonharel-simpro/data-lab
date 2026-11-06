"""Shared English instructions: A, B and C use these same strings and differ only in control structure."""

from typing import Final

CONTEXT: Final = "This week starts Monday November 9, 2026."
GREETING: Final = (
    "Greet the caller as the service desk of a home repair company and say you can book an appointment. "
    "Keep it to one short sentence."
)
ASK_NAME: Final = (
    "Ask for the caller's full name. If it is unusual, ask them to spell it. As soon as you have it, call record_name."
)
ASK_PHONE: Final = (
    "Ask for a callback phone number, then read it back in groups of digits. Once the caller agrees, call record_phone."
)
ASK_ADDRESS: Final = (
    "Ask for the service address: number, street, city and state. Call record_address with what the caller said."
)
ASK_PROBLEM: Final = (
    "Ask what the problem is and classify it as one of plumbing, electrical, hvac, appliance or other. "
    "If the caller describes several, the first one stated wins. Call record_problem with that type."
)
ASK_SLOT: Final = (
    "Ask when the caller wants the visit, then call check_slots and offer at most two of the free slots. "
    "Use the slot id exactly as returned and call choose_slot when the caller picks one."
)
CONFIRM: Final = (
    "Read the whole booking back to the caller and ask them to confirm; call confirm_booking only after a clear yes. "
    "If the caller changes anything, update it with the matching tool (or go back to that step), "
    "then read the whole booking back again."
)
GOODBYE: Final = "Your appointment is booked. Thank you for calling, goodbye."
# Not an instruction: a stand-in user turn so a request never ends on the agent's own message (see arch_b).
CALLER_WAITING: Final = "(The caller is on the line, waiting for your next question.)"
