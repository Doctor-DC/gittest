# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


from SDK.openstack.network.v2 import network
from SDK.openstack.network.v2 import port
from SDK.openstack.network.v2 import subnet
from SDK.openstack.tests.functional import base


class TestPort(base.BaseFunctionalTest):

    IPV4 = 4
    CIDR = "10.100.0.0/24"
    NET_ID = None
    SUB_ID = None
    PORT_ID = None

    def setUp(self):
        super(TestPort, self).setUp()
        self.NET_NAME = self.getUniqueString()
        self.SUB_NAME = self.getUniqueString()
        self.PORT_NAME = self.getUniqueString()
        self.UPDATE_NAME = self.getUniqueString()
        net = self.conn.network.create_network(name=self.NET_NAME)
        assert isinstance(net, network.Network)
        self.assertEqual(self.NET_NAME, net.name)
        self.NET_ID = net.id
        sub = self.conn.network.create_subnet(
            name=self.SUB_NAME,
            ip_version=self.IPV4,
            network_id=self.NET_ID,
            cidr=self.CIDR)
        assert isinstance(sub, subnet.Subnet)
        self.assertEqual(self.SUB_NAME, sub.name)
        self.SUB_ID = sub.id
        prt = self.conn.network.create_port(
            name=self.PORT_NAME,
            network_id=self.NET_ID)
        assert isinstance(prt, port.Port)
        self.assertEqual(self.PORT_NAME, prt.name)
        self.PORT_ID = prt.id

    def tearDown(self):
        sot = self.conn.network.delete_port(
            self.PORT_ID, ignore_missing=False)
        self.assertIsNone(sot)
        sot = self.conn.network.delete_subnet(
            self.SUB_ID, ignore_missing=False)
        self.assertIsNone(sot)
        sot = self.conn.network.delete_network(
            self.NET_ID, ignore_missing=False)
        self.assertIsNone(sot)
        super(TestPort, self).tearDown()

    def test_find(self):
        sot = self.conn.network.find_port(self.PORT_NAME)
        self.assertEqual(self.PORT_ID, sot.id)

    def test_get(self):
        sot = self.conn.network.get_port(self.PORT_ID)
        self.assertEqual(self.PORT_ID, sot.id)
        self.assertEqual(self.PORT_NAME, sot.name)
        self.assertEqual(self.NET_ID, sot.network_id)

    def test_list(self):
        ids = [o.id for o in self.conn.network.ports()]
        self.assertIn(self.PORT_ID, ids)

    def test_update(self):
        sot = self.conn.network.update_port(self.PORT_ID,
                                            name=self.UPDATE_NAME)
        self.assertEqual(self.UPDATE_NAME, sot.name)

    def test_set_tags(self):
        sot = self.conn.network.get_port(self.PORT_ID)
        self.assertEqual([], sot.tags)

        self.conn.network.set_tags(sot, ['blue'])
        sot = self.conn.network.get_port(self.PORT_ID)
        self.assertEqual(['blue'], sot.tags)

        self.conn.network.set_tags(sot, [])
        sot = self.conn.network.get_port(self.PORT_ID)
        self.assertEqual([], sot.tags)
