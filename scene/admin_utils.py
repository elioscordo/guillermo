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
    
    def ajax_update_view(self, request, object_id):
        # Implementation of the view logic from step 1
        # Use 'self' instead of passing model_admin
        obj = get_object_or_404(self.model, pk=object_id)
        if request.POST.get('prompt') is not None:
            obj.prompt = request.POST.get('prompt')
            obj.save()
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_IMAGE, owner=request.user) is None:
                obj.generate_image(user=request.user)
        elif request.POST.get('prompt_refine') is not None:
            obj.prompt_refine = request.POST.get('prompt_refine')
            obj.save()
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_REFINE_IMAGE, owner=request.user) is None:
                obj.refine_image(user=request.user)
        elif request.POST.get('prompt_comic') is not None:
            obj.prompt_comic = request.POST.get('prompt_comic')
            obj.save()
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_COMIC, owner=request.user) is None:
                obj.generate_comic(user=request.user)
        elif request.POST.get('prompt_video') is not None:
            obj.prompt_video = request.POST.get('prompt_video')
            obj.save()
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_VIDEO, owner=request.user) is None:
                obj.generate_video(obj.PRESET_VIDEO, user=request.user)
        elif request.POST.get('prompt_voice') is not None:
            obj.prompt_voice = request.POST.get('prompt_voice')
            obj.save()
            if Task.createTaskIfQueueEnabled( obj, settings.TASK_TYPE_GENERATE_VOICE, owner=request.user) is None:
                obj.generate_voice(obj.PRESET_VOICE, user=request.user)
        return JsonResponse({'status': 'success'})

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
                    count = linked_object.count()
                    model = linked_object.model

                    if not model:
                        return f"View ({count})"

                    link_field = next((f.name for f in model._meta.get_fields()
                                     if f.is_relation and f.related_model == obj._meta.concrete_model), None)

                    if not link_field:
                        return f"View ({count})"

                    url = reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist")
                    return format_html(
                        '<a href="{0}?{1}__id__exact={2}" class="text-primary-600 font-medium hover:underline">{3}</a>',
                        url, link_field, obj.pk, count
                    )
                else:
                    # This is a single instance (e.g., a ForeignKey)
                    model = linked_object._meta.model
                    url = reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_change", args=[linked_object.pk])
                    url = reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist")
                    return format_html('<a href="{0}?id__exact={1}" class="text-primary-600 font-medium hover:underline">{2}</a>', url, linked_object.pk, str(linked_object))

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