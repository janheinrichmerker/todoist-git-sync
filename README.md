[![CI](https://img.shields.io/github/workflow/status/heinrichreimer/todoist-git-sync/Export%20roadmap?label=export&style=flat-square)](https://github.com/heinrichreimer/todoist-git-sync/actions/workflows/export.yml)
[![Issues](https://img.shields.io/github/issues/heinrichreimer/todoist-git-sync?style=flat-square)](https://github.com/heinrichreimer/todoist-git-sync/issues)
[![Commit activity](https://img.shields.io/github/commit-activity/m/heinrichreimer/todoist-git-sync?style=flat-square)](https://github.com/heinrichreimer/todoist-git-sync/commits)
[![License](https://img.shields.io/github/license/heinrichreimer/todoist-git-sync?style=flat-square)](LICENSE)

# ✅ todoist-git-sync

Simple CLI to sync a project's Todoist tasks to a Git repository.

## Usage

1. Get a Todoist API token from the [integration settings](https://todoist.com/app/settings/integrations).
2. Open [Todoist](https://todoist.com/app/), navigate to the desired project, and determine the project ID from the browser adress bar: `https://todoist.com/app/project/<PROJECT_ID>`
3. Prepare a `config.yaml` like this:
    ```yaml
    gitRepositoryUrl: git@git.example.com:doe/example.git
    gitName: John Doe
    gitEmail: doe@example.com
    todoistToken: 1234556789abcdef0123456789abcdef01234567
    todoistProjectId: 1234567890
    exportPath: roadmap.md
    commitMessage: "Update roadmap"
    ```
4. Install [Python 3](https://python.org/downloads/), [pipx](https://pipxproject.github.io/pipx/installation/#install-pipx), and [Pipenv](https://pipenv.pypa.io/en/latest/install/#isolated-installation-of-pipenv-with-pipx).
5. Run `pipenv install`
5. Run `pipenv run python -m todoist_git_sync`.
