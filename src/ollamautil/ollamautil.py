# ---------------------------
# OllamaUtil
#
# A CLI utility for working with and moving the Ollama cache
# Currently has certain configurations hard-coded for my own setup
# but easily adaptable to a configuraiton file.
# Current as of the cache file structure of Ollama 0.1.29.
#
# ---------------------------
# Copyright (C) 2024  Andrew M. Cox
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ---------------------------
import os
import json
import ast
import argparse
import hashlib
from prettytable import PrettyTable
from tqdm import tqdm as tqdm
from typing import List, Dict, Tuple
import shutil
import ollama
import re

# FILE_LIST_IGNORE = ['.DS_Store'] # Duplicate removed
FILE_LIST_IGNORE = ['.DS_Store']
ollama_ext_dir = '/path/to/external/ollama'
ollama_int_dir = '/path/to/internal/ollama'


def walk_dir(directory):
    files = []
    for root, dirs, file_list in os.walk(directory):
        for filename in file_list:
            if filename in FILE_LIST_IGNORE:
                continue

            if os.access(os.path.join(root, filename), os.R_OK):
                files.append(os.path.join(root, filename))
            else:
                print(f"User doesn't have access to {root}/{filename}. Skipping...")
    return sorted(files)

def display_models_table(combined: List[List], table: PrettyTable|None = None):
    table = get_models_table(combined,table=table) if not table else table
    print(table)
    print(f'\nCurrent cache set to:    \033[4m{get_curnow_cache()}\033[0m')
    return table

def get_models_table(combined: List[List], table: PrettyTable|None = None):
    if not table:
        table = PrettyTable(['Lib', 'Model', 'Tag', 'External', 'Internal'],
                        title="Ollama GPTs Installed",
                        left_padding_width=3,
                        right_padding_width=2,
                        vertical_align_char='c',
                        horizontal_align_char='c')

    # Flatten combined into a format suitable for PrettyTable
    table_rows = []
    for model_info in combined:
        model_name, external_weights, internal_weights = model_info
        all_weights = set(external_weights + internal_weights)
        for weight in all_weights:
            exists_in_external = "Yes" if weight in external_weights else "No"
            exists_in_internal = "Yes" if weight in internal_weights else "No"
            table_rows.append([model_name.split(os.sep)[-2],
                               model_name.split(os.sep)[-1],
                               weight,
                               exists_in_external,
                               exists_in_internal])

    # Sort rows by model name and then by weight for consistency
    table_rows.sort(key=lambda x: (x[0], x[1]))

    # Add row index and append rows to the table
    table.add_rows(table_rows)
    table.add_autoindex("No.")

    return table

def build_ext_int_comb_filelist() -> Tuple[dict, dict, list]:
    '''
    Builds and returns external and internal model file lists.

    Returns:
        Tuple[Dict, Dict, List]: A tuple containing two dictionaries and a list:
            - external_dict (Dict): A dictionary with external models and their weights.
            - internal_dict (Dict): A dictionary with internal models and their weights.
            - combined_list (List): A list of combined information from both dictionaries.
    '''
    # Assuming walk_dir is defined elsewhere and works as expected
    external_files = walk_dir(ollama_ext_dir + "/manifests")
    internal_files = walk_dir(ollama_int_dir + "/manifests")

    def process_files(files):
        models_dict = {}
        for file_path in files:
            # Adjusted to accommodate additional directory layers
            print(f"file_path: {file_path}") # Debug log
            parts = file_path.split("/")[-4:]  # This will select superparent/parent/model/weight
            # Remove 'manifests/' prefix from the key
            dict_key = "/".join(parts[:-1]).replace('manifests/', '')  # Modified this line
            models_dict.setdefault(dict_key, []).append(parts[-1])  # Append weight
        return models_dict

    # Process files into model: [weights] mapping
    external_dict = process_files(external_files)
    internal_dict = process_files(internal_files)

    '''
    external_dict = {}
    for e in external_models:
        external_dict.setdefault(e[0], []).append(e[1])

    internal_dict = {}
    for i in internal_models:
        internal_dict.setdefault(i[0], []).append(i[1])
    '''

    combined = []

    # Combine the external and internal dicts
    all_model_names = set(external_dict.keys()).union(internal_dict.keys())
    for model_name in all_model_names:
        external_weights = external_dict.get(model_name, [])
        internal_weights = internal_dict.get(model_name, [])
        combined.append([model_name, external_weights, internal_weights])

    return external_dict, internal_dict, combined


