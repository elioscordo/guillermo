from typing import Any
from django.utils.safestring import mark_safe
import markdown
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html, strip_tags
from django.urls import reverse

from django.contrib.admin.utils import label_for_field, lookup_field
from django.db.models import Model
from django.http import HttpRequest
from django.template.loader import render_to_string

from unfold.utils import display_for_field
from unfold.sections import BaseSection, TemplateSection

from scene.models import Author

class TableSection(BaseSection):
    fields = []
    related_name = None
    verbose_name = None
    height = None
    template_name ="sections/base.html"

    def context_data(self) -> dict:
        return {}
    
    def render(self) -> str:
        if self.related_name is None:
            raise ValueError("TableSection must have a related_name")

        results = getattr(self.instance, self.related_name)
        headers = []
        rows = []

        for field_name in self.fields:
            if hasattr(self, field_name):
                if hasattr(getattr(self, field_name), "short_description"):
                    headers.append(getattr(self, field_name).short_description)
                else:
                    headers.append(field_name)
            else:
                headers.append(label_for_field(field_name, results.model))

        for result in results.all():
            row = []

            for field_name in self.fields:
                if hasattr(self, field_name):
                    row.append(getattr(self, field_name)(result))
                else:
                    field, attr, value = lookup_field(field_name, result)
                    row.append(display_for_field(value, field, "-"))

            rows.append(row)

        context = {
            "request": self.request,
            "table": {
                "headers": headers,
                "rows": rows,
            },
        }
        context.update(self.context_data())
        if hasattr(self, "verbose_name") and self.verbose_name:
            context["title"] = self.verbose_name

        if hasattr(self, "height") and self.height:
            context["height"] = self.height

        return render_to_string(
            self.template_name,
            context=context,
        )

class AuthorSection(TableSection):
    model = Author
    NO_USER_LABEL = _("Use Create User Action")
    verbose_name = _("Authors")
    
    fields = ['name', 'scenes', 'nudges']
    extra = 0
    show_count = True  # This will run `count()`
    collapsible = True
    related_name = 'authors'
    
    def name(self, obj):
        return f"{obj.user.username if obj.user else obj.email}"

    def context_data(self) -> dict:
        return {"description": _("Manage authors within the story edit page. If you add emails, guillermo will send an invitation by email.")}

    def scenes(self, obj):
        turn_type = 'scene'
        turn_link = self.NO_USER_LABEL
        if obj.user:
            turn_link = format_html("<a href='/admin/scene/scene/?story__id__exact={0}&author__id__exact={1}' class='text-primary-600 font-medium hover:text-primary-500 dark:text-primary-400 dark:hover:text-primary-300'>{2}</a>", obj.story.id, obj.id, obj.scenes.filter(author=obj).count())
            if (obj.user == self.request.user):
                add_link = format_html("<a href='/admin/scene/scene/add/?story={0}&author={1}' class='text-primary-600 font-medium hover:text-primary-500 dark:text-primary-400 dark:hover:text-primary-300 ml-1'>[+]</a>", obj.story.id, obj.id)
                turn_link = format_html("{} {}", turn_link, add_link)
        return mark_safe(turn_link)
    
    def nudges(self, obj):
        nudge_link = self.NO_USER_LABEL
        if obj.user:
            nudge_count = obj.user.received_nudges.count()
            nudge_link = format_html("<a href='/admin/scene/nudge/?receiver__id__exact={0}' class='text-primary-600 font-medium hover:text-primary-500 dark:text-primary-400 dark:hover:text-primary-300'>{1}</a>", obj.user.id, nudge_count) 
            if (obj.user != self.request.user):
                add_link = format_html("<a href='/admin/scene/nudge/add/?receiver={0}&story={1}&sender={2}' class='text-primary-600 font-medium hover:text-primary-500 dark:text-primary-400 dark:hover:text-primary-300 ml-1'>-></a>", obj.user.id, obj.story.id, self.request.user.id)
                nudge_link = format_html("{} {}", nudge_link, add_link)
        return mark_safe(nudge_link)
    


class ThemeSection(TemplateSection):
    template_name ="sections/prompt.html"
    
    def get_context_data(self, request, instance) -> dict[str, Any]:
        return {
            "item" : instance.theme,
            "request": request,
        }


class SceneSection(TableSection):
    template_name ="sections/story_scene.html"

    def context_data(self) -> dict:
        return {
            "story": self.instance,
            "author": self.request.user.authors.filter(story=self.instance).first()
        }

    def prompt(self, obj):
        if obj.prompt:
            return mark_safe(f"<div class='markdown'>{markdown.markdown(obj.prompt)}</div>")
        return _("No Prompt")
        
    def get_name(self, obj):
        url = "/admin/scene/scene/?id__exact={0}".format(obj.id)
        return format_html(
            '<a href="{}" class="text-primary-600 font-medium hover:text-primary-500 dark:text-primary-400 dark:hover:text-primary-300">{}</a>',
            url,
            obj.name if obj.name else _("Scene {pk}").format(pk=obj.pk)
        )
    get_name.short_description = _("Name")

    fields = ['prompt', 'get_name', 'author', "items"]
    extra = 0
    show_count = True  # This will run `count()`
    collapsible = False
    related_name = 'scenes'


class SceneBaseCardsSection(TemplateSection):
    template_name = "sections/scene_cards.html"
    key = None
    title = None

    def get_context_data(self, request, instance):
        return {
            "title": self.title,
            "items": self.get_items(instance),
            "instance": instance,
            "section_key": self.key
        }

class SceneCharactersSection(SceneBaseCardsSection):
    key = 'characters'
    title = _("Characters")

    def get_items(self, instance):
        return instance.get_cast()


class SceneLocationsSection(SceneBaseCardsSection):
    key = 'locations'
    title = _("Locations")
    
    def get_items(self, instance):
        return instance.get_locations()


class ScenePropsSection(SceneBaseCardsSection):
    key = 'props'
    title = _("Props")

    def get_items(self, instance):
        return instance.get_props()
