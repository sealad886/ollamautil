# OllamaUtil

Additional utilities to work with and manage the Ollama CLI, in particular managing the 
cache when on-device storage is at a premium.

## Description

OllamaUtil adds some cool functionlaity that adds the ability to migrate your cache off of your 
main storage disk, while still easily syncing models between internal and external storage
without having to download them again from the repo.

Whenever the cache or a part of it is migrated, the sha256 checksum is calculated on the target data
(i.e. after copy) and the utility will not continue until the user decides to keep or 
delete the corrupted data. 

## Before you start

This technique relies on creating a symlink at `$HOME/.ollama/models` that can toggle between
your internal and external caches. Make sure you're okay with that.

## Getting Started

A note that this is all very much so under development. Furhter instructions for how to 
install and configure environments and what to install will be forthcoming in future versions. 

### Dependencies

Describe any prerequisites, libraries, OS version, etc., needed before installing program.
* Install Ollama [Ollama.com](https://ollama.com/download) or on [GitHub](https://github.com/ollama/ollama)

Stop any active Ollama processes currently running. 

To start, move your current cache to a new directory, then symlink to the new location, as in this example:
```bash
mv $HOME/.ollama/models $HOME/ollama_internal/models/
ln -s -F $HOME/ollama_internal/models $HOME/.ollama/
```

### Installing

In your base environment, or in the environment of your choosing, install a couple of basic reqs:
```bash
pip install -U tqdm prettytable typing git
```

Decide where you'll download this script. It should be a unique folder for this repo. 
```bash
mkdir -p path/to/parent/repo/
cd path/to/parent/repo
git clone https://github.com/sealad886/ollama_util.git .
```

To be able to run this at the command line like any other utility, create an alias. Note that I am using
`python3` as my invoking command, but yours might allow `python` or some other variation.
```
alias ollamautil="python3 /path/to/repo/ollamautil.py"
```
HINT: add this to your BASH, zsh, or other shell startup files so this happens automagically.
On MacOS Catalina and later, zsh is the default. [more info](https://wiki.archlinux.org/title/zsh#)

### Executing program

BEFORE running this utility, ensure that you're ready to start messing around with your cache. It is not for the 
faint of heart, and it may lead to file instability, unexpected behaviors, file corruption, etc. 

I will re-iterate: this utility is released as-is, and I do not work for or develop for Ollama. 

The Ollama cache, briefly, looks like this if you use the defaults during setup:
in the home directory:
```bash
.ollama
|--models
    |--blobs
        -- <blobs>
        ...
    |--manifests
        |--registry.ollama.ai
            |--library
                |--modelA
                    --variant1
                    --variant2
                    --latest
                |--modelB
                    --latest
```
Add the following to your shell startup scripts, and point them to the "models" directory:
```bash
export OLLAMAUTIL_INTERNAL_DIR="<path to internal (on-disk) cache>"
export OLLAMAUTIL_EXTERNAL_DIR="<path to external (removable drive) cache>"
export OLLAMAUTIL_FILE_IGNORE='["complete file name" "complete file name" "complete file name"]' 
```
For MacOS, the recommendation is to set `OLLAMAUTIL_FILE_IGNORE` as follows:
```bash
export OLLAMAUTIL_FILE_IGNORE='[".DS_Store"]'
```
Pay close attention to the single- and double-quotes when configuring this or it will break. 

## Help

* When setting up the environment variables: Pay close attention to the single- and double-quotes when configuring this or it will break. 

## TODO

1. Check if Ollama models are running / active before allowing any part of the utility to run.
1. Finish the remove_from_cache() method.
    1. This is different from the `ollama rm` tool because it will enable you to remove from either the internal or external cache without having to switch over. 
1. Develop wrapper function for other commands in `ollama` CLI (e.g. enable `ollama pull` to store to either cache)
1. Eventually, maybe even have so much wrapper around this that ollama wouldn't know which cache you used for which models. The user could be presented with all models in the internal/external cache, and then the invoking method could figure out how to handle the symlinks. 
    1. Only potential issue here would be that you could only have one model running at any given time. 
1. Tab-completion in zsh.

## Authors

Contributors names and contact info

* Andrew M. Cox
    * email: acox.dev@icloud.com
    * GitHub: [github.com/sealad886](https://github.com/sealad886)

## Version History

* 0.1
    * Initial Release

## License

   Copyright 2024 Andrew M. Cox

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       [http://www.apache.org/licenses/LICENSE-2.0]

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

## Acknowledgments

I will note that portions of this code were analyzed and edits suggested by various LLMs, including:
* OpenAI ChatGPT-4
* wizardcoder (7B and 34B-Python models)
* Mystral 