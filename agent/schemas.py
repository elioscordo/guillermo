from pydantic import BaseModel
from typing import List, Optional


class SyncReport(dict):
    """
    Standard dictionary report recording created/edited state and fields
    for synchronized Django model instances.
    """
    def __init__(self, name, instance, created, edited, fields_edited):
        super().__init__({
            'name': name,
            'instance': instance,
            'created': created,
            'edited': edited,
            'fields_edited': fields_edited
        })
        self.name = name
        self.instance = instance
        self.created = created
        self.edited = edited
        self.fields_edited = fields_edited


def get_asset_sync_info(instance, created):
    """
    Computes diff changes against model history to construct a SyncReport.
    """
    fields_edited = []
    if not created and hasattr(instance, 'history'):
        try:
            latest = instance.history.first()
            if latest:
                prev = latest.prev_record
                if prev:
                    delta = latest.diff_against(prev)
                    fields_edited = [change.field for change in delta.changes]
        except Exception:
            pass

    return SyncReport(
        name=getattr(instance, 'name', getattr(instance, 'symbol', str(instance))),
        instance=instance,
        created=created,
        edited=not created and len(fields_edited) > 0,
        fields_edited=fields_edited
    )


class OutputWithMessageSchema(BaseModel):
    message: str
    output: str

    def sync_model(self, source):
        return dict(self)

    def get_output(self):
        return self.output


class CreateInstructionsSchema(OutputWithMessageSchema):
    def sync_model(self, source):
        from agent.models import Prompt
        Prompt.objects.update_or_create(
            name="Prompt Automatically Created",
            defaults={
                'prompt': self.output,
            }
        )
        return dict(self)
