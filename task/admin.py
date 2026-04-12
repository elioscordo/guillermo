from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Task, TaskPreset
from django.utils.safestring import mark_safe
from django.template.loader import render_to_string

@admin.register(Task)
class TaskAdmin(ModelAdmin):
    list_display = ('id', 'created', 'modified',
                    'task_type', 'html_status', 'last_logs'
                    )
    list_filter = ('task_type', 'status', 'created', 'modified')
    actions = [
        'reprocess'
    ]

    def last_logs(self, obj):
        out = '--'
        logs = obj.tasklog_set.all()
        if logs.count() > 0:
            out = logs.last().text
        return out

    def reprocess(self, request, queryset):
        for item in queryset:
            msg = f"The task {item.id} has been queued for reprocessing"
            item.process()
            self.message_user(
                request,
                msg
            )
    reprocess.short_description = "Retry"


@admin.register(TaskPreset)
class TaskPresetAdmin(ModelAdmin):
    list_display = (
        'id', 'name', 'preset_type',
        'description', 'preset', 'system_default'
    )
    list_editable = ('name', 'description', 'preset_type', 'system_default')

