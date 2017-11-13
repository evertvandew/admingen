""" Define the syntaxes for the configuration files and elements """

# The syntax is defined in EBNF.
# Uses the tatsu parser framework for lexing and parsing

import tatsu

fsm_syntax = r'''
config = modules:[modules] '\n'%{[ fsms:fsm | tables:table | rules:rules | actions:actions ]} ;

modules = "import" path:module NEWLINE ;
module  = "."%{ name } ; 
name = name:/\w+/ ;
word = /\w+/ ;

fsm = "fsm" name:word "\n" {[transitions:transition] NEWLINE} blockend ;
transition = !(".\n") ','%{from:state} /\s*-?->\s*/ to:state [":" details:restofline] ;
state = word | "[*]" ;
blockend = "." ;

table = "table" name:word NEWLINE {[columns:column] NEWLINE} blockend ;
column = !(".\n") name:word ":" details:restofline ;

rules = "rules" fsm:word NEWLINE {[rules:rule] NEWLINE} blockend ;
rule = !(".\n") /\s*,\s*/%{ states:name } ":" details:restofline ;


actions = "actions" NEWLINE {[actions:action] NEWLINE} blockend;
action = !(".\n") "\s*,\s*"%{ "."%{path:word} } ":" details:restofline ;

NEWLINE = (SPACES | (['\\r'] /[\n\r\f]/) [SPACES]) ;
SPACES = /[ \t]+/ ;
restofline = /[^\n]*/ ;
'''


fsm_model = tatsu.compile(fsm_syntax)

if __name__ =='__main__':
    model = tatsu.compile(fsm_syntax)
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
