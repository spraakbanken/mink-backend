"""Utility functions for calculating paths."""

import os
from pathlib import Path

from flask import current_app as app


def get_corpora_dir(domain="local", user="", oc=None, mkdir=False):
    """Get user specific dir for corpora."""
    if domain not in ["local", "nc", "sparv", "sparv-default"]:
        raise Exception(f"Failed to get corpora dir for '{domain}'. Domain does not exist.")
    if domain == "local":
        corpora_dir = Path(app.instance_path) / Path(app.config.get("TMP_DIR")) / Path(user)
        if mkdir:
            os.makedirs(str(corpora_dir), exist_ok=True)
    elif domain == "nc":
        corpora_dir = app.config.get("NC_CORPORA_DIR")
        if mkdir:
            oc.mkdir(str(corpora_dir))
    elif domain == "sparv":
        corpora_dir = Path(app.config.get("SPARV_CORPORA_DIR")) / Path(user)
    elif domain == "sparv-default":
        corpora_dir = Path(app.config.get("SPARV_DEFAULT_CORPORA_DIR"))
    return corpora_dir


def get_corpus_dir(domain="local", user="", corpus_id="", oc=None, mkdir=False):
    """Get dir for given corpus."""
    send_mkdir = mkdir if domain == "local" else False
    corpora_dir = get_corpora_dir(domain, user, oc, send_mkdir)
    corpus_dir = corpora_dir / Path(corpus_id)
    if mkdir:
        if domain == "local":
            os.makedirs(str(corpus_dir), exist_ok=True)
        elif domain == "nc":
            oc.mkdir(str(corpus_dir))
    return corpus_dir


def get_export_dir(domain="local", user="", corpus_id="", oc=None, mkdir=False):
    """Get export dir for given corpus."""
    send_mkdir = mkdir if domain == "local" else False
    corpus_dir = get_corpus_dir(domain, user, corpus_id, oc, send_mkdir)
    export_dir = corpus_dir / Path(app.config.get("SPARV_EXPORT_DIR"))
    if mkdir:
        if domain == "local":
            os.makedirs(str(export_dir), exist_ok=True)
        elif domain == "nc":
            oc.mkdir(str(export_dir))
    return export_dir


def get_source_dir(domain="local", user="", corpus_id="", oc=None, mkdir=False):
    """Get source dir for given corpus."""
    send_mkdir = mkdir if domain == "local" else False
    corpus_dir = get_corpus_dir(domain, user, corpus_id, oc, send_mkdir)
    source_dir = corpus_dir / Path(app.config.get("SPARV_SOURCE_DIR"))
    if mkdir:
        if domain == "local":
            os.makedirs(str(source_dir), exist_ok=True)
        elif domain == "nc":
            oc.mkdir(str(source_dir))
    return source_dir


def get_config_file(domain="local", user="", corpus_id=""):
    """Get path to corpus config file."""
    corpus_dir = get_corpus_dir(domain, user, corpus_id)
    return corpus_dir / Path(app.config.get("SPARV_CORPUS_CONFIG"))
