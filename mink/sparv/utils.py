"""Utility functions for calculating paths on the Sparv server."""

import os
import unicodedata
from pathlib import Path

from mink.core.config import settings


def get_corpora_dir(default_dir: bool = False) -> Path:
    """Get dir for corpora."""
    if default_dir:
        return Path(settings.SPARV_DEFAULT_CORPORA_DIR)
    return Path(settings.SPARV_CORPORA_DIR)


def get_corpus_dir(resource_id: str, default_dir: bool = False) -> Path:
    """Get dir for given corpus."""
    corpora_dir = get_corpora_dir(default_dir=default_dir)
    if default_dir:
        return corpora_dir / resource_id
    return corpora_dir / resource_id[len(settings.RESOURCE_PREFIX)] / resource_id


def get_export_dir(resource_id: str) -> Path:
    """Get export dir for given corpus."""
    corpus_dir = get_corpus_dir(resource_id)
    return corpus_dir / settings.SPARV_EXPORT_DIR


def get_work_dir(resource_id: str) -> Path:
    """Get sparv workdir for given corpus."""
    corpus_dir = get_corpus_dir(resource_id)
    return corpus_dir / settings.SPARV_WORK_DIR


def get_source_dir(resource_id: str) -> Path:
    """Get source dir for given corpus."""
    corpus_dir = get_corpus_dir(resource_id)
    return corpus_dir / settings.SPARV_SOURCE_DIR


def get_config_file(resource_id: str) -> Path:
    """Get path to corpus config file."""
    corpus_dir = get_corpus_dir(resource_id)
    return corpus_dir / settings.SPARV_CORPUS_CONFIG


def secure_filename(filename: str) -> Path:
    """Return a secure version of a filename."""
    filename = unicodedata.normalize("NFC", filename)

    for sep in os.path.sep, os.path.altsep:
        if sep:
            filename = filename.replace(sep, " ")

    return Path(filename.strip())
