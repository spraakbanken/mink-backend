"""Utility functions for calculating paths."""

import os

from flask import current_app as app


def get_corpora_dir(domain="local", user="", oc=None, mkdir=False):
    """Get user specific dir for corpora."""
    if domain not in ["local", "nc", "sparv"]:
        raise Exception(f"Failed to get corpora dir for '{domain}'. Domain does not exist.")
    if domain == "local":
        corpora_dir = os.path.join(app.instance_path, app.config.get("TMP_DIR"), user)
        if mkdir:
            os.makedirs(corpora_dir, exist_ok=True)
    elif domain == "nc":
        corpora_dir = app.config.get("CORPORA_DIR")
        if mkdir:
            oc.mkdir(corpora_dir)
    elif domain == "sparv":
        corpora_dir = os.path.join(app.config.get("REMOTE_CORPORA_DIR"), user)
    return corpora_dir


def get_corpus_dir(domain="local", user="", corpus_id="", oc=None, mkdir=False):
    """Get dir for given corpus."""
    send_mkdir = mkdir if domain == "local" else False
    corpora_dir = get_corpora_dir(domain, user, oc, send_mkdir, )
    corpus_dir = os.path.join(corpora_dir, corpus_id)
    if mkdir:
        if domain == "local":
            os.makedirs(corpus_dir, exist_ok=True)
        elif domain == "nc":
            oc.mkdir(corpus_dir)
    return corpus_dir


def get_export_dir(domain="local", user="", corpus_id="", oc=None, mkdir=False):
    """Get export dir for given corpus."""
    send_mkdir = mkdir if domain == "local" else False
    corpus_dir = get_corpus_dir(domain, user, corpus_id, oc, send_mkdir)
    export_dir = os.path.join(corpus_dir, app.config.get("SPARV_EXPORT_DIR"))
    if mkdir:
        if domain == "local":
            os.makedirs(export_dir, exist_ok=True)
        elif domain == "nc":
            oc.mkdir(export_dir)
    return export_dir


def get_source_dir(domain="local", user="", corpus_id="", oc=None, mkdir=False):
    """Get source dir for given corpus."""
    send_mkdir = mkdir if domain == "local" else False
    corpus_dir = get_corpus_dir(domain, user, corpus_id, oc, send_mkdir)
    source_dir = os.path.join(corpus_dir, app.config.get("SPARV_SOURCE_DIR"))
    if mkdir:
        if domain == "local":
            os.makedirs(source_dir, exist_ok=True)
        elif domain == "nc":
            oc.mkdir(source_dir)
    return source_dir


def get_config_file(domain="local", user="", corpus_id=""):
    """Get path to corpus config file."""
    corpus_dir = get_corpus_dir(domain, user, corpus_id)
    return os.path.join(corpus_dir, app.config.get("SPARV_CORPUS_CONFIG"))
