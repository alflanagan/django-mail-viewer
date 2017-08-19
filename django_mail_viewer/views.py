from __future__ import absolute_import, division, print_function, unicode_literals

# email parsing
from io import BytesIO

from django.core import mail
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.utils.encoding import smart_str
from django.views.generic.base import TemplateView, View

try:
    from django.core.urlresolvers import reverse
except ImportError:
    from django.urls import reverse


class SingleEmailMixin(object):
    """
    Mixin for details for a single email
    """

    def get_message(self):
        message = None
        with mail.get_connection() as connection:
            message_id = self.kwargs.get('message_id')
            message = connection.get_message(u'<%s>' % message_id)
        return message

    def _parse_email_attachment(self, message, decode_file=True):
        """
        Parse an attachment out of an email.message.Message object.

        params:
        msg: email.message.Message object
        decode_file: Boolean whether to decode the base64 encoded file to an actual file or not
        """
        content_disposition = message.get("Content-Disposition", None)
        if content_disposition:
            dispositions = content_disposition.strip().split(";")
            if bool(content_disposition and dispositions[0].lower() == "attachment"):
                if decode_file:
                    file_data = message.get_payload(decode=True)
                    attachment = BytesIO(file_data)
                    attachment.size = len(file_data)

                    attachment.content_type = message.get_content_type()
                    attachment.name = None
                    attachment.create_date = None
                    attachment.mod_date = None
                    attachment.read_date = None
                else:
                    attachment = None
                for param in dispositions[1:]:
                    name, value = param.split("=")
                    name = name.lower()

                    # Since I am terrible and left terrible comments I am assuming the
                    # datetime TODO comments below mean to store as a datetime.datetime object
                    if name == "filename":
                        attachment.name = value
                    elif name == "create-date":
                        attachment.create_date = value  # TODO: datetime
                    elif name == "modification-date":
                        attachment.mod_date = value  # TODO: datetime
                    elif name == "read-date":
                        attachment.read_date = value  # TODO: datetime
                return {
                    'filename': message.get_filename(), 'content_type': message.get_content_type(), 'file': attachment}
        return None

    def _parse_email_parts(self, message, decode_files=True):
        # much of this borrowed from
        # https://www.ianlewis.org/en/parsing-email-attachments-python
        attachments = []
        body = None
        html = None
        for part in message.walk():
            attachment = self._parse_email_attachment(part, decode_files)
            if attachment:
                attachments.append(attachment)
            elif part.get_content_type() == 'text/plain':
                # should we get the default charset from the system if no charset?
                # decode=True handles quoted printable and base64 encoded data
                charset = part.get_param('charset')
                body = part.get_payload(decode=True).decode(charset, errors='replace')
            elif part.get_content_type() == 'text/html':
                # original code set html to '' if it was None and then appended
                # as if we might have multiple html parts which are just one html message?
                charset = part.get_param('charset')
                html = part.get_payload(decode=True).decode(charset, errors='replace')

        subject = message.get('subject')
        msg_from = message.get('from')
        to = message.get('to')
        return (subject, body, html, msg_from, to, attachments)


class EmailListView(TemplateView):
    """
    Display a list of sent emails.
    """
    template_name = 'mail_viewer/email_list.html'

    def get_context_data(self, **kwargs):
        # TODO: need to make a custom backend which sets a predictable message-id header.
        # built in locmem uses a random number each time the message is accessed
        # preventing lookup in the detail view
        with mail.get_connection() as connection:
            # add a backend.get_outbox() for supporting multiple backends?
            outbox = connection.get_outbox()
        return super(EmailListView, self).get_context_data(outbox=outbox, **kwargs)


class EmailDetailView(SingleEmailMixin, TemplateView):
    """
    Display details of an email
    """
    template_name = 'mail_viewer/email_detail.html'

    def get(self, request, *args, **kwargs):
        self.message = self.get_message()
        if not self.message:
            return HttpResponseRedirect(reverse('mail_viewer_list'))

        return super(EmailDetailView, self).get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        lookup_id = kwargs.get('message_id')
        message = self.message

        with mail.get_connection() as connection:
            outbox = connection.get_outbox()

        subject, text_body, html_body, sender, to, attachments = self._parse_email_parts(message, decode_files=False)
        return super(EmailDetailView, self).get_context_data(lookup_id=lookup_id,
                                                             message=message,
                                                             text_body=text_body,
                                                             html_body=html_body,
                                                             subject=subject,
                                                             sender=sender,
                                                             to=to,
                                                             attachments=attachments,
                                                             outbox=outbox,
                                                             **kwargs)


class EmailAttachmentDownloadView(SingleEmailMixin, View):
    """
    Stream out an email attachment to the web browser
    """

    def get_attachment(self, message):
        # TODO: eventually will need to handle different ways of having these
        # atachments stored.  Probably handle that on the EmailBackend class
        requested = int(self.kwargs.get('attachment'))
        i = 0
        # TODO: de-nest this some
        for part in message.walk():
            content_disposition = part.get("Content-Disposition", '')
            dispositions = content_disposition.strip().split(";")
            if (content_disposition and dispositions[0].lower() == "attachment"):
                if i == requested:
                    return self._parse_email_attachment(part, True)
                i += 1
        raise Http404('Attachment not found')

    def get(self, request, *args, **kwargs):
        message = self.get_message()
        attachment = self.get_attachment(message)
        response = HttpResponse(attachment['file'], content_type=attachment['content_type'])
        response['Content-Disposition'] = 'attachment; filename=%s' % smart_str(attachment['filename'])
        return response
