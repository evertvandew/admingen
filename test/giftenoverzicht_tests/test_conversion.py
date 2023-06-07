import admingen.clients.exact_xml as ex
import json

files = {'Users': ['Accounts_1.xml'],
         'Accounts': ['GLAccounts_1.xml'],
         'Transactions': ['GLTransactions_1.xml', 'GLTransactions_2.xml']}


xml_parsers = {'Users': ex.processAccounts,
               'Accounts': ex.processLedgers,
               'Transactions': ex.processTransactionLines}

for dossier, fnames in files.items():
    all = []
    for fname in fnames:
        p = f'/home/ehwaal/admingen/{fname}'
        records = xml_parsers[dossier](open(p, 'rb'))
        print(f"Got {len(records)} records")
        all.extend(records)

    json.dump(all, open(f'test_{dossier}.json', 'w'), indent=2)
