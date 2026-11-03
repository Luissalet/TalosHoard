"""Meeting -> commitments, proposals, open questions, decisions and requirements, by plain linguistic rules.

No model is involved. Every utterance of a transcript is cut into sentences and clauses and each clause is labelled with
one of five kinds, always with the exact words that triggered the label (the *cue*), the rule that matched and a
confidence. The same rules run for Spanish and English (modal verbs, conditionals, interrogatives, explicit decision
markers); a clause that matches nothing produces nothing.

* ``commitment``  a firm promise: first-person future or "I take it" forms, or a named person who will do something.
  Owner, counterpart and due date are read only when the words say them. Anything hedged or conditional is NOT a
  commitment: "podríamos", "could", "maybe we", "intentaré", "if you ... I'll ..." are proposals.
* ``proposal``    "podríamos", "we could", "maybe", "what if", "I suggest", conditionals, soft promises.
* ``question``    open question; ``addressee`` says who has to answer when the words say it.
* ``decision``    an explicit marker of agreement ("hemos decidido", "we agreed", "let's go with"); a negated or pending
  decision ("todavía no hemos decidido") is not one.
* ``requirement`` what the deliverable must do ("debe", "tiene que", "must", "needs to be").

Every item points at its source segment (``segment`` and ``playback``: start/end seconds and the transcript text) so it
can be played back. Requirements and decisions can be tied to an engagement's deliverable or decision by a free external
reference (:class:`RequirementLinks`); this module is not a CRM and stores nothing else.
"""

from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable

from .due_dates import resolve_due

KINDS = ("commitment", "proposal", "question", "decision", "requirement")
LINK_KINDS = ("deliverable", "decision")
LINKABLE = ("requirement", "decision")
RULES_VERSION = 1

# ---------------------------------------------------------------------------------------------------- folding


def _fold_char(ch: str) -> str:
    if ch in "’‘`´":
        return "'"
    decomposed = unicodedata.normalize("NFD", ch)
    base = decomposed[0] if decomposed else ch
    base = base.lower()
    return base[0] if base else ch


def fold(text: str) -> str:
    """Lower-case and accent-free, one output character per input character (so offsets still point into the original)."""
    return "".join(_fold_char(c) for c in text)


def hms(seconds: float) -> str:
    total = int(max(0, seconds))
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# ---------------------------------------------------------------------------------------------------- rule tables


@dataclass(frozen=True)
class Rule:
    id: str
    kind: str
    lang: str
    pattern: re.Pattern
    confidence: float
    fold: bool = True  # False: the pattern runs on the original text (accents and capitals matter)

    def search(self, original: str, folded: str):
        return self.pattern.search(folded if self.fold else original)


def _r(id_: str, kind: str, lang: str, pattern: str, confidence: float, fold_: bool = True) -> Rule:
    return Rule(id_, kind, lang, re.compile(pattern, 0 if fold_ else re.IGNORECASE), confidence, fold_)


_VERB_ES = r"[a-z]{3,}"
_INF_ES = r"[a-z]{2,}(?:ar|er|ir)(?:me|te|se|lo|la|los|las|le|les|nos|os)?"

DECISION_RULES = [
    _r("es.decision.decidido", "decision", "es", r"\bdecidid[oa]s?\b", 0.9),
    _r("es.decision.decidimos", "decision", "es", r"\bdecidimos\b", 0.9),
    _r("es.decision.acordado", "decision", "es", r"\b(?:hemos acordado|queda acordado|esta acordado|quedo acordado|ha quedado acordado|acordado:|acordamos)\b", 0.9),
    _r("es.decision.quedamos_en_que", "decision", "es", r"\bquedamos en que\b", 0.85),
    _r("es.decision.queda_asi", "decision", "es", r"\b(?:queda asi|lo hacemos asi|queda cerrado|nos quedamos con|vamos con (?:la |el )?(?:opcion|propuesta|plan|alternativa|version)|adelante con|nos decantamos por|optamos por|elegimos|aprobamos|aprobado|la decision es|decision (?:tomada|final))\b", 0.8),
    _r("en.decision.we_decided", "decision", "en", r"\bwe(?:'ve| have| had)? (?:all )?(?:decided|agreed)\b", 0.9),
    _r("en.decision.its_decided", "decision", "en", r"\b(?:it|that)(?:'s| is| has been|'s been) (?:been )?(?:decided|agreed|settled|approved)\b", 0.9),
    _r("en.decision.the_decision", "decision", "en", r"\b(?:the )?(?:final )?decision is\b|\bdecision made\b|\bfinal decision\b", 0.85),
    _r("en.decision.go_with", "decision", "en", r"\b(?:let's go with|we'll go with|we will go with|we're going with|we are going with|going ahead with|we'll proceed with|we'll stick with|approved)\b", 0.8),
    _r("en.decision.agreed_start", "decision", "en", r"^(?:ok(?:ay)?,? |so,? |right,? )?(?:agreed|decided)\b", 0.8),
]

# decisions that are negated, pending or conditional: looked for in the three words before the cue and the two after it
_GUARD_BEFORE = {"no", "nunca", "todavia", "aun", "sin", "pendiente", "pendientes", "si", "until", "not", "never", "yet", "still", "n't", "if", "unless", "whether",
                 "falta", "faltan", "once", "should", "must", "need", "needs", "tbd", "hasn't", "haven't", "hadn't", "wasn't", "isn't", "didn't", "cuando", "when"}
_GUARD_AFTER = {"todavia", "aun", "pendiente", "yet", "still", "pending"}


