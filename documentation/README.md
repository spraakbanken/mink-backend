# Maintaining OAS

The open API specification (OAS) in `minsb/static/oas.yaml` was created semi automatically.
Requests and example responses were created with [Postman](https://www.postman.com/),
converted into OAS with [APITransform](https://apitransform.com/convert/) and extended with the manually maintained
file `info.yaml`.

In order to keep the semi automatic documentation process intact you will need to import the collection `postman.json` 
into Postman. There you can add and edit requests. To update the OAS follow the following steps:

1. Export Postman collection.
2. Convert to OAS using https://apitransform.com/convert/ and save result as `oas.json`
3. Adapt information in `info.yaml`
4. Run `python update-oas.py path/to/oas.json` (with venv activated)
