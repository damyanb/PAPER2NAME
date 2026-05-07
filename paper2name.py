# -*- coding: utf-8 -*-
"""Renombra PDFs (ApellidoAñoletra.pdf) usando solo metadatos + texto del propio PDF."""
import re
import shutil
import sys
import unicodedata
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.dont_write_bytecode = True

from pypdf import PdfReader

try:
    import fitz  # PyMuPDF, optional but preferred
    _HAS_FITZ = True
except Exception:  # pragma: no cover
    fitz = None  # type: ignore
    _HAS_FITZ = False


def _print(s: str) -> None:
    try:
        sys.stdout.write(s + "\n")
        sys.stdout.flush()
    except Exception:
        pass


# ----------------------- BASIC HELPERS -----------------------

_VALID_YEAR_RX = re.compile(r"^(?:18\d{2}|19\d{2}|20[0-3]\d)$")


def _valid_year(y: str) -> bool:
    if not y or not _VALID_YEAR_RX.match(y):
        return False
    n = int(y)
    return 1800 <= n <= 2030


def _strip_quotes(s: str) -> str:
    s = str(s).strip()
    return s.strip('"').strip("'").strip("\u201c").strip("\u201d").strip()


def _norm_unicode(s: str) -> str:
    if not s:
        return s
    s = s.replace("\u00a0", " ")
    return unicodedata.normalize("NFC", s)


_PARTICLES = frozenset(
    {
        "de", "del", "da", "das", "di", "do", "dos",
        "la", "le", "el", "lo", "los",
        "van", "von", "der", "den", "des", "ter", "ten",
        "du", "ben", "bin", "mc", "mac", "st",
    }
)

_MONTHS = frozenset(
    {
        "january", "february", "march", "april", "may", "june", "july",
        "august", "september", "october", "november", "december",
        "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
        "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
        "agosto", "septiembre", "octubre", "noviembre", "diciembre",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    }
)

_PLACE_TOKENS = frozenset(
    {
        "shanghai", "beijing", "tokyo", "kyoto", "osaka", "seoul", "moscow", "saintpetersburg",
        "petersburg", "berlin", "munich", "paris", "lyon", "marseille", "grenoble",
        "london", "manchester", "edinburgh", "dublin", "rome", "milan", "madrid", "barcelona",
        "stockholm", "oslo", "copenhagen", "helsinki", "vienna", "zurich", "geneva",
        "amsterdam", "brussels", "lisbon", "porto", "athens", "warsaw", "prague",
        "bangkok", "hanoi", "manila", "jakarta", "delhi", "mumbai", "chennai", "bangalore",
        "sydney", "melbourne", "auckland", "toronto", "ottawa", "montreal", "vancouver",
        "boston", "newyork", "chicago", "losangeles", "houston", "dallas", "atlanta",
        "santiago", "lima", "quito", "bogota", "caracas", "mexico", "monterrey", "guadalajara",
        "buenosaires", "saopaulo", "riodejaneiro", "brasilia", "salvador", "fortaleza",
        "california", "texas", "florida", "colorado", "oregon", "washington", "virginia",
        "michigan", "arizona", "minnesota", "ohio", "georgia", "indiana", "missouri",
        "ontario", "quebec", "alberta", "lajolla", "sandiego", "scripps", "woodshole",
        "shanghai", "guangzhou", "shenzhen", "wuhan", "tianjin", "edinburgh",
        "fluids", "fluid", "mech", "phys", "rev", "lett", "proc", "trans", "bull", "acta",
        "comp", "comm", "soc", "anal", "ann", "annu", "appl", "biol", "chem", "geol",
        "intl", "int", "natl", "nat", "scient", "sci",
    }
)

_BAD_SURNAME = frozenset(
    {
        "fluids", "mech", "phys", "rev", "lett", "proc", "trans", "bull", "acta",
        "comp", "comm", "soc", "anal", "ann", "annu", "appl", "biol", "chem", "geol",
        "intl", "natl", "scient", "sci", "vol", "volume", "issue", "edition",
        "abstract", "summary", "highlights", "keywords", "research", "article",
        "ich", "doi", "issn", "isbn", "page", "pages", "received", "accepted", "published",
        "available", "online", "revised", "communicated", "communication", "communications",
        "letters", "letter", "review", "reviews", "report", "reports", "study", "studies",
        "july", "june", "april", "march", "may", "august", "september", "october", "november",
        "december", "january", "february",
        "philadelphia", "boston", "shanghai", "tokyo", "santiago", "data", "only",
        "council", "supplementary", "correspondence", "edited", "reviewed", "citation", "citations",
        "fig", "table", "section", "chapter", "introduction", "background",
        "elsevier", "springer", "wiley", "blackwell", "mdpi", "ieee", "acm", "siam",
        "sciencedirect", "researchgate", "scopus", "ltd", "inc", "gmbh", "press",
        "physica", "nature", "science", "journal", "transform", "nearshore", "celeris",
        "jounal", "journal", "journals", "issue", "transactions",
        "sens", "physic", "physics", "remotesensing", "imaging",
        "international", "national", "global", "regional", "local",
        "topological", "kinematic", "infragravity", "estuarine", "antidune", "freak", "rogue",
        "soliton", "solitons", "wave", "waves", "vortex", "vortices",
        "korteweg", "vries", "boussinesq", "navier", "stokes",
        "celeris", "bathymetry", "drone", "imagery",
        "see", "profile", "publications", "reads", "downloaded",
        "editor", "editors", "series", "chief", "vol", "volume", "edition",
        "abstract", "highlights", "supplementary", "contents", "lists", "available",
    }
)

_TITLE_VOCAB = frozenset(
    """
    a an the of for in on at to with from by into onto upon over under between among
    is are be been being was were has have had this that these those some all any each every few many several
    other another such same using uses used use without within across along about around against above below
    near far energy stability dynamics analysis numerical theoretical computational empirical statistical
    experimental review reviews letter letters report reports note notes paper papers article articles study
    studies work works introduction abstract chapter section equation equations method methods model models
    theory theories approach approaches nonlinear linear shallow deep periodic discrete continuous integrable
    dispersive inverse hidden harmonic conservative dissipative finite infinite bounded unbounded boundary
    initial coastal marine fluid waves wave water tidal estuarine ocean turbulence vortex vortices vorticity
    soliton solitons solitary kinematic mixing characteristic interaction generator infragravity frequency
    bottom layer estuaries antidune simulations continuum based bathymetry mapping drone imagery rogue freak
    directional fission multi serre green naghdi assessing formation transport matter fundamental property
    kdv korteweg vries equation burgers traveling stability peakons mathematical communication transformation
    dissipation surf zone solution numerical compact finite volume scheme weakly boussinesq part one two three
    four five six seven eight nine ten field data only data summary supplementary research article
    """.split()
)

