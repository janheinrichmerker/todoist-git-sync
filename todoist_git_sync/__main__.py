from datetime import datetime, timedelta
from itertools import groupby
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional

from git import Repo, PushInfo
from ratelimit import rate_limited, sleep_and_retry
from requests import Session
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError
from todoist_api_python.api import TodoistAPI
from tqdm import tqdm
from urllib3 import Retry
from yaml import safe_load

from todoist_git_sync.model import TaskInfo

CONFIG_FILE = Path(__file__).parent.parent / "config.yaml"


def sync(
        todoist_token: str,
        todoist_project_id: str,
        git_repository_url: str,
        git_name: str,
        git_email: str,
        export_path: str,
        commit_message: str,
) -> None:
    session = Session()
    retries = Retry(
        total=10,
        backoff_factor=1,
        status_forcelist=[502, 503, 504],
    )
    # noinspection HttpUrlsUsage
    session.mount("http://", HTTPAdapter(max_retries=retries))
    session.mount("https://", HTTPAdapter(max_retries=retries))

    with TemporaryDirectory() as temp_dir:
        git_repository_path = Path(temp_dir)
        git_repository = Repo.clone_from(
            git_repository_url,
            git_repository_path,
            multi_options=["--depth", "1"]
        )
        with git_repository.config_writer() as git_config:
            git_config.set_value("user", "name", git_name)
            git_config.set_value("user", "email", git_email)

        git_export_path = git_repository_path / export_path

        todoist_api = TodoistAPI(todoist_token, session)

        project = todoist_api.get_project(todoist_project_id)
        open_tasks = [
            TaskInfo.from_task(task)
            for task in todoist_api.get_tasks(project_id=todoist_project_id)
        ]

        completed_tasks_legacy = session.post(
            "https://api.todoist.com/sync/v9/completed/get_all",
            headers={"Authorization": f"Bearer {todoist_token}"},
            data={
                "project_id": todoist_project_id,
            }
        ).json()["items"]
        completed_tasks_legacy = sorted(
            completed_tasks_legacy,
            key=lambda task: datetime.fromisoformat(
                task["completed_at"].removesuffix("Z")
            )
        )
        completed_tasks_legacy = tqdm(
            completed_tasks_legacy,
            desc="Load completed tasks",
            unit="task",
        )

        @sleep_and_retry
        @rate_limited(calls=15, period=10)
        def get_task_info(task_id: str) -> Optional[TaskInfo]:
            try:
                task = todoist_api.get_task(task_id)
            except HTTPError as e:
                if e.response.status_code != 404:
                    raise e
                return None
            return TaskInfo.from_task(task)

        completed_tasks = (
            get_task_info(task_legacy["task_id"])
            for task_legacy in completed_tasks_legacy
        )
        completed_tasks = [
            task for task in completed_tasks if task is not None
        ]

        backlog_tasks = [
            task
            for task in open_tasks
            if task.due_at is None
        ]
        scheduled_tasks = [
            task
            for task in open_tasks
            if task.due_at is not None
        ]
        scheduled_week_tasks = {
            week: list(tasks)
            for week, tasks in groupby(
                scheduled_tasks,
                key=lambda task: int(task.due_at.strftime("%W"))
            )
        }
        current_week = int(datetime.now().strftime("%W"))
        future_week_tasks = {
            week: tasks
            for week, tasks in scheduled_week_tasks.items()
            if week >= current_week
        }
        overdue_week_tasks = {
            week: tasks
            for week, tasks in scheduled_week_tasks.items()
            if week < current_week
        }

        with git_export_path.open("w") as file:
            file.write("# Roadmap\n\n")
            file.write(
                f"Tasks automatically exported from "
                f"Todoist project [{project.name}]({project.url}).\n\n"
                f"Jump to [future tasks](#future-tasks) "
                f"or to the [backlog](#backlog).\n\n"
            )
            file.write("## Completed tasks\n\n")
            file.write(
                "<details>\n<summary>Show completed tasks</summary>\n\n")
            for task in completed_tasks:
                file.write(task.to_markdown())
            file.write("\n")
            file.write("</details>\n\n")
            file.write("## Overdue tasks\n\n")
            for week, overdue_tasks in overdue_week_tasks.items():
                week_date = overdue_tasks[0].due_at
                start = week_date - timedelta(days=week_date.weekday())
                end = start + timedelta(days=6)
                file.write(
                    f"### From {start.strftime('%Y/%m/%d')} "
                    f"to {end.strftime('%Y/%m/%d')}\n\n"
                )
                for task in overdue_tasks:
                    file.write(task.to_markdown())
                file.write("\n")
            file.write("## Future tasks\n\n")
            for week, future_tasks in future_week_tasks.items():
                week_date = future_tasks[0].due_at
                start = week_date - timedelta(days=week_date.weekday())
                end = start + timedelta(days=6)
                file.write(
                    f"### From {start.strftime('%Y/%m/%d')} "
                    f"to {end.strftime('%Y/%m/%d')}\n\n"
                )
                for task in future_tasks:
                    file.write(task.to_markdown())
                file.write("\n")
            file.write("## Backlog\n\n")
            for task in backlog_tasks:
                file.write(task.to_markdown())

            file.write("\n\n")
            for task in [*completed_tasks, *open_tasks]:
                file.write(task.to_markdown_ref())

        if not git_repository.is_dirty(untracked_files=True):
            return

        git_repository.index.add([
            git_export_path.relative_to(git_repository_path)
        ])
        git_repository.index.commit(commit_message)
        git_push_info: PushInfo = git_repository.remotes.origin.push()[0]
        assert git_push_info.flags == PushInfo.FAST_FORWARD


def main() -> None:
    with CONFIG_FILE.open("r") as file:
        config = safe_load(file)
    todoist_token = config["todoistToken"]
    todoist_project_id = config["todoistProjectId"]
    git_repository_url = config["gitRepositoryUrl"]
    git_name = config["gitName"]
    git_email = config["gitEmail"]
    export_path = config["exportPath"]
    commit_message = config["commitMessage"]
    sync(
        todoist_token,
        todoist_project_id,
        git_repository_url,
        git_name,
        git_email,
        export_path,
        commit_message,
    )


if __name__ == "__main__":
    main()
