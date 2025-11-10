"""Class defining resource info objects."""

import json
from pathlib import Path

from mink.cache import cache_utils
from mink.core import exceptions, registry
from mink.core.config import settings
from mink.core.jobs import Job
from mink.core.logging import logger
from mink.core.resource import Resource
from mink.core.user import User


class Info:
    """An info item holding all information about a resource, organized into subclasses."""

    def __init__(
        self,
        id: str,  # noqa: A002
        owner: User,
        resource: Resource | None = None,
        job: Job | None = None,
    ) -> None:
        """Create an info instance.

        Args:
            id: The ID of the resource.
            owner: The owner of the resource.
            resource: The resource associated with the info.
            job: The job associated with the resource.
        """
        self.id = id
        self.owner = owner
        self.resource = resource or Resource(id=self.id)
        self.job = job or Job(id=self.id, owner=self.owner)

        # Set parent in subclasses
        self.owner.set_parent(self)
        self.resource.set_parent(self)
        self.job.set_parent(self)

    def __str__(self) -> str:
        """Convert the info instance to a string.

        Returns:
            A string representation of the info instance.
        """
        return str(self.serialize())

    def serialize(self) -> dict:
        """Convert class data into dict.

        Returns:
            A dictionary representation of the info instance.
        """
        return {"resource": self.resource, "owner": self.owner, "job": self.job}

    def to_dict(self) -> dict:
        """Recursively transform class data into dict (also transforming the data of its children).

        Returns:
            A dictionary representation of the info instance and its children.
        """
        return json.loads(json.dumps(self, default=lambda x: x.serialize()))

    def create(self) -> None:
        """Create new info object in cache and filesystem.

        Raises:
            exceptions.CorpusExistsError: If the resource ID already exists.
        """
        # Save to cache
        all_resources = cache_utils.get_all_resources()
        if self.id in all_resources:
            raise exceptions.CorpusExistsError(self.id)
        all_resources.append(self.id)
        cache_utils.set_all_resources(all_resources)
        self.update()

    def update(self) -> None:
        """Write an info item to the cache and filesystem."""
        dump = json.dumps(self, default=lambda x: x.serialize())

        cache_utils.set_job(self.id, dump)

        # Save backup to file system queue
        registry_dir = Path(settings.INSTANCE_PATH) / settings.REGISTRY_DIR
        subdir = registry_dir / self.id[len(settings.RESOURCE_PREFIX)]
        subdir.mkdir(parents=True, exist_ok=True)
        backup_file = subdir / self.id
        with backup_file.open("w") as f:
            f.write(dump)

    def remove(self, abort_job: bool = False) -> None:
        """Remove an info item from the cache and file system.

        Args:
            abort_job: Whether to abort the job if it is running.

        Raises:
            exceptions.ProcessStillRunningError: If the job cannot be removed due to a running Sparv process.
        """
        if self.job.status.is_running():
            if abort_job:
                try:
                    self.job.abort_sparv()
                except (exceptions.ProcessNotRunningError, exceptions.ProcessNotFoundError):
                    pass
                except Exception:
                    raise
            else:
                raise exceptions.ProcessStillRunningError

        # Remove from queue
        registry.pop_from_queue(self.job)

        # Remove from cache
        try:
            cache_utils.remove_job(self.id)
            all_resources = cache_utils.get_all_resources()
            if self.id in all_resources:
                all_resources.pop(all_resources.index(self.id))
                cache_utils.set_all_resources(all_resources)
        except Exception as e:
            logger.error("Failed to delete job ID from cache client: %s", e)

        # Remove backup from file system
        registry_dir = Path(settings.INSTANCE_PATH) / settings.REGISTRY_DIR
        subdir = registry_dir / self.id[len(settings.RESOURCE_PREFIX)]
        filename = subdir / self.id
        filename.unlink(missing_ok=True)


def load_from_str(jsonstr: str) -> Info:
    """Load an Info instance from a json string.

    Args:
        jsonstr: The JSON string to load the info from.

    Returns:
        An Info instance loaded from the JSON string.
    """
    json_info = json.loads(jsonstr)
    resource_id = json_info["resource"]["id"]
    return Info(
        resource_id,
        resource=Resource(**json_info.get("resource")),
        owner=User(**json_info.get("owner")),
        job=Job(resource_id, **json_info.get("job")),
    )
