"""Current and historical identity resolution."""
from __future__ import annotations

from collections import defaultdict

from .tokens import norm_phone


class IdentityError(LookupError):
    pass


class IdentityResolver:
    """Maps a request email (current or historical, any case) to one user and exposes all of the user's tokens."""

    def __init__(self, identities: list, audit_log: list):
        self.users = {r["user_id"]: r for r in identities}
        cur = {r["email"].strip().lower(): r["user_id"] for r in identities}
        old = defaultdict(set)
        self._tokens = defaultdict(set)
        for r in identities:
            uid = r["user_id"]
            self._tokens[uid].update({uid.lower(), r["email"].strip().lower(), r["email_hash"].strip().lower(),
                                      norm_phone(r["phone"])})
        for a in audit_log:
            uid, field, vals = a["user_id"], a["field_name"], (a["old_value"], a["new_value"])
            for v in vals:
                v = v.strip()
                if not v:
                    continue
                if field == "email":
                    self._tokens[uid].add(v.lower())
                elif field == "email_hash":
                    self._tokens[uid].add(v.lower())
                elif field == "phone":
                    self._tokens[uid].add(norm_phone(v))
            if field == "email" and a["old_value"].strip():
                old[a["old_value"].strip().lower()].add(uid)
        self._current = cur
        self._historic = {e: next(iter(u)) for e, u in old.items() if len(u) == 1}
        self._ambiguous_hist = {e for e, u in old.items() if len(u) > 1}
        # token -> users (to detect tokens shared by several users and to find owners)
        self.token_users = defaultdict(set)
        for uid, toks in self._tokens.items():
            for t in toks:
                self.token_users[t].add(uid)

    def resolve(self, email: str):
        """Return (user_id, form) where form is 'current' or 'historical'."""
        e = email.strip().lower()
        if e in self._current:
            return self._current[e], "current"
        if e in self._historic:
            return self._historic[e], "historical"
        raise IdentityError(f"email does not resolve to exactly one user: {email!r}")

    def tokens(self, user_id: str) -> frozenset:
        return frozenset(self._tokens[user_id])

    def usable_tokens(self, user_id: str) -> frozenset:
        """Tokens that belong to this user alone (a token shared with another user would link the wrong person)."""
        return frozenset(t for t in self._tokens[user_id] if len(self.token_users[t]) == 1)
