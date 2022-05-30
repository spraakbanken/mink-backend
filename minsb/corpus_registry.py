"""Corpus registry utilities.

The corpus registry lives in the cache and also on the local file system.
"""

from pathlib import Path
from typing import List

from flask import current_app as app
from flask import g

from minsb import exceptions


def init() -> None:
    """Init a corpus registry from the filesystem if it has not been initialized already."""
    if not g.cache.get_corpus_registry_initialized():
        corpus_registry_dir = Path(app.instance_path) / app.config.get("CORPUS_REGISTRY")
        corpora = set()
        g.cache.set_corpus_registry_initialized(True)
        if corpus_registry_dir.is_dir():
            for corpus in corpus_registry_dir.glob("*/*"):
                corpora.add(corpus.name)
        g.cache.set_corpora(list(corpora))
        app.logger.debug(f"Corpora in cache: {len(g.cache.get_corpora())}")


def get_all() -> List[str]:
    """Get all existing corpus IDs."""
    return g.cache.get_corpora()


def add(corpus: str) -> None:
    """Add a corpus ID to the corpus registry."""
    corpora = set(g.cache.get_corpora())
    if corpus in corpora:
        raise exceptions.CorpusExists("Corpus ID already exists!")

    corpora.add(corpus)
    g.cache.set_corpora(list(corpora))
    app.logger.debug(f"Corpora in cache: {len(g.cache.get_corpora())}")

    corpus_registry_dir = Path(app.instance_path) / app.config.get("CORPUS_REGISTRY")
    subdir = corpus_registry_dir / corpus[len(app.config.get("RESOURCE_PREFIX"))]
    if not subdir.is_dir():
        subdir.mkdir(parents=True)
    (subdir / corpus).touch()


def remove(corpus: str) -> None:
    """Remove corpus from registry."""
    corpora = set(g.cache.get_corpora())

    corpora.remove(corpus)
    g.cache.set_corpora(list(corpora))

    corpus_registry_dir = Path(app.instance_path) / app.config.get("CORPUS_REGISTRY")
    cache_file = corpus_registry_dir / corpus[len(app.config.get("RESOURCE_PREFIX"))] / corpus
    cache_file.unlink(missing_ok=True)
