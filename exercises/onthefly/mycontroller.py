#!/usr/bin/env python2
import argparse
import grpc
import os
import sys
from time import sleep

# Import P4Runtime lib from parent utils dir
# Probably there's a better way of doing this.
sys.path.append(
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 '../../utils/'))
import p4runtime_lib.bmv2
from p4runtime_lib.error_utils import printGrpcError
from p4runtime_lib.switch import ShutdownAllSwitchConnections
import p4runtime_lib.helper

SWITCH_TO_HOST_PORT = 1
SWITCH_TO_SWITCH_PORT = 2


def writeTunnelRules(p4info_helper, ingress_sw, egress_sw, tunnel_id,
                     dst_eth_addr, dst_ip_addr):
    """
    Installs three rules:
    1) An tunnel ingress rule on the ingress switch in the ipv4_lpm table that
       encapsulates traffic into a tunnel with the specified ID
    2) A transit rule on the ingress switch that forwards traffic based on
       the specified ID
    3) An tunnel egress rule on the egress switch that decapsulates traffic
       with the specified ID and sends it to the host

    :param p4info_helper: the P4Info helper
    :param ingress_sw: the ingress switch connection
    :param egress_sw: the egress switch connection
    :param tunnel_id: the specified tunnel ID
    :param dst_eth_addr: the destination IP to match in the ingress rule
    :param dst_ip_addr: the destination Ethernet address to write in the
                        egress rule
    """
    # 1) Tunnel Ingress Rule
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.ipv4_lpm",
        match_fields={
            "hdr.ipv4.dstAddr": (dst_ip_addr, 32)
        },
        action_name="MyIngress.myTunnel_ingress",
        action_params={
            "dst_id": tunnel_id,
        })
    ingress_sw.WriteTableEntry(table_entry)
    print "Installed ingress tunnel rule on %s" % ingress_sw.name

    # 2) Tunnel Transit Rule
    # The rule will need to be added to the myTunnel_exact table and match on
    # the tunnel ID (hdr.myTunnel.dst_id). Traffic will need to be forwarded
    # using the myTunnel_forward action on the port connected to the next switch.
    #
    # For our simple topology, switch 1 and switch 2 are connected using a
    # link attached to port 2 on both switches. We have defined a variable at
    # the top of the file, SWITCH_TO_SWITCH_PORT, that you can use as the output
    # port for this action.
    #
    # We will only need a transit rule on the ingress switch because we are
    # using a simple topology. In general, you'll need on transit rule for
    # each switch in the path (except the last switch, which has the egress rule),
    # and you will need to select the port dynamically for each switch based on
    # your topology.

    # TODO build the transit rule
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.myTunnel_exact",
        match_fields={
            "hdr.myTunnel.dst_id": tunnel_id
        },
        action_name="MyIngress.myTunnel_forward",
        action_params={
            "port": SWITCH_TO_SWITCH_PORT,
        })
    # TODO install the transit rule on the ingress switch
    ingress_sw.WriteTableEntry(table_entry)
    print "Installed transit tunnel rule on %s" % ingress_sw.name

    # 3) Tunnel Egress Rule
    # For our simple topology, the host will always be located on the
    # SWITCH_TO_HOST_PORT (port 1).
    # In general, you will need to keep track of which port the host is
    # connected to.
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.myTunnel_exact",
        match_fields={
            "hdr.myTunnel.dst_id": tunnel_id
        },
        action_name="MyIngress.myTunnel_egress",
        action_params={
            "dstAddr": dst_eth_addr,
            "port": SWITCH_TO_HOST_PORT
        })
    egress_sw.WriteTableEntry(table_entry)
    print "Installed egress tunnel rule on %s" % egress_sw.name


