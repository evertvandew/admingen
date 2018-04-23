""" A tool / environment for analysing the data in exact.

Original idea:
Graag zou ik voor alle administraties binnen de exact omgeving alle mutaties iig
van 2017 en 2018 in 1 excel bestand de mutaties willen benaderen. Kan wat mij betreft
van alle bedrijven ook in 2 bestanden:
    1. alle grootboekrekening <#4000 (balans)
    2. >4000 (Winst- en verliesrekening).

Ik zou graag alle bestaande mutaties met nieuwe mutaties in 1 database bestand willen
hebben zodat ik hier een draaitabel op kan loslaten. Hierbij wil ik alle beschikbare
attributen die exact biedt in de kolommen beschikbaar willen hebben.


It seems that the easiest way to get data into access is to import a CSV file.
An alternative could be a local app that writes into ODBC.

"""

from admingen.clients.rest import OAuth2
from admingen.clients.exact_xml import






def export():
    # Get a token with which to authenticate...
    # First query exact to retrieve all administrations.
    # The REST api is used for this

    connection =
    # Read all data for all administrations, over the period
    # Write the data into two files, one for the balance, the other cashflow.

