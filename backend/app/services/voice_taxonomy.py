"""v3: a deterministic, explainable apparel aspect taxonomy for customer text (reviews, returns, tickets).

Each theme is a set of rules. A rule is either a regex over one clause or a proximity rule
("a body part within N words of a fit descriptor"). Every hit is checked for:

- negation: a negator ("not", "no", "never", "without", "n't" …) among the few words before the hit, or
  before the descriptor of a proximity hit, in the same comma/"and"-delimited part of the clause.
  "Not tight at all" does not count as tight. A negated hit can flip to an opposite theme
  ("not warm enough" -> not warm), or else it is dropped;
- hedging: "I was worried it would pill, but it doesn't" -> the worried clause is dropped;
- body descriptions: "I have broad shoulders" describes the customer, not the garment.

Clauses are split at sentence ends and at contrast words ("but", "however", "though" …), so
"tight at first but it relaxed" scopes "tight" to its own clause.

No LLM is involved: the same text always yields the same mentions, so every count is reproducible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

# --------------------------------------------------------------------------- vocabulary

NEGATORS = {
    "not", "no", "never", "without", "hardly", "barely", "nor", "zero", "none", "lack", "lacks", "lacking",
    "dont", "doesnt", "didnt", "isnt", "wasnt", "arent", "werent", "cant", "cannot", "couldnt", "wont",
    "wouldnt", "havent", "hasnt", "hadnt", "shouldnt", "aint",
}
HEDGES = {"worried", "worry", "afraid", "feared", "concerned", "thought", "hoped", "hoping", "expected",
          "expecting", "assumed", "nervous"}
# Adjectives that, right before a body part, describe the customer's body rather than the garment.
BODY_DESCRIPTORS = {"big", "bigger", "broad", "broader", "wide", "wider", "large", "larger", "full", "fuller",
                    "small", "smaller", "narrow", "narrower", "petite", "ample", "flat", "curvy", "busty", "long",
                    "longer", "short", "shorter", "thick", "thicker", "muscular", "athletic", "slim"}
_COPULA = {"is", "are", "was", "were", "be", "being"}

_SENTENCE = re.compile(r"[^.!?\n]+[.!?]*[\"')\]]*|\n")
_CONTRAST = re.compile(r"\b(?:but|however|although|though|whereas|yet|except|otherwise)\b", re.I)
_PART_BOUNDARY = re.compile(r",|;|:|\band\b|\s[-–\u2014]\s|&", re.I)
_TOKEN = re.compile(r"[a-z]+(?:'[a-z]+)?")
_FOLLOW_NEG = re.compile(
    r"^[\s,?!:-]*(?:"
    r"(?:(?:is|was|are|were|has been|have been)\s+)?(?:not|never|isn't|wasn't|aren't|weren't)\s+(?:at all|an? (?:issue|problem|concern))"
    r"|not at all|(?:is|was|are|were) (?:no|zero|not an?) (?:issue|problem|concern)"
    r"|(?:not|weren't|wasn't|aren't|isn't)\b(?!\s+only))", re.I)


@dataclass(frozen=True)
class Near:
    """`a` and `b` (token regexes, full-token match) within `window` tokens of each other in one clause."""

    a: str
    b: str
    window: int = 4
    body_part: bool = True  # apply the body-description guard to `a`


@dataclass(frozen=True)
class Theme:
    id: str
    group: str  # fit | fabric | colour | construction | care | comfort | warmth | value | returns
    name: str  # display name
    phrase: str  # how a finding reads: "41 of 176 reviews mention <phrase>"
    kind: str  # problem | praise | rating (polarity from the record's rating)
    patterns: tuple[str, ...] = ()
    near: tuple[Near, ...] = ()
    negated_to: str | None = None  # a negated hit counts for this theme instead (else it is dropped)
    excludes: tuple[str, ...] = ()  # a hit whose clause matches one of these is ignored


SHOULDER = r"shoulders?|shoulder"
CHEST = r"chest|bust|boobs?|breasts?|bustline|cleavage"
WAIST = r"waist|waistband|waistline|midsection|middle|tummy"
HIPS = r"hips?|thighs?|butt|bum|rear|seat|backside|derriere"
SLEEVE = r"sleeves?|arms?|armholes?|biceps?|forearms?|armhole"
TIGHT = r"tight|tighter|tightly|snug|snugger|narrow|restrictive|restricted|restricting|constricting|small|smaller|binding|binds|squeez\w*"
LOOSE = r"loose|looser|big|bigger|baggy|wide|broad|huge|roomy|large|larger|gap|gaps|gaped|gapes|gaping|sloppy|swimming"

# "too tight across the shoulders" is a point-of-measure finding, not an overall sizing one.
_NOT_LOCAL = (r"(?! (?:\w+ ){0,2}(?:across|around|in|at|through|on|under|over) (?:the |my |your )?(?:upper )?"
              r"(?:shoulders?|chest|bust|arms?|armholes?|sleeves?|waist|waistband|hips?|thighs?|back|butt|bum|neck|"
              r"neckline|calves|biceps?|forearms?|rear|seat|tummy|stomach|midsection|ribs?))")

THEMES: tuple[Theme, ...] = (
    # ---- fit: overall sizing
    Theme("fit.runs_small", "fit", "Runs small", "it running small", "problem", patterns=(
        r"\bruns? (?:\w+ )?small\b", r"\brunning (?:\w+ )?small\b", r"\bsiz(?:e|ed|ing) up\b",
        r"\b(?:go|went|going|order(?:ed)?|get|got|buy|bought) (?:a |one )?(?:full |half )?size up\b",
        r"\b(?:go|went|going|order(?:ed)?|get|got) up (?:a|one|two) (?:full |half )?sizes?\b",
        r"\btoo (?:small|tight|snug)\b" + _NOT_LOCAL, r"\bsmaller than (?:i )?(?:expected|usual|normal|anticipated|my usual)\b",
        r"\bsize (?:or two )?(?:larger|bigger)\b", r"\bsize too small\b"),
        excludes=(r"\b(?:sleeves?|arms?|armholes?) (?:are|were|is|was) too (?:small|tight)\b",)),
    Theme("fit.runs_large", "fit", "Runs large", "it running large", "problem", patterns=(
        r"\bruns? (?:\w+ )?(?:large|big|huge)\b", r"\brunning (?:\w+ )?(?:large|big)\b", r"\bsiz(?:e|ed|ing) down\b",
        r"\b(?:go|went|going|order(?:ed)?|get|got) down (?:a|one|two) (?:full |half )?sizes?\b",
        r"\btoo (?:big|large|loose|baggy)\b" + _NOT_LOCAL, r"\b(?:bigger|larger) than (?:i )?(?:expected|usual|normal|anticipated)\b",
        r"\bswimming in\b", r"\bhuge\b(?! (?:fan|hit|plus|compliments?|deal|difference|selection))", r"\bsize too large\b"),
        excludes=(r"\b(?:sleeves?|arms?) (?:are|were|is|was) too (?:big|long|loose)\b",)),
    Theme("fit.true_to_size", "fit", "True to size", "a true-to-size fit", "praise", patterns=(
        r"\btrue to size\b", r"\btts\b", r"\bfits? (?:perfectly|like a glove|great|beautifully|wonderfully|just right)\b",
        r"\bperfect fit\b", r"\bfit (?:is|was) (?:perfect|great|spot on|just right)\b", r"\bfits? true\b")),
    # ---- fit: points of measure
    Theme("fit.shoulders_tight", "fit", "Tight across the shoulders", "tight shoulders", "problem",
          near=(Near(SHOULDER, TIGHT, 4),),
          patterns=(r"\b(?:can't|cannot|couldn't|could not|can not|hard to|difficult to) (?:move|lift|raise|reach)(?: up)? (?:my )?arms?\b",
                    r"\b(?:tight|snug|pulls?|pulled) across the (?:upper )?back\b")),
    Theme("fit.shoulders_wide", "fit", "Too wide in the shoulders", "wide or dropping shoulders", "problem",
          near=(Near(SHOULDER, r"wide|broad|big|huge|boxy|droop\w*|slip\w*|fall\w*|fell|hangs?|hanging|sloppy|loose", 4),)),
    Theme("fit.chest_tight", "fit", "Tight at the chest / bust", "a tight chest or bust", "problem",
          near=(Near(CHEST, TIGHT + r"|pulls|pulling|pulled|gap|gaps|gaping|gapes|flatten\w*|squish\w*", 4),)),
    Theme("fit.chest_loose", "fit", "Too roomy at the chest / bust", "a loose chest or bust", "problem",
          near=(Near(CHEST, r"loose|looser|baggy|roomy|big|bigger|huge|wide|sloppy", 4),)),
    Theme("fit.waist_tight", "fit", "Tight at the waist", "a tight waist", "problem",
          near=(Near(WAIST, TIGHT + r"|dig|digs|digging|dug", 4),)),
    Theme("fit.waist_loose", "fit", "Too loose at the waist", "a loose or gaping waist", "problem",
          near=(Near(WAIST, LOOSE, 4),)),
    Theme("fit.hips_tight", "fit", "Tight at the hips / thighs", "tight hips or thighs", "problem",
          near=(Near(HIPS, TIGHT + r"|cling\w*|clings", 4),)),
    Theme("fit.too_short", "fit", "Too short", "it being too short", "problem", patterns=(
        r"\btoo short\b", r"\bshorter than (?:i )?(?:expected|pictured|shown|anticipated|it looks|in the (?:photo|picture)s?)\b",
        r"\b(?:length|hem|body) (?:is|was) (?:\w+ )?short\b", r"\b(?:hits|hit|falls|fell) (?:way |well )?above\b",
        r"\bcropped than\b"),
        excludes=(r"\b(?:sleeves?|arms?)\b",)),
    Theme("fit.too_long", "fit", "Too long", "it being too long", "problem", patterns=(
        r"\btoo long\b", r"\blonger than (?:i )?(?:expected|pictured|shown|anticipated|it looks|in the (?:photo|picture)s?)\b",
        r"\b(?:length|hem|body) (?:is|was) (?:\w+ )?long\b", r"\b(?:drags?|dragged|dragging) on the (?:floor|ground)\b",
        r"\bhad to (?:have (?:it|them) )?(?:hem|hemmed|shorten|shortened)\b", r"\boverwhelm(?:s|ed|ing)? my (?:\w+ )?frame\b"),
        excludes=(r"\b(?:sleeves?|arms?)\b",)),
    Theme("fit.sleeves_short", "fit", "Sleeves too short", "short sleeves", "problem",
          near=(Near(r"sleeves?|arms?", r"short|shorter", 3, body_part=False),),
          excludes=(r"\bshort[- ]sleeve[sd]?\b",)),
    Theme("fit.sleeves_long", "fit", "Sleeves too long", "long sleeves", "problem",
          near=(Near(r"sleeves?|arms?", r"long|longer", 3, body_part=False),),
          excludes=(r"\blong[- ]sleeve[sd]?\b(?!\s+(?:are|were|is|was))", r"\b(?:my|i have) (?:\w+ )?long arms\b")),
    Theme("fit.sleeves_tight", "fit", "Tight sleeves / arms", "tight sleeves or armholes", "problem",
          near=(Near(SLEEVE, TIGHT, 4),)),
    Theme("fit.boxy", "fit", "Boxy / shapeless", "a boxy or shapeless cut", "rating", patterns=(
        r"\bboxy\b", r"\bshapeless\b", r"\bfrumpy\b", r"\bmaternity\b", r"\bno shape\b",
        r"\blike a (?:tent|sack|box|potato sack|bag)\b", r"\btent[- ]like\b")),
    # ---- fabric
    Theme("fabric.pilling", "fabric", "Pilling", "pilling", "problem", patterns=(
        r"\bpill(?:s|ed|ing|y)?\b", r"\bpiling\b", r"\bfuzz(?:y)? balls\b", r"\bbobbl\w*")),
    Theme("fabric.itchy", "fabric", "Itchy / scratchy", "itchy or scratchy fabric", "problem", patterns=(
        r"\bitch(?:y|iness|ed|es|ing)?\b", r"\bscratch(?:y|iness)\b", r"\bprickl(?:y|iness)\b", r"\birritat\w*")),
    Theme("fabric.thin", "fabric", "Thin / flimsy fabric", "thin or flimsy fabric", "rating", patterns=(
        r"(?<!wear )(?<!wearing )\bthin\b(?! (?:straps?|belts?|lines?|layers?|stripes?|person|frame|build|women|people|ladies|girls?|"
        r"tops?|sweaters?|shirts?|tees?|t-shirts?|camis?|camisoles?|blouses?|turtlenecks?|cardigans?|knits?|arms|legs|"
        r"tanks?|undershirts?|long[- ]sleeves?))",
        r"\bflimsy\b", r"\bcheap(?:ly)? (?:fabric|material|feeling|feel)\b", r"\bfabric (?:is|was|feels|felt) cheap\b")),
    Theme("fabric.sheer", "fabric", "See-through", "the fabric being see-through", "rating", patterns=(
        r"\bsee[- ]?through\b", r"\bsheer\b", r"\btransparent\b", r"\bsee (?:my|your|the) (?:bra|underwear|undergarments)\b",
        r"\b(?:need|needs|needed|require[sd]?) (?:a |to wear a )?(?:cami|camisole|slip|tank)\b")),
    Theme("fabric.wrinkles", "fabric", "Wrinkles easily", "wrinkling", "problem", patterns=(
        r"\bwrinkl\w*", r"\bcreas(?:e|es|ed|ing)\b"),
        excludes=(r"\bwrinkle[- ](?:free|resistant)\b",
                  r"\b(?:arrived|came|shipped|folded|packag\w*|out of the (?:box|bag|package|mail))\b")),
    Theme("fabric.shrinks", "fabric", "Shrinks", "shrinkage", "problem", patterns=(
        r"\bshr[au]nk\b", r"\bshrink(?:s|ing|age)?\b")),
    Theme("fabric.stretches_out", "fabric", "Stretches out / loses shape", "it stretching out or losing shape", "problem",
          patterns=(r"\bstretch(?:es|ed|ing)? out\b", r"\bbag(?:s|ged|gy)? out\b", r"\b(?:lose|loses|lost|losing) (?:its|it's|their|the|all) shape\b",
                    r"\bgrow(?:s|ing)? (?:throughout|during|over) the day\b", r"\bsag(?:s|gy|ged|ging)?\b")),
    Theme("fabric.snags", "fabric", "Snags", "snagging", "problem", patterns=(r"\bsnag(?:s|ged|ging|gy)?\b",)),
    Theme("fabric.quality_praised", "fabric", "Soft, quality fabric", "soft, quality fabric", "praise", patterns=(
        r"\bsoft(?:est|er)?\b", r"\bbuttery\b", r"\bluxurious\b", r"\b(?:great|good|high|nice|excellent|amazing|superb) quality\b",
        r"\bwell[- ]made\b", r"\bsubstantial\b", r"\bquality (?:is|was) (?:great|excellent|amazing|good|superb)\b")),
    # ---- colour
    Theme("colour.vs_photo", "colour", "Looks different from the photos", "colour or look differing from the photos",
          "problem", patterns=(
              r"\b(?:colou?r|shade|hue)s? (?:is|was|are|were|looks?|looked|appears?) (?:\w+ )?(?:different|off|darker|lighter|duller|brighter|more \w+|less \w+|washed[- ]out)\b(?: than| from| in| on| online)?",
              r"\b(?:colou?r|shade)s? (?:\w+ )?(?:than|from) (?:the )?(?:pictured|shown|online|website|photos?|pictures?|pics?|images?)\b",
              r"\b(?:nothing|not) (?:at all )?like (?:the |in the |on the )?(?:pictures?|photos?|pics?|images?|model|pictured|shown|website)\b",
              r"\b(?:doesn't|does not|didn't|did not) look (?:\w+ )?like (?:the |in the |on the )?(?:pictures?|photos?|pics?|images?|model|website)\b",
              r"\bnot as (?:pictured|shown|described|advertised)\b",
              r"\b(?:different|differs) (?:than|from) (?:the |what was )?(?:pictured|shown|pictures?|photos?|pics?|images?|website|online)\b",
              r"\bnot (?:the )?(?:same )?colou?r (?:as|that was) (?:pictured|shown)\b")),
    Theme("colour.praised", "colour", "Loved the colour", "the colour", "praise", patterns=(
        r"\b(?:love|loved|beautiful|gorgeous|great|rich|vibrant|pretty|lovely|stunning|nice|perfect) (?:the )?colou?rs?\b",
        r"\bcolou?rs? (?:is|are|was|were) (?:so |very |really |just |absolutely )?(?:beautiful|gorgeous|great|rich|vibrant|pretty|lovely|stunning|perfect|amazing)\b")),
    # ---- construction
    Theme("construction.seams", "construction", "Seams & stitching failing", "seams or stitching coming apart", "problem",
          near=(Near(r"seams?|stitch\w*|hems?|hemline|threads?",
                     r"came|coming|apart|ripped|rip|rips|split|splitting|unravel\w*|crooked|pucker\w*|fray\w*|undone|broke|broken|tore|torn|holes?|uneven",
                     4, body_part=False),)),
    Theme("construction.zip", "construction", "Zip problems", "zip problems", "problem",
          near=(Near(r"zip|zips|zipper|zippers|zipped|zipping",
                     r"broke|broken|stuck|sticks|snag\w*|hard|difficult|cheap|flimsy|catch\w*|bulky|wavy|pucker\w*|separat\w*|split|jam\w*|struggle\w*|impossible",
                     4, body_part=False),)),
    Theme("construction.buttons", "construction", "Buttons & closures", "buttons or closures failing", "problem",
          near=(Near(r"buttons?|snaps?|hooks?|buttonholes?|closures?",
                     r"fell|falling|came|coming|loose|missing|cheap|popped|popping|pop|gap|gaps|gape|gaping|gapes|pull|pulls|pulling|broke|broken",
                     3, body_part=False),)),
    Theme("construction.lining", "construction", "Lining issues", "lining problems", "rating",
          near=(Near(r"lining|liner|lined",
                     r"ripped|rip|tore|torn|bunch\w*|twist\w*|hangs?|hanging|sticks?|sticky|static|shorter|longer|peek\w*|shows?|showing|cheap|itchy|bulky",
                     4, body_part=False),),
          patterns=(r"\bunlined\b", r"\b(?:no|without(?: a)?) lining\b", r"\b(?:isn't|is not|wasn't|was not|not) (?:fully )?lined\b")),
    Theme("construction.pockets", "construction", "Missing / poor pockets", "missing or poor pockets", "problem", patterns=(
        r"\bno pockets\b", r"\b(?:wish|wished|if only)(?: it| they)? (?:had|has|have) (?:real |functional )?pockets\b",
        r"\bpockets? (?:are|is|were|was) (?:too |very |so |really )?(?:small|shallow|tiny|useless|fake|non[- ]?functional)\b",
        r"\b(?:fake|faux|shallow|tiny|useless) pockets\b", r"\bwithout pockets\b", r"\black(?:s|ing)? (?:of )?pockets\b",
        r"\bneeds? pockets\b")),
    Theme("construction.quality", "construction", "Poor make quality", "poor make quality", "problem", patterns=(
        r"\b(?:poor|bad|terrible|cheap|low|awful|horrible|shoddy|questionable) quality\b",
        r"\bquality (?:is|was|seems|seemed) (?:\w+ )?(?:poor|bad|terrible|cheap|low|awful|lacking)\b",
        r"\b(?:cheaply|poorly|badly) (?:made|constructed|sewn|finished)\b", r"\bf[ae]ll(?:ing)? apart\b",
        r"\bloose threads?\b", r"\bdefect(?:ive|s)?\b", r"\b(?:design )?flaws?\b", r"\b(?:looks?|looked|feels?|felt) cheap\b")),
    # ---- care
    Theme("care.dry_clean", "care", "Dry clean / hand wash only", "dry-clean or hand-wash-only care", "rating", patterns=(
        r"\bdry[- ]?clean(?:ed|ing)?(?: only)?\b", r"\bhand[- ]?wash(?:ed|ing)?(?: only)?\b")),
    Theme("care.durability", "care", "Doesn't survive wear & wash", "problems after washing or wearing", "problem", patterns=(
        r"\bafter (?:only )?(?:one|1|the first|first|a single|two|2|a few|few|several|the second|one or two|a couple(?: of)?) (?:wash|washes|washing|washings|wear|wears|wearing|wearings|times?)\b",
        r"\bfad(?:ed|es|ing)\b(?! (?:wash|denim|jeans|effect|look|out))")),
    # ---- comfort
    Theme("comfort.comfortable", "comfort", "Comfortable", "comfort", "praise", patterns=(
        r"\bcomf(?:ortable|y|iest|ier|ortably)\b", r"\bcozy\b", r"\bcosy\b"), negated_to="comfort.uncomfortable"),
    Theme("comfort.uncomfortable", "comfort", "Uncomfortable", "discomfort", "problem", patterns=(
        r"\buncomfortable\b", r"\bdig(?:s|ging)? (?:in|into)\b", r"\bdug (?:in|into)\b", r"\bstiff\b", r"\brigid\b")),
    # ---- warmth
    Theme("warmth.warm", "warmth", "Warm", "warmth", "praise", patterns=(
        r"(?<!too )\bwarm(?:th|est)?\b(?! (?:weather|months?|days?|climates?|temps?|temperatures?|spring|summer|tones?|colou?rs?|hues?|browns?|gr[ae]ys?|undertones?|nights?))",
        r"\btoasty\b", r"\bkeeps? (?:me|you) (?:\w+ )?warm\b"), negated_to="warmth.not_warm"),
    Theme("warmth.not_warm", "warmth", "Not warm enough", "it not being warm enough", "problem", patterns=(
        r"\bnot (?:\w+ )?warm enough\b", r"\b(?:still|was|were|got|get|felt|feel|am|i'm|freezing) (?:\w+ )?(?:cold|chilly|freezing)\b",
        r"\bwind (?:goes|blows|cuts|went) (?:right )?through\b", r"\b(?:too thin|not heavy enough|not thick enough) for (?:winter|cold|fall|autumn)\b")),
    Theme("warmth.too_warm", "warmth", "Too warm / doesn't breathe", "it being too warm or not breathing", "problem",
          patterns=(r"\btoo (?:hot|warm)\b", r"\b(?:doesn't|does not|don't|didn't|did not) breathe\b", r"\bsweat(?:y|ing)?\b",
                    r"\bstuffy\b", r"\bnot breathable\b")),
    # ---- value
    Theme("value.overpriced", "value", "Overpriced", "price or value concerns", "problem", patterns=(
        r"\boverpriced\b", r"\b(?:too|very|so|really|quite|a bit|a little|rather) (?:expensive|pricey|pricy)\b", r"\b(?:pricey|pricy)\b",
        r"\bnot worth (?:the|it|that)\b", r"\b(?:isn't|wasn't|is not|was not) worth\b",
        r"\b(?:wait|waiting|waited) (?:for|until) (?:it |this |a |the )?(?:to go |goes |to be )?(?:on )?sale\b",
        r"\b(?:only|definitely) (?:buy|get|worth it|worth buying|purchase)(?: it| this)? on sale\b",
        r"\bprice (?:is|was) (?:too |way |a bit |very )?(?:high|steep)\b",
        r"\bfor (?:the|this) price,? (?:i|it|you|one) (?:expected|would expect|should|could)\b")),
    Theme("value.good", "value", "Good value", "good value", "praise", patterns=(
        r"\b(?:great|good|excellent|fantastic|amazing) (?:value|price|deal)\b",
        r"\bworth (?:every penny|the (?:price|money|splurge|investment)|it)\b", r"\b(?:bargain|steal)\b"),
        negated_to="value.overpriced"),
    # ---- outcome
    Theme("returns.returned", "returns", "Returned or exchanged", "a return or exchange", "problem", patterns=(
        r"\breturn(?:ed|ing)?\b(?! (?:customer|policy|shopper))", r"\b(?:sent|send|sending) (?:it|them|this|these|both) back\b",
        r"\b(?:going|went) back\b", r"\bexchang(?:e|ed|ing)\b")),
)

THEME_BY_ID: dict[str, Theme] = {t.id: t for t in THEMES}
GROUP_LABELS = {"fit": "Fit", "fabric": "Fabric", "colour": "Colour", "construction": "Construction",
                "care": "Care", "comfort": "Comfort", "warmth": "Warmth", "value": "Price & value",
                "returns": "Returns"}


# --------------------------------------------------------------------------- matcher


@dataclass
class Mention:
    theme_id: str
    start: int  # offsets in the analysed string
    end: int
    raw_theme_id: str = ""  # the rule's own theme before a negation flip
    flipped: bool = False


@dataclass
class _Compiled:
    theme: Theme
    patterns: list[re.Pattern]
    near: list[tuple[re.Pattern, re.Pattern, int, bool]]
    excludes: list[re.Pattern] = field(default_factory=list)


@lru_cache(maxsize=1)
def _compiled() -> list[_Compiled]:
    out = []
    for t in THEMES:
        out.append(_Compiled(
            theme=t,
            patterns=[re.compile(p, re.I) for p in t.patterns],
            near=[(re.compile(rf"^(?:{n.a})$"), re.compile(rf"^(?:{n.b})$"), n.window, n.body_part) for n in t.near],
            excludes=[re.compile(p, re.I) for p in t.excludes],
        ))
    return out


def clauses(text: str) -> list[tuple[int, int]]:
    """(start, end) spans: sentences, further split at contrast words."""
    spans: list[tuple[int, int]] = []
    for m in _SENTENCE.finditer(text):
        s, e = m.start(), m.end()
        if not text[s:e].strip():
            continue
        cuts = [s] + [c.start() for c in _CONTRAST.finditer(text, s, e)] + [e]
        for a, b in zip(cuts, cuts[1:]):
            if text[a:b].strip():
                spans.append((a, b))
    return spans


def _norm_token(tok: str) -> str:
    return tok.replace("'", "")


def _tail_tokens(prefix: str, n: int) -> list[str]:
    """The last n tokens of `prefix`, not crossing a comma / 'and' / dash boundary."""
    cut = 0
    for m in _PART_BOUNDARY.finditer(prefix):
        cut = m.end()
    return [_norm_token(t) for t in _TOKEN.findall(prefix[cut:].lower())][-n:]


def is_negated(clause: str, start: int, end: int, descriptor_at: int | None = None) -> bool:
    """A negator in the 3 tokens before the hit (or before its descriptor), or a trailing "not at all"."""
    for pos in {start, descriptor_at if descriptor_at is not None else start}:
        toks = _tail_tokens(clause[:pos], 3)
        if any(t in NEGATORS for t in toks):
            return True
    return bool(_FOLLOW_NEG.match(clause[end:end + 40]))


def is_hedged(clause: str, start: int) -> bool:
    toks = [_norm_token(t) for t in _TOKEN.findall(clause[:start].lower())][-6:]
    return any(t in HEDGES for t in toks)


def _near_hits(clause: str, a: re.Pattern, b: re.Pattern, window: int, body_part: bool):
    toks = [(m.group(0), m.start(), m.end()) for m in _TOKEN.finditer(clause.lower())]
    for i, (ta, sa, ea) in enumerate(toks):
        if not a.match(ta):
            continue
        body_desc_clause = body_part and (
            (i > 0 and toks[i - 1][0] == "my" and i + 1 < len(toks) and toks[i + 1][0] in _COPULA)
            or any(t[0] in ("have", "i've", "ive") for t in toks[max(0, i - 4):i]))
        for j in range(max(0, i - window), min(len(toks), i + window + 1)):
            if j == i:
                continue
            tb, sb, eb = toks[j]
            if not b.match(tb):
                continue
            if body_part and tb in BODY_DESCRIPTORS and (j == i - 1 or body_desc_clause):
                continue  # "broad shoulders", "my hips are wide": the customer's body, not the garment
            yield min(sa, sb), max(ea, eb), sb
            break


def find_mentions(text: str) -> list[Mention]:
    """All theme mentions in `text`, after negation / hedging / exclusions (deterministic)."""
    out: list[Mention] = []
    if not text:
        return out
    for cs, ce in clauses(text):
        clause = text[cs:ce]
        for c in _compiled():
            if c.excludes and any(x.search(clause) for x in c.excludes):
                continue
            hits: list[tuple[int, int, int | None]] = [(m.start(), m.end(), None) for p in c.patterns for m in p.finditer(clause)]
            for a, b, w, bp in c.near:
                hits += list(_near_hits(clause, a, b, w, bp))
            for s, e, desc in sorted(hits):
                if is_hedged(clause, s):
                    continue
                theme_id = c.theme.id
                flipped = False
                if is_negated(clause, s, e, desc):
                    if not c.theme.negated_to:
                        continue
                    theme_id, flipped = c.theme.negated_to, True
                out.append(Mention(theme_id, cs + s, cs + e, raw_theme_id=c.theme.id, flipped=flipped))
    return out


def themes_in(text: str) -> set[str]:
    """Convenience for tests: the set of theme ids mentioned in `text`."""
    return {m.theme_id for m in find_mentions(text)}
