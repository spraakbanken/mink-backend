# Mink Backend

Mink is [Språkbanken Text](https://spraakbanken.gu.se/)'s data platform, allowing users to upload corpus data, annotate
it with [Sparv](https://spraakbanken.gu.se/sparv), and view or search it in [Korp](https://spraakbanken.gu.se/korp) and
[Strix](https://spraakbanken.gu.se/strix).

The Mink backend is a FastAPI application serving as a backend to the [Mink frontend](https://spraakbanken.gu.se/mink).

The source code is available under the [MIT license](https://opensource.org/licenses/MIT). If you have any questions,
problems or suggestions please contact <sb-mink@svenska.gu.se>.

## Prerequisites

* [Python 3.11](http://python.org/) or newer
* [memcached](http://memcached.org/)

## Installation

To install the dependencies, we recommend using [uv](https://docs.astral.sh/uv/).

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if you don't have it already.
2. While in the mink-backend directory, run:

   ```sh
   uv sync --no-install-project
   ```

   This will create a virtual environment in the `.venv` directory and install the dependencies listed in
   `pyproject.toml`.

Alternatively, you can set up a virtual environment manually using Python's built-in `venv` module and install the
dependencies using pip:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## How to Run a Development Server

default when running `uv sync`, unless `--no-dev` is specified). Start the development server (with and activated venv,
alternatively with the `uv run` prefix, but then you can drop the `python` from the commands) with:

Ensure the dependencies listed in the `[dev]` section of `pyproject.toml` are installed. These are included by default
when running `uv sync`, unless you specify `--no-dev`.

To start the development server (with an activated virtual environment or with the `uv run` prefix, dropping `python`
from the commands), run:

```bash
python run.py [--host <host>] [--port <port>]
```

To start the queue manager, run:

```bash
python queue_manager.py
```

Once started, your development server will be running and you can access the API documentation at:
<http://localhost:8000/docs>

## Configuration

The default configuration is defined in `config.py`. To override these settings, create a `.env` file in the project's
root directory and set the environment variables listed in `config.py`. For examples, see the [developer's
guide](/docs/developers-guide.md#configuration).

## Tracking to Matomo

To enable tracking to Matomo, set the following config variables:

* `TRACKING_MATOMO_URL` - url to matomo
* `TRACKING_MATOMO_IDSITE` - id for this site (get from matomo admin)
* `TRACKING_MATOMO_AUTH_TOKEN` - access token to enable tracking IP numbers

## Testing

To run the automated tests, use `pytest` (with an activated virtual environment, or prefix the command with `uv run`):

```bash
pytest [--custom-log-level=<log_level>] [--mink-log-level=<log_level>] [-k <test_name>]
```
