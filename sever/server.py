from sys import platform
from os import path
import socket, select
import configparser


def servlet(conn):
    head = yield conn.recv(1024)
    print(head)
    respond_content = '''HTTP/1.x 200 OK
    Content-Type: text/html
    length: 20

    <head>
    <title>WOW</title>
    </head>
    <html>
    <p>hi, Python Server</p>
    <img src="test.jpg"/>
    </html>
    '''
    ret = yield conn.write(bytearray(respond_content, encoding='utf-8'))
    print('lalala')


class AsyncState:
    def __init__(self, data):
        self.data = data

    def io(self):
        raise NotImplementedError


class AsyncRead(AsyncState):
    def __init__(self, buf_size):
        super().__init__(buf_size)

    def io(self, conn):
        return conn.recv(self.data)


class AsyncWrite(AsyncState):
    def __init__(self, buf):
        super().__init__(buf)

    def io(self, conn):
        return conn.send(self.data)


class AsyncEOF(AsyncState):
    def __init__(self):
        pass

    def io(self, conn):
        pass


class AsyncContext:
    def __init__(self, conn, servlet):
        self.conn = conn
        self.gen = servlet(AsyncConn())
        self.state = self.gen.send(None)

    def match(self, state=AsyncEOF):
        return isinstance(self.state, state)

    def perform(self):
        data = self.state.io(self.conn)
        try:
            self.state = self.gen.send(data)
            return 0
        except StopIteration as e:
            self.state = AsyncEOF()
            return -1


class AsyncConn:
    def recv(self, buf_size):
        return AsyncRead(buf_size)

    def write(self, buf):
        return AsyncWrite(buf)


def prepare_server_socket():
    conf = path.dirname(path.abspath('.')) + '/sever/SeverConfig.ini'
    config = configparser.ConfigParser()
    config.read(conf)

    # host and port
    HOST_INI = 'sever'
    HOST = config.get(HOST_INI, 'host')
    PORT = int(config.get(HOST_INI, 'port'))

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(5)
    return server_socket


class EventLoop:
    def __init__(self):
        self.changelist = []

    def _flush_events(self):
        ret = self.changelist
        self.changelist = []
        return ret

    def _register_connection(self, fileno):
        event = select.kevent(ident=fileno,
                              filter=select.KQ_FILTER_READ,
                              flags=select.KQ_EV_ADD | select.KQ_EV_ENABLE)
        self.changelist.append(event)

    def _set_connection_status(self, fileno, isReadOrWrite=bool, enable=bool):
        event = select.kevent(ident=fileno,
                              filter=select.KQ_FILTER_READ if isReadOrWrite else select.KQ_FILTER_WRITE,
                              flags=select.KQ_EV_ADD | (select.KQ_EV_ENABLE if enable else select.KQ_EV_DISABLE))
        self.changelist.append(event)

    def _remove_connection(self, fileno):
        event = select.kevent(ident=fileno,
                              filter=select.KQ_FILTER_READ|select.KQ_FILTER_WRITE,
                              flags=select.KQ_EV_DELETE)
        self.changelist.append(event)


# https://www.freebsd.org/cgi/man.cgi?kqueue
class KQueueEventLoop(EventLoop):
    def __init__(self):
        super().__init__()
        self.kq = select.kqueue()
        server_socket = prepare_server_socket()
        self._register_connection(server_socket)
        self.server_socket = server_socket
        self.contexts = {}

    def _get_socket(self, fileno):
        return socket.fromfd(fileno, socket.AF_INET, socket.SOCK_STREAM, 0)

    def __iter__(self):
        return self

    def _stream(self):
        while True:
            yield from self._once()

    def run(self):
        while True:
            changelist = self._flush_events()
            revents = self.kq.control(changelist, 100, None)
            for event in revents:
                fileno = event.ident
                if event.filter == select.KQ_FILTER_READ:
                    if fileno == self.server_socket.fileno():
                        new_conn, _ = self.server_socket.accept()
                        self._register_connection(new_conn.fileno())
                        self.contexts[new_conn.fileno()] = AsyncContext(new_conn, servlet)
                    else:
                        size = event.data
                        if size == 0 and (event.flags and select.KQ_EV_EOF):
                            self._remove_connection(fileno)
                        else:
                            context = self.contexts[fileno]
                            if context.match(AsyncRead):
                                yield context

                            if context.match(AsyncWrite):
                                self._set_connection_status(fileno, False, True)

                elif event.filter == select.KQ_FILTER_WRITE:
                    context = self.contexts[fileno]
                    if context.match(AsyncWrite):
                        yield context

                    if context.match(AsyncWrite) is False:
                        self._set_connection_status(fileno, False, False)
