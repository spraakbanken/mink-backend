"""General utility functions."""

import functools
import gzip
import json
import subprocess
import zipfile
from pathlib import Path
from typing import Any, Callable, Optional

import yaml
from flask import Response, g, request
from flask import current_app as app

from mink.sparv import storage


def response(msg: str, err: bool = False, **kwargs: dict[str, Any]) -> Response:
    """Create json error response.

    Args:
        msg: The error message.
        err: Whether the response is an error.
        **kwargs: Additional key-value pairs to include in the response.

    Returns:
        A Flask Response object.
    """
    # Log error
    if err:
        args = "\n".join(f"{k}: {v}" for k, v in kwargs.items() if v != "")  # noqa: PLC1901
        args = "\n" + args if args else ""
        app.logger.error("%s%s", msg, args)

    res = {"status": "error" if err else "success", "message": msg}
    res.update({k: v for k, v in kwargs.items() if v != ""})  # noqa: PLC1901

    return Response(json.dumps(res, ensure_ascii=False), mimetype="application/json")


def gatekeeper(function: Callable) -> Callable:
    """Make sure that only the protected user can access the decorated endpoint.

    Args:
        function: The function to decorate.

    Returns:
        The decorated function.
    """

    @functools.wraps(function)  # Copy original function's information, needed by Flask
    def decorator(*args: tuple, **kwargs: dict) -> tuple[Response, Optional[int]] | Callable:
        secret_key = request.args.get("secret_key") or request.form.get("secret_key")
        if secret_key != app.config.get("MINK_SECRET_KEY"):
            return response(
                "Failed to confirm secret key for protected route", err=True, return_code="failed_confirming_secret_key"
            ), 401
        return function(*args, **kwargs)

    return decorator


def ssh_run(command: str, ssh_input: Optional[bytes] = None) -> subprocess.CompletedProcess:
    """Execute 'command' on server and return process.

    Args:
        command: The command to execute.
        ssh_input: The input to pass to the command.

    Returns:
        The completed process.
    """
    user = app.config.get("SPARV_USER")
    host = app.config.get("SPARV_HOST")
    return subprocess.run(
        ["ssh", "-i", app.config.get("SSH_KEY"), f"{user}@{host}", command],
        capture_output=True,
        input=ssh_input,
        check=False,
    )


def uncompress_gzip(inpath: Path, outpath: Optional[Path] = None) -> None:
    """Uncompress file with gzip and save to outpath (or inpath if no outpath is given).

    Args:
        inpath: The path to the input file.
        outpath: The path to the output file.
    """
    with gzip.open(inpath, "rb") as z:
        data = z.read()
        if outpath is None:
            outpath = inpath
        with Path(outpath).open("wb") as f:
            f.write(data)


def create_zip(inpath: Path, outpath: Path, zip_rootdir: Optional[str] = None) -> None:
    """Zip files in inpath into an archive at outpath.

    Args:
        inpath: The path to the input files.
        outpath: The path to the output zip file.
        zip_rootdir: Name that the root folder inside the zip file should be renamed to.
    """
    zipf = zipfile.ZipFile(outpath, "w")
    if Path(inpath).is_file():
        zipf.write(inpath, Path(inpath).name)
    else:
        for filepath in Path(inpath).rglob("*"):
            zippath = filepath.relative_to(Path(inpath).parent)
            if zip_rootdir:
                zippath = Path(zip_rootdir) / Path(*zippath.parts[1:])
            zipf.write(filepath, zippath)
    zipf.close()


def check_file_ext(filename: str, valid_extensions: Optional[list[str]] = None) -> bool:
    """Check if file extension is valid.

    Args:
        filename: The filename to check.
        valid_extensions: List of valid extensions.

    Returns:
        True if the file extension is valid, False otherwise.
    """
    filename = Path(filename)
    return not (valid_extensions and not any(i.lower() == filename.suffix.lower() for i in valid_extensions))


def check_file_compatible(filename: str, source_dir: Path) -> tuple[bool, str, Optional[str]]:
    """Check if the file extension of filename is identical to the first file in source_dir.

    Args:
        filename: The filename to check.
        source_dir: The source directory.

    Returns:
        A tuple containing a boolean indicating compatibility, the current extension, and the existing extension.
    """
    existing_files = storage.list_contents(str(source_dir))
    current_ext = Path(filename).suffix
    if not existing_files:
        return True, current_ext, None
    existing_ext = Path(existing_files[0].get("name")).suffix
    return current_ext == existing_ext, current_ext, existing_ext


def check_size_ok(source_dir: Path, incoming_size: int) -> bool:
    """Check if the size of the incoming files exceeds the max corpus size.

    Args:
        source_dir: The source directory.
        incoming_size: The size of the incoming files.

    Returns:
        True if the size is within the limit, False otherwise.
    """
    if app.config.get("MAX_CORPUS_LENGTH") is not None:
        current_size = storage.get_size(str(source_dir))
        total_size = current_size + incoming_size
        if total_size > app.config.get("MAX_CORPUS_LENGTH"):
            return False
    return True


