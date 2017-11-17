

from .rest import restapi
from .oauth2 import OAuth2


class ExactXmlClient:
    pass



@restapi
class ExactRestClient(OAuth2):
    class division:
        class TransactionLine:
            pass
        class Account:
            pass
        class GLAccount:
            pass
