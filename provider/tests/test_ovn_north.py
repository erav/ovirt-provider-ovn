# Copyright 2017 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
from __future__ import absolute_import

from uuid import UUID
import mock
import pytest

import ovndb.constants as ovnconst

from handlers.base_handler import ConflictError
from ovirt_provider_config_common import dhcp_lease_time
from ovirt_provider_config_common import dhcp_mtu
from ovirt_provider_config_common import dhcp_server_mac
from ovirt_provider_config_common import tenant_id
from ovndb.ovn_north import OvnNorth
from ovndb.ovn_north_mappers import Network
from ovndb.ovn_north_mappers import NetworkMapper
from ovndb.ovn_north_mappers import NetworkPort
from ovndb.ovn_north_mappers import PortMapper
from ovndb.ovn_north_mappers import SubnetConfigError
from ovndb.ovn_north_mappers import SubnetMapper
from ovndb.ovn_north_mappers import UnsupportedDataValueError

from ovntestlib import assert_network_equal
from ovntestlib import assert_port_equal
from ovntestlib import assert_subnet_equal
from ovntestlib import NetworkApiInputMaker
from ovntestlib import PortApiInputMaker
from ovntestlib import SubnetApiInputMaker
from ovntestlib import OvnNetworkRow
from ovntestlib import OvnPortRow
from ovntestlib import OvnRouterPort
from ovntestlib import OvnRouterRow
from ovntestlib import OvnSubnetRow