def writeMRIRules(p4info_helper, s1, s2):
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.ipv4_lpm",
        match_fields={
            "hdr.ipv4.dstAddr": ("10.0.2.0", 24)
        },
        action_name="MyIngress.ipv4_forward",
        action_params={
            "dstAddr": "00:00:00:02:03:00",
            "port": 2
        })
    s1.WriteTableEntry(table_entry)
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.ipv4_lpm",
        match_fields={
            "hdr.ipv4.dstAddr": ("10.0.1.1", 32)
        },
        action_name="MyIngress.ipv4_forward",
        action_params={
            "dstAddr": "00:00:00:00:01:01",
            "port": 1
        })
    s1.WriteTableEntry(table_entry)
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyEgress.swtrace",
        default_action=True,
        action_name="MyEgress.add_swtrace",
        action_params={
            "swid": 1
        })
    s1.WriteTableEntry(table_entry)
    print "Installed rules on s1"

    ### s2
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.ipv4_lpm",
        match_fields={
            "hdr.ipv4.dstAddr": ("10.0.1.0", 24)
        },
        action_name="MyIngress.ipv4_forward",
        action_params={
            "dstAddr": "00:00:00:01:03:00",
            "port": 2
        })
    s2.WriteTableEntry(table_entry)
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.ipv4_lpm",
        match_fields={
            "hdr.ipv4.dstAddr": ("10.0.2.2", 32)
        },
        action_name="MyIngress.ipv4_forward",
        action_params={
            "dstAddr": "00:00:00:00:02:02",
            "port": 1
        })
    s2.WriteTableEntry(table_entry)
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyEgress.swtrace",
        default_action=True,
        action_name="MyEgress.add_swtrace",
        action_params={
            "swid": 2
        })
    s2.WriteTableEntry(table_entry)
    print "Installed rules on s2"

def readTableRules(p4info_helper, sw):
    """
    Reads the table entries from all tables on the switch.

    :param p4info_helper: the P4Info helper
    :param sw: the switch connection
    """
    print '\n----- Reading tables rules for %s -----' % sw.name
    for response in sw.ReadTableEntries():
        for entity in response.entities:
            entry = entity.table_entry
            # TODO For extra credit, you can use the p4info_helper to translate
            #      the IDs in the entry to names
            table_name = p4info_helper.get_tables_name(entry.table_id)
            print '%s: ' % table_name,
            for m in entry.match:
                print p4info_helper.get_match_field_name(table_name, m.field_id),
                print '%r' % (p4info_helper.get_match_field_value(m),),
            action = entry.action.action
            action_name = p4info_helper.get_actions_name(action.action_id)
            print '->', action_name,
            for p in action.params:
                print p4info_helper.get_action_param_name(action_name, p.param_id),
                print '%r' % p.value,
            print


def printCounter(p4info_helper, sw, counter_name, index):
    """
    Reads the specified counter at the specified index from the switch. In our
    program, the index is the tunnel ID. If the index is 0, it will return all
    values from the counter.

    :param p4info_helper: the P4Info helper
    :param sw:  the switch connection
    :param counter_name: the name of the counter from the P4 program
    :param index: the counter index (in our case, the tunnel ID)
    """
    for response in sw.ReadCounters(p4info_helper.get_counters_id(counter_name), index):
        for entity in response.entities:
            counter = entity.counter_entry
            print "%s %s %d: %d packets (%d bytes)" % (
                sw.name, counter_name, index,
                counter.data.packet_count, counter.data.byte_count
            )

