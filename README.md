# OpenFlow Sandbox 
## CSC 573 - Internet Protocols

## Steps to run

+ Start mininet with this simple config:

	`$ sudo mn --topo single,3 --mac --switch ovsk --controller remote`

+ Start POX controller, using the rules in `pox\misc\of_tutorial.py` this:

	`$./pox.py log.level --DEBUG misc.of_tutorial`

	Change the path to run any other py file for controller.

+ Open xterm for each host. In mininet console, type:

	`xterm h1 h2 h3`

+ For host2 and host3, start tcpdump

	`tcpdump -XX -n -i h2-eth0` replace (h2 )interface address with correct one for respective host, like h3 or h1

+ Ping from host1 to others. Should be successful after 1st ping failure.

	`ping -c1 10.0.0.x` where x is number of dest host

+ To open our topology

	`sudo mn --custom ~/mininet/custom/our_topology.py --topo our_topology --mac --controller remote --arp`

+ To Start POX controller, using the rules in `pox\forwarding\ourtop_learning.py` this:

	`$./pox.py log.level --DEBUG forwarding.ourtop_learning openflow.discovery openflow.spanning_tree --no-flood --hold-down`

+ To create a large file
	`$ fallocate -l 100M 100Mfilename`

##Steps to Implement the Routing Algorithm 

+ Run the Controller: 

    `$./pox.py log.level --WARNING forwarding.ourtop_learning openflow.discovery openflow.spanning_tree --no-flood --hold-down`

+ Run the Topology :

    `sudo mn --custom ~/mininet/custom/our_topology.py --topo our_topology --mac --controller remote --arp --link tc`

+ Configure IP address to all the 3 Switches :

    `sudo ifconfig switch1 10.0.0.252`

    `sudo ifconfig switch2 10.0.0.253`

    `sudo ifconfig switch3 10.0.0.254`

    

## Steps to add a New Host 

+ Add new Host:

    `py net.addHost('h4')`

+ Add link between Switch and Host :

    `py net.addLink(switch1, net.get('h4'))`

+ Attach the switch interface:

    `py switch1.attach('switch1-eth7')`

+ Set the MAC address of the Host :

    `py h4.intf('h4-eth0').setMAC('00:00:00:00:00:0d')`

+ Set the IP address of the Host:

    `py h4.intf('h4-eth0').setIP('10.0.0.13/24')`



## Steps to run LoadBalancer (LB)
**Required**
Update the `pox/proto/arp_responder.py` file in the VM from the updated file in the repo

+ Mininet:

	`sudo mn --topo single,6 --mac --arp --controller remote`


+ POX: [LB IP addr we give here as 10.0.1.1, lb_dpid will be dpif of swtich on which LB runs]

	`./pox.py log.level --DEBUG misc.ip_loadbalancer --ip=10.0.1.1 --servers=10.0.0.1,10.0.0.2 --lb_dpid=3`
 	Add following flags if topology has loops:
 	`openflow.discovery openflow.spanning_tree --no-flood --hold-down` 

+ Start servers: [on h1/h2]

	`python -m SimpleHTTPServer 80`


+ Do request: [on h3-h6] Request will go to LB's IP addr

	`wget 10.0.1.1`


## What's next?

#### 1. ~~How to create mininet hosts with server-client model~~
How to run HTTP/FTP server on a host, and make it server requests from other hosts.

To run server in h1:
Run in h1:
`python -m SimpleHTTPServer 80`
or mininet> `h1 (python cmd as above)`

To download a file from h1:
Run in h2:
`wget <serverip>/<filename>`
OR 
`wget -O - 10.0.0.1` to get default server response on stdout


#### 2. Do load-balancing for specific topology

+ 1 ~~switch connected to multiple redundant servers, and multiple different client hosts~~
+ 2 multiple switches connected in linear fashion (no loops)
+ 3 multiple switches connected in ring (loop exists)
+ 4 Make LB server-aware. So servers going down, or new ones coming up are supported !
```
Right now for the servers it knows, if some go down, it can handle that fine. Then if it 
goes up again that is handled. If a new server is to be serviced at this LB, that is not handled yet,
as the list of servers is provided in the beginning. Do we need this?? 
```

#### 3. Do proper forwarding of packets in a triangle topology of 3 switches. 

Think about the following questions:

