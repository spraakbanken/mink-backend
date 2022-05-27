"""Utility functions for calculating paths on the Sparv server."""

from pathlib import Path

from flask import current_app as app


def get_corpora_dir(default_dir=False):
    """Get dir for corpora."""
    if default_dir:
        return Path(app.config.get("SPARV_DEFAULT_CORPORA_DIR"))
    return Path(app.config.get("SPARV_CORPORA_DIR"))


def get_corpus_dir(corpus_id, default_dir=False):
    """Get dir for given corpus."""
    corpora_dir = get_corpora_dir(default_dir=default_dir)
    corpus_dir = corpora_dir / Path(corpus_id)
    return corpus_dir


def get_export_dir(corpus_id):
    """Get export dir for given corpus."""
    corpus_dir = get_corpus_dir(corpus_id)
    export_dir = corpus_dir / Path(app.config.get("SPARV_EXPORT_DIR"))
    return export_dir


def get_work_dir(corpus_id):
    """Get sparv workdir for given corpus."""
    corpus_dir = get_corpus_dir(corpus_id)
    work_dir = corpus_dir / Path(app.config.get("SPARV_WORK_DIR"))
    return work_dir


def get_source_dir(corpus_id):
    """Get source dir for given corpus."""
    corpus_dir = get_corpus_dir(corpus_id)
    source_dir = corpus_dir / Path(app.config.get("SPARV_SOURCE_DIR"))
    return source_dir


def get_config_file(corpus_id):
    """Get path to corpus config file."""
    corpus_dir = get_corpus_dir(corpus_id)
    return corpus_dir / Path(app.config.get("SPARV_CORPUS_CONFIG"))
