"""Does the request actually authorize deletion?

Sentence-level, multilingual, negation-aware. Anything it cannot place is UNCLEAR and is routed to the LLM
fallback by the caller (see llm/). The text is the primary signal; CLASSIFY_REQUEST events only corroborate.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

DELETE, NON_DELETE, UNCLEAR = "DELETE", "NON_DELETE", "UNCLEAR"

# deletion verbs / nouns by language (stems; matched on word starts for latin scripts, substrings for CJK)
_DEL_LATIN = (
    r"delet", r"erase", r"erasure", r"remov", r"wipe", r"purge", r"destroy", r"close (?:my|this|the) account",
    r"closed? (?:my|this|the) account", r"account closure", r"forget me", r"terminate (?:my|this|the) account",
    r"elimin", r"borr", r"cerrar (?:mi|la) cuenta", r"suppress", r"supprim", r"effac", r"fermer (?:mon|le) compte",
    r"exclus", r"exclu", r"apag", r"encerr", r"lösch", r"entfern", r"cancel(?:ar|ler)? (?:mi|mon|a minha|la) ",
)
_DEL_CJK = ("삭제", "削除", "消去", "삭제해", "탈퇴")
_DEL_RE = re.compile(r"\b(?:" + "|".join(_DEL_LATIN) + r")", re.I)
# a request to confirm that the data is already gone is a deletion audit, even without a deletion verb
_GONE_RE = re.compile(r"\b(?:is|are|was|were|been|has been|have been) gone\b", re.I)

# words that negate a deletion verb when they appear shortly before it
_NEG_WORDS = {"not", "n't", "no", "never", "without", "dont", "don't", "cannot", "can't", "neither", "nor",
              "instead", "nunca", "sin", "pas", "jamais", "sem", "nicht", "ohne"}
_NEG_PHRASES = (
    r"not (?:asking|requesting|looking|wanting) (?:for|to) (?:a |the )?(?:delet|eras|remov)",
    r"not a request to (?:delet|eras|remov)",
    r"(?:do not|don't|please do not|please don't) (?:delete|erase|remove|close)",
    r"without (?:delet|eras|remov)",
)
# a removal that only concerns marketing is an opt-out, not a deletion request
_OPT_OUT = re.compile(r"\b(?:marketing|promotional|promotions|newsletter|newsletters|mailing list|mailing lists|"
                      r"advertis\w*|unsubscribe|bolet[ií]n|promocion\w*|publicidad|publicit\w*|promotionnel\w*|"
                      r"werbung|werbe\w*|propaganda|promo[cç][oõ]es)\b", re.I)
# explicit non-deletion actions (used only to label NON_DELETE when there is no affirmative deletion request)
_NON_DEL_ACTION = re.compile(
    r"\b(?:update|replace|change|correct|fix|misspell\w*|reset\w*|copy|download\w*|export|portable|access|"
    r"what personal information|information request|invoices?|opt[- ]?out|stop the|unsubscribe|out of date)\b", re.I)
# the same actions in the other request languages seen in the data (es, fr) and the likely ones (pt, de)
_NON_DEL_OTHER = re.compile(
    r"\b(?:copia (?:de )?(?:todos )?(?:mis|los|sus) datos|enviar(?:me|nos)? (?:una )?copia|acceder a (?:mis|los) datos|"
    r"acceso a (?:mis|los) datos|corregir|actualizar|cambiar (?:mi|el) \w+|descargar|exportar|dejar de recibir|darme de baja|"
    r"copie de (?:toutes )?(?:mes|les) donn[ée]es|envoyer(?:-moi)? une copie|acc[ée]der [àa] mes donn[ée]es|"
    r"droit d'acc[èe]s|corriger|rectifier|mettre [àa] jour|modifier (?:mon|ma|mes)|t[ée]l[ée]charger|exporter|ne plus recevoir|"
    r"me d[ée]sabonner|d[ée]sinscri\w*|c[óo]pia (?:de |dos )?(?:todos )?(?:os )?(?:meus )?dados|enviar uma c[óo]pia|"
    r"acessar|acesso aos meus|atualizar|alterar|baixar|parar de receber|kopie meiner daten|auskunft|korrigier\w*|"
    r"aktualisier\w*|[äa]ndern|herunterlad\w*|exportier\w*|abmelden)\b", re.I)
_AFFIRM_KEEP = re.compile(r"\b(?:keep|leave|retain|continue using|still (?:need|use|want)|conservar|mantener|garder|conserver|"
                          r"manter|behalten)\b", re.I)


@dataclass(frozen=True)
class Intent:
    label: str          # DELETE | NON_DELETE | UNCLEAR
    reason: str         # short machine-readable cue, for the run report


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text).replace("’", "'").replace("‘", "'")


def _sentences(text: str) -> list:
    return [s.strip() for s in re.split(r"(?<=[.!?。！？])\s+|\n+", text) if s.strip()]


def _negated(sentence: str, start: int) -> bool:
    before = sentence[max(0, start - 60):start].lower()
    tokens = re.findall(r"[a-zà-ÿ']+", before)[-5:]
    return any(t in _NEG_WORDS or t.endswith("n't") for t in tokens)


def classify_text(request_text: str) -> Intent:
    text = _norm(request_text)
    affirmative, negated, opt_out = [], [], []
    for sent in _sentences(text):
        low = sent.lower()
        cjk = [c for c in _DEL_CJK if c in sent]
        matches = list(_DEL_RE.finditer(low))
        if _GONE_RE.search(low) and not matches:
            affirmative.append(sent)
            continue
        if not matches and not cjk:
            continue
        neg_spans = [m.span() for p in _NEG_PHRASES for m in re.finditer(p, low)]
        live = [m for m in matches if not _negated(low, m.start())
                and not any(a <= m.start() < b for a, b in neg_spans)]
        if not live and not cjk:
            negated.append(sent)
            continue
        if _OPT_OUT.search(low) and re.search(r"\b(?:only|just|from|lists?|emails?)\b", low):
            opt_out.append(sent)
            continue
        affirmative.append(sent)
    if affirmative:
        return Intent(DELETE, "affirmative deletion request")
    if negated or opt_out:
        return Intent(NON_DELETE, "deletion explicitly negated or limited to marketing opt-out")
    if _NON_DEL_ACTION.search(text) or _NON_DEL_OTHER.search(text) or _AFFIRM_KEEP.search(text):
        return Intent(NON_DELETE, "non-deletion action requested")
    return Intent(UNCLEAR, "no recognised deletion or non-deletion cue")
