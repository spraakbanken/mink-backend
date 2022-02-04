"""Utility functions for calculating paths on the Sparv server."""

from pathlib import Path

from flask import current_app as app


def get_corpora_dir(user):
    """Get user specific dir for corpora."""
    if not user:
        corpora_dir = Path(app.config.get("SPARV_DEFAULT_CORPORA_DIR"))
    else:
        corpora_dir = Path(app.config.get("SPARV_CORPORA_DIR")) / Path(user)
    return corpora_dir


def get_corpus_dir(user, corpus_id):
    """Get dir for given corpus."""
    corpora_dir = get_corpora_dir(user=user)
    corpus_dir = corpora_dir / Path(corpus_id)
    return corpus_dir


def get_export_dir(user, corpus_id):
    """Get export dir for given corpus."""
    corpus_dir = get_corpus_dir(user, corpus_id)
    export_dir = corpus_dir / Path(app.config.get("SPARV_EXPORT_DIR"))
    return export_dir


def get_work_dir(user, corpus_id):
    """Get sparv workdir for given corpus."""
    corpus_dir = get_corpus_dir(user, corpus_id)
    work_dir = corpus_dir / Path(app.config.get("SPARV_WORK_DIR"))
    return work_dir


def get_source_dir(user, corpus_id):
    """Get source dir for given corpus."""
    corpus_dir = get_corpus_dir(user, corpus_id)
    source_dir = corpus_dir / Path(app.config.get("SPARV_SOURCE_DIR"))
    return source_dir


def get_config_file(user, corpus_id):
    """Get path to corpus config file."""
    corpus_dir = get_corpus_dir(user, corpus_id)
    return corpus_dir / Path(app.config.get("SPARV_CORPUS_CONFIG"))
