"""Karp storage backend and singleton instance."""

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from dateutil.parser import isoparse

from mink.core import exceptions
from mink.core.config import settings
from mink.core.resource_specs import get_spec
from mink.core.storage_base import BaseStorage
from mink.karp.config import karp_settings
from mink.karp.spec import LEXICON

if TYPE_CHECKING:
    from mink.core.info import Info


class KarpStorage(BaseStorage):
    """Storage backend for Karp resources."""

    local: ClassVar[bool] = True  # Whether the storage is local (i.e. on the same server as Mink)
    user = karp_settings.KARP_USER
    host = karp_settings.KARP_HOST

    def is_valid_path(self, path: Path, resource_id: str) -> bool:
        """Check if path points to a permitted location for the resource."""
        return self.get_resource_dir(resource_id).resolve() in {*list(path.resolve().parents), path.resolve()}

    @staticmethod
    def relative_path(filepath: Path) -> str:
        """Return a path string relative to the lexicon directory (for API responses)."""
        return "/".join(filepath.parts[4:])

    def get_file_changes(self, resource_id: str, info_item: "Info") -> tuple[bool, bool]:
        """Get changes for source file and config file.

        Args:
            resource_id: The resource ID.
            info_item: The resource info item.

        Returns:
            A tuple containing two booleans:
            - Whether the source file has changed.
            - Whether the config file has changed.

        Raises:
            exceptions.JobNotFoundError: If the job has not started.
        """
        source_changed = config_changed = False

        if not info_item.job.started:
            raise exceptions.JobNotFoundError(resource_id)
        started = isoparse(info_item.job.started)

        # Compare source files modification times to the time stamp of the last job started
        source_file = info_item.resource.source_files[0]
        if isoparse(source_file.get("last_modified")) > started:
            source_changed = True

        # Compare the config file modification time to the time stamp of the last job started
        config_file_obj = self.get_file_info(self.get_config_file(resource_id))
        if isoparse(config_file_obj["last_modified"]) > started:
            config_changed = True

        return source_changed, config_changed

    # ------------------------------------------------------------------------------
    # Path getters
    # ------------------------------------------------------------------------------

    def get_resource_dir(self, resource_id: str, mkdir: bool = False) -> Path:
        """Get dir for given lexicon."""
        resource_dir = (
            Path(karp_settings.KARP_DATA_DIR) / resource_id[len(settings.RESOURCE_PREFIX)] / resource_id
        )
        if mkdir:
            self.make_dir(resource_dir)
        return resource_dir

    def get_output_dir(self, resource_id: str, mkdir: bool = False) -> Path:
        """Get output dir for given corpus."""
        output_dir = self.get_resource_dir(resource_id) / karp_settings.KARP_OUTPUT_DIR
        if mkdir:
            self.make_dir(output_dir)
        return output_dir

    def get_source_dir(self, resource_id: str, mkdir: bool = False) -> Path:
        """Get source dir for given corpus."""
        source_dir = self.get_resource_dir(resource_id) / karp_settings.KARP_SOURCE_DIR
        if mkdir:
            self.make_dir(source_dir)
        return source_dir

    def get_config_file(self, resource_id: str) -> Path:
        """Get path to corpus config file."""
        config_filename = get_spec(LEXICON).config_filename
        return self.get_resource_dir(resource_id) / config_filename

    # ------------------------------------------------------------------------------
    # Local path getters (on Mink server, used for file downloads)
    # ------------------------------------------------------------------------------

    def get_local_output_dir(self, resource_id: str, mkdir: bool = False) -> Path:
        """Get output dir for given resource."""
        resdir = self.get_local_resource_dir(resource_id, mkdir=mkdir)
        output_dir = resdir / karp_settings.KARP_OUTPUT_DIR
        if mkdir:
            output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def get_local_source_dir(self, resource_id: str, mkdir: bool = False) -> Path:
        """Get source dir for given corpus."""
        resdir = self.get_local_resource_dir(resource_id, mkdir=mkdir)
        source_dir = resdir / karp_settings.KARP_SOURCE_DIR
        if mkdir:
            source_dir.mkdir(parents=True, exist_ok=True)
        return source_dir

    def get_local_config_file(self, resource_id: str) -> Path:
        """Get path to corpus config file."""
        resdir = self.get_local_resource_dir(resource_id)
        return resdir / karp_settings.KARP_CONFIG


storage = KarpStorage()
