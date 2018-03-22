#!/usr/bin/env python
# coding=utf-8
#
# Copyright © 2018 VMware, Inc. All Rights Reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and
# to permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions
# of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED
# TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
# CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.

__author__ = 'yasensim'


import requests, time
try:
    from com.vmware.nsx.fabric.nodes_client import Status
#    from com.vmware.nsx.fabric_client import Nodes
#    from com.vmware.nsx.model_client import Node
    from com.vmware.nsx.model_client import HostNode
    from com.vmware.nsx_client import TransportNodes
    from com.vmware.nsx_client import TransportZones
    from com.vmware.nsx_client import HostSwitchProfiles
    from com.vmware.nsx.model_client import TransportZone
    from com.vmware.nsx.model_client import TransportZoneEndPoint
    from com.vmware.nsx.model_client import TransportNode
    from com.vmware.nsx.model_client import HostSwitchSpec
    from com.vmware.nsx.model_client import HostSwitch
    from com.vmware.nsx.model_client import HostSwitchProfileTypeIdEntry
    from com.vmware.nsx.model_client import UplinkHostSwitchProfile
    from com.vmware.nsx.model_client import Pnic

    from com.vmware.vapi.std.errors_client import NotFound
    from vmware.vapi.lib import connect
    from vmware.vapi.security.user_password import \
        create_user_password_security_context
    from vmware.vapi.stdlib.client.factories import StubConfigurationFactory
    from com.vmware.nsx.model_client import ApiError
    from com.vmware.vapi.std.errors_client import Error
    HAS_PYNSXT = True
except ImportError:
    HAS_PYNSXT = False


def getTransportZoneEndPoint(module, stub_config):
    tz_endpoints = []
    transportzones_svc = TransportZones(stub_config)
    try:
        tzs = transportzones_svc.list()
    except Error as ex:
        api_error = ex.data.convert_to(ApiError)
        module.exit_json(changed=False, message="Error listing Transport Zones: "%(api_error))

    for tz_name in module.params['transport_zone_endpoints']:
        for vs in tzs.results:
            fn = vs.convert_to(TransportZone)
            if fn.display_name == tz_name:
                ep=TransportZoneEndPoint(transport_zone_id=fn.id)
                tz_endpoints.append(ep)
    return tz_endpoints

def getUplinkProfileId(module, stub_config):
    hsp_svc = HostSwitchProfiles(stub_config)
    try:
        hsps = hsp_svc.list()
    except Error as ex:
        api_error = ex.data.convert_to(ApiError)
        module.exit_json(changed=False, message="Error listing Transport Zones: "%(api_error))

    for vs in hsps.results:
        fn = vs.convert_to(UplinkHostSwitchProfile)
        if fn.display_name == module.params['uplink_profile']:
            return fn.id

def createTransportNode(module, stub_config):
    tz_endpoints=getTransportZoneEndPoint(module, stub_config)
    uplink_profile_id=getUplinkProfileId(module, stub_config)
    hsptie=HostSwitchProfileTypeIdEntry(
        key=HostSwitchProfileTypeIdEntry.KEY_UPLINKHOSTSWITCHPROFILE,
        value=uplink_profile_id
    )
    hsprof_list = []
    hsprof_list.append(hsptie)

    pnic_list = []
    for key, value in module.params["pnics"].items():
        pnic=Pnic(device_name=value, uplink_name=key)
        pnic_list.append(pnic)

    hs=HostSwitch(
        host_switch_name=module.params["host_switch_name"],
        host_switch_profile_ids=hsprof_list,
        pnics=pnic_list,
        static_ip_pool_id=module.params["static_ip_pool_id"]
    )
    hs_list= []
    hs_list.append(hs)
    tn_svc = TransportNodes(stub_config)
    transport_node=TransportNode(
        display_name=module.params['display_name'],
        host_switches=hs_list,
        node_id=module.params['node_id'],
        transport_zone_endpoints=tz_endpoints
    )
    try:
        rs = tn_svc.create(transport_node)
    except Error as ex:
        api_error = ex.data.convert_to(ApiError)
        module.exit_json(changed=False, message="API Error creating Transport Node: "%(api_error))
    return rs


def listTransportNodes(module, stub_config):
    try:
        fabricnodes_svc = TransportNodes(stub_config)
    except Error as ex:
        api_error = ex.data.convert_to(ApiError)
        module.fail_json(msg='API Error listing nodes: %s'%(api_error.error_message))
    return fabricnodes_svc.list()


def getTransportNodeByName(module, stub_config):
    result = listTransportNodes(module, stub_config)
    for vs in result.results:
        fn = vs.convert_to(TransportNode)
        if fn.display_name == module.params['display_name']:
            return fn
    return None

def deleteTransportNode(module, node, stub_config):
    fnodes_svc = TransportNodes(stub_config)
    node_id = node.id
    node_name = node.display_name
    try:
        fnodes_svc.delete(node_id)
    except Error as ex:
        api_error = ex.data.convert_to(ApiError)
        module.fail_json(msg='API Error Deleting node: %s'%(api_error.error_message))
    time.sleep(10)
    module.exit_json(changed=True, id=node.id, object_name=node_name)



def main():
    module = AnsibleModule(
        argument_spec=dict(
            display_name=dict(required=True, type='str'),
            node_id=dict(required=True, type='str'),
            maintenance_mode=dict(required=False, type='str'),
            static_ip_pool_id=dict(required=True, type='str'),
            host_switch_name=dict(required=False, type='str'),
            transport_zone_endpoints=dict(required=False, type='list'),
            pnics=dict(required=False, type='dict'),
            uplink_profile=dict(required=False, type='str'),
            state=dict(required=False, type='str', default="present"),
            nsx_manager=dict(required=True, type='str'),
            nsx_username=dict(required=True, type='str'),
            nsx_passwd=dict(required=True, type='str', no_log=True)
        ),
        supports_check_mode=False
    )

    if not HAS_PYNSXT:
        module.fail_json(msg='pynsxt is required for this module')
    session = requests.session()
    session.verify = False
    nsx_url = 'https://%s:%s' % (module.params['nsx_manager'], 443)
    connector = connect.get_requests_connector(
        session=session, msg_protocol='rest', url=nsx_url)
    stub_config = StubConfigurationFactory.new_std_configuration(connector)
    security_context = create_user_password_security_context(module.params["nsx_username"], module.params["nsx_passwd"])
    connector.set_security_context(security_context)
    requests.packages.urllib3.disable_warnings()
#
# TODO: Check Transport Node STATUS before exit on creation and deletion
#  Compate different parameters on UPDATE
    if module.params['state'] == "present":
        node = getTransportNodeByName(module, stub_config)
        if node is None:
            result = createTransportNode(module, stub_config)
            module.exit_json(changed=True, object_name=module.params['display_name'], id=result.id, body=str(result))
        else:
            module.exit_json(changed=False, object_name=module.params['display_name'], id=node.id, message="Transport Node with name %s already exists!"%(module.params['display_name']))

    elif module.params['state'] == "absent":
        node = getTransportNodeByName(module, stub_config)
        if node is None:
            module.exit_json(changed=False, object_name=module.params['display_name'], message="No Transport Node with name %s"%(module.params['display_name']))
        else:
            deleteTransportNode(module, node, stub_config)



from ansible.module_utils.basic import *

if __name__ == "__main__":
    main()