def get_user_confirmation(prompt):
    '''
    Prompts the user with a yes/no question and returns True/False based on the response.

    Args:
        prompt (str): The question or prompt to display to the user.

    Returns:
        bool: True if the user confirms (yes), False otherwise (no).
    '''
    valid_responses = {"yes": True, "y": True, "no": False, "n": False}
    prompt = prompt.strip()
    while True:
        # Ask the user and get the response
        user_response = input(f"{prompt} (yes/no): ").lower()

        # Validate and process the response
        if user_response in valid_responses:
            return valid_responses[user_response]
        else:
            print("Invalid response. Please answer 'yes' or 'no'.")

def get_curnow_cache():
    home = os.path.expanduser("~")
    current_path = os.path.realpath(os.path.join(home, '.ollama', 'models'))
    current_path = os.path.realpath(os.path.join(home, '.ollama', 'models'))
    curnow = None
    if current_path == ollama_int_dir:
        curnow = "internal"
    elif current_path == ollama_ext_dir:
        curnow = "external"
    else:
        AssertionError(f"Error: somehow managed to get to {current_path}")

    return curnow

def toggle_int_ext_cache(combined, table: PrettyTable = None) -> str:
    curnow = get_curnow_cache()
    toggle_to = {
        'internal': "external",
        'external': "internal"
    }

    table = display_models_table(combined=combined, table=table)
    print("Review which models are available in which cache carefully.\n\n")
    if get_user_confirmation("Would you like to move cache files first? (Note: will not overwrite existing files): "):
        direction = '1' if curnow == "external" else '0'
        migrate_cache(table=table, combined=combined, bypassGetAll=True, which_direction=direction, overwrite=False)

    print(f"Current Ollama cache set to: {curnow.upper()}.")
    user_conf = get_user_confirmation("Would you like to swap symlink the other source? (yN): ")
    if user_conf: _toggle_cache(toggle_to[curnow])
    else: print(f"No changes to Ollama cache pointer made. Still using \033[1;4m{curnow.upper()}\033[0m.")

def _toggle_cache(toggle_target: str):
    if toggle_target == "internal":
        os.system(f"ln -s -F {ollama_int_dir} ${{HOME}}/.ollama/")
        print(f"Changed .ollama symlink to look to INTERNAL drive.")
        return "external"
    elif toggle_target == "external":
        os.system(f"ln -s -F {ollama_ext_dir} ${{HOME}}/.ollama/")
        print(f"Changed .ollama symlink to look to EXTERNAL drive.")
        return "internal"
    else:
        print(f'Cache target not toggled. Requested target \'{toggle_target}\' not defined.')

def select_models(table: PrettyTable, prompt: str | None = "", allow_multiples: bool = True, bypassGetAll: bool = False) -> List[List[str]]:
    def is_valid_input(user_input) -> bool:
        pattern = r"^[\d,0-9\s\-]+$"
        if re.match(pattern, user_input):
            return True
        else:
            return False

    selected_files = []
    print(table)

    if prompt is None:
        base_prompt = "Select model/tag items to act on using numbers (e.g. 1, 3, 12-15) or all"
    else:
        base_prompt = prompt

    while True:  # Loop until valid input is received
        user_input = "ALL" if bypassGetAll else input(f"{base_prompt}: ").strip()
        if not is_valid_input(user_input):
            print(f"Invalid input, contains unpermitted characters: \'{user_input}\'. Please enter a valid selection.")
            continue

        if user_input == "":
            print("No model/tag option selected. Quitting...")
            return []

        # handle special case of "all" option (i.e. all models)
        if user_input.upper() == "ALL":
            user_input = [int(num) for num in range(1, len(table._rows) + 1)]

        # Remove leading/trailing whitespaces and split by comma
        # input() return type is 'str'`
        if type(user_input) == str:
            user_input = [num.strip() for num in user_input.split(",")]

        try:
            ranges = []
            for item in user_input:
                if '-' in item:
                    parts = item.split('-')
                    if len(parts) != 2:
                        print(f"Invalid range: \'{item}\'. Please enter a valid range. Original input:\n    '{user_input}'")
                        continue
                    start, end = map(lambda x: int(x.strip()), parts)
                    ranges.extend(range(start, end + 1))
                else:
                    ranges.append(int(item))

            # Remove duplicates and sort the list
            ranges = sorted(set(ranges))

            for i in ranges:
                selected_files.append(table._rows[i - 1][1:-2])
        except ValueError:
            print(f"Invalid input '{user_input}'. Please enter numbers separated by commas.")
            continue

        if not allow_multiples and len(selected_files) > 1:
            print("Multiple selections are not allowed. Please select only one model.")
            continue

        return selected_files

