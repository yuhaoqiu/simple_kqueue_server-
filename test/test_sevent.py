from sever.server import KQueueEventLoop

if __name__ == '__main__':
    event_loop = KQueueEventLoop()

    for context in event_loop.run():
        context.perform()

    print('silent close')