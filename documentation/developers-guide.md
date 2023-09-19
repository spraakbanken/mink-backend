# Developer's Guide for the Mink Backend

Mink is [Språkbanken Text](https://spraakbanken.gu.se/)'s platform where
users can upload corpus data, get it annotated with [Sparv](https://spraakbanken.gu.se/sparv) and view and search it in
[Korp](https://spraakbanken.gu.se/korp) and [Strix](https://spraakbanken.gu.se/strix).

This is a Flask application serving as a backend to the [Mink frontend](https://spraakbanken.gu.se/mink). In short, the
backend contains functionality for uploading and downloading corpus-related files, processing corpora with Sparv and
installing them in Korp and Strix.

This document serves as documentation for Mink backend developers. It explains how the backend works, provides
information about the general structure of the application and its critical parts. It also holds information on how the
API is documented and tested.

## Workflow

Although there is no strict order in which a user needs to make calls to the Mink backend, there is a natural workflow
that should be followed (more or less) to achieve successful processing of data. Reading the following workflow
description will give you a general idea of how the Mink backend works.

**1. Creating a new corpus**

Before any data can be uploaded and processed a user needs to create a corpus (when using the Mink frontend this is done
behind the scenes). When creating a new corpus Mink will generate a unique corpus ID (prefixed with 'mink-') which will
be stored in the backend's corpus registry. The generated corpus ID will also be registered in the authentication system
and the user creating the corpus will receive owner rights. Creating a new corpus is done through the `/create-corpus`
route.

**2. Uploading corpus source files**

The uploaded corpus source files will be stored on the [storage server](#servers) in a directory that receives its name
from the corpus ID. When uploading multiple files the backend will check whether the file extensions match since Sparv
cannot handle a corpus with source files of different types. Uploading source files is done with the `/upload-sources`
route.

**3. Uploading a corpus config file**

Before a corpus can be processed with Sparv the user needs to upload a [Sparv corpus config
file](https://spraakbanken.gu.se/sparv/#/user-manual/corpus-configuration). When using Mink through the frontend the
user won't usually have to do this manually because the frontend will generate a default config file. When uploading a
config file the backend will check if the `importer` specified in the config file matches the file extension of
previously uploaded source files (if there are any). Uploading a config file is done with the `/upload-config`.

**4. Running Sparv**

When a corpus has source files and a corpus config file it can be processed with Sparv which means enriching the source
files with automatic annotations and producing different output formats (exports). This is done through the `/run-sparv`
route. In a setup where the [storage server](#servers) is separated from the [Sparv server](#servers) calling
`/run-sparv` will trigger a synchronisation step where source and config files are copied from the storage server to the
Sparv server (otherwise this step is skipped). Before Sparv is run the backend will check if the `importer` specified in
the config file matches the file extension of the source files (in case the config was uploaded first).

During this step a [job object](#job-object) is created and the job is added to the [job queue](job-queue). Once all
previous queue items have been processed Sparv will start processing the corpus automatically.

**5. Checking the status**

When a job has been queued its status can be checked with the `/check-status` route. The answer provides information
about the queue priority, the status of the annotation process, how long it took to process the corpus and possible
warnings and errors produced by Sparv. The meaning of the different status codes can be checked by calling the
`/status-codes` route.

In a setup where the [storage server](#servers) is separated from the [Sparv server](#servers) it is necessary to do a
status check upon completion of the annotation process in order for the export files to be synced.

**6. Downloading export files**

When a Sparv job has been completed for a corpus the user may download the export files for viewing and further
processing. This can be done with the `/download-exports` route. The user can choose to download all exports or specific
subdirectories or files.

**7. Installing in Korp and/or Strix**

Instead of downloading files the user may want to install the corpus in our corpus search tools Korp or Strix (or both).
This can be done with the `/install-korp` and `/install-strix` routes. Installation is done with Sparv and thus an
installation process needs to be queued just like an annotation process.

After a successful installation the user can log into Korp/Strix and search their own corpora as usual. Installations
are private which means that they can only be viewed by the logged-in user owning the installed corpus.


## Project Structure

### Important Concepts

#### Job Object

A job object is created when a user attempts to run a corpus through Sparv. It holds information about some general
corpus properties, the user who created the job, the annotation process and of course the job status. The job object is
stored in a json file in the instance directory of the backend and for quicker access it is also cached (using
[Memcached](https://memcached.org/)). The information is updated upon `/check-status` calls (if any information has
changed).

#### Job Queue

In order to prevent overloading Sparv with too many simultaneous annotation or installation processes the Mink backend
has a queuing system. When a user attempts to run a corpus through Sparv a job object is created and the job will be
added to the job queue. The queue manager will check regularly if there is capacity to run another job and start the
annotation or installation process for the next job in line.

#### Queue Manager

The queue manager is not part of the Flask application but can be seen as an external component that is run as a
separate process. The Python package [APScheduler](https://apscheduler.readthedocs.io/en/3.x/) is used to run the queue
manager in regular time intervals. The queue manager will call the `/advance-queue` route of the mink backend API which
in turn will do three things:

1. Unqueue jobs that are done, aborted or erroneous.
2. For running jobs, it checks if their processes are still running. If not they will be removed.
3. If there are fewer running jobs than allowed, it will run the next job in the job queue.


### Modules

The Mink backend is organised into different modules. The application should be kept as modular as possible so that
different components can be replaced more easily.

The following scripts belong to the `core` module which provides general functionality and cannot be easily exchanged:
- `corpus_registry.py` containing code for keeping track of all corpora uploaded to Mink
- `exceptions.py` containing Mink specific exceptions
- `jobs.py` containing code for managing and running corpus jobs (for processing and installing corpora)
- `queue.py` containing code for the job queuing system
- `routes.py` containing some general routes that are independent of non-core functionality (like serving the
  documentation)
- `status.py` containing classes for handling job statuses
- `utils.py` containing general utility functions

Furthermore there are some modules (Python subpackages) for more specific purposes that may be replaced by other
components in the future:
- `sb_auth` for authentication with sbAuth
- `sparv` for processing jobs with Sparv and for file storage
- `memcached` for caching jobs and the job queue with [Memcached](https://memcached.org/)

### Servers

The Mink backend is typically (but not necessarily) distributed over multiple servers:

- The **backend server** is where the flask application is running, receiving and processing the requests.

- The **storage server** is where the user's corpus source files, the corpus config file and the resulting export files
  are being stored.

- The **Sparv server** is where Sparv is run and ideally this is a server with a GPU. The corpus source files and the
  corpus config files must be synced here from the storage server before corpora can be processed. The working files
  used by Sparv are stored here but they may be deleted when a corpus is done processing or installing or when a user
  has not accessed it for some time. The export files resulting from running Sparv are also stored here and will be
  synced to the storage server. In the current Mink setup no separate storage server is used and the Sparv server also
  acts as a storage server.

- Installing corpora from Mink usually means syncing specific Sparv export files to servers where other applications
  (e.g. Korp and Strix) are run.


## API documentation

The API for this application is documented with an [OpenAPI Specification](https://spec.openapis.org/oas/v3.1.0) (OAS)
which is a standard interface description for HTTP APIs. It is being used for generating the documentation web page that
is shown on the `/api-doc` route.

The OAS is located in `mink/static/oas.yaml` and was created semi automatically. Requests including their parameters and
descriptions as well as example responses were created manually with [Postman](https://www.postman.com/), converted into
OAS with [APIMatic](https://www.apimatic.io/dashboard?modal=transform) and extended with the manually maintained file
`info.yaml`.

In order to keep the semi automatic documentation process intact you will need to import the collection `postman.json` 
into Postman where one can can add and edit requests. To update the OAS follow the following steps:

1. Export Postman collection (v2.1).
2. Convert the Postman collection into an OAS using APIMatic.
3. Adapt information in `info.yaml` if necessary.
4. Run `python update-oas.py path/to/OAS.json`.

This will produce a new version of `mink/static/oas.yaml`. Don't forget to check in new versions of `postman.json`,
`info.yaml` and `oas.yaml`.


## Testing

There are no automatic tests in place yet. For manual testing [Postman](https://www.postman.com/) is recommended. A
Postman collection is included in the `documentation` folder which can be imported in the application and after setting
some environment variables all the routes can be run from the interface. The necessary environment variables are listed
in the table below.


|Variable |Description |Example Value |
|:--------|:-----------|:-------------|
|`host` |URL to the backend |`http://localhost:9000` |
|`standard-corpus` |ID of the corpus that is used in most of the example calls |`mink-dxh6e6wtff` |
|`fake-corpus` |ID of a non existing corpus that is used to generate error responses |`mink-dxh6e6wtfg` |
|`api-key` |API key used for authentication in the internal routes |`2XZqJKYD3AjeBnw9D5RUaMDp` |
|`jwt` |A valid bearer token (JWT) |`eyJ0eXA...`|
