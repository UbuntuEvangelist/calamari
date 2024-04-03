

import os
import mock
from tests.util import load_fixture
from tests.config import TestConfig

os.environ.setdefault("CALAMARI_CONFIG", os.path.join(os.path.dirname(__file__), "../../dev/calamari.conf"))

from django.utils.unittest.case import TestCase
from django.utils.unittest.case import skipIf
from mock import Mock, patch

from cthulhu.manager.server_monitor import ServerMonitor, ServiceId


config = TestConfig()

OSD_MAP = load_fixture('osd_map.json')
MON_MAP = load_fixture('mon_map.json')
BAD_MAP = load_fixture('bad_map.json')
BAD_MAP2 = load_fixture('bad_map2.json')
BAD_MAP3 = load_fixture('bad_map3.json')

# After migrating osd.1 from gravel2 to gravel1
OSD_MAP_MIGRATED = load_fixture('osd_map_migrated.json')
MON_CEPH_SERVICES_MIGRATED = load_fixture('gravel1.rockery_services_migrated.json')

# After removing osd.1
OSD_MAP_1_REMOVED = load_fixture('osd_map_1_removed.json')

# After removing mon
MON_MAP_1_REMOVED = load_fixture('mon_map_1_removed.json')

FSID = "d530413f-9030-4daa-aba5-dfe3b6c4bb25"
MON_CEPH_SERVICES = load_fixture('gravel1.rockery_services.json')
MON_HOSTNAME = 'gravel1'
MON_FQDN = 'gravel1.rockery'

OSD_HOSTNAME = 'gravel2'
OSD_FQDN = 'gravel2.rockery'
OSD_CEPH_SERVICES = load_fixture('gravel2.rockery_services.json')

MDS1_HOSTNAME = 'gravel1'
MDS2_HOSTNAME = 'gravel2'
MDS1_FQDN = "gravel1.rockery"
MDS2_FQDN = "gravel2.rockery"
MDS1_SERVICES = load_fixture('mds1_services.json')
MDS2_SERVICES = load_fixture('mds2_services.json')
MDS_MAP = load_fixture('mds_map.json')
MDS_MAP_1_REMOVED = load_fixture('mds_map_1_removed.json')


