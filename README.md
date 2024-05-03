# OllamaUtil

Additional utilities to work with and manage the Ollama CLI, in particular managing the 
cache when on-device storage is at a premium.

## Description

The Ollama Utility is a command-line tool designed to manage the Ollama cache and facilitate the maintenance of a larger externally cached database. It provides features to copy files between internal and external caches, toggle between internal and external caches, remove models from the cache, and pull selected models from Ollama.com.

## Disclaimer

I do not claim to be employed by, associated with, or otherwise endorsed by Ollama, Inc. or any of its affiliates. I am an independent developer who has created this tool as a convenience for my own use.

## Before you start

The utility relies on creating a symlink at `$HOME/.ollama/models` that will then toggle between
your internal and external caches. Make sure you're okay with that.

Move/copy your entire cache to another directory:
```
mkdir -p ${HOME}/ollama_internal/models
cp -r ${HOME}/.ollama/models/ ${HOME}/ollama_internal/models/
# run the below command to then remove the previous Ollama cache directory:
# rm -rf ${HOME}/.ollama/models
```

Create a symlink to your external cache:
```
ln -s ${HOME}/ollama_internal/models ${HOME}/.ollama/models
```

### Mac vs Windows vs Linux

I have only tested this on MacOS Sonoma 14.4+. It should reasonably work on any POSIX system. 

Symlinks are not available on Windows, so the utility is not recommedned on Windows.

### Installing

Clone this repository:
```
git clone https://github.com/sealad886/ollama-util.git
cd /path/to/ollama-util
pip install -U -r requirements.txt
```
Note: it is highly recommended that you create a virtual environment that is stable for this utility. For example:
```
python -m venv ollama-util
source ollama-util/bin/activate
pip install -U -r requirements.txt
```

### Required Configuration
Before using this utility, you need to configure the following environment variables:

* `OLLAMAUTIL_INTERNAL_DIR`: points to the path of the internal "models" directory
* `OLLAMAUTIL_EXTERNAL_DIR`: points to the path of the external "models" directory
* `OLLAMAUTIL_FILE_IGNORE`: (optional) a list of file patterns to ignore (e.g., [".DS_Store"])

For MacOS, the recommendation is to set `OLLAMAUTIL_FILE_IGNORE` as follows:
```bash
export OLLAMAUTIL_FILE_IGNORE='[".DS_Store"]'
```
Pay close attention to the single- and double-quotes when configuring this or it will break. 
This is defaulted in code, but it is not recommended that you rely on this default.

* For `zsh`, add these to your `.zshenv` file. 
* For `bash`, add these to your `.bashrc` file. (I think)
* For `fish`, add these to your `.config/fish/config.fish` file. (I think)

## Features
1. **Copy**: Migrate files between internal and external cache folders.
2. **Toggle**: Switch between internal and external cache folders.
3. **Remove**: Remove one or more models from the internal or external cache.
4. **Pull**: Pull selected models from Ollama.com (in some cases, can help to repair damaged cache).

## Usage
Run the utility by executing `python ollamautil.py` in your terminal/command prompt.
Select a feature from the main menu:
```
1: Copy cache
2: Toggle internal/external cache
3: Remove from cache
4: Pull selected models
5: Push selected models
Q: Quit
```

### Optional steps to make execution easier
If you would prefer to run `ollamautil` from anywhere, I recommend:
1. Update the shebang in the first line of `ollamautil.py` to point to your virtual environment's Python executable. 
2. Rename the file: `cp ollamautil.py ollamautil`
3. Make the file executable: `chmod +x ollamautil`
4. Optional: move this into your PATH so you don't have to remember where it is: `mv ollamautil /usr/local/bin/ollamautil`
This 4th step is the gamechanger in terms of ease-of-use. It makes this utility available from any directory.

## Background on Ollama cache system

Note: I remind people that I am not affiliate with Ollama in any way. What I state here is my own understanding learned from using and manipulating the cache.

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
The `blobs` directory contains all of the model files, organized by model name and variant. The `manifests` directory contains a registry file for each Ollama registry. In this case, there is only one: `registry.ollama.ai`. This file lists all of the models in that registry, along with their variants. The `latest` file in each model directory is a symlink to the latest variant of that model, and running the latest model is the default (i.e. `ollama run codellama` is equivalent to `ollama run codellama:latest`).

## Help

* When setting up the environment variables: Pay close attention to the single- and double-quotes when configuring this or it will break. 

## TODO

1. Check if Ollama models are running / active before allowing any part of the utility to run.
1. Develop wrapper function for other commands in `ollama` API (via `ollama-python`)
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

* Thanks to Ollama for creating a great tool for running LLMs.
* Thanks to the `llama.cpp` project for enabling conversion and quantization of models.
* Thanks to my previous CS professors--apparently I still know a thing or two, or at least pretend to!