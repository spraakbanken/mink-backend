"""Corpus registry utilities.

The corpus registry lives in the cache and also on the local file system.
"""

from pathlib import Path

from flask import current_app as app
from flask import g

from minsb import exceptions


def init():
    """Init a corpus registry from the filesystem if it has not been initialized already."""
    if not g.cache.get_corpus_registry_initialized():
        corpus_registry = Path(app.instance_path) / app.config.get("CORPUS_REGISTRY")
        corpora = set()
        g.cache.set_corpus_registry_initialized(True)
        if corpus_registry.is_file():
            with open(corpus_registry, "r") as f:
                for corpus in f.readlines():
                    corpora.add(corpus.strip())
        g.cache.set_corpora(list(corpora))
        app.logger.debug(f"Corpora in cache: {len(g.cache.get_corpora())}")
        _save()


def get_all():
    """Get all existing corpus IDs."""
    return g.cache.get_corpora()


def add(corpus):
    """Add a job item to the queue."""
    corpora = set(g.cache.get_corpora())
    if corpus in corpora:
        raise exceptions.CorpusExists("Corpus ID already exists!")

    corpora.add(corpus)
    g.cache.set_corpora(list(corpora))
    app.logger.debug(f"Corpora in cache: {len(g.cache.get_corpora())}")
    _save()


def remove(corpus):
    """Remove corpus from registry."""
    corpora = set(g.cache.get_corpora())

    corpora.remove(corpus)
    g.cache.set_corpora(list(corpora))
    _save()


def _save():
    """Save corpus registry to file."""
    corpora = "\n".join(set(g.cache.get_corpora()))
    corpus_registry = Path(app.instance_path) / app.config.get("CORPUS_REGISTRY")
    with open(corpus_registry, "w") as f:
        f.write(corpora)
    # TODO: Do we risk saving too many times on simultaneous requests?
