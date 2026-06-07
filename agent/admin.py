from django.contrib import admin
from unfold.admin import ModelAdmin
from django.contrib.contenttypes.models import ContentType

from agent.mixins import AdminActionsMixin
from agent.models import AgentModel, Agent, GoogleApiKey, GoogleVoice, Prompt, TokenUsage, AgentProfile, Message
from agent.utils import get_genai_client
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.models import User, Group

from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
from unfold.admin import ModelAdmin

from django.contrib import admin
from unfold.admin import ModelAdmin
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from unfold.contrib.import_export.forms import ExportForm, ImportForm, SelectableFieldsExportForm


admin.site.unregister(User)
admin.site.unregister(Group)

@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    # Forms loaded from `unfold.forms`
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass


@admin.register(ContentType)
class ContentTypeAdmin(ModelAdmin):
    search_fields = ("model", "app_label")


@admin.action(description="List available genai models")
def list_models(modeladmin, request, queryset):
    client = get_genai_client()
    models = client.models.list()
    for model in models:
        if not AgentModel.objects.filter(name=model.name).exists():
            AgentModel.objects.create(name=model.name)
            modeladmin.message_user(request, "Model '{}' created.".format(model.name))

@admin.register(AgentModel)
class AgentModelAdmin(ModelAdmin):
    list_display = ('name', )
    list_display_links = ('name',)
    actions = [list_models]

@admin.register(Prompt)
class PromptAdmin(ModelAdmin):
    list_display = ('id', 'name', 'prompt', 'category')
    list_filter = ('category', 'content_types')
    list_editable = ('name', 'prompt', 'category')
    list_display_links = ('id',)
    autocomplete_fields = ('content_types',)
    search_fields = ("name",)


@admin.register(Agent)
class AgentAdmin(ModelAdmin,):
    list_display = ('name', 'output_type', 'schema')
    list_display_links = ('name',)

class GoogleVoiceResource(resources.ModelResource):
    class Meta:
        model = GoogleVoice
        fields = ('id', 'name', 'description')
        export_order = ('id', 'name', 'description')

class PromptResource(resources.ModelResource):
    class Meta:
        model = Prompt
        fields = ('id', 'name', 'prompt', 'category')
        export_order = ('id', 'name', 'prompt', 'category')

class AgentResource(resources.ModelResource):
    class Meta:
        model = Agent
        fields = ('id', 'name', 'output_type', 'schema')
        export_order = ('id', 'name', 'output_type', 'schema')

@admin.register(GoogleVoice)
class GoogleVoiceAdmin(AdminActionsMixin, ModelAdmin, ImportExportModelAdmin):
    list_display = ('id', 'name', 'description')
    list_display_links = ('name', 'description')
    actions = ['clone']
    import_form_class = ImportForm
    export_form_class = ExportForm
    resource_classes = [GoogleVoiceResource]
    search_fields = ("name",)


@admin.register(GoogleApiKey)
class GoogleApiKeyAdmin(ModelAdmin):
    list_display = ('name', 'user')
    list_display_links = ('name',)
    autocomplete_fields = ['user']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # Users only see themselves
        return qs.filter(id=request.user.id)

    def has_change_permission(self, request, obj=None):
        if not obj:
            return True
        return obj.user == request.user or request.user.is_superuser


@admin.register(AgentProfile)
class AgentProfileAdmin(ModelAdmin):
    list_display = ('user', 'credits')
    list_display_links = ('user',)
    autocomplete_fields = ['user']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # Users only see themselves
        return qs.filter(id=request.user.id)

    def has_change_permission(self, request, obj=None):
        if not obj:
            return True
        return obj.user == request.user or request.user.is_superuser


@admin.register(TokenUsage)
class TokenUsageAdmin(ModelAdmin):
    list_display = ('id', 'user', 'agent', 'tokens', 'preset', 'content_object', 'created')
    list_display_links = ('id',)
    autocomplete_fields = ['user']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # Users only see themselves
        return qs.filter(user=request.user)

@admin.register(Message)
class MessageAdmin(ModelAdmin):
    list_display = ('id', 'content_object', 'agent', 'target_field', 'created_at')
    readonly_fields = ('created_at',)

    def has_change_permission(self, request, obj=None):
        if not obj:
            return True
        return obj.user == request.user or request.user.is_superuser
