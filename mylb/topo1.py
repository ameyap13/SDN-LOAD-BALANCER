"""Custom topology example

Two directly connected switches plus a host for each switch:

   host --- switch --- switch --- host

Adding the 'topos' dict with a key/value pair to generate our newly defined
topology enables one to pass in '--topo=mytopo' from the command line.
"""

from mininet.topo import Topo

class MyTopo( Topo ):
  "Custom Topo 1"

  def __init__( self ):
    "Create custom topo."

    # Initialize topology
    Topo.__init__( self )

     # Add hosts and switches
    leftHost0 = self.addHost( 'h1' )
    leftHost1 = self.addHost( 'h2' )
    leftHost2 = self.addHost( 'h3' )
    rightHost0 = self.addHost( 'h4' )
    rightHost1 = self.addHost( 'h5' )
    rightHost2 = self.addHost( 'h6' )

    leftSwitch = self.addSwitch( 's3' )
    rightSwitch = self.addSwitch( 's4' )

    # Add links
    self.addLink( leftHost0, leftSwitch )
    self.addLink( leftHost1, leftSwitch )
    self.addLink( leftHost2, leftSwitch )
    self.addLink( rightSwitch, rightHost0 )
    self.addLink( rightSwitch, rightHost1 )
    self.addLink( rightSwitch, rightHost2 )

    self.addLink( leftSwitch, rightSwitch )

topos = { 'mytopo': ( lambda: MyTopo() ) }