+ 3.a. ~~Determine the cost of edges?~~ Use `bw`, and `delay` parameter of links(TClinks)
+ 3.b. L2 or L3 forwarding?
+ 3.c. Subnets -> Same or Different?
+ 3.d. Discovery of switches and hosts?
+ 3.e. ~~STP?~~ Can use! 
+ 3.f. Changing of Bandwidth of the link - We could use by editing our topology file.


#### 4. Integrate LB with triangle topology, for final config.

+ integrate !


## Steps to perform forwarding and test it

1. Task 1 - create a static flow table and test if forwarding work s- on our_topology .
2. Task 2 - add link costs and test.
3. Task 3 - Create link failure and check if re-routing is taking place.


### Some mininet commands

`dumps` dumps all link info

`links` all link info

`nodes` node info

`net` for network info

`<host>/<switch> arp -n` Displays the ARP table of the host/switch ~~ The ARP table of the hosts is populated perfectly but not the switches 

`sudo ovs-ofctl show <switch>` Displays all the links parameter including speed and status 

`arping -c 1 -I h1-eth0 h2` arpping dest h2 from h1.

### Some Git commands

+ To Git clone

	`git clone <web link of our repository>`	Make sure you do this in the directory you want your git

	You will have to add your unity id as username and its password when prompted

+ To check status where your local repository stands in comparison to the online Git

	`git status`

+ To add your file to your local git repsitory

	`git add <filename>` 

+ To committ

	`git commit -m "Any comment on what your committed"` 

+ To pull files/changes

	`git pull -r`
	
+ To committ

	`git push -u origin master`	Do this just first time, next time you can just 'git push' 




## LB POX notes

Documentation [https://openflow.stanford.edu/display/ONL/POX+Wiki#POXWiki-proto.arp_responder](https://openflow.stanford.edu/display/ONL/POX+Wiki#POXWiki-proto.arp_responder)

	servers = array of IPAddr(ip of each server)
	ip = IPAddr object of LB ip addres

	proto.arp_responder - util to learn and proxy ARPs

Objects/Classes providing API register on `core`, and then can be called with that name by others.
	
	core.registerNew(iplb, event.connection, IPAddr(ip), servers)
    # this registers iplb class, and passes the following 3 as parameters to class constructor.

LB remembers `dpid` of first switch to connect, and then provides LB on only that in future events, ignoring other switches. Attaches event listeners on the `iplb` object. Done.


do_expire :: to expire probes and memorized flows

do_probe :: sends an ARP to a server to see if it still alive

	get a server to ping from `servers` list
	make a new arp type ethernet packet by setting all required attributes. 	
	add a timeout to the probe, store in dict of ip->timeout in `outstanding_probes`
	send it out



	on packetin event:
		get incoming port, and paket.parsed
		if tcp :
			if arp:
				if arp.reply type:
				then
					update the outstanding_probes dict
					update the live_servers dict - ignore if already found server, ADD if new server found.
					add as IP->mac,port to dict
		return drop packet if not tcp + arp (resends packet)

		if ip:
			if ip.srcip is known in servers list:
				extract key as srcip, dstip, srcport, dstport for TCP
				get entry from `memory`	
				   return drop packet (resends packet)

				refresh entry to reinstall it

			else if ip.dstip is loadbalancer's ip:
				~this packet needs to be LBed~
				extract key same as before, and get entry from memory for this key
				if entry is none, or entry.server not in live_Servers list:
					new possibly !
					pick server to send it to (LB strategy here! RR/WRR/random)
					create entry for it

				entry refresh/reinstall
				setup table entry towards seleced server
				setup actions, and create and install flowmod.

*LOG.level*
CRITICAL
ERROR
WARNING
INFO
DEBUG

#### Useful links

[Mininet Walkthrough](http://www.google.com/url?q=http%3A%2F%2Fmininet.org%2Fwalkthrough%2F%23link-updown&sa=D&sntz=1&usg=AFQjCNGHcivtlMaVPYeP7ZyxtTtbffVNlQ)

[How to identify different switches](http://www.google.com/url?q=http%3A%2F%2Fstackoverflow.com%2Fquestions%2F23114250%2Fhow-to-identify-a-specific-switch-in-mininet-when-connected-to-a-pox-controller&sa=D&sntz=1&usg=AFQjCNFXi1OG4Whf5rqfAyEU7k4V_SvQFg)

[Topology changes on-the-fly!](http://www.google.com/url?q=http%3A%2F%2Fwww.kiranvemuri.info%2Fdynamic-topology-changes-in-mininet-advanced-users%2F&sa=D&sntz=1&usg=AFQjCNFEGMLuaRI2U0QVCpwtbEUhL9h0vA)
