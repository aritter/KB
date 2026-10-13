"""Administrative semantic registrations; every classification is independent."""
SEMANTICS = {
    'message_acknowledges': ('request','Does this message acknowledge receipt of the request?'),
    'message_requests_info': ('request','Does this message request additional information or documents?'),
    'message_promises': ('request','Does this message promise a future action on the request?'),
    'message_claims_completion': ('request','Does this message claim the requested action has been completed? A vague all-set statement is a claim, not verification.'),
    'evidence_addresses': ('requirement','Does this evidence document the requested appointment or funding outcome, rather than merely acknowledge or promise it?'),
}
PREDICATES = {name: (['message', role], question) for name,(role,question) in SEMANTICS.items()}

# Absence of a statement is not an explicit denial. These choices assess what
# the supplied message says, not whether an external administrative action occurred.
CHOICE_DESCRIPTIONS = {
    'message_acknowledges': {
        'supported': 'The sender says they received the request.',
        'contradicted': 'The sender explicitly says they have not received the request.',
        'insufficient_evidence': 'The message does not establish whether the sender received the request.'},
    'message_requests_info': {
        'supported': 'The sender asks for additional information or documents for the request.',
        'contradicted': 'The sender explicitly says no additional information or documents are needed.',
        'insufficient_evidence': 'The message does not establish whether additional information or documents are needed.'},
    'message_promises': {
        'supported': 'The sender commits to taking a future action on the request.',
        'contradicted': 'The sender explicitly refuses or says they will not take action on the request.',
        'insufficient_evidence': 'The message makes no clear commitment or refusal to take future action.'},
    'message_claims_completion': {
        'supported': 'The sender says the requested action is complete, including an all-set statement in reply to the request. This is a claim, not proof.',
        'contradicted': 'The sender explicitly says the requested action is not complete or has not been done yet.',
        'insufficient_evidence': 'The message does not establish whether the sender claims completion; acknowledgment or a future promise alone is insufficient.'},
    'evidence_addresses': {
        'supported': 'The supplied document records the appointment or funding outcome and provides concrete details relevant to the evidence requirement. Exact field correctness is checked separately.',
        'contradicted': 'The supplied text explicitly says it is not confirmation of the requested appointment or funding outcome.',
        'insufficient_evidence': 'The text merely acknowledges, promises, or vaguely claims completion, or lacks enough information to identify it as outcome documentation.'},
}
