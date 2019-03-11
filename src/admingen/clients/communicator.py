









def sendMsg(uri, msg):
    method, details = uri.split(':', 1)
    if method == 'mailto':
        pass