# XML Template Language

admingen contains a new XML template engine. Using this engine, XML can be used to define templates that are powerful
enough to be used for data-driven Domain Specific Languages.

Within admingen, it is used to define interactive websites. One definition file contains all information necessary to
generate the HML pages and configure the database.

This works as follows:

@startuml
webinterface --> webif_templates
write_datastructure --> webinterface
write_datastructure --> datamodel
write_pages --> webinterfaces
write_pages --> html
@enduml

The webinterface definition includes other files, for example a file containing common templates. 
There are several tools that generate a particular part of the application:

* The data model
* The HTML code
* The ACM rights matrix

These tools use different parts of the webinterface definition, usually by handling specific tags in the XML.

Tools that use the XML template language, 


# Elements in the XML language

## Defining "template" tags

Template tags look like any other tag in XML, except that they are defined in the XML file itself.
These tags are expanded to bits of XML code.

Obviously, these template tags are definied using the XML syntax itself, as follows:

```XML
<Template tag="<new tag name>" args="<arg1>,<arg2>,<arg3=default>">
    ...Replacement template...
</Template>
```

The python template engine `Mako` is used to expand the replacement template. The arguments specified in the Template tag are available
as Python variables within this context, as well as any variables or function provided to the Mako environment by the tool handling the template.
`Mako` was selected because it is powerful and does not bite syntax of e.g. Angular.

The template engine allows the use of other template tags inside the template, with the arguments for that inner template
constructed inside the outer template. You can also define templates within another template. 
These template can only be used within the scope where they are defined.

## Template Slots

XML has two ways of handling data. The first one, arguments, is handled directly by the `Template` definition tag.
However, XML also allows either further XML tags or text to be included within a tag, as in
`<Tag>...your text goes here...</Tag>`. Template Slots are used for this.

In XML, the body of a tag is a single structure. However, when that tag is in fact a template, the body may well need
to be slit and treated differently. Template Slots allow this.

If a template contains a single Template Slot, the body given to an instance of the Template is inserted into that slot.
If a template has multiple slots, each slot is given a different name. 
The parts can be separated by wrapping them in a `<TemplateSlot_<name> >` tag. Such a definition is scoped, and stays relevant
until overwritten. This means that slots can also be given default values.

If any part of the body that is not wrapped in a `<TemplateSlot_<name> >` tag is inserted into the last TemplateSlot 
defined in the template.

A template can instantiate a slot multiple times.

An example:

```XML
<!-- Definition of a new tag -->
<Template tag="Page">
<!DOCTYPE html>
<html lang="en">
<head></head>
<body>
<TemplateSlot name="body" />
</body>
</html>
</Template>

<!-- Use of the new tag -->
<Page>
    Dit is de body van de pagina.
</Page>
```

A slightly more complicated example:

```XML
<!-- Definition of a new tag -->
<Template tag="Page">
<!DOCTYPE html>
<html lang="en">
<head>
<TemplateSlot name="head" />
</head>
<body>
<TemplateSlot name="body" />
</body>
</html>
</Template>

<!-- Use of the new tag -->

<Page>
    Dit is de body van de pagina.
</Page>
```

## Importing an external template file

```XML
<include file="<template file>" />
```

The included file is inserted into the XML text, just like with e.g. the C programming language.

## Comments

The template engine allows the use of XML comments. These comments are removed before further processing.


# Built-in structures

## Data model

As administrative applications are data-driven, support for a data model is built-in into the template language.

An example of a data model is given below.

```XML
<Datamodel name="operations" url_prefix="operations">
enum: Richting
    toename
    gelijk
    afname
    vervallen
enum: OT_Class
    kans
    risico
    geen_kr
table: BP_Caterory
    parent: BP_Caterory
    naam: str
    color: color
table: BP_Richting
    punt: BelangrijkPunt
    richting: Richting
    opmerking: longstr
    invuller: qualsys.Werknemer
table: BelangrijkPunt
    naam: str
    datum_ingebracht: date
    categorie: BP_Caterory
    belang_mt: BP_Richting
    belang_mt_vorig: BP_Richting
    ot_class: OT_Class
    ot_class_previous: OT_Class
    omschrijving: longstr
    aantekening: longstr
</Datamodel>
```

Standard data types are: `str`, `int`, `float`, `date`, `time`, `datetime`, `longstr`, `password`, `email`, `phone`, `bool`, `color`, `fileblob` and `image`.
A table can also have elements that refer to other tables or to itself.

Each field in a record can have several optional attributes, apart from its type.
These will fine-tune the way the field is handled by the various tools.

* `optional`: means that this field can be null.
* `protected`: means that this field is set by the software, and hidden from the user.