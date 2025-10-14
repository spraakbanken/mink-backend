# Changelog

All notable API changes will be documented in this file. The format is based on [Keep a
Changelog](https://keepachangelog.com/en/1.0.0/).

## [unreleased]

### Added

- The API documentation now contains better schemas for parameters and responses.
- `/upload-sources` now contains the exception message in the response in case invalid XML is uploaded.
- Automatic tests with [pytest](https://docs.pytest.org/en/stable/) have been added.
- Added route `/swagger` which serves the Swagger UI for exploring the OpenAPI spec.
- Added route `/openapi-to-markdown` which generates a markdown version of the OpenAPI spec (mostly used for
  documentation).

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

### Deprecated

- The `corpus_id` parameter is deprecated and will be removed in a future release. Use `resource_id` instead.
- The `/api-spec` route is deprecated and will be removed in a future release. Use `/openapi.json` instead.
- The `/api-docs` route is deprecated and will be removed in a future release. Use `/redoc` instead.
- The `/developers-guide` route is deprecated and will be removed in a future release. Use `/docs` instead.

### Fixed

- Fixed bug: config changes were ignored when re-installing a corpus to Korp or Strix.
- Fixed bug: `sparv.storage.get_size()` did not return size in bytes.
- Fixed bugs related to exception handling.
- Fixed bug: when downloading a plain text source file, it was not unpickled before being sent to the user.

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

[unreleased]: https://github.com/spraakbanken/mink-backend/compare/v1.1.0...dev
[1.1.0]: https://github.com/spraakbanken/mink-backend/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/spraakbanken/mink-backend/releases/tag/v1.0.0
