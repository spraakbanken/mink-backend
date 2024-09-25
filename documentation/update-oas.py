"""Add info from INFO_YAML to infile and output OUTPUT_FILE."""

import argparse
import json
from pathlib import Path

import yaml

INFO_YAML = "info.yaml"
OUTPUT_FILE = "../mink/static/oas.yaml"


def update(oas_path: Path):
    """Add info from INFO_YAML to input_oas and output OUTPUT_FILE."""
    with Path(INFO_YAML).open(encoding="utf-8") as f:
        info_yaml = yaml.load(f, Loader=yaml.FullLoader)

    with oas_path.open(encoding="utf-8") as f:
        input_oas = yaml.load(f, Loader=yaml.FullLoader)

    # Replace '{{}}' variables
    input_oas = replace_vars(input_oas, info_yaml)

    # Override info, servers and tags
    input_oas["info"] = info_yaml.get("info")
    input_oas["servers"] = info_yaml.get("servers")
    input_oas["tags"] = info_yaml.get("tags")

    # Remove unnecessary info
    for path, pathobj in input_oas.get("paths", {}).items():
        input_oas["paths"] = remove_key(input_oas.get("paths"), "deprecated")
        for method, methodobj in pathobj.items():
            # # Remove request bodies
            # if "requestBody" in methodobj:
            #     input_oas["paths"][path][method] = remove_key(methodobj, "requestBody")
            # Remove response headers
            for response, responsobj in methodobj.get("responses", {}).items():
                if "headers" in responsobj:
                    input_oas["paths"][path][method]["responses"][response].pop("headers")

    yamldump = yaml.dump(input_oas, sort_keys=False, allow_unicode=True)
    # Save yaml
    with Path(OUTPUT_FILE).open("w", encoding="utf-8") as f:
        f.write(yamldump)
    print(f"Done converting! Saved OpenAPI specs in {OUTPUT_FILE}")  # noqa: T201


def replace_vars(oas_obj, info_obj):
    """Search and replace '{{}}' variables with their actual values."""
    # Convert to string
    oas_string = json.dumps(oas_obj)
    # Do string replacements
    for var, value in info_obj.get("variables", {}).items():
        oas_string = oas_string.replace("{{" + var + "}}", value)
    # Convert back to object
    return json.loads(oas_string)


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

    update(Path(args.input))
