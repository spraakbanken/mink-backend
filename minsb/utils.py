"""General utility functions."""

import functools
import json
import os
import shlex
import zipfile
from pathlib import Path

import yaml
from flask import Response
from flask import current_app as app
from flask import g, request
from pymemcache.client.base import Client

from minsb import queue
from minsb.nextcloud import storage


def response(msg, err=False, **kwargs):
    """Create json error response."""
    res = {"status": "error" if err else "success", "message": msg}
    for key, value in kwargs.items():
        if value != "":
            res[key] = value
    return Response(json.dumps(res, ensure_ascii=False), mimetype="application/json")


def gatekeeper(function):
    """Make sure that only the protected user can access the decorated endpoint."""
    @functools.wraps(function)  # Copy original function's information, needed by Flask
    def decorator(*args, **kwargs):
        secret_key = request.args.get("secret_key") or request.form.get("secret_key")
        if secret_key != app.config.get("MIN_SB_SECRET_KEY"):
            return response("Failed to confirm secret key for protected route", err=True), 401
        return function(*args, **kwargs)
    return decorator


def create_zip(inpath, outpath):
    """Zip files in inpath into an archive at outpath."""
    zipf = zipfile.ZipFile(outpath, "w")
    if Path(inpath).is_file():
        zipf.write(inpath, Path(inpath).name)
    for root, _dirs, files in os.walk(inpath):
        for f in files:
            zipf.write(os.path.join(root, f), os.path.relpath(os.path.join(root, f), os.path.join(inpath, "..")))
    zipf.close()


def check_file_ext(filename, valid_extensions=None):
    """Shell escape filename and check if its extension is valid (return False if not)."""
    filename = Path(shlex.quote(filename))
    if valid_extensions:
        if filename.suffix not in valid_extensions:
            return False
    return filename


def check_file_compatible(filename, source_dir, oc):
    """Check if the file extension of filename is identical to the first file in source_dir."""
    existing_files = storage.list_contents(oc, str(source_dir))
    current_ext = Path(filename).suffix
    if not existing_files:
        return True, current_ext, None
    existing_ext = Path(existing_files[0].get("name")).suffix
    return current_ext == existing_ext, current_ext, existing_ext


def validate_xml(file_contents):
    """Check if inputfile is valid XML."""
    import xml.etree.ElementTree as etree
    try:
        etree.fromstring(file_contents)
        return True
    except etree.ParseError:
        return False


def config_compatible(config, source_file):
    """Check if the importer module in the corpus config is compatible with the source files."""
    file_ext = Path(source_file.get("name")).suffix
    config_yaml = yaml.load(config, Loader=yaml.FullLoader)
    current_importer = config_yaml.get("import", {}).get("importer", "").split(":")[0] or None
    importer_dict = app.config.get("SPARV_IMPORTER_MODULES", {})

    # If no importer is specified xml is default
    if current_importer is None and file_ext == ".xml":
        return True, None

    expected_importer = importer_dict.get(file_ext)
    if current_importer == expected_importer:
        return True, None
    return False, response("The importer in your config file is not compatible with your source files",
                            err=True, current_importer=current_importer, expected_importer=expected_importer)


def set_corpus_id(config, corpus_id):
    """Set the correct corpus_id in a corpus config."""
    config_yaml = yaml.load(config, Loader=yaml.FullLoader)

    # If corpus_id already has correct value, do nothing
    if config_yaml.get("metadata", {}).get("id") == corpus_id:
        return config

    if not config_yaml.get("metadata"):
        config_yaml["metadata"] = {}
    config_yaml["metadata"]["id"] = corpus_id
    return yaml.dump(config_yaml, sort_keys=False, allow_unicode=True)
