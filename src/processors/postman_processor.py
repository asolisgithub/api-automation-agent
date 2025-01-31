import json
import re
import copy


class PostmanProcessor:
    """Processes V2 Postman collection .json"""

    numeric_only = r"^\d+$"

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

                elif self._item_is_a_test_case(data):

                    result = self._extract_request_data(data)

                    if result["name"] not in {result["name"] for result in results}:

                        results.append(self._extract_request_data(data))

        elif isinstance(data, list):
            for item in data:
                results.extend(self.extract_verb_chunks(item))

        return results

    def map_verb_path_pairs_to_services(
        self, verb_path_pairs, no_query_params_routes_grouped_by_service
    ):

        verb_chunks_with_query_params = []

        self._extract_query_params_for_verb_path_pairs(
            verb_chunks_with_query_params, verb_path_pairs
        )

        verb_path_pairs_and_services = {}

        for verb_path_pair in verb_chunks_with_query_params:

            for service, routes in no_query_params_routes_grouped_by_service.items():

                if verb_path_pair["path"] in routes:

                    if service not in verb_path_pairs_and_services:
                        verb_path_pairs_and_services[service] = []

                    verb_path_pairs_and_services[service].append(
                        {
                            "verb": verb_path_pair["verb"],
                            "path": verb_path_pair["path"],
                            "query_params": verb_path_pair["query_params"],
                            "body": verb_path_pair["body"],
                        }
                    )

        return verb_path_pairs_and_services

    def add_service_name_to_verb_chunks(self, verb_chunks, all_services_dict):

        verb_chunks_tagged_with_service = copy.deepcopy(verb_chunks)

        for verb_chunk in verb_chunks_tagged_with_service:

            for service, routes in all_services_dict.items():

                verb_chunk_path_no_query_params = verb_chunk["path"].split("?")[0]

                if verb_chunk_path_no_query_params in routes:

                    verb_chunk["service"] = service
                    break

        return verb_chunks_tagged_with_service

    def get_all_distinct_paths_no_query_params(self, extracted_verb_chunks):
        distinct_paths_no_query_params = list(
            set([item["path"].split("?")[0] for item in extracted_verb_chunks])
        )

        return distinct_paths_no_query_params

    def _extract_query_params_for_verb_path_pairs(
        self, verb_path_query_params, extracted_verb_chunks
    ):
        distinct_paths_no_query_params = self.get_all_distinct_paths_no_query_params(
            extracted_verb_chunks
        )

        for path_no_query_params in distinct_paths_no_query_params:

            verbs = []
            matching_full_paths = []

            for item in extracted_verb_chunks:

                if item["path"].startswith(path_no_query_params):

                    matching_full_paths.append(item)

                    if item["verb"] not in verbs:

                        verbs.append(item["verb"])

            for verb in verbs:

                all_query_params_on_verb_path = {}

                all_body_attributes_on_verb_path = {}

                for path_item in matching_full_paths:

                    if path_item["verb"] == verb:

                        if path_item["body"] is not None:
                            self._accumulate_request_body_attributes(
                                all_body_attributes_on_verb_path, path_item["body"]
                            )

                        path_sliced_on_query_param_start = path_item["path"].split("?")

                        if len(path_sliced_on_query_param_start) > 1:

                            all_query_params = path_sliced_on_query_param_start[
                                1
                            ].split("&")

                            if len(all_query_params) > 0:
                                self._accumulate_query_params(
                                    all_query_params_on_verb_path, all_query_params
                                )

                verb_path_query_params.append(
                    {
                        "verb": verb,
                        "root_path": self._get_root_path(path_no_query_params),
                        "path": path_no_query_params,
                        "query_params": all_query_params_on_verb_path,
                        "body": all_body_attributes_on_verb_path,
                    }
                )

    def _accumulate_query_params(self, all_query_params, current_request_query_params):
        for param in current_request_query_params:

            param_array = param.split("=")
            param_name = param_array[0]

            if (param_name) and (param_name not in all_query_params):
                if len(param_array) > 1:
                    if re.match(PostmanProcessor.numeric_only, param_array[1]):
                        all_query_params[param_name] = "number"
                    else:
                        all_query_params[param_name] = "string"
            elif all_query_params[param_name] == "number" and len(param_array) > 1:
                if not re.match(PostmanProcessor.numeric_only, param_array[1]):
                    all_query_params[param_name] = "string"

    def _accumulate_request_body_attributes(
        self, all_body_attributes, current_request_body
    ):
        for key, value in current_request_body.items():
            if key not in all_body_attributes:
                if isinstance(value, str) and re.match(
                    PostmanProcessor.numeric_only, value
                ):
                    all_body_attributes[key] = "number"
                elif isinstance(value, str):
                    all_body_attributes[key] = "string"
                elif isinstance(value, dict):
                    all_body_attributes[f"{key}Object"] = self._map_object_attributes(
                        value
                    )
                elif isinstance(value, list):
                    all_body_attributes[f"{key}Object"] = "array"
            elif isinstance(value, str) and not re.match(
                PostmanProcessor.numeric_only, value
            ):
                all_body_attributes[key] = "string"

    def _to_camel_case(self, s: str) -> str:
        words = re.split(r"[^a-zA-Z0-9]", s)
        words = [word for word in words if word]
        if not words:
            return ""
        return words[0].lower() + "".join(word.capitalize() for word in words[1:])

    def _extract_request_data(self, data: str):
        result = {
            "path": "",
            "verb": "",
            "body": {},
            "prerequest": [],
            "script": [],
            "name": "",
        }

        if "request" in data and isinstance(data["request"], dict):

            result["verb"] = data["request"].get("method", "")

            if "url" in data["request"]:
                url_value = data["request"].get("url", "")
                raw_url_value = (
                    url_value["raw"] if isinstance(url_value, dict) else url_value
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
                    result["script"] = script.get("script", {}).get("exec", [])
                elif script.get("listen") == "prerequest":
                    result["prerequest"] = script.get("script", {}).get("exec", [])

        result["name"] = self._to_camel_case(data["name"])

        return result

    def _item_is_a_test_case(self, data: str):
        return "request" in data or (("event" in data) and ("request" in data))

    def _get_root_path(self, full_path):
        match = re.search(r"(?<!/)/([^/]+)/", full_path)
        if match:
            return match.group(1)
        else:
            return ""

    def _map_object_attributes(self, obj):

        mapped_attributes = {}

        for key, value in obj.items():
            if isinstance(value, str) and re.match(
                PostmanProcessor.numeric_only, value
            ):
                mapped_attributes[key] = "number"
            elif isinstance(value, str):
                mapped_attributes[key] = "string"
            elif isinstance(value, dict):
                mapped_attributes[f"{key}Object"] = self._map_object_attributes(value)
            elif isinstance(value, list):
                mapped_attributes[f"{key}Object"] = "array"

        return mapped_attributes
