# Introduction

Mink is [Språkbanken Text](https://spraakbanken.gu.se/)'s data platform for managing, annotating, and exploring corpus
data. Users can upload their own texts, annotate them with [Sparv](https://spraakbanken.gu.se/sparv), and access or
search the results in [Korp](https://spraakbanken.gu.se/korp) and [Strix](https://spraakbanken.gu.se/strix).

The goal of Mink is to make Språkbanken Text’s research infrastructure easily accessible to researchers. With Mink, you
can apply advanced language technology methods to your own collected texts. The processed data can be downloaded or made
available through our research tools, such as Korp and Strix, with secure access.

The Mink frontend is a modern single-page web application written in [TypeScript](https://www.typescriptlang.org/) using
the [Vue 3](https://vuejs.org/) framework. It communicates with the [Mink
backend](https://github.com/spraakbanken/mink-backend/) via API calls, and leverages libraries such as
[Axios](https://axios-http.com/) and [Tailwind CSS](https://tailwindcss.com/).

The backend is a [FastAPI](https://fastapi.tiangolo.com/) application that powers the Mink frontend. It provides
endpoints for uploading and downloading corpus files, processing corpora with Sparv, and installing them in Korp and
Strix for further exploration.
