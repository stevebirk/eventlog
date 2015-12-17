#
# Shortcuts for various tasks.
#

test-service: export EVENTLOG_SETTINGS=$(shell pwd)/tests/service/test.conf
test-service:
	@(py.test -q --cov eventlog/service tests/service/)

test-lib:
	@(py.test -q --cov eventlog/lib tests/lib/)

test: test-service test-lib
