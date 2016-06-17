#
# Shortcuts for various tasks.
#

test-service: export EVENTLOG_SETTINGS=$(shell pwd)/tests/service/test.conf
test-service:
	@(py.test -q --cov eventlog/service --cov-report term-missing tests/service/)

test-lib:
	@(py.test -q --cov eventlog/lib --cov-report term-missing tests/lib/)

test: test-service test-lib
