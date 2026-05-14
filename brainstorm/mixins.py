from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.auth.models import Group, Permission, User
from django.conf import settings
import secrets
import string

class EmailSenderMixin: 
    
    def send_email(self, subject,  context, recipient_list):
        html_message = render_to_string(self.email_template, context)
        plain_message = strip_tags(html_message)
        send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            recipient_list,
            html_message=html_message
        )

class UserCreatorMixin:
    
    def create_user(self, obj, email):
        username = email.split('@')[0]
        # 1. Generate a secure random string
        alphabet = string.ascii_letters + string.digits
        password = ''.join(secrets.choice(alphabet) for i in range(12))
        user, created = User.objects.get_or_create(username=username, email=email)
        user.set_password(password)
        user.is_staff = True
        group = Group.objects.get(name='faf')
        user.groups.add(group)
        user.save()
        # Render HTML and create plain text alternative
        html_message = render_to_string(
            'email/invitation.html', 
            {'user': user, 
                'obj': obj, 
                'password': password, 
                'cta': settings.SITE_URL + f'/admin/brainstorm/session/?id__exact={obj.id}'
            }
        )
        plain_message = strip_tags(html_message)
        send_mail(
            f'Invitation to join the brainstorming: {self}', plain_message, settings.DEFAULT_FROM_EMAIL, [email],
            html_message=html_message # <--- HTML added here
        )
        return user

