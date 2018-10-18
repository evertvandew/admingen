""" Tools to handle international trade
"""

from enum import IntEnum


# The EU codes are: Austria, Belgium, Bulgaria, Czech republic, Croatia, Cyprus, Denmark, Estonia,
# Finland, France, Germany, Great Brittain, Greece, Hungary, Ireland, Italy, Latvia, Lithania,
# Luxembourg, Malta, Netherlands, Poland, Portugal, Romania, Slovakia, Slovenia, Spain, Sweden.
# 28 in total

PP_EU_COUNTRY_CODES = ['BE', 'BG', 'CY', 'DK', 'DU', 'EE', 'FI', 'FR', 'GR', 'HU', 'IE', 'IT', 'HR',
                       'LV', 'LT', 'LU', 'MT', 'NL', 'AT', 'PL', 'PT', 'RO', 'SI', 'SK', 'ES', 'CZ',
                       'GB', 'SE']

# Country codes according to ISO 3166
ISO_EU_COUNTRY_CODES = ['AT', 'BE', 'BG', 'CZ', 'HR', 'CY', 'DK', 'EE', 'FI', 'FR', 'DE', 'GB',
                        'GR', 'HU', 'IE', 'IT', 'LV', 'LT', 'LU', 'MT', 'NL', 'PL', 'PT', 'RO', 'SK',
                        'SI', 'ES', 'SE']


class SalesType(IntEnum):
    Unknown = 0
    Local = 1
    EU_private = 2
    EU_ICP = 3
    Other = 4
    Invoiced = 5
