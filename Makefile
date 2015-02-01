#
# Shortcuts for various tasks.
#

test-service: export EVENTLOG_SETTINGS=$(shell pwd)/tests/service/test.conf
test-service:
	@(nosetests --cover-erase \
			    --cover-package eventlog.service \
			    --with-coverage \
			    -w tests/service/)

test-lib:
	@(nosetests --cover-erase \
			    --cover-package eventlog.lib \
			    --with-coverage \
			    -w tests/lib/)

test: test-service test-lib
