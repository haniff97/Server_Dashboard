import ast
from pathlib import Path
import threading
from types import SimpleNamespace
from unittest.mock import Mock
import unittest


def flow():
    tree = ast.parse((Path(__file__).parent/'controllers/plug_controller.py').read_text())
    nodes = [n for n in tree.body if getattr(n,'name',None) in ('persist_reading','refresh_device_energy')]
    db = SimpleNamespace(**{k:Mock() for k in ('insert_energy','aggregate_daily','get_today_summary','get_current_month_usage','aggregate_monthly')})
    state = SimpleNamespace(energy_cache_lock=threading.Lock(),energy_cache={'plug':{'total_kwh':0,'cost_rm':0}})
    aws = SimpleNamespace(publish=Mock(side_effect=RuntimeError('Cloud unavailable')))
    mqtt = Mock()
    ns = dict(db=db,state=state,aws_iot_publisher=aws,publish_local_mqtt=mqtt,
              tuya_local=SimpleNamespace(DEVICES={'plug':{'id':'test'}}))
    exec(compile(ast.Module(nodes,type_ignores=[]),'<energy>', 'exec'),ns)
    return ns,db,state,aws,mqtt


class EnergyPipelineTests(unittest.TestCase):
    def test_cloud_failure_does_not_prevent_storage(self):
        ns,db,state,aws,mqtt = flow()
        ns['persist_reading']('plug',dict(device_name='Test',watts=47.7,voltage=230,current_ma=210),.1325)
        self.assertEqual(db.insert_energy.call_args.kwargs['wh_delta'],.1325)
        db.aggregate_daily.assert_called_once_with('test')
        mqtt.assert_called_once()

    def test_monthly_failure_does_not_discard_today(self):
        ns,db,state,aws,mqtt = flow()
        db.get_today_summary.return_value = {'total_kwh':1,'cost_rm':.1943}
        db.get_current_month_usage.return_value = 10
        db.aggregate_monthly.side_effect = RuntimeError('Summary unavailable')
        with self.assertRaises(RuntimeError): ns['refresh_device_energy']('plug')
        self.assertEqual(state.energy_cache['plug']['total_kwh'],1)
        self.assertEqual(state.energy_cache['plug']['cost_rm'],.1943)
        self.assertEqual(state.energy_cache['plug']['month_kwh'],10)

    def test_daily_summary_failure_does_not_skip_publish(self):
        ns,db,state,aws,mqtt = flow()
        db.aggregate_daily.side_effect = RuntimeError('Summary unavailable')
        ns['persist_reading']('plug',dict(device_name='Test',watts=47.7,voltage=230,current_ma=210),.1)
        db.insert_energy.assert_called_once()
        aws.publish.assert_called_once()
        mqtt.assert_called_once()

if __name__ == '__main__': unittest.main()