PROPOSAL_RULES = [
    _r("es.proposal.podriamos", "proposal", "es", r"\b(?:podriamos|podria|podrian)\b", 0.88),
    _r("es.proposal.quiza", "proposal", "es", r"\b(?:quiza|quizas|tal vez|a lo mejor|igual (?:podemos|podriamos|deberiamos|lo))\b", 0.85),
    _r("es.proposal.y_si", "proposal", "es", r"(?:^|\W)y si\b|\bque tal si\b|\bsi quieres\b|\bsi os parece\b|\bsi te parece\b", 0.8),
    _r("es.proposal.propongo", "proposal", "es", r"\b(?:propongo|proponemos|sugiero|sugerimos|sugerencia|mi propuesta|una propuesta)\b", 0.88),
    _r("es.proposal.deberiamos", "proposal", "es", r"\b(?:deberiamos|convendria|estaria bien|seria bueno|seria mejor|habria que|me gustaria|nos vendria bien)\b", 0.8),
    _r("es.proposal.opcion", "proposal", "es", r"\b(?:una opcion|otra opcion|una alternativa|otra alternativa|una idea|otra idea|se podria|podemos probar|podemos intentar)\b", 0.8),
    _r("es.proposal.podemos", "proposal", "es", r"\bpodemos\b", 0.55),
    _r("es.proposal.soft_promise", "proposal", "es", r"\b(?:intentare|tratare de|probablemente|supongo que|creo que (?:podre|puedo|llego)|a ver si|puede que|igual me da tiempo|si me da tiempo|si puedo)\b", 0.78),
    _r("es.proposal.conditional_start", "proposal", "es", r"^[Ss]i\s+[^,]{2,}(?=,\s*\S)", 0.8, fold_=False),
    _r("es.proposal.conditional_mid", "proposal", "es", r"(?<![\w])[Ss]i\s+(?:me|te|nos|le|os|lo|la|puedes|puedo|podemos|tienes|tengo|tenemos|hay|no|se|tú|yo|vosotros|usted)\b|\ba menos que\b|\bsiempre que\b|\bsiempre y cuando\b|\bsalvo que\b", 0.78, fold_=False),
    _r("en.proposal.could", "proposal", "en", r"\b(?:we could|could we|we might|might be|we may|it could|this could|that could|could be)\b|\bcould\b(?! you\b)", 0.88),
    _r("en.proposal.maybe", "proposal", "en", r"\b(?:maybe|perhaps|possibly)\b", 0.85),
    _r("en.proposal.what_if", "proposal", "en", r"\b(?:what if|how about|why don't we|why not|what about)\b", 0.85),
    _r("en.proposal.suggest", "proposal", "en", r"\bi(?:'d| would)? (?:suggest|propose|recommend)\b|\bmy suggestion\b|\bmy proposal\b|\bi was thinking\b", 0.88),
    _r("en.proposal.should", "proposal", "en", r"\bwe should\b|\bit would be (?:nice|good|great|better|worth)\b|\bwould be nice\b", 0.65),
    _r("en.proposal.option", "proposal", "en", r"\b(?:one option|an option|another option|one idea|another idea|alternatively|let's try|we can try|let's consider|we can consider)\b", 0.8),
    _r("en.proposal.soft_promise", "proposal", "en", r"\bi(?:'ll| will) (?:try|probably|maybe|see|think)\b|\bi'll try\b|\bprobably\b|\bi guess\b|\bif i can\b|\bif i have time\b|\bwe'll see\b", 0.78),
    _r("en.proposal.conditional", "proposal", "en", r"^if\b[^,]*(?=,\s*\S)|\b(?:if you|if we|if they|if i|unless|provided that|as long as|only if|assuming)\b", 0.78),
]

COMMITMENT_RULES = [
    # strong, explicit
    _r("es.commitment.prometo", "commitment", "es", r"\b(?:me comprometo|prometo|te lo prometo|doy mi palabra|cuenta conmigo|me responsabilizo)\b", 0.92),
    _r("en.commitment.promise", "commitment", "en", r"\bi (?:promise|commit|guarantee)\b|\byou have my word\b|\bcount on me\b", 0.92),
    # taking something on
    _r("es.commitment.me_encargo", "commitment", "es", r"\b(?:me encargo|nos encargamos|me ocupo|nos ocupamos|me hago cargo|nos hacemos cargo|yo me encargo|lo hago yo|yo lo hago|lo llevo yo|yo lo llevo|me lo quedo)\b", 0.85),
    _r("es.commitment.lo_hare", "commitment", "es", r"\b(?:lo hare|lo haremos|lo tendre|lo tendremos|lo envio yo|lo mando yo|lo preparo yo|lo reviso yo)\b", 0.85),
    _r("es.commitment.lo_hago", "commitment", "es", r"\blo (?:hago|envio|mando|preparo|reviso|paso|tengo|termino|cierro|subo|confirmo|entrego|redacto|miro)\b", 0.7),
    _r("es.commitment.voy_a", "commitment", "es", rf"\bvoy a (?!ver\b|pensar\b|intentar\b|mirar si\b){_INF_ES}\b", 0.8),
    _r("es.commitment.vamos_a", "commitment", "es", rf"\bvamos a (?!ver\b|pensar\b|intentar\b|mirar\b){_INF_ES}\b", 0.7),
    _r("es.commitment.te_envio", "commitment", "es", r"\b(?:te|os|le|les) (?:lo |la |los |las )?(?:envio|mando|paso|escribo|llamo|confirmo|preparo|traigo|entrego|reenvio|comparto|aviso|cuento)\b", 0.82),
    _r("es.commitment.yo_verbo", "commitment", "es", r"\byo (?:(?:te|os|le|les|lo|la|los|las) )?(?:envio|mando|preparo|llamo|reviso|hago|paso|traigo|escribo|confirmo|entrego|subo|contacto|cierro|termino|actualizo|redacto|comparto|agendo|reservo|pago|compro|instalo|despliego|pruebo|coordino|organizo|miro|busco|investigo)\b", 0.8),
    _r("es.commitment.futuro_acento", "commitment", "es", r"\b(?!podr|sabr|habr|ser\b|estar|querr|vendr)[a-zñ]+[aei]r[eé]\b", 0.82, fold_=False),
    _r("es.commitment.futuro_sin_acento", "commitment", "es", r"\b(?:enviare|mandare|hare|preparare|revisare|llamare|pasare|confirmare|entregare|tendre|escribire|subire|cerrare|terminare|compartire|avisare|reservare|contactare|redactare|actualizare|pagare|comprare)\b", 0.8),
    _r("es.commitment.tengo_que", "commitment", "es", r"\b(?:tengo que|debo|he de|me toca)\s+[a-z]{2,}", 0.65),
    _r("en.commitment.ill", "commitment", "en", r"\bi(?:'ll| will| shall) (?:take care|handle|own|do|send|prepare|review|call|write|follow up|get back|set up|share|book|schedule|fix|update|check|confirm|draft|finish|deliver|submit|ship|make sure|look into|take|get|have|put|forward|email|ping|ask|open|create|add|talk|reach|build|test|pay|buy|order|arrange)\b", 0.85),
    _r("en.commitment.going_to", "commitment", "en", r"\bi(?:'m| am) going to (?!try\b|see\b|think\b)\w+", 0.8),
    _r("en.commitment.let_me", "commitment", "en", r"\b(?:let me (?:send|prepare|handle|check|take|do|review|get|look)|i(?:'m| am) on it|i can take (?:that|this|it)|i'll take (?:that|this|it)|leave it to me|i(?:'ve| have) got (?:it|this|that)|that's on me|on me)\b", 0.82),
    _r("en.commitment.well", "commitment", "en", r"\bwe(?:'ll| will) (?:send|prepare|deliver|ship|review|have|handle|take care|do|write|share|get|schedule|set up|follow up|fix|update|confirm|finish)\b|\bwe(?:'re| are) going to (?!see\b|think\b|try\b)\w+", 0.75),
    _r("en.commitment.ill_generic", "commitment", "en", r"\bi(?:'ll| will) (?!try\b|see\b|think\b|probably\b|maybe\b|perhaps\b|be\b|let\b)\w+", 0.7),
    _r("en.commitment.have_to", "commitment", "en", r"\bi (?:have to|must|need to|gotta) \w+", 0.6),
]

