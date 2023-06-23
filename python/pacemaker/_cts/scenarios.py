""" Test scenario classes for Pacemaker's Cluster Test Suite (CTS)
"""

__all__ = [ "AllOnce", "Boot", "BootCluster", "LeaveBooted", "RandomTests", "Sequence" ]
__copyright__ = "Copyright 2000-2023 the Pacemaker project contributors"
__license__ = "GNU General Public License version 2 or later (GPLv2+) WITHOUT ANY WARRANTY"

import re
import time

from pacemaker._cts.audits import ClusterAudit
from pacemaker._cts.input import should_continue
from pacemaker._cts.tests.ctstest import CTSTest
from pacemaker._cts.watcher import LogWatcher

class ScenarioComponent:

    def __init__(self, cm, env):
        self._cm = cm
        self._env = env

    def is_applicable(self):
        '''Return True if the current ScenarioComponent is applicable
        in the given LabEnvironment given to the constructor.
        '''

        raise NotImplementedError

    def setup(self):
        '''Set up the given ScenarioComponent'''

        raise NotImplementedError

    def teardown(self):
        '''Tear down (undo) the given ScenarioComponent'''

        raise NotImplementedError


class Scenario:
    (
'''The basic idea of a scenario is that of an ordered list of
ScenarioComponent objects.  Each ScenarioComponent is setup() in turn,
and then after the tests have been run, they are torn down using teardown()
(in reverse order).

A Scenario is applicable to a particular cluster manager iff each
ScenarioComponent is applicable.

A partially set up scenario is torn down if it fails during setup.
''')

    def __init__(self, cm, components, audits, tests):

        "Initialize the Scenario from the list of ScenarioComponents"

        self.stats = { "success": 0, "failure": 0, "BadNews": 0, "skipped": 0 }
        self.tests = tests

        self._audits  = audits
        self._bad_news = None
        self._cm = cm
        self._components = components

        for comp in components:
            if not issubclass(comp.__class__, ScenarioComponent):
                raise ValueError("Init value must be subclass of ScenarioComponent")

        for audit in audits:
            if not issubclass(audit.__class__, ClusterAudit):
                raise ValueError("Init value must be subclass of ClusterAudit")

        for test in tests:
            if not issubclass(test.__class__, CTSTest):
                raise ValueError("Init value must be a subclass of CTSTest")

    def is_applicable(self):
        (
'''A Scenario is_applicable() iff each of its ScenarioComponents is_applicable()
'''
        )

        for comp in self._components:
            if not comp.is_applicable():
                return False

        return True

    def setup(self):
        '''Set up the Scenario. Return TRUE on success.'''

        self._cm.prepare()
        self.audit() # Also detects remote/local log config
        self._cm.ns.wait_for_all_nodes(self._cm.Env["nodes"])

        self.audit()
        self._cm.install_support()

        self._bad_news = LogWatcher(self._cm.Env["LogFileName"],
                                  self._cm.templates.get_patterns("BadNews"),
                                  self._cm.Env["nodes"],
                                  self._cm.Env["LogWatcher"],
                                  "BadNews", 0)
        self._bad_news.set_watch() # Call after we've figured out what type of log watching to do in LogAudit

        j = 0
        while j < len(self._components):
            if not self._components[j].setup():
                # OOPS!  We failed.  Tear partial setups down.
                self.audit()
                self._cm.log("Tearing down partial setup")
                self.teardown(j)
                return False
            j += 1

        self.audit()
        return True

    def teardown(self, n_components=None):

        '''Tear Down the Scenario - in reverse order.'''

        if not n_components:
            n_components = len(self._components)-1

        j = n_components

        while j >= 0:
            self._components[j].teardown()
            j -= 1

        self.audit()
        self._cm.install_support("uninstall")

    def incr(self, name):
        '''Increment (or initialize) the value associated with the given name'''
        if not name in self.stats:
            self.stats[name] = 0
        self.stats[name] += 1

    def run(self, Iterations):
        self._cm.oprofileStart()
        try:
            self.run_loop(Iterations)
            self._cm.oprofileStop()
        except:
            self._cm.oprofileStop()
            raise

    def run_loop(self, Iterations):
        raise ValueError("Abstract Class member (run_loop)")

    def run_test(self, test, testcount):
        nodechoice = self._cm.Env.random_node()

        ret = True
        did_run = False

        self._cm.instance_errorstoignore_clear()
        choice = "(%s)" % nodechoice
        self._cm.log("Running test {:<22} {:<15} [{:>3}]".format(test.name, choice, testcount))

        starttime = test.set_timer()
        if not test.setup(nodechoice):
            self._cm.log("Setup failed")
            ret = False

        elif not test.can_run_now(nodechoice):
            self._cm.log("Skipped")
            test.skipped()

        else:
            did_run = True
            ret = test(nodechoice)

        if not test.teardown(nodechoice):
            self._cm.log("Teardown failed")

            if not should_continue(self._cm.Env):
                raise ValueError("Teardown of %s on %s failed" % (test.name, nodechoice))

            ret = False

        stoptime = time.time()
        self._cm.oprofileSave(testcount)

        elapsed_time = stoptime - starttime
        test_time = stoptime - test.get_timer()
        if "min_time" not in test.stats:
            test.stats["elapsed_time"] = elapsed_time
            test.stats["min_time"] = test_time
            test.stats["max_time"] = test_time
        else:
            test.stats["elapsed_time"] += elapsed_time
            if test_time < test.stats["min_time"]:
                test.stats["min_time"] = test_time
            if test_time > test.stats["max_time"]:
                test.stats["max_time"] = test_time

        if ret:
            self.incr("success")
            test.log_timer()
        else:
            self.incr("failure")
            self._cm.statall()
            did_run = True  # Force the test count to be incremented anyway so test extraction works

        self.audit(test.errors_to_ignore)
        return did_run

    def summarize(self):
        self._cm.log("****************")
        self._cm.log("Overall Results:%r" % self.stats)
        self._cm.log("****************")

        stat_filter = {
            "calls":0,
            "failure":0,
            "skipped":0,
            "auditfail":0,
            }
        self._cm.log("Test Summary")
        for test in self.tests:
            for key in list(stat_filter.keys()):
                stat_filter[key] = test.stats[key]

            name = "Test %s:" % test.name
            self._cm.log("{:<25} {!r}".format(name, stat_filter))

        self._cm.debug("Detailed Results")
        for test in self.tests:
            name = "Test %s:" % test.name
            self._cm.debug("{:<25} {!r}".format(name, stat_filter))

        self._cm.log("<<<<<<<<<<<<<<<< TESTS COMPLETED")

    def audit(self, local_ignore=None):
        errcount = 0

        ignorelist = ["CTS:"]

        if local_ignore:
            ignorelist.extend(local_ignore)

        ignorelist.extend(self._cm.errorstoignore())
        ignorelist.extend(self._cm.instance_errorstoignore())

        # This makes sure everything is stabilized before starting...
        failed = 0
        for audit in self._audits:
            if not audit():
                self._cm.log("Audit %s FAILED." % audit.name)
                failed += 1
            else:
                self._cm.debug("Audit %s passed." % audit.name)

        while errcount < 1000:
            match = None
            if self._bad_news:
                match = self._bad_news.look(0)

            if match:
                add_err = True
                for ignore in ignorelist:
                    if add_err and re.search(ignore, match):
                        add_err = False
                if add_err:
                    self._cm.log("BadNews: %s" % match)
                    self.incr("BadNews")
                    errcount += 1
            else:
                break
        else:
            print("Big problems")
            if not should_continue(self._cm.Env):
                self._cm.log("Shutting down.")
                self.summarize()
                self.teardown()
                raise ValueError("Looks like we hit a BadNews jackpot!")

        if self._bad_news:
            self._bad_news.end()
        return failed


