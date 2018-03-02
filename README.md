## Python kqueue Server


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

in this def, you can do something for http server