#!/Users/andrew/venvs/ollamautil/bin/python
# To make this executable, update shebang to your python executable
# (this should be your venv/bin/python file usually, not /usr/bin/python)
# To run as a command line util, run 'CHMOD +x ollamautil.py', and then put
# the final executable in your PATH. Optionally remove .py from the filename.
# command line execution: ollamautil
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
import os
import json
import ast
import argparse
import hashlib
from prettytable import PrettyTable
from tqdm import tqdm as tqdm
from typing import List, Tuple
import shutil
import ollama
import warnings
from copy import deepcopy
from contextlib import contextmanager

VERSION = "2.0.0"
GITPAGE = "https://github.com/sealad886/ollama_util"


def display_welcome() -> None:
    '''
    Print a welcome message and version number to stdout.
    Input: None
    Output: None
    '''
    welcome_message = f"\033[1;4mOllamaUtil\033[0m (c) 2024" \
        f"\nVersion {VERSION}\nMore info at: {GITPAGE}"
    print(welcome_message)


class Model:
    valid_cache_types = ['internal', 'external']

    def __init__(self, config, layers, library, model, version):
        self.config: dict = config
        self.layers: dict = layers
        self.caches: List[Tuple[str, str]] = []
        self.library: str = library
        self.model: str = model
        self.version: str = version

    @property
    def name(self):
        if self.library == "library":
            return f"{self.model}:{self.version}"
        else:
            return f"{self.library}/{self.model}:{self.version}"

    @property
    def manifest(self):
        return f"{self.library}/{self.model}/{self.version}"

    @property
    def size(self):
        size = 0
        if 'size' in self.config:
            size += self.config['size']
        for layer in self.layers:
            if 'size' in layer:
                size += layer['size']
        return size

    def add_cache_flag(self, cache: Tuple[str, str]):
        if cache[0] not in self.valid_cache_types:
            warn_text = "Unable to set invalid cache flag for cache type: %s."
            warnings.warn(warn_text % cache)
            return
        if cache not in self.caches:
            self.caches.append(cache)

    def remove_cache_flag(self, cache: Tuple[str, str]):
        if cache in self.caches:
            self.caches.remove(cache)
        else:
            warnings.warn(f"Attempted to remove cache flag {cache[0]} "
                          f"from model {self.name}, but model does not exist "
                          "in the specified cache.")

    def is_in_cache(self, cache_str: str = ""):
        if cache_str not in self.valid_cache_types:
            warnings.warn(f"Attempt to check cache {cache_str} but "
                          f"{cache_str} is not a valid cache type.")
            return False
        for cache in self.caches:
            if cache_str in cache:
                return True
        return False

    def to_dict(self):
        model_dict = {
            "name": self.name,
            "config": self.config,
            "layers": self.layers,
            "caches": self.caches,
            "size": self.size,
            "library": self.library,
            "model": self.model,
            "version": self.version
        }
        return model_dict

    def __eq__(self, other):
        if not isinstance(other, Model):
            return False
        return (
            self.name == other.name and
            self.get_digests() == other.get_digests()
        )

    def copy(self):
        return deepcopy(self)

    def get_digests(self):
        '''
        Return a list of the digest/blod file names to be moved.
        If the manifest file describes the filenames using a ':'
        character, this returns the file names using a '-' instead.
        Returns:
            List of digest filenames, replaces ':' with '-'
        '''
        digests = []
        digests.append(self.config['digest'].replace(':', '-'))
        for layer in self.layers:
            digests.append(layer['digest'].replace(':', '-'))
        return digests

    def get_size(self):
        def convert_bytes(size):
            for x in ['bytes', 'KB', 'MB', 'GB', 'TB']:
                if size < 1024.0:
                    return "%3.1f %s" % (size, x)
                size /= 1024.0

            return size
        return convert_bytes(self.size)

    def __str__(self):
        return f"{self.name} ({self.get_size()}): contains {len(self.get_digests())} digests."


