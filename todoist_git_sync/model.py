from dataclasses import dataclass
from datetime import datetime
from textwrap import indent
from typing import Optional

from todoist_api_python.models import Task


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
