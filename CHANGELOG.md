# Changelog

All notable API changes will be documented in this file. The format is based on [Keep a
Changelog](https://keepachangelog.com/en/1.0.0/).

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

<!-- [unreleased]: https://github.com/spraakbanken/mink-backend/compare/v2.0.0...dev -->
[2.0.0]: https://github.com/spraakbanken/mink-backend/releases/tag/v2.0.0
[1.1.0]: https://github.com/spraakbanken/mink-backend/releases/tag/v1.1.0
[1.0.0]: https://github.com/spraakbanken/mink-backend/releases/tag/v1.0.0