@contextmanager
def auto_cache_state():
    original_cache = get_curnow_cache()
    try:
        yield
    finally:
        _toggle_cache(original_cache, silent=True)


def cache_type_to_cache(cache_type: str) -> Tuple[str, str]:
    return next((cache, path) for cache, path in valid_caches if cache == cache_type)


def get_user_confirmation(prompt: str):
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
    curnow = None
    if current_path == ollama_int_dir:
        curnow = ("internal", current_path)
    elif current_path == ollama_ext_dir:
        curnow = ("external", current_path)
    else:
        AssertionError(f"Error: somehow managed to get to {current_path}")

    return curnow


def toggle_cache(skip_conf: bool = False) -> str:
    curnow, curnow_path = get_curnow_cache()
    toggle_to = {
        'internal': next((cache, path) for cache, path in valid_caches if cache == 'external'),
        'external': next((cache, path) for cache, path in valid_caches if cache == 'internal')
    }

    print(f"Current Ollama cache set to: {curnow.upper()}.")
    prompt = f"Would you like to swap symlink to \033[1m{toggle_to[curnow][0].upper()}\033[0m source? (yN): "
    if skip_conf or get_user_confirmation(prompt):
        _toggle_cache(toggle_to[curnow])
    else:
        print(f"No changes to Ollama cache pointer made. Still using \033[1;4m{curnow.upper()}\033[0m.")


def _toggle_cache(toggle_target: Tuple[str, str], *, silent=False) -> str:
    '''
    WARNING: any calling function should ensure that the cache state is returned
    to the original state when that function returns.
    Use decorator @auto_cache_state() where possible
    Change the cache symlinked at $HOME/.ollama.
    '''
    if not is_cache_available(toggle_target):
        warnings.warn(f"Target cache toggle {toggle_target[0].upper()} is not available.")
        return
    if toggle_target[0] == "internal":
        os.system(f"ln -s -F -f -h {ollama_int_dir} ${{HOME}}/.ollama/models")
        if not silent:
            print("Changed .ollama symlink to look to INTERNAL drive.")
        return "external"
    elif toggle_target[0] == "external":
        os.system(f"ln -s -F -f -h {ollama_ext_dir} ${{HOME}}/.ollama/models")
        if not silent:
            print("Changed .ollama symlink to look to EXTERNAL drive.")
        return "internal"
    else:
        warnings.warn(f'Cache target not toggled. Requested target \'{toggle_target[0]}\' not defined.')


def models_in_cache_list() -> List[Tuple[str, str, str]]:
    model_list = ollama.list()['models']
    model_names: List[str] = []
    for mod in model_list:
        model_names.append(mod['name'])
    for i, name in enumerate(model_names):
        if "/" in name:
            fq_library, fq_model = name.split('/', 1)
            fq_model, fq_version = fq_model.split(':', 1)
        else:
            fq_library = 'library'
            fq_model, fq_version = name.split(':', 1)
        model_names[i] = (fq_library, fq_model, fq_version)
    return model_names


@auto_cache_state()
def build_model_list(models: List[Model], *, force_rebuild: bool = False) -> list:
    if models != [] and not force_rebuild:
        warn_text = "Attempted to build_model_list, but the model_list is already built. " \
            "Use force_rebuild=True if the list should be rebuilt regardless."
        warnings.warn(warn_text)
        return
    caches = available_caches()
    # print(f'Available caches: {[c[0] for c in caches]}')
    for cache, cache_path in caches:
        _toggle_cache((cache, cache_path), silent=True)
        skipped_models = 0
        manifest_path = os.path.join(cache_path, "manifests", "registry.ollama.ai")
        for model in models_in_cache_list():
            try:
                with open(os.path.join(manifest_path, *model), 'r') as man:
                    manifest = json.load(man)
            except OSError as e:
                warnings.warn(f"Attempting to read manifest {model}, cached files do not exist.", source=e)
                continue
            new_model = Model(
                manifest['config'],
                manifest['layers'],
                *model
            )
            new_model.add_cache_flag((cache, cache_path))
            pass
            existing_model: Model = next((m for m in models if m == new_model), None)
            if existing_model:
                existing_model.add_cache_flag((cache, cache_path))
                skipped_models += 1
            else:
                models.append(new_model)

    return models


