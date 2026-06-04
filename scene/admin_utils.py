import json
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from task.models import Task
from .serializers import get_generic_serializer


class AjaxTaskModelAdmin(ModelAdmin):
    list_refresh = []
    class Media:
        js = ('js/admin_ajax.js',) # We will create this file
        
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'ajax-config/',
                self.admin_site.admin_view(self.ajax_config_view),
                name='action_ajax_config',
            ),
            path(
                'ajax-update/<int:object_id>/',
                self.admin_site.admin_view(self.ajax_update_view),
                name='action_ajax_update',
            ),
            path(
                'ajax-last-tasks/<int:object_id>/',
                self.admin_site.admin_view(self.get_last_tasks),
                name='action_ajax_last_tasks',
            ),
        ]
        return custom_urls + urls

    def ajax_config_view(self, request):
        fields = getattr(self, 'ajax_shift_fields', [])
        return JsonResponse({'ajax_shift_fields': fields})

    def get_last_tasks(self, request, object_id):
        # 1. Get the object
        obj = get_object_or_404(self.model, pk=object_id)
        obj.refresh_from_db()
        last_task = obj.tasks.first()
        status = last_task.status if last_task else None
        serializer_class = get_generic_serializer(self.model)

        refresh_data = {}
        for field_name in getattr(self, "list_refresh", []):
            try:
                # 1. Try Admin method (standard Django Admin behavior)
                if hasattr(self, field_name):
                    attr = getattr(self, field_name)
                    if callable(attr):
                        val = attr(obj)
                    else:
                        val = attr
                # 2. Try Model field/method
                elif hasattr(obj, field_name):
                    attr = getattr(obj, field_name)
                    if callable(attr):
                        val = attr()
                    else:
                        val = attr
                else:
                    continue
                
                refresh_data[field_name] = str(val) if val is not None else ""
            except Exception:
                continue

        response_data = {
            'html': obj.last_tasks(),
            'status': status,#
            'object': serializer_class(obj).data,
            'refresh': refresh_data
        }
        return JsonResponse(response_data)
    
    def save_ajax_fields(self, obj, request):
        """Updates model fields from POST data, handling Booleans and Foreign Keys."""
        for field in obj._meta.fields:
            if field.name in request.POST:
                val = request.POST.get(field.name)
                if val == 'on': val = True
                elif val == 'off': val = False
                
                # Use get_attname to handle ForeignKeys via their ID field (e.g., 'story_id')
                setattr(obj, field.get_attname(), val if val != "" else None)
        obj.save()

    def ajax_update_view(self, request, object_id):
        """Standard entry point for AJAX updates: saves fields then triggers tasks."""
        obj = get_object_or_404(self.model, pk=object_id)
        target_field = request.POST.get('target_field')
        self.save_ajax_fields(obj, request)
        self.trigger_ajax_task(request, obj, target_field)
        return JsonResponse({'status': 'success'})

    def trigger_ajax_task(self, request, obj, target_field):
        """Hook for triggering specific background tasks based on the updated field."""
        if target_field == 'prompt':
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_IMAGE, owner=request.user) is None:
                obj.generate_image(user=request.user)
        elif target_field == 'prompt_refine':
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_REFINE_IMAGE, owner=request.user) is None:
                obj.refine_image(user=request.user)
        elif target_field == 'prompt_comic':
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_COMIC, owner=request.user) is None:
                obj.generate_comic(user=request.user)
        elif target_field == 'prompt_video':
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_VIDEO, owner=request.user) is None:
                obj.generate_video(obj.PRESET_VIDEO, user=request.user)
        elif target_field == 'prompt_voice':
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_VOICE, owner=request.user) is None:
                obj.generate_voice(obj.PRESET_VOICE, user=request.user)

class AdminLinker:
    def __getattr__(self, name):
        if name.startswith("link_"):
            related_field = name[5:]

            def dynamic_link(obj):
                if not hasattr(obj, related_field):
                    return "-"

                linked_object = getattr(obj, related_field)

                if linked_object is None:
                    return "-"

                if hasattr(linked_object, "all"):  # This is a manager (e.g., ManyToMany or reverse ForeignKey)
                    model = linked_object.model
                    count = linked_object.count()

                    link_field = next((f.name for f in model._meta.get_fields()
                                     if f.is_relation and f.related_model == obj._meta.concrete_model), None)

                    if not link_field:
                        return format_html("View ({0})", count)

                    url = reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist")
                    return format_html(
                        '<a href="{0}?{1}__id__exact={2}" class="text-primary-600 font-medium hover:underline">{3}</a>',
                        url, link_field, obj.pk, count or 0
                    )
                else:
                    # This is a single instance (e.g., a ForeignKey)
                    model = linked_object._meta.model
                    url = reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_change", args=[linked_object.pk])
                    return format_html('<a href="{0}" class="text-primary-600 font-medium hover:underline">{1}</a>', url, str(linked_object))

            dynamic_link.short_description = related_field.replace("_", " ").title()
            return dynamic_link

        if name.startswith("image_"):
            related_field = name[6:]

            def dynamic_image(obj):
                if not hasattr(obj, related_field):
                    return "-"

                img = getattr(obj, related_field)
                if callable(img):
                    img = img()

                if not img or not hasattr(img, "url"):
                    return "-"

                return format_html(
                    '<img src="{0}" style="max-height: 80px;" class="rounded-md border border-gray-200 dark:border-gray-700 shadow-sm" />',
                    img.url
                )

            dynamic_image.short_description = related_field.replace("_", " ").title()
            return dynamic_image

        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")