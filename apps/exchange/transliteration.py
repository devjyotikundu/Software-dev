"""Offline romanization (transliteration) for Hindi and Bengali, and script/
language detection. Pure Python: works with no AI service at all.

Transliteration changes the *script*, not the language:
    आप कैसे हैं?  ->  aap kaise hain?      (still Hindi)
Translation (see translation.py) changes the language:
    आप कैसे हैं?  ->  How are you?

Romanization follows common chat spelling (aa, ee, oo for long vowels) and
drops the silent inherent vowel the way Hindi speakers type it:
at the end of a word (कमल -> kamal) and in the middle when a vowel comes
before and an explicit vowel after (मिलते -> milte, करता -> kartaa).
"""
import re

# ------------------------------------------------------------------ tables
DEVANAGARI = {
    "consonants": dict(zip(
        "कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसह",
        ["k", "kh", "g", "gh", "n", "ch", "chh", "j", "jh", "n", "t", "th", "d", "dh", "n",
         "t", "th", "d", "dh", "n", "p", "ph", "b", "bh", "m", "y", "r", "l", "v", "sh", "sh", "s", "h"])),
    "nukta": {"क": "q", "ख": "kh", "ग": "g", "ज": "z", "ड": "r", "ढ": "rh", "फ": "f", "य": "y"},
    "vowels": dict(zip("अआइईउऊऋएऐओऔ", ["a", "aa", "i", "ee", "u", "oo", "ri", "e", "ai", "o", "au"])),
    "signs": dict(zip("ािीुूृेैोौ", ["aa", "i", "ee", "u", "oo", "ri", "e", "ai", "o", "au"])),
    "inherent": "a", "virama": "्", "nukta_mark": "़",
    "marks": {"ं": "n", "ँ": "n", "ः": "h", "।": ".", "॥": "."},
    "digits": "०१२३४५६७८९", "medial_schwa_deletion": True,
}
BENGALI = {
    "consonants": dict(zip(
        "কখগঘঙচছজঝঞটঠডঢণতথদধনপফবভমযরলশষসহৎ",
        ["k", "kh", "g", "gh", "ng", "ch", "chh", "j", "jh", "n", "t", "th", "d", "dh", "n",
         "t", "th", "d", "dh", "n", "p", "ph", "b", "bh", "m", "j", "r", "l", "sh", "sh", "s", "h", "t"])),
    "nukta": {"ড": "r", "ঢ": "rh", "য": "y"},
    "vowels": dict(zip("অআইঈউঊঋএঐওঔ", ["o", "aa", "i", "ee", "u", "oo", "ri", "e", "oi", "o", "ou"])),
    "signs": dict(zip("ািীুূৃেৈোৌ", ["aa", "i", "ee", "u", "oo", "ri", "e", "oi", "o", "ou"])),
    "inherent": "o", "virama": "্", "nukta_mark": "়",
    "marks": {"ং": "ng", "ঁ": "n", "ঃ": "h", "।": "."},
    "digits": "০১২৩৪৫৬৭৮৯", "medial_schwa_deletion": False,
    "precomposed": {"ড়": "r", "ঢ়": "rh", "য়": "y"},
}
SCRIPTS = {"devanagari": DEVANAGARI, "bengali": BENGALI}
RANGES = {"devanagari": ("\u0900", "\u097F"), "bengali": ("\u0980", "\u09FF")}


def script_of(text):
    """'devanagari', 'bengali', 'latin' or 'none', by majority of letters."""
    counts = {"devanagari": 0, "bengali": 0, "latin": 0}
    for ch in text:
        for name, (low, high) in RANGES.items():
            if low <= ch <= high:
                counts[name] += 1
        if ch.isascii() and ch.isalpha():
            counts["latin"] += 1
    best = max(counts, key=counts.get)
    return best if counts[best] else "none"


