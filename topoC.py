"""This is 'our_toplogy' for this project
Three directly connected switches plus a host and three servers for each switch.
Adding the 'topos' dict with a key/value pair to generate 'our_toplogy'
enables one to pass in '--topo=our_topology' from the command line.
"""

from mininet.topo import Topo

class MyTopo( Topo ):

    def __init__( self ):

        # Initializing topology
        Topo.__init__( self )

        # Adding hosts, servers and switches
        host1 = self.addHost( 'h1' )
        host2 = self.addHost( 's1a' )
        host3 = self.addHost( 's1b' )
        host4 = self.addHost( 's1c' )
        host5 = self.addHost( 'h2' )
        host6 = self.addHost( 's2a' )
        host7 = self.addHost( 's2b' )
        host8 = self.addHost( 's2c' )
        host9 = self.addHost( 'h3' )
        host10 = self.addHost( 's3a' )
        host11 = self.addHost( 's3b' )
        host12 = self.addHost( 's3c' )
        switch1 = self.addSwitch( 'switch1' )
        switch2 = self.addSwitch( 'switch2' )
        switch3 = self.addSwitch( 'switch3' )
        linkopts = dict(bw=100)
        
        # (or you can use brace syntax: linkopts = {'bw':10, 'delay':'5ms', ... } )
        


        
        # Adding links
        self.addLink( host1, switch1 , **linkopts)
        self.addLink( host2, switch1 , **linkopts)
        self.addLink( host3, switch1 , bw=50)
        self.addLink( host4, switch1 , bw=25)
        self.addLink( switch1, switch2 , bw=100)
        self.addLink( host5, switch2, **linkopts)
        self.addLink( host6, switch2 , **linkopts)
        self.addLink( host7, switch2 , **linkopts)
        self.addLink( host8, switch2 , **linkopts)
        self.addLink( switch2, switch3 , **linkopts)
        self.addLink( host9, switch3 , **linkopts)
        self.addLink( host10, switch3, **linkopts )        
        self.addLink( host11, switch3, **linkopts )
        self.addLink( host12, switch3 , **linkopts)
        self.addLink( switch3, switch1, **linkopts )

topos = { 'our_topology': ( lambda: MyTopo() ) }