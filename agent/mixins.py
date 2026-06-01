from django.contrib import admin

class AdminActionsMixin:
    @admin.action(description="Clone selected items")
    def clone(self, request, queryset):
        for obj in queryset:
            if hasattr(obj, 'name') and obj.name:
                obj.name = f"{obj.name} (Clone)"
            obj.save()
            
        self.message_user(request, "Selected items have been cloned.")