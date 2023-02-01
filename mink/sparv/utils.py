"""Utility functions for calculating paths on the Sparv server."""

import os
import unicodedata
from pathlib import Path

from flask import current_app as app


def get_corpora_dir(default_dir: bool = False) -> Path:
    """Get dir for corpora."""
    if default_dir:
        return Path(app.config.get("SPARV_DEFAULT_CORPORA_DIR"))
    return Path(app.config.get("SPARV_CORPORA_DIR"))


def get_corpus_dir(corpus_id: str, default_dir: bool = False) -> Path:
    """Get dir for given corpus."""
    corpora_dir = get_corpora_dir(default_dir=default_dir)
    if default_dir:
        return corpora_dir / corpus_id
    return corpora_dir / corpus_id[len(app.config.get("RESOURCE_PREFIX"))] / corpus_id


def get_export_dir(corpus_id: str) -> Path:
    """Get export dir for given corpus."""
    corpus_dir = get_corpus_dir(corpus_id)
    export_dir = corpus_dir / Path(app.config.get("SPARV_EXPORT_DIR"))
    return export_dir


def get_work_dir(corpus_id: str) -> Path:
    """Get sparv workdir for given corpus."""
    corpus_dir = get_corpus_dir(corpus_id)
    work_dir = corpus_dir / Path(app.config.get("SPARV_WORK_DIR"))
    return work_dir


def get_source_dir(corpus_id: str) -> Path:
    """Get source dir for given corpus."""
    corpus_dir = get_corpus_dir(corpus_id)
    source_dir = corpus_dir / Path(app.config.get("SPARV_SOURCE_DIR"))
    return source_dir


def get_config_file(corpus_id: str) -> Path:
    """Get path to corpus config file."""
    corpus_dir = get_corpus_dir(corpus_id)
    return corpus_dir / Path(app.config.get("SPARV_CORPUS_CONFIG"))


def secure_filename(filename: str) -> str:
    """Return a secure version of a filename."""
    filename = unicodedata.normalize("NFC", filename)

    for sep in os.path.sep, os.path.altsep:
        if sep:
            filename = filename.replace(sep, " ")

    return filename.strip()
