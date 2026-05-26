from celery import shared_task
from django.conf import settings
from .models import Task
import importlib


@shared_task
def process_task(task_id):
    task = Task.objects.get(id=task_id)
    print(f"Processing task {task.id} ")
    if task.has_pending_previous():
        task.set_status(Task.TASK_STATUS_HOLDING)
    elif task.is_processable():
        delegate = settings.TASK_DELEGATES[task.task_type]
        delegate_package = delegate.rsplit(".", 1)[0]
        delegate_class = delegate.rsplit(".", 1)[1]
        Delegate = getattr(importlib.import_module(delegate_package),delegate_class)
        print(f"Delegate the task to {delegate}")
        delegate = Delegate(task)
        try:
            task.set_status(Task.TASK_STATUS_STARTED)
            delegate.process()
            task.set_status(Task.TASK_STATUS_SUCCESS)
        except Exception as e:
            task.log(str(e))
            task.set_status(Task.TASK_STATUS_ERROR)
        for next_task in task.next_tasks.all():
            if next_task.is_processable() \
                and not next_task.has_pending_previous():
                process_task.delay(next_task.id)
