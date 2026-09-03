
from django.utils.html import format_html


def get_thumbnail_url(image, size=(0, 150), crop=False, upscale=False):
    """Safely retrieves or generates an aspect-ratio-preserving thumbnail URL for an image object."""
    if not image:
        return ""
    try:
        if hasattr(image, 'easy_thumbnails_thumbnailer'):
            thumb = image.easy_thumbnails_thumbnailer.get_thumbnail({'size': size, 'crop': crop, 'upscale': upscale})
            return thumb.url if thumb else getattr(image, 'url', '')
        if hasattr(image, 'file') and hasattr(image.file, 'get_thumbnail'):
            thumb = image.file.get_thumbnail({'size': size, 'crop': crop, 'upscale': upscale})
            return thumb.url if thumb else getattr(image, 'url', '')
        if hasattr(image, 'url'):
            return image.url
    except Exception:
        if hasattr(image, 'url'):
            try:
                return image.url
            except Exception:
                pass
    if isinstance(image, str):
        return image
    return ""


def render_image_markup(url, model_label, object_id, field_name, max_height, label="", thumb_url=None):
    """Shared utility for rendering the standard image markup with menu triggers."""
    display_src = thumb_url or url
    if display_src:
        inner_html = format_html(
            '<img src="{0}" style="max-height: {1}px;" loading="lazy" '
            'class="cursor-pointer rounded-md border border-gray-200 dark:border-gray-700 shadow-sm max-w-full h-auto block transition-all hover:ring-2 hover:ring-primary-500/50" '
            'alt="{2}" />',
            display_src, max_height, label
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
