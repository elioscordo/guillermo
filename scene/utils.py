
from django.utils.html import format_html


def render_image_markup(url, model_label, object_id, field_name, max_height, label=""):
    """Shared utility for rendering the standard image markup with menu triggers."""
    if url:
        inner_html = format_html(
            '<img src="{0}" style="max-height: {1}px;" '
            'class="cursor-pointer rounded-md border border-gray-200 dark:border-gray-700 shadow-sm max-w-full h-auto block transition-all hover:ring-2 hover:ring-primary-500/50" '
            'alt="{2}" />',
            url, max_height, label
        )
    else:
        # Render a dashed placeholder if no image exists
        size = min(max_height, 60)
        inner_html = format_html(
            '<div style="height: {0}px; width: {0}px;" '
            'class="image-placeholder cursor-pointer rounded-md border-2 border-dashed border-gray-200 dark:border-gray-700 flex items-center justify-center text-gray-400 hover:border-primary-500 hover:text-primary-500 transition-all shadow-sm bg-gray-50 dark:bg-gray-800/50">'
            '<span class="material-symbols-outlined text-[20px]">add_photo_alternate</span>'
            '</div>',
            size
        )

    return format_html(
        '<div class="relative inline-block image-menu-container group" '
        'data-url="{0}" data-model="{1}" data-id="{2}" data-field="{3}">'
        '{4}'
        '</div>',
        url or "", model_label, object_id, field_name, inner_html
    )
