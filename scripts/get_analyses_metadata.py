"""Helper script to download the analyses metadata from the Spraakbanken Metadata API."""

import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

URL = "https://ws.spraakbanken.gu.se/ws/metadata/v3/analyses"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FILE = PROJECT_ROOT / "instance" / "available_analyses.json"

WHITELISTED_ANNOTATIONS = [
    # Stanford eng
    "sbx-eng-dependency-stanford",
    "sbx-eng-lemmatization-stanford",
    "sbx-eng-namedentity-stanford",
    "sbx-eng-pos-stanford",
    "sbx-eng-sentence-stanford",
    "sbx-eng-tokenization-stanford",
    "sbx-eng-upos-stanford",
    # Stanza eng
    "sbx-eng-msd-stanza-ufeats",
    "sbx-eng-namedentity-stanza",
    "sbx-eng-pos-stanza-upos",
    "sbx-eng-pos-stanza",
    "sbx-eng-sentence-stanza",
    "sbx-eng-tokenization-stanza",
    "sbx-eng-dependency-stanza",
    "sbx-eng-lemmatization-stanza",
    # Treetagger
    "sbx-bul-lemmatization-treetagger",
    "sbx-bul-pos-treetagger",
    "sbx-bul-upos-treetagger",
    "sbx-deu-lemmatization-treetagger",
    "sbx-deu-pos-treetagger",
    "sbx-deu-upos-treetagger",
    "sbx-eng-lemmatization-treetagger",
    "sbx-eng-pos-treetagger",
    "sbx-eng-upos-treetagger",
    "sbx-est-lemmatization-treetagger",
    "sbx-est-pos-treetagger",
    "sbx-est-upos-treetagger",
    "sbx-fin-lemmatization-treetagger",
    "sbx-fin-pos-treetagger",
    "sbx-fra-lemmatization-treetagger",
    "sbx-fra-pos-treetagger",
    "sbx-fra-upos-treetagger",
    "sbx-ita-lemmatization-treetagger",
    "sbx-ita-pos-treetagger",
    "sbx-ita-upos-treetagger",
    "sbx-lat-lemmatization-treetagger",
    "sbx-lat-pos-treetagger",
    "sbx-lat-upos-treetagger",
    "sbx-nld-lemmatization-treetagger",
    "sbx-nld-pos-treetagger",
    "sbx-nld-upos-treetagger",
    "sbx-pol-lemmatization-treetagger",
    "sbx-pol-pos-treetagger",
    "sbx-pol-upos-treetagger",
    "sbx-ron-lemmatization-treetagger",
    "sbx-ron-pos-treetagger",
    "sbx-ron-upos-treetagger",
    "sbx-rus-lemmatization-treetagger",
    "sbx-rus-pos-treetagger",
    "sbx-rus-upos-treetagger",
    "sbx-slk-lemmatization-treetagger",
    "sbx-slk-pos-treetagger",
    "sbx-slk-upos-treetagger",
    "sbx-spa-lemmatization-treetagger",
    "sbx-spa-pos-treetagger",
    "sbx-spa-upos-treetagger",
    # Segmentation
    "sbx-mul-paragraph-sparv-blanklines",
    "sbx-mul-paragraph-sparv-linebreaks",
    "sbx-mul-paragraph-sparv-whitespace",
    "sbx-mul-sentence-sparv-blanklines",
    "sbx-mul-sentence-sparv-linebreaks",
    "sbx-mul-sentence-sparv-punctuation",
    "sbx-mul-sentence-sparv-whitespace",
    "sbx-mul-tokenization-sparv-blanklines",
    "sbx-mul-tokenization-sparv-linebreaks",
    "sbx-mul-tokenization-sparv-whitespace",
    "sbx-swe-tokenization-sparv-betterword",
    "sbx-swe-sentence-sparv-storsuc",
    # Misc swe
    "sbx-swe-compound-sparv-saldolemgram",
    "sbx-swe-compound-sparv-saldowords",
    "sbx-swe-dependency-malt-treebank",
    "sbx-swe-dependency-stanza-stanzasynt",
    "sbx-swe-geotagcontext-sparv",
    "sbx-swe-geotagmetadata-sparv",
    "sbx-swe-lemgram-sparv-saldo",
    "sbx-swe-lemgram-sparv-saldo_dalin_swedberg_1800",
    "sbx-swe-lemgram-sparv-schlyter_soderwall_fsv",
    "sbx-swe-lemmatization-sparv-saldo",
    "sbx-swe-lemmatization-sparv-saldo2",
    "sbx-swe-lemmatization-sparv-saldo_dalin_swedberg_1800",
    "sbx-swe-lemmatization-sparv-schlyter_soderwall_fsv",
    "sbx-swe-lemmatization-stanza-stanzalem",
    "sbx-swe-lexical_classes_text-sparv-blingbring",
    "sbx-swe-lexical_classes_text-sparv-swefn",
    "sbx-swe-lexical_classes_token-sparv-blingbring",
    "sbx-swe-lexical_classes_token-sparv-swefn",
    "sbx-swe-msd-hunpos-suc3",
    "sbx-swe-msd-hunpos-suc3_1800",
    "sbx-swe-msd-stanza-stanzamorph-suc3",
    "sbx-swe-msd-stanza-stanzamorph-ufeats",
    "sbx-swe-namedentity-swener",
    "sbx-swe-pos-hunpos-suc3",
    "sbx-swe-pos-hunpos-suc3_1800",
    "sbx-swe-pos-stanza-stanzamorph",
    "sbx-swe-readability-sparv-lix",
    "sbx-swe-readability-sparv-nk",
    "sbx-swe-readability-sparv-ovix",
    "sbx-swe-sense-sparv-saldo",
    "sbx-swe-sense-sparv-saldo_dalin_swedberg_1800",
    "sbx-swe-sense-sparv",
    "sbx-swe-sentiment-sparv-sensaldo",
    "sbx-swe-spelling_variants-sparv-fsv",
]

