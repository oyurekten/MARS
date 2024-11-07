from io import TextIOWrapper
import time
import requests
import json
from typing import Any
from mars_lib.authentication import get_metabolights_auth_token, get_webin_auth_token
from mars_lib.biosamples_external_references import (
    get_header,
    biosamples_endpoints,
    BiosamplesRecord,
    validate_json_against_schema,
    input_json_schema_filepath,
)
from mars_lib.credential import CredentialManager
from mars_lib.isa_json import load_isa_json
from mars_lib.models.isa_json import IsaJson
from mars_lib.target_repo import TargetRepository
from mars_lib.logging import print_and_log
from pydantic import ValidationError

from mars_lib.ftp_upload import FTPUploader
from pathlib import Path
from typing import List


def submission(
    credential_service_name: str,
    username_credentials: str,
    credentials_file: TextIOWrapper,
    isa_json_file: str,
    target_repositories: list[str],
    investigation_is_root: bool,
    urls: dict[str, Any],
    file_transfer: str,
    data_file_paths=None,
):
    # If credential manager info found:
    # Get password from the credential manager
    # Else:
    # read credentials from file
    if not (credential_service_name is None or username_credentials is None):
        cm = CredentialManager(credential_service_name)
        user_credentials = {
            "username": username_credentials,
            "password": cm.get_password_keyring(username_credentials),
        }
    else:
        if credentials_file == "":
            raise ValueError("No credentials found")

        user_credentials = json.load(credentials_file)

    isa_json = load_isa_json(isa_json_file, investigation_is_root)

    # Guard clause to keep MyPy happy
    if isinstance(isa_json, ValidationError):
        raise ValidationError(f"ISA JSON is invalid: {isa_json}")

    print_and_log(
        f"ISA JSON with investigation '{isa_json.investigation.title}' is valid."
    )

    if (
        TargetRepository.ENA in target_repositories
        and data_file_paths
        and file_transfer
    ):
        upload_to_ena(
            file_paths=data_file_paths,
            user_credentials=user_credentials,
            submission_url=urls["ENA"]["DATA-SUBMISSION"],
            file_transfer=file_transfer,
        )
    elif TargetRepository.ENA in target_repositories:
        # TODO: Filter out other assays
        ena_result = submit_to_ena(
            isa_json=isa_json,
            user_credentials=user_credentials,
            submission_url=urls["ENA"]["SUBMISSION"],
        )
        print_and_log(
            f"Submission to {TargetRepository.ENA} was successful. Result:\n{ena_result.json()}"
        )
        # TODO: Update `isa_json`, based on the receipt returned

    elif TargetRepository.BIOSAMPLES in target_repositories:
        # Submit to Biosamples
        biosamples_result = submit_to_biosamples(
            isa_json=isa_json,
            biosamples_credentials=user_credentials,
            biosamples_url=urls["BIOSAMPLES"]["SUBMISSION"],
            webin_token_url=urls["WEBIN"]["TOKEN"],
        )
        print_and_log(
            f"Submission to {TargetRepository.BIOSAMPLES} was successful. Result:\n{biosamples_result.json()}",
            level="info",
        )
        # TODO: Update `isa_json`, based on the receipt returned
    elif TargetRepository.METABOLIGHTS in target_repositories:
        metabolights_result = upload_to_metabolights(
            file_paths=data_file_paths,
            file_transfer=file_transfer,
            isa_json=isa_json,
            metabolights_credentials=user_credentials,
            metabolights_url=urls["METABOLIGHTS"]["SUBMISSION"],
            metabolights_token_url=urls["METABOLIGHTS"]["TOKEN"],
        )
        print_and_log(
            f"Submission to {TargetRepository.METABOLIGHTS} was successful. Result:\n{metabolights_result}",
            level="info",
        )
        # TODO: Update `isa_json`, based on the receipt returned
    elif TargetRepository.EVA in target_repositories:
        # Submit to EVA
        # TODO: Filter out other assays
        print_and_log(
            f"Submission to {TargetRepository.EVA} was successful.", level="info"
        )
        # TODO: Update `isa_json`, based on the receipt returned
    else:
        raise ValueError("No target repository selected.")

    # TODO: Return the updated ISA JSON


def submit_to_biosamples(
    isa_json: IsaJson,
    biosamples_credentials: dict[str, str],
    webin_token_url: str,
    biosamples_url: str,
) -> requests.Response:
    params = {
        "webinjwt": get_webin_auth_token(
            biosamples_credentials, auth_base_url=webin_token_url
        )
    }
    headers = {"accept": "*/*", "Content-Type": "application/json"}
    result = requests.post(
        biosamples_url,
        headers=headers,
        params=params,
        json=isa_json.model_dump(by_alias=True, exclude_none=True),
    )

    if result.status_code != 200:
        body = (
            result.request.body.decode()
            if isinstance(result.request.body, bytes)
            else result.request.body or ""
        )
        raise requests.HTTPError(
            f"Request towards BioSamples failed!\nRequest:\nMethod:{result.request.method}\nStatus:{result.status_code}\nURL:{result.request.url}\nHeaders:{result.request.headers}\nBody:{body}"
        )

    return result