def pull_models(combined, table: PrettyTable|None = None, prompt: str|None = None, allow_multiples: bool = True):
    if table is None: table = display_models_table(combined)

    # Call 'select_models()' function and store the result in a list of files to pull
    sel_dirfil = select_models(table, prompt=prompt, allow_multiples=allow_multiples)

    for weight in sel_dirfil:
        # construct the model name/path for Ollama.com specifically
        if weight[0] != 'library':
            model_path = weight[0] + "/" + weight[1] + ":" + weight[2]
        else:
            model_path = weight[1] + ":" + weight[2]
        print(f'Pulling {model_path} from Ollama.com...')
        ollama.pull(model_path)

def push_models(combined, table: PrettyTable|None = None):
    if table is None: table = display_models_table(combined)

    sel_dirfil = select_models(table)

    for weight in sel_dirfil:
        # construct the model name/path for Ollama.com specifically
        if weight[0] != 'library':
            model_path = weight[0] + "/" + weight[1] + ":" + weight[2]
        else:
            print(f"Only personal repos are supported at this time. To upload to your personal repository, models must be saved as: \
                  \n      <username>/<model>\
                  \n  eg. sealad886/llama3:my_customization\
                  \n  eg. <username>/{':'.join(weight[1:2])}")
            continue
        print(f'Pushing {model_path} to Ollama.com...')
        ollama.push(model_path)

def migrate_cache_user(table, combined):
    if combined == []:
        external_dict, internal_dict, combined = build_ext_int_comb_filelist()
    source_files = []
    if table is None:
        table = display_models_table(combined)

    selected_files = select_models(table, None, True, bypassGetAll=False)
    if selected_files == []:
        print("No models selected. Quitting...")
        return

    which_direction = input("Move from:\n(1) external to internal\n(2) internal to external\n(1 or 2): ")
    overwrite = input("If the model already exists, should it be overwritten? (y/N): ").lower() in ("y", "yes")

    migrate_cache(table=table, combined=combined, selected_files=selected_files, bypassGetAll=False, overwrite=overwrite, which_direction=which_direction)


def migrate_cache(table: PrettyTable|None = None, combined: list = [], selected_files: list = [], which_direction: str = None, bypassGetAll: bool = False, overwrite: bool = False) -> None:
    source_files = []
    sel_dirfil = [os.sep.join(tmpvar) for tmpvar in selected_files]

    # Define source and destination directories
    source_dir = ollama_ext_dir if which_direction == '1' else ollama_int_dir
    dest_dir = ollama_int_dir if which_direction == '1' else ollama_ext_dir

    # Get the files from the selected directories
    for file_path in walk_dir(os.path.join(source_dir, "manifests")):
        # Normalize the file path to use consistent separators
        normalized_path = os.path.normpath(file_path)

        # Extract the last three segments of the path
        path_segments = normalized_path.split(os.sep)[-3:]

        # Re-join the last two segments and check if this combination is in sel_dirfil
        dir_file_combination = os.sep.join(path_segments)
        if dir_file_combination in sel_dirfil:
            source_files.append(file_path)

    for source_file in source_files:
        dest_file = os.path.join(dest_dir, *source_file.split(os.path.sep + 'models' + os.path.sep)[1:])

        # Ensure the destination directory exists
        os.makedirs(os.path.dirname(dest_file), exist_ok=True)

        # Copy the file if overwrite is True or if the file does not exist in the destination
        if overwrite or not os.path.exists(dest_file):
            with tqdm(total=os.stat(source_file).st_size, unit='B', unit_scale=True, desc=f"Copying {os.path.basename(dest_file)}") as pbar:
                with open(source_file, 'rb') as src, open(dest_file, 'wb') as dst:
                    for chunk in iter(lambda: src.read(4096), b""):
                        dst.write(chunk)
                        pbar.update(len(chunk))
                copy_metadata(source_file, dest_file)
            print(f"Copied {source_file} to {dest_file}")
        else:
            None

        # Now deal with the blobs
        copy_blob_files(source_file=source_file, dest_file=dest_file, source_dir=source_dir, dest_dir=dest_dir, overwrite=overwrite)

        # Now tell Ollama that these exist again
        # os.system(f"ollama pull {':'.join(os.path.normpath(source_file).split(os.sep)[-2:])}")