def main(p4info_file_path, bmv2_file_path):
    exit_flag = False

    # Instantiate a P4Runtime helper from the p4info file
    p4info_helper = p4runtime_lib.helper.P4InfoHelper(p4info_file_path)
    pi_helper_mri = p4runtime_lib.helper.P4InfoHelper('./build/mri.p4info')

    try:
        # Create a switch connection object for s1 and s2;
        # this is backed by a P4Runtime gRPC connection.
        # Also, dump all P4Runtime messages sent to switch to given txt files.
        s1 = p4runtime_lib.bmv2.Bmv2SwitchConnection(
            name='s1',
            address='127.0.0.1:50051',
            device_id=0,
            proto_dump_file='logs/s1-p4runtime-requests.txt')
        s2 = p4runtime_lib.bmv2.Bmv2SwitchConnection(
            name='s2',
            address='127.0.0.1:50052',
            device_id=1,
            proto_dump_file='logs/s2-p4runtime-requests.txt')

        # Send master arbitration update message to establish this controller as
        # master (required by P4Runtime before performing any other write operation)
        s1.MasterArbitrationUpdate()
        s2.MasterArbitrationUpdate()

        # Install the P4 program on the switches
        s1.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                       bmv2_json_file_path=bmv2_file_path)
        print "Installed basic tunnel P4 Program using SetForwardingPipelineConfig on s1"
        s2.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                       bmv2_json_file_path=bmv2_file_path)
        print "Installed basic tunnel P4 Program using SetForwardingPipelineConfig on s2"

        # Write the rules that tunnel traffic from h1 to h2
        writeTunnelRules(p4info_helper, ingress_sw=s1, egress_sw=s2, tunnel_id=100,
                         dst_eth_addr="00:00:00:00:02:02", dst_ip_addr="10.0.2.2")

        # Write the rules that tunnel traffic from h2 to h1
        writeTunnelRules(p4info_helper, ingress_sw=s2, egress_sw=s1, tunnel_id=200,
                         dst_eth_addr="00:00:00:00:01:01", dst_ip_addr="10.0.1.1")

        # TODO Uncomment the following two lines to read table entries from s1 and s2
        readTableRules(p4info_helper, s1)
        readTableRules(p4info_helper, s2)

        print "Change modes with:"
        print " > load tunnel"
        print " -or- "
        print " > load mri"
        print "Type 'exit' to exit"

        # Print the tunnel counters every 2 seconds
        while not exit_flag:
            user_input = raw_input("controller> ")
            if user_input == "exit":
                exit_flag = True
                print " Shutting down."
            elif user_input == "load tunnel":
                s1.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                               bmv2_json_file_path=bmv2_file_path)
                print "Installed basic tunnel P4 Program using SetForwardingPipelineConfig on s1"
                s2.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                               bmv2_json_file_path=bmv2_file_path)
                print "Installed basic tunnel P4 Program using SetForwardingPipelineConfig on s2"

                writeTunnelRules(p4info_helper, ingress_sw=s1, egress_sw=s2, tunnel_id=100,
                                 dst_eth_addr="00:00:00:00:02:02", dst_ip_addr="10.0.2.2")

                writeTunnelRules(p4info_helper, ingress_sw=s2, egress_sw=s1, tunnel_id=200,
                                 dst_eth_addr="00:00:00:00:01:01", dst_ip_addr="10.0.1.1")

                readTableRules(p4info_helper, s1)
                readTableRules(p4info_helper, s2)
            elif user_input == "load mri":
                print "Changing P4 app in switches.."
                # Install the P4 program on the switches
                s1.SetForwardingPipelineConfig(p4info=pi_helper_mri.p4info,
                                               bmv2_json_file_path='./build/mri.json')
                print "Installed MRI P4 Program using SetForwardingPipelineConfig on s1"
                s2.SetForwardingPipelineConfig(p4info=pi_helper_mri.p4info,
                                               bmv2_json_file_path='./build/mri.json')
                print "Installed MRI P4 Program using SetForwardingPipelineConfig on s2"
                writeMRIRules(pi_helper_mri, s1, s2)
                readTableRules(pi_helper_mri, s1)
                readTableRules(pi_helper_mri, s2)
            else:
                print "option does not exist!"

    except KeyboardInterrupt:
        print " Shutting down."
    except grpc.RpcError as e:
        printGrpcError(e)

    ShutdownAllSwitchConnections()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='P4Runtime Controller')
    parser.add_argument('--p4info', help='p4info proto in text format from p4c',
                        type=str, action="store", required=False,
                        default='./build/advanced_tunnel.p4info')
    parser.add_argument('--bmv2-json', help='BMv2 JSON file from p4c',
                        type=str, action="store", required=False,
                        default='./build/advanced_tunnel.json')
    args = parser.parse_args()

    if not os.path.exists(args.p4info):
        parser.print_help()
        print "\np4info file not found: %s\nHave you run 'make'?" % args.p4info
        parser.exit(1)
    if not os.path.exists(args.bmv2_json):
        parser.print_help()
        print "\nBMv2 JSON file not found: %s\nHave you run 'make'?" % args.bmv2_json
        parser.exit(1)
    main(args.p4info, args.bmv2_json)