def upload_to_metabolights(
    file_paths: list[str],
    isa_json: IsaJson,
    metabolights_credentials: dict[str, str],
    metabolights_url: str,
    metabolights_token_url: str,
    file_transfer: str = "ftp",
):
    data_upload_protocol = "ftp" if not file_transfer or file_transfer.lower() == "ftp"  else ""
    
    if not data_upload_protocol == "ftp":
        raise ValueError(f"Data upload protocol {data_upload_protocol} is not supported")
    
    token = get_metabolights_auth_token(
            metabolights_credentials, auth_url=metabolights_token_url
    )
    headers = {"accept": "*/*", "Content-Type": "application/json", 'Authorization': f'Bearer {token}',}
    result = requests.post(
        metabolights_url,
        headers=headers,
        json=isa_json.model_dump(by_alias=True, exclude_none=True),
    )
    result.raise_for_status()
    validation_url = find_value_in_info_section("validation-url", result["info"])
    validation_status_url = find_value_in_info_section("validation-status-url", result["info"])
    ftp_credentials_url = find_value_in_info_section("ftp-credentials-url", result["info"])
    
    if file_transfer == "ftp":
        ftp_credentials_url = find_value_in_info_section("validation-url", result["info"])
        ftp_credentials_response = requests.get(ftp_credentials_url, headers=headers)
        ftp_credentials_response.raise_for_status()
        ftp_credentials = ftp_credentials_response.json()
        ftp_base_path = ftp_credentials["ftpPath"]
        uploader = FTPUploader(
            ftp_credentials["ftpHost"],
            ftp_credentials["ftpUsername"],
            ftp_credentials["ftpPassword"],
        )
        
        uploader.upload(file_paths, target_location=ftp_base_path)
    
    validation_response = requests.get(validation_url, headers=headers)
    validation_response.raise_for_status()
    pool_time_in_seconds = 10
    max_pool_count = 100
    validation_status_response = None
    for _ in range(max_pool_count):
        validation_status_response = requests.get(validation_status_url, headers=headers)
        validation_status_response.raise_for_status()
        validation_status = validation_status_response.json()
        validation_time = find_value_in_info_section("validation-time", validation_status["info"], fail_gracefully=True)
        if validation_time:
            break
        time.sleep(pool_time_in_seconds)
    else:
        raise ValueError(f"Validation failed after {max_pool_count} iterations")
    
    if validation_status_response:
        return validation_status_response.text  
        
    return None

def find_value_in_info_section(key: str, info_section: list[Any], fail_gracefully: bool = False) -> Any:
    for info in info_section:
        if info["name"] == key:
            return info["message"]
    if fail_gracefully:
        return None
    raise ValueError(f"Name {key} not found in info section")
    


def submit_to_ena(
    isa_json: IsaJson, user_credentials: dict[str, str], submission_url: str
) -> requests.Response:
    params = {
        "webinUserName": user_credentials["username"],
        "webinPassword": user_credentials["password"],
    }
    headers = {"accept": "*/*", "Content-Type": "application/json"}
    result = requests.post(
        submission_url,
        headers=headers,
        params=params,
        json=isa_json.model_dump(by_alias=True, exclude_none=True),
    )

    if result.status_code != 200:
        body = (
            result.request.body.decode()
            if isinstance(result.request.body, bytes)
            else result.request.body or ""
        )
        raise requests.HTTPError(
            f"Request towards ENA failed!\nRequest:\nMethod:{result.request.method}\nStatus:{result.status_code}\nURL:{result.request.url}\nHeaders:{result.request.headers}\nBody:{body}"
        )

    return result


def upload_to_ena(
    file_paths: List[Path],
    user_credentials: dict[str, str],
    submission_url: str,
    file_transfer: str,
):
    ALLOWED_FILE_TRANSFER_SOLUTIONS = {"ftp", "aspera"}
    file_transfer = file_transfer.lower()

    if file_transfer not in ALLOWED_FILE_TRANSFER_SOLUTIONS:
        raise ValueError(f"Unsupported transfer protocol: {file_transfer}")
    if file_transfer == "ftp":
        uploader = FTPUploader(
            submission_url,
            user_credentials["username"],
            user_credentials["password"],
        )
        uploader.upload(file_paths)


def create_external_references(
    biosamples_credentials: dict[str, str],
    biosamples_externalReferences: dict[str, Any],
    production: bool,
) -> None:
    """
    Main function to be executed when script is run.

    Args:
    biosamples_credentials: Dictionary with the credentials of the submitter of the existing Biosamples records.
    biosamples_externalReferences: Dictionary containing the mapping between the
    production: Boolean indicating the environment of BioSamples to use.
    """
    if production:
        biosamples_endpoint = biosamples_endpoints["prod"]
    else:
        biosamples_endpoint = biosamples_endpoints["dev"]

    validate_json_against_schema(
        json_doc=biosamples_externalReferences, json_schema=input_json_schema_filepath
    )
    token = get_webin_auth_token(biosamples_credentials)
    if not token:
        raise ValueError("The token could not be generated.")
    header = get_header(token)

    for biosample_r in biosamples_externalReferences["biosampleExternalReferences"]:
        bs_accession = biosample_r["biosampleAccession"]
        BSrecord = BiosamplesRecord(bs_accession)
        BSrecord.fetch_bs_json(biosamples_endpoint)
        # To test it without the fetching, you can download it manually and then use:
        #   BSrecord.load_bs_json(bs_json_file="downloaded-json.json")
        new_ext_refs_list = biosample_r["externalReferences"]
        BSrecord.extend_externalReferences(new_ext_refs_list)
        BSrecord.update_remote_record(header)