class TestServiceDetection(TestCase):
    """
    Exercise ServerMonitor with mock data for a two-server cluster with
    one mon and two OSDs.
    """
    def setUp(self):
        super(TestServiceDetection, self).setUp()
        grains = {
            MON_FQDN: {
                'fqdn': MON_FQDN,
                'host': MON_HOSTNAME
            },
            OSD_FQDN: {
                'fqdn': OSD_FQDN,
                'host': OSD_HOSTNAME
            }
        }
        ServerMonitor._get_grains = mock.Mock(side_effect=lambda fqdn: grains[fqdn])

    def tearDown(self):
        super(TestServiceDetection, self).tearDown()

    @skipIf(config.get('testing', 'ceph_control') == 'converged', "")
    def test_managed_servers(self):
        """
        That managed servers (those sending salt messages) generate
        a correct view of service locations
        """
        sm = ServerMonitor(Mock(), Mock(), Mock())
        sm.on_server_heartbeat(MON_FQDN, MON_CEPH_SERVICES)
        sm.on_server_heartbeat(OSD_FQDN, OSD_CEPH_SERVICES)

        self.assertEqual(len(sm.servers), 2)
        self.assertEqual(len(sm.services), 3)
        self.assertEqual(len(sm.fsid_services), 1)
        self.assertEqual(len(sm.hostname_to_server), 2)

        self.assertListEqual(sm.servers.keys(), [MON_FQDN, OSD_FQDN])
        self.assertEqual(sm.servers[OSD_FQDN].fqdn, OSD_FQDN)
        self.assertListEqual(sm.servers[MON_FQDN].services.keys(), [
            ServiceId(FSID, 'mon', MON_HOSTNAME)
        ])
        self.assertListEqual(sm.servers[OSD_FQDN].services.keys(), [
            ServiceId(FSID, 'osd', '1'),
            ServiceId(FSID, 'osd', '0')
        ])

    @skipIf(config.get('testing', 'ceph_control') == 'converged', "")
    def test_unmanaged_servers(self):
        """
        That when only the mons are sending salt messages, we generate
        a correct view of service locations including OSDs.
        """
        sm = ServerMonitor(Mock(), Mock(), Mock())

        sm.on_server_heartbeat(MON_FQDN, MON_CEPH_SERVICES)
        sm.on_osd_map(OSD_MAP)

        self.assertEqual(len(sm.servers), 2)
        self.assertEqual(len(sm.services), 3)
        self.assertEqual(len(sm.fsid_services), 1)
        self.assertEqual(len(sm.hostname_to_server), 2)

        self.assertListEqual(sm.servers[MON_FQDN].services.keys(), [
            ServiceId(FSID, 'mon', MON_HOSTNAME)
        ])
        self.assertListEqual(sm.servers[OSD_HOSTNAME].services.keys(), [
            ServiceId(FSID, 'osd', '1'),
            ServiceId(FSID, 'osd', '0')
        ])

    @skipIf(config.get('testing', 'ceph_control') == 'converged', "")
    def test_unmanaged_managed_transition(self):
        """
        That when a pesky user doesn't initially install salt on OSD servers
        but later adds it, we correctly transition from paying attention
        to the CRUSH config to paying attention to the salt data, and
        fill in the correct FQDNs.
        """
        sm = ServerMonitor(Mock(), Mock(), Mock())

        sm.on_server_heartbeat(MON_FQDN, MON_CEPH_SERVICES)
        sm.on_osd_map(OSD_MAP)

        self.assertListEqual(sm.servers.keys(), [MON_FQDN, OSD_HOSTNAME])
        self.assertListEqual(sm.servers[MON_FQDN].services.keys(), [
            ServiceId(FSID, 'mon', MON_HOSTNAME)
        ])
        self.assertListEqual(sm.servers[OSD_HOSTNAME].services.keys(), [
            ServiceId(FSID, 'osd', '1'),
            ServiceId(FSID, 'osd', '0')
        ])

        sm.on_server_heartbeat(OSD_FQDN, OSD_CEPH_SERVICES)

        self.assertListEqual(sm.servers.keys(), [MON_FQDN, OSD_FQDN])
        self.assertEqual(sm.servers[OSD_FQDN].fqdn, OSD_FQDN)
        self.assertListEqual(sm.servers[MON_FQDN].services.keys(), [
            ServiceId(FSID, 'mon', MON_HOSTNAME)
        ])
        self.assertListEqual(sm.servers[OSD_FQDN].services.keys(), [
            ServiceId(FSID, 'osd', '1'),
            ServiceId(FSID, 'osd', '0')
        ])

    @skipIf(config.get('testing', 'ceph_control') == 'converged', "")
    def test_unmanaged_service_relocate(self):
        """
        That when an OSD disappears from one server's salt.services output
        and reappears on another server, this is reflected in the state.
        """
        sm = ServerMonitor(Mock(), Mock(), Mock())

        sm.on_server_heartbeat(MON_FQDN, MON_CEPH_SERVICES)
        sm.on_osd_map(OSD_MAP)

        # osd.1 initially on unmanaged server OSD
        self.assertEqual(sm.services[ServiceId(FSID, 'osd', "1")].server_state.fqdn, OSD_HOSTNAME)

        sm.on_server_heartbeat(MON_FQDN, MON_CEPH_SERVICES_MIGRATED)
        sm.on_osd_map(OSD_MAP_MIGRATED)

        # osd.1 now on managed server MON
        self.assertEqual(sm.services[ServiceId(FSID, 'osd', "1")].server_state.fqdn, MON_FQDN)

        # Check the servers' lists of services are up to date too
        self.assertListEqual(sm.servers[MON_FQDN].services.keys(), [
            ServiceId(FSID, 'osd', '1'),
            ServiceId(FSID, 'mon', MON_HOSTNAME)

        ])
        self.assertListEqual(sm.servers[OSD_HOSTNAME].services.keys(), [
            ServiceId(FSID, 'osd', '0')
        ])

    @skipIf(config.get('testing', 'ceph_control') == 'converged', "")
    def test_delete_managed(self):
        """
        That when a managed server is removed, it no longer appears
        in the server/service data.
        """
        sm = ServerMonitor(Mock(), Mock(), Mock())

        sm.on_server_heartbeat(MON_FQDN, MON_CEPH_SERVICES)
        sm.on_server_heartbeat(OSD_FQDN, OSD_CEPH_SERVICES)

        sm.delete(OSD_FQDN)

        # The two OSD services, and the 'osd' server should be gone
        self.assertEqual(len(sm.servers), 1)
        self.assertEqual(len(sm.services), 1)
        self.assertEqual(len(sm.fsid_services), 1)
        self.assertEqual(len(sm.hostname_to_server), 1)

        self.assertListEqual(sm.servers.keys(), [MON_FQDN])
        self.assertListEqual(sm.services.keys(), [ServiceId(FSID, 'mon', MON_HOSTNAME)])
        self.assertListEqual([s.id for s in sm.fsid_services[FSID]], [ServiceId(FSID, 'mon', MON_HOSTNAME)])
        self.assertListEqual(sm.hostname_to_server.keys(), [MON_HOSTNAME])

    @skipIf(config.get('testing', 'ceph_control') == 'converged', "")
    def test_remove_osd(self):
        """
        That when an OSD is disappears from the OSD map, it is also removed
        from ServerMonitor's worldview
        """
        sm = ServerMonitor(Mock(), Mock(), Mock())

        sm.on_server_heartbeat(MON_FQDN, MON_CEPH_SERVICES)
        sm.on_server_heartbeat(OSD_FQDN, OSD_CEPH_SERVICES)

        self.assertListEqual(sm.services.keys(), [
            ServiceId(FSID, 'osd', '0'),
            ServiceId(FSID, 'osd', '1'),
            ServiceId(FSID, 'mon', MON_HOSTNAME)
        ])

        sm.on_osd_map(OSD_MAP_1_REMOVED)

        self.assertListEqual(sm.services.keys(), [
            ServiceId(FSID, 'osd', '0'),
            ServiceId(FSID, 'mon', MON_HOSTNAME)
        ])

    @skipIf(config.get('testing', 'ceph_control') == 'converged', "")
    def test_remove_mon(self):
        """
        That when a mon disappears from the mon map, ServerMonitor notices
        """
        sm = ServerMonitor(Mock(), Mock(), Mock())

        sm.on_server_heartbeat(MON_FQDN, MON_CEPH_SERVICES)
        sm.on_server_heartbeat(OSD_FQDN, OSD_CEPH_SERVICES)
        sm.on_mon_map(MON_MAP, {'election_epoch': 1})

        self.assertListEqual(sm.services.keys(), [
            ServiceId(FSID, 'osd', '0'),
            ServiceId(FSID, 'osd', '1'),
            ServiceId(FSID, 'mon', MON_HOSTNAME)
        ])

        sm.on_mon_map(MON_MAP_1_REMOVED, {'election_epoch': 1})
        self.assertListEqual(sm.services.keys(), [
            ServiceId(FSID, 'osd', '0'),
            ServiceId(FSID, 'osd', '1')
        ])

    @skipIf(config.get('testing', 'ceph_control') == 'converged', "")
    def test_remove_mds(self):
        """
        That when an mds disappears from the mds map, ServerMonitor notices
        """
        sm = ServerMonitor(Mock(), Mock(), Mock())

        sm.on_server_heartbeat(MDS1_FQDN, MDS1_SERVICES)
        sm.on_server_heartbeat(MDS2_FQDN, MDS2_SERVICES)
        sm.on_mds_map(FSID, MDS_MAP)

        self.assertListEqual(sm.services.keys(), [
            ServiceId(FSID, 'mds', MDS1_HOSTNAME),
            ServiceId(FSID, 'mds', MDS2_HOSTNAME)
        ])

        sm.on_mds_map(FSID, MDS_MAP_1_REMOVED)
        self.assertListEqual(sm.services.keys(), [
            ServiceId(FSID, 'mds', MDS1_HOSTNAME)
        ])

    def test_get_osd_to_host_mapping_empty(self):
        """
        That we get an empty mapping when osd_map contains no data
        """
        osd_map = {'tree': {'nodes': []}, 'osds': []}
        sm = ServerMonitor(Mock(), Mock(), Mock())
        self.assertEqual({}, sm.get_hostname_to_osds(osd_map))

    @patch('cthulhu.manager.server_monitor.socket')
    def test_get_osd_to_host_mapping_osd_metadata_absent(self, mocket):
        """
        That we get a mapping when osd_map contains osd_metadata no data
        """
        mocket.getnameinfo.return_value = [OSD_HOSTNAME]
        mocket.getfqdn.return_value = OSD_FQDN
        osd_map = {"osds": [{"cluster_addr": "192.34.58.142:6808/14001122",
                             "osd": 0}]}
        sm = ServerMonitor(Mock(), Mock(), Mock())
        self.assertEqual({('gravel2.rockery', 'gravel2'): [{'cluster_addr': '192.34.58.142:6808/14001122', 'osd': 0}]}, sm.get_hostname_to_osds(osd_map))

    @patch('cthulhu.manager.server_monitor.socket')
    def test_get_osd_to_host_mapping_osd_metadata_exists(self, mocket):
        """
        That we get a mapping when osd_map contains osd_metadata no data
        """
        osd_map = {"osds": [{"cluster_addr": "192.34.58.142:6808/14001122",
                             "osd": 0}],
                   "osd_metadata": [{
                       "back_addr": "192.34.58.142:6808/14001122",
                       "hostname": "gravel2.rockery",
                       "id": 0,
                       "hb_back_addr": "192.34.58.142:6809/14001122",
                       "hb_front_addr": "192.34.58.142:6810/14001122",
                       "front_addr": "192.34.58.142:6800/1122"}]}

        sm = ServerMonitor(Mock(), Mock(), Mock())
        self.assertEqual({('gravel2.rockery', 'gravel2'): [{'cluster_addr': '192.34.58.142:6808/14001122', 'osd': 0}]}, sm.get_hostname_to_osds(osd_map))

        self.assertEqual(False, mocket.called)

    @patch('cthulhu.manager.server_monitor.socket')
    def test_get_osd_to_host_mapping_osd_metadata_exists_contains_hostname(self, mocket):
        """
        That we get a mapping when osd_map contains osd_metadata no data
        """
        mocket.getnameinfo.return_value = [OSD_HOSTNAME]
        mocket.getfqdn.return_value = OSD_FQDN
        osd_map = {"osds": [{"cluster_addr": "192.34.58.142:6808/14001122",
                             "osd": 0}],
                   "osd_metadata": [{
                       "back_addr": "192.34.58.142:6808/14001122",
                       "hostname": "gravel2",
                       "id": 0,
                       "hb_back_addr": "192.34.58.142:6809/14001122",
                       "hb_front_addr": "192.34.58.142:6810/14001122",
                       "front_addr": "192.34.58.142:6800/1122"}]}

        sm = ServerMonitor(Mock(), Mock(), Mock())
        self.assertEqual({('gravel2.rockery', 'gravel2'): [{'cluster_addr': '192.34.58.142:6808/14001122', 'osd': 0}]}, sm.get_hostname_to_osds(osd_map))

    @patch('cthulhu.manager.server_monitor.socket')
    def test_get_osd_to_host_mapping_osd_metadata_partial_exists(self, mocket):
        """
        That we get a mapping when osd_map contains osd_metadata no data
        """
        mocket.getnameinfo.return_value = [OSD_HOSTNAME]
        mocket.getfqdn.return_value = OSD_FQDN
        osd_map = {"osds": [{"cluster_addr": "192.34.58.142:6808/14001122",
                             "osd": 0},
                            {"cluster_addr": "192.34.58.142:6802/17383",
                             "osd": 1}],
                   "osd_metadata": [{
                       "back_addr": "192.34.58.142:6808/14001122",
                       "hostname": "gravel2",
                       "id": 0,
                       "hb_back_addr": "192.34.58.142:6809/14001122",
                       "hb_front_addr": "192.34.58.142:6810/14001122",
                       "front_addr": "192.34.58.142:6800/1122"}]}

        sm = ServerMonitor(Mock(), Mock(), Mock())
        self.assertEqual({('gravel2.rockery', 'gravel2'): [{'cluster_addr': '192.34.58.142:6808/14001122', 'osd': 0}, {'cluster_addr': '192.34.58.142:6802/17383', 'osd': 1}]}, sm.get_hostname_to_osds(osd_map))

    @patch('cthulhu.manager.server_monitor.socket')
    def test_get_osd_to_host_mapping_osd_down_and_out_from_epoch1(self, mocket):
        """
        That we don't get a mapping when osd_map contains osd_metadata no data
        """
        mocket.getnameinfo.return_value = [OSD_HOSTNAME]
        mocket.getfqdn.return_value = OSD_FQDN
        osd_map = {"osd_metadata": [],
                   "osds": [{"cluster_addr": ":/0",
                             "down_at": 0,
                             "heartbeat_back_addr": ":/0",
                             "heartbeat_front_addr": ":/0",
                             "in": 0,
                             "last_clean_begin": 0,
                             "last_clean_end": 0,
                             "lost_at": 0,
                             "osd": 0,
                             "primary_affinity": 1.0,
                             "public_addr": ":/0",
                             "state": [
                                 "exists",
                                 "new"
                             ],
                             "up": 0,
                             "up_from": 0,
                             "up_thru": 0,
                             "uuid": "f53e0a25-d29c-4aa3-9a2e-f6ebee538f8e",
                             "weight": 0.0}]}

        sm = ServerMonitor(Mock(), Mock(), Mock())
        self.assertEqual({}, sm.get_hostname_to_osds(osd_map))

    @patch('cthulhu.manager.server_monitor.socket')
    def test_on_osd_map(self, mocket):
        def get_name_info(addr, _):
            if addr == ":/0":
                return ['']
            else:
                return [OSD_HOSTNAME]

        def get_fqdn(thing):
            if thing == [""]:
                return ''
            else:
                return OSD_FQDN

        mocket.getnameinfo = get_name_info
        mocket.getfqdn = get_fqdn

        sm = ServerMonitor(Mock(), Mock(), Mock())
        sm.on_osd_map(BAD_MAP)
        sm.on_osd_map(BAD_MAP2)
        sm.on_osd_map(BAD_MAP3)
