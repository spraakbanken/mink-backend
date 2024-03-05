"""Class defining resource info objects."""

import json
from pathlib import Path
from typing import Optional

from flask import current_app as app
from flask import g

from mink.core import exceptions, registry
from mink.core.jobs import Job
from mink.core.resource import Resource
from mink.core.user import User


class Info:
    """An info item holding all information about a resource, organized into subclasses."""

    def __init__(
            self,
            id: str,
            resource: Optional[Resource] = None,
            owner: Optional[User] = None,
            job: Optional[Job] = None
        ):
        """Create an info instance."""
        self.id = id
        self.resource = resource or Resource(id=self.id)
        self.owner = owner or User()
        self.job = job or Job(id=self.id, owner=self.owner)

        # Set parent in subclasses
        self.resource.set_parent(self)
        self.owner.set_parent(self)
        self.job.set_parent(self)

    def __str__(self):
        return str(self.serialize())

    def serialize(self):
        """Convert class data into dict."""
        return {
            "resource": self.resource,
            "owner": self.owner,
            "job": self.job
        }

    def to_dict(self):
        """Recursively transform class data into dict (also transforming the data of its children)."""
        return json.loads(json.dumps(self, default=lambda x: x.serialize()))

    def create(self):
        """Create new info object in cache and filesystem."""
        # Save to cache
        all_resources = g.cache.get_all_resources()
        if self.id in all_resources:
            raise exceptions.CorpusExists("Resource ID already exists!")
        all_resources.append(self.id)
        g.cache.set_all_resources(all_resources)
        self.update()

    def update(self):
        """Write an info item to the cache and filesystem."""
        dump = json.dumps(self, default=lambda x: x.serialize())

        g.cache.set_job(self.id, dump)

        # Save backup to file system queue
        registry_dir = Path(app.instance_path) / Path(app.config.get("REGISTRY_DIR"))
        subdir = registry_dir / self.id[len(app.config.get("RESOURCE_PREFIX"))]
        subdir.mkdir(parents=True, exist_ok=True)
        backup_file = subdir / Path(self.id)
        with backup_file.open("w") as f:
            f.write(dump)

    def remove(self, abort_job=False):
        """Remove an info item from the cache and file system."""
        if self.job.status.is_running():
            if abort_job:
                try:
                    self.job.abort_sparv()
                except (exceptions.ProcessNotRunning, exceptions.ProcessNotFound):
                    pass
                except Exception as e:
                    raise e
            else:
                raise exceptions.JobError("Job cannot be removed due to a running Sparv process!")

        # Remove from queue
        registry.pop_from_queue(self.job)

        # Remove from cache
        try:
            g.cache.remove_job(self.id)
            all_resources = g.cache.get_all_resources()
            if self.id in all_resources:
                all_resources.pop(all_resources.index(self.id))
                g.cache.set_all_resources(all_resources)
        except Exception as e:
            app.logger.error("Failed to delete job ID from cache client: %s", e)

        # Remove backup from file system
        registry_dir = Path(app.instance_path) / Path(app.config.get("REGISTRY_DIR"))
        subdir = registry_dir / self.id[len(app.config.get("RESOURCE_PREFIX"))]
        filename = subdir / Path(self.id)
        filename.unlink(missing_ok=True)


def load_from_str(jsonstr):
    """Load an Info instance from a json string."""
    json_info = json.loads(jsonstr)
    resource_id = json_info["resource"]["id"]
    return Info(resource_id,
                resource=Resource(**json_info.get("resource")),
                owner=User(**json_info.get("owner")),
                job=Job(resource_id, **json_info.get("job"))
                )
