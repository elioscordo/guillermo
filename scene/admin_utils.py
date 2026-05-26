from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from unfold.admin import ModelAdmin

from task.models import Task
from .serializers import get_generic_serializer


class AjaxTaskModelAdmin(ModelAdmin):
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
        last_task = obj.tasks.first()
        status = last_task.status if last_task else None
        serializer_class = get_generic_serializer(self.model)
        response_data = {
            'html': obj.last_tasks(),
            'status': status,#
            'object': serializer_class(obj).data
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