_AFFILIATION_HINTS = re.compile(
    r"(?i)(?:\b(?:university|universit[aá]|universidad|universit[éy]|d[eé]partement|"
    r"departamento|department|dept\.?|institute|institut|instituto|laboratory|laboratorio|laboratoire|"
    r"faculty|facult[aé]d|facult[ée]|escuela|school|college|coll[èe]ge|center|centre|centro|"
    r"avenue|avenida|street|calle|cedex|hospital|"
    r"china|france|spain|chile|brazil|brasil|mexico|argentina|peru|usa|u\.s\.a\.|united\s+states|"
    r"japan|korea|germany|italy|sweden|finland|norway|denmark|russia|india|australia|canada|portugal|netherlands|"
    r"received|accepted|published\s+online|in\s+revised\s+form|correspondence|email|e\-mail|"
    r"inc|incorporated|corp|corporation|ltd|limited|gmbh|s\.a\.|s\.r\.l\.|llc|co\.)\b)"
)
_EMAIL = re.compile(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+")

_ABSTRACT_RE = re.compile(
    r"\b(?:Abstract|ABSTRACT|Summary|SUMMARY|RESUMEN|Resumen|Highlights|HIGHLIGHTS|"
    r"Graphical\s+Abstract|Keywords|Key\s+Words|KEYWORDS)\b"
    r"|(?:^|\n)\s*1\s*[.)]\s*Introduction\b"
)


def _front_matter(text: str, limit: int = 2200) -> str:
    if not text:
        return ""
    m = _ABSTRACT_RE.search(text)
    if m and m.start() > 80:
        return text[: m.start()][:limit]
    return text[:limit]


def _is_garbage_text(text: str) -> bool:
    if not text:
        return True
    head = text[:3000]
    if len(head) < 200:
        return False
    slashes = head.count("/")
    if slashes / max(1, len(head)) > 0.10 and ("/C" in head or "/D" in head or "/G" in head):
        return True
    return False


def _list_pdfs(root: Path) -> List[Path]:
    out: List[Path] = []
    for p in root.iterdir():
        if not p.is_file() or p.suffix.lower() != ".pdf":
            continue
        if p.name.startswith(".__p2n_"):
            continue
        out.append(p)
    return sorted(out, key=lambda x: x.name.lower())


def _work_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _join_digit_only_lines(text: str) -> str:
    if not text:
        return text
    lines = text.splitlines()
    out: List[str] = []
    for line in lines:
        s = line.strip()
        if s and re.fullmatch(r"\d{1,3}(?:\s*[,;]\s*\d{1,3}){0,3}", s) and out:
            out[-1] = out[-1].rstrip() + s
        else:
            out.append(line)
    return "\n".join(out)


def _rejoin_broken_lines(text: str) -> str:
    """Some PDFs (dvips/Ghostscript) put each word, or even each letter, on its own line.
    Detect that case and rebuild text by joining adjacent fragments back together."""
    if not text:
        return text
    lines = text.splitlines()
    sample = [l for l in lines[:400] if l.strip()]
    if len(sample) < 30:
        return text
    avg = sum(len(l.strip()) for l in sample) / len(sample)
    if avg >= 6.0:
        return text
    out: List[str] = []
    buf = ""
    for line in lines:
        s = line.strip()
        if not s:
            if buf:
                out.append(buf)
                buf = ""
            out.append("")
            continue
        if not buf:
            buf = s
            continue
        last = buf[-1]
        first = s[0]
        if last.isalpha() and first.islower():
            buf += s
        elif len(buf) == 1 and last.isalpha() and first.isalpha():
            buf += s
        else:
            buf += " " + s
    if buf:
        out.append(buf)
    return "\n".join(out)


def _extract_text_fitz(path: Path, max_pages: int = 4) -> str:
    if not _HAS_FITZ:
        return ""
    try:
        doc = fitz.open(str(path))
    except Exception:
        return ""
    try:
        n = min(max_pages, doc.page_count)
        chunks: List[str] = []
        for i in range(n):
            try:
                chunks.append(doc[i].get_text("text") or "")
            except Exception:
                pass
        return _norm_unicode("\n".join(chunks))
    finally:
        try:
            doc.close()
        except Exception:
            pass


def _extract_text_pypdf(reader: PdfReader, max_pages: int = 4) -> str:
    chunks: List[str] = []
    n = min(max_pages, len(reader.pages))
    for i in range(n):
        try:
            t = reader.pages[i].extract_text()
        except Exception:
            t = ""
        if t:
            chunks.append(t)
    return _norm_unicode("\n".join(chunks))


def _extract_text(path: Path, reader: PdfReader, max_pages: int = 4) -> str:
    text = _extract_text_pypdf(reader, max_pages)
    if not text.strip() or _is_garbage_text(text):
        alt = _extract_text_fitz(path, max_pages)
        if alt and len(alt.strip()) >= 60:
            text = alt
    text = _rejoin_broken_lines(text)
    text = _join_digit_only_lines(text)
    return text


# ----------------------- YEAR EXTRACTION -----------------------

_YR = r"(18\d{2}|19\d{2}|20[0-3]\d)"

_PAT_REPRINT = re.compile(r"(?is)reprinted[\s\S]{0,400}?\b" + _YR)
_PAT_ANNU_REV = re.compile(r"(?i)\bannu\.\s*rev\.[^\n]{0,80}?\b" + _YR)
_PAT_JOURNAL_PAREN = re.compile(
    r"(?i)\b(?:J\.|Journal|Phys\.|Rev\.|Annu\.|Proc\.|Comm\.|Int\.|Mech\.|Sci\.|Appl\.|Math\.|Soc\.|"
    r"Trans\.|Bull\.|Acta|Lett\.|Eng\.|Fluid|Nature|Science)[^\n]{0,80}?\(\s*" + _YR + r"\s*\)"
)
_PAT_PUBLISHED_ONLINE = re.compile(r"(?i)published\s+online[^\n]{0,40}?\b" + _YR)
_PAT_PUBLISHED = re.compile(r"(?i)\bpublished[:\s][^\n]{0,40}?\b" + _YR)
_PAT_COPYRIGHT = re.compile(
    r"(?:©|\(c\)|c\u20dd|copyright[^\n]{0,40}?(?:©|c\u20dd)?)\s*c?\s*\b" + _YR,
    re.IGNORECASE,
)
_PAT_PUBLISHER = re.compile(
    r"(?i)\b" + _YR + r"\s+(?:John\s+Wiley|Elsevier|Springer|Cambridge|Annual\s+Reviews|"
    r"IEEE|ACM|Taylor\s*&\s*Francis|Wiley|Blackwell|Royal\s+Society|"
    r"American\s+Physical|American\s+Geophysical|Cambridge\s+University|Oxford\s+University)"
)
_PAT_RECEIVED = re.compile(
    r"(?i)(?:received|accepted|revised|in\s+revised\s+form|in\s+final\s+form)[^\n]{0,40}?\b" + _YR
)
_PAT_VOL_PAREN = re.compile(r"(?i)(?:vol\.?|volume)\s*\d{1,3}[^\n()]{0,40}\(\s*" + _YR + r"\s*\)")
_PAT_PAREN = re.compile(r"\(\s*" + _YR + r"\s*\)")
_PAT_DOI_YR = re.compile(r"(?i)doi[:\s/]\s*\S*?\.(\d{4})\.")
_PAT_INLINE_DATE = re.compile(
    r"(?i)(?:"
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|"
    r"Janvier|F[ée]vrier|Mars|Avril|Mai|Juin|Juillet|Ao[uû]t|Septembre|Octobre|Novembre|D[ée]cembre|"
    r"Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto|Septiembre|Octubre|Noviembre|Diciembre)"
    r"[a-z.]*\.?\s+\d{1,2},?\s+"
    r"|\ble\s+\d{1,2}\s+\w+\s+"
    r")(" + _YR + r")"
)
_PAT_SEMESTER = re.compile(r"(?i)\b(?:semestre|semester)\b[^\n]{0,30}\b" + _YR)
_PAT_HEAD_DATE = re.compile(r"^[^\n]{0,140}?,\s*" + _YR + r"\b", re.MULTILINE)
_PAT_ARXIV = re.compile(r"(?i)arxiv:\s*(\d{2})(\d{2})\.\d{4,5}")
_PAT_META_DATE = re.compile(r"D:\s*(\d{4})")


def _year_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    front = _front_matter(text, 4500)
    head = text[:8000]

    if "reprinted" in head[:1500].lower():
        m = _PAT_REPRINT.search(head[:2200])
        if m and _valid_year(m.group(1)):
            return m.group(1)

    for pat in (
        _PAT_ANNU_REV,
        _PAT_JOURNAL_PAREN,
        _PAT_PUBLISHED_ONLINE,
    ):
        m = pat.search(head)
        if m and _valid_year(m.group(1)):
            return m.group(1)

    for pat in (_PAT_PUBLISHER, _PAT_COPYRIGHT, _PAT_PUBLISHED):
        m = pat.search(head)
        if m and _valid_year(m.group(1)):
            return m.group(1)

    m = _PAT_VOL_PAREN.search(front)
    if m and _valid_year(m.group(1)):
        return m.group(1)

    m = _PAT_SEMESTER.search(front)
    if m and _valid_year(m.group(1)):
        return m.group(1)

    m = _PAT_INLINE_DATE.search(front[:2500])
    if m and _valid_year(m.group(1)):
        return m.group(1)

    for m in _PAT_PAREN.finditer(front[:1800]):
        if _valid_year(m.group(1)):
            return m.group(1)

    m = _PAT_RECEIVED.search(front)
    if m and _valid_year(m.group(1)):
        return m.group(1)

    m = _PAT_DOI_YR.search(front)
    if m and _valid_year(m.group(1)):
        return m.group(1)

    m = _PAT_HEAD_DATE.search(front[:1500])
    if m and _valid_year(m.group(1)):
        return m.group(1)

    m = _PAT_ARXIV.search(text[:8000])
    if m:
        yy = int(m.group(1))
        y = str(1900 + yy) if yy >= 91 else str(2000 + yy)
        if _valid_year(y):
            return y

    return None


_PAT_META_DATE_FULL = re.compile(r"D:\s*(\d{4})(\d{2})(\d{2})")


def _year_from_meta_title(reader: PdfReader) -> Optional[str]:
    title = _meta_title_str(reader)
    if not title:
        return None
    for m in re.finditer(r"(?<!\d)(18\d{2}|19\d{2}|20[0-3]\d)(?!\d)", title):
        if _valid_year(m.group(1)):
            return m.group(1)
    return None


def _year_from_metadata(reader: PdfReader) -> Optional[str]:
    m = reader.metadata
    if not m:
        return None
    for key in ("/CreationDate", "/ModDate"):
        raw = None
        if hasattr(m, "get"):
            raw = m.get(key)
        if not raw:
            continue
        mm = _PAT_META_DATE_FULL.search(str(raw))
        if mm:
            y, mo, da = mm.group(1), mm.group(2), mm.group(3)
            if not _valid_year(y):
                continue
            try:
                if not (1 <= int(mo) <= 12):
                    continue
                if not (1 <= int(da) <= 31):
                    continue
            except ValueError:
                continue
            return y
    return None


# ----------------------- AUTHOR EXTRACTION -----------------------


def _is_title_token(tok: str) -> bool:
    t = re.sub(r"[^\w\-']", "", tok.strip(), flags=re.UNICODE).lower()
    if not t:
        return False
    if len(t) < 2:
        return False
    return t in _TITLE_VOCAB


def _looks_like_title_line(line: str) -> bool:
    cleaned = re.sub(r"[^\w\s'\-]", " ", line, flags=re.UNICODE).strip()
    toks = [t for t in cleaned.split() if t]
    if not toks:
        return True
    title_hits = sum(1 for t in toks if _is_title_token(t))
    if len(toks) >= 4 and title_hits >= 2:
        return True
    return False


def _strip_dotted_initials_prefix(s: str) -> str:
    """'S.Trillo' / 'G.F.Clauss' -> surname tail; leaves other strings unchanged."""
    s = (s or "").strip()
    if not s:
        return s
    m = re.match(r"^(?:[A-ZÀ-Ý]\.){1,4}(.+)$", s)
    if m:
        rest = m.group(1).strip()
        if len(re.sub(r"[^\w\-'\u00C0-\u024F]", "", rest, flags=re.UNICODE)) >= 2:
            return rest
    return s


def _strip_one_letter_initial_glued_to_surname(tok: str) -> str:
    """PDF glue without dots: 'STrillo' / 'STrilloa' -> 'Trillo' / 'Trilloa'."""
    if not tok or len(tok) < 4:
        return tok
    m = re.match(r"^([A-ZÀ-Ý])([A-ZÀ-Ý][a-zà-ÿ]{2,})$", tok)
    if m:
        return m.group(2)
    return tok


def _normalize_surname(s: str) -> str:
    s = (s or "").strip()
    s = _strip_dotted_initials_prefix(s)
    s = _strip_one_letter_initial_glued_to_surname(s)
    s = re.sub(r"[^\w\-'\u00C0-\u024F]", "", s, flags=re.UNICODE)
    if not s:
        return ""
    if any(c.isdigit() for c in s):
        return ""
    if "-" in s:
        s = s.split("-", 1)[0]
    if s.isupper() or s.islower():
        s = s.capitalize()
    return s


def _is_valid_surname(s: str) -> bool:
    if not s:
        return False
    if len(s) < 2 or len(s) > 28:
        return False
    if any(c.isdigit() for c in s):
        return False
    low = s.lower()
    if low in _BAD_SURNAME:
        return False
    if low in _MONTHS:
        return False
    if low in _PLACE_TOKENS:
        return False
    if low in _TITLE_VOCAB:
        return False
    if len(s) >= 4 and not re.search(r"[aeiouyàáâãäåèéêëìíîïòóôõöøùúûüýÿ]", low):
        return False
    return True


def _strip_footnotes(line: str) -> str:
    line = re.sub(r"[\u2217\u2020\u2021\u00B6\u00A7\u204E\u2042\u2731\u22C6\*\^]+", " ", line)
    line = re.sub(r"(?<=[A-Za-zÀ-ÿ])\s*\d+(?:\s*[,;]\s*\d+)*", " ", line)
    line = re.sub(r"\s+", " ", line)
    return line.strip(" ,;")


def _is_initial_token(t: str) -> bool:
    t = t.rstrip(".")
    if not t:
        return False
    if len(t) <= 2 and t.replace(".", "").isalpha() and len(t.replace(".", "")) == 1:
        return True
    if re.fullmatch(r"(?:[A-ZÀ-Ý]\.){1,4}", t + "." if not t.endswith(".") else t):
        return True
    if re.fullmatch(r"(?:[A-ZÀ-Ý]\.)+[A-ZÀ-Ý]?", t):
        return True
    return False


_ELSEVIER_AFFIL_LETTERS = "abcdefghijk"


def _surname_from_name_segment(seg: str) -> Optional[str]:
    """Get surname (last meaningful token, with optional particle) from a single-author name like 'P. MEUNIER' or 'Cristián Escauriaza'."""
    if not seg:
        return None
    seg = re.sub(r"\(.*?\)", "", seg)
    seg = _strip_footnotes(seg)
    seg = re.sub(r"\s+", " ", seg).strip(" ,;.")
    if not seg:
        return None
    tokens = [t for t in seg.split() if t]
    out: List[str] = []
    for t in tokens:
        clean = t.rstrip(",;.")
        if not clean:
            continue
        clean = _strip_dotted_initials_prefix(clean)
        clean = _strip_one_letter_initial_glued_to_surname(clean)
        if not clean:
            continue
        if re.fullmatch(r"[A-ZÀ-Ý]", clean):
            continue
        if re.fullmatch(r"(?:[A-ZÀ-Ý]\.?){1,4}", clean) and "." in t:
            continue
        if re.fullmatch(r"[A-ZÀ-Ý]\.[A-ZÀ-Ý]\.?", clean):
            continue
        out.append(clean)
    while (
        len(out) >= 2
        and len(out[-1]) == 1
        and out[-1].lower() in _ELSEVIER_AFFIL_LETTERS
        and out[-2][-1].isalpha()
    ):
        out.pop()
    if not out:
        return None
    if len(out) >= 2 and out[-2].lower().strip(".") in _PARTICLES:
        compound = out[-2] + out[-1]
        return _normalize_surname(compound)
    last = out[-1]
    return _normalize_surname(last)


def _split_first_author_segment(line: str) -> str:
    """Split a multi-author line and return the first author's name segment."""
    s = line.strip()
    s = re.split(r"\s+(?:and|y)\s+", s, maxsplit=1, flags=re.IGNORECASE)[0]
    s = re.split(r"\s*&\s*", s, maxsplit=1)[0]
    s = re.split(r"\s*;\s*", s, maxsplit=1)[0]
    s = re.split(r"\s*\|\s*", s, maxsplit=1)[0]
    s = re.split(r"\s*[·•]\s*", s, maxsplit=1)[0]
    if "," in s:
        head, _, tail = s.partition(",")
        head = head.strip()
        tail_first = tail.split(",")[0].strip()
        if re.fullmatch(r"(?:[A-ZÀ-Ý]\.?\s*){1,4}", tail_first):
            return s.split(",", 2)[0] if False else (head + ", " + tail_first)
        return head
    return s


def _strip_elsevier_marker(token: str, line_context: str = "") -> str:
    """Strip a single trailing affiliation letter only when the PDF clearly separates it
    (e.g. 'Trillo a,'); avoids 'Albalawi' -> 'Albalaw' (false positive on final 'i')."""
    if not token or len(token) < 3:
        return token
    last = token[-1]
    if not last.islower() or last not in _ELSEVIER_AFFIL_LETTERS:
        return token
    base = token[:-1]
    if not base or not base[0].isupper():
        return token
    esc_b = re.escape(base)
    esc_l = re.escape(last)
    if line_context and re.search(
        esc_b + r"\s+" + esc_l + r"(?=\s*[,\*;:\u2217\u2020\u2021]|\s*$)",
        line_context,
        re.I,
    ):
        return base
    if last in "ij":
        return token
    inner = base[1:]
    if inner and inner.lower() == inner:
        if line_context and re.search(
            r",\s*(?:[\u2217\u2020\u2021\u00B6\u00A7\u204E\u2042\u2731\u22C6\*\^]|\d|[a-h]\b)",
            line_context,
        ):
            return base
        if re.search(r"[\u2217\u2020\u2021\u00B6\u00A7\u204E\u2042\u2731\u22C6\*\^]", line_context):
            return base
        if re.search(r"\b" + re.escape(token) + r"\b\s*,\s*[A-Z]", line_context):
            return base
    return token


def _surname_from_authors_line(line: str) -> Optional[str]:
    raw_line = line
    line = _strip_footnotes(line)
    seg = _split_first_author_segment(line)
    if "," in seg:
        head, _, tail = seg.partition(",")
        head = head.strip()
        tail_first = tail.split(",")[0].strip()
        if re.fullmatch(r"(?:[A-ZÀ-Ý]\.?\s*){1,4}", tail_first):
            tokens = [t for t in head.split() if t]
            if tokens:
                if len(tokens) >= 2 and tokens[-2].lower() in _PARTICLES:
                    cand = _normalize_surname(tokens[-2] + tokens[-1])
                else:
                    cand = _normalize_surname(_strip_elsevier_marker(tokens[-1], raw_line))
                if cand:
                    return cand
        seg = head
    sur = _surname_from_name_segment(seg)
    if sur:
        sur2 = _strip_elsevier_marker(sur, raw_line)
        return _normalize_surname(sur2) if sur2 != sur else sur
    return None


# ---- specific strategies ----


def _glue_broken_diacritic_word(s: str) -> str:
    """Repair surname strings broken by spacing diacritic marks: 'Duplanˇ ci´ c Leder' -> 'Duplancic Leder'."""
    s = re.sub(r"[ˇˆ´`˜¨\u02C7\u00B4\u00A8\u02C6\u02DC]", "", s)
    parts = re.split(r"\s+", s.strip())
    out: List[str] = []
    for p in parts:
        if not p:
            continue
        if out and len(p) <= 2 and p.isalpha() and not p[0].isupper():
            out[-1] = out[-1] + p
        else:
            out.append(p)
    return " ".join(out)


def _strategy_citation_block(text: str) -> Optional[str]:
    """Parse 'Citation:' blocks from journals. Handles multiple formats:
       a) Frontiers: 'Citation:\\nSurname F.M., Other A, ... (YYYY)'
       b) MDPI: 'Citation: Surname1, F.; Surname2, F.; ... Title.'
       c) Plain prose: 'Citation: Surname, FirstName, and FirstName Surname2.'"""
    head = text[:6000]
    m = re.search(r"(?im)\bCitation\s*:\s*((?:[^\n]+\n){0,5})", head)
    if not m:
        return None
    block = m.group(1).strip()
    block_oneline = re.sub(r"\s+", " ", block)
    m2 = re.match(
        r"\s*([A-ZÀ-Ý][A-Za-zÀ-ÿ\-'ˇˆ´` ]{1,60}?)\s*,\s*([A-ZÀ-Ý]\.?(?:\s*[A-ZÀ-Ý]\.?)?)\s*[;]",
        block_oneline,
    )
    if m2:
        sur_raw = _glue_broken_diacritic_word(m2.group(1))
        first_word = sur_raw.split()[0] if sur_raw.split() else ""
        sur = _normalize_surname(first_word)
        if sur and _is_valid_surname(sur):
            return sur
    m3 = re.match(
        r"\s*([A-ZÀ-Ý][A-Za-zÀ-ÿ\-']{1,30})\s+([A-ZÀ-Ý]{1,3})(?:[\s,]|$)",
        block_oneline,
    )
    if m3:
        sur = _normalize_surname(m3.group(1))
        if sur and _is_valid_surname(sur):
            return sur
    m4 = re.match(
        r"\s*([A-ZÀ-Ý][A-Za-zÀ-ÿ\-']{1,30})\s*,\s*([A-ZÀ-Ý][a-zà-ÿ]+)\s*,",
        block_oneline,
    )
    if m4:
        sur = _normalize_surname(m4.group(1))
        if sur and _is_valid_surname(sur):
            return sur
    return None


def _strategy_first_author_label(text: str) -> Optional[str]:
    """Explicit 'First Author: <Name>' label."""
    head = text[:5000]
    m = re.search(r"(?im)\bFirst\s+Author\s*:\s*([^\n]+)$", head)
    if not m:
        return None
    line = m.group(1).strip()
    sur = _surname_from_authors_line(line)
    if sur and _is_valid_surname(sur):
        return sur
    return None


_EDITOR_CONTEXT_RX = re.compile(
    r"(?i)\b(?:editor[\s\-]?in[\s\-]?chief|series\s+editor|guest\s+editor|"
    r"associate\s+editor|edited\s+by|review\s+editor|academic\s+editor|managing\s+editor|"
    r"editorial\s+board|editorial\s+team)\b"
)


def _line_in_editor_context(lines: List[str], idx: int, window: int = 4) -> bool:
    for j in range(max(0, idx - window), idx):
        if _EDITOR_CONTEXT_RX.search(lines[j] or ""):
            return True
    return False


def _find_authors_label_idx(lines: List[str]) -> Optional[int]:
    """Detect a generic '<N> authors[, including]:' label commonly used by ResearchGate-prefixed
    or other PDFs. Returns the index of the label line if found."""
    for i, l in enumerate(lines[:30]):
        s = (l or "").strip()
        if re.match(r"(?i)^\s*\d+\s+authors?(?:\s*,\s*including)?\s*[:.]?\s*$", s):
            return i
    return None


def _first_nonempty_after(lines: List[str], idx: int, limit: int) -> Optional[int]:
    for k in range(idx + 1, min(len(lines), limit)):
        if (lines[k] or "").strip():
            return k
    return None


def _score_author_line(line: str, lines: List[str], idx: int, boundary: int, affil_idx: Optional[int], authors_label_idx: Optional[int] = None) -> int:
    """Score how likely a line contains author names.
    The scoring is journal-agnostic: it uses universal cues like footnote markers,
    name patterns, separators (·, &, and), and proximity to affiliation lines."""
    s = line.strip()
    if not s:
        return -100
    L = len(s)
    if L > 250 or L < 4:
        return -100
    if _looks_like_title_line(s):
        return -50
    head_toks = s.split()[:4]
    if any(_is_title_token(t) for t in head_toks):
        return -30
    if re.match(
        r"(?i)^\s*(?:abstract|keywords|key\s+words|article(?:\s+(?:info|history|title))?|"
        r"received|accepted|published|copyright|doi|issn|isbn|introduction|conclusion|"
        r"see\s+(?:discussions|profile)|view\s+publication|contents\s+lists|available\s+(?:at|online)|"
        r"highlights|graphical\s+abstract|journal\s+homepage|to\s+cite|cite\s+as|"
        r"author\s+queries|author\s+contributions|reviewed\s+by|all\s+content|the\s+user)\b",
        s,
    ):
        return -50
    if re.match(
        r"(?i)^\s*(?:vol\.?|volume|issue|chapter|fig\.?|figure|table|page|reads|citations)\b",
        s,
    ):
        return -50
    if re.match(r"^\s*\d", s):
        return -10
    if re.search(r"https?://|www\.|/locate/", s, re.I):
        return -50
    if re.search(r"\bdoi:?\s*\d", s, re.I):
        return -30
    if _line_in_editor_context(lines, idx):
        return -40
    if _AFFILIATION_HINTS.search(s) and not re.search(r"[\u2217\u2020\u2021\*\^]", s):
        return -20
    if "@" in s and not re.search(r"[A-ZÀ-Ý][a-zà-ÿ]+\s+[A-ZÀ-Ý]", s):
        return -50
    if s.startswith(","):
        return -30

    score = 0
    title_case = re.findall(r"\b[A-ZÀ-Ý][A-Za-zà-ÿ\u2019']+\b", s)
    tc = len(title_case)
    if tc < 1:
        return -10
    if tc >= 2:
        score += 2
    if tc >= 3:
        score += 1

    if re.search(
        r"[A-ZÀ-Ý][a-zà-ÿ]{2,}[a-h](?=,\s*[\u2217\u2020\u2021\*\^]|,\s*\d|,\s*[a-h]\b|"
        r"\s*[\u2217\u2020\u2021\*\^])",
        s,
    ):
        score += 5
    if re.search(r"[A-ZÀ-Ý][a-zà-ÿ]{2,}\s*[\u2217\u2020\u2021\*\^]", s):
        score += 4
    if re.search(r",\s*[\u2217\u2020\u2021\*\^]", s):
        score += 3
    if re.search(r"[A-ZÀ-Ý][a-zà-ÿ]{2,}\s*\d(?!\d{3})", s) and not re.search(r"\(\d{4}\)", s):
        score += 2

    if "·" in s:
        score += 5

    if re.search(r"\b(?:[A-ZÀ-Ý]\.\s*){1,4}[A-ZÀ-Ý][a-zà-ÿ]+", s):
        score += 4
    if re.search(r"\b[A-Z][a-zà-ÿ]+\s+[A-ZÀ-Ý]{3,}\b", s):
        score += 5
    if re.search(r"\s+and\s+[A-ZÀ-Ý]", s):
        score += 2
    if re.search(r"\s+&\s+[A-ZÀ-Ý]", s):
        score += 2

    proximity_bonus = 0
    if affil_idx is not None and affil_idx > idx and affil_idx - idx <= 6:
        proximity_bonus = 4
    else:
        for j in range(idx + 1, min(len(lines), idx + 4)):
            n = lines[j].strip()
            if not n:
                continue
            if _AFFILIATION_HINTS.search(n) or "@" in n:
                proximity_bonus = 4
            break
    score += proximity_bonus

    for j in range(idx + 1, min(len(lines), idx + 3)):
        n = (lines[j] or "").strip()
        if not n:
            continue
        if re.match(
            r"^[a-h](?:\s*[,\*\u2217\u2020\u2021]\s*[a-h\d\*\u2217\u2020\u2021]*)+\s*$|"
            r"^[a-h]\s*$|"
            r"^[\*\u2217\u2020\u2021\^]+\s*$",
            n,
        ):
            score += 5
        break

    if authors_label_idx is not None and idx > authors_label_idx:
        first_after = _first_nonempty_after(lines, authors_label_idx, boundary)
        if first_after == idx:
            score += 8

    digits = sum(c.isdigit() for c in s)
    if L > 0 and digits / L > 0.3:
        score -= 5
    if re.search(r"\(\d{4}\)|\b\d{2,3}\s*[\(\[]\d{4}", s):
        score -= 3
    if re.search(r"\b(?:elsevier|springer|wiley|mdpi|ieee|acm|cambridge|oxford|sciencedirect|"
                 r"researchgate|frontiers|nature|science|j\.\s+fluid)\b", s, re.I) and \
            not re.search(r"[\u2217\u2020\u2021\*\^]", s):
        score -= 4

    return score


def _strategy_general_author_block(fm: str) -> Optional[str]:
    """Universal author detector: scan the front matter, score each line for author-likeness,
    and extract the first author surname from the best-scoring line.
    No per-journal patterns: relies on contextual cues that hold across publishers."""
    lines = fm.splitlines()
    if not lines:
        return None

    boundary = len(lines)
    for i, l in enumerate(lines[:30]):
        s = (l or "").strip()
        if not s:
            continue
        if re.match(
            r"(?i)^\s*(?:abstract|article\s+(?:info|history)|keywords|highlights|"
            r"graphical\s+abstract|introduction|received\b|accepted\b|published\b|"
            r"copyright|to\s+cite|author\s+queries|article\s+title)\b",
            s,
        ):
            boundary = i
            break

    affil_idx: Optional[int] = None
    for i, l in enumerate(lines[:max(boundary, 1)]):
        if "@" in (l or "") or _AFFILIATION_HINTS.search(l or ""):
            affil_idx = i
            break

    authors_label_idx = _find_authors_label_idx(lines[:max(boundary, 1)])

    candidates: List[Tuple[int, int, str]] = []
    for i in range(min(len(lines), max(boundary, 1))):
        s = lines[i].strip()
        if not s:
            continue
        score = _score_author_line(s, lines, i, boundary, affil_idx, authors_label_idx)
        if score > 0:
            candidates.append((score, i, s))

    if not candidates:
        return None

    candidates.sort(key=lambda x: (-x[0], x[1]))
    for _score, _idx, line in candidates[:6]:
        sur = _surname_from_authors_line(line)
        if sur and _is_valid_surname(sur):
            return sur
    return None


def _strategy_byline(text: str) -> Optional[str]:
    head = text[:3000]
    m = re.search(r"(?m)^\s*By\s+([A-Z][^\n]+?)\s*$", head)
    if not m:
        return None
    line = m.group(1)
    sur = _surname_from_authors_line(line)
    if sur and _is_valid_surname(sur):
        return sur
    return None


_MARKER_LINE_RX = re.compile(
    r"^\s*([A-ZÀ-Ý][\w'\-.\sÀ-ÿ]{4,80}?)"
    r"(?:[\u2217\u2020\u2021\u00B6\u00A7\u204E\u2042\u2731\u22C6\*\^]"
    r"|\s*\d+(?:\s*[,;]\s*\d+)*"
    r"|\s*\(\s*[a-zà-ÿ]"
    r")"
)


_JOURNAL_ABBR_RX = re.compile(
    r"(?i)\b(?:J\.|Int\.|Phys\.|Rev\.|Annu\.|Proc\.|Comm\.|Mech\.|Sci\.|Appl\.|Math\.|Soc\.|"
    r"Trans\.|Bull\.|Acta|Lett\.|Eng\.|Geol\.|Chem\.|Biol\.|Numer\.|Meth\.|Anal\.|Comp\.|"
    r"Vol\.|Volume|Issue|ISSN|ISBN|DOI|doi|arXiv|arxiv)\b"
)


def _looks_like_journal_or_code(seg: str) -> bool:
    if _JOURNAL_ABBR_RX.search(seg):
        return True
    toks = seg.split()
    if any(re.search(r"\d", t) for t in toks):
        return True
    return False


def _strategy_marker_line(fm: str) -> Optional[str]:
    lines = fm.splitlines()
    for line in lines[:35]:
        s = line.strip()
        if not s or len(s) < 6 or len(s) > 280:
            continue
        if re.match(
            r"(?i)^\s*(?:doi|arxiv|received|accepted|abstract|keywords|published|"
            r"figure|table|chapter|volume|page|edited|reviewed|isbn|issn|copyright|©|"
            r"int\.|j\.|phys\.|rev\.|annu\.|proc\.|comm\.|mech\.|sci\.|appl\.|math\.|"
            r"trans\.|bull\.|acta|lett\.|eng\.|vol\.|article|research)\b",
            s,
        ):
            continue
        m = _MARKER_LINE_RX.match(s)
        if not m:
            continue
        seg = m.group(1).strip(" ,;.")
        if _looks_like_title_line(seg):
            continue
        if _looks_like_journal_or_code(seg):
            continue
        sur = _surname_from_authors_line(seg)
        if sur and _is_valid_surname(sur):
            return sur
    return None


_INITIALS_THEN_NAME = re.compile(
    r"(?m)^\s*((?:[A-ZÀ-Ý]\.\s*){1,4}[A-ZÀ-Ý][A-Za-zÀ-ÿ\-']{1,30}(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ\-']{1,30})?)"
    r"(?:[\s,;]|$)"
)


def _strategy_initials_then_surname(fm: str) -> Optional[str]:
    lines = fm.splitlines()
    for line in lines[:35]:
        s = line.strip()
        if not s or "@" in s or _AFFILIATION_HINTS.search(s):
            continue
        if re.match(r"(?i)^(?:doi|arxiv|received|accepted|abstract|keywords|published|figure|table|chapter|volume|page|edited|reviewed|isbn|issn|copyright|©|by\s)", s):
            continue
        m = _INITIALS_THEN_NAME.match(s)
        if not m:
            continue
        seg = m.group(1)
        if _looks_like_title_line(seg):
            continue
        if _looks_like_journal_or_code(seg):
            continue
        sur = _surname_from_authors_line(seg)
        if sur and _is_valid_surname(sur):
            return sur
    return None


_ALLCAPS_LINE = re.compile(r"^\s*([A-ZÀ-Ý][A-ZÀ-Ý'´`\-\s\.]{3,60}[A-ZÀ-Ý])\s*$")
_ALLCAPS_INLINE_SURNAME = re.compile(
    r"^\s*([A-ZÀ-Ý][a-zà-ÿ]{1,20}\s+[A-ZÀ-Ý]{2,20})(?=\s|,|;|\d|\*|†|\u2020|\u2021|$)"
)


def _strategy_allcaps_surname_inline(fm: str) -> Optional[str]:
    lines = fm.splitlines()
    for line in lines[:35]:
        s = line.strip()
        if not s or "@" in s:
            continue
        if _AFFILIATION_HINTS.search(s):
            continue
        if re.match(r"(?i)^\s*(?:doi|arxiv|received|accepted|abstract|by\s|in\s|edited|reviewed)", s):
            continue
        m = _ALLCAPS_INLINE_SURNAME.match(s)
        if not m:
            continue
        seg = m.group(1).strip()
        toks = [t for t in seg.split() if t]
        if len(toks) < 2:
            continue
        first, last = toks[0], toks[-1]
        if _is_title_token(first) or _is_title_token(last):
            continue
        cand = _normalize_surname(last)
        if _is_valid_surname(cand):
            return cand
    return None


def _strategy_allcaps_alone(fm: str) -> Optional[str]:
    lines = fm.splitlines()
    for i, line in enumerate(lines[:30]):
        s = line.strip()
        if not s or "@" in s:
            continue
        m = _ALLCAPS_LINE.match(s)
        if not m:
            continue
        cand = m.group(1).strip()
        toks = [t for t in re.split(r"\s+", cand) if t]
        toks = [t.rstrip(".") for t in toks if not re.fullmatch(r"[A-ZÀ-Ý]\.", t)]
        if not (1 <= len(toks) <= 4):
            continue
        if any(_is_title_token(t) for t in toks):
            continue
        if any(t.lower() in _AFFIL_BLOCK for t in toks):
            continue
        ctx = " ".join(lines[i + 1 : i + 6]).lower()
        ctx_prev = " ".join(lines[max(0, i - 3) : i]).lower()
        if not (
            "@" in ctx
            or _AFFILIATION_HINTS.search(ctx)
            or _AFFILIATION_HINTS.search(ctx_prev)
        ):
            continue
        if len(toks) >= 2 and toks[-2].lower() in _PARTICLES:
            cand = toks[-2] + toks[-1]
        else:
            cand = toks[-1]
        cand_n = _normalize_surname(cand)
        if cand_n and not _is_title_token(cand_n):
            return cand_n
    return None


_AFFIL_BLOCK = frozenset(
    """
    university universidad universite institute institut instituto laboratory laboratorio
    laboratoire faculty facultad faculte escuela school college academy hospital department
    departamento departement avenue avenida street calle road brazil china france spain chile
    mexico argentina peru usa japan korea germany italy sweden finland norway denmark russia
    india australia canada portugal netherlands cambridge oxford harvard mit caltech ucla zurich
    edited reviewed citation correspondence woods hole
    """.split()
)


def _strategy_label_author(fm: str) -> Optional[str]:
    lines = [l.strip() for l in fm.splitlines()]
    for i, l in enumerate(lines[:25]):
        if re.match(r"(?i)^\s*(?:author|autor|by)\s*:?\s*$", l):
            for j in range(i + 1, min(len(lines), i + 4)):
                if not lines[j]:
                    continue
                seg = lines[j]
                if _looks_like_title_line(seg):
                    continue
                sur = _surname_from_authors_line(seg)
                if sur and not _is_title_token(sur):
                    return sur
                break
    return None


_PERSON_LINE = re.compile(
    r"^\s*([A-ZÀ-Ý][a-zà-ÿ'\-]{1,20}(?:\s+[A-ZÀ-Ý][a-zà-ÿ'\-]{1,20}){2,5})\s*$"
)


def _strategy_person_line(fm: str) -> Optional[str]:
    lines = fm.splitlines()
    for i, line in enumerate(lines[:30]):
        s = line.strip()
        if not s or "@" in s:
            continue
        if any(c.isdigit() for c in s):
            continue
        if "," in s:
            continue
        if _AFFILIATION_HINTS.search(s):
            continue
        if re.match(r"(?i)^(?:profesor|professora?|doctor|docente|estudiante|alumno)\b", s):
            continue
        m = _PERSON_LINE.match(s)
        if not m:
            continue
        toks = [t for t in s.split() if t]
        if not (3 <= len(toks) <= 6):
            continue
        if any(_is_title_token(t) for t in toks):
            continue
        if any(t.lower() in _AFFIL_BLOCK for t in toks):
            continue
        last = toks[-1]
        if len(toks) >= 2 and toks[-2].lower() in _PARTICLES:
            cand = toks[-2] + toks[-1]
        else:
            cand = last
        cand = _normalize_surname(cand)
        if cand and not _is_title_token(cand):
            return cand
    return None


def _xmp_creator(reader: PdfReader) -> Optional[str]:
    try:
        x = getattr(reader, "xmp_metadata", None)
    except Exception:
        return None
    if x is None:
        return None
    try:
        cr = getattr(x, "dc_creator", None)
    except Exception:
        return None
    if not cr:
        return None
    if isinstance(cr, (list, tuple)):
        return str(cr[0]).strip() if cr else None
    return str(cr).strip()


def _meta_author_str(reader: PdfReader) -> Optional[str]:
    m = reader.metadata
    if not m:
        return None
    a = getattr(m, "author", None)
    if a:
        return _strip_quotes(str(a))
    if hasattr(m, "get"):
        v = m.get("/Author")
        if v:
            return _strip_quotes(str(v))
    return None


def _meta_title_str(reader: PdfReader) -> Optional[str]:
    m = reader.metadata
    if not m:
        return None
    t = getattr(m, "title", None)
    if t:
        return _strip_quotes(str(t))
    if hasattr(m, "get"):
        v = m.get("/Title")
        if v:
            return _strip_quotes(str(v))
    return None


_BAD_META_AUTHORS = frozenset(
    {
        "berk yumer",
        "user",
        "admin",
        "administrator",
        "owner",
        "windows user",
        "default",
        "unknown",
    }
)


def _strategy_meta_author(reader: PdfReader) -> Optional[str]:
    for src in (_xmp_creator, _meta_author_str):
        raw = src(reader)
        if not raw:
            continue
        cleaned = raw.strip()
        if cleaned.lower() in _BAD_META_AUTHORS:
            continue
        first = re.split(
            r"\s+and\s+|\s*&\s*|\s*;\s*|\s+y\s+", cleaned, maxsplit=1, flags=re.IGNORECASE
        )[0].strip()
        if not first:
            continue
        sur = _surname_from_authors_line(first)
        if sur and not _is_title_token(sur):
            return sur
    return None


_THESIS_LABEL_RX = re.compile(
    r"(?i)^\s*(?:"
    r"soluci\W*on\s+examen\s+final|examen\s+final|"
    r"informe\s+(?:final|t\W*ecnico)|tesis(?:\s+de\s+\w+)?|tese|thesis|memoria|"
    r"author|autor|estudiante|alumno|alumna|presentado\s+por|presented\s+by|"
    r"submitted\s+by|elaborado\s+por|preparado\s+por"
    r")\s*[:.]?\s*$"
)


def _strategy_thesis_label(fm: str) -> Optional[str]:
    lines = fm.splitlines()
    n = len(lines)
    for i, line in enumerate(lines[:35]):
        s = line.strip()
        if not _THESIS_LABEL_RX.match(s):
            continue
        for j in range(i + 1, min(n, i + 5)):
            cand = lines[j].strip()
            if not cand:
                continue
            if "@" in cand or any(c.isdigit() for c in cand):
                break
            if _AFFILIATION_HINTS.search(cand):
                break
            toks = [t for t in re.split(r"\s+", cand) if t]
            if not (2 <= len(toks) <= 7):
                break
            last = toks[-1]
            last = re.sub(r"[^\w\-'\u00C0-\u024F]", "", last, flags=re.UNICODE)
            if not last:
                break
            sur = _normalize_surname(last)
            if _is_valid_surname(sur):
                return sur
            break
    return None


def _strategy_french_thesis(text: str) -> Optional[str]:
    """French thesis: 'présentée et soutenue ... par <Author> le <date>' / 'Thèse ... par <Author>'."""
    head = text[:6000]
    m = re.search(
        r"(?is)(?:pr[ée]sent[ée]e?\s+(?:et\s+soutenue?)?[^\n]{0,80}?par|"
        r"soutenue?[^\n]{0,40}?par|"
        r"th[èe]se[^\n]{0,80}?par|"
        r"par\s+\b)\s*([A-Z][^\n]{3,80}?)\s+(?:le\s+\d|\d{1,2}\s+\w+\s+\d{4})",
        head,
    )
    if not m:
        return None
    seg = m.group(1).strip()
    seg = re.sub(r"\s+", " ", seg)
    sur = _surname_from_authors_line(seg)
    if sur and _is_valid_surname(sur):
        return sur
    return None


def _strategy_meta_title_surname(reader: PdfReader) -> Optional[str]:
    title = _meta_title_str(reader)
    if not title:
        return None
    m = re.search(r"\b\d{1,4}\s+([A-ZÀ-Ý]{3,30})\b", title)
    if m:
        cand = m.group(1)
        if not _is_title_token(cand):
            return _normalize_surname(cand)
    return None


def _first_author_surname(reader: PdfReader, text: str) -> Optional[str]:
    fm = _front_matter(text, 4500)
    for fn in (
        lambda: _strategy_first_author_label(text),
        lambda: _strategy_french_thesis(text),
        lambda: _strategy_thesis_label(fm),
        lambda: _strategy_byline(text),
        lambda: _strategy_citation_block(text),
        lambda: _strategy_general_author_block(fm),
        lambda: _strategy_marker_line(fm),
        lambda: _strategy_initials_then_surname(fm),
        lambda: _strategy_allcaps_surname_inline(fm),
        lambda: _strategy_allcaps_alone(fm),
        lambda: _strategy_label_author(fm),
        lambda: _strategy_person_line(fm),
        lambda: _strategy_meta_author(reader),
        lambda: _strategy_meta_title_surname(reader),
    ):
        try:
            s = fn()
        except Exception:
            s = None
        if s and _is_valid_surname(s):
            return s
    return None


def _citation_parts(path: Path) -> Optional[Tuple[str, str]]:
    try:
        reader = PdfReader(str(path), strict=False)
    except Exception:
        return None
    if getattr(reader, "is_encrypted", False):
        try:
            if reader.decrypt("") == 0:
                return None
        except Exception:
            return None
    text = _extract_text(path, reader, 4)
    if _is_garbage_text(text):
        return None
    surname = _first_author_surname(reader, text)
    if not surname:
        return None
    year = _year_from_text(text)
    if not year:
        year = _year_from_meta_title(reader)
    if not year:
        year = _year_from_metadata(reader)
    if not year:
        return None
    surname = re.sub(r"[^\w\-'À-ÿ]", "", surname, flags=re.UNICODE)
    if len(surname) < 2 or len(surname) > 28:
        return None
    if _is_title_token(surname):
        return None
    return surname, year


# ----------------------- RENAME LOGIC -----------------------


_WIN_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_stem(s: str) -> str:
    s = _WIN_BAD.sub("", s)
    s = s.strip(" .")
    return s[:180] if s else ""


def _compact_surname(s: str) -> str:
    if "-" in s:
        s = s.split("-", 1)[0]
    return re.sub(r"[\s.]+", "", s)


def _dup_letter(i: int) -> str:
    s: List[str] = []
    x = i + 1
    while x:
        x, r = divmod(x - 1, 26)
        s.append(chr(ord("a") + r))
    return "".join(reversed(s))


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except Exception:
        return False


def _cleanup_stale(root: Path) -> None:
    for p in root.iterdir():
        if p.is_file() and p.name.startswith(".__p2n_"):
            try:
                p.unlink()
            except Exception:
                pass
    cache = root / "__pycache__"
    if cache.is_dir():
        shutil.rmtree(cache, ignore_errors=True)


def _bar(i: int, n: int, width: int = 28) -> str:
    if n <= 0:
        return "[" + ("-" * width) + "] 0/0"
    i = max(0, min(i, n))
    filled = int((i / n) * width)
    return "[" + ("#" * filled) + ("-" * (width - filled)) + f"] {i}/{n}"


def main() -> None:
    root = _work_dir()
    _cleanup_stale(root)
    pdfs = _list_pdfs(root)
    _print(f"paper2name: encontrados {len(pdfs)} PDF en {root}")
    items: List[Tuple[Path, str]] = []
    scanned = 0
    compatible = 0
    for idx, p in enumerate(pdfs, start=1):
        scanned += 1
        _print(_bar(idx - 1, len(pdfs)))
        parts = _citation_parts(p)
        if not parts:
            continue
        compatible += 1
        surname, year = parts
        stem = _safe_stem(_compact_surname(surname) + year)
        if not stem:
            continue
        items.append((p, stem))
    _print(_bar(len(pdfs), len(pdfs)))

    groups: Dict[str, List[int]] = {}
    for idx, (_, stem) in enumerate(items):
        groups.setdefault(stem.lower(), []).append(idx)

    new_stems: Dict[int, str] = {}
    for _, idxs in groups.items():
        base = items[idxs[0]][1]
        for k, i in enumerate(sorted(idxs, key=lambda j: str(items[j][0]).lower())):
            new_stems[i] = base + _dup_letter(k)

    planned: List[Tuple[Path, Path]] = []
    for i, (src, _) in enumerate(items):
        new_stem = new_stems[i]
        dst = src.with_name(new_stem + src.suffix.lower())
        if dst.name == src.name:
            continue
        if dst.exists() and not _same_file(dst, src):
            continue
        planned.append((src, dst))

    if not planned:
        _print(f"listo: {scanned} revisados, {compatible} compatibles, 0 renombrados.")
        return

    token = uuid.uuid4().hex[:10]
    staged: List[Tuple[Path, Path, Path]] = []
    for j, (src, dst) in enumerate(planned):
        mid = root / f".__p2n_{token}_{j:04d}{src.suffix.lower()}"
        staged.append((src, mid, dst))

    moved: List[Tuple[Path, str]] = []
    for src, mid, _ in staged:
        try:
            src.rename(mid)
            moved.append((mid, src.name))
        except Exception:
            for m, oname in reversed(moved):
                try:
                    m.rename(root / oname)
                except Exception:
                    pass
            return

    for src, mid, dst in staged:
        try:
            if dst.exists() and not _same_file(dst, mid):
                mid.rename(root / src.name)
                continue
            mid.rename(dst)
        except Exception:
            try:
                mid.rename(root / src.name)
            except Exception:
                pass

    _print(f"listo: {scanned} revisados, {compatible} compatibles, {len(planned)} renombrados.")


if __name__ == "__main__":
    main()