# a named person who will do something ("Marta enviará el informe", "Pedro will send the draft")
_NAME = r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?"
_NOT_NAMES = {"the", "this", "that", "it", "we", "they", "he", "she", "you", "i", "there", "el", "la", "eso", "esto", "y", "pero", "entonces", "then",
              "so", "and", "but", "yes", "no", "vale", "ok", "okay", "perfecto", "bueno", "si", "sí", "tu", "tú", "yo", "nosotros", "ellos", "ella", "él",
              "ahora", "now", "also", "luego", "después", "despues", "one", "someone", "alguien", "nadie", "everyone", "todos", "nobody", "what", "who", "when"}
_THIRD_ES = re.compile(rf"^(?P<name>{_NAME})\s+(?:se (?:encarga|encargará|ocupa|ocupará|hace cargo|hará cargo)|(?!podrá\b|sabrá\b|habrá\b|será\b|estará\b|querrá\b|vendrá\b|tendrá que\b)[a-záéíóúñ]{{2,}}(?:ará|erá|irá)\b|va a (?!ver\b|pensar\b)[a-záéíóúñ]+(?:ar|er|ir)\b|lo (?:hará|enviará|preparará|revisará))")
_THIRD_EN = re.compile(rf"^(?P<name>{_NAME})\s+(?:will|'ll|is going to|is gonna|has agreed to|agreed to|owns|takes|is taking care of|will take care of)\s+(?!be\b|see\b|think\b|probably\b|maybe\b|need\b|have\b|likely\b)(?P<rest>\w+)")

REQUIREMENT_RULES = [
    _r("es.requirement.debe", "requirement", "es", r"\b(?:debe|deben|debera|deberan|tiene que|tienen que|tendra que|tendran que|ha de|han de|habra de)\b", 0.82),
    _r("es.requirement.necesario", "requirement", "es", r"\b(?:es necesario|es imprescindible|es obligatorio|hace falta|se necesita|se requiere|se exige|imprescindible|obligatori[oa]s?|indispensable|requisito|requisitos|necesitamos que|necesita (?:que|poder|ser|tener|soportar|permitir)|necesitan (?:que|poder|ser|tener|soportar|permitir))\b", 0.8),
    _r("es.requirement.permita", "requirement", "es", r"\b(?:que permita|que permitan|que soporte|que admita|que pueda|que sea capaz|debe poder|tiene que poder|tiene que ser|tiene que estar|no puede|no debe|no debera|no tiene que|que no tarde|capaz de)\b", 0.78),
    _r("es.requirement.necesitamos", "requirement", "es", r"\b(?:necesitamos|necesitaremos|queremos que|queremos un|queremos una|quiero que)\b", 0.55),
    _r("es.requirement.deberia", "requirement", "es", r"\b(?:deberia|deberian)\b", 0.55),
    _r("en.requirement.must", "requirement", "en", r"\b(?:must not|must|shall not|shall|is a must|are a must)\b", 0.85),
    _r("en.requirement.needs_to", "requirement", "en", r"\b(?:it|this|that|they|the \w+(?: \w+)?|each \w+|every \w+|users?|customers?|clients?) (?:needs? to|has to|have to|need to|has got to)\b|\bneeds? to be\b|\bhas to be\b", 0.8),
    _r("en.requirement.required", "requirement", "en", r"\b(?:required|requirement|requirements|mandatory|a hard requirement|non-negotiable|is essential|essential that)\b", 0.8),
    _r("en.requirement.should_be_able", "requirement", "en", r"\b(?:should be able to|should support|should allow|should let|has to support|needs to support|should handle|should not|shouldn't)\b", 0.7),
    _r("en.requirement.we_need", "requirement", "en", r"\bwe need (?:a|an|the|it|them|this|that|to)\b|\bwe want (?:it|a|an|the|users)\b|\bwe have to\b|\bwe must\b", 0.55),
]