def config_compatible(config: str, source_file: dict) -> tuple[bool, Optional[Response]]:
    """Check if the importer module in the corpus config is compatible with the source files.

    Args:
        config: The corpus config.
        source_file: The source file.

    Returns:
        A tuple containing a boolean indicating compatibility and an optional response.
    """
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
    return False, response(
        "The importer in your config file is not compatible with your source files",
        err=True,
        current_importer=current_importer,
        expected_importer=expected_importer,
        return_code="incompatible_config_importer",
    )


def standardize_config(config: str, corpus_id: str) -> tuple[str, str]:
    """Set the correct corpus ID and remove the compression setting in the corpus config.

    Args:
        config: The corpus config.
        corpus_id: The corpus ID.

    Returns:
        A tuple containing the standardized config and the corpus name.
    """
    config_yaml = yaml.load(config, Loader=yaml.FullLoader)

    # Set correct corpus ID
    if config_yaml.get("metadata", {}).get("id") != corpus_id:
        if not config_yaml.get("metadata"):
            config_yaml["metadata"] = {}
        config_yaml["metadata"]["id"] = corpus_id

    # Get corpus name
    name = config_yaml.get("metadata", {}).get("name", {})

    # Remove the compression setting in order to use the standard one given by the default config
    if config_yaml.get("sparv", {}).get("compression") is not None:
        config_yaml["sparv"].pop("compression")
        # Remove entire Sparv section if empty
        if not config_yaml.get("sparv", {}):
            config_yaml.pop("sparv")

    # Remove settings that a Mink user is not allowed to modify
    config_yaml.pop("cwb", None)
    config_yaml.pop("korp", None)
    config_yaml.pop("sbx_strix", None)
    # Remove all install and uninstall targets (this is handled in the installation step instead)
    config_yaml.pop("install", None)
    config_yaml.pop("uninstall", None)

    # Add Korp settings
    config_yaml["korp"] = {
        "protected": True,
        "context": ["1 sentence", "5 sentence"],
        "within": ["sentence", "5 sentence"],
    }
    # Make Strix corpora appear in correct mode
    config_yaml["sbx_strix"] = {"modes": [{"name": "mink"}]}
    # Add '<text>:misc.id as _id' to annotations for Strix' sake
    if "export" in config_yaml and "annotations" in config_yaml["export"]:  # noqa: SIM102
        if "<text>:misc.id as _id" not in config_yaml["export"]["annotations"]:
            config_yaml["export"]["annotations"].append("<text>:misc.id as _id")

    return yaml.dump(config_yaml, sort_keys=False, allow_unicode=True), name


def standardize_metadata_yaml(metadata_yaml: str) -> tuple[str, str]:
    """Get resource name from metadata yaml and remove comments etc.

    Args:
        metadata_yaml: The metadata yaml.

    Returns:
        A tuple containing the standardized yaml and the resource name.
    """
    yaml_contents = yaml.load(metadata_yaml, Loader=yaml.FullLoader)

    # Get resource name
    name = yaml_contents.get("name", {})

    return yaml.dump(yaml_contents, sort_keys=False, allow_unicode=True), name


# ------------------------------------------------------------------------------
# Get local paths (mostly used for download)
# ------------------------------------------------------------------------------

def get_resources_dir(mkdir: bool = False) -> Path:
    """Get user specific dir for corpora."""
    resources_dir = Path(app.instance_path) / Path(app.config.get("TMP_DIR")) / g.request_id
    if mkdir:
        resources_dir.mkdir(parents=True, exist_ok=True)
    return resources_dir


def get_resource_dir(resource_id: str, mkdir: bool = False) -> Path:
    """Get dir for given resource."""
    resources_dir = get_resources_dir(mkdir=mkdir)
    resdir = resources_dir / Path(resource_id)
    if mkdir:
        resdir.mkdir(parents=True, exist_ok=True)
    return resdir


def get_export_dir(corpus_id: str, mkdir: bool = False) -> Path:
    """Get export dir for given resource."""
    resdir = get_resource_dir(corpus_id, mkdir=mkdir)
    export_dir = resdir / Path(app.config.get("SPARV_EXPORT_DIR"))
    if mkdir:
        export_dir.mkdir(parents=True, exist_ok=True)
    return export_dir


def get_work_dir(corpus_id: str, mkdir: bool = False) -> Path:
    """Get sparv workdir for given corpus."""
    resdir = get_resource_dir(corpus_id, mkdir=mkdir)
    work_dir = resdir / Path(app.config.get("SPARV_WORK_DIR"))
    if mkdir:
        work_dir.mkdir(parents=True, exist_ok=True)
    return work_dir


def get_source_dir(corpus_id: str, mkdir: bool = False) -> Path:
    """Get source dir for given corpus."""
    resdir = get_resource_dir(corpus_id, mkdir=mkdir)
    source_dir = resdir / Path(app.config.get("SPARV_SOURCE_DIR"))
    if mkdir:
        source_dir.mkdir(parents=True, exist_ok=True)
    return source_dir


def get_config_file(corpus_id: str) -> Path:
    """Get path to corpus config file."""
    resdir = get_resource_dir(corpus_id)
    return resdir / Path(app.config.get("SPARV_CORPUS_CONFIG"))


def get_metadata_yaml_file(resource_id: str) -> Path:
    """Get path to local metadata yaml file."""
    resdir = get_resource_dir(resource_id)
    return resdir / (resource_id + ".yaml")
