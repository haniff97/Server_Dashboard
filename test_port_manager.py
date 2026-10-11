import unittest
from unittest.mock import patch
from services import port_manager as pm

SERVICE = {'id':'mqtt','name':'MQTT','manager':'systemd','target':'mosquitto.service','ports':[{'protocol':'TCP','port':1883}]}

class PortManagerTests(unittest.TestCase):
    def test_parse_ipv6_and_missing_owner(self):
        sockets = pm.parse_sockets('tcp LISTEN 0 100 [::]:1883 [::]:* users:(("mosquitto",pid=2,fd=1))\nudp UNCONN 0 0 0.0.0.0:53 0.0.0.0:*')
        self.assertIn('[::]', sockets['TCP',1883]['addresses'])
        self.assertEqual(sockets['UDP',53]['owners'],set())

    @patch.dict('os.environ', {'PORT_CONTROL_TOKEN':''})
    @patch.object(pm,'configured_services',return_value=[])
    @patch.object(pm,'command',return_value='tcp LISTEN 0 10 0.0.0.0:53 0.0.0.0:*')
    def test_missing_setup_is_explained(self,*mocks):
        rows, errors = pm.inventory()
        self.assertFalse(rows[0]['controllable'])
        self.assertTrue(any('port_services.json' in error for error in errors))
        self.assertTrue(any('PORT_CONTROL_TOKEN' in error for error in errors))

    @patch.dict('os.environ', {'PORT_CONTROL_TOKEN':'test'})
    @patch.object(pm,'configured_services',return_value=[SERVICE])
    @patch.object(pm,'command',return_value='')
    @patch.object(pm,'service_running',return_value=False)
    def test_stopped_service_retained(self,*mocks):
        rows, errors = pm.inventory()
        self.assertEqual(rows[0]['status'],'Stopped')
        self.assertFalse(rows[0]['bound'])
        self.assertTrue(rows[0]['controllable'])

    @patch.dict('os.environ', {'PORT_CONTROL_TOKEN':'test'})
    @patch.object(pm,'command')
    def test_invalid_token_cannot_execute(self,command):
        with self.assertRaises(PermissionError): pm.control('mqtt','stop','wrong')
        command.assert_not_called()

    @patch.dict('os.environ', {'PORT_CONTROL_TOKEN':'test'})
    @patch.object(pm,'configured_services',return_value=[SERVICE])
    @patch.object(pm,'service_running',side_effect=[False,True])
    @patch.object(pm,'command',return_value='')
    def test_start_uses_registered_target(self,command,*mocks):
        pm.control('mqtt','start','test')
        command.assert_any_call(['systemctl','start','mosquitto.service'])

    @patch.dict('os.environ', {'PORT_CONTROL_TOKEN':'test'})
    @patch.object(pm,'configured_services',return_value=[SERVICE])
    @patch.object(pm,'service_running',return_value=False)
    @patch.object(pm,'command',return_value='tcp LISTEN 0 10 0.0.0.0:1883 0.0.0.0:*')
    def test_start_rejects_occupied_port(self,command,*mocks):
        with self.assertRaises(RuntimeError): pm.control('mqtt','start','test')
        self.assertEqual(command.call_count,1)

if __name__ == '__main__': unittest.main()
