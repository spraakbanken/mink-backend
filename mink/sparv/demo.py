"""Functions for creating and managing demo resources."""

import hashlib
import re

import yaml

from mink.cache import jobs_cache
from mink.core import exceptions, registry, return_codes, utils
from mink.core.config import settings
from mink.core.info import Info
from mink.core.resource import Resource
from mink.core.user import User
from mink.sparv.config import sparv_settings
from mink.sparv.spec import CORPUS

DEMO_ID_PREFIX = f"{settings.RESOURCE_PREFIX}demo-"
DEMO_ID_PATTERN = re.compile(rf"{re.escape(DEMO_ID_PREFIX)}[0-9a-f]{{8}}\Z")
DEMO_DUMMY_ID = f"{DEMO_ID_PREFIX}dummy"
DEMO_RESOURCE_NAME = {"swe": "Demo", "eng": "Demo"}
DEMO_INPUT_FILENAME = "input.txt"
# TODO: Make this configurable through settings?
DEMO_DEFAULT_CONFIG = """\
import:
  importer: text_import:parse

export:
  annotations:
    - <sentence>
    - <token>:saldo.baseform2 as baseform
    - <token>:saldo.lemgram
    - <token>:wsd.sense
    - <token>:stanza.pos
    - <token>:stanza.msd
"""


def compute_demo_id(text: str, config: str) -> str:
    """Compute a deterministic demo id such as mink-demo-<hash>.

    Hash consists of: input text|config|salt, where salt is a manual versioning string to avoid collisions when changing
    the hashing scheme.
    """
    salt = "v1"  # Change this if the hashing scheme changes
    unique_string = f"{text}|{config}|{salt}"
    demo_hash = hashlib.sha256(unique_string.encode()).hexdigest()[:8]
    return f"{DEMO_ID_PREFIX}{demo_hash}"


def is_demo_id(resource_id: str) -> bool:
    """Check if a resource ID is a demo resource ID."""
    if resource_id == DEMO_DUMMY_ID:
        return True
    return DEMO_ID_PATTERN.fullmatch(resource_id) is not None


def sanitize_config(config: str) -> str:
    """Sanitize the corpus config for demo resources."""
    from mink.sparv.utils import standardize_config  # ruff: ignore[import-outside-top-level], avoids circular import

    sanitized_config, _ = standardize_config(config, DEMO_DUMMY_ID)
    # Sort yaml keys for consistent hashing
    sanitized_config_yaml = yaml.load(sanitized_config, Loader=yaml.FullLoader)
    sorted_config_yaml = dict(sorted(sanitized_config_yaml.items()))
    return yaml.dump(sorted_config_yaml, sort_keys=True, allow_unicode=True)


def insert_id_into_config(config: str, resource_id: str) -> str:
    """Insert the resource ID into the corpus config."""
    config_yaml = yaml.load(config, Loader=yaml.FullLoader)
    if not config_yaml.get("metadata"):
        config_yaml["metadata"] = {}
    config_yaml["metadata"]["id"] = resource_id
    return yaml.dump(config_yaml, sort_keys=False, allow_unicode=True)


def get_demo_resource(text: str, config: str) -> Info:
    """Find or create a demo resource for the given text and config.

    Args:
        text: The input text.
        config: The corpus config.

    Returns:
        The (existing or newly created) resource info item.
    """
    # Use default config if none was uploaded
    default_config_used = False
    if config is None or not config.strip():
        config = DEMO_DEFAULT_CONFIG.strip()
        default_config_used = True

    sanitized_config = sanitize_config(config)
    resource_id = compute_demo_id(text, sanitized_config)
    try:
        info_item = registry.get(resource_id)
    except exceptions.JobNotFoundError:
        info_item = create_demo_resource(resource_id, text, sanitized_config, default_config_used)

    return info_item


def create_demo_resource(resource_id: str, text: str, config: str, default_config_used: bool) -> Info:
    """Create a new demo resource for the given text and config.

    Args:
        resource_id: The resource ID.
        text: The input text.
        config: The corpus config.
        default_config_used: Whether the default config was used.
    """
    from mink.sparv import utils as sparv_utils  # ruff: ignore[import-outside-top-level], avoids circular import
    from mink.sparv.storage import storage  # ruff: ignore[import-outside-top-level], avoids circular import

    res = Resource(resource_id, type=CORPUS, demo_mode=True, last_accessed=utils.get_current_time())
    info_item = Info(resource_id, resource=res, owner=get_demo_user())
    info_item.create()

    # Create corpus dir
    storage.get_corpus_dir(resource_id, mkdir=True)

    # Save input text
    filename = DEMO_INPUT_FILENAME
    try:
        source_dir = storage.get_source_dir(resource_id, mkdir=True)
        source_file_path = source_dir / filename
        storage.write_file_contents(source_file_path, text.encode("UTF-8"), resource_id)
        res.set_source_files()
    except Exception as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_UPLOADING, info=str(e)) from e

    # Check if the config is compatible with the source file (check is necessary when user uploads a custom config)
    if not default_config_used:
        sparv_utils.require_compatible_config(config, info_item.resource.source_files)

    # Insert resource ID and save config
    new_yaml = insert_id_into_config(config, resource_id)
    try:
        # TODO: Do we really need a resource name?
        info_item.resource.set_resource_name(DEMO_RESOURCE_NAME)
        config_path = storage.get_config_file(resource_id)
        storage.write_file_contents(config_path, new_yaml.encode("UTF-8"), resource_id)
    except Exception as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.FAILED_UPLOADING, info=str(e)) from e

    return info_item


def get_demo_user() -> User:
    """Create a synthetic anonymous owner for demo resources."""
    return User(id="anonymous-demo", name="Demo User", email="", idp="", sub="")


def get_demo_resource_by_id(resource_id: str) -> Info:
    """Get the info item for a demo resource and update its last accessed timestamp, or raise an error if not found."""
    if not is_demo_id(resource_id):
        raise exceptions.MinkHTTPException(return_code=return_codes.RESOURCE_NOT_FOUND)

    try:
        info_item = registry.get(resource_id)
    except exceptions.JobNotFoundError as e:
        raise exceptions.MinkHTTPException(return_code=return_codes.RESOURCE_NOT_FOUND) from e

    if not info_item.resource.demo_mode or info_item.resource.type != CORPUS:
        raise exceptions.MinkHTTPException(return_code=return_codes.RESOURCE_NOT_FOUND)

    # Update last_accessed timestamp for the resource
    info_item.resource.touch()

    return info_item


def resource_is_expired(info_item: Info) -> bool:
    """Check if a demo resource has expired based on its last accessed timestamp."""
    lifetime_seconds = sparv_settings.SPARV_DEMO_RESOURCE_LIFETIME
    return utils.is_older_than(info_item.resource.last_accessed, lifetime_seconds)


def get_expired_demo_resources() -> list[Info]:
    """Get a list of expired demo resources (info items)."""
    expired_resources = []
    all_resources = jobs_cache.get_all_resources()
    for resource_id in all_resources:
        if is_demo_id(resource_id):
            try:
                info_item = registry.get(resource_id)
                is_expired = resource_is_expired(info_item)
                # Check if the resource is a demo corpus and has expired
                if info_item.resource.demo_mode and info_item.resource.type == CORPUS and is_expired:
                    expired_resources.append(info_item)
            except exceptions.JobNotFoundError:
                continue
    return expired_resources