# Without a question mark (speech recognition often drops it) only forms that cannot start a statement count as questions.
_Q_ES_ACCENT = re.compile(r"^[¿\s]*(?:y |pero |entonces |vale,? |bueno,? |oye,? |perdona,? )?(?:qué|quién|quiénes|cuándo|cómo|cuál|cuáles|cuánto|cuánta|cuántos|cuántas|dónde|adónde|por qué|para qué)\b", re.IGNORECASE)
_Q_ES_VERB = re.compile(r"^[¿\s]*(?:y |pero |entonces |vale,? |bueno,? |oye,? |perdona,? )?(?:puedes|podrias|podeis|podrian|puede usted|alguien|te parece|os parece|le parece|se puede|se podria)\b")
_Q_EN = re.compile(r"^(?:and |but |so |ok,? |okay,? |well,? |hey,? |sorry,? )?(?:(?:what|who|whom|when|where|why|how|which)\s+(?:is|are|was|were|do|does|did|can|could|would|will|should|shall|has|have|about|else|time|many|much)|"
                   r"can you|could you|would you|will you|can we|could we|should we|shall we|do you|did you|do we|have you|has anyone|is it|is there|are you|are we|are there|any(?:one|body) (?:know|have|got|can)|does anyone)\b")
_TAG_Q = re.compile(r",?\s*¿?(?:vale|ok|okay|no|verdad|de acuerdo|te parece|eh|right|yeah|alright|yes|sí|si)\s*\?+\s*$", re.IGNORECASE)
_ADDRESSEE_2P = re.compile(r"\b(?:tu|vosotros|ustedes|usted|puedes|podrias|podeis|tienes|sabes|has|habeis|quieres|crees|piensas|opinas|te parece|os parece|le parece|you|your|can you|could you|would you|do you|did you|have you|will you|are you)\b")
_ADDRESSEE_GROUP = re.compile(r"\b(?:podemos|podriamos|tenemos|deberiamos|debemos|hacemos|vamos|we|shall we|should we|can we|could we|do we|are we)\b")
_VOCATIVE = re.compile(rf"^(?:y |pero |vale,? |ok,? |oye,? |so |and |hey,? )?(?P<name>{_NAME})\s*[,:]\s")
_VOCATIVE_END = re.compile(rf",\s*(?P<name>{_NAME})\s*\?*\s*$")
_ASKED_ABOUT = re.compile(rf"\b(?:opina|piensa|sabe|tiene|puede|podria|think|know|knows|have|has|can|could|does|did|will|would)\s+(?P<name>{_NAME})\b")

# ---------------------------------------------------------------------------------------------------- dates

_WD_ES = r"(?:lunes|martes|miercoles|jueves|viernes|sabado|domingo)"
_WD_EN = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|tues|wed|thu|thurs|fri)"
_MONTH = r"(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre|january|february|march|april|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)"
_NUM = r"(?:\d{1,3}|un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|quince|veinte|a|an|one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty)"
DATE_PATTERNS = [
    re.compile(rf"\b(?:(?:para|antes del?|hasta|by|before|until|on|for|next|this|el proximo|el|este|la proxima)\s+)?(?:el\s+)?(?:proximo\s+|next\s+|this\s+)?{_WD_ES}(?:\s+(?:que viene|proximo|siguiente|por la (?:manana|tarde)))?\b"),
    re.compile(rf"\b(?:(?:by|before|until|on|for|next|this)\s+)?(?:next\s+|this\s+)?{_WD_EN}\b"),
    re.compile(r"\b(?:pasado manana|manana(?: por la (?:manana|tarde))?|hoy|esta (?:tarde|noche|semana|manana)|tomorrow|today|tonight|this (?:afternoon|evening|week|month)|next (?:week|month)|ma[nñ]ana por la (?:manana|tarde))\b"),
    re.compile(r"\b(?:(?:para|a|by|before)\s+)?(?:la semana (?:que viene|proxima|siguiente)|el mes (?:que viene|proximo)|fin(?:ales)? de (?:mes|semana|ano|dia)|final de (?:mes|semana)|(?:a )?(?:finales|principios|mediados) de (?:mes|semana|\w+)|end of (?:the )?(?:day|week|month|quarter|year)|eod|eow|eom|cierre de (?:mes|semana))\b"),
    re.compile(rf"\b(?:en|in|within|dentro de)\s+{_NUM}\s+(?:dias?|semanas?|meses|mes|horas?|days?|weeks?|months?|hours?)\b"),
    re.compile(rf"\b(?:(?:el|para el|antes del|hasta el|by the|on the|by|on)\s+)?\d{{1,2}}(?:st|nd|rd|th)?(?:\s+(?:de|of))?\s+{_MONTH}(?:\s+(?:de|of)?\s*\d{{4}})?\b"),
    re.compile(rf"\b(?:by |on |before )?{_MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?\b"),
    re.compile(r"\b(?:el |para el |antes del )\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b|\b\d{4}-\d{2}-\d{2}\b"),
]
_DATE_LEAD = re.compile(r"^(?:para el|para la|para|antes del|antes de la|antes de|hasta el|hasta|by the|by|before|until|on the|on|for)\s+")


def find_due(clause_original: str, clause_folded: str) -> tuple[str, int, int] | None:
    best = None
    for pattern in DATE_PATTERNS:
        m = pattern.search(clause_folded)
        if m and m.end() > m.start() and (best is None or m.start() < best[1]):
            best = (m.group(0), m.start(), m.end())
    if best is None:
        return None
    return clause_original[best[1]:best[2]].strip(), best[1], best[2]


def resolve(due_text: str, base: date | None) -> str | None:
    if not due_text or base is None:
        return None
    text = _DATE_LEAD.sub("", fold(due_text).strip())
    for candidate in (due_text, text):
        try:
            found = resolve_due(candidate, base)
        except Exception:  # noqa: BLE001 - a date the family parser cannot read stays words
            found = None
        if found:
            return found
    return None


# ---------------------------------------------------------------------------------------------------- splitting

_SENT = re.compile(r"[^.!?…\n]+(?:[.!?…]+|$)")
_CLAUSE_SPLIT = re.compile(r";|,\s*(?:pero|but|and then|and|y luego|y despues|y|e|so|asi que|aunque|although|however|sin embargo)\b|\s(?:pero|but)\s", re.IGNORECASE)


