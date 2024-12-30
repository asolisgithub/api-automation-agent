import json
import re
import uuid


class PostmanProcessor:
    """Processes V2 Postman collection .json"""

    def __init__(self):
        pass

    def process_json(self, json_file_path):
        with open(json_file_path, encoding="utf-8") as postman_json_export:
            data = json.load(postman_json_export)
            return self.extract_verb_chunks(data)

    def extract_verb_chunks(self, data: str):

        results = []

        if isinstance(data, dict):

            for key, value in data.items():
                if key == "item" and isinstance(value, list):
                    for item in value:
                        results.extend(self.extract_verb_chunks(item))
                elif isinstance(value, dict):
                    results.extend(self.extract_verb_chunks(value))
                elif "request" in data or (("event" in data) and ("request" in data)):
                    result = {
                        "path": "",
                        "verb": "",
                        "body": {},
                        "prerequest": [],
                        "script": [],
                    }

                    if "request" in data and isinstance(data["request"], dict):
                        result["verb"] = data["request"].get("method", "")

                        if "url" in data["request"]:
                            url_value = data["request"].get("url", "")
                            raw_url_value = (
                                url_value["raw"]
                                if isinstance(url_value, dict)
                                else url_value
                            )
                            result["path"] = raw_url_value

                        if "body" in data["request"]:
                            try:
                                raw_body = data["request"]["body"].get("raw", "")
                                clean_json_body = json.loads(
                                    raw_body.replace("\r", "").replace("\n", "")
                                )
                            except (KeyError, json.JSONDecodeError):
                                clean_json_body = None
                            result["body"] = clean_json_body

                    if "event" in data and isinstance(data["event"], list):
                        for script in data["event"]:
                            if script.get("listen") == "test":
                                result["script"] = script.get("script", {}).get(
                                    "exec", []
                                )
                            elif script.get("listen") == "prerequest":
                                result["prerequest"] = script.get("script", {}).get(
                                    "exec", []
                                )
                    result["id"] = uuid.uuid4()
                    results.append(result)

        elif isinstance(data, list):
            for item in data:
                results.extend(self.extract_verb_info(item))

        return results

    def _get_root_path(self, full_path):
        match = re.search(r"(?<!/)/([^/]+)/", full_path)
        if match:
            return match.group(1)
        else:
            return ""

    def _map_object_attributes(self, obj):
        numeric_only = r"^\d+$"
        mapped_attributes = {}

        for key, value in obj.items():
            if isinstance(value, str) and re.match(numeric_only, value):
                mapped_attributes[key] = "number"
            elif isinstance(value, str):
                mapped_attributes[key] = "string"
            elif isinstance(value, dict):
                mapped_attributes[f"{key}Object"] = self._map_object_attributes(value)
            elif isinstance(value, list):
                mapped_attributes[f"{key}Object"] = "array"

        return mapped_attributes

    def _get_root_paths(self, all_paths):
        root_paths = []

        for url in all_paths:
            match = re.search(r"(?<!/)/([^/]+)/", url)
            if match:
                root_paths.append(match.group(1))

        return list(set(root_paths))

    def map_verb_chunks_to_path_chunks(self, collection_file_path):
        verb_path_query_params = []
        path_chunks = []
        distinct_paths_no_query_params = list(
            set(
                [
                    item["path"].split("?")[0]
                    for item in self.process_json(collection_file_path)
                ]
            )
        )
        for path_no_query_params in distinct_paths_no_query_params:

            verbs = []
            matching_full_paths = []

            for item in self.process_json(collection_file_path):
                if item["path"].startswith(path_no_query_params):
                    matching_full_paths.append(item)
                    if item["verb"] not in verbs:
                        verbs.append(item["verb"])

            for verb in verbs:

                numeric_only = r"^\d+$"

                all_query_params_on_verb_path = {}

                all_body_attributes_on_verb_path = {}

                for path_item in matching_full_paths:

                    if path_item["verb"] == verb:

                        if path_item["body"] is not None:
                            for key, value in path_item["body"].items():
                                if key not in all_body_attributes_on_verb_path:
                                    if isinstance(value, str) and re.match(
                                        numeric_only, value
                                    ):
                                        all_body_attributes_on_verb_path[key] = "number"
                                    elif isinstance(value, str):
                                        all_body_attributes_on_verb_path[key] = "string"
                                    elif isinstance(value, dict):
                                        all_body_attributes_on_verb_path[
                                            f"{key}Object"
                                        ] = self._map_object_attributes(value)
                                    elif isinstance(value, list):
                                        all_body_attributes_on_verb_path[
                                            f"{key}Object"
                                        ] = "array"
                                elif isinstance(value, str) and not re.match(
                                    numeric_only, value
                                ):
                                    all_body_attributes_on_verb_path[key] = "string"

                        path_sliced_on_query_param_start = path_item["path"].split("?")

                        if len(path_sliced_on_query_param_start) > 1:

                            all_query_params = path_sliced_on_query_param_start[
                                1
                            ].split("&")

                            if len(all_query_params) > 0:

                                for param in all_query_params:

                                    param_array = param.split("=")
                                    param_name = param_array[0]

                                    if (param_name) and (
                                        param_name not in all_query_params_on_verb_path
                                    ):
                                        if len(param_array) > 1:
                                            if re.match(numeric_only, param_array[1]):
                                                all_query_params_on_verb_path[
                                                    param_name
                                                ] = "number"
                                            else:
                                                all_query_params_on_verb_path[
                                                    param_name
                                                ] = "string"
                                    elif (
                                        all_query_params_on_verb_path[param_name]
                                        == "number"
                                        and len(param_array) > 1
                                    ):
                                        if not re.match(numeric_only, param_array[1]):
                                            all_query_params_on_verb_path[
                                                param_name
                                            ] = "string"

                verb_path_query_params.append(
                    {
                        "verb": verb,
                        "root_path": self._get_root_path(path_no_query_params),
                        "path": path_no_query_params,
                        "query_params": all_query_params_on_verb_path,
                        "body": all_body_attributes_on_verb_path,
                    }
                )

        path_chunks = [
            {"path": root_path, "verbs": []}
            for root_path in self._get_root_paths(distinct_paths_no_query_params)
        ]

        for verb_chunk in verb_path_query_params:
            for path_chunk in path_chunks:
                if path_chunk["path"] == verb_chunk["root_path"]:
                    path_chunk["verbs"].append(verb_chunk)

        return path_chunks
