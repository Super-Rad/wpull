# encoding=utf-8
'''WARC format.

For the WARC file specification, see
http://bibnum.bnf.fr/WARC/WARC_ISO_28500_version1_latestdraft.pdf.

For the CDX specifications, see
https://archive.org/web/researcher/cdx_file_format.php and
https://github.com/internetarchive/CDX-Writer.
'''
import base64
import hashlib
import uuid

from wpull.namevalue import NameValueRecord
import wpull.util


class WARCRecord(object):
    '''A record in a WARC file.'''
    VERSION = 'WARC/1.0'
    WARC_TYPE = 'WARC-Type'
    CONTENT_TYPE = 'Content-Type'
    WARC_DATE = 'WARC-Date'
    WARC_RECORD_ID = 'WARC-Record-ID'
    WARCINFO = 'warcinfo'
    WARC_FIELDS = 'application/warc-fields'
    REQUEST = 'request'
    RESPONSE = 'response'
    TYPE_REQUEST = 'application/http;msgtype=request'
    TYPE_RESPONSE = 'application/http;msgtype=response'
    NAME_OVERRIDES = frozenset([
        'WARC-Date',
        'WARC-Type',
        'WARC-Record-ID',
        'WARC-Concurrent-To',
        'WARC-Refers-To',
        'Content-Length',
        'Content-Type',
        'WARC-Target-URI',
        'WARC-Block-Digest',
        'WARC-IP-Address',
        'WARC-Filename',
        'WARC-Warcinfo-ID',
        'WARC-Payload-Digest',
    ])
    '''Field name case normalization overrides because hanzo's warc-tools do
    not adequately conform to specifications.'''

    def __init__(self):
        self.fields = NameValueRecord(normalize_overrides=self.NAME_OVERRIDES)
        self.block_file = None

    def set_common_fields(self, warc_type, content_type):
        '''Set the required fields for the record.'''
        self.fields[self.WARC_TYPE] = warc_type
        self.fields[self.CONTENT_TYPE] = content_type
        self.fields[self.WARC_DATE] = wpull.util.datetime_str()
        self.fields[self.WARC_RECORD_ID] = '<{0}>'.format(uuid.uuid4().urn)

    def set_content_length(self):
        '''Find and set the content length.

        :seealso: :func:`compute_checksum`.
        '''
        if not self.block_file:
            self.fields['Content-Length'] = '0'
            return

        with wpull.util.reset_file_offset(self.block_file):
            self.block_file.seek(0, 2)
            self.fields['Content-Length'] = str(self.block_file.tell())

    def compute_checksum(self, payload_offset=None):
        '''Compute and add the checksum data to the record fields.

        This function also sets the content length.
        '''
        if not self.block_file:
            self.fields['Content-Length'] = '0'
            return

        block_hasher = hashlib.sha1()
        payload_hasher = hashlib.sha1()

        with wpull.util.reset_file_offset(self.block_file):
            if payload_offset is not None:
                data = self.block_file.read(payload_offset)
                block_hasher.update(data)

            while True:
                data = self.block_file.read(4096)
                if data == b'':
                    break
                block_hasher.update(data)
                payload_hasher.update(data)

            content_length = self.block_file.tell()

        content_hash = block_hasher.digest()

        self.fields['WARC-Block-Digest'] = 'sha1:{0}'.format(
            base64.b32encode(content_hash).decode()
        )

        if payload_offset is not None:
            payload_hash = payload_hasher.digest()
            self.fields['WARC-Payload-Digest'] = 'sha1:{0}'.format(
                base64.b32encode(payload_hash).decode()
            )

        self.fields['Content-Length'] = str(content_length)

    def __iter__(self):
        yield self.VERSION.encode()
        yield b'\r\n'
        yield bytes(self.fields)
        yield b'\r\n'

        with wpull.util.reset_file_offset(self.block_file):
            while True:
                data = self.block_file.read(4096)
                if data == b'':
                    break
                yield data

        yield b'\r\n\r\n'

    def __str__(self):
        return ''.join(iter(self))
