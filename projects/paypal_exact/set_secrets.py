""" A simple script to set the correct secrets
    for the paypal export and exact online import.
"""

from admingen.keyring import KeyRing
from admingen.clients.paypal import PaypalSecrets
from admingen.clients.rest   import OAuthDetails


if __name__ == '__main__':
    pw = input("Keyring password:")
    ring = KeyRing('oauthring.enc', pw)

    taskid = input("Task ID:")
    secrets = []
    for t, c in [("Please enter exact-online task details", OAuthDetails),
                 ("Please enter paypal login secrets", PaypalSecrets)]:
        print(t)
        details = {}
        for n, t in c.__annotations__.items():
            details[n] = input('%s:'%n).strip()

        secrets.append(c(**details))

    ring[taskid] = secrets

    print('Bye Bye')
