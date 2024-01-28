
all: run
TEMP=Dit is een test

# Set the PYTHON variable if it isn't already set
PYTHON ?= $(shell which python3)
# Determine which Python version is being used
PYVER=$(shell $(PYTHON) -c 'import sys; print (f"{sys.version_info.major}.{sys.version_info.minor}")')

page_definitions.xml: webinterface.xml webif_templates.xml
	xml_template -i webinterface.xml > page_definitions.xml

html/last_generated: page_definitions.xml
	write_pages < page_definitions.xml
	install_components -f page_definitions.xml
	touch html/last_generated

data_model.py: webinterface.xml
	write_sqlalchemy_model > $@ < webinterface.xml

acm_table: webinterface.xml my_queries.py
	write_acm < webinterface.xml >$@
	#python my_queries.py --write_acm >> $@

resources:
	mkdir $@
	chmod 700 $@

run: html/last_generated data_model.py resources acm_table
	echo PYTHON: $(PYTHON) PYVER: $(PYVER)
	$(PYTHON) run.py

deploy: html/last_generated data_model.py resources acm_table
	uwsgi --ini uwsgi.ini

soffice:
	/usr/bin/soffice --accept='socket,host=localhost,port=8100;urp;StarOffice.Service' --headless

clean:
	rm -f page_definitions.xml

realclean:
	rm -rf page_definition.xml data_model.py html

print-%:
	@echo '$*=$($*)'

