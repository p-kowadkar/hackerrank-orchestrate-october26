# intent_classify

Used by `code/llm/reader.py` (`IntentFallback`) only for request texts that the rule-based classifier in
`ghostaudit/intent.py` could not place. Expected to fire for none of the 518 requests; it exists for robustness.

## System

You decide whether a customer's message asks for their personal data to be deleted. The message may be in any language. Answer
with a single JSON object and nothing else.

## Task

Return a JSON object with exactly two keys:

- `label`: `"DELETE"` if the person asks for their account, profile or personal data to be deleted, erased, removed or closed.
  `"NON_DELETE"` for anything else: a request for a copy of their data or an export, access, a correction or update, a
  change of e-mail or phone number, a marketing or newsletter opt-out, a question about an invoice or a login, or a
  message in which the person explicitly says they do not want their account or data deleted.
- `reason`: one short sentence in English quoting the words that decided it.

A marketing opt-out that keeps the account is `NON_DELETE`. A message that asks for both a copy and a deletion is `DELETE`.
