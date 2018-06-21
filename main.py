import socket
import ssl
import re
import time
import base64

class TextParser:

    def __init__(self):
        self.reg_from_field = re.compile('From: ([^>]*)')
        self.reg_date_field = re.compile('Date: ([^\n]*)')
        self.reg_subject = re.compile('Subject: (.*)MIME', re.DOTALL)
        self.reg_boundary = re.compile('boundary="([^"]*)')
        self.get_type = re.compile("\r\n(Content-Type[^\r\n]*)")
        self.get_file_name = re.compile('\r\n\tfilename="([^"]*)')
        self.get_transfer_encoding = re.compile('\r\n(Content-Transfer[^\r\n]*)')
        self.get_body = re.compile("\r\n\r\n", re.DOTALL)

    def get_boundary(self, data):
        return self.reg_boundary.search(data).group(1)

    def getFromField(self, data):
        return self.reg_from_field.search(data).group(1)

    def getDateField(self, data):
        return self.reg_date_field.search(data).group(1)

    def get_subject_field(self, data):
        return self.reg_subject.search(data).group(1)

    def get_blocs(self, boundary, data):
        return re.split('-*' + boundary, data)

class PopException(Exception):

    def __index__(self, msg):
        self.msg = msg
        super().__init__(msg)


class PopExceptionServerNotAvailable(PopException):

    def __init__(self):
        super().__init__('server is not available')


class PopClient:

    def __init__(self, login, password):
        self.password = password
        self.user = login
        self.address, self.port = ('pop.gmail.com', 995)
        self.sock = ssl.wrap_socket(socket.socket())
        self.sock.settimeout(2)
        self.messages_descriptor = {}
        self.count_messages = 0
        self.min_size = 1024 * 1024
        self.parser = TextParser()

    def send(self, data):
        self.sock.send((data + '\n').encode())

    def auth(self):
        self.sock.connect((self.address, self.port))
        if not self.sock.recv(1024).decode().strip().startswith('+OK'):
            raise PopExceptionServerNotAvailable
        self.send('user '+ self.user)
        if not self.sock.recv(1024).decode().strip().startswith('+OK'):
            raise PopException("incorrect user")
        self.send('pass ' + self.password)
        a = self.sock.recv(1024).decode().strip()
        if not a.startswith('+OK'):
            raise PopException("incorrect password")

    def response_as_text(self):
        data = b''
        while True:
            try:
                part = self.sock.recv(1024)
                data += part
            except Exception:
                break
        return data.decode()

    def get_message_header(self, count):
        try:
            for i in range(0, count):
                self.send('top ' + str(self.count_messages - i) + '  0')
                data = self.response_as_text()
                #print(len(data))
                #if (i == 1):
                    #print(data)
                from_ = ''
                date =''
                subject = ''
                try:
                    from_ = self.get_from_as_text(self.parser.getFromField(data)).strip()
                    for coding_line in self.parser.get_subject_field(data).split("\r\n\t"):
                        subject += self.from_base_64_to_str(coding_line).strip()
                except:
                    pass
                print('Message :')
                print('From : ', from_)
                print('Data :', date)
                print('Subject :', subject)
        except PopException as exc:
            self.auth()
            self.get_message_header(count)

    def get_message(self, number):
        try:
            self.send('top ' + str(self.count_messages - number + 1) + ' '
                      + str(120000))
            data = self.response_as_text()
            boundary = self.parser.get_boundary(data)
            blocs = self.parser.get_blocs(boundary, data)[2:-1]
            self.save_blocs(blocs)
            a = len(blocs)
        except:
            self.auth()
            self.get_message_header(number)

    def get_messages_descriptor(self):
        try:
            self.send('list')
            line = b''
            isCount = False
            while True:
                b = self.sock.recv(1)
                if b == b' ':
                    if not isCount:
                        isCount = True
                    else:
                        break
                line += b
            self.count_messages = int(line.decode().strip().split(' ')[1])
            while self.sock.recv(1) != b'\n':
                pass

            for i in range(1, self.count_messages + 1):
                line = b''
                while True:
                    b = self.sock.recv(1)
                    if b == b'\n':
                        break
                    line += b
                size = int(line.decode().strip().split(' ')[1])
                self.min_size = min(size, self.min_size)
                self.messages_descriptor[i] = size
            self.sock.recv(3)
        except Exception as exc:
            self.auth()
            self.get_messages_descriptor()

        #print(self.messages_descriptor)

    def get_from_as_text(self, from_):
        try:
            return self.from_base_64_to_str(from_, from_.split(' ')[-1] + '>')
        except Exception as exc:
            return from_

    def from_base_64_to_str(self, data, additional=''):
        blocks = data.split('?')
        try:
            if blocks[1].lower() == 'utf-8':
                return base64.b64decode(blocks[3]).decode('utf-8') + additional
        except Exception as exc:
            return data

    def save_blocs(self, blocs):
        for data in blocs:
            name = 'body'
            content_transfer_encoding =''
            content_type = ''
            try:
                mime_type = self.parser.get_type.search(data).group(1).strip().split(';')
                for field in mime_type:
                    if field.startswith('Content-Type'):
                        content_type = field.split(':')[1]
                    if field.startswith('charset'):
                        charset = field.split('=')[1]
                name = self.from_base_64_to_str(self.parser.get_file_name.search(data).group(1))
                content_transfer_encoding = self.parser.get_transfer_encoding.search(data).group(1)
            except:
                pass
            body = self.parser.get_body.split(data, re.DOTALL)[-1]
            file_type = self.get_file_type(content_type)
            if content_type.strip().startswith('text'):
                f = open(name + file_type, 'w+')
                f.write(body)
                f.close()
            if content_type.strip().startswith('application') or content_type.strip().startswith('image'):
                f = open(name, 'wb+')
                file_data = base64.b64decode(body.strip())
                f.write(file_data)
                f.close()


    def get_file_type(self, content_type):
        if (content_type.endswith('plain')):
            return '.txt'
        if (content_type.endswith('html')):
            return '.html'
        if (content_type.endswith('pdf')):
            return '.pdf'
        if (content_type.endswith('jpeg')):
            return '.jpeg'
        if (content_type.endswith('png')):
            return '.png'
        return '.file'


pc = PopClient('userName', 'password')
pc.get_messages_descriptor()
pc.get_message_header(2)
pc.get_message(1)