def split_sentences(text: str) -> list[tuple[int, int]]:
    spans = []
    for m in _SENT.finditer(text):
        start, end = m.start(), m.end()
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if end - start >= 2:
            spans.append((start, end))
    return spans


def split_clauses(text: str, start: int, end: int) -> list[tuple[int, int]]:
    sentence = text[start:end]
    parts, last = [], 0
    for m in _CLAUSE_SPLIT.finditer(sentence):
        if m.start() > last:
            parts.append((last, m.start()))
        last = m.end()
    parts.append((last, len(sentence)))
    out = []
    for a, b in parts:
        while a < b and sentence[a] in " ,;\t":
            a += 1
        while b > a and sentence[b - 1] in " ,;\t":
            b -= 1
        if b - a >= 2:
            out.append((start + a, start + b))
    return out or [(start, end)]


_LANG_ES = re.compile(r"\b(?:el|la|los|las|que|de|y|en|un|una|por|para|con|se|lo|es|no|pero|yo|nosotros|mañana|vale|entonces|tenemos|vamos|hemos|puedes|podríamos)\b", re.IGNORECASE)
_LANG_EN = re.compile(r"\b(?:the|and|to|of|that|is|it|we|you|will|i'll|could|should|maybe|but|for|with|have|need|going|let's|agreed|decided|tomorrow)\b", re.IGNORECASE)


def detect_language(text: str) -> str:
    es, en = len(_LANG_ES.findall(text)), len(_LANG_EN.findall(text))
    return "en" if en > es else "es"


# ---------------------------------------------------------------------------------------------------- classification


def _first(rules: Iterable[Rule], original: str, folded: str, lang: str):
    best = None
    for rule in rules:
        if lang != "auto" and rule.lang != lang:
            continue
        m = rule.search(original, folded)
        if m and m.end() > m.start() and (best is None or rule.confidence > best[0].confidence or (rule.confidence == best[0].confidence and m.start() < best[1].start())):
            best = (rule, m)
    return best


def _has_question_form(original: str, folded: str, lang: str) -> tuple[bool, str]:
    if "?" in original or "¿" in original:
        return True, "?"
    stripped = original.strip(" ¡'\"")
    if lang in ("auto", "es"):
        m = _Q_ES_ACCENT.match(stripped) or _Q_ES_VERB.match(fold(stripped))
        if m:
            return True, m.group(0).strip(" ¿")
    if lang in ("auto", "en"):
        m = _Q_EN.match(fold(stripped))
        if m:
            return True, m.group(0).strip()
    return False, ""


def _addressee(original: str, folded: str, speaker: str) -> dict:
    m = _VOCATIVE.match(original) or _VOCATIVE_END.search(original)
    if m and fold(m.group("name").split()[0]) not in _NOT_NAMES:
        return {"kind": "person", "name": m.group("name"), "cue": m.group(0).strip(" ,:?")}
    m = _ASKED_ABOUT.search(original)
    if m and fold(m.group("name").split()[0]) not in _NOT_NAMES:
        return {"kind": "person", "name": m.group("name"), "cue": m.group(0)}
    wh = re.match(r"^\W*(?:quien|quienes|who|whom|alguien|anyone|anybody|has anyone|alguno)\b", folded.strip(" ¿¡"))
    if wh:
        return {"kind": "anyone", "name": None, "cue": wh.group(0).strip(" ¿")}
    g = _ADDRESSEE_2P.search(folded)
    if g:
        other = {"yo": "otros", "otros": "yo"}.get(speaker)
        if other:
            return {"kind": "speaker", "name": other, "cue": g.group(0)}
        return {"kind": "other", "name": None, "cue": g.group(0)}
    g = _ADDRESSEE_GROUP.search(folded)
    if g:
        return {"kind": "group", "name": None, "cue": g.group(0)}
    return {"kind": "unassigned", "name": None, "cue": ""}


def _counterpart(original: str) -> str | None:
    m = re.search(rf"\b(?:a|para|to|for|with|con)\s+(?P<n>{_NAME})\b", original)
    if m and fold(m.group("n").split()[0]) not in _NOT_NAMES:
        return m.group("n")
    return None


def _guarded_decision(folded: str, m: re.Match) -> bool:
    before = re.findall(r"[a-z']+", folded[:m.start()])[-3:]
    after = re.findall(r"[a-z']+", folded[m.end():])[:2]
    return any(w in _GUARD_BEFORE or w.endswith("n't") for w in before) or any(w in _GUARD_AFTER for w in after)


