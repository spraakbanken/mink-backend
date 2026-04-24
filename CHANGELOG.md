# Changelog

All notable API changes will be documented in this file. The format is based on [Keep a
Changelog](https://keepachangelog.com/en/1.0.0/).

## [unreleased]

### Changed

- The config setting "METADATA_ORG_PREFIXES" has been renamed to "ORGANIZATION_PREFIXES".

### Added

- Added a new resource type: lexicons. This includes routes for creating, listing, uploading and downloading lexicons.
- Added a new route `/metadata/list` for listing all metadata resources.
- Added a new internal route `/queue/health` which exposes monitorable queue statistics and returns a warning when
  queued or running jobs exceed the configured threshold.
- Added a new route `/user/info/get` for retrieving information about the currently authenticated user.
- Added regular queue health polling in `queue_manager.py`, which calls `/queue/health`, logs degraded queue state and
  optionally notifies via a Slack webhook.
- Added a new field `queued` to the `/resource/status` responses which indicates when a job was queued.
- Added a 'warnings' field to the response from `/corpus/korp/uninstall/<id>` and `/corpus/strix/uninstall/<id>` which
  contains any warnings that occurred during the export process.
- Added checks for unused config variables in the .env file upon app start to help identify typos or misconfigurations.
- Added fields `idp` and `sub` to the User class and model (used in the responses from `/resource/status/list` and
  `/resource/status/list`).
- Added a query param `custom_config` to the `/<resource-type>/config/upload` routes which allows marking a resource as
  having a custom config. This is used for tracking whether the user has modified the config from the default generated
  by the frontend.

### Removed

- The deprecated query parameter `corpus_id` has been removed from all routes. Use the path parameter `resource_id`
  instead.
- The deprecated route `/download-source-text` has been removed. The source text can be downloaded via the plain text
  export from Sparv instead.
- The deprecated routes with the old format where the resource ID was provided as a query parameter (e.g.
  `/upload-sources?resource_id=...`,) have been removed. Use the new routes with the format
  `/<resource-type>/<sub-resource>/<action>/<resource-id>` instead (e.g. `/corpora/sources/upload/<resource_id>`).

### Fixed

- Fixed bug: "Try it out" button in Swagger UI did not work for routes requiring a resource ID as a path parameter.
- Fixed bug: When in admin mode resources were not filtered by type.
- Fixed bug: `installed_*` flags were set to True before the installation process was completed.

### Deprecated

- The route `/corpus/korp/list` is deprecated and will be removed in a future release.
- The route `/admin-mode-on` is deprecated and will be removed in a future release. Use `/user/admin-mode/activate`
  instead.
- The route `/admin-mode-off` is deprecated and will be removed in a future release. Use `/user/admin-mode/deactivate`
  instead.
- The route `/admin-mode-status` is deprecated and will be removed in a future release. Use `/user/info/get` (field
  `user.admin_mode`) instead.

## [2.2.0] - 2026-04-02

### Changed

- `/info` response schema has changed: the fields `importer_modules` and `recommended_file_size` have been moved under a
  new `resource_info` field, which is a dictionary keyed by resource type.
- Some response models and status codes were updated to be more consistent and accurate.
- `/resource-info` response schema has changed: each resource now has a `job_status` field indicating the status of the
  current job for that resource, replacing the previous `return_code` field. The possible values for `job_status` are
  the ones indicated by `status_codes` in the `/info`response.
- `/list-corpora` and `/list-korp-corpora` response schema has changed: the list of corpora is now returned under the
  `resources` field instead of `corpora` to be more consistent with other resource types.
- The Sparv output (nohupfile) and the Sparv run script are no longer removed when calling `/clear-annotations` which
  allows for better debugging.
- Core resource handling is now spec-driven: resource packages (like `sparv` and `metadata`) register their behavior via
  the `SPEC_MODULES` setting, and module settings are loaded from `CONFIG_MODULES` (no longer hard-coded in core).
- Introduced a base job class (`BaseJob`) with resource-specific job subclasses. Job status/process handling is no
  longer Sparv-specific in core and process lists are provided by resource specs.
- Storage backends were reorganized under a shared base class, with resource-specific storage implementations per module.
- Common route helpers for resource creation/removal and file upload were extracted into `mink/core/route_helpers.py` to
  reduce code duplication between modules.
- Cache utilities were split by domain (jobs/auth/schema) and cache keys are now namespaced.
- Router modules from resource packages are now loaded dynamically based on the resource spec instead of being
  hard-coded in core routes.
- The config setting "SPARV_WORKERS" has been renamed to "MAX_WORKERS" since it is now used by all resource types
  instead of just Sparv.
- The documentation was updated to reflect the new project structure.
- SB Auth resource types are now defined in the config and mappen in the specs. The login module is able to return
  resources of the specified type only, avoiding accidental execution of actions on the wrong resource type.

### Added

- Added new route `/resource/list` for listing all resources regardless of type.
- Added a new script `config_helper.py` for validating and displaying config values from all modules and the .env file.
- Added a new route `/return-codes` which lists all possible return codes and their meanings, to make it easier for
  users to understand the API responses.
- Caching of Sparv data computed in `/sparv-exports` and `/sparv-languages` to speed up subsequent calls. The cache can
  be bypassed by setting the `update-cache` query parameter to true.

### Removed

- The `/api-spec` route has been removed. Use `/openapi.json` instead.
- The `/api-docs` route has been removed. Use `/redoc` instead.
- The `/developers-guide` route has been removed. Use `/docs` instead.

### Fixed

- When creating a new resource, the correct resource type is now passed to the authentication system.
- Fixed some outdated URLs in the documentation.
- Fixed issue with bad path patterns occurring in the response from `/sparv-exports`.

### Deprecated

- Most API routes have been renamed according to the pattern `<resource-type>/<sub-resource>/<action>/<resource-id>`
  instead of `/<action>-<resource-type>?resource-id=<resource-id>` (e.g. `/upload-sources` is now
  `/corpora/sources/upload`). Check the API documentation for the updated route names. The old routes are still
  available but they are deprecated and will be removed in a future release.
- The `/download-source-text` route is deprecated and will be removed in a future release. The plain text export from
  Sparv should be used instead.

## [2.1.1] - 2026-02-04

### Fixed

- Fixed bug: Matomo tracking did not work because of an incorrect dependency version.
- Fixed bug: `/advance-queue` requests were still logged despite the intention to not log them.
- Fixed bug: incorrect calculation of job end time and duration in cases where `/clear-annotations` was called.
- Fixed bug: `ended` timestamp is now returned in the server's timezone.
- Fixed bug: `/swagger` route was broken.

## [2.1.0] - 2025-12-10

### Changed

- Changed the preferred installation method to `uv` instead of `pip`.
- Improved logging configuration in development mode (i.e. when running with `run.py`) which makes all logs appear in
  the console and reduces noise from certain modules.

### Added

- Added route `/sparv-schema` for retrieving the Sparv config schema.
- Distinguish between `READ`, `WRITE` and `ADMIN` access levels for resource access. This allows for more fine-grained
  control over what users can do with each resource.
- Added configuration option `SPARV_ENABLED` to enable or disable Sparv integration. If disabled, attempts to start
  Sparv jobs will raise a `ConfigurationError`. This allows for running the application in development mode with some
  unset config variables.
- Added documentation about resource access levels in the developer's guide.
- Improved error logging for time calculation in the `Job` class.

### Fixed

- Fixed pytest deprecation warnings.

## [2.0.2] - 2025-11-14

### Fixed

- Fixed bug: `installed_korp` and `installed_strix` were not reset after uninstallation
- Type issues reported by pylance have been fixed across the codebase.
- Restore `owner` in resource info

### Changed

- Raised minimum Python version to 3.11.

## [2.0.1] - 2025-11-05

### Fixed

- Fixed bug: no session ID was generated when enabling admin mode.

## [2.0.0] - 2025-10-27

### Added

- The API documentation now contains better schemas for parameters and responses.
- `/upload-sources` now contains the exception message in the response in case invalid XML is uploaded.
- Automatic tests with [pytest](https://docs.pytest.org/en/stable/) have been added.
- Added route `/swagger` which serves the Swagger UI for exploring the OpenAPI spec.
- Added route `/openapi-to-markdown` which generates a markdown version of the OpenAPI spec (mostly used for
  documentation).
- Added routes `/uninstall-korp` and `/uninstall-strix` for uninstalling a corpus from Korp or Strix.
- Added to config: a list of protected Sparv corpus config options (`SPARV_PROTECTED_CONFIG_OPTIONS`) that a Mink user
  is not allowed to modify. These options will be removed from the corpus config upon upload.
- Added field `input_changed` to the `/check-changes` response, indicating whether the input for the corpus has changed
  since the last run.

### Changed

- The application is now fastAPI instead of Flask.
- Parameters that could be supplied as both query and form parameters have been converted to pure query parameters.
- The `corpus_id` parameter has been changed to `resource_id`. (`corpus_id` may still be used but it is deprecated.)
- The `corpus_id` field in JSON responses has been changed to `resource_id`.
- The `/sparv-exports` route now also lists the names of the exported files. Exports matching any pattern listed in
  the `SPARV_EXPORT_BLACKLIST` config variable will no longer be listed.
- When uploading a file with a name that already exists, it will only be replaced if its contents have changed.
- The developer's guide has received a new look (it is rendered with mkdocs now).
- The content type for YAML file responses has been changed to 'text/yaml'.
- Cache management has been improved.
- When listing resources from the authentication system, only resources that are handled by the current backend instance
  (e.g. resources belonging to the current registry) will be shown.
- The field `latest_seconds_taken` (used e.g. in the response from `/resource-info`) is now called `duration`.
- The field `done` (used e.g. in the response from `/resource-info`) is now called `ended`.

### Deprecated

- The `corpus_id` parameter is deprecated and will be removed in a future release. Use `resource_id` instead.
- The `/api-spec` route is deprecated and will be removed in a future release. Use `/openapi.json` instead.
- The `/api-docs` route is deprecated and will be removed in a future release. Use `/redoc` instead.
- The `/developers-guide` route is deprecated and will be removed in a future release. Use `/docs` instead.
- The `/list-korp-corpora` route is deprecated and will be removed in a future release.

### Removed

- The fields `last_run_started`, `last_run_ended`, `latest_seconds_taken` and `done` have been removed from the job info
  (e.g. in the response from `/resource-info`). Use `started` and `ended` and `duration` instead.
- The fields `sources_added`, `added_sources`, `changed_config`, `changed_sources` and `deleted_sources` have been
  removed from the `/check-changes` response.

### Fixed

- Fixed bug: config changes were ignored when re-installing a corpus to Korp or Strix.
- Fixed bug: `sparv.storage.get_size()` did not return size in bytes.
- Fixed bugs related to exception handling.
- Fixed bug: when downloading a plain text source file, it was not unpickled before being sent to the user.
- Fixed buggy calculation of timestamps and elapsed time for job processes.
- When killing a Sparv process, the Snakemake lock is now removed so that the corpus can be processed again.
- Fixed bugs with `/check-changes` not detecting changes correctly.
- Fixed bug: uploading non-text source files sometimes failed due to incorrect handling of file contents.

## [1.1.0] - 2024-01-05

### Added

- Added new resource type: metadata YAML files. There are now calls for creating, uploading and downloading these.
- It is now possible to upload source files with uppercase file extensions.

### Changed

- The corpus registry and the job queue have been combined. Now, upon resource creation a job item is created
  immediately (instead of it being created first upon starting a Sparv job).
- The `/check-status`-call has been replaced with `/resource-info` with a different response format.

## [1.0.0] - 2023-09-19

This is the first release of the Mink backend! This application contains functionality for uploading and downloading
corpus-related files, processing corpora with [Sparv](https://spraakbanken.gu.se/sparv/) and installing them in
[Korp](https://spraakbanken.gu.se/korp) and [Strix](https://spraakbanken.gu.se/strix).

[unreleased]: https://github.com/spraakbanken/mink-backend/compare/v2.2.0...dev/
[2.2.0]: https://github.com/spraakbanken/mink-backend/releases/tag/v2.2.0
[2.1.1]: https://github.com/spraakbanken/mink-backend/releases/tag/v2.1.1
[2.1.0]: https://github.com/spraakbanken/mink-backend/releases/tag/v2.1.0
[2.0.2]: https://github.com/spraakbanken/mink-backend/releases/tag/v2.0.2
[2.0.1]: https://github.com/spraakbanken/mink-backend/releases/tag/v2.0.1
[2.0.0]: https://github.com/spraakbanken/mink-backend/releases/tag/v2.0.0
[1.1.0]: https://github.com/spraakbanken/mink-backend/releases/tag/v1.1.0
[1.0.0]: https://github.com/spraakbanken/mink-backend/releases/tag/v1.0.0
