from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import groupby
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import indent
from time import sleep
from typing import Optional

from git import Repo, PushInfo
from requests import post
from requests.exceptions import HTTPError
from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Task
from tqdm import tqdm
from yaml import safe_load

CONFIG_FILE = Path(__file__).parent.parent / "config.yaml"


@dataclass(frozen=True)
class TaskInfo:
    id: str
    url: str
    title: str
    description: Optional[str]
    due_at: Optional[datetime]
    is_completed: bool
    priority: int

    @classmethod
    def from_task(
            cls,
            task: Task,
    ) -> "TaskInfo":
        return TaskInfo(
            id=task.id,
            url=task.url,
            title=task.content,
            description=(
                task.description
                if len(task.description) > 0 else None
            ),
            due_at=(
                (
                    datetime.fromisoformat(task.due.datetime.removesuffix("Z"))
                    if task.due.datetime is not None
                    else datetime.fromisoformat(task.due.date)
                )
                if task.due is not None
                else None
            ),
            is_completed=task.is_completed,
            priority=task.priority,
        )

    def to_markdown(self) -> str:
        completed = "x" if self.is_completed else " "
        description = (
            f"  \n{indent(self.description, '    ')}"
            if self.description is not None else ""
        )
        priority = (
            " ❗" if self.priority >= 4 else
            " ❕" if self.priority >= 2 else
            ""
        )
        completed_at = ""
        # completed_at = (
        #     f" (completed {self.completed_at.strftime('%Y/%m/%d')})"
        #     if self.completed_at is not None else ""
        # )
        return f"- [{completed}] {self.title}{priority}{completed_at} " \
               f"[🔗][{self.id}]{description}\n"

    def to_markdown_ref(self) -> str:
        return f"[{self.id}]: {self.url}\n"


def sync(
        todoist_token: str,
        todoist_project_id: str,
        git_repository_url: str,
        git_name: str,
        git_email: str,
        export_path: str,
        commit_message: str,
) -> None:
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

        todoist_api = TodoistAPI(todoist_token)

        project = todoist_api.get_project(todoist_project_id)
        open_tasks = [
            TaskInfo.from_task(task)
            for task in todoist_api.get_tasks(project_id=todoist_project_id)
        ]

        completed_tasks_legacy = post(
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
        completed_tasks = []
        for task_legacy in completed_tasks_legacy:
            try:
                task = todoist_api.get_task(task_legacy["task_id"])
            except HTTPError as e:
                if e.response.status_code != 404:
                    raise e
                continue
            sleep(0.5)
            completed_tasks.append(
                TaskInfo.from_task(
                    task
                )
            )

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
            file.write("<details>\n<summary>Show completed tasks</summary>\n\n")
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
