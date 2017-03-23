#!/usr/bin/python
from pox.core import core
from pox.lib.util import dpid_to_str
from pox.lib.revent import *

log = core.getLogger()

class ConnectionUp(Event):
    def __init__(self,connection,ofp):
        Event.__init__(self)
        self.connection = connection
        self.dpid = connection.dpid
        self.ofp = ofp
class ConnectionDown(Event):
    def __init__(self,connection,ofp):
        Event.__init__(self)
        self.connection = connection
        self.dpid = connection.dpid

class MyComponent(object):
    def __init__(self):
        core.openflow.addListeners(self)

    def _handle_ConnectionUp(self,event):
        ConnectionUp(event.connection,event.ofp)
        log.info("Switch %s has come up.",dpid_to_str(event.dpid))

    def _handle_ConnectionDown(self,event):
        ConnectionDown(event.connection,event.dpid)
        log.info("Switch %s has shutdown.",dpid_to_str(event.dpid))

def launch():
    core.registerNew(MyComponent)
    