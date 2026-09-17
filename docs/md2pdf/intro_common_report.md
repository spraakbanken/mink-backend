# Introduction

Mink is [Språkbanken](https://sprakbanken.se/)'s data platform. Its goal is to make our research infrastructure easily
accessible to researchers.

As a user, you can apply advanced language technology methods to your own data, and download or explore the results in
our research tools with secure access.

Mink currently supports three kinds of resources:

- Corpora: have large text data annotated with [Sparv](https://spraakbanken.gu.se/sparv), and explore it in
  [Korp](https://spraakbanken.gu.se/korp) and [Strix](https://spraakbanken.gu.se/strix)
- Lexicons: explore lists or tabular data in [Karp's search mode](https://spraakbanken.gu.se/karp)
- Metadata: add language resources to [Språkbanken's resource catalogue](https://spraakbanken.gu.se/en/resources)

The system is built with a client-server architecture:

- **Mink frontend** runs in the user's web browser and presents a graphical user interface (GUI) to the services of the
  backend
- **Mink backend** runs on a server where it manages stored data and executes data processing operations
