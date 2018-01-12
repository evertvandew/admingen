""" Tools to handle international trade
"""

from enum import IntEnum


EU_COUNTRY_CODES = ['BE', 'BG', 'CY', 'DK', 'DU', 'EE', 'FI', 'FR', 'GR', 'HU', 'IE', 'IT', 'HR',
                    'LV', 'LT', 'LU', 'MT', 'NL', 'AT', 'PL', 'PT', 'RO', 'SI', 'SK', 'ES', 'CZ',
                    'GB', 'SE']


class SalesType(IntEnum):
    Unknown = 0
    Local = 1
    EU_private = 2
    EU_ICP = 3
    Other = 4
