from admingen import htmltools


def createService(ast):
    """ Create the viewer and editor for a single data entity """
    class Service:
        def index(self):
            pass
        def edit(self):
            pass
        def add(self):
            pass
        def view(self):
            pass
        def delete(self):
            pass
        exposed=True


def createServices(ast):
    """ Convert a model of the application into an HMI frontend """
    # Create viewers and editors for each data entity
    viewers = {a['name']: createService(a) for a in ast['tables']}

    class Services: pass

    Services.__dict__.update(viewers)


