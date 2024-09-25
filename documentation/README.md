# Maintaining OAS

The open API specification (OAS) in `mink/static/oas.yaml` was created semi automatically.
Requests and example responses were created with [Apidog](https://apidog.com/),
exported as an OAS and extended with the manually maintained file `info.yaml`.

Other software than Apidog may be used, as long as it can import and export OAS. Different software will probably handle
imports/exports differently, so always do some manual checking so no important information is lost from the
documentation.

In order to keep the semi automatic documentation process intact you will need to import the OAS
(`/mink/static/oas.yaml`) into Apidog. There you can add and edit requests. To update the OAS follow the following
steps:

1. Export from the 'Root' context menu, choose 'Open API 3.1'
2. Adapt information in `info.yaml`
3. Run `python update-oas.py 'path/to/Mink API.openapi.yaml'` (with venv activated)
