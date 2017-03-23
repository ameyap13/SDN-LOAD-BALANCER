# Copyright 2013 James McCauley
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
A very sloppy IP load balancer.

Run it with --ip=<Service IP> --servers=IP1,IP2,...

Please submit improvements. :)
"""

from pox.core import core
import pox
log = core.getLogger("iplb")

from pox.lib.packet.ethernet import ethernet, ETHER_BROADCAST
from pox.lib.packet.ipv4 import ipv4
from pox.lib.packet.arp import arp
from pox.lib.addresses import IPAddr, EthAddr
from pox.lib.util import str_to_bool, dpid_to_str

import pox.openflow.libopenflow_01 as of

import time
import random

FLOW_IDLE_TIMEOUT = 10
FLOW_MEMORY_TIMEOUT = 60 * 5

CURRENT_RR_INDEX = 0


class MemoryEntry (object):
  """
  Record for flows we are balancing

  Table entries in the switch "remember" flows for a period of time, but
  rather than set their expirations to some long value (potentially leading
  to lots of rules for dead connections), we let them expire from the
  switch relatively quickly and remember them here in the controller for
  longer.

  Another tactic would be to increase the timeouts on the switch and use
  the Nicira extension which can match packets with FIN set to remove them
  when the connection closes.
  """
  def __init__ (self, server, first_packet, client_port):
    self.server = server
    self.first_packet = first_packet
    self.client_port = client_port
    self.refresh()

  def refresh (self):
    self.timeout = time.time() + FLOW_MEMORY_TIMEOUT

  @property
  def is_expired (self):
    return time.time() > self.timeout

  @property
  def key1 (self):
    ethp = self.first_packet
    ipp = ethp.find('ipv4')
    tcpp = ethp.find('tcp')

    return ipp.srcip,ipp.dstip,tcpp.srcport,tcpp.dstport

  @property
  def key2 (self):
    ethp = self.first_packet
    ipp = ethp.find('ipv4')
    tcpp = ethp.find('tcp')

    return self.server,ipp.srcip,tcpp.dstport,tcpp.srcport


class iplb (object):
  """
  A simple IP load balancer

  Give it a service_ip and a list of server IP addresses.  New TCP flows
  to service_ip will be randomly redirected to one of the servers.

  We probe the servers to see if they're alive by sending them ARPs.
  """
  def __init__ (self, connection, service_ip, servers = []):
    self.service_ip = IPAddr(service_ip)
    self.servers = [IPAddr(a) for a in servers]
    self.con = connection
    self.mac = self.con.eth_addr
    self.live_servers = {} # IP -> MAC,port

    try:
      self.log = log.getChild(dpid_to_str(self.con.dpid))
    except:
      # Be nice to Python 2.6 (ugh)
      self.log = log

    self.outstanding_probes = {} # IP -> expire_time

    # How quickly do we probe?
    self.probe_cycle_time = 5

    # How long do we wait for an ARP reply before we consider a server dead?
    self.arp_timeout = 3

    # We remember where we directed flows so that if they start up again,
    # we can send them to the same server if it's still up.  Alternate
    # approach: hashing.
    self.memory = {} # (srcip,dstip,srcport,dstport) -> MemoryEntry

    self._do_probe() # Kick off the probing

    # As part of a gross hack, we now do this from elsewhere
    self.con.addListeners(self)

  def _do_expire (self):
    """
    Expire probes and "memorized" flows

    Each of these should only have a limited lifetime.
    """
    t = time.time()

    # Expire probes
    for ip,expire_at in self.outstanding_probes.items():
      if t > expire_at:
        self.outstanding_probes.pop(ip, None)
        if ip in self.live_servers:
          self.log.warn("Server %s down", ip)
          del self.live_servers[ip]

    # Expire old flows
    c = len(self.memory)
    self.memory = {k:v for k,v in self.memory.items()
                   if not v.is_expired}
    if len(self.memory) != c:
      self.log.debug("Expired %i flows", c-len(self.memory))

  def _do_probe (self):
    """
    Send an ARP to a server to see if it's still up
    """
    self._do_expire()

    server = self.servers.pop(0)
    self.servers.append(server)

    r = arp()
    r.hwtype = r.HW_TYPE_ETHERNET
    r.prototype = r.PROTO_TYPE_IP
    r.opcode = r.REQUEST
    r.hwdst = ETHER_BROADCAST
    r.protodst = server
    r.hwsrc = self.mac
    r.protosrc = self.service_ip
    e = ethernet(type=ethernet.ARP_TYPE, src=self.mac,
                 dst=ETHER_BROADCAST)
    e.set_payload(r)
    #self.log.debug("ARPing for %s", server)
    msg = of.ofp_packet_out()
    msg.data = e.pack()
    msg.actions.append(of.ofp_action_output(port = of.OFPP_FLOOD))
    msg.in_port = of.OFPP_NONE
    self.con.send(msg)

    self.outstanding_probes[server] = time.time() + self.arp_timeout

    core.callDelayed(self._probe_wait_time, self._do_probe)

  @property
  def _probe_wait_time (self):
    """
    Time to wait between probes
    """
    r = self.probe_cycle_time / float(len(self.servers))
    r = max(.25, r) # Cap it at four per second
    return r

  def _pick_server (self, key, inport):
    global CURRENT_RR_INDEX
    print self.live_servers.keys()
    try:
      ch = self.live_servers.keys()[CURRENT_RR_INDEX]
      CURRENT_RR_INDEX += 1
      return ch
    except:
      CURRENT_RR_INDEX = 0
      ch = self.live_servers.keys()[CURRENT_RR_INDEX]
      CURRENT_RR_INDEX += 1
      return ch
    # ch = random.choice(self.live_servers.keys())

  def _handle_PacketIn (self, event):
    inport = event.port
    packet = event.parsed

    def drop ():
      if event.ofp.buffer_id is not None:
        # Kill the buffer
        msg = of.ofp_packet_out(data = event.ofp)
        self.con.send(msg)
      return None

    tcpp = packet.find('tcp')
    if not tcpp:
      arpp = packet.find('arp')
      if arpp:
        # Handle replies to our server-liveness probes
        if arpp.opcode == arpp.REPLY:
          if arpp.protosrc in self.outstanding_probes:
            # A server is (still?) up; cool.
            del self.outstanding_probes[arpp.protosrc]
            if (self.live_servers.get(arpp.protosrc, (None,None))
                == (arpp.hwsrc,inport)):
              # Ah, nothing new here.
              pass
            else:
              # Ooh, new server.
              self.live_servers[arpp.protosrc] = arpp.hwsrc,inport
              self.log.info("Server %s up", arpp.protosrc)
        return

      # Not TCP and not ARP.  Don't know what to do with this.  Drop it.
      return drop()

    # It's TCP.
    
    ipp = packet.find('ipv4')

    if ipp.srcip in self.servers:
      # It's FROM one of our balanced servers.
      # Rewrite it BACK to the client

      key = ipp.srcip,ipp.dstip,tcpp.srcport,tcpp.dstport
      entry = self.memory.get(key)

      if entry is None:
        # We either didn't install it, or we forgot about it.
        self.log.debug("No client for %s", key)
        return drop()

      # Refresh time timeout and reinstall.
      entry.refresh()

      #self.log.debug("Install reverse flow for %s", key)

      # Install reverse table entry
      mac,port = self.live_servers[entry.server]

      actions = []
      actions.append(of.ofp_action_dl_addr.set_src(self.mac))
      actions.append(of.ofp_action_nw_addr.set_src(self.service_ip))
      actions.append(of.ofp_action_output(port = entry.client_port))
      match = of.ofp_match.from_packet(packet, inport)

      msg = of.ofp_flow_mod(command=of.OFPFC_ADD,
                            idle_timeout=FLOW_IDLE_TIMEOUT,
                            hard_timeout=of.OFP_FLOW_PERMANENT,
                            data=event.ofp,
                            actions=actions,
                            match=match)
      self.con.send(msg)

    elif ipp.dstip == self.service_ip:
      # Ah, it's for our service IP and needs to be load balanced

      # Do we already know this flow?
      key = ipp.srcip,ipp.dstip,tcpp.srcport,tcpp.dstport
      entry = self.memory.get(key)
      if entry is None or entry.server not in self.live_servers:
        # Don't know it (hopefully it's new!)
        if len(self.live_servers) == 0:
          self.log.warn("No servers!")
          return drop()

        # Pick a server for this flow
        server = self._pick_server(key, inport)
        # print serverlist
        # server = serverlist[0]
        # self.log.debug("Received server: %s", server)
        self.log.debug("Directing traffic to %s", server)
        entry = MemoryEntry(server, packet, inport)
        self.log.debug("Looked up entry server %s", entry.server)
        self.memory[entry.key1] = entry
        self.memory[entry.key2] = entry
   
      # Update timestamp
      entry.refresh()

      # Set up table entry towards selected server
      mac,port = self.live_servers[entry.server]

      actions = []
      actions.append(of.ofp_action_dl_addr.set_dst(mac))
      actions.append(of.ofp_action_nw_addr.set_dst(entry.server))
      actions.append(of.ofp_action_output(port = port))
      match = of.ofp_match.from_packet(packet, inport)

      msg = of.ofp_flow_mod(command=of.OFPFC_ADD,
                            idle_timeout=FLOW_IDLE_TIMEOUT,
                            hard_timeout=of.OFP_FLOW_PERMANENT,
                            data=event.ofp,
                            actions=actions,
                            match=match)
      self.con.send(msg)


# Remember which DPID we're operating on (first one to connect)
_dpid = None

# hardcoding multi switch settings
iplist = ["10.0.1.1", "10.0.1.2"]
serverlist = ["10.0.0.1,10.0.0.2","10.0.0.4,10.0.0.5"]
dpidlist=["3","4"]
LBinited = [0, 0]

iplb_list = list()

# hardcoding single switch settings
# iplist = ["10.0.1.1"]
# serverlist = ["10.0.0.1,10.0.0.2"]
# dpidlist=["3"]

from proto.arp_responder import launch as arp_launch
import logging


# launch ARP reponder for the passed switch. the LB is launched elsewhere on connection Up event.
def launchLB(service_ip, service_servers, sw_dpid):
  try:
    # service_servers = service_servers.replace(","," ").split()
    # servers = [IPAddr(x) for x in service_servers]
    ip = IPAddr(service_ip)
    _dpid = sw_dpid

    objname = "arp_resp_"+_dpid
    arp_launch(eat_packets=False,objname=objname,**{str(ip):True})
    logging.getLogger("proto.arp_responder").setLevel(logging.WARN)

    # log.info("IP Load Balancer Ready for Switch %s", _dpid)
    # core.registerNew(iplb, event.connection, IPAddr(ip), servers)
    # log.info("Load Balancing on %s", _dpid)

  except Exception as ex:
    print ex 



# this will launch the LB object for each switch, reading from hardcoded array values above
def launch (ip=None, servers=None, switch_dpid=None):
  global iplist, serverlist, dpidlist, iplb_list, LBinited
  print iplist
  print serverlist
  print dpidlist

  for i in range(len(iplist)):
    launchLB(iplist[i], serverlist[i], dpidlist[i])

  # global _dpid
  # try:

  #   servers = servers.replace(","," ").split()
  #   servers = [IPAddr(x) for x in servers]
  #   ip = IPAddr(ip)
  #   # _dpid = switch_dpid

  #   # Boot up ARP Responder
  #   from proto.arp_responder import launch as arp_launch
  #   arp_launch(eat_packets=False,**{str(ip):True})
  #   import logging
  #   logging.getLogger("proto.arp_responder").setLevel(logging.WARN)
    
    def _handle_ConnectionUp (event):
      global iplist, serverlist, dpidlist, iplb_list, LBinited
      print "Event in from dpid: " + str(event.dpid)

      if str(event.dpid) in dpidlist:
        idx = dpidlist.index(str(event.dpid))
        temp_service_servers = serverlist[idx]
        temp_service_servers = temp_service_servers.replace(","," ").split()
        servers = [IPAddr(x) for x in temp_service_servers]

        # core.registerNew(iplb, event.connection, IPAddr(iplist[idx]), servers)
        if (LBinited[i] != 1):
          iplb_obj = iplb(event.connection, IPAddr(iplist[idx]), servers)
          lb_component_name = "iplb_"+str(event.dpid)
          core.register(lb_component_name, iplb_obj) # todo register component with some name, and then invoke funcs on that obj
          iplb_list.append(lb_component_name) #add this component name to list
          LBinited[i] = 1

        log.info("Load Balancing on %s", event.dpid)
      else:
        log.warn("this dpid %s not found in dpid list!", event.dpid)

  #     global _dpid
  #     if _dpid is None:
  #       log.info("IP Load Balancer Ready.")
  #       core.registerNew(iplb, event.connection, IPAddr(ip), servers)
  #       # if switch not specified in params, then LB the first switch which connects
  #       # else set it to the passed value in params
  #       if (switch_dpid is None):
  #         _dpid = event.dpid
  #       else:
  #         _dpid = switch_dpid

  #     if str(_dpid) != str(event.dpid):
  #       log.warn("Ignoring switch %s. Needed dpid: %s, found in event: %s", event.connection, _dpid, event.dpid)
  #     else:
  #       log.info("Load Balancing on %s", event.connection)

  #       '''
  #       # Gross hack
  #       # core.iplb.con = event.connection
  #       # event.connection.addListeners(core.iplb)
  #       '''

  # except Exception as ex:
  #   print ex 


  core.openflow.addListenerByName("ConnectionUp", _handle_ConnectionUp)
