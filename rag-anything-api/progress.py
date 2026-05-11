"""
上传导入任务的进度追踪模块
提供 task_id → SSE events 的存储与查询
"""

import time
import uuid


class ProgressTracker:
    def __init__(self):
        self._tasks: dict = {}

    def create_task(self, total: int) -> str:
        task_id = str(uuid.uuid4())[:8]
        self._tasks[task_id] = {
            "total": total,
            "completed": 0,
            "failed": 0,
            "events": [],
            "finished": False,
            "created_at": time.time(),
        }
        return task_id

    def emit(self, task_id: str, event_type: str, file_name: str,
             message: str = "", error: str = ""):
        if task_id not in self._tasks:
            return
        event = {
            "type": event_type,
            "file": file_name,
            "message": message,
            "error": error,
            "timestamp": time.time(),
        }
        task = self._tasks[task_id]
        task["events"].append(event)
        if event_type == "done":
            task["completed"] += 1
        elif event_type == "error":
            task["failed"] += 1

    def finalize(self, task_id: str):
        if task_id in self._tasks:
            self._tasks[task_id]["finished"] = True

    def get_events_since(self, task_id: str, index: int):
        task = self._tasks.get(task_id)
        if not task:
            return [], index, True
        events = task["events"][index:]
        return events, index + len(events), task["finished"]

    def get_task(self, task_id: str):
        return self._tasks.get(task_id)


progress_tracker = ProgressTracker()
