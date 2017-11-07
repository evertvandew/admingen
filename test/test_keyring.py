

from unittest import TestCase

from admingen.keyring import KeyRing, DecodeError


class KeyringTest(TestCase):
    def test(self):
        ring = KeyRing('test.enc', 'Haleluja!')
        for value, key in enumerate('Zoals het klokje thuis tikt tikt het nergens'.split()):
            ring[key] = value

        ring2 = KeyRing('test.enc', 'Haleluja!')

        self.assertEqual(ring2['Zoals'], 0)
        self.assertEqual(ring2['het'], 6)
        self.assertEqual(ring2['nergens'], 7)

        with self.assertRaises(DecodeError):
            ring3 = KeyRing('test.enc', 'Haleluia!')
