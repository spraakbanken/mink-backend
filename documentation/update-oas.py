"""Add info from INFO_YAML to infile and output OUTPUT_FILE."""

import argparse
import json

import yaml

INFO_YAML = "info.yaml"
OUTPUT_FILE = "../minsb/static/oas.yaml"
HOST = "https://ws.spraakbanken.gu.se/ws/min-sb"


def main(infile):
    """Add info from INFO_YAML to infile and output OUTPUT_FILE."""
    with open(infile) as f:
        input_oas = json.load(f)

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

    # Convert example to schemas
    for path, pathobj in input_oas.get("paths", {}).items():
        for methodobj in pathobj.values():
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

    # Add components
    for key, value in info_yaml.get("components").items():
        input_oas["components"][key] = value

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

    main(args.input)
