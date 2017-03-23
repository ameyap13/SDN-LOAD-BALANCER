# Copyright 2011-2012 James McCauley
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
This code implements a L2 learning switch. We can use this code
on multiple switches. This code works on any topology but we have
modified this code to work on a triangle topology that has a loop. We use
openflow.discovery module with openflow.spanning_tree to handle the loop.
This will block one of the ports of one switch so that the loop is
removed. Once this is done, we are maintaining separate switch dictionaries.
These dictionaries map MAC addresses of each hosts to the particular ports
of the switch that are to be used to reach them from the switch. This is 
done for all the hosts/servers in the network, not only to the one's 
directly connected to the switch.Once this mapping is done, the controller
keeps polling each hosts to check if they are up or down. 
Once it is reported that a particular host is down, we immediately delete 
the entry of MAC address of this host from all the switch dictionaries.
This way we ensure that the MAC tables work dynamically. Also this takes 
care of new links added or old links re-added in the topology.
"""

from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.addresses import EthAddr
from pox.lib.revent import *
from pox.lib.recoco import Timer
from collections import defaultdict
from pox.lib.util import dpid_to_str
from pox.lib.util import str_to_bool
from pox.openflow.discovery import Discovery
import time
import threading
import os
import subprocess

log = core.getLogger()
PORT_PORT = 0
EVNT_MAC = ""
# We don't want to flood immediately when a switch connects.
# Can be overriden on commandline.
_flood_delay = 0

IP_TO_MAC = { "10.0.0.1" : EthAddr('00:00:00:00:00:01'), "10.0.0.2" : EthAddr('00:00:00:00:00:02'), "10.0.0.3" : EthAddr('00:00:00:00:00:03'), "10.0.0.4" : EthAddr('00:00:00:00:00:04'), "10.0.0.5" : EthAddr('00:00:00:00:00:05'), "10.0.0.6" : EthAddr('00:00:00:00:00:06'), "10.0.0.7" : EthAddr('00:00:00:00:00:07'), "10.0.0.8" : EthAddr('00:00:00:00:00:08'), "10.0.0.9" : EthAddr('00:00:00:00:00:09'), "10.0.0.10" : EthAddr('00:00:00:00:00:0a'), "10.0.0.11" : EthAddr('00:00:00:00:00:0b'), "10.0.0.12" : EthAddr('00:00:00:00:00:0c'), "10.0.0.13" : EthAddr('00:00:00:00:00:0d'), "10.0.0.14" : EthAddr('00:00:00:00:00:0e'), "10.0.0.15" : EthAddr('00:00:00:00:00:0f'), "10.0.0.16" : EthAddr('00:00:00:00:00:10')}


class LearningSwitch (object):
  """
  The learning switch "brain" associated with a single OpenFlow switch.

  When we see a packet, we'd like to output it on a port which will
  eventually lead to the destination.  To accomplish this, we build a
  table that maps addresses to ports.

  We populate the table by observing traffic.  When we see a packet
  from some source coming from some port, we know that source is out
  that port.

  When we want to forward traffic, we look up the desintation in our
  table.  If we don't know the port, we simply send the message out
  all ports except the one it came in on.  (In the presence of loops,
  this is bad!).

  In short, our algorithm looks like this:

  For each packet from the switch:
  1) Use source address and switch port to update address/port table
  2) Is transparent = False and either Ethertype is LLDP or the packet's
     destination address is a Bridge Filtered address?
     Yes:
        2a) Drop packet -- don't forward link-local traffic (LLDP, 802.1x)
            DONE
  3) Is destination multicast?
     Yes:
        3a) Flood the packet
            DONE
  4) Port for destination address in our address/port table?
     No:
        4a) Flood the packet
            DONE
  5) Is output port the same as input port?
     Yes:
        5a) Drop packet and similar ones for a while
  6) Install flow table entry in the switch so that this
     flow goes out the appopriate port
     6a) Send the packet out appropriate port
  """
  def __init__ (self, connection, transparent):
    # Switch we'll be adding L2 learning switch capabilities to
    self.connection = connection
    self.transparent = transparent

    # Our table
    self.macToPort = {}

    # We want to hear PacketIn messages, so we listen
    # to the connection
    connection.addListeners(self)

    # We just use this to know when to log a helpful message
    self.hold_down_expired = _flood_delay == 0

    switchlist.append(self)


  def _handle_PacketIn (self, event):
    """
    Handle packet in messages from the switch to implement above algorithm.
    """
    packet = event.parsed
    global PORT_PORT, EVNT_MAC

    def flood (message = None):
      """ Floods the packet """
      msg = of.ofp_packet_out()
      if time.time() - self.connection.connect_time >= _flood_delay:
        # Only flood if we've been connected for a little while...

        if self.hold_down_expired is False:
          # Oh yes it is!
          self.hold_down_expired = True
          log.info("%s: Flood hold-down expired -- flooding",
              dpid_to_str(event.dpid))

        if message is not None: log.debug(message)
        log.debug("%i: flood %s -> %s", event.dpid,packet.src,packet.dst)
        # OFPP_FLOOD is optional; on some switches you may need to change
        # this to OFPP_ALL.
        msg.actions.append(of.ofp_action_output(port = of.OFPP_FLOOD))
      else:
        pass
        # log.info("Holding down flood for %s", dpid_to_str(event.dpid))
      msg.data = event.ofp
      msg.in_port = event.port
      self.connection.send(msg)


    def drop (duration = None):
      """
      Drops this packet and optionally installs a flow to continue
      dropping similar ones for a while
      """
      if duration is not None:
        if not isinstance(duration, tuple):
          duration = (duration,duration)
        msg = of.ofp_flow_mod()
        msg.match = of.ofp_match.from_packet(packet)
        msg.idle_timeout = duration[0]
        msg.hard_timeout = duration[1]
        msg.buffer_id = event.ofp.buffer_id
        self.connection.send(msg)
      elif event.ofp.buffer_id is not None:
        msg = of.ofp_packet_out()
        msg.buffer_id = event.ofp.buffer_id
        msg.in_port = event.port
        self.connection.send(msg)
    PORT_PORT = event.port
    EVNT_MAC = packet.src

    self.macToPort[packet.src] = event.port # 1

    if not self.transparent: # 2
      if packet.type == packet.LLDP_TYPE or packet.dst.isBridgeFiltered():
        drop() # 2a
        return

    if packet.dst.is_multicast:
      flood() # 3a
    else:
      if packet.dst not in self.macToPort: # 4
        flood("Port for %s unknown -- flooding" % (packet.dst,)) # 4a
      else:
        port = self.macToPort[packet.dst]
        if port == event.port: # 5
          # 5a
          log.warning("Same port for packet from %s -> %s on %s.%s.  Drop."
              % (packet.src, packet.dst, dpid_to_str(event.dpid), port))
          drop(10)
          return
        # 6
        log.debug("installing flow for %s.%i -> %s.%i" %(packet.src, event.port, packet.dst, port))
        msg = of.ofp_flow_mod()
        msg.match = of.ofp_match.from_packet(packet, event.port)
        msg.idle_timeout = 10
        msg.hard_timeout = 30
        msg.actions.append(of.ofp_action_output(port = port))
        msg.data = event.ofp # 6a
        self.connection.send(msg)
        

switchlist = []
def printlist () :
  global switchlist
  threading.Timer(10.0,printlist).start()
  if len(switchlist) > 1 :
      for i in range(len(switchlist)) :
        print "Printing mactoport for switch" + str(i + 1) + ":-"
        print switchlist[i].macToPort 


def flush () :
  global IP_TO_MAC, switchlist, PORT_PORT, EVNT_MAC
  threading.Timer(10.0,flush).start()
  try:
    if len(switchlist) > 1 :
      for j in range(0,15):
        h1_ip = "10.0.0." + str(j+1) 
        pingcmd = "ping -c 1 " + h1_ip
        devnull = open(os.devnull, 'w')
        response = subprocess.call(pingcmd, shell=True, stdout=devnull)
        print "Got response {}, port: {}, mac: {}".format(response, PORT_PORT, EVNT_MAC)
        for i in range(len(switchlist)) :
          if response == 0:
            # ping successful
            print "Host is Up, Adding to dictionary if not present."
            if IP_TO_MAC[h1_ip] not in switchlist[i].macToPort:
              switchlist[i].macToPort[IP_TO_MAC[h1_ip]] = PORT_PORT
              IP_TO_MAC[h1_ip] = EVNT_MAC
          else:
            # ping failed. host is down
            print "For switch " + str(i+1)
            print IP_TO_MAC[h1_ip]
            print switchlist[i].macToPort
            if IP_TO_MAC[h1_ip] in switchlist[i].macToPort:
              del switchlist[i].macToPort[IP_TO_MAC[h1_ip]]
              print "Host is down, removing from dictionary."
  except KeyError:
    pass # ignore key errors in dictionary access

class l2_learning (EventMixin):
  """
  Waits for OpenFlow switches to connect and makes them learning switches.
  """
  def __init__ (self, transparent):
    def startup ():  
      core.openflow.addListeners(self) 
      core.openflow_discovery.addListeners(self) 
    core.call_when_ready(startup, ('openflow', 'openflow_discovery')) 
    self.transparent = transparent 


  def _handle_ConnectionUp (self, event):
    log.debug("Connection %s" % (event.connection,))

    LearningSwitch(event.connection, self.transparent)
    

def launch (transparent=False, hold_down=_flood_delay):
  """
  Starts an L2 learning switch.
  """
  try:
    global _flood_delay
    _flood_delay = int(str(hold_down), 10)
    assert _flood_delay >= 0
  except:
    raise RuntimeError("Expected hold-down to be a number")

  core.registerNew(l2_learning, str_to_bool(transparent))
  printlist()
  flush()
