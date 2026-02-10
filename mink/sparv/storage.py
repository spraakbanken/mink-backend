"""Sparv storage backend and singleton instance."""

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from dateutil.parser import isoparse

from mink.core import exceptions
from mink.core.config import settings
from mink.core.resource import ResourceType
from mink.core.resource_specs import get_spec
from mink.core.storage_base import BaseStorage
from mink.sparv.config import sparv_settings

if TYPE_CHECKING:
    from mink.core.info import Info


class SparvStorage(BaseStorage):
    """Storage backend for Sparv resources."""

    local: ClassVar[bool] = True  # Whether the storage is local (i.e. on the same server as Mink)
    user = sparv_settings.SPARV_USER
    host = sparv_settings.SPARV_HOST
    always_exclude: ClassVar[list[str]] = [".snakemake"]  # Paths to always exclude when listing contents

    def is_valid_path(self, path: Path, resource_id: str) -> bool:
        """Check if path points to a permitted location for the resource."""
        return self.get_corpus_dir(resource_id).resolve() in {*list(path.resolve().parents), path.resolve()}

    @staticmethod
    def relative_path(filepath: Path) -> str:
        """Return a path string relative to the corpus directory (for API responses)."""
        return "/".join(filepath.parts[4:])

    def get_file_changes(self, resource_id: str, info_item: "Info") -> tuple[bool, bool, bool]:
        """Get changes for source files and config file.

        Args:
            resource_id: The resource ID.
            info_item: The resource info item.

        Returns:
            A tuple containing three booleans:
            - Whether source files have changed.
            - Whether source files have been deleted.
            - Whether the config file has changed.

        Raises:
            exceptions.JobNotFoundError: If the job has not started.
        """
        source_changed = sources_deleted = config_changed = False

        if not info_item.job.started:
            raise exceptions.JobNotFoundError(resource_id)
        started = isoparse(info_item.job.started)

        # Compare source files modification times to the time stamp of the last job started
        source_files = info_item.resource.source_files
        for sf in source_files:
            if isoparse(sf.get("last_modified")) > started:
                source_changed = True
                break

        # Compare the 'sources_deleted' timestamp to the time stamp of the last job started
        if info_item.resource.sources_deleted and isoparse(info_item.resource.sources_deleted) > started:
            sources_deleted = True

        # Compare the config file modification time to the time stamp of the last job started
        config_file_obj = self.get_file_info(self.get_config_file(resource_id))
        if isoparse(config_file_obj["last_modified"]) > started:
            config_changed = True

        return source_changed, sources_deleted, config_changed

    # ------------------------------------------------------------------------------
    # Path getters
    # ------------------------------------------------------------------------------

    def get_corpus_dir(self, resource_id: str, mkdir: bool = False, default_dir: bool = False) -> Path:
        """Get dir for given corpus."""
        if default_dir:
            corpus_dir = Path(sparv_settings.SPARV_DEFAULT_CORPORA_DIR) / resource_id
        else:
            corpus_dir = (
                Path(sparv_settings.SPARV_CORPORA_DIR) / resource_id[len(settings.RESOURCE_PREFIX)] / resource_id
            )
        if mkdir:
            self.make_dir(corpus_dir)
        return corpus_dir

    def get_export_dir(self, resource_id: str, mkdir: bool = False) -> Path:
        """Get export dir for given corpus."""
        export_dir = self.get_corpus_dir(resource_id) / sparv_settings.SPARV_EXPORT_DIR
        if mkdir:
            self.make_dir(export_dir)
        return export_dir

    def get_work_dir(self, resource_id: str, mkdir: bool = False) -> Path:
        """Get sparv workdir for given corpus."""
        work_dir = self.get_corpus_dir(resource_id) / sparv_settings.SPARV_WORK_DIR
        if mkdir:
            self.make_dir(work_dir)
        return work_dir

    def get_source_dir(self, resource_id: str, mkdir: bool = False) -> Path:
        """Get source dir for given corpus."""
        source_dir = self.get_corpus_dir(resource_id) / sparv_settings.SPARV_SOURCE_DIR
        if mkdir:
            self.make_dir(source_dir)
        return source_dir

    def get_config_file(self, resource_id: str) -> Path:
        """Get path to corpus config file."""
        config_filename = get_spec(ResourceType.corpus).config_filename
        return self.get_corpus_dir(resource_id) / config_filename

    # ------------------------------------------------------------------------------
    # Local path getters (on Mink server, used for file downloads)
    # ------------------------------------------------------------------------------

    def get_local_export_dir(self, resource_id: str, mkdir: bool = False) -> Path:
        """Get export dir for given resource."""
        resdir = self.get_local_resource_dir(resource_id, mkdir=mkdir)
        export_dir = resdir / sparv_settings.SPARV_EXPORT_DIR
        if mkdir:
            export_dir.mkdir(parents=True, exist_ok=True)
        return export_dir

    def get_local_work_dir(self, resource_id: str, mkdir: bool = False) -> Path:
        """Get sparv workdir for given corpus."""
        resdir = self.get_local_resource_dir(resource_id, mkdir=mkdir)
        work_dir = resdir / sparv_settings.SPARV_WORK_DIR
        if mkdir:
            work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir

    def get_local_source_dir(self, resource_id: str, mkdir: bool = False) -> Path:
        """Get source dir for given corpus."""
        resdir = self.get_local_resource_dir(resource_id, mkdir=mkdir)
        source_dir = resdir / sparv_settings.SPARV_SOURCE_DIR
        if mkdir:
            source_dir.mkdir(parents=True, exist_ok=True)
        return source_dir

    def get_local_config_file(self, resource_id: str) -> Path:
        """Get path to corpus config file."""
        resdir = self.get_local_resource_dir(resource_id)
        return resdir / sparv_settings.SPARV_CORPUS_CONFIG


storage = SparvStorage()