def classify_clause(original: str, lang: str = "auto", speaker: str = "S1") -> dict | None:
    """Label one clause, or return None. The result carries the kind, confidence, cue and rule; people and dates come from the words."""
    tagged = _TAG_Q.search(original)
    if tagged:  # "lo envío el lunes, ¿vale?" is a statement with a tag, not a question
        original = original[:tagged.start()].rstrip(" ,") + "."
    text = original.strip()
    if len(text.split()) < 2:
        return None
    folded = fold(original)
    is_question, question_cue = _has_question_form(original, folded, lang)

    def result(kind, rule, m, confidence, **extra):
        return {"kind": kind, "rule": rule.id, "lang": rule.lang, "cue": original[m.start():m.end()].strip(), "cue_span": [m.start(), m.end()],
                "confidence": confidence, **extra}

    # 1. explicit decision markers (not negated, not pending, not a question)
    if not is_question:
        found = _first(DECISION_RULES, original, folded, lang)
        if found and not _guarded_decision(folded, found[1]):
            return result("decision", found[0], found[1], found[0].confidence)

    # 2. questions
    if is_question:
        mark = re.search(r"\?|¿", original)
        return {"kind": "question", "rule": "any.question.mark" if mark else "any.question.opening", "lang": detect_language(original), "cue": "?" if mark else question_cue,
                "cue_span": [mark.start(), mark.end()] if mark else [0, len(question_cue)], "confidence": 0.9 if mark else 0.65,
                "addressee": _addressee(original, folded, speaker), "open": True}

    # 3. hedges, proposals and conditionals: never a firm promise
    found = _first(PROPOSAL_RULES, original, folded, lang)
    if found:
        rule, m = found
        return result("proposal", rule, m, rule.confidence, conditional="conditional" in rule.id or rule.id.endswith("conditional_start"),
                      hedged="soft" in rule.id or rule.id.endswith("podemos"))

    # 4. firm commitments: first person, or a named person who will do something
    found = _first(COMMITMENT_RULES, original, folded, lang)
    if found and found[0].id in ("en.commitment.have_to", "es.commitment.tengo_que") and _requirement_first(original, folded, lang):
        found = None
    if found:
        return result("commitment", found[0], found[1], found[0].confidence, owner_from="speaker")
    for pattern, rule_id, rule_lang in ((_THIRD_ES, "es.commitment.named_person", "es"), (_THIRD_EN, "en.commitment.named_person", "en")):
        if lang not in ("auto", rule_lang):
            continue
        third = pattern.match(text)
        if third and fold(third.group("name").split()[0]) not in _NOT_NAMES:
            start = len(third.group("name"))
            return {"kind": "commitment", "rule": rule_id, "lang": rule_lang, "cue": text[start:third.end()].strip(), "cue_span": [start, third.end()],
                    "confidence": 0.78, "owner_from": "named", "owner": third.group("name")}

    # 5. requirements
    found = _first(REQUIREMENT_RULES, original, folded, lang)
    if found:
        return result("requirement", found[0], found[1], found[0].confidence)
    return None


def _requirement_first(original: str, folded: str, lang: str) -> bool:
    """"I have to" is a promise to myself; "the system has to" is a requirement. The first-person forms win, so this is only used for tie-breaks."""
    found = _first([r for r in REQUIREMENT_RULES if r.confidence >= 0.8], original, folded, lang)
    return bool(found and found[1].start() < 3)


# ---------------------------------------------------------------------------------------------------- analysis


def _as_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value)).date()
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def item_id(session_id: str, start_s: float, kind: str, text: str) -> str:
    """Stable across re-reads: depends on the session, the segment's start (milliseconds), the kind and the words, not on row ids."""
    raw = f"{session_id}|{int(round(float(start_s) * 1000))}|{kind}|{' '.join(fold(text).split())}"
    return "rq-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def analyze_segments(session_id: str, segments: list[dict], *, meeting_date: Any = None, lang: str = "auto", min_confidence: float = 0.0,
                     kinds: Iterable[str] | None = None) -> list[dict]:
    """Classify the clauses of every segment. ``segments``: dicts with ``start_s``, ``end_s``, ``speaker``, ``text`` and optionally ``id``."""
    base = _as_date(meeting_date)
    wanted = set(kinds) if kinds else set(KINDS)
    items: list[dict] = []
    seen: set[str] = set()
    for seg in segments:
        text = str(seg.get("text") or "")
        if not text.strip():
            continue
        speaker = str(seg.get("speaker") or "S1")
        start_s, end_s = float(seg.get("start_s") or 0), float(seg.get("end_s") or 0)
        for s_start, s_end in split_sentences(text):
            sentence_text = text[s_start:s_end]
            clauses = [(s_start, s_end)] if ("?" in sentence_text or "¿" in sentence_text) else split_clauses(text, s_start, s_end)
            for c_start, c_end in clauses:
                clause = text[c_start:c_end]
                verdict = classify_clause(clause, lang, speaker)
                if verdict is None:
                    continue
                kind = verdict["kind"]
                confidence = float(verdict["confidence"])
                due_found = find_due(clause, fold(clause)) if kind in ("commitment", "requirement", "decision", "proposal") else None
                due_text = due_found[0] if due_found else ""
                due = resolve(due_text, base) if due_text else None
                if kind == "commitment" and due_text:
                    confidence += 0.05
                if kind == "commitment" and verdict.get("owner_from") == "speaker" and speaker not in ("yo", "otros"):
                    confidence -= 0.05  # a single-track recording cannot say who the first person is
                confidence = round(max(0.3, min(0.97, confidence)), 2)
                if confidence < min_confidence or kind not in wanted:
                    continue
                cue_span = verdict.get("cue_span")
                item = {
                    "id": item_id(session_id, start_s, kind, clause),
                    "kind": kind,
                    "text": clause.strip(),
                    "sentence": text[s_start:s_end].strip(),
                    "confidence": confidence,
                    "cue": verdict["cue"],
                    "cue_rule": verdict["rule"],
                    "cue_span": cue_span,
                    "lang": verdict["lang"],
                    "speaker": speaker,
                    "segment": {"id": seg.get("id"), "start_s": round(start_s, 2), "end_s": round(end_s, 2), "t": hms(start_s), "speaker": speaker, "text": text.strip()},
                    "playback": {"session_id": session_id, "start_s": round(start_s, 2), "end_s": round(end_s, 2), "t": f"{hms(start_s)}-{hms(end_s)}",
                                 "transcript": text.strip(), "transcript_call": {"tool": "scribe_transcript", "arguments": {"session_id": session_id, "from_s": round(start_s, 2), "to_s": round(end_s, 2)}}},
                }
                if kind == "commitment":
                    item.update({"firm": True, "owner": verdict.get("owner") or speaker, "counterpart": _counterpart(clause), "due_text": due_text, "due": due})
                elif kind == "proposal":
                    item.update({"firm": False, "conditional": bool(verdict.get("conditional")), "hedged": bool(verdict.get("hedged")), "due_text": due_text, "due": due,
                                 "why_not_firm": "conditional" if verdict.get("conditional") else "hedged or suggested, not promised"})
                elif kind == "question":
                    item.update({"open": True, "addressee": verdict["addressee"], "asked_by": speaker})
                elif kind == "decision":
                    item.update({"decided": True, "due_text": due_text, "due": due})
                elif kind == "requirement":
                    item.update({"due_text": due_text, "due": due})
                if item["id"] in seen:
                    continue
                seen.add(item["id"])
                item["refs"] = []
                items.append(item)
    items.sort(key=lambda i: (i["segment"]["start_s"], i["segment"].get("id") or 0))
    return items


