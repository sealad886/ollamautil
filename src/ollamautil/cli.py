from __future__ import annotations

import argparse
import json
import sys

from prettytable import PrettyTable

from .ollamautil import (
    OllamaUtilError,
    build_ext_int_comb_filelist,
    cache_statuses,
    display_models_table,
    get_curnow_cache,
    load_config,
    migrate_cache_user,
    pull_models,
    push_models,
    remove_from_cache,
    toggle_int_ext_cache,
    _toggle_cache,
)
from .utils import ftStr


def main_menu() -> str:
    print("\n\033[1mMain Menu\033[0m")
    print(f"1. {ftStr('Copy')} Ollama data files from internal or external cache")
    print(f"2. {ftStr('Toggle')} Ollama internal/external cache")
    print(f"3. {ftStr('Remove')} from cache")
    print(f"4. {ftStr('Pull')} selected models from Ollama.com")
    print(f"5. {ftStr('Push')} selected models to Ollama.com")
    print(f"Q. {ftStr('Quit')}")
    try:
        return input("Select: ")
    except EOFError:
        return "q"


def process_choice(choice: str, combined: list[list], models_table: PrettyTable | None = None) -> bool:
    choice = choice.lower()
    if choice in ["1", "c", "copy"]:
        print(f"{ftStr('Copy')} cache: migrate files between internal and external cache folders.")
        migrate_cache_user(models_table, combined)
    elif choice in ["2", "t", "toggle"]:
        print(f"{ftStr('Toggle')} Ollama internal/external cache.")
        toggle_int_ext_cache(combined=combined, table=models_table)
    elif choice in ["3", "r", "remove"]:
        print(f"{ftStr('Remove')} from cache.")
        remove_from_cache(combined, models_table)
    elif choice in ["4", "p", "pull"]:
        print(f"{ftStr('Pull')} selected models from Ollama.com.")
        pull_models(combined, models_table)
    elif choice in ["5", "u", "push"]:
        print(f"{ftStr('Push')} selected models to Ollama.com.")
        push_models(combined, models_table)
    elif choice in ["q", "quit"]:
        print(f"{ftStr('Quit')} utility, exiting...")
        return False
    else:
        print("Invalid choice, please try again.")
    return True


def run_menu() -> int:
    config = load_config()
    while True:
        _, _, combined = build_ext_int_comb_filelist(config)
        models_table = display_models_table(combined, config=config)
        if not process_choice(main_menu(), combined, models_table=models_table):
            return 0


def run_doctor(args: argparse.Namespace) -> int:
    config = load_config()
    statuses = cache_statuses(config)
    payload = {
        "caches": {
            name: {
                "path": str(status.path),
                "available": status.available,
                "error": status.error,
            }
            for name, status in statuses.items()
        },
        "models_link": str(config.models_link),
        "current_cache": get_curnow_cache(config),
        "file_ignore": list(config.file_ignore),
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")
    return 0


def run_list(args: argparse.Namespace) -> int:
    config = load_config()
    statuses = cache_statuses(config)
    external, internal, combined = build_ext_int_comb_filelist(config)
    if args.json:
        print(
            json.dumps(
                {
                    "external": external,
                    "internal": internal,
                    "current_cache": get_curnow_cache(config),
                    "caches": {
                        name: {
                            "path": str(status.path),
                            "available": status.available,
                            "error": status.error,
                        }
                        for name, status in statuses.items()
                    },
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        display_models_table(combined, config=config)
    return 0


def run_toggle(args: argparse.Namespace) -> int:
    _toggle_cache(args.to, config=load_config())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ollamautil")
    subparsers = parser.add_subparsers(dest="command")

    doctor = subparsers.add_parser("doctor", help="Validate configuration and cache pointers.")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=run_doctor)

    list_cmd = subparsers.add_parser("list", help="List manifests in configured caches.")
    list_cmd.add_argument("--json", action="store_true")
    list_cmd.set_defaults(func=run_list)

    toggle = subparsers.add_parser("toggle", help="Atomically point ~/.ollama/models at a cache.")
    toggle.add_argument("--to", choices=["internal", "external"], required=True)
    toggle.set_defaults(func=run_toggle)

    menu = subparsers.add_parser("menu", help="Open interactive menu.")
    menu.set_defaults(func=lambda _args: run_menu())
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        return run_menu()
    try:
        return args.func(args)
    except OllamaUtilError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
