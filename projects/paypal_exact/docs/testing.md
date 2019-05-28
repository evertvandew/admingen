# Testing the paypal exporter


To manually exectute the paypal exporter, do the following:

* Download the transactions and store them in the `~/tmp/pp_export/test-data` directory.
* Run the `future_improvements.py` script.

The script has a number of parameters. Use e.g.

    ./future_improvements.py -t "1 3 5 6"

De rest van het systeem zijn verouderd. Er zijn stukken om de transacties
te downloaden van Paypal en te uploaden naar exact.

De download mechanismes maken nog geen gebruik van het nieuwe paypal feature
dat willekeurige ranges als text kunnen worden ingevuld.