def summarize(items: list[dict]) -> dict:
    counts = {k: 0 for k in KINDS}
    for it in items:
        counts[it["kind"]] += 1
    open_q = [i for i in items if i["kind"] == "question"]
    return {"total": len(items), "by_kind": counts, "firm_commitments": counts["commitment"], "open_questions": len(open_q),
            "unassigned_questions": sum(1 for i in open_q if i["addressee"]["kind"] in ("unassigned", "anyone")),
            "commitments_without_due": sum(1 for i in items if i["kind"] == "commitment" and not i.get("due") and not i.get("due_text"))}


# ---------------------------------------------------------------------------------------------------- export

LABELS = {
    "es": {"title": "Requisitos y pendientes de la reunión", "meeting": "Reunión", "date": "Fecha", "commitment": "Compromisos firmes", "proposal": "Propuestas (no son compromisos)",
           "question": "Preguntas abiertas", "decision": "Decisiones", "requirement": "Requisitos", "none": "Nada detectado.", "owner": "responsable", "due": "fecha",
           "to": "a", "cue": "indicio", "conf": "confianza", "who": "debe responder", "anyone": "sin asignar", "group": "el grupo", "links": "vinculado a",
           "note": "Clasificación por reglas lingüísticas (sin modelo). Cada elemento enlaza con el fragmento de la transcripción; revísalo antes de actuar.",
           "conditional": "condicional", "hedged": "con reserva", "engagement": "Encargo", "orphans": "Vínculos sin elemento (la transcripción cambió)"},
    "en": {"title": "Meeting requirements and pending items", "meeting": "Meeting", "date": "Date", "commitment": "Firm commitments", "proposal": "Proposals (not commitments)",
           "question": "Open questions", "decision": "Decisions", "requirement": "Requirements", "none": "Nothing detected.", "owner": "owner", "due": "due",
           "to": "to", "cue": "cue", "conf": "confidence", "who": "must answer", "anyone": "unassigned", "group": "the group", "links": "linked to",
           "note": "Classified by linguistic rules (no model). Each item points at its transcript segment; review it before acting.",
           "conditional": "conditional", "hedged": "hedged", "engagement": "Engagement", "orphans": "Links without an item (the transcript changed)"},
}
ORDER = ("commitment", "decision", "requirement", "question", "proposal")


def _who(item: dict, t: dict) -> str:
    a = item.get("addressee") or {}
    if a.get("kind") in ("person", "speaker"):
        return a["name"]
    if a.get("kind") == "group":
        return t["group"]
    return t["anyone"]


def render_markdown(session: dict, items: list[dict], locale: str = "es", engagement_ref: str | None = None, orphans: list[dict] | None = None) -> str:
    t = LABELS.get(locale, LABELS["es"])
    started = session.get("started_at")
    when = datetime.fromtimestamp(started).strftime("%Y-%m-%d %H:%M") if isinstance(started, (int, float)) else ""
    lines = [f"# {t['title']}", "", f"- {t['meeting']}: {session.get('title') or session.get('id')} (`{session.get('id')}`)"]
    if when:
        lines.append(f"- {t['date']}: {when}")
    if engagement_ref:
        lines.append(f"- {t['engagement']}: `{engagement_ref}`")
    lines += ["", f"_{t['note']}_", ""]
    for kind in ORDER:
        group = [i for i in items if i["kind"] == kind]
        lines += [f"## {t[kind]} ({len(group)})", ""]
        if not group:
            lines += [f"_{t['none']}_", ""]
            continue
        for it in group:
            extra = []
            if kind == "commitment":
                extra.append(f"{t['owner']}: {it.get('owner')}")
                if it.get("counterpart"):
                    extra.append(f"{t['to']}: {it['counterpart']}")
                if it.get("due") or it.get("due_text"):
                    extra.append(f"{t['due']}: {it.get('due') or it.get('due_text')}")
            elif kind == "question":
                extra.append(f"{t['who']}: {_who(it, t)}")
            elif kind == "proposal":
                if it.get("conditional"):
                    extra.append(t["conditional"])
                if it.get("hedged"):
                    extra.append(t["hedged"])
            extra.append(f"{t['cue']}: «{it['cue']}»")
            extra.append(f"{t['conf']}: {it['confidence']:.2f}")
            line = f"- `{it['segment']['t']}` ({it['speaker']}) {it['text']}  \n  {' · '.join(extra)}"
            if it.get("refs"):
                line += "  \n  " + t["links"] + ": " + ", ".join(f"`{r['ref']}` ({r['ref_kind']})" for r in it["refs"])
            lines.append(line)
        lines.append("")
    if orphans:
        lines += [f"## {t['orphans']}", ""] + [f"- `{o['item_id']}` -> `{o['ref']}`" for o in orphans] + [""]
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------------------------------- links


class RequirementLinks:
    """Free external references tied to a requirement or decision of a session (table ``requirement_links``). No other state."""

    def __init__(self, db):
        self.db = db

    def add(self, session_id: str, item_id_: str, ref: str, ref_kind: str = "deliverable", engagement: str = "") -> dict:
        ref, engagement = ref.strip(), (engagement or "").strip()
        if not ref or len(ref) > 200:
            raise ValueError("ref must be a free id of 1 to 200 characters.")
        if ref_kind not in LINK_KINDS:
            raise ValueError(f"ref_kind must be one of {', '.join(LINK_KINDS)}.")
        with self.db.lock:
            self.db.conn.execute(
                "INSERT INTO requirement_links(session_id, item_id, ref, ref_kind, engagement, created_at) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(session_id, item_id, ref) DO UPDATE SET ref_kind = excluded.ref_kind, engagement = excluded.engagement",
                (session_id, item_id_, ref, ref_kind, engagement[:200], time.time()))
        return {"session_id": session_id, "item_id": item_id_, "ref": ref, "ref_kind": ref_kind, "engagement": engagement}

    def remove(self, session_id: str, item_id_: str, ref: str) -> bool:
        with self.db.lock:
            return self.db.conn.execute("DELETE FROM requirement_links WHERE session_id = ? AND item_id = ? AND ref = ?", (session_id, item_id_, ref.strip())).rowcount > 0

    def for_session(self, session_id: str) -> list[dict]:
        with self.db.lock:
            rows = self.db.conn.execute("SELECT * FROM requirement_links WHERE session_id = ? ORDER BY created_at, ref", (session_id,)).fetchall()
        return [{"session_id": r["session_id"], "item_id": r["item_id"], "ref": r["ref"], "ref_kind": r["ref_kind"], "engagement": r["engagement"]} for r in rows]


