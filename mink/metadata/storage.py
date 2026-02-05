"""Metadata storage backend and singleton instance."""

from pathlib import Path

from mink.core import storage_base
from mink.core.config import settings


class MetadataStorage(storage_base.BaseStorage):
    """Storage backend for metadata resources."""

    user = settings.METADATA_USER
    host = settings.METADATA_HOST

    supports_upload = False
    supports_download_dir = False
    supports_list = False

    def is_valid_path(self, path: Path, resource_id: str) -> bool:
        """Check if path points to a permitted location for the resource."""
        return self.get_resource_dir(resource_id).resolve() in {*list(path.resolve().parents), path.resolve()}

    # ------------------------------------------------------------------------------
    # Path getters
    # ------------------------------------------------------------------------------

    @staticmethod
    def get_resources_dir() -> Path:
        """Get dir for metadata resources."""
        return Path(settings.METADATA_DIR)

    def get_resource_dir(self, resource_id: str, mkdir: bool = False) -> Path:
        """Get dir for given resource."""
        resources_dir = self.get_resources_dir()
        resdir = resources_dir / resource_id[len(settings.RESOURCE_PREFIX)] / resource_id
        if mkdir:
            self.make_dir(resdir)
        return resdir

    def get_source_dir(self, resource_id: str, mkdir: bool = False) -> Path:
        """Get source dir for given resource."""
        resdir = self.get_resource_dir(resource_id)
        source_dir = resdir / settings.METADATA_SOURCE_DIR
        if mkdir:
            self.make_dir(source_dir)
        return source_dir

    def get_yaml_file(self, resource_id: str) -> Path:
        """Get path to metadata yaml file."""
        resdir = self.get_resource_dir(resource_id)
        return resdir / (resource_id + ".yaml")


storage = MetadataStorage()
