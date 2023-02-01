"""Add info from INFO_YAML to infile and output OUTPUT_FILE."""

import argparse
import json
from pathlib import Path

import requests  # https://docs.python-requests.org/en/master/
import yaml

INFO_YAML = "info.yaml"
OUTPUT_FILE = "../mink/static/oas.yaml"
HOST = "https://ws.spraakbanken.gu.se/ws/min-sb"


def convert_from_postman(filepath):
    """Convert postman json export to oas with https://apitransform.com/."""
    # curl -X POST --form file="@/path/to/postman.json" 'https://nofxupu264.execute-api.us-east-1.amazonaws.com/production/api-transformation/'
    upload_url = "https://nofxupu264.execute-api.us-east-1.amazonaws.com/production/api-transformation/"
    files = {
        "file": ("postman.json", open(filepath, "rb"), "application/json"),
    }
    response = requests.post(upload_url, files=files)
    download_url = response.json().get("message")

    response = requests.get(download_url)
    oas = response.json()

    # Copy new version of postman collection into this folder
    destination = Path("postman.json")
    destination.write_bytes(Path(filepath).read_bytes())

    return oas


def replace_vars(input_oas):
    """Search and replace Postman variables with their values."""
    with open(INFO_YAML) as f:
        info_yaml = yaml.load(f, Loader=yaml.FullLoader)

    # Convert to string
    oas_string = json.dumps(input_oas)
    # Do string replacements
    for var, value in info_yaml.get("variables", {}).items():
        oas_string = oas_string.replace("{{" + var + "}}", value)
    # Convert back to object
    return json.loads(oas_string)


def update(input_oas):
    """Add info from INFO_YAML to input_oas and output OUTPUT_FILE."""
    with open(INFO_YAML) as f:
        info_yaml = yaml.load(f, Loader=yaml.FullLoader)

    # Override info, servers, tags and security
    input_oas["info"] = info_yaml.get("info")
    input_oas["servers"] = info_yaml.get("servers")
    input_oas["tags"] = info_yaml.get("tags")
    input_oas["security"] = info_yaml.get("security")

    # Remove unnecessary info
    input_oas["paths"] = remove_key(input_oas.get("paths"), "servers")
    for path, pathobj in input_oas.get("paths", {}).items():
        for method, methodobj in pathobj.items():
            if "requestBody" in methodobj:
                input_oas["paths"][path][method]["requestBody"] = remove_key(
                    methodobj.get("requestBody"), "description")
            # Remove response headers
            for response, responsobj in methodobj.get("responses", {}).items():
                if "headers" in responsobj:
                    input_oas["paths"][path][method]["responses"][response].pop("headers")

    # Convert examples to schemas
    for path, pathobj in input_oas.get("paths", {}).items():
        for methodobj in pathobj.values():
            if methodobj:
                for responseobj in methodobj.get("responses", {}).values():
                    example = responseobj.get("content", {}).get("application/json", {}).get("example", {})
                    if example:
                        new_schema = {}
                        new_schema["type"] = "object"
                        new_schema["properties"] = {}

                        for k, v in example.items():
                            new_schema["properties"][k] = {}
                            new_schema["properties"][k]["type"] = json_type(v)
                            new_schema["properties"][k]["example"] = v
                        responseobj["content"]["application/json"]["schema"] = new_schema
    input_oas["components"].pop("schemas")

    # Extend paths
    for path, pathobj in info_yaml.get("paths", {}).items():
        for method, methodobj in pathobj.items():
            input_oas["paths"][path][method].update(methodobj)

    # Override securitySchemes
    input_oas["components"]["securitySchemes"] = {}
    for key, value in info_yaml.get("securitySchemes").items():
        input_oas["components"]["securitySchemes"][key] = value

    # Override some parameters
    try:
        # OAS 3.0.0 from https://apitransform.com/
        for key, value in info_yaml.get("parameters").items():
            input_oas["components"]["parameters"][key] = value
    except KeyError:
        for key, value in info_yaml.get("parameters").items():
            for path, pathobj in input_oas.get("paths", {}).items():
                for method, methodobj in pathobj.items():
                    if methodobj:
                        for j, param in enumerate(methodobj.get("parameters", [])):
                            if param.get("name", "") == key:
                                input_oas["paths"][path][method]["parameters"][j] = value


    yamldump = yaml.dump(input_oas, sort_keys=False, allow_unicode=True)
    # print(yamldump)

    # # Save yaml
    with open(OUTPUT_FILE, "w") as f:
        f.write(yamldump)
    print(f"Done converting! Saved OpenAPI specs in {OUTPUT_FILE}")


def json_type(entity):
    """Get the json type of entity."""
    if isinstance(entity, dict):
        return("object")
    if isinstance(entity, list):
        return("array")
    if isinstance(entity, str):
        return("string")
    if isinstance(entity, int):
        return("integer")
    if isinstance(entity, float):
        return("number")
    if isinstance(entity, bool):
        return("boolean")


def remove_key(obj, bad_key):
    """Remove bad_key from obj."""
    if isinstance(obj, dict):
        obj = {key: remove_key(value, bad_key) for key, value in obj.items() if key != bad_key}
    elif isinstance(obj, list):
        obj = [remove_key(item, bad_key) for item in obj if item != bad_key]
    return obj


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extend the open API specification with info from 'info.yaml'.")
    parser.add_argument("input", type=str, help="The input OAS file (in json)")
    args = parser.parse_args()

    # oas = convert_from_postman(args.input)
    # oas = replace_vars(oas)
    # update(oas)

    # Use this if run with https://www.apimatic.io/dashboard?modal=transform
    with open(args.input) as f:
        oas = yaml.load(f, Loader=yaml.FullLoader)
        oas = replace_vars(oas)
    update(oas)