# ------------------------------------------------------------- romanize
def _syllables(word, table):
    """Split one word into (consonant_or_vowel_text, vowel_text, explicit_vowel) units."""
    units, i = [], 0
    cons, vowels, signs = table["consonants"], table["vowels"], table["signs"]
    while i < len(word):
        ch = word[i]
        if ch in table.get("precomposed", {}):
            base = table["precomposed"][ch]
            i += 1
        elif ch in cons:
            base = cons[ch]
            i += 1
            if i < len(word) and word[i] == table["nukta_mark"]:
                base = table["nukta"].get(ch, base)
                i += 1
        else:
            if ch in vowels:
                units.append(["", vowels[ch], True])
            elif ch in table["marks"]:
                if units:
                    units[-1][1] += table["marks"][ch]
                else:
                    units.append(["", table["marks"][ch], True])
            elif ch in table["digits"]:
                units.append([str(table["digits"].index(ch)), "", True])
            else:
                units.append([ch, "", True])
            i += 1
            continue
        # consonant: what vowel follows?
        if i < len(word) and word[i] == table["virama"]:
            units.append([base, "", True])
            i += 1
        elif i < len(word) and word[i] in signs:
            units.append([base, signs[word[i]], True])
            i += 1
        else:
            units.append([base, table["inherent"], False])  # inherent vowel, may be silent
        while i < len(word) and word[i] in table["marks"]:
            units[-1][1] += table["marks"][word[i]]
            i += 1
    return units


def _romanize_word(word, table):
    units = _syllables(word, table)
    inherent = table["inherent"]
    for index, unit in enumerate(units):
        if unit[2] or not unit[0]:
            continue
        is_last = index == len(units) - 1
        if is_last and index > 0:
            unit[1] = unit[1][len(inherent):]          # silent at the end of a word
        elif table["medial_schwa_deletion"] and 0 < index < len(units) - 1:
            prev_has_vowel = bool(units[index - 1][1])
            nxt = units[index + 1]
            if prev_has_vowel and nxt[0] and nxt[2] and nxt[1]:
                unit[1] = unit[1][len(inherent):]      # silent in the middle (मिलते -> milte)
    return "".join(c + v for c, v, _ in units)


def romanize(text):
    """Romanize Hindi (Devanagari) or Bengali text; other characters pass through."""
    out = []
    for token in re.split(r"(\s+|[^\w\u0900-\u09FF]+)", text):
        if not token:
            continue
        name = script_of(token)
        out.append(_romanize_word(token, SCRIPTS[name]) if name in SCRIPTS else token)
    return "".join(out)


# ------------------------------------------------------- language guess
ROMAN_HINDI_WORDS = set("""
hai hain ho hoon hu tha thi the kya kyu kyun kaise kaisa kaisi kahan kaha kab kaun kitna kitne
mera meri mere mujhe mujhko tum tumhara tumhari aap aapka aapki hum hamara ham main mai
nahi nahin na haan ji acha accha achha theek thik bahut bohot thoda thodi jaldi abhi kal aaj
raha rahe rahi karo karna karta karti kar gaya gayi ja jao jaana aana aao aata aati milte milna
bhook pyaas lagi laga lagta yaar bhai dost khana pani ghar kuch sab sabhi bhi bhi aur ya lekin
""".split())
ROMAN_BENGALI_WORDS = set("""
ami tumi apni tomar amar kemon acho achen achi ki keno kothay kokhon bhalo bhalobashi khub
na hya haan ekhon kal aaj jabo jachho korbo kori koro boli bolo shuno dekho khabo khete
""".split())


def guess_language(text):
    """Best guess for UI hints: 'hi', 'bn', 'hi-Latn', 'bn-Latn', 'en' or 'unknown'.

    The AI translator does its own detection; this only decides which buttons
    to show and which voice to read with.
    """
    script = script_of(text)
    if script == "devanagari":
        return "hi"
    if script == "bengali":
        return "bn"
    if script != "latin":
        return "unknown"
    words = re.findall(r"[a-z]+", text.lower())
    if not words:
        return "unknown"
    hindi = sum(w in ROMAN_HINDI_WORDS for w in words)
    bengali = sum(w in ROMAN_BENGALI_WORDS for w in words)
    threshold = max(1, round(len(words) * 0.34))
    if max(hindi, bengali) >= threshold:
        return "hi-Latn" if hindi >= bengali else "bn-Latn"
    return "en"
