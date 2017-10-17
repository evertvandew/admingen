""" Define the syntaxes for the configuration files and elements """

# The syntax is defined in EBNF.
# Uses the tatsu parser framework for lexing and parsing

import tatsu

fsm_grammar = r'''
fsms = {transitions | datadef} ;
transitions = (startmarker naam newline) {statement} endmarker ;

startmarker = "@startuml" ;
endmarker = "@enduml";
statement = [transition] newline ;
transition = state arrow state colon conditie ;

conditie = /(\S+[ \t\f\v]*)*/ ;
state = naam | startpoint ;
startpoint = "[*]" ;
arrow = "-->" | "->" ;


datadef = (defdatastart colon naam) {defregel | comment}* defdataend ;

defdatastart = "~defdata" ;
defdataend = "~enddata" ;

defregel = naam colon typedef { comma naam equals value }+ ;

typedef = naam | ("Set(" naam ")") ;
value = literal ;
naam = /[a-zA-Z_]\w*/ ;
colon = ":";
comma = ",";
equals = "=";

literal = stringlit | intlit | floatlit ;
stringlit = /(?P<quote>['"]).*?(?P=quote)/ ;
intlit = /\d+/ ;
floatlit = /[+\-]?\d*[.]\d*/ ;
newline = (SPACES | (['\r'] /[\n\r\f]/) [SPACES]) ;
SPACES = /[ \t]*/ ;
comment = '#' /.*?/ newline ;

'''



if __name__ =='__main__':
    model = tatsu.compile(fsm_grammar)
    print (model.parse('''@startuml feestje
    @enduml'''))

    print (model.parse('''@startuml Opdracht
    [*] --> Aanvraag : NieuweAanvraag
    Aanvraag --> Offerte : VerzendOfferte
    Offerte --> Aanvraag : OfferteAfgekeurd
    Offerte --> Lopend : OfferteGeaccepteerd
    Lopend --> [*] : OpdrachtAfgerond
    Lopend --> Lopend : VoegWerkerToe
    Lopend --> Lopend : HaalWerkerWeg
    @enduml'''))

    ast = model.parse('''@startuml Opdracht
    [*] --> Aanvraag : NieuweAanvraag
    Aanvraag --> Offerte : VerzendOfferte
    Offerte --> Aanvraag : OfferteAfgekeurd
    Offerte --> Lopend : OfferteGeaccepteerd
    Lopend --> [*] : OpdrachtAfgerond
    Lopend --> Lopend : VoegWerkerToe
    Lopend --> Lopend : HaalWerkerWeg
    @enduml
    
    @startuml Factuur
    
    [*] --> Opgehouden : MaakFactuur && not FactuurReady
    [*] --> Review : MaakFactuur && FactuurReady
    Opgehouden --> Review : FactuurReady
    Review --> Verstuurd : FactuurGoedgekeurd
    Verstuurd --> Mislukt : VerzendFout
    Mislukt --> Verstuurd : VerstuurOpnieuw
    Verstuurd --> Voldaan : FactuurBetaald
    Verstuurd --> TeLaat : FactuurTeLaat
    TeLaat --> Voldaan : FactuurBetaald
    TeLaat --> VeelTeLaat : FactuurTeLaat
    VeelTeLaat --> Voldaan : FactuurBetaald
    VeelTeLaat --> [*] : FactuurAfgeschreven
    Voldaan --> [*]  : FactuurOpruimen
    
    @enduml
    
    ''', rule_name = 'fsms')
    print (ast)