# Assuming source_file is the path to the manifest file
def copy_blob_files(source_file, dest_file, source_dir, dest_dir, overwrite):
    # load manifest
    blob_hash_prefix = "sha256-"
    bb_px_len = len(blob_hash_prefix)
    manifest_data = []
    try:
        with open(source_file, 'r') as f:
            rawdata = json.load(f)
    except Exception as e:
        print(f"Error loading manifest: {e}")
        assert rawdata is not None
    else:
        for layer in rawdata['layers']:
            if "ollama.image" in layer['mediaType']:
                manifest_data.append(layer['digest'][bb_px_len:])
        manifest_data.append(rawdata['config']['digest'][bb_px_len:])
        manifest_data.extend([layer['digest'][bb_px_len:] for layer in rawdata['layers']])

    for blob_digest in manifest_data:
        source_blob = os.path.join(source_dir, "blobs", blob_hash_prefix + blob_digest)
        dest_blob_dir = os.path.join(dest_dir, "blobs")
        dest_blob = os.path.join(dest_blob_dir, blob_hash_prefix + blob_digest)

        # Ensure the destination blob directory exists
        os.makedirs(dest_blob_dir, exist_ok=True)

        # Copy the blob file if overwrite is True or if the blob does not exist in the destination
        if overwrite or not os.path.exists(dest_blob):
            with tqdm(total=os.stat(source_blob).st_size, unit='B', unit_scale=True, desc=f"Copying {blob_digest}") as pbar:
                with open(source_blob, 'rb') as src, open(dest_blob, 'wb') as dst:
                    for chunk in iter(lambda: src.read(4096), b""):
                        dst.write(chunk)
                        pbar.update(len(chunk))
                copy_metadata(source_blob, dest_blob)
            print(f"Copied {source_blob} to {dest_blob}")

            # Validate SHA-256 hash of copied blob
            validate_blob_sha256(dest_blob, blob_hash_prefix, blob_hash_prefix + blob_digest)

def validate_blob_sha256(dest_blob: str, blob_hash_prefix: str, expected_digest: str = ""):
    sha256_hash = hashlib.sha256()
    try:
        with open(dest_blob, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        actual_chksum = sha256_hash.hexdigest()
        actual_digest = blob_hash_prefix + actual_chksum
        if expected_digest == "":
            print(f"Expected checksum for {dest_blob} not given. For your information, it is: {actual_chksum}")
        if actual_digest != expected_digest:
            print(f"Error: Digest does not match for {dest_blob}.\n    Expected {expected_digest}, got {actual_digest}.")
            handle_corrupted_file(dest_blob)
    except Exception as e:
        print(f"Error validating blob: {e}")

    print(f"Checksum verified: {dest_blob}")

def copy_metadata(src, dst) -> None:
    try:
        #shutil.copymode(src, dst)
        shutil.copystat(src, dst)
        # TODO: decide if updating the parent directory information is the right thing to do. Probably yes, but make the deicion later.
        shutil.copystat(os.path.dirname(src), os.path.dirname(dst))
    except Exception as e:
        print(f'Unable to copy metadata and other attributes for {os.path.basename(dst)}. Continuing with copy.')

def handle_corrupted_file(file_path):
    response = input("Keep corrupted file on target disk? (y/N): ").lower()
    if response not in ('y', 'yes'):
        try:
            os.remove(file_path)
            print(f"Removed corrupted file: {file_path}")
        except Exception as e:
            print(f"Error removing corrupted file: {e}")
    else:
        corrupted_path = file_path + "_corrupted"
        os.rename(file_path, corrupted_path)
        print(f"Renamed corrupted file to: {corrupted_path}")

def remove_from_cache(combined, table) -> None:
    '''Use the ollama Python library to remove models from the Ollama cache.
    User is first prompted to remove models from internal, external, or both caches, and the
    the displayed table contains only those models that exist in the selected cache(s).
    args:
        combined  (list): list of tuples containing model names and their corresponding file paths.
        table  (PrettyTable): PrettyTable object cached in memory containing the table to display
    output: None
    '''
    external_dict, internal_dict, _ = build_ext_int_comb_filelist()

    # Prompt user to select cache(s) to remove from
    caches = []        # options are: ['internal', 'external', 'both']
    while True:
        cache_choice = input("Note that \033[1;4mall Tags\033[0m are shown in both caches if you select only one. \
                             \nRemove models from which cache? (q) exit to menu, (1) internal, (2) external, (3) both? ")
        if cache_choice in ('q', 'Q'): return
        elif cache_choice in ('1', '2', '3'):
            if cache_choice ==1: caches = ['internal']
            elif cache_choice ==2: caches = ['external']
            elif cache_choice ==3: caches = ['internal', 'external']
            break
        else:
            print("Invalid choice. Please try again.")

    # Filter combined list based on user's cache selection
    if cache_choice == '1':
        edit_combined = [(model, ext_weights, int_weights) for model, ext_weights, int_weights in combined if model in internal_dict]
    elif cache_choice == '2':
        edit_combined = [(model, ext_weights, int_weights) for model, ext_weights, int_weights in combined if model in external_dict]