@mock.patch('ovsdbapp.backend.ovs_idl.connection', autospec=False)
class TestOvnNorth(object):
    MAC_ADDRESS = '01:00:00:00:00:11'
    DEVICE_ID = 'device-id-123456'
    NIC_NAME = 'port_name'
    NETWORK_NAME = 'test_net'
    LOCALNET_NAME = 'localnet'
    LOCALNET_VLAN = 10
    DEVICE_OWNER_OVIRT = 'oVirt'
    SUBNET_CIDR = '1.1.1.0/24'
    VALUE_NETWORK_MTU = 32854

    NETWORK_ID10 = UUID(int=10)
    NETWORK_ID11 = UUID(int=11)
    NETWORK_ID12 = UUID(int=12)
    NETWORK_IDMTU = UUID(int=123)
    NETWORK_NAME10 = 'name10'
    NETWORK_NAME11 = 'name11'
    NETWORK_NAME12 = 'name12'
    NETWORK_NAMEMTU = 'nameMTU'

    PORT_ID01 = UUID(int=1)
    PORT_ID02 = UUID(int=2)
    PORT_ID03 = UUID(int=3)
    PORT_NAME01 = 'port1'
    PORT_NAME02 = 'port2'
    PORT_NAME03 = 'port3'

    PORT_NAME01_FIXED_IP = "1.1.1.1"
    PORT_NAME01_FIXED_IPS = [{
        PortMapper.REST_PORT_IP_ADDRESS: PORT_NAME01_FIXED_IP
    }]

    PORT_1 = OvnPortRow(
        PORT_ID01,
        addresses=MAC_ADDRESS,
        external_ids={
            PortMapper.OVN_NIC_NAME: PORT_NAME01,
            PortMapper.OVN_DEVICE_ID: str(PORT_ID01),
            PortMapper.OVN_DEVICE_OWNER: DEVICE_OWNER_OVIRT,
        }
    )
    PORT_2 = OvnPortRow(
        PORT_ID02,
        addresses=MAC_ADDRESS,
        external_ids={
            PortMapper.OVN_NIC_NAME: PORT_NAME02,
            PortMapper.OVN_DEVICE_ID: str(PORT_ID02),
            PortMapper.OVN_DEVICE_OWNER: DEVICE_OWNER_OVIRT,
        }
    )

    PORT_3 = OvnPortRow(
        PORT_ID03,
        addresses=MAC_ADDRESS,
        external_ids={
            PortMapper.OVN_NIC_NAME: PORT_NAME03,
            PortMapper.OVN_DEVICE_ID: str(PORT_ID03),
            PortMapper.OVN_DEVICE_OWNER: DEVICE_OWNER_OVIRT,
        },
        port_type=ovnconst.LSP_TYPE_LOCALNET,
        options={ovnconst.LSP_OPTION_NETWORK_NAME: LOCALNET_NAME},
        tag=LOCALNET_VLAN
    )

    SUBNET_ID101 = UUID(int=101)
    SUBNET_ID102 = UUID(int=102)
    SUBNET_IDMTU = UUID(int=987)

    SUBNET_101 = OvnSubnetRow(
        SUBNET_ID101,
        network_id=str(NETWORK_ID10),
        cidr=SUBNET_CIDR
    )

    SUBNET_102 = OvnSubnetRow(SUBNET_ID102, cidr=SUBNET_CIDR)

    SUBNET_MTU = OvnSubnetRow(
        SUBNET_IDMTU,
        network_id=str(NETWORK_IDMTU),
        cidr=SUBNET_CIDR
    )

    NETWORK_10 = OvnNetworkRow(NETWORK_ID10, NETWORK_NAME10)
    NETWORK_11 = OvnNetworkRow(
        NETWORK_ID11, NETWORK_NAME11, ports=[PORT_1, PORT_2]
    )
    NETWORK_12 = OvnNetworkRow(
        NETWORK_ID12,
        NETWORK_NAME12
    )
    NETWORK_LOCALNET_12 = OvnNetworkRow(
        NETWORK_ID12,
        NETWORK_NAME12,
        ports=[PORT_3]
    )
    NETWORK_MTU = OvnNetworkRow(
        NETWORK_IDMTU, NETWORK_NAMEMTU,
        external_ids={NetworkMapper.REST_MTU: str(VALUE_NETWORK_MTU)}
    )

    ROUTER_ID20 = UUID(int=20)
    ROUTER_NAME20 = 'router20'

    ROUTER_20 = OvnRouterRow(ROUTER_ID20, ROUTER_NAME20)

    ports = [PORT_1, PORT_2]

    networks = [NETWORK_10, NETWORK_11, NETWORK_LOCALNET_12]

    subnets = [SUBNET_101, SUBNET_102]

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsListCommand',
        autospec=False
    )
    def test_get_networks(self, mock_ls_list, mock_connection):
        mock_ls_list.return_value.execute.return_value = TestOvnNorth.networks

        ovn_north = OvnNorth()
        result = ovn_north.list_networks()

        assert len(result) == 3
        assert_network_equal(
            result[0], Network(ls=TestOvnNorth.NETWORK_10, localnet_lsp=None)
        )
        assert_network_equal(
            result[1], Network(ls=TestOvnNorth.NETWORK_11, localnet_lsp=None)
        )
        localnet_network = TestOvnNorth.NETWORK_LOCALNET_12
        assert_network_equal(
            result[2],
            Network(
                ls=localnet_network, localnet_lsp=localnet_network.ports[0]
            )
        )
        assert mock_ls_list.call_count == 1
        assert mock_ls_list.return_value.execute.call_count == 1

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand',
        autospec=False
    )
    def test_get_network(self, mock_ls_get, mock_connection):
        mock_ls_get.return_value.execute.return_value = (
            TestOvnNorth.NETWORK_10
        )
        ovn_north = OvnNorth()
        result = ovn_north.get_network(str(TestOvnNorth.NETWORK_ID10))

        network = Network(ls=TestOvnNorth.NETWORK_10, localnet_lsp=None)
        assert_network_equal(result, network)
        assert mock_ls_get.call_count == 1
        assert mock_ls_get.return_value.execute.call_count == 1
        assert mock_ls_get.mock_calls[0] == mock.call(
            ovn_north.idl, str(TestOvnNorth.NETWORK_ID10)
        )

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsAddCommand',
        autospec=False
    )
    def test_add_network(self, mock_add_command, mock_connection):
        mock_add_command.return_value.execute.return_value = (
            TestOvnNorth.NETWORK_10
        )
        ovn_north = OvnNorth()
        rest_data = NetworkApiInputMaker(TestOvnNorth.NETWORK_NAME10).get()
        result = ovn_north.add_network(rest_data)

        network = Network(ls=TestOvnNorth.NETWORK_10, localnet_lsp=None)
        assert_network_equal(result, network)
        assert mock_add_command.call_count == 1
        assert mock_add_command.mock_calls[0] == mock.call(
            ovn_north.idl,
            TestOvnNorth.NETWORK_NAME10,
            False,
            external_ids={}
        )

    @mock.patch('ovsdbapp.schema.ovn_northbound.commands.LsAddCommand')
    @mock.patch('ovsdbapp.schema.ovn_northbound.commands.LsGetCommand')
    @mock.patch('ovsdbapp.schema.ovn_northbound.commands.LspAddCommand')
    @mock.patch('ovsdbapp.backend.ovs_idl.command.DbSetCommand')
    def test_add_localnet_network(self, mock_db_set_command,
                                  mock_lsp_add_command, mock_ls_get_command,
                                  mock_ls_add_command, mock_connection):
        mock_ls_get_command.return_value.execute.return_value = (
            TestOvnNorth.NETWORK_LOCALNET_12)
        mock_ls_add_command.return_value.execute.return_value = (
            TestOvnNorth.NETWORK_LOCALNET_12)
        ovn_north = OvnNorth()
        rest_data = NetworkApiInputMaker(
            TestOvnNorth.NETWORK_NAME12,
            provider_type=NetworkMapper.NETWORK_TYPE_VLAN,
            provider_physical_network=TestOvnNorth.LOCALNET_NAME,
            vlan_tag=TestOvnNorth.LOCALNET_VLAN
        ).get()
        result = ovn_north.add_network(rest_data)

        localnet_network = TestOvnNorth.NETWORK_LOCALNET_12
        assert_network_equal(
            result,
            Network(
                ls=localnet_network, localnet_lsp=localnet_network.ports[0]
            )
        )
        assert mock_ls_add_command.call_count == 1
        assert mock_ls_add_command.mock_calls[0] == mock.call(
            ovn_north.idl,
            TestOvnNorth.NETWORK_NAME12,
            False,
            external_ids={}
        )
        assert mock_lsp_add_command.call_count == 1
        assert mock_lsp_add_command.mock_calls[0] == mock.call(
            ovn_north.idl,
            str(TestOvnNorth.NETWORK_LOCALNET_12.uuid),
            ovnconst.LOCALNET_SWITCH_PORT_NAME,
            None,
            None,
            False
        )
        assert mock_db_set_command.call_count == 2
        assert mock_ls_get_command.call_count == 1

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsGetCommand.'
        'execute',
        lambda cmd, check_error: TestOvnNorth.SUBNET_MTU
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsAddCommand.'
        'execute',
        lambda cmd, check_error: TestOvnNorth.SUBNET_MTU
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsListCommand.'
        'execute',
        lambda cmd, check_error: []
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsAddCommand.execute',
        lambda cmd, check_error: TestOvnNorth.NETWORK_MTU
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand.execute',
        lambda cmd, check_error: TestOvnNorth.NETWORK_MTU
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbSetCommand',
        autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsSetOptionsCommand',
        autospec=False
    )
    def test_add_network_with_mtu(
            self,
            mock_setoptions_command,
            mock_dbset_command,
            mock_connection
    ):
        ovn_north = OvnNorth()
        network_rest_data = NetworkApiInputMaker(
            TestOvnNorth.NETWORK_NAMEMTU, mtu=TestOvnNorth.VALUE_NETWORK_MTU
        ).get()
        network_creation_result = ovn_north.add_network(network_rest_data)
        assert_network_equal(
            network_creation_result,
            Network(ls=TestOvnNorth.NETWORK_MTU, localnet_lsp=None)
        )

        # create a subnet associated with the above network
        subnet_rest_data = SubnetApiInputMaker(
            TestOvnNorth.SUBNET_102.external_ids.get(
                SubnetMapper.OVN_NAME
            ),
            cidr=TestOvnNorth.SUBNET_CIDR,
            network_id=str(TestOvnNorth.NETWORK_IDMTU),
            dns_nameservers=['1.1.1.1'],
            gateway_ip='1.1.1.0'
        ).get()

        expected_options_call = mock.call(
            ovn_north.idl,
            TestOvnNorth.SUBNET_IDMTU,
            dns_server='1.1.1.1',
            lease_time=dhcp_lease_time(),
            router='1.1.1.0',
            server_id='1.1.1.0',
            server_mac=dhcp_server_mac(),
            mtu=str(TestOvnNorth.VALUE_NETWORK_MTU)
        )

        subnet_creation_result = ovn_north.add_subnet(subnet_rest_data)
        assert mock_setoptions_command.call_count == 1
        assert mock_setoptions_command.mock_calls[0] == expected_options_call
        assert mock_dbset_command.call_count == 1
        assert_subnet_equal(subnet_creation_result, TestOvnNorth.SUBNET_MTU)

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsGetCommand.'
        'execute',
        lambda cmd, check_error: TestOvnNorth.SUBNET_MTU
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsAddCommand.'
        'execute',
        lambda cmd, check_error: TestOvnNorth.SUBNET_MTU
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsAddCommand.execute',
        lambda cmd, check_error: TestOvnNorth.NETWORK_MTU
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand.execute',
        lambda cmd, check_error: TestOvnNorth.NETWORK_MTU
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbSetCommand',
        autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsSetOptionsCommand',
        autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsListCommand'
    )
    def test_update_networks_mtu(
            self,
            mock_dhcp_list_command,
            mock_setoptions_command,
            mock_dbset_command,
            mock_connection
    ):
        mock_dhcp_list_command.return_value.execute.return_value = []

        ovn_north = OvnNorth()
        network_rest_data = NetworkApiInputMaker(
            TestOvnNorth.NETWORK_NAMEMTU, mtu=TestOvnNorth.VALUE_NETWORK_MTU
        ).get()
        ovn_north.add_network(network_rest_data)

        # create a subnet associated with the above network
        subnet_rest_data = SubnetApiInputMaker(
            TestOvnNorth.SUBNET_102.external_ids.get(
                SubnetMapper.OVN_NAME
            ),
            cidr=TestOvnNorth.SUBNET_CIDR,
            network_id=str(TestOvnNorth.NETWORK_IDMTU),
            dns_nameservers=['1.1.1.1'],
            gateway_ip='1.1.1.0'
        ).get()

        ovn_north.add_subnet(subnet_rest_data)
        new_mtu = 14999
        mtu_update = NetworkApiInputMaker(
            TestOvnNorth.NETWORK_NAMEMTU, mtu=new_mtu
        ).get()

        assert mock_setoptions_command.call_count == 1
        mock_dhcp_list_command.return_value.execute.return_value = [
            TestOvnNorth.SUBNET_MTU
        ]

        ovn_north.update_network(mtu_update, TestOvnNorth.NETWORK_IDMTU)
        expected_external_ids_update = mock.call(
            ovn_north.idl,
            ovnconst.TABLE_LS,
            TestOvnNorth.NETWORK_IDMTU,
            (ovnconst.ROW_LSP_NAME, TestOvnNorth.NETWORK_NAMEMTU),
            (
                ovnconst.ROW_LSP_EXTERNAL_IDS,
                {NetworkMapper.REST_MTU: str(new_mtu)},
            ),
        )
        expected_network_mtu_update = mock.call(
            ovn_north.idl,
            ovnconst.TABLE_DHCP_Options,
            TestOvnNorth.SUBNET_IDMTU,
            (
                ovnconst.ROW_DHCP_OPTIONS,
                {SubnetMapper.OVN_DHCP_MTU: str(new_mtu)}
            )
        )
        assert expected_external_ids_update in mock_dbset_command.mock_calls
        assert expected_network_mtu_update in mock_dbset_command.mock_calls

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand.execute',
        lambda cmd, check_error: OvnNetworkRow(
            TestOvnNorth.NETWORK_ID10,
            TestOvnNorth.NETWORK_NAME10
        )
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbSetCommand',
        autospec=False
    )
    def test_update_network(self, mock_set_command, mock_connection):
        ovn_north = OvnNorth()
        rest_data = NetworkApiInputMaker(TestOvnNorth.NETWORK_NAME10).get()
        result = ovn_north.update_network(rest_data, TestOvnNorth.NETWORK_ID10)

        network = Network(ls=TestOvnNorth.NETWORK_10, localnet_lsp=None)
        assert_network_equal(result, network)
        assert mock_set_command.call_count == 1
        assert mock_set_command.mock_calls[0] == mock.call(
            ovn_north.idl,
            ovnconst.TABLE_LS,
            TestOvnNorth.NETWORK_ID10,
            (NetworkMapper.REST_NETWORK_NAME, TestOvnNorth.NETWORK_NAME10)
        )

    @mock.patch('ovsdbapp.schema.ovn_northbound.commands.LsGetCommand')
    @mock.patch('ovsdbapp.backend.ovs_idl.command.DbSetCommand')
    def test_update_localnet_network(self,
                                     mock_set_command, mock_ls_get_command,
                                     mock_connection):
        mock_ls_get_command.return_value.execute.return_value = (
            TestOvnNorth.NETWORK_LOCALNET_12
        )
        ovn_north = OvnNorth()
        rest_data = NetworkApiInputMaker(
            TestOvnNorth.NETWORK_NAME12,
            provider_type=NetworkMapper.NETWORK_TYPE_VLAN,
            provider_physical_network=TestOvnNorth.LOCALNET_NAME,
            vlan_tag=TestOvnNorth.LOCALNET_VLAN
        ).get()
        result = ovn_north.update_network(rest_data, TestOvnNorth.NETWORK_ID12)

        localnet_network = TestOvnNorth.NETWORK_LOCALNET_12
        assert_network_equal(
            result,
            Network(
                ls=localnet_network, localnet_lsp=localnet_network.ports[0]
            )
        )
        assert mock_set_command.call_count == 2
        assert mock_set_command.mock_calls[0] == mock.call(
            ovn_north.idl,
            ovnconst.TABLE_LS,
            TestOvnNorth.NETWORK_ID12,
            (NetworkMapper.REST_NETWORK_NAME, TestOvnNorth.NETWORK_NAME12)
        )
        assert mock_ls_get_command.call_count == 2

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand.execute',
        lambda cmd, check_error: TestOvnNorth.NETWORK_10
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsDelCommand',
        autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsListCommand.'
        'execute',
        lambda cmd, check_error: []
    )
    def test_delete_network(self, mock_del_command, mock_connection):
        ovn_north = OvnNorth()
        ovn_north.delete_network(TestOvnNorth.NETWORK_ID10)
        assert mock_del_command.call_count == 1
        expected_del_call = mock.call(
            ovn_north.idl,
            TestOvnNorth.NETWORK_ID10,
            False
        )
        assert mock_del_command.mock_calls[0] == expected_del_call

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsListCommand.execute',
        lambda cmd, check_error: TestOvnNorth.networks
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LspGetCommand.execute',
        lambda cmd, check_error: TestOvnNorth.PORT_1
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsListCommand.'
        'execute',
        lambda cmd, check_error: [TestOvnNorth.SUBNET_101]
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand.execute',
        lambda cmd, check_error: TestOvnNorth.NETWORK_10
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbClearCommand.execute',
        lambda cmd, check_error: []
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LspAddCommand',
        autospec=False
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbSetCommand',
        autospec=False
    )
    def test_add_port(self, mock_db_set, mock_add_command, mock_connection):
        mock_add_command.return_value.execute.return_value = (
            TestOvnNorth.PORT_1
        )
        ovn_north = OvnNorth()
        rest_data = PortApiInputMaker(
            TestOvnNorth.PORT_NAME01, str(TestOvnNorth.NETWORK_ID10),
            device_id=TestOvnNorth.DEVICE_ID,
            device_owner=TestOvnNorth.DEVICE_OWNER_OVIRT, admin_state_up=True,
            mac_address=TestOvnNorth.MAC_ADDRESS,
            fixed_ips=TestOvnNorth.PORT_NAME01_FIXED_IPS
        ).get()
        result = ovn_north.add_port(rest_data)

        # ID11 because this network has the port in TestOvnNorth.networks
        logical_switch = OvnNetworkRow(
            TestOvnNorth.NETWORK_ID11, name=TestOvnNorth.NETWORK_NAME11,
            ports=[TestOvnNorth.PORT_1]
        )
        port = NetworkPort(lsp=TestOvnNorth.PORT_1, ls=logical_switch,
                           dhcp_options=None, lrp=None)
        assert_port_equal(result, port)

        assert mock_add_command.call_count == 1
        mock_add_command.assert_called_with(
            ovn_north.idl,
            str(TestOvnNorth.NETWORK_ID10),
            TestOvnNorth.PORT_NAME01,
            None,
            None,
            False
        )

        assert mock_db_set.call_count == 3

        assert mock_db_set.mock_calls[0] == mock.call(
            ovn_north.idl,
            ovnconst.TABLE_LSP,
            str(TestOvnNorth.PORT_ID01),
            (
                ovnconst.ROW_LSP_NAME,
                str(TestOvnNorth.PORT_ID01)
            )
        )

        assert mock_db_set.mock_calls[2] == mock.call(
            ovn_north.idl,
            ovnconst.TABLE_LSP,
            TestOvnNorth.PORT_ID01,
            (
                ovnconst.ROW_LSP_EXTERNAL_IDS,
                {PortMapper.OVN_DEVICE_ID: TestOvnNorth.DEVICE_ID}
            ),
            (
                ovnconst.ROW_LSP_EXTERNAL_IDS,
                {PortMapper.OVN_NIC_NAME: TestOvnNorth.PORT_NAME01}
            ),
            (
                ovnconst.ROW_LSP_EXTERNAL_IDS,
                {PortMapper.OVN_DEVICE_OWNER: TestOvnNorth.DEVICE_OWNER_OVIRT}
            ),
            (
                ovnconst.ROW_LSP_ENABLED,
                True
            )
        )

        assert mock_db_set.mock_calls[4] == mock.call(
            ovn_north.idl,
            ovnconst.TABLE_LSP,
            TestOvnNorth.PORT_ID01,
            (ovnconst.ROW_LSP_DHCPV4_OPTIONS, TestOvnNorth.SUBNET_ID101),
            (
                ovnconst.ROW_LSP_ADDRESSES,
                ['{mac_address} {ip_address}'.format(
                    mac_address=TestOvnNorth.MAC_ADDRESS,
                    ip_address=TestOvnNorth.PORT_NAME01_FIXED_IP
                )]
            ),
        )

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsListCommand.'
        'execute',
        lambda cmd, check_error: []
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsListCommand.execute',
        lambda cmd, check_error: TestOvnNorth.networks
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LspListCommand.execute',
        lambda cmd, check_error: TestOvnNorth.ports
    )
    def test_list_ports(self, mock_connection):
        ovn_north = OvnNorth()
        ports = ovn_north.list_ports()
        assert len(ports) == 2
        logical_switch = OvnNetworkRow(
            TestOvnNorth.NETWORK_ID11, name=TestOvnNorth.NETWORK_NAME11,
            ports=[TestOvnNorth.PORT_1, TestOvnNorth.PORT_2]
        )
        first_port = NetworkPort(
            lsp=TestOvnNorth.PORT_1,
            ls=logical_switch,
            dhcp_options=None,
            lrp=None
        )
        second_port = NetworkPort(
            lsp=TestOvnNorth.PORT_2,
            ls=logical_switch,
            dhcp_options=None,
            lrp=None
        )

        assert_port_equal(ports[0], first_port)
        assert_port_equal(ports[1], second_port)

    @mock.patch('ovsdbapp.schema.ovn_northbound.commands.LspGetCommand.'
                'execute',
                lambda cmd, check_error: OvnPortRow(
                    TestOvnNorth.PORT_ID01,
                    external_ids={
                        PortMapper.OVN_DEVICE_OWNER:
                            TestOvnNorth.DEVICE_OWNER_OVIRT
                    }
                ))
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LspDelCommand',
        autospec=False
    )
    def test_delete_port(self, mock_del_command, mock_connection):
        ovn_north = OvnNorth()
        ovn_north.delete_port(TestOvnNorth.PORT_ID01)
        assert mock_del_command.call_count == 1
        expected_del_call = mock.call(
            ovn_north.idl,
            TestOvnNorth.PORT_ID01,
            None,
            False
        )
        assert mock_del_command.mock_calls[0] == expected_del_call

    @mock.patch('ovsdbapp.schema.ovn_northbound.commands.LspGetCommand.'
                'execute',
                lambda cmd, check_error: OvnPortRow(
                    TestOvnNorth.PORT_ID01,
                    external_ids={
                        PortMapper.OVN_DEVICE_OWNER:
                            PortMapper.DEVICE_OWNER_ROUTER
                    }
                ))
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LspDelCommand',
        autospec=False
    )
    def test_delete_router_port(self, mock_del_command, mock_connection):
        ovn_north = OvnNorth()
        with pytest.raises(ConflictError):
            ovn_north.delete_port(TestOvnNorth.PORT_ID01)
        assert mock_del_command.call_count == 0

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsListCommand.'
        'execute',
        lambda cmd, check_error: TestOvnNorth.subnets
    )
    def test_list_subnets(self, mock_connection):
        ovn_north = OvnNorth()
        result = ovn_north.list_subnets()
        assert len(result) == 2
        assert result[0]['id'] == str(TestOvnNorth.SUBNET_ID101)
        assert result[0]['network_id'] == str(TestOvnNorth.NETWORK_ID10)
        assert result[0]['tenant_id'] == tenant_id()

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsGetCommand.'
        'execute',
        lambda cmd, check_error: TestOvnNorth.SUBNET_101
    )
    def test_get_subnet(self, mock_connection):
        ovn_north = OvnNorth()
        result = ovn_north.get_subnet(TestOvnNorth.SUBNET_ID101)
        assert result['id'] == str(TestOvnNorth.SUBNET_ID101)
        assert result['network_id'] == str(TestOvnNorth.NETWORK_ID10)
        gateway_ip = TestOvnNorth.SUBNET_101.options['router']
        assert result['gateway_ip'] == gateway_ip

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsDelCommand',
        autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsGetCommand.'
        'execute',
        lambda cmd, check_error: TestOvnNorth.SUBNET_101
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand.execute',
        lambda cmd, check_error: TestOvnNorth.NETWORK_10
    )
    def test_delete_subnet(self, mock_del_command, mock_connection):
        ovn_north = OvnNorth()
        ovn_north.delete_subnet(TestOvnNorth.SUBNET_ID101)
        assert mock_del_command.call_count == 1
        expected_del_call = mock.call(
            ovn_north.idl,
            TestOvnNorth.SUBNET_ID101,
        )
        assert mock_del_command.mock_calls[0] == expected_del_call

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsListCommand.'
        'execute',
        lambda cmd, check_error: []
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand.execute',
        lambda cmd, check_error: TestOvnNorth.NETWORK_10
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsGetCommand.'
        'execute',
        lambda cmd, check_error: TestOvnNorth.SUBNET_102
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbSetCommand',
        autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsAddCommand',
        autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsSetOptionsCommand',
        autospec=False
    )
    def test_add_subnet(self, mock_setoptions_command, mock_add_command,
                        mock_dbset_command, mock_connection):
        add_execute = mock_add_command.return_value.execute
        add_execute.return_value = TestOvnNorth.SUBNET_102
        ovn_north = OvnNorth()
        rest_data = SubnetApiInputMaker(
            TestOvnNorth.SUBNET_102.external_ids.get(
                SubnetMapper.OVN_NAME
            ),
            cidr=TestOvnNorth.SUBNET_CIDR,
            network_id=str(TestOvnNorth.NETWORK_ID10),
            dns_nameservers=['1.1.1.1'], gateway_ip='1.1.1.0'
        ).get()
        result = ovn_north.add_subnet(rest_data)
        assert_subnet_equal(result, TestOvnNorth.SUBNET_102)
        assert mock_dbset_command.call_count == 1
        assert mock_add_command.call_count == 1
        assert mock_setoptions_command.call_count == 1

        expected_dbset_call = mock.call(
            ovn_north.idl,
            ovnconst.TABLE_LS,
            str(TestOvnNorth.NETWORK_ID10),
            (
                ovnconst.ROW_LS_OTHER_CONFIG,
                {NetworkMapper.OVN_SUBNET: TestOvnNorth.SUBNET_CIDR}
            ),
        )
        assert mock_dbset_command.mock_calls[0] == expected_dbset_call

        expected_add_call = mock.call(
            ovn_north.idl,
            TestOvnNorth.SUBNET_CIDR,
            ovirt_name=TestOvnNorth.SUBNET_102.external_ids.get(
                    SubnetMapper.OVN_NAME
                ),
            ovirt_network_id=str(TestOvnNorth.NETWORK_ID10)
        )
        assert mock_add_command.mock_calls[0] == expected_add_call

        expected_options_call = mock.call(
            ovn_north.idl,
            TestOvnNorth.SUBNET_ID102,
            dns_server='1.1.1.1',
            lease_time=dhcp_lease_time(),
            router='1.1.1.0',
            server_id='1.1.1.0',
            server_mac=dhcp_server_mac(),
            mtu=dhcp_mtu()
        )
        assert mock_setoptions_command.mock_calls[0] == expected_options_call

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsListCommand.'
        'execute',
        lambda cmd, check_error: []
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand.execute',
        lambda cmd, check_error: TestOvnNorth.NETWORK_10
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsGetCommand.'
        'execute',
        lambda cmd, check_error: TestOvnNorth.SUBNET_102
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbSetCommand',
        autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsAddCommand',
        autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsSetOptionsCommand',
        autospec=False
    )
    def test_add_subnet_no_dns(self, mock_setoptions_command, mock_add_command,
                               mock_dbset_command, mock_connection):
        add_execute = mock_add_command.return_value.execute
        add_execute.return_value = TestOvnNorth.SUBNET_102
        ovn_north = OvnNorth()
        rest_data = SubnetApiInputMaker(
            'subnet_name', cidr=TestOvnNorth.SUBNET_CIDR,
            network_id=str(TestOvnNorth.NETWORK_ID10), dns_nameservers=[],
            gateway_ip='1.1.1.0'
        ).get()
        result = ovn_north.add_subnet(rest_data)
        assert_subnet_equal(result, TestOvnNorth.SUBNET_102)
        assert mock_dbset_command.call_count == 1
        assert mock_add_command.call_count == 1
        assert mock_setoptions_command.call_count == 1

    """
    TODO: This test causes Jenkins to get stuck. Commenting out until the
    issue is solved.

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsListCommand.execute',
        lambda cmd, check_error: TestOvnNorth.networks
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LspGetCommand.execute',
        lambda cmd, check_error: TestOvnNorth.PORT_1
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsListCommand.'
        'execute',
        lambda cmd, check_error: []
    )
    @mock.patch(
        'ovsdbapp.backend.ovs_idl.command.DbSetCommand',
        autospec=False
    )
    def test_update_subnet(self, mock_db_set, mock_connection):

        ovn_north = OvnNorth()
        rest_data = {
           SubnetMapper.REST_SUBNET_NAME: 'subnet_name',
           SubnetMapper.REST_SUBNET_ENABLE_DHCP: True,
           SubnetMapper.REST_SUBNET_NETWORK_ID: TestOvnNorth.NETWORK_ID10,
           SubnetMapper.REST_SUBNET_DNS_NAMESERVERS: ['8.8.8.8'],
           SubnetMapper.REST_SUBNET_GATEWAY_IP: '172.16.0.254',
           SubnetMapper.REST_SUBNET_IP_VERSION: 4,
           SubnetMapper.REST_SUBNET_CIDR: '172.16.0.0/24'
        }
        ovn_north.update_subnet(rest_data, TestOvnNorth.SUBNET_ID101)

        assert mock_db_set.call_count == 2

        assert mock_db_set.mock_calls[0] == mock.call(
            ovn_north.idl,
            OvnNorth.TABLE_LS,
            TestOvnNorth.NETWORK_ID10,
            (
                OvnNorth.ROW_LS_OTHER_CONFIG,
                {NetworkMapper.OVN_SUBNET:
                    rest_data[SubnetMapper.REST_SUBNET_CIDR]}
            )
        )

        assert mock_db_set.mock_calls[2] == mock.call(
            ovn_north.idl,
            OvnNorth.TABLE_DHCP_Options,
            TestOvnNorth.SUBNET_ID101,
            (
                OvnNorth.ROW_DHCP_OPTIONS,
                {SubnetMapper.OVN_DHCP_SERVER_ID:
                    rest_data[SubnetMapper.REST_SUBNET_CIDR].split('/', 1)[0]}
            ),
            (
                OvnNorth.ROW_DHCP_CIDR,
                rest_data[SubnetMapper.REST_SUBNET_CIDR]
            ),
            (
                OvnNorth.ROW_DHCP_EXTERNAL_IDS,
                {SubnetMapper.OVN_NAME:
                    rest_data[SubnetMapper.REST_SUBNET_NAME]}
            ),
            (
                OvnNorth.ROW_DHCP_EXTERNAL_IDS,
                {SubnetMapper.OVN_NETWORK_ID:
                    rest_data[SubnetMapper.REST_SUBNET_NETWORK_ID]}
            ),
            (
                OvnNorth.ROW_DHCP_OPTIONS,
                {SubnetMapper.OVN_GATEWAY:
                    rest_data[SubnetMapper.REST_SUBNET_GATEWAY_IP]}
            ),
            (
                OvnNorth.ROW_DHCP_OPTIONS,
                {SubnetMapper.OVN_DNS_SERVER:
                    rest_data[SubnetMapper.REST_SUBNET_DNS_NAMESERVERS][0]}
            ),
            (
                OvnNorth.ROW_DHCP_OPTIONS,
                {SubnetMapper.OVN_DHCP_LEASE_TIME: dhcp_lease_time()}
            ),
            (
                OvnNorth.ROW_DHCP_OPTIONS,
                {SubnetMapper.OVN_DHCP_SERVER_MAC: dhcp_server_mac()}
            )
        )
    """

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand.execute',
        lambda cmd, check_error: OvnNetworkRow(
            TestOvnNorth.NETWORK_ID10,
            TestOvnNorth.NETWORK_NAME10
        )
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsListCommand.'
        'execute',
        lambda cmd, check_error: TestOvnNorth.subnets
    )
    def test_subnet_add_duplicate_network(self, mock_connection):
        ovn_north = OvnNorth()
        rest_data = SubnetApiInputMaker(
            'subnet_name', cidr=TestOvnNorth.SUBNET_CIDR,
            network_id=str(TestOvnNorth.NETWORK_ID10), gateway_ip='1.1.1.0'
        ).get()
        with pytest.raises(SubnetConfigError):
            ovn_north.add_subnet(rest_data)

    def test_subnet_dhcp_enabled_false(self, mock_connection):
        ovn_north = OvnNorth()
        rest_data = SubnetApiInputMaker(
            'subnet_name', cidr=TestOvnNorth.SUBNET_CIDR, network_id='',
            dns_nameservers=['1.1.1.1'], gateway_ip='1.1.1.0',
            enable_dhcp=False
        ).get()
        with pytest.raises(UnsupportedDataValueError):
            ovn_north.add_subnet(rest_data)

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand.execute',
        lambda cmd, check_error: None
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsGetCommand.execute',
        lambda cmd, check_error: TestOvnNorth.NETWORK_10
    )
    def test_subnet_add_invalid_network(self, mock_connection):
        ovn_north = OvnNorth()
        rest_data = SubnetApiInputMaker(
            'subnet_name', cidr=TestOvnNorth.SUBNET_CIDR, network_id=7,
            dns_nameservers=['1.1.1.1'], gateway_ip='1.1.1.0'
        ).get()
        with pytest.raises(SubnetConfigError):
            ovn_north.add_subnet(rest_data)

    def test_port_admin_state_up_none_enabled_none(self, mock_connection):
        self._port_admin_state(mock_connection, None, None, False)

    def test_port_admin_state_up_true_enabled_none(self, mock_connection):
        self._port_admin_state(mock_connection, [True], None, True)

    def test_port_admin_state_up_false_enabled_none(self, mock_connection):
        self._port_admin_state(mock_connection, [False], None, False)

    def test_port_admin_state_up_none_enabled_true(self, mock_connection):
        self._port_admin_state(mock_connection, None, [True], False)

    def test_port_admin_state_up_true_enabled_true(self, mock_connection):
        self._port_admin_state(mock_connection, [True], [True], True)

    def test_port_admin_state_up_false_enabled_true(self, mock_connection):
        self._port_admin_state(mock_connection, [False], [True], False)

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.DhcpOptionsListCommand.'
        'execute',
        lambda cmd, check_error: []
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LsListCommand',
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LspGetCommand'
    )
    def _port_admin_state(self, mock_connection, is_up, is_enabled, result,
                          mock_lsp_get, mock_ls_list):
        port_row = OvnPortRow(
            TestOvnNorth.PORT_ID01,
            external_ids={
                PortMapper.OVN_NIC_NAME: TestOvnNorth.PORT_NAME01,
                PortMapper.OVN_DEVICE_ID: str(TestOvnNorth.PORT_ID01),
                PortMapper.OVN_DEVICE_OWNER: TestOvnNorth.DEVICE_OWNER_OVIRT,
            }
        )
        port_row.up = is_up
        port_row.enabled = is_enabled

        mock_lsp_get.return_value.execute.return_value = port_row
        mock_ls_list.return_value.execute.return_value = [
            OvnNetworkRow(TestOvnNorth.NETWORK_ID11, ports=[port_row])
        ]

        ovn_north = OvnNorth()
        port = ovn_north.get_port(TestOvnNorth.PORT_ID01)
        assert port[PortMapper.REST_PORT_ADMIN_STATE_UP] == result

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.impl_idl.OvnNbApiIdlImpl.lookup',
    )
    def test_get_router(self, mock_lookup, mock_connection):
        mock_lookup.return_value = TestOvnNorth.ROUTER_20
        ovn_north = OvnNorth()
        result = ovn_north.get_router(str(TestOvnNorth.ROUTER_ID20))

        assert result['id'] == str(TestOvnNorth.ROUTER_ID20)
        assert result['name'] == str(TestOvnNorth.ROUTER_NAME20)

        assert mock_lookup.call_args == mock.call(
            ovnconst.TABLE_LR, str(TestOvnNorth.ROUTER_ID20)
        )

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LrDelCommand',
        autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.impl_idl.OvnNbApiIdlImpl.lookup',
    )
    def test_delete_router(self, mock_lookup, mock_del_command,
                           mock_connection):
        mock_lookup.return_value = TestOvnNorth.ROUTER_20
        ovn_north = OvnNorth()

        ovn_north.delete_router(str(TestOvnNorth.ROUTER_ID20))

        assert mock_lookup.call_args == mock.call(
            ovnconst.TABLE_LR, str(TestOvnNorth.ROUTER_ID20)
        )

        assert mock_del_command.call_count == 1
        expected_del_call = mock.call(
            ovn_north.idl,
            str(TestOvnNorth.ROUTER_ID20),
            False
        )
        assert mock_del_command.mock_calls[0] == expected_del_call

    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.commands.LrDelCommand',
        autospec=False
    )
    @mock.patch(
        'ovsdbapp.schema.ovn_northbound.impl_idl.OvnNbApiIdlImpl.lookup',
    )
    def test_delete_router_fail(self, mock_lookup, mock_del_command,
                                mock_connection):
        mock_lookup.return_value = OvnRouterRow(
            TestOvnNorth.ROUTER_ID20,
            ports=[OvnRouterPort()]
        )
        ovn_north = OvnNorth()
        with pytest.raises(ConflictError):
            ovn_north.delete_router(str(TestOvnNorth.ROUTER_ID20))

        assert mock_lookup.call_args == mock.call(
            ovnconst.TABLE_LR, str(TestOvnNorth.ROUTER_ID20)
        )
        assert mock_del_command.call_count == 0
