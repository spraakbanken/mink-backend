# Mink Backend

Mink is [Språkbanken Text](https://spraakbanken.gu.se/)'s data platform where
users can upload corpus data, get it annotated with [Sparv](https://spraakbanken.gu.se/sparv) and view and search it in
[Korp](https://spraakbanken.gu.se/korp) and [Strix](https://spraakbanken.gu.se/strix).

This is a flask application serving as a backend to the [Mink frontend](https://spraakbanken.gu.se/mink).

## Prerequisites

* [Python 3.9](http://python.org/) or newer
* [memcached](http://memcached.org/)

## How to enable tracking to Matomo

To enable tracking to Matomo, set the following config variables:

* `TRACKING_MATOMO_URL` - url to matomo
* `TRACKING_MATOMO_IDSITE` - id for this site (get from matomo admin)
* `TRACKING_MATOMO_AUTH_TOKEN` - access token to enable tracking IP numbers

## How to run a test server

Install the requirements listed in `requirements.in` e.g. by using a Python virtual environment.

Start the test server:

```bash
python run.py
```

Start the queue manager:

```bash
python queue_manager.py
```

Check out the [API documentation](http://localhost:9000/api-doc) and the [Developer's
Guide](http://localhost:9000/developers-guide)
