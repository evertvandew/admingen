

all: test
.PHONY: test


test:
	export PYTHONPATH=`pwd`/src
	python3 -m unittest test.test_csv_handling
	#python3 -m unittest discover -s test/urenreg -v
