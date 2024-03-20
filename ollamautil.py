#!/user/bin/python3
# To make this executable, update shebang to your python interpreter
# then CHMOD +x ollamautil.py and put it in your PATH. Optionally
# remove .py from the filename.
# ---------------------------
# OllamaUtil
#
# A CLI utility for working with and moving the Ollama cache
# Currently has certain configurations hard-coded for my own setup
# but easily adaptable to a configuraiton file.
# Current as of the cache file structure of Ollama 0.1.29.
#
# ---------------------------
#    Copyright 2024 - Andrew M. Cox
#    (e) acox.dev@icloud.com
#    (w) github.com/sealad886
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
# ---------------------------
import os
import json
import ast
import hashlib
from prettytable import PrettyTable
from tqdm import tqdm as tqdm
from typing import List, Dict, Tuple

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
    return table

def get_models_table(combined: List[List], table: PrettyTable|None = None):
    if not table:
        table = PrettyTable(['Model', 'Tag', 'External', 'Internal'],
                        title="Ollama GPTs Installed (External/Internal)",
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
            table_rows.append([model_name, weight, exists_in_external, exists_in_internal])

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

    # Process files into model: [weights] mapping
    external_models = [e.split("/")[-2:] for e in external_files]
    internal_models = [i.split("/")[-2:] for i in internal_files]

    external_dict = {}
    for e in external_models:
        external_dict.setdefault(e[0], []).append(e[1])

    internal_dict = {}
    for i in internal_models:
        internal_dict.setdefault(i[0], []).append(i[1])

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


def toggle_int_ext_cache(combined, table: PrettyTable = None) -> str:
    current_path = os.path.realpath("/Users/andrew/.ollama/models")
    if current_path == ollama_int_dir:
        curnow = "internal"
    elif current_path == ollama_ext_dir:
        curnow = "external"
    else:
        AssertionError(f"Error: somehow managed to get to {current_path}")
    
    table = display_models_table(combined=combined, table=table)
    print("Review which models are available in which cache carefully.\n\n")
    if get_user_confirmation("Would you like to move ALL cache files? (Note: will not overwrite existing repos)"):
        direction = '1' if curnow == "external" else '0'
        migrate_cache_args(direction, False, ['all'])

    print(f"Current Ollama cache set to: {curnow.upper()}.")
    user_conf = get_user_confirmation("Would you like to swap symlink the other source? (yN): ")
    if user_conf:
        if curnow == "internal":
            os.system(f"ln -s -F {ollama_ext_dir} ${{HOME}}/.ollama/")
            print(f"Changed .ollama symlink to look to EXTERNAL drive.")
            return "external"
        else:
            os.system(f"ln -s -F {ollama_int_dir} ${{HOME}}/.ollama/")
            print(f"Changed .ollama symlink to look to INTERNAL drive.")
            return "internal"
    else:
        print(f"No changes to .ollama cache made. Still looking to {curnow.upper()}.")
    
        
def select_models(table: PrettyTable, prompt: str | None = "", allow_multiples: bool = True, bypassGetAll: bool = False) -> List[List[str]]:
    selected_files = []
    print(table)
    if prompt is None:
        base_prompt = "Enter the number of the model/tag to act on (e.g. 1, 3, 5) or all"
    else:
        base_prompt = prompt

    while True:  # Loop until valid input is received
        user_input = "ALL" if bypassGetAll else input(f"{base_prompt}: ").strip()
        
        if user_input.upper() == "ALL":
            user_input = list(range(1, len(table._rows) + 1))

        if user_input == "":
            print("No model/tag option selected. Quitting...")
            return []
        if type(user_input) != list:
            user_input = user_input.split(",")
        try:
            if not (type(user_input[0] is int)):
                ints = [int(x.strip()) for x in user_input if x.strip().isdigit()]
            else:
                ints = user_input
            for i in ints:
                selected_files.append(table._rows[int(i)-1][1:])
        except ValueError:
            print("Invalid input. Please enter numbers separated by commas.")
            continue

        if not allow_multiples and len(selected_files) > 1:
            print("Multiple selections are not allowed. Please select only one model.")
            continue  # Prompt the user to select again if multiple selections are not allowed
        
        return selected_files
    
def migrate_cache_args(direction: str|int, overwrite: bool=False, selected_models: list=['all']) -> None:
    '''
    To be completely honest, I'm not sure if this one works yet.

    Returns:
        None
    '''
    external_dict, internal_dict, combined = build_ext_int_comb_filelist()
    table = get_models_table(combined)
    # Assuming selected_models is a list of tuples or lists, like [('model1', 'latest'), ('model2', 'version')]
    selected_models=select_models(table, bypassGetAll=True)
    sel_dirfil = [f"{model[0]}/{model[1]}" for model in selected_models]
    if not selected_models:
        print("No models selected. Quitting...")
        return

    # Define source and destination directories based on the direction
    source_dir, dest_dir = (ollama_ext_dir, ollama_int_dir) if direction == '1' else (ollama_int_dir, ollama_ext_dir)

    source_files = []
    for file_path in walk_dir(os.path.join(source_dir, "manifests")):
        normalized_path = os.path.normpath(file_path)
        path_segments = normalized_path.split(os.sep)[-2:]
        dir_file_combination = '/'.join(path_segments)
        if dir_file_combination in sel_dirfil:
            source_files.append(file_path)

    
    for source_file in source_files:
        dest_file = os.path.join(dest_dir, '/'.join(source_file.split('/models/')[1:]))
        os.makedirs(os.path.dirname(dest_file), exist_ok=True)

        if overwrite or not os.path.exists(dest_file):
            with tqdm(total=os.stat(source_file).st_size, unit='B', unit_scale=True, desc=f"Copying {os.path.basename(dest_file)}") as pbar:
                with open(source_file, 'rb') as src, open(dest_file, 'wb') as dst:
                    for chunk in iter(lambda: src.read(4096), b""):
                        dst.write(chunk)
                        pbar.update(len(chunk))
            print(f"Copied {source_file} to {dest_file}")

        copy_blob_files(source_file=source_file, dest_file=dest_file, source_dir=source_dir, dest_dir=dest_dir, overwrite=overwrite)
        os.system(f"ollama pull {':'.join(os.path.normpath(source_file).split(os.sep)[-2:])}")


def migrate_cache(table: PrettyTable|None = None, combined: list = []) -> None:
    if combined == []:
        external_dict, internal_dict, combined = build_ext_int_comb_filelist()
    source_files = []
    if table is None:
        table = display_models_table(combined)

    selected_files = select_models(table, None, True)
    sel_dirfil = [f"{tmpvar[0]}/{tmpvar[1]}" for tmpvar in selected_files]
    if selected_files == []:
        print("No models selected. Quitting...")
        return

    which_direction = input("Move from:\n(1) external to internal\n(2) internal to external\n(1 or 2): ")
    overwrite = input("If the model already exists, should it be overwritten? (y/N): ").lower() in ("y", "yes")

    # Define source and destination directories
    source_dir = ollama_ext_dir if which_direction == '1' else ollama_int_dir
    dest_dir = ollama_int_dir if which_direction == '1' else ollama_ext_dir

    # Get the files from the selected directories
    for file_path in walk_dir(os.path.join(source_dir, "manifests")):
        # Normalize the file path to use consistent separators
        normalized_path = os.path.normpath(file_path)
        
        # Extract the last two segments of the path
        path_segments = normalized_path.split(os.sep)[-2:]
        
        # Re-join the last two segments and check if this combination is in sel_dirfil
        dir_file_combination = '/'.join(path_segments)
        if dir_file_combination in sel_dirfil:
            source_files.append(file_path)
    
    for source_file in source_files:
        dest_file = os.path.join(dest_dir, '/'.join(source_file.split('/models/')[1:]))

        # Ensure the destination directory exists
        os.makedirs(os.path.dirname(dest_file), exist_ok=True)

        # Copy the file if overwrite is True or if the file does not exist in the destination
        if overwrite or not os.path.exists(dest_file):
            with tqdm(total=os.stat(source_file).st_size, unit='B', unit_scale=True, desc=f"Copying {os.path.basename(dest_file)}") as pbar:
                with open(source_file, 'rb') as src, open(dest_file, 'wb') as dst:
                    for chunk in iter(lambda: src.read(4096), b""):
                        dst.write(chunk)
                        pbar.update(len(chunk))
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
    blob_hash_prefix = "sha256:"
    bb_px_len = len(blob_hash_prefix)
    manifest_data = []
    try:
        with open(source_file, 'r') as f:
            rawdata = json.load(f)
            manifest_data.append(rawdata['config']['digest'][bb_px_len:])
            manifest_data.extend([layer['digest'][bb_px_len:] for layer in rawdata['layers']])
    except Exception as e:
        print(f"Error loading manifest: {e}")
        return
    
    for blob_digest in manifest_data:
        source_blob = os.path.join(source_dir, "blobs", blob_hash_prefix + blob_digest)
        dest_blob_dir = os.path.join(dest_dir, "blobs")
        dest_blob = os.path.join(dest_blob_dir, blob_hash_prefix+ blob_digest)

        # Ensure the destination blob directory exists
        os.makedirs(dest_blob_dir, exist_ok=True)

        # Copy the blob file if overwrite is True or if the blob does not exist in the destination
        if overwrite or not os.path.exists(dest_blob):
            with tqdm(total=os.stat(source_blob).st_size, unit='B', unit_scale=True, desc=f"Copying {blob_digest}") as pbar:
                with open(source_blob, 'rb') as src, open(dest_blob, 'wb') as dst:
                    for chunk in iter(lambda: src.read(4096), b""):
                        dst.write(chunk)
                        pbar.update(len(chunk))
            print(f"Copied {source_blob} to {dest_blob}")

            # Validate SHA-256 hash of copied blob
            validate_blob_sha256(dest_blob, blob_hash_prefix + blob_digest)

def validate_blob_sha256(dest_blob: str, expected_digest: str = ""):
    sha256_hash = hashlib.sha256()
    try:
        with open(dest_blob, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        actual_chksum = sha256_hash.hexdigest()
        actual_digest = 'sha256:' + actual_chksum
        if expected_digest == "":
            print(f"Expected checksum for {dest_blob} not given. For your information, it is: {actual_chksum}")
        if actual_digest != expected_digest:
            print(f"Error: Digest does not match for {dest_blob}.\n    Expected {expected_digest}, got {actual_digest}.")
            handle_corrupted_file(dest_blob)
    except Exception as e:
        print(f"Error validating blob: {e}")
    
    print(f"Checksum verified: {dest_blob}")

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

def remove_from_cache() -> None:
    print("Please use 'ollama rm [MODEL]' until this functionality is finished.")
    return 
    while True:
        int_or_ext = input("Delete files from?\n1. Internal\n2. External\n3. Both")
        if int_or_ext not in ['1', '2', '3']:
            print(f"{int_or_ext} is not a valid selection.\n")
            continue
        break
    curcache = os.getenv("OLLAMA_MODELS")
    if int_or_ext == '1':
        # Internal selected
        os.environ["OLLAMA_MODELS"] = ollama_int_dir
        os.system("ollama ")
    elif int_or_ext == '2':
        # External selected
        None
    elif int_or_ext == '3':
        print(f'Option not yet implemented. Please remove files from internal and external caches separately.')

def ftStr(word: str) -> str:
    '''
    Helper function to format a string as such:
        first letter: bold and underlined
        rest of string: bold only
    In this use case, to be used to indicate to shell user which additional
    text inputs are valid options in a menu selection.

    Input:
        word: (Required) str - a string of 
    '''
    word = word.strip()
    if word == "":
        return ""
    opt = "\033[1;4m" + word[0] + "\033[0m"
    if len(word) > 1:
        opt += "\033[1m" + word[1:] + "\033[0m"
    return opt

def main_menu():
    print("\n\033[1mMain Menu\033[0m")
    print(f"1. {ftStr('Copy')} Cache")
    print(f"2. {ftStr('Toggle')} Ollama Int/Ext Cache")
    print(f"3. {ftStr('Remove')} from cache")
    print(f"4. {ftStr('Quit')}")
    choice = input("Select: ")
    return choice

def process_choice(choice: str, combined, models_table: PrettyTable|None = None):
    choice = choice.lower()
    if choice in ['1', 'c', 'copy']:
        print(f"{ftStr('Copy')} cache: migrate files between internal and external cache folders.")
        migrate_cache(models_table, combined)
    elif choice in ['2', 't', 'toggle']:
        print(f"{ftStr('Toggle')} Ollama Int/Ext Cache: Swtich between internal and external cache folders.")
        toggle_int_ext_cache(combined=combined, table=models_table)
    elif choice in ['3', 'r', 'remove']:
        print(f"{ftStr('Remove')} from cache: remove one or more model/tag from internal or external cache.")
        remove_from_cache()
    elif choice in ['4', 'q', 'quit']:
        print(f"{ftStr('Quit')} utility, exiting...")
        exit()
    else:
        print("Invalid choice, please try again.")

def main() -> None:
    '''
    Display main menu and basic high-level handling.
    '''
    # Assuming 'combined' is your list of models and weights
    while True:
        # re-build the table every time you return to the main menu
        _, _, combined = build_ext_int_comb_filelist()
        models_table = display_models_table(combined)
        choice = main_menu()
        process_choice(choice, combined, models_table=models_table)

if __name__ == "__main__":
    # define the default source directories (no training delimiter)
    # points to path of internal "modules" directory
    ollama_int_dir = os.getenv("OLLAMAUTIL_INTERNAL_DIR")
    # points to path of external "modules" directory
    ollama_ext_dir = os.getenv("OLLAMAUTIL_EXTERNAL_DIR")
    # Note that this should be set as '["val1" "val2"]' in the environment global other this won't load properly
    try:
        ollama_file_ignore = ast.literal_eval(os.getenv("OLLAMAUTIL_FILE_IGNORE"))
    except:
        print("\033[1mOLLAMAUTIL_FILE_IGNORE not set, using defaults.\033[0m")
        ollama_file_ignore = ['.DS_Store']
    if not ollama_ext_dir or not ollama_int_dir or not ollama_file_ignore:
        print(("Warning: environment variables not configured correctly",
            f"OLLAMAUTIL_INTERNAL_DIR: {ollama_int_dir}",
            f"OLLAMAUTIL_EXTERNAL_DIR: {ollama_ext_dir}",
            f"OLLAMAUTIL_FILE_IGNORE: {ollama_file_ignore}"
            "These are required to be configured before invoking this utility."))
        AssertionError("Environment variables not configured correctly. Unable to run utility.")
    FILE_LIST_IGNORE = ollama_file_ignore

    main()