class RequirementsService:
    def __init__(self, db, sessions):
        self.db = db
        self.sessions = sessions
        self.links = RequirementLinks(db)

    def analyze(self, session_id: str, *, lang: str = "auto", min_confidence: float = 0.0, kinds: Iterable[str] | None = None,
                engagement_ref: str | None = None) -> dict:
        session = self.sessions.get(session_id)
        if session is None:
            raise LookupError(f"Unknown session: {session_id}")
        segments = self.sessions.segments(session_id)
        items = analyze_segments(session_id, segments, meeting_date=session.get("started_at"), lang=lang, min_confidence=min_confidence, kinds=kinds)
        links = self.links.for_session(session_id)
        by_item: dict[str, list[dict]] = {}
        for link in links:
            by_item.setdefault(link["item_id"], []).append({"ref": link["ref"], "ref_kind": link["ref_kind"], "engagement": link["engagement"]})
        ids = {i["id"] for i in analyze_segments(session_id, segments, meeting_date=session.get("started_at"), lang=lang)}
        for it in items:
            it["refs"] = by_item.get(it["id"], [])
        orphans = [l for l in links if l["item_id"] not in ids]
        if engagement_ref:
            items = [i for i in items if any(r["engagement"] == engagement_ref or r["ref"] == engagement_ref for r in i["refs"])]
        return {"session_id": session_id, "title": session.get("title", ""), "status": session.get("status"), "rules_version": RULES_VERSION,
                "meeting_date": (_as_date(session.get("started_at")) or date.min).isoformat() if session.get("started_at") else None,
                "segments": len(segments), "summary": summarize(items), "items": items, "orphan_links": orphans,
                "note": "Rule-based classification, no model. Review before acting; ASR errors carry over."}

    def link(self, session_id: str, item_id_: str, ref: str, ref_kind: str = "deliverable", engagement: str = "", remove: bool = False) -> dict:
        if self.sessions.get(session_id) is None:
            raise LookupError(f"Unknown session: {session_id}")
        if remove:
            return {"removed": self.links.remove(session_id, item_id_, ref), "item_id": item_id_, "ref": ref}
        current = self.analyze(session_id)
        item = next((i for i in current["items"] if i["id"] == item_id_), None)
        if item is None:
            raise LookupError(f"No item {item_id_} in session {session_id}.")
        if item["kind"] not in LINKABLE:
            raise ValueError(f"Only {' and '.join(LINKABLE)} can be linked to an engagement reference (this one is a {item['kind']}).")
        return {"linked": True, **self.links.add(session_id, item_id_, ref, ref_kind, engagement)}

    def export(self, session_id: str, fmt: str = "json", *, locale: str = "es", **kw) -> dict | str:
        result = self.analyze(session_id, **kw)
        if fmt == "md":
            session = self.sessions.get(session_id)
            return render_markdown(session, result["items"], locale, kw.get("engagement_ref"), result["orphan_links"])
        return result

    def importable_commitments(self, session_id: str, **kw) -> dict:
        """Only firm commitments are importable elsewhere (the People app); everything else comes back with the reason it is not."""
        result = self.analyze(session_id, **kw)
        started = self.sessions.get(session_id).get("started_at")
        firm = [i for i in result["items"] if i["kind"] == "commitment" and i.get("firm")]
        rejected = [{"id": i["id"], "kind": i["kind"], "text": i["text"], "reason": _not_importable(i)} for i in result["items"] if i not in firm]
        return {"schema": "talos.commitments/1", "session_id": session_id, "title": result["title"], "meeting_date": result["meeting_date"], "meeting_at": _iso(started),
                "meeting": {"title": result["title"], "at": _iso(started), "session_id": session_id},
                "commitments": [commitment_payload(i, result["title"], started) for i in firm], "rejected": rejected}


def _not_importable(item: dict) -> str:
    if item["kind"] == "proposal":
        return "proposal: hedged, conditional or suggested; it is not a firm commitment"
    return f"{item['kind']}: not a commitment"


def _iso(ts) -> str | None:
    return datetime.fromtimestamp(float(ts)).astimezone().isoformat(timespec="seconds") if isinstance(ts, (int, float)) else None


def commitment_payload(item: dict, title: str = "", started_at: float | None = None) -> dict:
    """The exchange shape (``talos.commitment/1``) that People imports: the words, owner, day and the exact segment to play back."""
    seg = item["segment"]
    return {"schema": "talos.commitment/1", "kind": "commitment", "firm": True, "item_id": item["id"], "text": item["text"], "owner": item.get("owner"),
            "counterpart": item.get("counterpart"), "due": item.get("due"), "due_text": item.get("due_text") or "", "confidence": item["confidence"], "cue": item["cue"],
            "source": {"app": "talos", "session_id": item["playback"]["session_id"], "ref": f"talos:{item['playback']['session_id']}#{item['id']}", "title": title,
                       "start_s": seg["start_s"], "end_s": seg["end_s"], "quote": seg["text"][:1000], "speaker": seg["speaker"],
                       **({"at": _iso(started_at + seg["start_s"])} if isinstance(started_at, (int, float)) else {})}}
