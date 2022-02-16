# Maintaining OAS

The open API specification (OAS) in `minsb/static/oas.yaml` was created semi automatically.
Requests and example responses were created with [Postman](https://www.postman.com/),
converted into OAS with [APITransform](https://apitransform.com/convert/) and extended with the manually maintained
file `info.yaml`.

If APITransform is not working, the conversion can be done with
[APIMatic](https://www.apimatic.io/dashboard?modal=transform), although this requires a user account. (Anne has one.)

In order to keep the semi automatic documentation process intact you will need to import the collection `postman.json` 
into Postman. There you can add and edit requests. To update the OAS follow the following steps:

1. Export Postman collection (v2.1)
2. Adapt information in `info.yaml`
3. Run `python update-oas.py path/to/postman-collection.json` (with venv activated)
