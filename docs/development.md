# Automatic Python formatting

Install the hook once per clone. Python 3.12 with `venv` and network access are required for the tool installation and initial hook environment setup. From the repository root:

```sh
python3.12 -m venv .git/format-tools
PIP_NO_CACHE_DIR=1 .git/format-tools/bin/python -m pip install --no-cache-dir -r ci/requirements-dev.txt
/usr/bin/python3 ci/install_format_hook.py
```

The installer refuses an existing foreign hook or `core.hooksPath`; it does not overwrite either. It supports normal clones with a `.git` directory. The hook uses caches in the clone's Git common directory. The first commit may download hook environments. To prepare them beforehand, run:

```sh
PRE_COMMIT_HOME="$PWD/.git/pre-commit" VIRTUALENV_APP_DATA="$PWD/.git/virtualenv" PIP_CACHE_DIR="$PWD/.git/pip-cache" PIP_NO_CACHE_DIR=1 .git/format-tools/bin/python -m pre_commit install-hooks
```

On each commit, pre-commit runs isort then Black on staged Python files using `pyproject.toml`. If either modifies files, the commit stops: review the changes, stage the intended result explicitly, and commit again. Unstaged changes are temporarily stashed by pre-commit and restored. The hook never stages changes for you. CI remains the independent formatting check.