class AllOnce(Scenario):
    '''Every Test Once''' # Accessable as __doc__
    def run_loop(self, Iterations):
        testcount = 1
        for test in self.tests:
            self.run_test(test, testcount)
            testcount += 1


class RandomTests(Scenario):
    '''Random Test Execution'''
    def run_loop(self, Iterations):
        testcount = 1
        while testcount <= Iterations:
            test = self._cm.Env.random_gen.choice(self.tests)
            self.run_test(test, testcount)
            testcount += 1


class Sequence(Scenario):
    '''Named Tests in Sequence'''
    def run_loop(self, Iterations):
        testcount = 1
        while testcount <= Iterations:
            for test in self.tests:
                self.run_test(test, testcount)
                testcount += 1


class Boot(Scenario):
    '''Start the Cluster'''
    def run_loop(self, Iterations):
        testcount = 0


class BootCluster(ScenarioComponent):
    (
'''BootCluster is the most basic of ScenarioComponents.
This ScenarioComponent simply starts the cluster manager on all the nodes.
It is fairly robust as it waits for all nodes to come up before starting
as they might have been rebooted or crashed for some reason beforehand.
''')
    def is_applicable(self):
        '''BootCluster is so generic it is always Applicable'''
        return True

    def setup(self):
        '''Basic Cluster Manager startup.  Start everything'''

        self._cm.prepare()

        #        Clear out the cobwebs ;-)
        self._cm.stopall(verbose=True, force=True)

        # Now start the Cluster Manager on all the nodes.
        self._cm.log("Starting Cluster Manager on all nodes.")
        return self._cm.startall(verbose=True, quick=True)

    def teardown(self):
        '''Set up the given ScenarioComponent'''

        # Stop the cluster manager everywhere

        self._cm.log("Stopping Cluster Manager on all nodes")
        self._cm.stopall(verbose=True, force=False)


class LeaveBooted(BootCluster):
    def teardown(self):
        '''Set up the given ScenarioComponent'''

        # Stop the cluster manager everywhere

        self._cm.log("Leaving Cluster running on all nodes")