def is_cache_available(cache_tuple: str) -> bool:
    return os.path.isdir(cache_tuple[1])


def available_caches() -> List[Tuple[str, str]]:
    available_caches = []
    for cache in valid_caches:
        if is_cache_available(cache):
            available_caches.append(cache)
    return available_caches


def display_models(models: List[Model]) -> None:
    """
    Display the list of models and their metadata using PrettyTable.

    Parameters:
    models (List[Model]): The list of Model objects to display.
    """
    # Create a PrettyTable object
    table = PrettyTable()

    # Set the field names (column headers)
    table.field_names = ["Library", "Model", "Version", "Size", "Int?", "Ext?"]

    # Add rows to the table for each model
    for model in models:
        table.add_row([model.library, model.model, model.version,
                       model.get_size(), model.is_in_cache('internal'),
                       model.is_in_cache('external')])

    table.add_autoindex("No.")

    # Print the table
    print(table)


def copy_models_cache_to_cache(models: List[Model]):
    def convert_bytes(size):
        for x in ['bytes', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return "%3.1f %s" % (size, x)
            size /= 1024.0

        return size
    # Step 1: Confirm the current and target caches
    current_cache = get_curnow_cache()
    if len(valid_caches) == 2:
        target_cache = next((cache for cache in valid_caches if cache != current_cache))
    else:
        print("Multiple caches found.")
        for i, cache in enumerate(valid_caches):
            print(f"{i + 1}. {cache[0].capitalize()} ({cache[1]})")
        target_choice = int(input("Select the target cache number: ")) - 1
        target_cache = valid_caches[target_choice]

    if current_cache == target_cache:
        print("Current cache and target cache are the same. No action taken.")
        return

    # Step 2: Display available models
    selected_models = user_select_models(models)

    if not selected_models:
        print("No valid models selected. Exiting copy operation.")
        return

    # Step 3: Build the list of files to copy
    files_to_copy = build_files_to_copy(selected_models, current_cache)
    # Check if files already exist in the destination cache
    target_cache_path = target_cache[1]
    existing_files = [
        f for f in files_to_copy if os.path.exists(f.replace(current_cache[1], target_cache_path))
    ]

    if existing_files:
        print(f"\nOf {len(files_to_copy)} total files, {len(existing_files)} files already exist in the destination cache.")

        overwrite = get_user_confirmation("Do you want to overwrite these files?")
        if not overwrite:
            # Remove the existing files from the list of files to copy
            files_to_copy = [f for f in files_to_copy if f not in existing_files]

    if not files_to_copy:
        print("No files to copy. Exiting copy operation.")
        return

    # Step 4: Confirm transfer details
    print(f"Copying from {current_cache[0]} to {target_cache[0]}.")
    total_size = sum(os.path.getsize(f) for f in files_to_copy)
    print(f"Total files to copy: {len(files_to_copy)} "
          f"{f'(excluding {len(existing_files)} existing files)' if not overwrite else ''}")
    print(f"Total size: {convert_bytes(total_size)}")

    if not get_user_confirmation("Proceed with the transfer? "):
        print("Transfer cancelled by the user.")
        return

    # Step 5: Copy files and verify integrity
    copy_files(files_to_copy, current_cache, target_cache)

    # Step 6: Handle any errors and cleanup if necessary
    print("Transfer completed successfully.")


def parse_indices(indices: str, models: List) -> List:
    """
    Parse user input indices to select models.

    Args:
        indices (str): The indices entered by the user.
        models (List[Model]): The list of models.

    Returns:
        List[Model]: The list of selected models.
    """
    selected = []
    if indices.lower() == 'all':
        selected = models
    else:
        try:
            ranges = indices.split(',')
            for r in ranges:
                if '-' in r:
                    start, end = map(int, r.split('-'))
                    selected.extend(models[start - 1:end])
                else:
                    selected.append(models[int(r) - 1])
        except (ValueError, IndexError):
            print("Invalid selection. Please enter valid indices.")
    return selected


def build_files_to_copy(models: List[Model], current_cache: Tuple[str, str]) -> List[str]:
    """
    Build the list of files to copy for the selected models.

    Args:
        models (List[Model]): The selected models.
        current_cache (Tuple[str, str]): The current cache.

    Returns:
        List[str]: The list of file paths to copy.
    """
    files_to_copy = set()
    for model in models:
        for digest in model.get_digests():
            digest_path = os.path.join(current_cache[1], 'blobs',  digest)
            if os.path.exists(digest_path):
                files_to_copy.add(digest_path)
        manifest_path = os.path.join(current_cache[1], 'manifests', 'registry.ollama.ai', model.manifest)
        if os.path.exists(manifest_path):
            files_to_copy.add(manifest_path)
    return list(files_to_copy)


def copy_files(files_to_copy: List[str], current_cache: Tuple[str, str], target_cache: Tuple[str, str]) -> None:
    """
    Copy the files and verify integrity.

    Args:
        files_to_copy (List[str]): The files to copy.
        current_cache (Tuple[str, str]): The current cache.
        target_cache (Tuple[str, str]): The target cache.
    """
    target_dir = target_cache[1]
    for file in tqdm(files_to_copy, desc="Copying files", unit="file", dynamic_ncols=True, miniters=1):
        target_file = file.replace(current_cache[1], target_dir)
        target_dir_path = os.path.realpath(os.path.dirname(target_file))
        os.makedirs(target_dir_path, exist_ok=True)
        shutil.copy2(file, target_file)
        if not file_integrity_check(file, target_file):
            warnings.warn(f"Integrity check failed for file: {file}")


def file_integrity_check(source_file: str, target_file: str) -> bool:
    """
    Check if the copied file has the same hash as the source file.

    Args:
        source_file (str): The source file.
        target_file (str): The target file.

    Returns:
        bool: True if integrity is intact, False otherwise.
    """
    return file_hash(source_file) == file_hash(target_file)


def file_hash(file_path: str) -> str:
    """
    Calculate the hash of a file.

    Args:
        file_path (str): The path to the file.

    Returns:
        str: The hash of the file.
    """
    hash_md5 = hashlib.md5()
    buffer_size = 65536
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(buffer_size), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def user_select_models(models):
    display_models(models)
    model_indices = input("\nSelect models by index (e.g., 1,2,3 or 1-3): ")
    selected_models = parse_indices(model_indices, models)
    return selected_models


def user_select_cache(curcache, avail_caches):
    for i, av_c in enumerate(avail_caches):
        print(f"{'*' if cache_type_to_cache(curcache) == av_c else ''}{i+1} {av_c}")
    print("* indicates current cache")
    selected = input("Which cache(s) should models be removed from? (e.g. 1,2,3 or 1-3): ")
    return parse_indices(selected, avail_caches)


@auto_cache_state()
def remove_model_from_cache(models: List[Model]) -> None:
    """
    Remove one or more models from the specified cache.
    Prompts the user to select models to remove, confirms the action, and deletes the relevant files.

    Parameters:
    models (List[Model]): The list of available Model objects.
    """

    # Display available models for removal
    display_models(models)
    current_cache_type, current_cache_path = get_curnow_cache()

    # Prompt user to select models to remove
    selected_models = user_select_models(models)

    # Validate the selection
    if not selected_models:
        print("No valid models selected. Operation canceled.")
        return

    # Prompt user to select cache(s)
    selected_caches = user_select_cache(current_cache_type, available_caches())
    if not selected_caches:
        print("No caches selected. Operation canceled.")
        return

    print("\nSelected models for removal:")
    for model in selected_models:
        print(f" - {model.name}")
    print(f"Models will be removed from the following cache(s): {[c[0] for c in selected_caches]}")

    # Confirm with the user before proceeding
    if not get_user_confirmation("This operation can not be undone.\nAre you sure you want to remove the above models?"):
        print("Removal canceled.")
        return

    # Remove the selected models
    for cache in selected_caches:
        _toggle_cache(cache)
        for model in tqdm(selected_models, desc="Deleting models", unit="models", dynamic_ncols=True):
            ollama.delete(model.name)

        # I think ollama.list() will force the ollama server to do its cleanup activites?
        _ = ollama.list()
    # Display results
    print(f"Removed {len(selected_models)} models successfully.")

    # Refresh models list after removal
    models = build_model_list(models, force_rebuild=True)


def pull_models(models: List[Model]) -> None:
    """
    Pull selected models from Ollama.com.

    Args:
        models (List[Model]): The list of available Model objects.
    """
    selected_models = user_select_models(models)

    if not selected_models:
        print("No valid models selected. Operation canceled.")
        return

    print("\nSelected models to pull:")
    for model in selected_models:
        print(f" - {model.name}")

    # Confirm with the user before proceeding
    prompt = "This operation may take some time depending on the number of" \
        "models and your connection speed.\nAre you sure you want to pull the above models?"
    if not get_user_confirmation(prompt):
        print("Pull operation canceled.")
        return

    for model in tqdm(selected_models, desc="Pulling models", unit="models", dynamic_ncols=True):
        ollama.pull(model.name)

    print(f"Pulled {len(selected_models)} models successfully.")


def push_models(models: List[Model]) -> None:
    """
    Push selected models to Ollama.com.

    Args:
        models (List[Model]): The list of available Model objects.
    """
    selected_models = user_select_models(models)

    if not selected_models:
        print("No valid models selected. Operation canceled.")
        return

    print("\nSelected models to push:")
    for model in selected_models:
        print(f" - {model.name}")

    # Confirm with the user before proceeding
    prompt = "This operation may take some time depending on the number " \
        "of models and your connection speed.\nAre you sure you want to push the above models?"
    if not get_user_confirmation(prompt):
        print("Push operation canceled.")
        return

    for model in tqdm(selected_models, desc="Pushing models", unit="models", dynamic_ncols=True):
        ollama.push(model.name)

    print(f"Pushed {len(selected_models)} models successfully.")


def ftStr(word: str, emphasis_index=0, emphasis_span=1) -> str:
    """
    Formats a string with escape chars to bold and underline chosen chars.

    Parameters:
        word   (str): String to format; can be of any length including zero.
        emphasis_index   (int, optional): Index of first emphasized char
                                        (default is 0).
        emphasis_span   (int, optional): Number of consecutive emphasized chars
                                       after the index (default is 1).

    Returns:
        str: Formatted string with embedded escape characters.

    Raises:
        TypeError: If word is not a string or both index and span are not integers.
        ValueError: If emphasis_index is outside the bounds of the string.
    """
    if not isinstance(word, str) or not all(isinstance(arg, int) for arg in [emphasis_index, emphasis_span]):
        raise TypeError("Word must be a string; emphasis index and span must be integers.")

    word = word.strip()
    if len(word) == 0:
        return ""

    if emphasis_index < 0 or emphasis_index >= len(word):
        raise ValueError("Emphasis index must be between 0 and the length of the string.")

    opt = "\033[1m" + word[:emphasis_index] + "\033[0m"
    if emphasis_span > 0:
        opt += "\033[4;1m" + word[emphasis_index:emphasis_index+emphasis_span] + "\033[0m"
    if emphasis_index + emphasis_span < len(word):
        opt += "\033[1m" + word[emphasis_index+emphasis_span:] + "\033[0m"

    return opt


def process_choice(choice: str, models: List[Model]):
    choice = choice.lower()
    if choice in ['0', 'd', 'display']:
        print(f"{ftStr('Display')} contents of internal and external cache directories in a table.")
        display_models(models)
    elif choice in ['1', 'c', 'copy']:
        print(f"{ftStr('Copy')} cache: migrate files between internal and external cache folders.")
        copy_models_cache_to_cache(models)
    elif choice in ['2', 't', 'toggle']:
        print(f"{ftStr('Toggle')} Ollama Int/Ext Cache: Swtich between internal and external cache folders.")
        toggle_cache()
    elif choice in ['3', 'r', 'remove']:
        print(f"{ftStr('Remove')} from cache: remove one or more model/tag from internal or external cache.")
        remove_model_from_cache(models)
    elif choice in ['4', 'p', 'pull']:
        print(f"{ftStr('Pull')} selected models from Ollama.com, will not pull files if they already exist.")
        pull_models(models)
    elif choice in [5, 'u', 'push']:
        print(f"{ftStr('Push', 1)} selected models to Ollama.com.")
        push_models(models)
    elif choice in ['Q', 'q', 'quit']:
        print(f"{ftStr('Quit')} utility, exiting...")
        exit()
    else:
        print("Invalid choice, please try again.")
        return

    input("Press return to continue...")


def main_menu():
    print("\n\033[1mMain Menu\033[0m")
    print(f"0. {ftStr('Display')} cache contents")
    print(f"1. {ftStr('Copy')} Ollama data files from internal or external cache")
    print(f"2. {ftStr('Toggle')} Ollama internal/external cache")
    print(f"3. {ftStr('Remove')} from cache")
    print(f"4. {ftStr('Pull')} selected models from Ollama.com")
    print(f"5. {ftStr('Push')} selected models to Ollama.com")
    print(f"Q. {ftStr('Quit')}")
    choice = input("Select: ")
    return choice


def main() -> None:
    models = []
    build_model_list(models)
    choice = None
    while True:
        if choice is None:
            display_welcome()
        choice = main_menu()
        process_choice(choice, models)


if __name__ == "__main__":
    parser = argparse.ArgumentParser("Ollamautil",
                                     description="Command line utility to manage the Ollama cache"
                                     "and make it easier to maintain a larger externally cached "
                                     "database and move models on- and off-device. Assumes Ollama "
                                     "defaults on installation (namely ~/.ollama is default directory) "
                                     "is used.\n\nBefore using this utility, you should configure "
                                     "OLLAMAUTIL_INTERNAL_DIR and OLLAMAUTIL_EXTERNAL_DIR to point "
                                     "to the \033[1mmodels/\033[0m directory in your internal and "
                                     "external caches, respectively.]]")
    # define the default source directories (no training delimiter)
    # points to path of internal "modules" directory
    global ollama_int_dir
    ollama_int_dir = os.getenv("OLLAMAUTIL_INTERNAL_DIR")
    # points to path of external "modules" directory
    global ollama_ext_dir
    ollama_ext_dir = os.getenv("OLLAMAUTIL_EXTERNAL_DIR")
    global valid_caches
    valid_caches = [
        ('internal', ollama_int_dir),
        ('external', ollama_ext_dir)
    ]
    # Note that this should be set as '["val1" "val2"]' in the environment global other this won't load properly
    try:
        global ollama_file_ignore
        ollama_file_ignore = ast.literal_eval(os.getenv("OLLAMAUTIL_FILE_IGNORE"))
    except OSError:
        print("\033[1mOLLAMAUTIL_FILE_IGNORE not set, using defaults.\033[0m")
        ollama_file_ignore = ['.DS_Store']
    if not ollama_ext_dir or not ollama_int_dir or not ollama_file_ignore:
        print(("Warning: environment variables not configured correctly",
               f"OLLAMAUTIL_INTERNAL_DIR: {ollama_int_dir}",
               f"OLLAMAUTIL_EXTERNAL_DIR: {ollama_ext_dir}",
               f"OLLAMAUTIL_FILE_IGNORE: {ollama_file_ignore} (optional)"
               "Please configure these before using this utility."))
        raise RuntimeError.add_note(note="Environment variables not configured correctly. Unable to run utility.")
    FILE_LIST_IGNORE = ollama_file_ignore

    main()