# Korp-specific annotation renaming
ANNOTATION_EXPANSIONS = {
    "<token>:stanza.dephead_ref": "dephead",
    "<token>:malt.dephead_ref": "dephead",
    "<sentence>:geo.geo_context": "geocontext",
    "<token>:saldo.lemgram": "lex",
    "<token>:hist.lemgram": "lex",
    "<token>:saldo.baseform2": "lemma",
    "<token>:hist.baseform": "lemma",
}


def main() -> None:
    """Download the analyses metadata from the Spraakbanken Metadata API and output it as JSON."""
    try:
        req = Request(URL, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=30) as resp:
            data = json.load(resp)
    except Exception as e:
        print(f"Failed to download JSON: {e}", file=sys.stderr)  # ruff: ignore[print]
        sys.exit(1)

    resources = data.get("resources", [])

    filtered_resources = [
        {
            key: value
            for key, value in {
                "id": r.get("id"),
                "name": r.get("name"),
                # Fix ANNOTATION_EXPANSIONS
                "annotations": (
                    [
                        f"{annotation} as {ANNOTATION_EXPANSIONS[annotation]}"
                        if annotation in ANNOTATION_EXPANSIONS
                        else annotation
                        for annotation in r["annotations"]
                    ]
                    if r.get("annotations") is not None
                    else None
                ),
                "task": r.get("task"),
                "analysis_unit": r.get("analysis_unit"),
                "short_description": r.get("short_description"),
                "languages": r.get("languages"),
                "language_varieties": r.get("language_varieties"),
            }.items()
            if value not in (None, [], {}, "")
        }
        for r in resources
        # Only include resources that are not collections and are whitelisted
        if not r.get("collection") and r.get("id") in WHITELISTED_ANNOTATIONS
    ]

    OUTPUT_FILE.write_text(json.dumps(filtered_resources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
