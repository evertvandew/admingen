import glob
import calendar
import io
import json
import logging
import datetime
from admingen.clients.exact_xml import processAccounts, processLedgers, processTransactionLines
from admingen import config

from commands import USERS_FILE, TRANSACTIONS_FILE, ACCOUNTS_FILE
import model
from giften import (generate_overviews, generate_overview, amount2Str, pdfUrl,
                    odataDate2Datetime, generate_pdfs, pdfName, pdfUrl2Name, PDF_DIR,
                     filter_gifts)

def data_uploaded(org_id, files):
    ufname = USERS_FILE.format(config.opsdir, org_id)
    tfname = TRANSACTIONS_FILE.format(config.opsdir, org_id)
    afname = ACCOUNTS_FILE.format(config.opsdir, org_id)
    targets = {'users': ufname,
               'accounts': afname,
               'transaction': tfname}
    xml_parsers = {'users': processAccounts,
                   'accounts': processLedgers,
                   'transaction': processTransactionLines}

    for arg, fname in targets.items():
        value = files.get(arg, [])
        if value:
            if not isinstance(value, list):
                value = [value]
            texts = []
            for v in value:
                texts.append(v)

            # Parse the files and store as json.
            collection = []
            for text in texts:
                text = text.decode('utf8').strip()
                if '<?xml' in text[:10]:
                    strm = io.StringIO(text)
                    collection.extend(xml_parsers[arg](strm))
                else:
                    raise RuntimeError("Unsupported file format")

            with open(fname, 'w') as of:
                logging.info(f"Writing to file: {fname}, {len(collection)} records")
                json.dump(collection, of, indent=2)

            # Determine start and end dates.
            if False: # arg == 'transaction':
                with model.sessionScope():
                    org = model.Organisation[org_id]

                    gifts = filter_gifts(org.to_dict(with_lazy=True), collection)
                    dates = [g['Date'].date() for g in gifts]
                    period_start, period_end = [func(dates) for func in [min, max]]
                    org.status = model.SystemStates.GeneratingPDF
                    org.period_start = datetime.datetime(period_start.year, period_start.month, 1)
                    org.period_end = datetime.datetime(
                        period_end.year,
                        period_end.month,
                        calendar.monthrange(period_end.year, period_end.month)[1],
                        23, 59, 59)


def read_files(directory):
    fnames = {'users': glob.glob(directory+"Accounts*.xml"),
              'accounts': glob.glob(directory+"GLAccounts*.xml"),
              'transaction': glob.glob(directory+"GLTransactions*.xml")}
    files = {k: [open(f, 'rb').read() for f in v] for k, v in fnames.items()}
    data_uploaded(1, files)


model.openDb('sqlite://overzichtgen.db')
read_files(r"/home/ehwaal/Downloads/tmp/Exports Exact GCV 2021/")