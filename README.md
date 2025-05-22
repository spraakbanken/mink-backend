# Mink Backend

Mink is [Språkbanken Text](https://spraakbanken.gu.se/)'s data platform, allowing users to upload corpus data, annotate
it with [Sparv](https://spraakbanken.gu.se/sparv), and view or search it in [Korp](https://spraakbanken.gu.se/korp) and
[Strix](https://spraakbanken.gu.se/strix).

This is a fastAPI application serving as a backend to the [Mink frontend](https://spraakbanken.gu.se/mink).

## Prerequisites

* [Python 3.10](http://python.org/) or newer
* [memcached](http://memcached.org/)

## How to Run a Development Server

Install the requirements listed in `requirements.in` e.g. by using a Python virtual environment. Start the development
server:

```bash
fastapi dev [--host <host>] [--port <port>] mink/main.py
```

Start the queue manager:

```bash
python queue_manager.py
```

Check out the [API documentation](http://localhost:8000/redoc) and the [Developer's
Guide](http://localhost:8000/developers-guide).

## Configuration

The default configuration is defined in `config.py`. To override these settings, create a `.env` file in the project's
root directory and set the environment variables listed in `config.py`. For examples, see the [developer's
guide](/documentation/developers-guide.md#configuration).

## Tracking to Matomo

To enable tracking to Matomo, set the following config variables:

* `TRACKING_MATOMO_URL` - url to matomo
* `TRACKING_MATOMO_IDSITE` - id for this site (get from matomo admin)
* `TRACKING_MATOMO_AUTH_TOKEN` - access token to enable tracking IP numbers

## Generating PDF Documentation

To generate the PDF documentation, ensure that `pandoc`, `markdown`, and a LaTeX distribution are installed on your
system. The development server should be running at `http://localhost:8000`.

Navigate to the `/documentation/md2pdf` directory and execute:

```bash
./make-pdf.sh
```

The resulting PDF will be saved in the `documentation/md2pdf/output` directory. It includes both the Developer's Guide
and the API documentation.
