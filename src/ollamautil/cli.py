import argparse
from prettytable import PrettyTable
from .utils import ftStr
from .ollamautil import build_ext_int_comb_filelist, display_models_table, migrate_cache_user, toggle_int_ext_cache, remove_from_cache, pull_models, push_models
import os
import ast

def main_menu():
    print("\n\033[1mMain Menu\033[0m")
    print(f"1. {ftStr('Copy')} Ollama data files from internal or external cache")
    print(f"2. {ftStr('Toggle')} Ollama internal/external cache")
    print(f"3. {ftStr('Remove')} from cache")
    print(f"4. {ftStr('Pull')} selected models from Ollama.com")
    print(f"Q. {ftStr('Quit')}")
    choice = input("Select: ")
    return choice

def process_choice(choice: str, combined, models_table: PrettyTable|None = None):
    choice = choice.lower()
    if choice in ['1', 'c', 'copy']:
        print(f"{ftStr('Copy')} cache: migrate files between internal and external cache folders.")
        migrate_cache_user(models_table, combined)
    elif choice in ['2', 't', 'toggle']:
        print(f"{ftStr('Toggle')} Ollama Int/Ext Cache: Swtich between internal and external cache folders.")
        toggle_int_ext_cache(combined=combined, table=models_table)
    elif choice in ['3', 'r', 'remove']:
        print(f"{ftStr('Remove')} from cache: remove one or more model/tag from internal or external cache.")
        remove_from_cache(combined, models_table)
    elif choice in ['4', 'p', 'pull']:
        print(f"{ftStr('Pull')} selected models from Ollama.com, will not pull files if they already exist. Useful to repair cache that has missing files.")
        pull_models(combined, models_table)
    elif choice in [5, 'u', 'push']:
        print(f"ftStr('Push',1) selected models to Ollama.com.")
        push_models(combined, models_table)
    elif choice in ['Q', 'q', 'quit']:
        print(f"{ftStr('Quit')} utility, exiting...")
        exit()
    else:
        print("Invalid choice, please try again.")

def main() -> None:
    '''
    Display main menu and basic high-level handling.
    '''
    # Set up environment variables
    ollama_int_dir = os.getenv("OLLAMAUTIL_INTERNAL_DIR")
    ollama_ext_dir = os.getenv("OLLAMAUTIL_EXTERNAL_DIR")
    try:
        ollama_file_ignore = ast.literal_eval(os.getenv("OLLAMAUTIL_FILE_IGNORE", "['.DS_Store']"))
    except:
        print("\033[1mOLLAMAUTIL_FILE_IGNORE not set, using defaults.\033[0m")
        ollama_file_ignore = ['.DS_Store']

    if not ollama_ext_dir or not ollama_int_dir:
        print("Warning: Required environment variables not configured:")
        print(f"OLLAMAUTIL_INTERNAL_DIR: {ollama_int_dir}")
        print(f"OLLAMAUTIL_EXTERNAL_DIR: {ollama_ext_dir}")
        raise SystemExit("Environment variables not configured correctly. Unable to run utility.")

    # Assuming 'combined' is your list of models and weights
    while True:
        # re-build the table every time you return to the main menu
        _, _, combined = build_ext_int_comb_filelist()
        models_table = display_models_table(combined)
        choice = main_menu()
        process_choice(choice, combined, models_table=models_table)

if __name__ == "__main__":
    main()
