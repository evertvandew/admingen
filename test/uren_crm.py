def Opdracht.Offerte.entry
pdf = adminlib.RenderTemplate('offerte.rst', opdracht)
body = adminlib.RenderTemplate('offerte_body.rst', opdracht)
email(attachment=pdf,
      sendto=opdracht.opdrachtgever.contactpersoon.email,
      subject="Offerte voor opdracht {opdracht.naam}",
      body=body)
opdracht.pdf = pdf
.



FactuurReady = ForAll(werker in opdracht.werkers,
    Count(ws in werker
          where ws.periode_start < factuur.periode_einde
            and ws.periode_einde > factuur.periode_start
            and ws.status >= Goedgekeurd
    ) == NrWeekstatenInPeriod(factuur.periode_start, factuur.periode_einde))

